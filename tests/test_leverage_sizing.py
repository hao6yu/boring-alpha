"""Invariants for the funded engine's path/carry reporting and for leverage sizing.

Round 4 added two fields to the shared funded simulator (`path`, `carry_paid`) so
that a caller could price a worst month and an interest bill without
re-implementing the engine. New reporting fields are exactly where a simulator
lies most comfortably — they are computed, printed, and never compared to
anything — so each one is pinned here against a hand-computable case, and the
conservation test that used to catch a cash-leg bug is repeated against the new
fields to make sure the fix that introduced them is still the fix in force.
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import run_voltarget_scan as engine  # noqa: E402
import leverage_sizing as sizing  # noqa: E402


def days(n):
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


def flat_market(n, cash_factor=1.0002):
    """Prices that never move, cash that always pays. Nothing can hide here."""

    return days(n), [100.0] * n, [0.0] * n, [cash_factor] * n


class CarryAccounting(unittest.TestCase):
    def test_unlevered_account_pays_no_worthwhile_spread(self):
        """An unlevered account may touch zero cash on an entry charge, but it
        must not accumulate an interest bill. A 2x account must."""

        res = engine.funded(*flat_market(252)[1:], dates=flat_market(252)[0],
                            targets=[1.0] * 252, band=0.0, start=0)
        self.assertLess(res.carry_paid, res.ending * 0.001)

        levered = engine.funded(*flat_market(252)[1:], dates=flat_market(252)[0],
                                targets=[2.0] * 252, band=0.0, start=0)
        self.assertGreater(levered.carry_paid, res.carry_paid * 20)

    def test_carry_is_spread_only_not_the_whole_cash_rate(self):
        """The borrowed leg accrues at cash+spread; only the spread is carry.

        Charging the cash rate as carry too would price every levered row twice
        — once as interest and once as the opportunity cost already implicit in
        the comparator — and would quietly manufacture a reason to reject
        leverage.
        """
        n = 252
        dates, closes, rets, cfr = flat_market(n, cash_factor=1.0)
        saved = engine.BORROW_SPREAD
        try:
            engine.BORROW_SPREAD = 0.02
            res = engine.funded(closes, rets, cfr, dates, targets=[2.0] * n,
                                band=0.0, start=0)
            # Debt equals the whole account value at 2x on flat prices, so the
            # year's spread bill is roughly the average borrowed notional times
            # the spread. Deposits are $500/mo, so notional runs ~5k to ~10k.
            self.assertGreater(res.carry_paid, 60.0)
            self.assertLess(res.carry_paid, 220.0)
        finally:
            engine.BORROW_SPREAD = saved

    def test_carry_rises_monotonically_with_the_spread(self):
        """Not exactly proportional: the debt path itself depends on how much
        interest was already charged, so compounding bends the line. Monotone and
        roughly linear is the honest claim; exact proportionality is not true and
        asserting it would have made this test fail for the wrong reason."""

        n = 252
        dates, closes, rets, cfr = flat_market(n, cash_factor=1.0)
        bills = []
        saved = engine.BORROW_SPREAD
        try:
            for spread in (0.01, 0.02, 0.04):
                engine.BORROW_SPREAD = spread
                bills.append(engine.funded(
                    closes, rets, cfr, dates, targets=[2.0] * n,
                    band=0.0, start=0).carry_paid)
        finally:
            engine.BORROW_SPREAD = saved
        self.assertTrue(bills[0] < bills[1] < bills[2])
        self.assertAlmostEqual(bills[1] / bills[0], 2.0, delta=0.05)
        self.assertAlmostEqual(bills[2] / bills[0], 4.0, delta=0.15)


class Conservation(unittest.TestCase):
    def test_flat_market_never_creates_equity(self):
        """With no prices moving, ending value is deposits minus costs. Never more."""

        # Cash factor pinned to 1.0 so interest cannot be the explanation for
        # anything: equity never moves and cash never pays, so the only forces on
        # the account are deposits and the three costs.
        n = 252
        dates, closes, rets, cfr = flat_market(n, cash_factor=1.0)
        for lever in (1.0, 1.5, 2.0):
            res = engine.funded(closes, rets, cfr, dates, targets=[lever] * n,
                                band=0.10, start=0)
            paid = 5_000.0 + 500.0 * sum(
                1 for i in range(1, n)
                if dates[i].month != dates[i - 1].month)
            self.assertLess(res.ending, paid, f"{lever}x created equity")
            self.assertGreater(res.ending, paid * 0.90, f"{lever}x lost implausibly much")
            self.assertFalse(res.ruined)

    def test_path_covers_every_traded_session(self):
        n = 120
        dates, closes, rets, cfr = flat_market(n)
        res = engine.funded(closes, rets, cfr, dates, targets=[1.5] * n,
                            band=0.10, start=0)
        self.assertEqual(len(res.path), n)
        self.assertEqual(res.path[0][0], dates[0])
        self.assertEqual(res.path[-1][0], dates[n - 1])
        for _stamp, value in res.path:
            self.assertGreater(value, 0.0)


class WorstMonth(unittest.TestCase):
    def test_a_deposit_is_not_a_gain(self):
        """Month-end values must be compared, not inflows netted into returns."""

        path = ((date(2020, 1, 30), 10_000.0), (date(2020, 2, 29), 9_000.0),
                (date(2020, 3, 31), 9_500.0))
        self.assertAlmostEqual(sizing.worst_month(path), -0.10, places=6)

    def test_a_rising_account_has_no_worst_month(self):
        path = tuple((date(2020, m, 28), 1_000.0 * m) for m in range(1, 13))
        self.assertEqual(sizing.worst_month(path), 0.0)

    def test_empty_and_single_point_paths_are_not_errors(self):
        self.assertEqual(sizing.worst_month(()), 0.0)
        self.assertEqual(sizing.worst_month(((date(2020, 1, 1), 100.0),)), 0.0)


class WrapperPricing(unittest.TestCase):
    """A daily-reset fund is a different object from the same exposure on margin.

    These tests exist because the first version of `wrapper_returns` charged an
    annual spread as if it were a daily one and reported a 99% loss, which was
    then briefly believed. A function whose only output is "this instrument is
    catastrophic" will be believed, so the arithmetic is pinned twice: once on
    magnitudes and once against a hand-computable case.
    """

    def test_flat_market_costs_a_sane_amount_not_everything(self):
        """Cash pinned at zero so the only drags are expense and spread.

        Left at the fixture's normal paying-cash factor the fund also carries a
        ~5% financing leg on the borrowed half, which is a true cost and not one
        this test is about; isolating it is the point of the next test.
        """

        n = 252
        _dates, _closes, rets, _cfr = flat_market(n, cash_factor=1.0)
        wr = sizing.wrapper_returns(rets, [1.0] * n, 2.0, 0.0090, 0.0025)
        year = -sum(wr)
        self.assertAlmostEqual(year, 0.0115, places=4)  # 0.90% ER + 0.25% spread
        self.assertLess(year, 0.05)                     # tens of bps, not 90%

    def test_annual_inputs_are_divided_by_the_session_count(self):
        """The bug this pins: charging an annual number every session.

        At the wrong scale the spread alone is 63% a year and the wrapper looks
        catastrophic. At the right scale it is a quarter of one percent and the
        ratio below is exactly 0.5.
        """

        n = 252
        _dates, _closes, rets, _cfr = flat_market(n, cash_factor=1.0)
        cheap = -sum(sizing.wrapper_returns(rets, [1.0] * n, 2.0, 0.0045, 0.0))
        dear = -sum(sizing.wrapper_returns(rets, [1.0] * n, 2.0, 0.0090, 0.0))
        self.assertAlmostEqual(cheap / dear, 0.5, places=3)
        self.assertAlmostEqual(dear, 0.0090, places=6)  # one year, not 252 years

    def test_leverage_multiplies_return_and_carry_alike(self):
        _dates, _closes, rets, cfr = flat_market(252)
        up = 0.001
        boosted = sum(sizing.wrapper_returns([up] * 252, [1.0] * 252, 2.0, 0.0, 0.0))
        plain = sum(sizing.wrapper_returns([up] * 252, [1.0] * 252, 1.0, 0.0, 0.0))
        self.assertAlmostEqual(boosted / plain, 2.0, places=6)

    def test_unlevered_wrapper_is_the_underlying_untouched(self):
        rets = [0.01, -0.02, 0.005]
        wr = sizing.wrapper_returns(rets, [1.0, 1.0, 1.0], 1.0, 0.0, 0.0)
        for want, got in zip(rets, wr):
            self.assertAlmostEqual(want, got, places=12)


class ControlRow(unittest.TestCase):
    def test_engine_reproduces_the_comparator_exactly(self):
        """The tool's own check, asserted rather than eyeballed on a screen.

        Target 1.0 with no band must be dollar-identical to plain DCA. If this
        ever drifts, every levered row above it is measuring the simulator.
        """

        n = 400
        dates = days(n)
        closes = [100.0 + i * 0.05 for i in range(n)]        # drifting upward
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, n)]
        rets.insert(0, 0.0)
        cfr = [1.0001] * n
        comp = sizing.comparator(dates, closes, rets, cfr, 1)
        control = engine.funded(closes, rets, cfr, dates, targets=[1.0] * n,
                                band=0.0, start=1)
        self.assertAlmostEqual(control.ending, comp.ending, places=6)
        self.assertAlmostEqual(control.max_drawdown, comp.max_drawdown, places=9)


if __name__ == "__main__":
    unittest.main()
