"""Tests for the two routes to the same exposure: a broker's loan and a fund's own leverage.

The claim this file exists to make is counter-intuitive enough that it needs pinning rather than reading: a
leveraged ETF is *not* the cheap way to lever, it is the convenient way, and which one wins depends on leverage in
a direction that surprises people. At 1.25x the fund loses at any interest rate; at 3x it wins. That sign flip is
arithmetic on where the fee lands, so these tests assert the flip and the reason for it, not the printed numbers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import leverage_routes as lr                       # noqa: E402
import income_frontier as ifr                      # noqa: E402


class TheTwoRoutesArePricedOnWhatTheyActuallyCharge(unittest.TestCase):
    def test_a_loan_charges_only_on_the_borrowed_part(self):
        # 1.25x: borrow 0.25 per dollar of equity, i.e. 0.20 per dollar of exposure.
        self.assertAlmostEqual(lr.cost_of_loan(1.25, 0.049), 0.2 * 0.049, places=10)
        self.assertAlmostEqual(lr.cost_of_loan(2.0, 0.049), 0.5 * 0.049, places=10)

    def test_a_fund_charges_its_fee_on_the_whole_position_regardless_of_leverage(self):
        """The fee per unit of exposure is just `er` — it does not fall with leverage, which is the fact that
        makes the whole crossover work the way it does."""

        for L in (1.25, 2.0, 3.0):
            self.assertAlmostEqual(lr.cost_of_fund(L, 0.0095, 0.0, 0.0), 0.0095, places=10,
                                   msg=f"at {L}x the fee appeared to be spread over leverage")

    def test_an_unlevered_fund_costs_its_fee_and_nothing_else(self):
        self.assertAlmostEqual(lr.cost_of_fund(1.0, 0.0095, 0.05, 0.05), 0.0095, places=10)
        self.assertEqual(lr.cost_of_loan(1.0, 0.049), 0.0, "nothing borrowed, nothing charged")


class TheCrossoverHasTheSignItMustHave(unittest.TestCase):
    def test_at_125x_the_fund_loses_at_every_interest_rate_when_the_dealer_is_paid(self):
        x = lr.crossover_bill(1.25, 0.0095, 0.005, ifr.MENU_PUBLIC)
        self.assertLess(x, 0.0, "1.25x is where the fund's fee dominates; it must not look competitive")

    def test_at_125x_with_no_swap_cost_the_fund_wins_only_near_zero_rates(self):
        x = lr.crossover_bill(1.25, 0.0095, 0.0, ifr.MENU_PUBLIC)
        self.assertGreater(x, 0.0)
        self.assertLess(x, 0.01, "even free funding barely rescues it at this leverage")

    def test_the_crossover_rises_with_leverage_because_the_fee_gets_spread_thinner(self):
        """The non-obvious part. Higher leverage gives the fund *more* advantage on cost, because the same fee
        covers more exposure while the loan's interest keeps growing. Everything else being equal, a 3x fund is a
        better-value unit of leverage than a 1.25x fund — which is not the same as saying 3x is a better idea."""

        a = lr.crossover_bill(1.25, 0.0095, 0.005, ifr.MENU_PUBLIC)
        b = lr.crossover_bill(2.0, 0.0095, 0.005, ifr.MENU_PUBLIC)
        c = lr.crossover_bill(3.0, 0.0095, 0.005, ifr.MENU_PUBLIC)
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertGreater(c, ifr.MENU_PUBLIC - 0.02)

    def test_at_3x_the_fund_beats_the_loan_at_todays_rate_by_a_sliver(self):
        loan = lr.cost_of_loan(3.0, ifr.MENU_PUBLIC)
        fund = lr.cost_of_fund(3.0, 0.0095, 0.005, 0.0288)
        self.assertLess(fund, loan)
        self.assertLess(loan - fund, 0.002, "the flip is real but marginal; it must not be sold as a rout")


class ThePathCostIsNotAFee(unittest.TestCase):
    def test_the_drag_is_zero_when_there_is_no_leverage(self):
        self.assertEqual(lr.drag(1.0, 0.20), 0.0)

    def test_the_drag_grows_with_the_square_of_leverage(self):
        """2x should cost roughly 3x what 1.25x costs (2 vs 0.3125 in the (L-1)L/2 factor, a 6.4x ratio). The
        point of the test is the direction and the superlinearity, not the coefficient."""
        d125, d200, d300 = lr.drag(1.25, .2), lr.drag(2.0, .2), lr.drag(3.0, .2)
        self.assertLess(d200, d125)
        self.assertLess(d300, d200)
        self.assertGreater(abs(d200) / abs(d125), 4.0)
        self.assertGreater(abs(d300) / abs(d200), 1.5)

    def test_the_drag_is_worst_in_the_cheap_rate_regime_that_makes_the_fund_look_good(self):
        """The trap this file is here to prevent: the fund wins on *cost* exactly when rates are at zero, which in
        the archive means the calm high-drawdown-risk years, and the path cost is what the cost table omits."""
        self.assertLess(lr.drag(3.0, 0.30), -0.02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
