"""Tests for the withdrawal engine.

Written in the shape the last three rounds established: every test names the edit it would
catch, and the interesting ones are about money the engine declines to charge rather than
about money it charges correctly. A withdrawal simulator that flatters a levered account
is not a wrong number, it is a different and much more expensive kind of wrong.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import withdrawal_capacity as wc


def months(count: int, start: date = date(2000, 1, 1)) -> list[date]:
    out, year, month = [], start.year, start.month
    for _ in range(count):
        out.append(date(year, month, 1))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


FLAT_CASH = [0.0] * 240
BORROW_SPREAD_FOR_TEST = 0.015


class ExactAccounting(unittest.TestCase):
    """The engine may not lose or invent a dollar on a path computable by hand."""

    def setUp(self) -> None:
        self.saved_turnover = wc.TURNOVER_COST
        wc.TURNOVER_COST = 0.0

    def tearDown(self) -> None:
        wc.TURNOVER_COST = self.saved_turnover

    def test_a_untouched_flat_account_is_exactly_its_starting_value(self) -> None:
        outcome = wc.run([0.0] * 240, FLAT_CASH, 1.0, 0.0, 0.0, inflate=0.0)
        self.assertTrue(outcome.survived)
        self.assertAlmostEqual(outcome.ending, wc.START, places=6)
        self.assertEqual(outcome.calls, 0)

    def test_withdrawals_come_straight_out_of_a_flat_unlevered_account(self) -> None:
        """240 months at $400 off $100k must leave exactly $4,000. If the engine charges
        itself anything not named in the arguments, this stops being true."""

        outcome = wc.run([0.0] * 240, FLAT_CASH, 1.0, 400.0, 0.0, inflate=0.0)
        self.assertTrue(outcome.survived)
        self.assertAlmostEqual(outcome.paid, 400.0 * 240, places=6)
        self.assertAlmostEqual(outcome.ending, wc.START - 400.0 * 240, places=6)

    def test_the_account_dies_the_month_it_overs_pays(self) -> None:
        """$100k at $10k a month survives ten months and not eleven."""

        outcome = wc.run([0.0] * 240, FLAT_CASH, 1.0, 10_000.0, 0.0, inflate=0.0)
        self.assertFalse(outcome.survived)

    def test_a_levered_flat_account_loses_exactly_its_carry(self) -> None:
        """Flat prices, no expense, no withdrawal, 2x leverage: the only cash flow is
        interest on the loan, so the ending value is one line of arithmetic. This is the
        test the paper book failed for a whole round — it charged a spread and an expense
        ratio and never once charged interest on a 128% position, which moved the reported
        drag from 5.0 to 17.5 bps the moment it was fixed.

        The band is deliberately enormous: a rebalance would make the closed form wrong,
        and a test that quietly depends on the rebalancing rule is testing the wrong thing.
        """

        spread = 0.012
        monthly = spread / 12.0
        outcome = wc.run([0.0] * 240, FLAT_CASH, 2.0, 0.0, 0.0, inflate=0.0,
                         band=0.90, spread=spread)
        self.assertTrue(outcome.survived)
        self.assertEqual(outcome.calls, 0)
        expected = 2.0 * wc.START - wc.START * (1.0 + monthly) ** 240
        self.assertAlmostEqual(outcome.ending, expected, places=2)
        self.assertLess(outcome.ending, wc.START)


class CostsMustBite(unittest.TestCase):
    def test_a_dearer_loan_pays_less(self) -> None:
        """Raise the spread, get a smaller reliable withdrawal. A single argument in a
        simulator that makes no difference to any output is not a cost, it is a comment."""

        cheap = wc.capacity(self.windows, 2.0, 0.0, 0.025, "margin", 0.30, 0.005)
        dear = wc.capacity(self.windows, 2.0, 0.0, 0.025, "margin", 0.30, 0.030)
        self.assertGreater(cheap[0], dear[0])

    def test_an_expense_ratio_pays_less(self) -> None:
        free = wc.capacity(self.windows, 1.0, 0.0, 0.025, "margin", 0.30, 0.015)
        charged = wc.capacity(self.windows, 1.0, 0.0095, 0.025, "margin", 0.30, 0.015)
        self.assertGreater(free[0], charged[0])

    def setUp(self) -> None:
        rng = list(range(240))
        returns = [0.05 if i % 7 else -0.06 for i in rng]
        self.windows = [(returns, FLAT_CASH, date(1990, 1, 1))]


class Maintenance(unittest.TestCase):
    """The forced-sale rule, which is the only part of this simulator that can kill a plan
    that arithmetic alone would have saved — or save a plan arithmetic would have killed."""

    WHIPSAW = [-0.10, 0.10] + [0.0] * 238

    def test_a_deep_crash_triggers_a_call_and_a_zero_cushion_does_not(self) -> None:
        """Three times leverage, one -10% month. The lender cuts the book and the account
        lives, slightly worse off than if no lender existed. Both halves matter: a
        maintenance rule that never fires is decoration, and one that fires and changes no
        number is a prop."""

        called = wc.run(self.WHIPSAW, FLAT_CASH, 3.0, 200.0, 0.0009, inflate=0.0,
                        maintenance=0.30)
        free = wc.run(self.WHIPSAW, FLAT_CASH, 3.0, 200.0, 0.0009, inflate=0.0,
                      maintenance=0.0)
        self.assertEqual(called.calls, 1)
        self.assertEqual(free.calls, 0)
        self.assertTrue(called.survived and free.survived)
        self.assertNotAlmostEqual(called.ending, free.ending, places=2,
                                  msg="a call that changes no number is not a rule")

    def test_the_maintenance_fee_is_taken_from_the_position_not_the_cash_line(self) -> None:
        """A fee charged to a clamped cash line is a fee that is not charged — round 6's
        `max(0.0, cash)`, in a different file.

        Isolating this took two attempts and the first one was the mistake worth writing
        down. Comparing "with costs" against "without costs" measures whether *something*
        is charged, and a run with a forced sale also has a rebalance and a withdrawal, so
        the defect passed by paying a different fee. Here the withdrawal is zero and the
        band is wider than the post-call gap, so the rebalance cannot fire either: the
        forced-sale fee is the only fee that exists anywhere in the run, and any difference
        between the two endings can only be that fee.
        """

        saved = wc.TURNOVER_COST
        try:
            wc.TURNOVER_COST = 0.0
            no_fee = wc.run(self.WHIPSAW, FLAT_CASH, 3.0, 0.0, 0.0009, inflate=0.0,
                            band=2.5, maintenance=0.30)
            wc.TURNOVER_COST = 0.02
            with_fee = wc.run(self.WHIPSAW, FLAT_CASH, 3.0, 0.0, 0.0009, inflate=0.0,
                              band=2.5, maintenance=0.30)
        finally:
            wc.TURNOVER_COST = saved
        self.assertEqual(no_fee.calls, 1, "no forced sale; the fixture stopped testing "
                                          "the thing the test is named after")
        self.assertEqual(with_fee.calls, 1)
        self.assertLess(with_fee.ending, no_fee.ending)
        self.assertGreater(no_fee.ending - with_fee.ending, 1_000.0,
                           msg="the forced-sale fee is invisible; it is not being charged")


class Guardrail(unittest.TestCase):
    """The variable-withdrawal option: spend less when the account has fallen.

    This mechanism moves the floor further than any amount of leverage does, so it gets
    the same treatment as every other claim here — proof that it fires, and proof that
    the number it produces is caused by the rule rather than by the fixture.
    """

    CRASH = [-0.02] * 24 + [0.006] * 216
    GUARD = (0.25, 0.5)

    def test_the_guardrail_converts_a_death_into_a_survival(self) -> None:
        """At $400 a month the fixed plan runs out and the guarded plan finishes with
        money left. If both behave the same, the guardrail is a comment in the code."""

        plain = wc.run(self.CRASH, FLAT_CASH, 1.0, 400.0, 0.0009, inflate=0.025)
        guarded = wc.run(self.CRASH, FLAT_CASH, 1.0, 400.0, 0.0009, inflate=0.025,
                         guard=self.GUARD)
        self.assertFalse(plain.survived)
        self.assertTrue(guarded.survived)
        self.assertGreater(guarded.cuts, 0)

    def test_a_run_that_never_cuts_earns_no_credit_for_the_guardrail(self) -> None:
        """The guardrail must be observed working before any improvement is attributed to
        it. A test that compares two runs where the rule never fired would happily credit
        an untouched constant with saving the account — round 5's lesson that a check has
        to exercise the object it is named after."""

        calm = [0.006] * 240
        outcome = wc.run(calm, FLAT_CASH, 1.0, 300.0, 0.0009, inflate=0.025,
                         guard=self.GUARD)
        self.assertTrue(outcome.survived)
        self.assertEqual(outcome.cuts, 0)

    def test_a_deeper_cut_survives_more(self) -> None:
        """Monotonicity in the one knob the policy actually has: a rule that cuts harder
        must not be less reliable than one that cuts softly, or the comparison between
        guardrails is measuring nothing."""

        soft = wc.capacity(self.windows, 1.0, 0.0009, 0.025, "margin", 0.30, 0.015,
                           (0.25, 0.75))
        hard = wc.capacity(self.windows, 1.0, 0.0009, 0.025, "margin", 0.30, 0.015,
                           (0.25, 0.40))
        self.assertGreater(hard[0], soft[0])

    def setUp(self) -> None:
        self.windows = [([-0.02] * 24 + [0.006] * 216, FLAT_CASH, date(2000, 1, 1)),
                        ([-0.04] * 18 + [0.005] * 222, FLAT_CASH, date(2004, 1, 1))]


class Monotonicity(unittest.TestCase):
    def test_withdrawing_more_never_leaves_more(self) -> None:
        returns = [0.08 if i % 3 else -0.05 for i in range(240)]
        small = wc.run(returns, FLAT_CASH, 1.5, 300.0, 0.0009, inflate=0.0)
        large = wc.run(returns, FLAT_CASH, 1.5, 900.0, 0.0009, inflate=0.0)
        self.assertTrue(small.survived)
        self.assertLess(large.ending, small.ending)

    def test_the_frontier_is_reliable_all_the_way_down(self) -> None:
        """Bisection is only an answer if the passing set is an interval. The forced-sale
        rule can break that — selling more raises the equity ratio — so the frontier is
        re-checked at a point just under it, and `gaps` reports anything that passes above
        the first failure."""

        returns = [-0.06] * 18 + [0.03] * 40 + [-0.05] * 14 + [0.02] * 168
        windows = [(returns, FLAT_CASH, date(2000, 1, 1))]
        fraction, gaps, binding = wc.capacity(windows, 1.75, 0.0009, 0.025, "margin", 0.30)
        self.assertTrue(wc.reliable(windows, 1.75, 0.0009, 0.025, fraction * 0.99,
                                    "margin", 0.30))
        self.assertIsInstance(gaps, int)
        self.assertNotEqual(binding, "none")


class Wrapper(unittest.TestCase):
    """The wrapper's only property is that it multiplies. A simulator that quietly stops
    multiplying while still charging for it would report a conservative fund, and a
    conservative fund is exactly what nobody is buying."""

    def test_the_leverage_actually_levers_in_both_directions(self) -> None:
        """The monotonicity test, round 3's lesson applied to a new mechanism: twice the
        leverage must mean more upside on the way up and less on the way down. A -50% month
        is not a test of leverage at all, because an un-levered fund dies on that path too
        — which is precisely why the first version of this test passed while the leverage
        was switched off beneath it."""

        up = [0.01] * 240
        down = [-0.01] * 240
        single = wc._run_wrapper(up, FLAT_CASH, 1.0, 0.0, 0.0, BORROW_SPREAD_FOR_TEST)
        double = wc._run_wrapper(up, FLAT_CASH, 2.0, 0.0, 0.0, BORROW_SPREAD_FOR_TEST)
        single_down = wc._run_wrapper(down, FLAT_CASH, 1.0, 0.0, 0.0,
                                      BORROW_SPREAD_FOR_TEST)
        double_down = wc._run_wrapper(down, FLAT_CASH, 2.0, 0.0, 0.0,
                                      BORROW_SPREAD_FOR_TEST)
        self.assertGreater(double.ending, single.ending * 1.4,
                           msg="2x did not behave like 2x on the way up")
        self.assertLess(double_down.ending, single_down.ending * 0.6,
                        msg="2x did not behave like 2x on the way down")

    def test_a_two_times_wrapper_dies_on_a_fifty_percent_month(self) -> None:
        outcome = wc._run_wrapper([-0.5] + [0.0] * 239, FLAT_CASH, 2.0, 400.0, 0.0, 0.015)
        self.assertFalse(outcome.survived)

    def test_a_wrapper_is_never_called_however_it_falls(self) -> None:
        """No loan, nothing to call. It can go to zero and it cannot be force-sold."""

        returns = [-0.04] * 30 + [0.02] * 210
        outcome = wc.run(returns, FLAT_CASH, 2.0, 400.0, 0.0, inflate=0.0,
                        instrument="wrapper")
        self.assertEqual(outcome.calls, 0)

    def test_the_wrapper_pays_its_own_expense_and_the_sleeve_does_not(self) -> None:
        cheap = wc.run([0.01] * 240, FLAT_CASH, 1.0, 0.0, 0.0003, inflate=0.0)
        wrapped = wc.run([0.01] * 240, FLAT_CASH, 1.0, 0.0, 0.0003, inflate=0.0,
                        instrument="wrapper")
        self.assertLess(wrapped.ending, cheap.ending)


class Windows(unittest.TestCase):
    def test_a_short_history_produces_no_window_rather_than_a_short_one(self) -> None:
        """VOO has sixteen years. It must be refused, not measured on a truncated plan
        and printed as though it had survived one."""

        returns = [0.005] * 192
        self.assertEqual(
            wc.windows_for(returns, [0.0] * 192, months(192), 20, 3), [])

    def test_monthly_returns_and_keys_are_aligned(self) -> None:
        series = {date(2000, 1, 31): 100.0, date(2000, 2, 29): 110.0,
                  date(2000, 3, 31): 99.0}
        factors = {d: 1.0 for d in series}
        returns, rates, keys = wc.monthly(series, factors)
        self.assertEqual(keys, [date(2000, 2, 29), date(2000, 3, 31)])
        self.assertAlmostEqual(returns[0], 0.10)
        self.assertAlmostEqual(returns[1], -0.10)
        self.assertEqual(rates, [0.0, 0.0])

    def test_the_last_day_of_a_month_is_the_close(self) -> None:
        series = {date(2000, 1, 3): 90.0, date(2000, 1, 31): 100.0}
        returns, _rates, _keys = wc.monthly(
            {**series, date(2000, 2, 1): 105.0}, {d: 1.0 for d in series})
        self.assertAlmostEqual(returns[0], 0.05)


class TargetPaths(unittest.TestCase):
    """A window may carry its own month-by-month exposure instead of one constant leverage.

    The mechanism exists so a weight can never be lined up against the wrong month. These
    tests exist because the version that dropped `window[3]` on the floor still ran, still
    printed a table, and printed $0 in the median column for every policy row — the worst
    kind of failure, since $0 is a number a reader argues with instead of a crash they fix.
    """

    CRASH = ([0.005] * 24 + [-0.12] * 6 + [0.06] * 6 + [0.005] * 204)[:240]

    def _windows(self, windows, want):
        """Every helper goes through here, because an empty window list once made three of
        these tests pass by measuring nothing at all. `want` is not decoration."""

        self.assertEqual(len(windows), want, "the test measured nothing")
        return windows

    def _capacity(self, windows, lever=0.0, want=1):
        return wc.capacity(self._windows(windows, want), lever, 0.0, 0.0,
                           tolerance=1e-4, steps=60)[0] * wc.START

    def _per_window(self, windows, lever=0.0, want=1):
        return wc.per_window(self._windows(windows, want), lever, 0.0, 0.0, "margin",
                            wc.MAINTENANCE_EQUITY, 0.0, tolerance=1e-4, steps=60)[0] * wc.START

    def test_a_constant_path_is_the_same_thing_as_that_leverage(self) -> None:
        """1.25 written out two hundred and forty times must be indistinguishable from
        lever=1.25. If the path is wired to anything other than the same exposure, the
        equality below stops being exact."""

        path = wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1,
                             weights=[1.25] * 240)
        flat = wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1)
        self.assertEqual(self._capacity(path), self._capacity(flat, 1.25))

    def test_per_window_honours_the_path_it_was_given(self) -> None:
        """The negative control for the dropped-column bug: two paths on identical returns
        differing only in exposure must disagree, and each must match the same exposure
        written as a flat leverage."""

        thin = wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1,
                             weights=[0.5] * 240)
        fat = wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1,
                            weights=[1.5] * 240)
        flat = wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1)
        self.assertGreater(self._per_window(thin), self._per_window(fat),
                           "the path changed nothing in the median column")
        self.assertAlmostEqual(self._per_window(thin), self._per_window(flat, 0.5), places=6)
        self.assertAlmostEqual(self._per_window(fat), self._per_window(flat, 1.5), places=6)

    def test_the_path_is_aligned_to_the_window_that_carries_it(self) -> None:
        """Same weights, opposite alignment against the same crash, must not score the same.

        The crash lands in month 24. The shielded path holds the floor across months 20–50
        and the ceiling across 100–130; the exposed path is its exact permutation, those two
        blocks swapped. Identical mean, identical multiset of weights — so any difference in
        the frontier is alignment and nothing else, which is the whole claim of carrying the
        path inside the window rather than indexing a shared array by position.
        """

        def path(shield_first: bool) -> list[float]:
            out = [0.8] * 240
            out[20:50] = [0.3] * 30 if shield_first else [1.3] * 30
            out[100:130] = [1.3] * 30 if shield_first else [0.3] * 30
            return out

        shielded, exposed = path(True), path(False)
        self.assertEqual(sorted(shielded), sorted(exposed))
        self.assertAlmostEqual(sum(shielded), sum(exposed), places=9)
        good = self._capacity(wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1,
                                            weights=shielded))
        bad = self._capacity(wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1,
                                           weights=exposed))
        self.assertGreater(good, 0.0, "the shielded path should pay something")
        self.assertLess(bad, good, "the same weights aligned the other way made no "
                                   "difference, so the slice is not attached to the month")

    def test_an_empty_window_list_is_refused_rather_than_paid(self) -> None:
        """A VOO-length history yields no 20-year window. `reliable` on no windows is
        vacuously true, so an unguarded frontier came out as the top of the grid: a $6,000
        a month for a sleeve that was never scored at all."""

        short = wc.windows_for([0.005] * 228, [0.0] * 228, months(228), 20, 3)
        self.assertEqual(short, [])
        for call in (lambda: wc.capacity(short, 1.0, 0.0, 0.0),
                     lambda: wc.per_window(short, 1.0, 0.0, 0.0, "margin",
                                           wc.MAINTENANCE_EQUITY, 0.0),
                     lambda: wc.smallest_cheque(short, 1.0, 0.0, 0.0, "margin",
                                                wc.MAINTENANCE_EQUITY, 0.0, None, 0.01)):
            with self.assertRaises(ValueError):
                call()

    def test_each_window_gets_its_own_slice_and_not_the_shared_array(self) -> None:
        """Handing every window the whole weight array is invisible to a single-window test
        and fatal to a multi-start table: window two would be scored on window one's
        decisions. A ramp makes the two slices impossible to confuse for each other."""

        ramp = [float(i) for i in range(480)]
        windows = wc.windows_for(self.CRASH + self.CRASH, [0.0] * 480, months(480), 20,
                                240, weights=ramp)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0][3], ramp[0:240])
        self.assertEqual(windows[1][3], ramp[240:480])
        self.assertEqual(len(windows[1][3]), len(windows[1][0]))

    def test_a_path_shorter_than_the_window_holds_its_last_weight(self) -> None:
        """The closing rebalance asks for a weight one month past the end. A path has nothing
        to say about a month that is not in it, so the last known weight is held — and the
        last month's weight is used, not skipped."""

        short = wc.run(self.CRASH, FLAT_CASH, 1.0, 400.0, 0.0, inflate=0.0,
                       targets=[1.0] * 239)
        whole = wc.run(self.CRASH, FLAT_CASH, 1.0, 400.0, 0.0, inflate=0.0,
                       targets=[1.0] * 240)
        self.assertAlmostEqual(short.ending, whole.ending, places=6)
        tail = wc.run(self.CRASH, FLAT_CASH, 1.0, 400.0, 0.0, inflate=0.0,
                      targets=[1.3] * 239 + [0.3])
        self.assertNotAlmostEqual(tail.ending, whole.ending, places=6)

    def test_a_dead_leverage_without_a_path_is_refused(self) -> None:
        """0.0× with no path is an empty account, not a policy. It must raise rather than
        hand back the $0 that a caller would otherwise publish as a result."""

        flat = wc.windows_for(self.CRASH, FLAT_CASH, months(240), 20, 1)
        with self.assertRaises(ValueError):
            wc.capacity(flat, 0.0, 0.0, 0.0)
        with self.assertRaises(ValueError):
            wc.smallest_cheque(flat, 0.0, 0.0, 0.0, "margin", wc.MAINTENANCE_EQUITY,
                               0.0, None, 0.01)


if __name__ == "__main__":
    unittest.main()
