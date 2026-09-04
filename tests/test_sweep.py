from datetime import date
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
[W-001.development]
start = 2021-01-01
end = 2022-12-31
"""

CONFIG = """
[strategy]
id = "W-001"
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
        self.assertEqual(criteria["strategy_id"], "W-001")
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
