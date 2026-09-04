"""C1-C5 must be decided by arithmetic, never by judgement at reading time."""

import unittest

from boring_alpha.criteria import Verdict, classify, evaluate_period

BASE = {
    "strategy": {"max_drawdown": -0.10, "sharpe_vs_cash": 0.50},
    "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.55},
}


def _period(**overrides) -> dict:
    variants = {
        "base": dict(BASE),
        "double_cost": dict(BASE),
        "lookback_9": dict(BASE),
        "lookback_15": dict(BASE),
        "drop_top_sleeve": dict(BASE),
    }
    variants.update(overrides)
    return variants


class CriteriaTests(unittest.TestCase):
    def test_all_criteria_pass_on_a_clearly_better_strategy(self) -> None:
        outcome = evaluate_period(_period())
        self.assertTrue(outcome.passed)
        self.assertEqual([c.name for c in outcome.criteria if not c.passed], [])

    def test_c1_fails_when_drawdown_is_not_enough_shallower(self) -> None:
        shallow = {"strategy": {"max_drawdown": -0.16, "sharpe_vs_cash": 0.5},
                   "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        outcome = evaluate_period(_period(base=shallow))
        c1 = next(c for c in outcome.criteria if c.name == "C1")
        self.assertFalse(c1.passed)
        self.assertIn("0.75", c1.detail)

    def test_c2_fails_when_sharpe_falls_more_than_a_tenth_below_static(self) -> None:
        weak = {"strategy": {"max_drawdown": -0.10, "sharpe_vs_cash": 0.30},
                "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.55}}
        outcome = evaluate_period(_period(base=weak))
        self.assertFalse(next(c for c in outcome.criteria if c.name == "C2").passed)

    def test_c3_covers_the_doubled_cost_variant(self) -> None:
        costly = {"strategy": {"max_drawdown": -0.19, "sharpe_vs_cash": 0.5},
                  "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        outcome = evaluate_period(_period(double_cost=costly))
        self.assertFalse(next(c for c in outcome.criteria if c.name == "C3").passed)

    def test_c4_covers_both_neighbouring_lookbacks(self) -> None:
        bad = {"strategy": {"max_drawdown": -0.19, "sharpe_vs_cash": 0.5},
               "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        self.assertFalse(
            next(c for c in evaluate_period(_period(lookback_15=bad)).criteria if c.name == "C4").passed
        )

    def test_c5_covers_removing_the_largest_contributing_sleeve(self) -> None:
        bad = {"strategy": {"max_drawdown": -0.19, "sharpe_vs_cash": 0.5},
               "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        self.assertFalse(
            next(c for c in evaluate_period(_period(drop_top_sleeve=bad)).criteria if c.name == "C5").passed
        )


class ClassificationTests(unittest.TestCase):
    def test_advance_requires_every_criterion_in_both_periods(self) -> None:
        self.assertEqual(classify(_period(), _period()), Verdict.ADVANCE)

    def test_reject_when_drawdown_is_no_shallower_than_static(self) -> None:
        deep = {"strategy": {"max_drawdown": -0.25, "sharpe_vs_cash": 0.5},
                "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        self.assertEqual(classify(_period(base=deep), _period()), Verdict.REJECT)

    def test_reject_when_sharpe_versus_cash_is_negative(self) -> None:
        losing = {"strategy": {"max_drawdown": -0.05, "sharpe_vs_cash": -0.1},
                  "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        self.assertEqual(classify(_period(), _period(base=losing)), Verdict.REJECT)

    def test_inconclusive_when_a_stability_check_fails_without_triggering_reject(self) -> None:
        wobbly = {"strategy": {"max_drawdown": -0.19, "sharpe_vs_cash": 0.5},
                  "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.5}}
        self.assertEqual(classify(_period(lookback_9=wobbly), _period()), Verdict.INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
