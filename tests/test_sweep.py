from datetime import date
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_config
from boring_alpha.data import load_market_data
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.signals.trend import ExcludingSleeve, MultiAssetTrend, ScaledAllocation
from boring_alpha.sweep import GRID, run_sweep, write_sweep_report

PERIODS = """
[BA-001.development]
start = 2021-01-01
end = 2022-12-31
"""

CONFIG = """
[strategy]
id = "BA-001"
name = "Sweep Test"
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


def _config(root: Path):
    (root / "configs").mkdir()
    (root / "configs" / "evaluation_periods.toml").write_text(PERIODS, encoding="utf-8")
    path = root / "configs" / "run.toml"
    path.write_text(CONFIG, encoding="utf-8")
    return load_config(path)


class PolicyTests(unittest.TestCase):
    def _data(self) -> MarketData:
        days = [date(2023, 12, 29), date(2024, 12, 31)]
        bars = [PriceBar(day, sym, 100.0 + i * 50, 100.0 + i * 50)
                for i, day in enumerate(days) for sym in ("A", "B")]
        return MarketData(bars, {day: 1.0 for day in days}, source="test")

    def test_excluding_a_sleeve_zeroes_only_that_weight(self) -> None:
        base = MultiAssetTrend(("A", "B"), 12, 0.5)
        snapshot = ExcludingSleeve(base, "A").snapshot(self._data(), date(2024, 12, 31))
        assert snapshot is not None
        self.assertEqual(snapshot.target_weights["A"], 0.0)
        self.assertEqual(snapshot.target_weights["B"], 0.5)
        self.assertIn("without A", snapshot.name)

    def test_scaling_matches_a_target_gross_exposure(self) -> None:
        scaled = ScaledAllocation(("A", "B"), 12, 0.5, 0.6)
        snapshot = scaled.snapshot(self._data(), date(2024, 12, 31))
        assert snapshot is not None
        self.assertAlmostEqual(sum(snapshot.target_weights.values()), 0.6)

    def test_scaling_never_exceeds_full_investment(self) -> None:
        scaled = ScaledAllocation(("A", "B"), 12, 0.5, 1.8)
        snapshot = scaled.snapshot(self._data(), date(2024, 12, 31))
        assert snapshot is not None
        self.assertAlmostEqual(sum(snapshot.target_weights.values()), 1.0)


class SweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = _config(self.root)
        self.data = load_market_data(self.config)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sweep_runs_every_variant_in_the_grid(self) -> None:
        sweep = run_sweep(self.config, self.data)
        self.assertEqual(set(sweep.variants), set(GRID))
        for name in GRID:
            self.assertIn("strategy", sweep.variants[name])
            self.assertIn("static", sweep.variants[name])

    def test_the_dropped_sleeve_is_ranked_by_excess_return_over_cash(self) -> None:
        sweep = run_sweep(self.config, self.data)
        excess = sweep.excess_contributions
        self.assertEqual(sweep.top_sleeve, max(excess, key=excess.get))
        # Raw P&L is reported too, but the charter ranks on excess over cash.
        self.assertNotEqual(sweep.excess_contributions, sweep.contributions)

    def test_sweep_records_provenance_and_the_unseal_reason(self) -> None:
        sweep = run_sweep(self.config, self.data)
        _, sweep_dir = write_sweep_report(self.config, self.data, sweep, unseal_reason="reviewed")
        records = [
            json.loads(line)
            for line in (sweep_dir / "provenance.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(records[0]["unseal_reason"], "reviewed")
        self.assertIn("git_commit", records[0])

    def test_sweep_manifest_carries_the_run_warnings_and_data_window(self) -> None:
        sweep = run_sweep(self.config, self.data)
        _, sweep_dir = write_sweep_report(self.config, self.data, sweep)
        manifest = json.loads((sweep_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(any("SYNTHETIC DATA" in w for w in manifest["warnings"]))
        self.assertIn("data_start", manifest)
        self.assertIn("data_end", manifest)

    def test_criteria_identify_the_strategy_and_the_code(self) -> None:
        sweep = run_sweep(self.config, self.data)
        _, sweep_dir = write_sweep_report(self.config, self.data, sweep)
        criteria = json.loads((sweep_dir / "criteria.json").read_text(encoding="utf-8"))
        self.assertEqual(criteria["strategy_id"], "BA-001")
        self.assertIn("code_sha256", criteria)
        self.assertIn("artifact_schema", criteria)

    def test_warnings_from_every_variant_are_collected(self) -> None:
        sweep = run_sweep(self.config, self.data)
        # The 15-month variant needs more anchor history than the base rule, so
        # its warm-up warnings must be recorded rather than silently dropped.
        tagged = [w for w in sweep.warnings if w.startswith("lookback_15:")]
        self.assertTrue(tagged, sweep.warnings)
        self.assertFalse([w for w in sweep.warnings if w.startswith("base:")], sweep.warnings)

    def test_criteria_are_evaluated_from_the_grid(self) -> None:
        sweep = run_sweep(self.config, self.data)
        self.assertEqual([c.name for c in sweep.outcome.criteria], ["C1", "C2", "C3", "C4", "C5"])

    def test_cluster_attribution_covers_every_sleeve(self) -> None:
        sweep = run_sweep(self.config, self.data)
        self.assertEqual(set(sweep.clusters), {"growth", "defensive"})
        self.assertAlmostEqual(
            sum(sweep.clusters.values()), sum(sweep.excess_contributions.values()), places=6
        )

    def test_the_report_leads_with_the_pre_registered_result(self) -> None:
        sweep = run_sweep(self.config, self.data)
        _, sweep_dir = write_sweep_report(self.config, self.data, sweep)
        summary = (sweep_dir / "summary.md").read_text(encoding="utf-8")
        self.assertLess(summary.index("Pre-registered"), summary.index("Stability checks"))
        self.assertIn("not a menu", summary)
        criteria = json.loads((sweep_dir / "criteria.json").read_text(encoding="utf-8"))
        self.assertEqual(len(criteria["criteria"]), 5)

    def test_rerunning_a_sweep_reuses_its_directory(self) -> None:
        sweep = run_sweep(self.config, self.data)
        first, _ = write_sweep_report(self.config, self.data, sweep)
        second, _ = write_sweep_report(self.config, self.data, sweep)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()


class SweepReproducibilityTests(SweepTests):
    def test_two_independent_recomputations_produce_identical_artifacts(self) -> None:
        """Content addressing is only honest if the content is deterministic."""

        def snapshot(directory: Path) -> dict[str, bytes]:
            return {
                str(path.relative_to(directory)): path.read_bytes()
                for path in sorted(directory.rglob("*"))
                if path.is_file() and path.name != "provenance.jsonl"
            }

        first_sweep = run_sweep(self.config, self.data)
        first_id, sweep_dir = write_sweep_report(self.config, self.data, first_sweep)
        written = snapshot(sweep_dir)
        self.assertIn("variants/base/strategy_equity.csv", written)
        self.assertIn("input_prices.csv.gz", written)

        reloaded = load_market_data(self.config)
        second_sweep = run_sweep(self.config, reloaded)
        second_id, second_dir = write_sweep_report(self.config, reloaded, second_sweep)

        self.assertEqual(first_id, second_id)
        self.assertEqual(sweep_dir, second_dir)
        self.assertEqual(snapshot(second_dir), written)


class ProfileGateTests(unittest.TestCase):
    def test_an_unregistered_strategy_id_is_refused_before_any_run(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "configs").mkdir()
        (root / "configs" / "evaluation_periods.toml").write_text(
            PERIODS.replace("BA-001", "W-001"), encoding="utf-8"
        )
        path = root / "configs" / "run.toml"
        path.write_text(CONFIG.replace('id = "BA-001"', 'id = "W-001"'), encoding="utf-8")
        config = load_config(path)
        with self.assertRaisesRegex(ValueError, "no evaluation profile.*W-001"):
            run_sweep(config, load_market_data(config))


TAX_TABLE = """
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
BENCHMARK_TABLE = '\n[benchmark]\nexposure = 0.6\nrebalance = "annual"\n'


def _write_distributions(root: Path, data: MarketData) -> None:
    """A distributions file consistent with synthetic prices: unadjusted equals
    adjusted (no dividends were ever paid), one row per priced session and symbol."""

    (root / "data").mkdir(exist_ok=True)
    lines = ["date,symbol,close,dividend"]
    for day in data.dates:
        for symbol in sorted(data.by_date[day]):
            lines.append(f"{day.isoformat()},{symbol},{data.by_date[day][symbol].close!r},0.0")
    (root / "data" / "distributions_daily.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "data" / "manifest.json").write_text(
        json.dumps({"methodology": "synthetic-test", "created_at": "2026-09-04T00:00:00+00:00",
                    "splits": {symbol: [] for symbol in ("A", "B", "C", "D")}}),
        encoding="utf-8",
    )


def _config_with(root: Path, extra: str):
    (root / "configs").mkdir()
    (root / "configs" / "evaluation_periods.toml").write_text(PERIODS, encoding="utf-8")
    path = root / "configs" / "run.toml"
    path.write_text(CONFIG + extra, encoding="utf-8")
    return load_config(path)


class TaxWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = _config_with(self.root, TAX_TABLE)
        self.data = load_market_data(self.config)
        _write_distributions(self.root, self.data)
        self.sweep = run_sweep(self.config, self.data)
        _, self.sweep_dir = write_sweep_report(self.config, self.data, self.sweep)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _tax_json(self) -> dict:
        return json.loads((self.sweep_dir / "tax.json").read_text(encoding="utf-8"))

    def test_tax_json_holds_every_run_under_every_scenario(self) -> None:
        tax = self._tax_json()
        self.assertEqual(tax["artifact_schema"], 6)
        self.assertEqual(tax["overlay_version"], "tax-overlay-v1")
        expected_runs = {"strategy", "benchmark", "exposure_matched", "cash"} | {
            f"variant:{name}" for name in GRID if name != "base"
        }
        self.assertEqual(set(tax["runs"]), expected_runs)
        for scenarios in tax["runs"].values():
            self.assertEqual(len(scenarios), 8)
            self.assertIn("hifo-deferral-base", scenarios)
            self.assertIn("after_tax_post_liquidation", scenarios["fifo-mtm_60_40-low"]["wealth"])

    def test_the_cash_run_pays_tax_only_on_interest(self) -> None:
        cash = self._tax_json()["runs"]["cash"]["hifo-deferral-base"]
        self.assertGreater(sum(year["cash_interest"] for year in cash["by_year"]), 0.0)
        self.assertEqual(cash["totals"]["open_lots_at_end"], 0)
        self.assertTrue(cash["identity_checks"]["share_identity_passed"])

    def test_identities_hold_on_the_synthetic_strategy(self) -> None:
        strategy = self._tax_json()["runs"]["strategy"]["hifo-deferral-base"]
        self.assertTrue(strategy["identity_checks"]["share_identity_passed"])
        self.assertTrue(strategy["identity_checks"]["income_plus_gain_passed"])
        self.assertEqual(strategy["identity_checks"]["ex_dates_checked"], 0)

    def test_manifest_and_criteria_carry_the_tax_identity(self) -> None:
        manifest = json.loads((self.sweep_dir / "manifest.json").read_text(encoding="utf-8"))
        criteria = json.loads((self.sweep_dir / "criteria.json").read_text(encoding="utf-8"))
        tax = self._tax_json()
        self.assertEqual(manifest["artifact_schema"], 6)
        self.assertEqual(manifest["tax_policy_sha256"], tax["tax_policy_sha256"])
        self.assertEqual(manifest["distributions_sha256"], tax["distributions_sha256"])
        self.assertEqual(manifest["distributions_manifest"]["methodology"], "synthetic-test")
        self.assertEqual(manifest["distributions_manifest"]["splits"], {s: [] for s in "ABCD"})
        self.assertEqual(criteria["tax_policy_sha256"], tax["tax_policy_sha256"])
        self.assertEqual(criteria["distributions_sha256"], tax["distributions_sha256"])

    def test_the_distributions_input_is_archived_beside_prices_and_cash(self) -> None:
        with gzip.open(self.sweep_dir / "input_distributions.csv.gz", "rt", encoding="utf-8") as handle:
            header = handle.readline().strip()
            first = handle.readline().strip()
        self.assertEqual(header, "date,symbol,close,dividend")
        self.assertTrue(first.startswith("2019-10-01,A,"))

    def test_the_summary_has_an_after_tax_block(self) -> None:
        summary = (self.sweep_dir / "summary.md").read_text(encoding="utf-8")
        self.assertIn("## After tax", summary)
        self.assertIn("| strategy |", summary)
        self.assertIn("hifo-deferral-base", summary)
        self.assertIn("NAV convention", summary)

    def test_the_after_tax_figures_enter_the_profile_extras_unchanged_for_ba_001(self) -> None:
        self.assertIsNotNone(self.sweep.tax)
        self.assertTrue(self.sweep.outcome.criteria)   # BA-001's criteria ignore extras and still evaluate


class NoTaxTests(unittest.TestCase):
    def test_without_a_tax_table_nothing_tax_related_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _config(Path(directory))
            data = load_market_data(config)
            sweep = run_sweep(config, data)
            _, sweep_dir = write_sweep_report(config, data, sweep)
            self._check(sweep, sweep_dir)

    def _check(self, sweep, sweep_dir: Path) -> None:
        self.assertIsNone(sweep.tax)
        self.assertFalse((sweep_dir / "tax.json").exists())
        self.assertFalse((sweep_dir / "input_distributions.csv.gz").exists())
        manifest = json.loads((sweep_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("tax_policy_sha256", manifest)
        self.assertEqual(manifest["artifact_schema"], 6)
        self.assertNotIn("## After tax", (sweep_dir / "summary.md").read_text(encoding="utf-8"))


class StaticFullRowTests(unittest.TestCase):
    def test_a_target_exposure_benchmark_adds_the_full_static_secondary_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config_with(root, BENCHMARK_TABLE + TAX_TABLE)
            data = load_market_data(config)
            _write_distributions(root, data)
            sweep = run_sweep(config, data)
            _, sweep_dir = write_sweep_report(config, data, sweep)
            self.assertIsNotNone(sweep.static_full)
            self.assertGreater(float(sweep.static_full["average_gross_exposure"]), 0.9)
            self.assertLess(float(sweep.variants["base"]["static"]["average_gross_exposure"]), 0.7)
            self.assertTrue((sweep_dir / "variants" / "static_full" / "strategy_equity.csv").is_file())
            tax = json.loads((sweep_dir / "tax.json").read_text(encoding="utf-8"))
            self.assertIn("static_full", tax["runs"])
            summary = (sweep_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("| Metric | Strategy | Static | Exposure-matched | Cash |", summary)
            self.assertIn("Full static", summary)

    def test_without_a_benchmark_table_there_is_no_static_full_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _config_with(Path(directory), "")
            sweep = run_sweep(config, load_market_data(config))
            self.assertIsNone(sweep.static_full)
