import contextlib
import copy
import csv
from datetime import date
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from boring_alpha.cli import run_aftertax, run_backtest
from boring_alpha.config import load_config
from boring_alpha.data import load_market_data
from boring_alpha.metrics import calculate_metrics
from boring_alpha.report import code_fingerprint
from boring_alpha.sweep import run_sweep, write_sweep_report
from boring_alpha.tax.reconstruct import reconstruct_result, tax_run_name

REPO_ROOT = Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def test_checked_in_synthetic_config_runs_end_to_end(self) -> None:
        source = (REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            config_path = root / "configs" / "demo.toml"
            config_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = run_backtest(config_path)
            self.assertEqual(status, 0)
            runs = list((root / "experiments" / "BA-001").iterdir())
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0] / "manifest.json").exists())
            self.assertIn("SYNTHETIC DATA", output.getvalue())

    def test_run_backtest_honours_the_configured_benchmark(self) -> None:
        # `load_config` folds a `[benchmark]` table into strategy_spec_sha256,
        # so `run_backtest` must actually use it. With the table present the
        # gating benchmark is an annual target-exposure allocation, which
        # enters on the first session of 2018 and rebalances only every
        # following January; a fixed monthly benchmark would trade every
        # month instead.
        source = (REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            output_dir = root / "run-output"
            output_dir.mkdir()
            source = source.replace('output_dir = "../experiments"', f'output_dir = "{output_dir}"')
            source += '\n[benchmark]\nexposure = 0.6\nrebalance = "annual"\n'
            config_path = root / "configs" / "demo.toml"
            config_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = run_backtest(config_path)
            self.assertEqual(status, 0)
            runs = list((output_dir / "BA-001").iterdir())
            self.assertEqual(len(runs), 1)
            trades_text = (runs[0] / "benchmark_trades.csv").read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(trades_text)))
            fill_dates = [date.fromisoformat(row["date"]) for row in rows]
            self.assertTrue(fill_dates, "expected at least one benchmark fill")
            self.assertTrue(
                all(fill_date.month == 1 for fill_date in fill_dates),
                f"expected every fill in January, got months {sorted({d.month for d in fill_dates})}",
            )
            self.assertGreater(
                len({fill_date.year for fill_date in fill_dates}),
                1,
                "expected fills across more than one year",
            )

    def test_engine_warnings_are_printed(self) -> None:
        source = (REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml").read_text(encoding="utf-8")
        # Shorten the warm-up so the decisive pre-start month-end has no history.
        source = source.replace('start = "2016-12-01"', 'start = "2017-06-01"')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            config_path = root / "configs" / "demo.toml"
            config_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run_backtest(config_path)
        self.assertIn("no signal at month-end 2017-12-29", output.getvalue())


SWEEP_PERIODS = """
[BA-001.development]
start = 2021-01-01
end = 2022-12-31
"""

SWEEP_CONFIG = """
[strategy]
id = "BA-001"
name = "After-tax Test"
symbols = ["A", "B", "C", "D"]
lookback_months = 12
sleeve_weight = 0.25
[portfolio]
initial_cash = 10000
[execution]
cost_bps = 10
[data]
source = "synthetic"
start = "2019-10-01"
end = "2024-12-31"
seed = 21
annual_cash_rate = 0.02
[backtest]
start = "2021-01-01"
end = "2022-12-31"
[evaluation]
period = "development"
[clusters]
growth = ["A", "B"]
defensive = ["C", "D"]
[report]
output_dir = "../experiments"
"""

TAX_ONLY = """
[tax]
distributions_path = "../data/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.5
[tax.qualified_fraction]
A = 1.0
B = 1.0
C = 0.0
D = 0.0
[tax.gains_class]
A = "standard"
B = "standard"
C = "standard"
D = "commodity_pool"
"""


class AfterTaxCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "configs").mkdir()
        (self.root / "configs" / "evaluation_periods.toml").write_text(SWEEP_PERIODS, encoding="utf-8")
        plain = self.root / "configs" / "plain.toml"
        plain.write_text(SWEEP_CONFIG, encoding="utf-8")
        taxed = self.root / "configs" / "taxed.toml"
        taxed.write_text(SWEEP_CONFIG + TAX_ONLY, encoding="utf-8")
        self.policy = self.root / "configs" / "policy.toml"
        self.policy.write_text(TAX_ONLY.replace("../data/", "../data/"), encoding="utf-8")
        self.plain_config = load_config(plain)
        self.taxed_config = load_config(taxed)
        self.data = load_market_data(self.plain_config)
        self._write_distributions()
        _, self.plain_dir = write_sweep_report(
            self.plain_config, self.data, run_sweep(self.plain_config, self.data)
        )
        _, self.taxed_dir = write_sweep_report(
            self.taxed_config, self.data, run_sweep(self.taxed_config, self.data)
        )
        self.distributions = self.root / "data" / "distributions_daily.csv"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_distributions(self) -> None:
        (self.root / "data").mkdir()
        lines = ["date,symbol,close,dividend"]
        for day in self.data.dates:
            for symbol in sorted(self.data.by_date[day]):
                lines.append(f"{day.isoformat()},{symbol},{self.data.by_date[day][symbol].close!r},0.0")
        self.distributions_text = "\n".join(lines) + "\n"
        (self.root / "data" / "distributions_daily.csv").write_text(self.distributions_text, encoding="utf-8")
        (self.root / "data" / "manifest.json").write_text(
            json.dumps({"methodology": "synthetic-test", "created_at": "2026-09-04T00:00:00+00:00",
                        "splits": {s: [] for s in "ABCD"}}),
            encoding="utf-8",
        )

    def _outputs(self, sweep_dir: Path) -> list[Path]:
        return sorted(sweep_dir.glob("tax-*.json"))

    def test_aftertax_reproduces_the_in_sweep_result_exactly(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            status = run_aftertax(self.plain_dir, self.policy, self.distributions)
        self.assertEqual(status, 0)
        outputs = self._outputs(self.plain_dir)
        self.assertEqual(len(outputs), 1)
        produced = json.loads(outputs[0].read_text(encoding="utf-8"))
        in_sweep = json.loads((self.taxed_dir / "tax.json").read_text(encoding="utf-8"))
        self.assertEqual(produced["runs"], in_sweep["runs"])
        self.assertEqual(produced["tax_policy_sha256"], in_sweep["tax_policy_sha256"])
        self.assertEqual(produced["distributions_sha256"], in_sweep["distributions_sha256"])
        self.assertEqual(produced["source"], "aftertax")
        self.assertEqual(produced["artifact_schema"], 6)

    def test_the_output_name_carries_policy_distributions_and_code(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        name = self._outputs(self.plain_dir)[0].name
        in_sweep = json.loads((self.taxed_dir / "tax.json").read_text(encoding="utf-8"))
        self.assertEqual(
            name,
            f"tax-{in_sweep['tax_policy_sha256'][:12]}-{in_sweep['distributions_sha256'][:12]}"
            f"-{code_fingerprint()[:12]}.json",
        )

    def test_running_twice_is_idempotent(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        self.assertEqual(len(self._outputs(self.plain_dir)), 1)

    def test_an_archived_distributions_input_makes_the_sweep_self_contained(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            status = run_aftertax(self.taxed_dir, self.policy, None)
        self.assertEqual(status, 0)
        produced = json.loads(self._outputs(self.taxed_dir)[0].read_text(encoding="utf-8"))
        in_sweep = json.loads((self.taxed_dir / "tax.json").read_text(encoding="utf-8"))
        self.assertEqual(produced["runs"], in_sweep["runs"])
        self.assertEqual(produced["distributions_manifest"], in_sweep["distributions_manifest"])

    def test_a_sweep_without_an_archive_needs_the_distributions_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "--distributions"):
            run_aftertax(self.plain_dir, self.policy, None)

    def test_the_policy_must_cover_the_sweep_s_universe(self) -> None:
        narrow = self.root / "configs" / "narrow.toml"
        narrow.write_text(TAX_ONLY.replace("D = 0.0\n", "").replace('D = "commodity_pool"\n', ""), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "is missing D"):
            run_aftertax(self.plain_dir, narrow, self.distributions)

    def test_the_command_prints_one_line_per_run(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        text = output.getvalue()
        self.assertIn("strategy", text)
        self.assertIn("cash", text)
        self.assertIn("worst", text)

    def _as_legacy_archive(self, sweep_dir: Path) -> dict:
        path = sweep_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.pop("artifacts_sha256")
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    def test_empty_legacy_trade_ledger_is_rejected_by_independent_replay(self) -> None:
        self._as_legacy_archive(self.plain_dir)
        path = self.plain_dir / "variants" / "base" / "strategy_trades.csv"
        header = path.read_text(encoding="utf-8").splitlines()[0]
        path.write_text(header + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "replay.*mismatch"):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        self.assertEqual(self._outputs(self.plain_dir), [])

    def test_new_archive_trade_checksums_are_verified(self) -> None:
        path = self.plain_dir / "variants" / "base" / "strategy_trades.csv"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum mismatch.*strategy_trades"):
            run_aftertax(self.plain_dir, self.policy, self.distributions)

    def test_missing_legacy_variant_is_refused(self) -> None:
        self._as_legacy_archive(self.plain_dir)
        (self.plain_dir / "variants" / "lookback_9").rename(self.root / "missing-variant")
        with self.assertRaisesRegex(ValueError, "variant coverage.*lookback_9"):
            run_aftertax(self.plain_dir, self.policy, self.distributions)

    def test_truncated_legacy_equity_curve_is_refused(self) -> None:
        self._as_legacy_archive(self.plain_dir)
        path = self.plain_dir / "variants" / "exposure_matched" / "benchmark_equity.csv"
        rows = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join([rows[0], *rows[2:]]) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "declared backtest window"):
            run_aftertax(self.plain_dir, self.policy, self.distributions)

    def test_legacy_market_archive_must_match_its_recorded_fingerprint(self) -> None:
        self._as_legacy_archive(self.plain_dir)
        path = self.plain_dir / "input_cash.csv.gz"
        rows = gzip.decompress(path.read_bytes()).decode("utf-8").splitlines()
        day, _ = rows[1].split(",")
        rows[1] = f"{day},1.5"
        path.write_bytes(gzip.compress(("\n".join(rows) + "\n").encode("utf-8"), mtime=0))
        with self.assertRaisesRegex(ValueError, "market data fingerprint"):
            run_aftertax(self.plain_dir, self.policy, self.distributions)

    def test_distribution_archive_must_match_its_canonical_fingerprint(self) -> None:
        self._as_legacy_archive(self.taxed_dir)
        path = self.taxed_dir / "input_distributions.csv.gz"
        rows = gzip.decompress(path.read_bytes()).decode("utf-8").splitlines()
        day, symbol, close, dividend = rows[1].split(",")
        rows[1] = f"{day},{symbol},{float(close) * 2},{dividend}"
        path.write_bytes(gzip.compress(("\n".join(rows) + "\n").encode("utf-8"), mtime=0))
        with self.assertRaisesRegex(ValueError, "distributions fingerprint"):
            run_aftertax(self.taxed_dir, self.policy, None)

    def test_old_source_hash_is_provenance_and_is_never_claimed_as_archive_verification(self) -> None:
        manifest = self._as_legacy_archive(self.taxed_dir)
        block = manifest["distributions_manifest"]
        block.pop("fingerprint_version")
        block.pop("csv_sha256")
        block["sha256"] = "a" * 64
        manifest["distributions_sha256"] = "a" * 64
        (self.taxed_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(run_aftertax(self.taxed_dir, self.policy, None), 0)
        self.assertIn("legacy-unverified", output.getvalue())
        produced = json.loads(self._outputs(self.taxed_dir)[0].read_text(encoding="utf-8"))
        self.assertNotEqual(produced["distributions_sha256"], "a" * 64)
        provenance = json.loads((self.taxed_dir / "distributions_provenance.jsonl").read_text().splitlines()[-1])
        self.assertEqual(provenance["legacy_claimed_source_sha256"], "a" * 64)
        self.assertTrue(provenance["distributions_verification"].startswith("legacy-unverified"))

    def test_future_rows_and_refetch_metadata_do_not_change_posthoc_identity(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        original = self._outputs(self.plain_dir)[0].read_bytes()
        self.distributions.write_text(self.distributions.read_text() + "2025-01-02,A,999.0,100.0\n")
        manifest_path = self.distributions.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["created_at"] = "2027-01-01T00:00:00+00:00"
        manifest["splits"]["A"].append({"date": "2025-01-02", "ratio": "2:1"})
        manifest_path.write_text(json.dumps(manifest))
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(self.plain_dir, self.policy, self.distributions)
        self.assertEqual(len(self._outputs(self.plain_dir)), 1)
        self.assertEqual(self._outputs(self.plain_dir)[0].read_bytes(), original)

    def test_nonpositive_wealth_and_nonworst_identity_failure_are_visible(self) -> None:
        scenarios = copy.deepcopy(json.loads((self.taxed_dir / "tax.json").read_text())["runs"]["strategy"])
        keys = list(scenarios)
        scenarios[keys[0]]["metrics"]["after_tax_cagr"] = None
        scenarios[keys[-1]]["metrics"]["after_tax_cagr"] = 0.5
        scenarios[keys[-1]]["identity_checks"]["income_plus_gain_passed"] = False
        output = io.StringIO()
        with patch("boring_alpha.cli.run_scenarios", return_value=scenarios), contextlib.redirect_stdout(output):
            self.assertEqual(run_aftertax(self.plain_dir, self.policy, self.distributions), 0)
        self.assertIn("n/a", output.getvalue())
        self.assertIn(f"strategy / {keys[-1]}: income_plus_gain_passed", output.getvalue())


class ReconstructionTests(unittest.TestCase):
    def test_a_reconstructed_run_has_the_archived_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "configs" / "evaluation_periods.toml").write_text(SWEEP_PERIODS, encoding="utf-8")
            path = root / "configs" / "run.toml"
            path.write_text(SWEEP_CONFIG, encoding="utf-8")
            config = load_config(path)
            data = load_market_data(config)
            sweep = run_sweep(config, data)
            _, sweep_dir = write_sweep_report(config, data, sweep)
            base = sweep_dir / "variants" / "base"
            rebuilt = reconstruct_result(
                "base", base / "strategy_equity.csv", base / "strategy_trades.csv", 10000.0
            )
            metrics = calculate_metrics(rebuilt, data)
            archived = json.loads((sweep_dir / "criteria.json").read_text(encoding="utf-8"))
            for key, value in archived["variants"]["base"]["strategy"].items():
                self.assertAlmostEqual(float(metrics[key]), float(value), places=9, msg=key)
            self.assertEqual(len(rebuilt.fills), len(sweep.runs["base"][0].fills))

    def test_run_names_mirror_the_sweep_s(self) -> None:
        self.assertEqual(tax_run_name("base", "strategy"), "strategy")
        self.assertEqual(tax_run_name("base", "benchmark"), "benchmark")
        self.assertEqual(tax_run_name("exposure_matched", "strategy"), "exposure_matched")
        self.assertEqual(tax_run_name("exposure_matched", "benchmark"), "cash")
        self.assertEqual(tax_run_name("static_full", "strategy"), "static_full")
        self.assertIsNone(tax_run_name("static_full", "benchmark"))
        self.assertEqual(tax_run_name("lookback_9", "strategy"), "variant:lookback_9")
        self.assertIsNone(tax_run_name("lookback_9", "benchmark"))


if __name__ == "__main__":
    unittest.main()
