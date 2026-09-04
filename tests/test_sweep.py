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
start = "2018-01-01"
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

    def test_the_dropped_sleeve_is_the_largest_contributor(self) -> None:
        sweep = run_sweep(self.config, self.data)
        contributions = sweep.contributions
        self.assertEqual(sweep.top_sleeve, max(contributions, key=contributions.get))

    def test_criteria_are_evaluated_from_the_grid(self) -> None:
        sweep = run_sweep(self.config, self.data)
        self.assertEqual([c.name for c in sweep.outcome.criteria], ["C1", "C2", "C3", "C4", "C5"])

    def test_cluster_attribution_covers_every_sleeve(self) -> None:
        sweep = run_sweep(self.config, self.data)
        self.assertEqual(set(sweep.clusters), {"growth", "defensive"})
        self.assertAlmostEqual(
            sum(sweep.clusters.values()), sum(sweep.contributions.values()), places=6
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
