"""Tests for scoring the paper candidate as a spending plan.

The claim under test is narrow: a vol target with a trend gate raises the *withdrawal floor*
because it delevers in exactly the regime that sets the floor. Four things could make that
true for the wrong reason, and each gets its own test here:

  the weight path peeks    → a gate that sees the crash coming earns its return twice, once
                             in the simulator and once in the narrative.
  the alignment is doing   → if shifting the decision by a month moved the headline, the
                             result would belong to the convention, not the rule.
  the leverage is doing    → answered by the tool's flat-at-average row; here, by the test
                             that the control row and the path share one mean.
  the ordering is noise    → the same weights read backwards must lose the edge, or the edge
                             was never about *when* the policy moved.

Everything is measured on the archive the tool measures, at the tolerances the tool uses.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper
import policy_withdrawal as pw
import withdrawal_capacity as wc
from boring_alpha.data.csv_loader import load_csv_market_data

SLEEVE = "SPY"


class Archive(unittest.TestCase):
    """Shared, loaded once. These tests read the same archive the tool reads; a fixture that
    drifts from the archive would test the fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.days = [d for d in sorted(cls.data.by_date) if SLEEVE in cls.data.by_date[d]]
        cls.closes = [cls.data.by_date[d][SLEEVE].close for d in cls.days]
        cls.returns, cls.cash, cls.keys = wc.monthly(
            {d: cls.data.by_date[d][SLEEVE].close for d in cls.days}, cls.data.cash_factors)
        cls.weights = pw.monthly_weights(pw.CANDIDATE, cls.days, cls.closes, cls.keys)

    def _frontier(self, weights=None, lever=1.0):
        windows = wc.windows_for(self.returns, self.cash, self.keys, 20, 3, weights)
        return wc.capacity(windows, lever, wc.EXPENSE[SLEEVE], 0.025, "margin",
                           wc.MAINTENANCE_EQUITY, wc.BORROW_SPREAD,
                           tolerance=0.0001, steps=60)[0] * wc.START


class NoLookAhead(Archive):
    def test_a_month_is_priced_only_on_sessions_that_already_happened(self) -> None:
        """Truncate the record at the session a month's weight is decided on — the first of
        the month, whose inputs stop the session before — and recompute. Same weight, or the
        path is reading the month it is supposed to be anticipating.

        What this test cannot see, stated because the last two rounds were about checks that
        tested the wrong object: it recomputes with the *same* code, so a window that reads
        today's close instead of yesterday's gives the same wrong answer at the same index
        and sails through. That leak is pinned one floor down, in
        `test_voltarget.py::test_moving_average_excludes_the_current_bar` and its gate
        companion, which fail the moment the window slides forward one bar. This test's job
        is the other direction: peeking into the future."""

        desired = pw.CANDIDATE.raw_weights(
            self.closes, [0.0] + [self.closes[i] / self.closes[i - 1] - 1.0
                                  for i in range(1, len(self.closes))])
        first: dict[tuple[int, int], int] = {}
        for index, day in enumerate(self.days):
            first.setdefault((day.year, day.month), index)
        checked = 0
        for month in self.keys[12:]:
            index = first[(month.year, month.month)]
            if index < 260:
                continue
            tail = pw.CANDIDATE.raw_weights(self.closes[:index + 1],
                                            [0.0] + [self.closes[i] / self.closes[i - 1] - 1.0
                                                     for i in range(1, index + 1)])
            self.assertAlmostEqual(desired[index], tail[-1], places=12,
                                   msg=f"the weight for {month} changed when the record "
                                       f"ended where it should have")
            checked += 1
            if checked == 6:
                break
        self.assertEqual(checked, 6, "too few months checked to conclude anything")

    def test_a_crash_invented_after_the_decision_leaves_the_decision_alone(self) -> None:
        """The blunt version of the same rule: append a month of collapse to the end of the
        record and check that no weight decided before it moved. Any peek in the volatility
        or trend window shows up here, including one introduced by a future vectorised
        rewrite of a loop that is currently careful."""

        returns = [0.0] + [self.closes[i] / self.closes[i - 1] - 1.0
                           for i in range(1, len(self.closes))]
        before = pw.CANDIDATE.raw_weights(self.closes, returns)
        previous, extra_closes, extra_returns = self.closes[-1], [], []
        for _step in range(21):
            previous *= 0.97
            extra_closes.append(previous)
            extra_returns.append(previous / self.closes[-1] - 1.0 if len(extra_closes) == 1
                                 else previous / extra_closes[-2] - 1.0)
        after = pw.CANDIDATE.raw_weights(self.closes + extra_closes,
                                        returns + extra_returns)
        self.assertEqual(len(after), len(before) + 21)
        for index in range(len(before) - 30, len(before)):
            self.assertEqual(before[index], after[index],
                             "a decision changed because of a crash that happened after it")

    def test_the_candidate_under_scoring_is_the_candidate_being_traded(self) -> None:
        """Five numbers are the whole strategy. Retuning them inside the scoring tool would
        answer a question nobody asked, so the tool's copy is compared to the live one."""

        self.assertEqual(pw.CANDIDATE, paper.CANDIDATE)


class TimingIsTheMechanism(Archive):
    def test_the_same_weights_read_backwards_lose_the_edge(self) -> None:
        """Identical multiset of weights, identical mean, order reversed. Whatever this row
        cannot match can only be *when* the policy moved — which is the entire claim, so the
        claim has to be this wide and not one point wide."""

        backwards = list(reversed(self.weights))
        self.assertEqual(sorted(self.weights), sorted(backwards))
        honest, reversed_own = self._frontier(self.weights), self._frontier(backwards)
        self.assertGreater(honest, 0.0)
        self.assertGreater(honest * 0.75, reversed_own,
                           f"read backwards the path still pays {reversed_own:,.0f} against "
                           f"{honest:,.0f}, so the ordering is not what is being paid for")

    def test_decision_timing_one_month_off_is_not_where_the_money_is(self) -> None:
        """Shift the whole path by a month each way. If the headline moved by a tenth, the
        result would belong to where the month boundary falls and no live book could be
        scored by this table. It must move, and it must not move much."""

        edges = {}
        for lag in (0, 1, -1):
            shifted = pw.monthly_weights(pw.CANDIDATE, self.days, self.closes, self.keys,
                                        lag)
            edges[lag] = self._frontier(shifted)
            self.assertGreater(edges[lag], 0.0, f"lag {lag} paid nothing at all")
        spread = max(edges.values()) - min(edges.values())
        self.assertGreater(spread, 0.0, "a one-month shift changed nothing, so the path "
                                       "is not being applied month by month")
        self.assertLess(spread, 0.05 * edges[0],
                        f"a one-month shift moves the floor by {spread:,.0f} on "
                        f"{edges[0]:,.0f}: the result belongs to the calendar, not the rule")

    def test_the_control_row_and_the_path_agree_on_exposure(self) -> None:
        """The flat control is only a control because its leverage is the path's own mean.
        Feed it anything else and the comparison is just leverage again."""

        mean = sum(self.weights) / len(self.weights)
        self.assertAlmostEqual(mean, sum(reversed(self.weights)) / len(self.weights),
                               places=12)
        self.assertGreater(mean, 1.0, "SPY's path averages under its own cap, which means "
                                      "the candidate row is a smaller position, and the tool "
                                      "would be comparing a discount to a benchmark")
        self.assertLess(mean, pw.CANDIDATE.max_weight)


class ThePathIsNotOptional(Archive):
    def test_a_path_window_cannot_be_scored_as_if_it_were_flat(self) -> None:
        """The tool hands the path rows a dead 0.0 leverage. Guarded: the same call on a
        path-less window list raises instead of scoring an empty account and reporting $0."""

        gated = wc.windows_for(self.returns, self.cash, self.keys, 20, 3, self.weights)
        plain = wc.windows_for(self.returns, self.cash, self.keys, 20, 3)
        self.assertEqual(len(gated), len(plain))
        wc.capacity(gated, 0.0, 0.0, 0.0)
        with self.assertRaises(ValueError):
            wc.capacity(plain, 0.0, 0.0, 0.0)

    def test_a_month_the_policy_did_not_answer_holds_the_floor_and_not_cash(self) -> None:
        """Where the rule declines to answer, the scoring path holds `min_weight` — a book
        that cannot answer still carries something — rather than 0 or 1.0. Reading silence as
        "all cash" would hand the comparison a free crash dodge on exactly the months where
        the archive is thinnest. The live paper book does sit in cash for those thirty
        sessions, which is thirty sessions of 8,458 at the very start of 1993; the floor is
        the harder of the two readings and the one the tool uses, on record here.

        The second half of this test is a fact about the rule rather than the scoring: from
        the 31st session to the 200th the volatility target is answered and the gate has
        nothing to say, so a sleeve's first ten months run at the cap. Worth pinning, because
        it happens where the windows are thinnest, and a future "fix" should be a decision
        rather than a quiet change of record."""

        desired = pw.CANDIDATE.raw_weights(
            self.closes, [0.0] + [self.closes[i] / self.closes[i - 1] - 1.0
                                  for i in range(1, len(self.closes))])
        first: dict[tuple[int, int], int] = {}
        for index, day in enumerate(self.days):
            first.setdefault((day.year, day.month), index)
        want = [pw.CANDIDATE.min_weight
                if desired[first[(key.year, key.month)]] is None
                else desired[first[(key.year, key.month)]] for key in self.keys]
        self.assertEqual(self.weights, want)
        self.assertTrue(all(weight > 0.0 for weight in self.weights))
        self.assertEqual(sum(1 for value in desired if value is None),
                         pw.CANDIDATE.vol_window,
                         "more sessions went unanswered than the vol window explains")

    def test_the_gate_is_disengaged_before_the_trend_window_fills(self) -> None:
        """No gate, full vol target, at the cap — on a sleeve's first ten months."""

        desired = pw.CANDIDATE.raw_weights(
            self.closes, [0.0] + [self.closes[i] / self.closes[i - 1] - 1.0
                                  for i in range(1, len(self.closes))])
        self.assertIsNotNone(desired[pw.CANDIDATE.vol_window + 1])
        self.assertGreater(desired[pw.CANDIDATE.vol_window + 1], pw.CANDIDATE.min_weight,
                           "the gate is clipping a window it has no data for")
        self.assertEqual(desired[pw.CANDIDATE.trend_window - 1], pw.CANDIDATE.max_weight)


if __name__ == "__main__":
    unittest.main()
