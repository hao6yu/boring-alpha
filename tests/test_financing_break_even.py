"""Tests for `financing_break_even`: the solver, the menu, and the two guards it leans on.

The mechanism being priced here is the only one left standing after ten rounds, and it hangs on
one input that is about the world rather than the model: what borrowing costs. So the tests here
are mostly about whether the tool can be lied to by its own wiring.

  the bisection  — a solver that returns its bracket looks identical to one that found a crossing.
      The only test is the residual: reprice at the answer and check the gap actually went to zero.
  monotonicity   — more leverage must need cheaper money. If this ever inverts, the solver is
      reading its bracket backwards and every "clears" verdict in the tool is inverted with it.
  no answer      — a 1.0x book borrows nothing. Answering "break-even: 0 bps" for it would be the
      most flattering possible way to print a zero, so the function raises instead.
  the guards     — round 10's rule, applied to the two things this tool assumes: the maintenance
      branch that disqualifies high leverage, and the band whose wedge is reported per row. The
      zero margin calls at 2x is only evidence if the guard is capable of firing, and the band's
      sign is only informative if it has been seen to flip.
  the bill       — the break-even *spread* and the bill at a *posted rate* disagree on this
      archive, by design, because the window's cash rate is not today's. One of them decides the
      verdict column and a test pins which.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import financing_break_even as fbe
from financing_break_even import MENU, at_rate, break_even_spread, comparator, priced


class TheSolver(unittest.TestCase):
    def test_the_fall_through_return_reports_the_gap_at_the_spread_it_hands_back(self) -> None:
        """The early exit re-prices by construction; the twenty-iteration fall-through did not, until round 98.

        A tolerance the loop can never satisfy forces the path where the reported residual came from the *previous probe*,
        a different spread from the narrowed midpoint — on a step-discontinuous function that is a few dollars of lie.
        """

        be, residual = break_even_spread("SPY", "full", 2.0, tolerance=1e-9)
        self.assertIsNotNone(be)
        fresh = priced("SPY", "full", 2.0, be, fbe.TIGHT).ending - comparator("full", "SPY").ending
        self.assertAlmostEqual(fresh, residual, delta=0.01,
                               msg="the fall-through path reported the search's residual, not the answer's")

    def test_the_answer_is_a_real_crossing_not_the_bracket(self) -> None:
        """Reprice at the spread the bisection returned: the gap has to actually be zero. A
        solver that quietly returns its midpoint would still print something plausible."""

        be, residual = break_even_spread("SPY", "full", 2.0)
        self.assertIsNotNone(be)
        self.assertLess(abs(residual), 50.0,
                        f"the solver returned {be:.4%} and left a ${residual:,.0f} gap")
        fresh = priced("SPY", "full", 2.0, be, fbe.TIGHT).ending - comparator("full", "SPY").ending
        self.assertAlmostEqual(fresh, residual, delta=1.0,
                               msg="the reported residual disagrees with a fresh run at the "
                                   "spread returned")

    def test_the_solver_and_the_verdict_price_the_same_mandate(self) -> None:
        """The band the solver prices at is not a detail. Solving under a 10% band while billing
        under a 1% one gave a break-even 40-65 bps more generous than the row it was supposed to
        describe: two reasonable-looking lines of code telling a lie in the flattering direction.
        Both halves must be the same execution of the same mandate, and the pin below is that
        requirement expressed as a number.
        """

        tight, _ = break_even_spread("SPY", "full", 1.5)
        self.assertLess(abs(tight - 0.0569), 0.002,
                        f"the solved spread moved to {tight:.4%}; check the band and the archive")
        wide_band = priced("SPY", "full", 1.5, tight, 0.10)
        self.assertGreater(wide_band.ending, priced("SPY", "full", 1.5, tight, fbe.TIGHT).ending,
                          "the wide band no longer flatters this cell; the wedge needs re-reading")

    def test_room_shrinks_as_the_book_gets_levered(self) -> None:
        """More borrowed needs cheaper money, monotonically. An inversion means the bisection is
        reading its bracket backwards and every verdict in the tool is inverted with it."""

        rooms = [break_even_spread("SPY", "full", lever)[0] for lever in (1.25, 1.5, 2.0)]
        for (a, b), lever in zip(zip(rooms, rooms[1:]), (1.5, 2.0)):
            self.assertGreater(a, b, f"the room at {lever}x was not narrower than before it")
        self.assertGreater(rooms[2], 0.03, "the room went to nearly nothing; check the archive")

    def test_free_financing_beats_dca_and_thirty_percent_does_not(self) -> None:
        """Both ends of the bracket, asserted rather than assumed. If the zero-spread end is not
        positive the whole idea is dead here; if the thirty-percent end is not negative the
        bracket never contained a crossing and the solver was interpolating fiction."""

        base = comparator("full", "SPY")
        self.assertGreater(priced("SPY", "full", 1.5, 0.0).ending, base.ending)
        self.assertLess(priced("SPY", "full", 1.5, 0.30).ending, base.ending)

    def test_a_book_that_borrows_nothing_is_refused_the_question(self) -> None:
        """1.0x has no break-even: it never borrows, so its gap is timing noise and every spread
        satisfies the equation vacuously. A zero printed there would read as the cheapest, most
        conservative result on the grid."""

        for lever in (1.0, 0.5):
            with self.assertRaises(ValueError):
                break_even_spread("SPY", "full", lever)

    def test_no_answer_comes_back_as_no_answer_when_leverage_cannot_pay(self) -> None:
        """Every real cell on this archive beats DCA with money for free, so the `None` branch is
        unreachable by honest means and would rot into dead code if left untested. Reach it by
        stubbing the engine: a book that loses at zero spread has no spread that rescues it, and
        the tool must say so rather than report the bottom of its bracket as if it were a price.
        """

        class Loser:
            ending = 1.0

        real = fbe.priced
        try:
            fbe.priced = lambda *a, **k: Loser()
            be, gap = break_even_spread("SPY", "full", 1.5)
        finally:
            fbe.priced = real
        self.assertIsNone(be, "a hopeless cell was handed a break-even number anyway")
        self.assertLess(gap, 0.0)


class TheGuardsAreAlive(unittest.TestCase):
    def test_the_maintenance_guard_can_actually_fire(self) -> None:
        """Round 10's rule applied to the constraint this tool leans on. Zero margin calls at 2x
        is only a measurement if the branch is capable of firing; at 3x on the same sleeve it
        fires twenty-odd times, so the zero above it is evidence and not a dead guard."""

        two = priced("SPY", "full", 2.0, 0.015, fbe.TIGHT)
        three = priced("SPY", "full", 3.0, 0.015, fbe.TIGHT)
        self.assertEqual(two.margin_calls, 0, "2x now trips maintenance; the grid's premise moved")
        self.assertGreater(three.margin_calls, 0,
                           "the forced-sale branch never fires at 3x either; it is decorative, and "
                           "every disqualified row in leverage_sizing was never disqualified")

    def test_the_band_wedge_has_been_seen_to_go_both_ways(self) -> None:
        """The band is not simply a cost. At low leverage it parks deposits in cash and the wedge
        is six figures in the wrong direction; at 2x on QQQ it also suppresses the forced
        sell-back-to-target through a V-shaped collapse, which pays. If the sign stops flipping,
        the column stopped measuring something."""

        self.assertGreater(fbe.band_wedge("SPY", "full", 1.25), 50_000)
        self.assertLess(fbe.band_wedge("QQQ", "full", 2.0), 0.0)

    def test_a_window_too_short_to_be_solved_is_refused(self) -> None:
        """Without the guard a short slice returns a small account and a small gap, which looks
        like a modest result rather than like nothing being measured."""

        saved = fbe.WINDOWS["full"]
        try:
            fbe._CACHE.pop(("full", "SPY"), None)   # a warm cache answers before the guard
            fbe.WINDOWS["full"] = (date(2026, 6, 1), date(2026, 9, 4))
            with self.assertRaises(ValueError):
                fbe.cell("full", "SPY")
        finally:
            fbe.WINDOWS["full"] = saved
            fbe._CACHE.pop(("full", "SPY"), None)


class TheBillDecides(unittest.TestCase):
    def test_the_comparator_buys_every_deposit_and_borrows_nothing(self) -> None:
        base = comparator("full", "SPY")
        # Not exactly zero, and the reason is worth knowing: an unlevered buy pays its 2 bps
        # fee out of the cash that arrived that day, leaving the account in debit for one
        # session and charging it the borrow spread. Over 33 years that is a quarter of a cent.
        self.assertLess(base.carry_paid, 0.05, "the unlevered comparator is being charged carry")
        self.assertLess(base.cost_paid, 200.0,
                        "the comparator's turnover bill is implausible for a buy-and-hold")
        self.assertGreater(base.turns, 400, "the comparator stopped investing deposits")

    def test_trailing_cash_is_not_the_window_average(self) -> None:
        """The two columns exist because these differ by more than a rounding. If they ever agree,
        the distinction this class exists to defend has gone."""

        factors = fbe.cell("full", "SPY")[3]
        self.assertGreater(abs(fbe.trailing_cash(factors) - fbe.annualised_cash(factors)), 0.005)

    def test_a_desk_charging_the_cash_rate_is_a_book_with_no_spread(self) -> None:
        """The invariant `at_rate` exists to hold: bill a desk at exactly the window's own cash
        rate and the book must cost the same as one financed spread-free. Pass the posted rate
        straight through as the spread — the obvious mistake, since the engine's argument is a
        spread — and the window's cash rate gets charged twice, overstating every desk by 150-400
        bps, which is most of the margin this tool was written to measure. The earlier version of
        this class had a test that survived exactly that mutation, because it only ever asserted
        the bill was negative; an assertion that only one direction can break it is half a test.
        """

        window, symbol, lever = "since 2010", "VTI", 2.0
        window_cash = fbe.annualised_cash(fbe.cell(window, symbol)[3])
        as_desk = fbe.at_rate(symbol, window, lever, window_cash)
        as_spread = fbe.priced(symbol, window, lever, 0.0, fbe.TIGHT)
        self.assertAlmostEqual(as_desk.ending, as_spread.ending, delta=1.0,
                               msg=f"a desk at the cash rate cost ${as_desk.ending - as_spread.ending:,.0f} "
                                   "more than the same book with no spread")

    def test_the_verdict_is_the_bill_and_not_the_room(self) -> None:
        """The discriminating one, and the cell is chosen for the margin: VTI since 2010 at 2.0x
        leaves 834 bps of room and E*TRADE's spread over today's cash is 664, so the spread
        comparison says the desk clears. Billed at E*TRADE's posted 10.45% in a window whose own
        cash averaged 1.51%, the same row loses — because financing is a nominal cost and the
        window's money market was not today's. The tool reports the loss. A later refactor that
        'reconciles' the two by adopting the friendly basis will fail here, which is the point."""

        room, _residual = break_even_spread("VTI", "since 2010", 2.0)
        spread_today = 0.1045 - fbe.trailing_cash(fbe.cell("since 2010", "VTI")[3])
        self.assertGreater(room, spread_today + 0.005,
                           "the spread basis no longer disagrees here; find a cell that still "
                           "does and repin this, rather than deleting the disagreement")
        self.assertLess(fbe.at_rate("VTI", "since 2010", 2.0, 0.1045).ending,
                        comparator("since 2010", "VTI").ending,
                        "the verdict column followed the spread instead of the bill")

    def test_a_desk_that_clears_implies_every_cheaper_desk_clears(self) -> None:
        """Financing is the only difference between the rows, so the clearing set must be a prefix
        of the menu sorted cheapest-first. A non-prefix set means the menu is unsorted, or a rate
        is being applied twice somewhere, or the comparator is not the same run for every row.

        Written as an index check rather than as a comparison of `cleared` against itself filtered
        by menu order — which is true for any set whatever its shape, and passed happily the first
        time it was tried.
        """

        for lever in (1.25, 2.0):
            base = comparator("full", "SPY")
            flags = [at_rate("SPY", "full", lever, rate).ending > base.ending for _n, rate in MENU]
            self.assertEqual(MENU, tuple(sorted(MENU, key=lambda t: t[1])),
                             "the menu is no longer cheapest-first, so 'up to X' means nothing")
            last_clearing = max((i for i, f in enumerate(flags) if f), default=-1)
            self.assertEqual(flags[:last_clearing + 1], [True] * (last_clearing + 1),
                             f"at {lever}x a desk clears while a cheaper one beside it does not")


class WhatTheGridSays(unittest.TestCase):
    """The load-bearing cells only: the tool takes six seconds over the whole grid and the suite
    should not pay for that twice."""

    def test_the_mechanism_clears_the_cheap_end_of_the_menu_everywhere(self) -> None:
        positive = 0
        checked = 0
        for window in fbe.WINDOWS:
            for symbol in fbe.SLEEVES:
                for lever in fbe.LEVERS:
                    if len(fbe.cell(window, symbol)[0]) < 252:
                        continue
                    checked += 1
                    positive += at_rate(symbol, window, lever, MENU[0][1]).ending > \
                        comparator(window, symbol).ending
        self.assertEqual(checked, 45, "the grid stopped being 5 sleeves by 3 windows by 3 levers")
        self.assertEqual(positive, checked,
                         f"{checked - positive} cells fail even at the cheapest desk on the menu")

    def test_the_deepest_row_on_the_grid_is_not_silently_bearable(self) -> None:
        """The drawdown is the price of the only surviving mechanism, so it is pinned rather than
        mentioned: the worst cell on the grid loses nine-tenths of its peak value, and any write-up
        that quotes the monthly dollars without this number is advertising."""

        worst = min(priced(s, w, l, 0.015, fbe.TIGHT).max_drawdown
                    for w in fbe.WINDOWS for s in fbe.SLEEVES for l in fbe.LEVERS)
        self.assertLess(worst, -0.90, f"the deepest row is only {worst:.1%}; re-quote the grid")


if __name__ == "__main__":
    unittest.main()
