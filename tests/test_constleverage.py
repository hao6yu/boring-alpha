"""Tests for the constant-leverage policy.

The interesting property of a constant-weight policy is not that it returns a constant — that is four lines of
code. It is that a policy with no signal in it must still satisfy every contract a signal policy satisfies, or
the forward book will price it differently for reasons that have nothing to do with its merits. Round 32 exists
because the live book has been observing a policy that rounds 25 and 26 measure as *negative* under honest
costs, while the only policy that measures positive runs unobserved; if this module quietly skipped entry
turnover it would look better than the comparator on the first day and the forward record would be lying.

So the emphasis is on the interface and on the accounting, not on the arithmetic.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boring_alpha.signals.constleverage import ConstantLeveragePolicy    # noqa: E402


class TheWeightIsTheClaim(unittest.TestCase):
    def test_the_weight_is_constant_and_above_one_because_that_is_what_the_plan_is(self):
        p = ConstantLeveragePolicy(weight=1.25)
        path = p.weights([0.0] * 40, [0.0] * 40)
        self.assertEqual(len(path), 40)
        self.assertTrue(all(abs(w - 1.25) < p.tolerance for w, _ in path))
        self.assertTrue(all(w is not None for w, _ in path),
                        "a policy that emits None makes the book guess; a constant has no warm-up to hide behind")

    def test_it_refuses_an_underweight_book_because_that_is_a_different_decision(self):
        """0.80x is round 24's cash decision, not a leverage decision, and letting it through here would let a
        drawdown preference be recorded as though it had been priced as a loan."""

        with self.assertRaises(ValueError):
            ConstantLeveragePolicy(weight=0.80)

    def test_it_refuses_leverage_this_project_has_never_measured(self):
        for bad in (2.01, 3.0, 5.0):
            with self.assertRaises(ValueError):
                ConstantLeveragePolicy(weight=bad)
        ConstantLeveragePolicy(weight=2.0)          # the boundary is measured (round 30), so it is allowed


class ItChargesForItsOwnEntry(unittest.TestCase):
    """The test this module exists to have."""

    def test_day_one_reports_the_full_weight_as_turnover_because_buying_the_book_is_a_trade(self):
        p = ConstantLeveragePolicy(weight=1.25)
        path = p.weights([0.0] * 5, [0.0] * 5)
        self.assertAlmostEqual(path[0][1], 1.25, places=12,
                               msg="free entry would flatter this plan against every other policy in the book")

    def test_every_later_session_reports_zero_turnover_because_a_constant_cannot_drift(self):
        p = ConstantLeveragePolicy(weight=1.25)
        path = p.weights([0.0] * 5, [0.0] * 5)
        self.assertTrue(all(t == 0.0 for _, t in path[1:]))
        self.assertAlmostEqual(sum(t for _, t in path), 1.25, places=12,
                               msg="total lifetime turnover must equal the entry and nothing else")


class ItMatchesThePolicyTheBookAlreadyRuns(unittest.TestCase):
    """Same call signature, same tuple shape, same non-empty guarantee — and where it differs, the difference
    has to be the *point* rather than an accident of implementation."""

    @classmethod
    def setUpClass(cls):
        from boring_alpha.signals.voltarget import VolTargetPolicy
        import withdrawal_capacity as wc
        import income_frontier as ifr
        from boring_alpha.data.csv_loader import load_csv_market_data
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        series = ifr.series_for(cls.data, "SPY")
        cls.closes = list(series.values())
        cls.returns = [0.0] + [cls.closes[i] / cls.closes[i - 1] - 1.0 for i in range(1, len(cls.closes))]
        cls.vol = VolTargetPolicy(target_vol=0.18, vol_window=30, trend_window=200, max_weight=1.3,
                                  min_weight=0.3, rebalance_band=0.10, review_every=5)
        cls.const = ConstantLeveragePolicy(weight=1.25)

    def test_the_two_policies_emit_the_same_number_of_sessions_so_the_book_sees_one_calendar(self):
        a = self.vol.weights(self.closes, self.returns)
        b = self.const.weights(self.closes, self.returns)
        self.assertEqual(len(a), len(b))

    def test_the_constant_averages_higher_because_that_is_the_whole_difference_between_them(self):
        """Round 26 measured the vol-target rule's mean weight at 0.843 once it is forbidden to borrow, and 1.023
        with the cap on. A constant 1.25 is simply more of the same exposure, and if that ever stops being true
        the two books are no longer describing the same market."""

        a = [w for w, _ in self.vol.weights(self.closes, self.returns) if w is not None]
        b = [w for w, _ in self.const.weights(self.closes, self.returns)]
        self.assertGreater(sum(b) / len(b), sum(a) / len(a))
        self.assertAlmostEqual(sum(b) / len(b), 1.25, places=12)

    def test_the_pinned_config_block_says_what_the_plan_actually_contains(self):
        d = self.const.describe()
        self.assertTrue(d["contains_no_forecast"])
        self.assertEqual(d["weight"], 1.25)
        self.assertIn("drawdown", d["measured_excess"],
                      "a config that cites the return and not the drawdown is marketing, not pre-registration")


if __name__ == "__main__":
    unittest.main(verbosity=2)
