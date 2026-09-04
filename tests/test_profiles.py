"""A strategy's grid, criteria and verdict live in its profile; BA-001's must not move."""

import json
from pathlib import Path
import unittest

from boring_alpha.config import load_config
from boring_alpha.criteria import (
    BASE,
    DOUBLE_COST,
    DROP_TOP_SLEEVE,
    LOOKBACK_15,
    LOOKBACK_9,
    Verdict,
)
from boring_alpha.profiles import BA001Profile, PROFILES, VariantSpec, profile_for
from boring_alpha.signals.trend import (
    ExcludingSleeve,
    FixedAllocation,
    MultiAssetTrend,
    TargetExposureAllocation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RegistryTests(unittest.TestCase):
    def test_ba_001_is_registered(self) -> None:
        self.assertIsInstance(profile_for("BA-001"), BA001Profile)
        self.assertEqual(profile_for("BA-001").strategy_id, "BA-001")
        self.assertIn("BA-001", PROFILES)

    def test_an_unknown_strategy_is_refused_by_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "no evaluation profile.*X-999"):
            profile_for("X-999")


class GoldenReplayTests(unittest.TestCase):
    """The two real BA-001 sweeps, replayed through the profile, must reproduce
    their own criteria files exactly and classify Inconclusive."""

    def setUp(self) -> None:
        self.development = _fixture("ba001_development_criteria.json")
        self.validation = _fixture("ba001_validation_criteria.json")
        self.profile = BA001Profile()

    def _replay(self, fixture: dict) -> None:
        outcome = self.profile.evaluate_period(fixture["variants"], {})
        self.assertEqual(outcome.passed, fixture["passed"])
        produced = [
            {"name": c.name, "description": c.description, "passed": c.passed, "detail": c.detail}
            for c in outcome.criteria
        ]
        self.assertEqual(produced, fixture["criteria"])

    def test_development_criteria_are_reproduced_exactly(self) -> None:
        self._replay(self.development)

    def test_validation_criteria_are_reproduced_exactly(self) -> None:
        self._replay(self.validation)

    def test_the_pair_classifies_inconclusive(self) -> None:
        verdict = self.profile.classify(self.development["variants"], self.validation["variants"])
        self.assertIs(verdict, Verdict.INCONCLUSIVE)


class GridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(REPO_ROOT / "configs" / "ba_001_development.toml")
        self.grid = BA001Profile().grid(self.config)

    def test_the_grid_has_the_charter_s_five_variants_in_order(self) -> None:
        self.assertEqual(
            list(self.grid), [BASE, DOUBLE_COST, LOOKBACK_9, LOOKBACK_15, DROP_TOP_SLEEVE]
        )
        self.assertTrue(all(isinstance(spec, VariantSpec) for spec in self.grid.values()))

    def test_descriptions_match_the_archived_sweep(self) -> None:
        # From experiments/BA-001/sweeps/4b9d1479f811d108/manifest.json "grid".
        self.assertEqual(
            {name: spec.description for name, spec in self.grid.items()},
            {
                BASE: "12-month lookback at 10 bps (pre-registered)",
                DOUBLE_COST: "12-month lookback at 20 bps",
                DROP_TOP_SLEEVE: "12-month lookback at 10 bps, top sleeve in cash",
                LOOKBACK_15: "15-month lookback at 10 bps",
                LOOKBACK_9: "9-month lookback at 10 bps",
            },
        )

    def test_costs_and_lookbacks_follow_the_charter(self) -> None:
        self.assertEqual(self.grid[BASE].cost_bps, 10.0)
        self.assertEqual(self.grid[DOUBLE_COST].cost_bps, 20.0)
        nine = self.grid[LOOKBACK_9].strategy(self.config, None)
        fifteen = self.grid[LOOKBACK_15].strategy(self.config, None)
        self.assertIsInstance(nine, MultiAssetTrend)
        self.assertEqual(nine.lookback_months, 9)
        self.assertEqual(fifteen.lookback_months, 15)
        # The benchmark takes the variant's own lookback so both series start together.
        self.assertEqual(self.grid[LOOKBACK_15].benchmark(self.config).lookback_months, 15)

    def test_only_the_drop_variant_needs_the_top_sleeve_and_excludes_it(self) -> None:
        self.assertEqual(
            [name for name, spec in self.grid.items() if spec.needs_top_sleeve],
            [DROP_TOP_SLEEVE],
        )
        policy = self.grid[DROP_TOP_SLEEVE].strategy(self.config, "SPY")
        self.assertIsInstance(policy, ExcludingSleeve)
        self.assertEqual(policy.symbol, "SPY")
        with self.assertRaisesRegex(ValueError, "top sleeve"):
            self.grid[DROP_TOP_SLEEVE].strategy(self.config, None)

    def test_the_benchmark_is_full_static_without_a_benchmark_table(self) -> None:
        benchmark = self.grid[BASE].benchmark(self.config)
        self.assertIsInstance(benchmark, FixedAllocation)
        self.assertNotIsInstance(benchmark, TargetExposureAllocation)

    def test_the_benchmark_follows_the_benchmark_table_when_present(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        (root / "configs").mkdir()
        periods = (REPO_ROOT / "configs" / "evaluation_periods.toml").read_text(encoding="utf-8")
        (root / "configs" / "evaluation_periods.toml").write_text(periods, encoding="utf-8")
        text = (REPO_ROOT / "configs" / "ba_001_development.toml").read_text(encoding="utf-8")
        text += '\n[benchmark]\nexposure = 0.6\nrebalance = "annual"\n'
        path = root / "configs" / "run.toml"
        path.write_text(text, encoding="utf-8")
        config = load_config(path)
        benchmark = BA001Profile().grid(config)[BASE].benchmark(config)
        self.assertIsInstance(benchmark, TargetExposureAllocation)
        self.assertEqual(benchmark.name, "Target-Exposure Benchmark (60%, annual)")


if __name__ == "__main__":
    unittest.main()
