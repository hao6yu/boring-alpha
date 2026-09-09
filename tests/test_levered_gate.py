"""Tests for `tools/levered_gate.py` — the same rule at leverage, billed at posted rates.

The classes below are ordered by what they refuse to accept:

  `TheWiring`      the tool must reduce, to the cent, to the round-9/round-10 tool it claims to
                   inherit. It is a new simulator until it does that, and a new simulator of a rule
                   already measured is how two tables start disagreeing about the same account.
  `TheGuards`      every device that is supposed to say no — the clip refusal, the warm-up floor,
                   the review calendar, the solver's brackets — has to be seen saying it. A guard
                   that has never fired is scenery (rule r10).
  `TheControls`    the flat books must be the exposure the policy actually took, and the comparator
                   must not be handicapped by a band it was never specified to have. The bug this
                   class pins was in the first draft of the tool and flattered every row above it.
  `TheBill`        a desk posting the cash rate must bill no spread, and a desk posting more must
                   bill more. The dollar column is only a bill if it moves with the rate.
  `WhatTheGridSays` the shipped numbers, and the two that decide whether the decision is worth
                   anything at scale.
"""

from __future__ import annotations

import io
from datetime import date
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import financing_break_even as fbe  # noqa: E402
import funded_policy as fp  # noqa: E402
import withdrawal_capacity as wc  # noqa: E402
import levered_gate as lg  # noqa: E402
import run_voltarget_scan as engine  # noqa: E402

CELL = ("SPY", "recent")


def _menu_rate(name: str) -> float:
    return dict(fbe.MENU)[name]


class TheWiring(unittest.TestCase):
    def test_priced_at_the_engines_own_assumption_it_is_round_tens_tool(self):
        """The load-bearing test: same rate, same cent as the tool this one claims to extend.

        `levered_gate` re-prices the engine's borrow to a posted rate, so at a posted rate equal to
        the engine's standing spread — `BORROW_SPREAD`, whatever value it currently carries — it must reproduce
        `funded_policy`'s as-traded row exactly — same fills, same ending. Anything else means the
        two tools hold two engines, and then neither table means what it says.
        """

        cash = fbe.annualised_cash(fbe.cell("recent", "SPY")[3])
        saved = fbe.MENU
        fbe.MENU = tuple((n, (cash + engine.BORROW_SPREAD) if n == lg.DESKS[0] else r)
                        for n, r in fbe.MENU)
        lg._DCA.clear()
        try:
            cell = lg.score("SPY", "recent", 1.0)
            reference = dict(fp.score("SPY", "recent"))["candidate (as traded)"]
        finally:
            fbe.MENU = saved
            lg._DCA.clear()
        assert cell["runs"][(lg.DESKS[0], "gate")].turns == reference.turns
        assert cell["runs"][(lg.DESKS[0], "gate")].ending == pytest.approx(
            reference.ending, abs=0.01)

    def test_the_flat_control_is_the_round_eleven_book(self):
        """The exposure control is imported from round 11's machinery, not restated.

        Two facts, and they are different things. The constant the control was *set* to is the gate
        run's realized average — that is the design. The control's own realized average then comes
        back a little below that constant (1.348 against 1.385 at 1.5x on SPY recent), because a
        banded book drifts down from its target between reviews while deposits sit in cash. Checking
        the wrong pair either fails a correct implementation or admits a control set to the wrong
        number, so the set value is checked against the run it came from, the drift direction is
        checked, and the mirror run through round 11's own `priced` is checked against the total.
        """

        cell = lg.score(*CELL, 1.5)
        set_to = cell["cell"]["average"][lg.DESKS[0]]
        assert set_to == pytest.approx(cell["runs"][(lg.DESKS[0], "gate tight")].avg_weight,
                                       abs=1e-9)
        assert cell["flat"].avg_weight == pytest.approx(set_to, abs=0.06)
        assert cell["flat"].avg_weight < set_to                 # drift under a band, always down
        mirror = fbe.priced(CELL[0], CELL[1], set_to,
                            lg.spread_for(_menu_rate(lg.DESKS[0]), lg.series(*CELL)[3]), lg.BAND)
        # Not equal, and equality would be the failure: round 11's book opens on session 1 of its
        # window and every row here opens on the session the *policy* can first answer, which is
        # session 29 on SPY — the convention round 9 established, because a comparator handed two
        # hundred sessions of compounding the policy never had is not a comparator. Same engine,
        # same costs, same weight, a four-week head start apart.
        assert abs(cell["flat"].ending - mirror.ending) / mirror.ending < 0.01
        assert cell["flat"].carry_paid > 0                     # the borrow is actually billed

    def test_scaling_the_answer_is_scaling_the_rule(self):
        """Doubling the lever doubles every weight, so every clip still fires where it fired."""

        dates, closes, returns, _f = lg.series(*CELL)
        base = lg.levered_desired(1.0, closes, returns)
        double = lg.levered_desired(2.0, closes, returns)
        pairs = [(a, b) for a, b in zip(base, double) if a is not None]
        assert pairs and all(abs(b / a - 2.0) < 1e-12 for a, b in pairs)
        assert sum(b is None for b in double) == sum(a is None for a in base)


class TheGuards(unittest.TestCase):
    def test_a_lever_that_would_clip_the_rule_is_refused(self):
        """Past 2.30x the candidate's own cap leaves the range its class calls credible.

        Clipping instead of refusing would swap the rule for a different one at exactly the point
        where the rule is being asked to pay, and the table would not say so.
        """

        dates, closes, returns, _f = lg.series(*CELL)
        with pytest.raises(ValueError, match="credible"):
            lg.levered_desired(2.5, closes, returns)
        lg.levered_desired(2.3, closes, returns)          # the ceiling itself is answerable

    def test_a_window_too_short_to_open_an_account_is_refused(self):
        """Eight months of prices cannot answer a question asked over thirty-three years.

        Patched on `financing_break_even.WINDOWS`, which is the dict the slice is actually cut
        from — this tool's own `WINDOWS` is a name bound at import, and editing it changes nothing,
        which is exactly how a guard test ends up testing a window nobody asked about.
        """

        saved = fbe.WINDOWS
        lg._DCA.clear()
        fbe._CACHE.pop(("recent", "SPY"), None)
        # Long enough to clear round 11's one-year floor (335 sessions) and too short to open an
        # account at session 29 and measure four hundred more, so it is *this* guard that refuses.
        fbe.WINDOWS = {**fbe.WINDOWS, "recent": (date(2025, 6, 1), fp.WINDOWS["recent"][1])}
        try:
            with pytest.raises(ValueError, match="not enough"):
                lg.cell_books("SPY", "recent", 1.0)
        finally:
            fbe.WINDOWS = saved
            fbe._CACHE.pop(("recent", "SPY"), None)
            lg._DCA.clear()

    def test_the_calendar_control_cannot_trade_on_a_session_it_is_not_let_on_to(self):
        """A cadence gate that cannot refuse is decoration, so ask it to refuse."""

        session_count = len(lg.series(*CELL)[0])
        allowed = lg.review_calendar(session_count)
        assert len(allowed) == pytest.approx(session_count / lg.CADENCE, abs=1)
        cell = lg.score(*CELL, 2.0)
        # One fill per reviewed session at most, plus the opening fill, which is not a rebalance.
        assert cell["matched"].turns <= len(allowed) + 1
        # ...and the same book with the calendar removed does trade more, which is what makes the
        # limit above a refusal rather than an accident of drift.
        dates, closes, returns, factors = lg.series(*CELL)
        saved = engine.BORROW_SPREAD
        engine.BORROW_SPREAD = 0.0
        try:
            ungated = engine.funded(closes, returns, factors, dates,
                                    targets=[cell["matched"].avg_weight] * session_count,
                                    band=lg.TIGHT,
                                    start=fp.first_live(lg.levered_desired(1.0, closes, returns)))
        finally:
            engine.BORROW_SPREAD = saved
        assert ungated.turns > cell["matched"].turns

    def test_the_solver_reports_which_branch_it_took(self):
        """All three branches, each named, each from a cell that is known to land on it.

        The solver can answer three ways and a solver that silently reports a bracket as a crossing
        is the failure mode that would flatter the whole matched-pain table: a leverage pinned to
        the ceiling is a *refusal* to answer, not an answer.
        """

        cells = {"VOO full": ("VOO", "full"), "SPY recent": ("SPY", "recent"),
                 "QQQ full": ("QQQ", "full"), "SPY full": ("SPY", "full")}
        out = {name: lg.dd_match(symbol, window) for name, (symbol, window) in cells.items()}
        for m in out.values():
            assert 1.0 <= m["lever"] <= 2.3 + 1e-9
            assert m["note"]
        # The drawdown is what was solved for, so the drawdown is what a "solved" answer has to
        # deliver. Pinning the lever instead is how the first version of this test survived a
        # bisection whose bracket was moved the wrong way: inverted, it still lands a hair inside
        # the interval after sixteen halvings and prints a plausible-looking table.
        for name in ("VOO full", "SPY recent"):
            assert out[name]["solved"], out[name]["note"]
            assert abs(out[name]["dd_gap"]) <= 0.006, (name, out[name]["dd_gap"])
            assert 1.0 < out[name]["lever"] < 2.3
        assert not out["QQQ full"]["solved"] and "cap binding" in out["QQQ full"]["note"]
        assert out["SPY full"]["solved"]                       # the crossing is inside the bracket
        # The third branch — already as deep as the index at the floor of the bracket — has to be
        # reached deliberately, by raising the floor, and it must report the floor rather than a
        # crossing. VTI since 2010 at 2.3x is 16 points deeper than its own index, so the solve has
        # nothing left to solve for.
        floor = lg.dd_match("VTI", "since 2010", low=2.3)
        assert not floor["solved"] and floor["lever"] == 2.3 and "1.0x" in floor["note"]

    def test_the_solver_is_bounded_and_monotone(self):
        """Deeper leverage must not make the worst month shallower, or the solve means nothing."""

        draws = [lg.gate_at(*CELL, lev).max_drawdown for lev in (1.0, 1.25, 1.5, 2.0, 2.3)]
        # Drawdown is stored negative, so "worse" means smaller each step.
        assert all(b <= a + 1e-9 for a, b in zip(draws, draws[1:])), draws


class TheControls(unittest.TestCase):
    def test_the_comparator_is_not_handed_the_policys_band(self):
        """The bug the first draft shipped with, pinned as a refusal.

        A 10% dead band on a book that is supposed to spend each deposit on arrival parks the
        deposit in cash: the comparator ends under-invested and cheaper to beat. Passing the
        candidate's band to every row looked like tidiness and was a handicap.
        """

        cell = lg.score(*CELL, 1.0)
        assert cell["base"].avg_weight == pytest.approx(1.0, abs=1e-3)
        dates, closes, returns, factors = lg.series(*CELL)
        engine.BORROW_SPREAD, saved = 0.0, engine.BORROW_SPREAD
        handicapped = engine.funded(closes, returns, factors, dates, targets=[1.0] * len(dates),
                                    band=lg.BAND, start=cell["cell"]["warmup"])
        engine.BORROW_SPREAD = saved
        assert handicapped.ending < cell["base"].ending
        assert handicapped.avg_weight < cell["base"].avg_weight

    def test_the_control_tracks_the_run_not_the_label(self):
        """The exposure control is set from realized weights, so it cannot drift off the run."""

        low, high = lg.score(*CELL, 1.0), lg.score(*CELL, 2.0)
        assert low["flat"].avg_weight < high["flat"].avg_weight
        for cell in (low, high):
            set_to = cell["cell"]["average"][lg.DESKS[0]]
            assert set_to == pytest.approx(cell["avg_weight"], abs=1e-9)
            assert cell["flat"].avg_weight == pytest.approx(set_to, abs=0.06)
        # The gate averages well below the nominal 2x: that is the band and the gate at work, and
        # it is why a control pinned to the lever would be a different amount of risk.
        assert high["avg_weight"] < 2.0 * low["avg_weight"] * 1.2

    def test_the_worse_of_the_two_controls_is_the_one_quoted(self):
        """`vs_control` is the minimum gap, never the flattering one."""

        for lev in (1.0, 1.5, 2.0):
            cell = lg.score(*CELL, lev)
            assert cell["vs_control"] == min(cell["vs_flat"], cell["vs_matched"])
            assert cell["beats_control"] == (cell["vs_control"] > 0)


class TheBill(unittest.TestCase):
    def test_a_desk_posting_the_cash_rate_bills_no_spread(self):
        """The invariant the whole menu rests on: cash in, zero out.

        The engine accrues `cash_daily + spread`, so a desk whose posted rate *is* the cash rate is
        a book with no spread, and its carry must be nil. If `spread_for` ever charged the cash rate
        twice, this would die — and every desk on the menu would be overcharged by 150-400 bps.
        """

        factors = lg.series(*CELL)[3]
        cash = fbe.annualised_cash(factors)
        assert lg.spread_for(cash, factors) == pytest.approx(0.0, abs=1e-12)
        dates, closes, returns, _f = lg.series(*CELL)
        path = [None if w is None else w for w, _ in fp.CANDIDATE.weights(closes, returns)]
        warmup = fp.first_live(path)
        saved = engine.BORROW_SPREAD
        engine.BORROW_SPREAD = lg.spread_for(cash, factors)          # the zero-spread desk
        try:
            free = engine.funded(closes, returns, factors, dates, targets=path, band=lg.TIGHT,
                                 start=warmup, allow=fp.reviewed_sessions(path))
        finally:
            engine.BORROW_SPREAD = saved
        assert free.carry_paid == pytest.approx(0.0, abs=1e-6)

    def test_the_spread_is_the_posted_rate_min_the_windows_cash(self):
        factors = lg.series(*CELL)[3]
        cash = fbe.annualised_cash(factors)
        assert lg.spread_for(0.10575, factors) == pytest.approx(0.10575 - cash, abs=1e-12)
        # A rate below the cash rate floors rather than going negative: nobody pays you to borrow.
        # The floor only bites when the posted rate is more than five points below the window's
        # cash, which no desk does: it is a guard against a nonsense input, not a rate.
        assert lg.spread_for(0.0, factors) == pytest.approx(-cash, abs=1e-12)
        assert lg.spread_for(cash - 0.20, factors) == pytest.approx(-0.05, abs=1e-12)

    def test_a_dearer_desk_ends_the_same_book_lower(self):
        cheap = lg.gate_at(*CELL, 2.0, lg.DESKS[0])
        dear = lg.gate_at(*CELL, 2.0, lg.DESKS[1])
        assert cheap.ending > dear.ending
        assert dear.carry_paid > cheap.carry_paid

    def test_the_sleeves_expense_ratio_is_applied_not_the_engines_default(self):
        """QQQ costs 20 bps and VTI 3. At the same weight on the same days they cannot agree.

        Patched at the table the tool reads rather than at the engine constant, because the tool
        sets that constant itself on every call — patching it here would test the test.
        """

        qqq = lg.gate_at("QQQ", "full", 1.0, lg.DESKS[0])
        vti = lg.gate_at("VTI", "full", 1.0, lg.DESKS[0])
        assert qqq.carry_paid > 0 and vti.carry_paid > 0
        saved = wc.EXPENSE["QQQ"]
        wc.EXPENSE["QQQ"] = wc.EXPENSE["VTI"]
        try:
            cheap_priced = lg.gate_at("QQQ", "full", 1.0, lg.DESKS[0])
        finally:
            wc.EXPENSE["QQQ"] = saved
        assert cheap_priced.ending > qqq.ending


class WhatTheGridSays(unittest.TestCase):
    def test_the_lever_clears_the_index_everywhere_and_earns_the_drawdown_back(self):
        """The two shipped claims: 15 of 15 cells clear DCA at 1.5x, and the hole stays shallower."""

        leg = [lg.score(s, w, 1.5) for w in lg.WINDOWS for s in lg.SLEEVES]
        assert all(t["clears_cheap"] for t in leg)
        assert sum(1 for t in leg if t["dd"] > t["dd_dca"]) >= 10
        assert sum(t["calls"] for t in leg) == 0

    def test_the_timing_claim_is_the_majority_that_it_is_not(self):
        """At most leverage the decision beats both exposure controls in under two thirds of cells.

        This is the number that keeps the note honest: the row clears the index everywhere and
        still loses to a book with no decision in it more often than not.
        """

        leg = [lg.score(s, w, 2.3) for w in lg.WINDOWS for s in lg.SLEEVES]
        assert sum(1 for t in leg if t["beats_control"]) < 12
        assert sum(1 for t in leg if t["vs_rev"] > 0) == 15       # the ordering is not a coin flip

    def test_higher_leverage_buys_margin_calls_not_safety(self):
        assert sum(t["calls"] for t in (lg.score(s, w, 1.5) for w in lg.WINDOWS
                                       for s in lg.SLEEVES)) == 0
        assert sum(t["calls"] for t in (lg.score(s, w, 2.3) for w in lg.WINDOWS
                                       for s in lg.SLEEVES)) > 0

    def test_the_verdict_line_names_which_test_failed(self):
        """A verdict that does not say which of its two conditions failed cannot be argued with."""

        tally = [
            {"lever": 1.0, "clears_cheap": True, "beats_control": False, "vs_flat": 10.0,
             "vs_matched": -10.0, "vs_rev": 1.0, "vs_ungated": 1.0, "mo_cheap": 1.0,
             "mo_dear": -1.0, "dd": -0.4, "dd_flat": -0.6, "dd_dca": -0.5, "calls": 0,
             "ruined": False, "both_axes": False, "both_axes_dear": False, "clears_dear": False}
            for _ in range(3)
        ]
        out = io.StringIO()
        with redirect_stdout(out):
            verdict = lg.reading(tally)
        text = out.getvalue()
        assert verdict == "B"
        assert "verdict B" in text and "the timing test fails" in text

    def test_a_stub_verdict_is_not_a_pass(self):
        """Negative control on the previous test: a clear-and-beat tally must not read as B."""

        tally = [
            {"lever": 1.0, "clears_cheap": True, "beats_control": True, "vs_flat": 10.0,
             "vs_matched": 10.0, "vs_rev": 1.0, "vs_ungated": 1.0, "mo_cheap": 1.0,
             "mo_dear": 1.0, "dd": -0.4, "dd_flat": -0.6, "dd_dca": -0.5, "calls": 0,
             "ruined": False, "both_axes": True, "both_axes_dear": True, "clears_dear": True}
            for _ in range(3)
        ]
        out = io.StringIO()
        with redirect_stdout(out):
            verdict = lg.reading(tally)
        assert verdict == "A" and "verdict A at 1.00x" in out.getvalue()
