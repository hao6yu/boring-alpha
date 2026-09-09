"""Tests for `tools/accuracy_bar.py` — the bar a signal needs, given how that signal trades.

The convention in this repository is that a check must test the object that would actually be abused
(r5, r6), so the centre of gravity here is not "does the tool run" but four structural claims:

  * the shadow book and the rule book are the same arithmetic, or the bar is fiction;
  * the always-long row lands exactly on its own bar, because it *is* the comparator;
  * a rule's mirror image scores exactly its complement, or the scoring is reading something else;
  * the gap and the money never disagree in sign, because they are the same curve read twice.

Plus the guard against the failure that would matter most: a signal that could see next week. The
harness hands every rule a prefix of the closes and nothing else, and
`NoRuleSeesTomorrow` proves the prefix is a real prefix rather than a promise.
"""

from __future__ import annotations

from datetime import date
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import accuracy_bar as ab  # noqa: E402

COST = 2.0 / 10_000.0
REPS = 120                       # tests are not the paper; the solve is stable at a fraction of 400


_CACHE: dict = {}


def _grid(symbol: str, window: str, cost: float = 2.0, reps: int = REPS, r3: bool = False):
    """Every rule on one cell, priced once per (cell, cost, expense placement)."""

    key = (symbol, window, cost, reps, r3)
    if key not in _CACHE:
        _CACHE[key] = ab.audit(symbol, window, ab.WINDOWS[window], cost, reps, r3)
    return _CACHE[key]


def _rows(symbol: str, window: str, cost: float = 2.0, reps: int = REPS, r3: bool = False):
    return {row["rule"]: row for row in _grid(symbol, window, cost, reps, r3)}


class TheShadowBookIsTheRule(unittest.TestCase):
    """If the shadow book cannot reproduce the rule, the bar is measuring a book that never existed."""

    def test_the_affine_shadow_reproduces_the_bar_by_bar_rule(self):
        for symbol in ("SPY", "QQQ", "VTI"):
            for label in ("full 1993..2026", "recent 2022..2026", "seen B 2018..2021"):
                slice_ = ab.slice_of(symbol, ab.WINDOWS[label])
                if len(slice_.bars) < 120:
                    continue
                for name in ("always long", "always flat", "200-session trend",
                             "13-week momentum", "dual MA 50/200"):
                    kind, arg = ab.RULES[name]
                    flags = ab.answers(slice_, kind, arg, None)
                    live = [i for i, v in enumerate(flags) if v is not None]
                    if not live:
                        continue
                    start = live[0]
                    runs = [(a + start, b + start, s) for a, b, s in ab.runs_of(flags[start:])]
                    spans = [ab.span(slice_, a, b) for a, b, _s in runs]
                    ending, _switches = ab.price_rule(slice_, flags, COST, start)
                    # Draw vector: under the accuracy exactly where the rule's own state was the
                    # winning leg — i.e. instruct the shadow to follow the rule decision for decision.
                    draws = [0.0 if (spans[i][0] > spans[i][1]) == runs[i][2] else 2.0
                             for i in range(len(runs))]
                    self.assertAlmostEqual(
                        ending, ab.shadow_book(slice_, runs, COST, start, draws, 1.0, spans),
                        places=6, msg=f"{symbol} {label} {name}")

    def test_the_comparator_is_what_the_tool_claims_it_is(self):
        """Always long IS plain DCA in this frame, so the two books must agree to the cent."""

        slice_ = ab.slice_of("SPY", ab.WINDOWS["full 1993..2026"])
        flags = ab.answers(slice_, "const", True, None)
        self.assertAlmostEqual(ab.price_rule(slice_, flags, COST, 0)[0],
                               ab.price_dca(slice_, COST, 0), places=6)


class TheBarHasTheShapeItMust(unittest.TestCase):
    """A bar that cannot be forced to refuse is not a bar (r10: test that a guard can say no)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = _rows("SPY", "full 1993..2026")

    def test_the_comparator_row_sits_exactly_on_its_own_bar(self):
        row = self.rows["always long"]
        self.assertIsNotNone(row["bar"])
        self.assertAlmostEqual(row["bar"], 1.0, places=9)
        self.assertAlmostEqual(row["gap"], 0.0, places=9)
        self.assertAlmostEqual(ab.per_month(row), 0.0, places=6)

    def test_the_flat_row_needs_perfection_and_does_not_get_it(self):
        row = self.rows["always flat"]
        self.assertAlmostEqual(row["bar"], 1.0, places=9)     # only perfection reaches DCA from flat
        self.assertLess(row["gap"], -0.9)
        self.assertLess(ab.per_month(row), 0.0)

    def test_the_bar_falls_when_the_toll_falls(self):
        """A bar that does not move with cost is not charging for switching.

        Round 3's ~58% came from a timer that changed its mind about half of all weeks and paid two
        legs each time. The same coin on a cheaper desk must need less, and the gap between the two
        numbers is the part of the old headline that was friction rather than skill.
        """

        cheap = _rows("SPY", "full 1993..2026", cost=0.3, reps=80)["coin flip"]["bar"]
        dear = _rows("SPY", "full 1993..2026", cost=2.0, reps=80)["coin flip"]["bar"]
        self.assertLess(cheap, dear)

    def test_a_calendar_no_accuracy_can_win_is_reported_as_one(self):
        """Some rows must print `no bar`, and the row that does must be losing money anyway."""

        slice_rows = _rows("SPY", "recent 2022..2026")
        unreachable = {name: row for name, row in slice_rows.items() if row["bar"] is None}
        self.assertTrue(unreachable, "expected at least one unreachable bar in a four-year window")
        for name, row in unreachable.items():
            self.assertLess(ab.per_month(row), 0.0, f"{name} had no bar but was not losing")

    def test_more_switching_at_the_same_skill_costs_more_money(self):
        """Holding skill fixed at 50% and forcing turnover up must push the ending down."""

        slice_ = ab.slice_of("SPY", ab.WINDOWS["full 1993..2026"])
        endings = []
        for flip in (0.02, 0.10, 0.40):
            rng = random.Random(7)
            flags, held = [], True
            for _bar in range(len(slice_.bars)):
                if rng.random() < flip:
                    held = not held
                flags.append(held)
            runs = ab.runs_of(flags)
            spans = [ab.span(slice_, a, b) for a, b, _s in runs]
            # Accuracy zero: every run holds the leg that lost. One switch on, one switch off, so the
            # only thing the flip rate buys is the toll.
            endings.append((len(runs), ab.shadow_book(slice_, runs, COST, 0,
                                                      [1.5] * len(runs), 1.0, spans)))
        (runs_slow, value_slow), _, (runs_fast, value_fast) = endings
        self.assertGreater(runs_fast, runs_slow)
        self.assertLess(value_fast, value_slow)


class TheReversalControl(unittest.TestCase):
    """A rule's mirror image must score exactly its complement, or the score is not the rule's."""

    @classmethod
    def setUpClass(cls):
        cls.rows = _rows("SPY", "full 1993..2026")

    def test_the_reversed_rule_scores_the_complement_of_the_rule(self):
        trend, back = self.rows["126-session trend"], self.rows["reversed 126-trend"]
        self.assertEqual(trend["runs"], back["runs"])
        self.assertAlmostEqual(trend["hits"] + back["hits"], 1.0, places=9)

    def test_the_reversed_rule_loses_even_when_its_count_of_wins_is_high(self):
        """The row that motivated the inverted reading: 72.6% of decisions right, minus $929 a month."""

        trend, back = self.rows["126-session trend"], self.rows["reversed 126-trend"]
        self.assertGreater(back["hits"], trend["hits"])           # the count says the opposite
        self.assertGreater(trend["skill"], back["skill"])         # the money says this
        self.assertLess(back["gap"], 0.0)
        self.assertLess(ab.per_month(back), 0.0)

    def test_the_wedge_changes_sign_under_reversal(self):
        """Skill minus count must flip sign with the rule, since which runs won is what flipped."""

        trend, back = self.rows["126-session trend"], self.rows["reversed 126-trend"]
        self.assertGreater(trend["wedge"], 0.0)
        self.assertLess(back["wedge"], 0.0)


class TheIdentity(unittest.TestCase):
    """`gap` and `$/mo` are the same monotone curve read twice, so they cannot disagree."""

    def test_sign_of_gap_equals_sign_of_money_in_every_row(self):
        for symbol in ("SPY", "QQQ", "VTI"):
            for label in ab.WINDOWS:
                for row in _grid(symbol, label, reps=40):
                    if row["gap"] is None:
                        continue
                    self.assertEqual((row["gap"] > 0), (ab.per_month(row) > 0),
                                     f"{symbol} {label} {row['rule']}: gap "
                                     f"{row['gap']:+.3f} vs {ab.per_month(row):+,.0f}/mo")

    def test_the_skill_column_lies_between_zero_and_one(self):
        rows = _rows("SPY", "full 1993..2026")
        for name, row in rows.items():
            if row["skill"] is not None:
                self.assertGreaterEqual(row["skill"], 0.0, name)
                self.assertLessEqual(row["skill"], 1.0, name)


class NoRuleSeesTomorrow(unittest.TestCase):
    """The failure this file exists to avoid: a bar computed on a signal that peeked."""

    def test_a_rule_is_handed_only_the_closes_before_its_own_entry(self):
        """Truncate the archive; every decision before the cut must survive unchanged."""

        slice_ = ab.slice_of("SPY", ab.WINDOWS["full 1993..2026"])
        cut = len(slice_.bars) - 40
        keep = slice_.bars[cut - 1][3] + 1          # sessions, not bars: the two counts differ 5x
        truncated = ab.Slice(slice_.symbol, slice_.expense, slice_.dates[:keep],
                             slice_.closes[:keep], slice_.bars[:cut])
        for name, (kind, arg) in ab.RULES.items():
            if kind == "coin":
                continue
            full = ab.answers(slice_, kind, arg, None)[:cut]
            short = ab.answers(truncated, kind, arg, None)
            self.assertEqual(full, short, f"{name} changed when the future was removed")

    def test_the_harness_passes_a_prefix_and_not_the_array(self):
        """Record what `decide` receives. A length beyond the entry session is a look-ahead."""

        slice_ = ab.slice_of("SPY", ab.WINDOWS["recent 2022..2026"])
        seen = []
        original = ab.decide

        def spy(kind, arg, closes):
            seen.append(len(closes))
            return original(kind, arg, closes)

        ab.decide = spy
        try:
            ab.answers(slice_, "trend", 200, None)
        finally:
            ab.decide = original
        entries = [bar[3] + 1 for bar in slice_.bars]
        self.assertEqual(seen, entries, "a rule was handed more closes than its entry session owns")

    def test_a_rule_that_did_see_tomorrow_would_show_up_as_skill_near_one(self):
        """Negative control: build a leaking rule by hand and confirm the table would catch it.

        If an oracle were *not* flattered by this machinery, the machinery would be useless for
        auditioning anything. Flags are built from the next bar's outcome — impossible in production,
        mandatory here.
        """

        slice_ = ab.slice_of("SPY", ab.WINDOWS["full 1993..2026"])
        flags = [None]
        for bar in range(1, len(slice_.bars)):
            fund, cash, _deposit, _entry = slice_.bars[bar - 1]
            ahead = slice_.bars[bar]                        # the leak: this bar, before it happens
            flags.append(ahead[0] > ahead[1])
        row = ab.score_book(slice_, flags, COST, REPS)
        self.assertGreater(row["skill"], 0.999)
        self.assertGreater(row["hits"], 0.90)
        self.assertGreater(ab.per_month(row), 0.0)
        self.assertGreater(row["ending"], row["dca"])


class TheExpenseSitsOnTheFund(unittest.TestCase):
    """Round 3 charged the fund's expense ratio to the cash leg. The flat state must get cheaper."""

    def test_being_flat_is_cheaper_once_the_expense_ratio_is_where_it_belongs(self):
        """Round 3 taxed the cash leg, so it priced the flat state too pessimistically."""

        corrected = _rows("SPY", "full 1993..2026")["always flat"]
        r3 = _rows("SPY", "full 1993..2026", r3=True)["always flat"]
        self.assertGreater(ab.per_month(corrected), ab.per_month(r3))

    def test_the_coin_bar_moves_when_the_wrong_leg_was_charged(self):
        """Attribution: part of round 3's ~58% was the misplaced expense ratio, not the toll.

        The flat row cannot show this — its bar is pinned at perfection either way — so the
        attribution is read off the coin, and with a deliberate margin: bisection on a 3,000-draw
        mean has a few basis points of wobble in it, and a claim this load-bearing should not rest
        on the sign of a difference the estimator cannot resolve.
        """

        corrected = _rows("SPY", "full 1993..2026", reps=300)["coin flip"]["bar"]
        r3 = _rows("SPY", "full 1993..2026", reps=300, r3=True)["coin flip"]["bar"]
        self.assertLess(corrected + 0.0005, r3)

    def test_the_fund_leg_actually_pays_the_sleeves_ratio(self):
        """The ratio is charged to the leg that owns the fund, and never to the flat leg.

        Priced through `slice_of`, because the drag is baked into the bars at construction — a
        `Slice` rebuilt with a different `expense` field would keep the old bars and prove nothing.
        The same patch must leave the all-flat book untouched to the cent.
        """

        bounds, rate = ab.WINDOWS["recent 2022..2026"], ab.wc.EXPENSE["SPY"]
        try:
            ab.wc.EXPENSE["SPY"] = 0.0020
            rich = ab.slice_of("SPY", bounds)
            ab.wc.EXPENSE["SPY"] = 0.0
            free = ab.slice_of("SPY", bounds)
        finally:
            ab.wc.EXPENSE["SPY"] = rate
        self.assertLess(ab.price_dca(rich, COST, 0), ab.price_dca(free, COST, 0))
        flat_rich = ab.price_rule(rich, [False] * len(rich.bars), COST, 0)[0]
        flat_free = ab.price_rule(free, [False] * len(free.bars), COST, 0)[0]
        self.assertAlmostEqual(flat_rich, flat_free, places=9)


class TheGuards(unittest.TestCase):
    """A tool that prints a confident table for a sleeve it cannot see is worse than no tool."""

    def test_a_sleeve_not_in_the_archive_refuses_instead_of_printing_nothing(self):
        with self.assertRaises(ValueError):
            ab.slice_of("ZWIG", ab.WINDOWS["full 1993..2026"])

    def test_an_unknown_rule_kind_is_an_error_not_a_default(self):
        with self.assertRaises(ValueError):
            ab.decide("vibes", 3, [1.0] * 500)

    def test_the_gate_row_cannot_be_shifted_off_its_own_bars(self):
        """Round 12's lesson: a run list priced one index out is a wrong number that looks right.

        `runs_of` restarts its counting on whatever slice it is handed, so the absolute indices have
        to be restored before pricing. The symptom scales with the number of runs, and nothing in
        the output says which of the two you priced: on SPY/recent the single-run gate row moves by
        $67 and the twelve-run 200-session-trend row by $1,626 — both silently, both monthly.
        """

        slice_ = ab.slice_of("SPY", ab.WINDOWS["recent 2022..2026"])
        shifts = {}
        for name, minimum in (("candidate's gate", 20.0), ("200-session trend", 500.0)):
            kind, arg = ab.RULES[name]
            flags = ab.answers(slice_, kind, arg, None)
            start = next(i for i, v in enumerate(flags) if v is not None)
            self.assertGreater(start, 0, f"{name} is only interesting because it warms up")
            correct = [(a + start, b + start, s) for a, b, s in ab.runs_of(flags[start:])]
            lazy = ab.runs_of(flags[start:])
            draws = [1.5] * len(correct)
            right = ab.shadow_book(slice_, correct, COST, start, draws, 1.0,
                                   [ab.span(slice_, a, b) for a, b, _s in correct])
            wrong = ab.shadow_book(slice_, lazy, COST, start, draws, 1.0,
                                   [ab.span(slice_, a, b) for a, b, _s in lazy])
            shifts[name] = abs(right - wrong)
            self.assertGreater(shifts[name], minimum, f"{name} {shifts}")


class TheCoinIsTheAttributionControl(unittest.TestCase):
    """At a coin's turnover this file must reproduce the number round 3 printed, or it is not it."""

    def test_a_coin_at_the_headline_cost_needs_about_what_round_3_said(self):
        coin = _rows("SPY", "full 1993..2026")["coin flip"]
        self.assertAlmostEqual(coin["skill"], 0.5, delta=0.03)
        self.assertGreater(coin["bar"], 0.55)
        self.assertLess(coin["bar"], 0.65)

    def test_a_coin_wins_about_half_of_what_it_touched(self):
        """Sanity on the scoring itself: the coin cannot be systematically right or wrong."""

        coin = _rows("SPY", "full 1993..2026")["coin flip"]
        self.assertAlmostEqual(coin["hits"], 0.5, delta=0.04)
        self.assertGreater(coin["runs"], 400)


class TheGridIsNotQuiet(unittest.TestCase):
    """What the table actually concludes, pinned so a future edit cannot quietly change the story."""

    def test_no_real_rule_clears_its_own_bar_anywhere_on_the_menu(self):
        offenders = []
        for symbol in ("SPY", "QQQ", "VTI"):
            for label in ab.WINDOWS:
                for row in _grid(symbol, label, reps=40):
                    if row["rule"] in ab.CONTROLS:
                        continue
                    if row["gap"] is not None and row["gap"] > 0:
                        offenders.append(f"{symbol} {label} {row['rule']} {row['gap']:+.3f}")
        self.assertEqual(offenders, [], "a rule cleared its own bar: " + "; ".join(offenders))


if __name__ == "__main__":
    unittest.main()


class TheCadenceIsAFreedomNotAnEdge(unittest.TestCase):
    """Round 14: round 13 left one door open — more, smaller bets lower the bar. Tested, closed.

    `--cadence` moves the review frequency and nothing else: every lookback stays in sessions, so a
    200-session trend filter asked the same question on Tuesday at one session per decision as at five.
    What changes is how soon it finds out, how many runs that makes, and how often the toll is paid.
    """

    @classmethod
    def setUpClass(cls):
        cls.weekly = ab.slice_of("SPY", ab.WINDOWS["full 1993..2026"], False, 5)
        cls.daily = ab.slice_of("SPY", ab.WINDOWS["full 1993..2026"], False, 1)

    def test_a_faster_clock_adds_bars_and_not_signals(self):
        """Five times the bars, the same deposits, and the same answer on the same session."""

        self.assertAlmostEqual(len(self.daily.bars) / len(self.weekly.bars), 5.0, delta=0.15)
        self.assertEqual(sum(b[2] for b in self.daily.bars), sum(b[2] for b in self.weekly.bars))
        entry_weekly = {self.weekly.bars[i][3]: i for i in range(len(self.weekly.bars))}
        fast = ab.answers(self.daily, "trend", 200, None)
        slow = ab.answers(self.weekly, "trend", 200, None)
        checked = 0
        for bar, (_fund, _cash, _deposit, entry) in enumerate(self.weekly.bars):
            if entry in entry_weekly and entry < len(fast) and fast[entry] is not None:
                self.assertEqual(fast[entry], slow[bar], f"the signal moved on {self.weekly.dates[entry]}")
                checked += 1
        self.assertGreater(checked, 1000)

    def test_the_expense_ratio_is_charged_per_session_held_not_per_bar(self):
        """A bar five times as long must cost five times as much drag, to the exponent."""

        self.assertAlmostEqual(self.daily.drag ** 5, self.weekly.drag, places=12)

    def test_a_faster_review_really_does_lower_the_bar(self):
        """The one prediction round 13 made in favour of short-term trading, checked rather than assumed."""

        quick = self.score("200-session trend", self.daily)
        slow = self.score("200-session trend", self.weekly)
        self.assertGreater(quick["runs"], slow["runs"], "a faster clock must see more runs")
        self.assertLess(quick["bar"], slow["bar"])
        # And the count swings nine points in the wrong direction while the money moves by 4%, because
        # the extra runs are whipsaws. The count is not a statistic of the book; it is a statistic of
        # the calendar the book is read on, which is the same lesson the reversal control taught.
        self.assertGreater(abs(quick["hits"] - slow["hits"]), 0.05)
        self.assertLess(abs(ab.per_month(quick) - ab.per_month(slow)), abs(ab.per_month(slow)) * 0.05)

    def test_the_skill_falls_with_the_bar_so_the_gap_does_not_close(self):
        """The bar falls ~2 points and the skill falls further, so the door opens onto the same wall."""

        quick, slow = self.score("126-session trend", self.daily), self.score("126-session trend", self.weekly)
        self.assertLess(quick["bar"], slow["bar"])
        self.assertLess(quick["skill"], slow["skill"])
        self.assertLess(quick["gap"], slow["gap"])
        self.assertLess(ab.per_month(quick), ab.per_month(slow), "and the book is worse for it")

    @staticmethod
    def score(name, slice_):
        kind, arg = ab.RULES[name]
        return ab.score_book(slice_, ab.answers(slice_, kind, arg, None), COST, 120)

    def test_the_fast_door_has_no_winning_row_either(self):
        """Pinned so nobody rediscovers 'short-term trading' as an answer a third time."""

        offenders = []
        for label in ("recent 2022..2026", "seen A 2007-06..2017-12"):
            for row in ab.audit("SPY", label, ab.WINDOWS[label], 2.0, 120, False, 1):
                if row["rule"] in ab.CONTROLS:
                    continue
                if (row["gap"] and row["gap"] > 0) or ab.per_month(row) > 0:
                    offenders.append(f"{label} {row['rule']}")
        self.assertEqual(offenders, [], "a daily rule cleared: " + "; ".join(offenders))
