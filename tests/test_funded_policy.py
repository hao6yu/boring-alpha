"""Tests for the deposit-frame scoring: `funded_policy` and the helpers in `funded_frame`.

The rule this round adds is that a check must test the object that would be abused, and
everything dangerous here is in the wiring rather than the arithmetic. Three things in a funded
comparison look equivalent and are not, in order of what they cost:

  the encoding of a banded policy — `raw_weights` is the weight the rule *wants*; `weights` is
      the weight it *holds* after the review interval and the band. Feeding the first to an
      engine that trades every session produces 415 fills for a rule that made 232, and an
      11% different terminal number. Neither row looks wrong on the page.
  where the account opens        — the engine starts at `max(start, first answered target)`, so
      a comparator given `start=0` against a policy that cannot answer for 200 sessions hands
      the unlevered book two hundred sessions of compounding and then reports the difference
      as the policy's performance.
  the reversal of a weight path  — reversing an array with leading Nones moves them to the end,
      and the engine `continue`s on a None target, skipping that month's deposit and that day's
      carry. The control loses two hundred sessions and the loss gets attributed to the
      scrambling.

The arithmetic tests are here because the money units are a conversion and a conversion can be
backwards, and the sign of a gap is the difference between income and a bill.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import funded_policy as fp
import withdrawal_capacity as wc
from boring_alpha.data.csv_loader import load_csv_market_data
from funded_frame import per_month_equivalent, worst_12m_difference
from paper import CANDIDATE
from run_voltarget_scan import funded


class AnnuityConversion(unittest.TestCase):
    def test_a_gap_discounted_at_the_comparator_rate_is_a_plain_annuity(self) -> None:
        """$12,000 of terminal gap over 120 months at 6% a year. The factor is
        r / ((1+r)^n − 1) at r = 1.06^(1/12) − 1, computed here independently of the helper."""

        months, rate = 120, 0.06
        r_month = (1.0 + rate) ** (1.0 / 12.0) - 1.0
        expected = 12_000.0 * r_month / ((1.0 + r_month) ** months - 1.0)
        self.assertAlmostEqual(per_month_equivalent(12_000.0, rate, months), expected,
                               places=9)
        self.assertGreater(expected, 70.0, "the hand check itself has gone wrong")
        self.assertLess(expected, 90.0)

    def test_a_zero_rate_falls_back_to_division_rather_than_dividing_by_zero(self) -> None:
        """At a zero comparator rate the annuity factor is 0/0. The limit is the plain
        division, and a month count of zero must clamp rather than crash."""

        self.assertAlmostEqual(per_month_equivalent(12_000.0, 0.0, 120), 100.0, places=9)
        with self.assertRaises(ValueError):
            per_month_equivalent(12_000.0, 0.0, 0)

    def test_the_conversion_never_turns_a_loss_into_income(self) -> None:
        """The sign is the whole difference between the tool reporting a wage and reporting a
        bill, and an even function or a squared term would silently do the swap."""

        self.assertLess(per_month_equivalent(-50_000.0, 0.08, 300), 0.0)
        self.assertGreater(per_month_equivalent(50_000.0, 0.08, 300), 0.0)
        self.assertAlmostEqual(per_month_equivalent(0.0, 0.08, 300), 0.0, places=9)


class WorstTwelveMonthHole(unittest.TestCase):
    @staticmethod
    def _path(start: date, values: list[float]) -> list[tuple[date, float]]:
        """One entry per month, one month apart, starting the month *after* `start`."""

        out, stamp = [], start
        for value in values:
            year, month = stamp.year + (stamp.month == 12), (stamp.month % 12) + 1
            stamp = date(year, month, 1)
            out.append((stamp, value))
        return out

    def test_identical_books_have_no_hole_by_construction(self) -> None:
        values = [1000.0 * (1.01 ** i) for i in range(40)]
        path = self._path(date(2005, 12, 1), values)
        self.assertEqual(worst_12m_difference(path, path), 0.0)

    def test_a_linear_drip_of_underperformance_reports_a_year_of_it(self) -> None:
        """The candidate falls $45 further behind every month from month 24 on. Nothing here
        is a coincidence to tune to: the answer is checked against an oracle that walks the
        same grid twice, written the slow obvious way, which is the only kind of check that
        would notice an off-by-one in the twelve-month window."""

        months, drip = 72, 45.0
        base = [10_000.0 + 500.0 * i for i in range(1, months + 1)]
        cand = [value - (0.0 if index < 24 else drip * (index - 23))
                for index, value in enumerate(base)]
        stamps = [stamp for stamp, _v in self._path(date(2005, 12, 1), base)]
        gap = [c - b for c, b in zip(cand, base)]
        oracle = min(0.0, min(gap[j] - gap[j - 12] for j in range(12, len(gap))))
        self.assertAlmostEqual(oracle, -drip * 12, places=6)
        self.assertAlmostEqual(worst_12m_difference(list(zip(stamps, cand)),
                                                  list(zip(stamps, base))),
                               oracle, places=6)

    def test_twelve_steps_across_a_hole_are_not_reported_as_a_year(self) -> None:
        """A thin sleeve missing two months has thirteen monthly points where twelve steps
        span fourteen months. That is a year and two months of underperformance reported as a
        year, inflated by exactly the hole, and the helper must skip the window.

        The grid without the hole is priced on the same script and *does* contain a real
        year of the same shortfall, so the pair of assertions says the only thing worth
        saying: the complete grid sees the whole hole, the holed grid does not see it at all,
        and neither invents a number the other would disown."""

        def drag(stamp: date) -> float:
            if stamp < date(2011, 1, 1):
                return 0.0
            return 300.0 if stamp < date(2011, 4, 1) else 600.0

        months = [date(2010 + (m // 12), m % 12 + 1, 1) for m in range(0, 16)]
        full = [(stamp, 1000.0 + 10.0 * index) for index, stamp in enumerate(months)]
        holed = [point for point in full
                 if point[0] not in (date(2011, 2, 1), date(2011, 3, 1))]
        cand_full = [(stamp, value - drag(stamp)) for stamp, value in full]
        cand_holed = [(stamp, value - drag(stamp)) for stamp, value in holed]
        self.assertEqual(len(holed), 14)
        self.assertAlmostEqual(worst_12m_difference(cand_full, full), -600.0, places=6)
        self.assertAlmostEqual(worst_12m_difference(cand_holed, holed), -300.0, places=6,
                               msg="a fourteen-month window was reported as a year")

    def test_a_short_history_reports_no_hole_rather_than_a_small_one(self) -> None:
        base = self._path(date(2020, 12, 1), [1000.0] * 8)
        cand = [(d, v - 100.0) for d, v in base]
        self.assertEqual(worst_12m_difference(cand, base), 0.0)


class Archive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.dates = [d for d in sorted(cls.data.by_date) if "SPY" in cls.data.by_date[d]]
        cls.closes = [cls.data.by_date[d]["SPY"].close for d in cls.dates]
        cls.returns = [cls.closes[i] / cls.closes[i - 1] - 1.0
                       for i in range(1, len(cls.closes))]
        cls.returns.insert(0, 0.0)
        cls.factors = [cls.data.cash_factors[d] for d in cls.dates]
        cls.desired = CANDIDATE.raw_weights(cls.closes, cls.returns)
        cls.live = fp.first_live(cls.desired)
        cls.applied = [w for w, _t in CANDIDATE.weights(cls.closes, cls.returns)]

    def _own_trades(self) -> int:
        return sum(1 for w, t in CANDIDATE.weights(self.closes, self.returns)
                   if w is not None and t > 0.0)


class TheEncodingIsThePolicy(Archive):
    def test_the_as_traded_encoding_booked_the_rules_own_number_of_trades(self) -> None:
        """The rule says how often it traded. An engine encoding that contradicts that is a
        different rule, however faithful its weights look."""

        own = self._own_trades()
        rows = fp.score("SPY", "full")
        as_traded = dict(rows)["candidate (as traded)"]
        self.assertGreater(own, 100, "the archive stopped producing a tradeable policy")
        self.assertLess(abs(as_traded.turns - own) / own, 0.20,
                        f"the rule traded {own} times, the engine booked {as_traded.turns}")

    def test_the_loose_encoding_is_the_trap_this_test_exists_for(self) -> None:
        """Passing the weight the policy *wants* to an engine that trades daily, with only a
        band to stop it, inflates the fill count from 232 to 418 and moves the terminal value
        by 12%. Both numbers printed confidently before this was noticed, which is the entire
        argument for testing the encoding instead of the arithmetic.

        Round 10 gave `allow` teeth, and these two rows still call `funded` without it on
        purpose: this is the shape of the naive call site, and the number it produces is the
        damage. The gated behaviour is pinned separately, in `TheCadenceGateIsEnforced`; if
        that class ever goes green while this one is deleted, the lesson went with it."""

        own = self._own_trades()
        loose = funded(self.closes, self.returns, self.factors, self.dates,
                       targets=self.desired, band=CANDIDATE.rebalance_band, start=self.live)
        as_traded = funded(self.closes, self.returns, self.factors, self.dates,
                           targets=self.applied, band=CANDIDATE.rebalance_band,
                           start=self.live)
        self.assertGreater(loose.turns, own * 1.4)
        self.assertGreater(as_traded.turns, own * 0.8)
        self.assertLess(as_traded.turns, own * 1.2)
        self.assertGreater(abs(loose.ending - as_traded.ending) / as_traded.ending, 0.05,
                           "the two encodings collapsed onto each other; either the engine "
                           "was fixed or this test stopped measuring anything")

    def test_the_naive_zero_band_encoding_trades_every_single_session(self) -> None:
        """Applied weight with no band is the *loosest* encoding, not the strictest — band 0
        means chase the drift daily. 8,428 fills for a 232-fill rule, and it is the encoding a
        caller reaches for when they want to be careful."""

        naive = funded(self.closes, self.returns, self.factors, self.dates,
                       targets=self.applied, band=0.0, start=self.live)
        self.assertGreater(naive.turns, self._own_trades() * 10)
        self.assertGreater(naive.cost_paid, 1.0)

    def test_the_scored_row_is_the_encoding_that_matches_the_rule(self) -> None:
        """Whichever encoding `score()` headlines, it must be the cadence-faithful one, and it
        must not be the loose one by accident of a later refactor."""

        rows = dict(fp.score("SPY", "full"))
        self.assertLess(rows["candidate (as traded)"].turns,
                        rows["candidate (loose enc.)"].turns)


class TheCadenceGateIsEnforced(Archive):
    """Round 10: `allow` used to be decorative — the trade test read `… or started or …` and
    `started` was sticky from the first fill, so from session two onward the engine traded
    whenever the band said so, and a five-session rule filled 241 times for 222 reviews.
    These tests price the gate instead of describing it.
    """

    def _run(self, targets: list[float | None], band: float, allow: set[int] | None):
        return funded(self.closes, self.returns, self.factors, self.dates, targets=targets,
                      band=band, allow=allow, start=self.live)

    def test_reviewed_sessions_marks_the_sessions_the_weight_changes_on(self) -> None:
        """Hand vector, hand answer. The object being tested is the set that decides what may
        trade, so it is not allowed to be verified by the trades it produces."""

        path: list[float | None] = [None, None, 0.5, 0.5, 0.7, 0.7, 0.7, 0.4]
        self.assertEqual(fp.reviewed_sessions(path), {2, 4, 7},
                         "the reviewed set stopped being the set of sessions the weight moves")
        self.assertNotIn(0, fp.reviewed_sessions([None] * 3 + [1.0] * 4),
                         "an unanswered session was counted as a review")

    def test_the_gate_refuses_drift_that_the_band_would_have_traded(self) -> None:
        """The razor. One allowed session out of eight thousand, on a book carrying its full
        weight: a book allowed to act once must have traded exactly once. Un-gated, the same
        prices and the same 10% band produce 21 fills on this archive — twenty drift trades the
        cadence refuses, which is why the control below insists on them rather than a bigger
        number that would say more about SPY's decade of compounding than about the gate."""

        once = self._run([1.0] * len(self.dates), 0.10, {self.live})
        self.assertEqual(once.turns, 1, f"a one-session cadence booked {once.turns} fills")
        free = self._run([1.0] * len(self.dates), 0.10, None)
        self.assertGreater(free.turns, once.turns * 5,
                           "the control that should churn did not; this test is measuring "
                           "nothing and the razor above is not sharp")

    def test_the_gate_removes_fills_that_the_un_gated_row_booked(self) -> None:
        """Negative control on the wiring, not on the rule: the same vector, band and start,
        with and without the reviewed set. If passing it changes nothing, the argument is
        decoration and the row's fill count is a property of the engine again."""

        gated = self._run(self.applied, CANDIDATE.rebalance_band,
                          fp.reviewed_sessions(self.applied))
        ungated = self._run(self.applied, CANDIDATE.rebalance_band, None)
        self.assertLess(gated.turns, ungated.turns,
                        f"{gated.turns} gated vs {ungated.turns} ungated — the gate did nothing")
        self.assertLessEqual(gated.turns, len(fp.reviewed_sessions(self.applied)),
                             "more fills than sessions the policy was allowed to act on")

    def test_the_gate_does_not_rescue_the_loose_encoding(self) -> None:
        """Gating both encodings is the fair comparison, and it does not make them agree: raw
        weights move nearly every session, so the reviewed set for the loose row is nearly
        every session. The encoding, not the cadence, is what was costing 12%."""

        raw_reviews = len(fp.reviewed_sessions(self.desired))
        held_reviews = len(fp.reviewed_sessions(self.applied))
        self.assertGreater(raw_reviews, held_reviews * 4,
                           "the raw encoding stopped changing its mind far more often than "
                           "the traded one; this test's premise needs re-deriving")
        loose = self._run(self.desired, CANDIDATE.rebalance_band,
                          fp.reviewed_sessions(self.desired))
        held = self._run(self.applied, CANDIDATE.rebalance_band,
                         fp.reviewed_sessions(self.applied))
        self.assertGreater(loose.turns, held.turns * 1.4)
        self.assertGreater(abs(loose.ending - held.ending) / held.ending, 0.05)

    def test_the_opening_fill_is_not_a_rebalance_and_happens_anyway(self) -> None:
        """The gate has to let the first trade through or every gated row is an empty account
        reporting zero as a result. Deliberately allow a session that is *not* the opening one:
        the account must still be open, and still have bought."""

        rows = self._run([1.0] * len(self.dates), 0.10, {self.live + 5})
        self.assertGreater(rows.ending, 0.0, "the gated account never opened")
        self.assertGreaterEqual(rows.turns, 1)

    def test_a_zero_band_is_deadly_only_when_nobody_says_where_the_reviews_are(self) -> None:
        """Retitled from round 9's warning about `band=0`. Band zero does not create daily
        churn on its own; it exposes the absence of a cadence. Hand the same vector its own
        reviewed sessions and the same rule books a fraction of the fills."""

        free = self._run(self.applied, 0.0, None)
        gated = self._run(self.applied, 0.0, fp.reviewed_sessions(self.applied))
        self.assertGreater(free.turns, self._own_trades() * 10)
        self.assertLess(gated.turns, free.turns / 10,
                        "a cadence-gated band-zero row still churns; the gate is not gating")


class TheAccountOpensOnce(Archive):
    def test_the_convention_is_the_one_the_pre_registered_scan_uses(self) -> None:
        """Pinned, because the alternative looks like a conservatism and is not one: pushing
        the opening back to the first session with a *full* trend window forfeits the deposits
        that would have arrived before it — $7,000 of principal, $194,000 of terminal value on
        SPY — and moves which history is scored. The gate being unwarmed for two hundred
        sessions is a property of the pre-registered rule, not a defect of the measurement."""

        self.assertEqual(self.live, CANDIDATE.vol_window,
                         "the policy stopped answering at its volatility window")
        self.assertLess(self.live, CANDIDATE.trend_window,
                        "the account now opens after the gate is warm, which is a different "
                        "account from the one the scan and the shadow book price")

    def test_every_row_opens_on_the_session_the_comparator_opens_on(self) -> None:
        """Not stylistic. The engine's start is `max(start, first answered target)`, so
        without a warm-up past the trend window the unlevered comparator compounds for two
        hundred sessions the policy never sees."""

        rows = dict(fp.score("SPY", "full"))
        first = rows[fp.COMPARATOR].path[0][0]
        for label in ("candidate (as traded)", "candidate (loose enc.)", "no trend gate",
                      "candidate, reversed"):
            self.assertEqual(rows[label].path[0][0], first,
                             f"{label} opened on a different session from the comparator")

    def test_the_guard_is_live_and_the_default_is_not_what_it_protects_against(self) -> None:
        """Prove the failure mode is real, so the default above is load-bearing rather than
        decorative: at warm-up 0 the comparator and the policy do not open together."""

        rows = dict(fp.score("SPY", "full", 0))
        self.assertNotEqual(rows[fp.COMPARATOR].path[0][0],
                            rows["candidate (as traded)"].path[0][0])

    def test_a_sleeve_too_short_for_the_warm_up_is_refused_not_scored_short(self) -> None:
        """VOO has sixteen years and a 200-session warm-up eats a year of it. A window that
        leaves too little must raise, not quietly price a shorter account against a longer
        comparator."""

        with self.assertRaises(ValueError):
            fp.score("VOO", "full", warmup=len(fp.series("VOO", fp.WINDOWS["full"])[0]) - 10)


class TheReversalIsAPermutation(Archive):
    def test_no_none_survives_the_reversal(self) -> None:
        path = fp.reversed_path(self.desired)
        self.assertEqual(len(path), len(self.desired))
        self.assertNotIn(None, path)

    def test_the_reversal_permutes_the_decisions_and_nothing_else(self) -> None:
        answered = [w for w in self.desired if w is not None]
        path = fp.reversed_path(self.desired)
        self.assertEqual(sorted(path[:len(answered)]), sorted(answered))
        self.assertEqual(path[len(answered):], [answered[0]] * (len(path) - len(answered)),
                         "the tail must continue the reversed series across the join, not "
                         "invent a decision the policy never made")

    def test_the_reversal_stays_inside_the_policy_own_bounds(self) -> None:
        path = fp.reversed_path(self.desired)
        for weight in path:
            self.assertGreaterEqual(weight, CANDIDATE.min_weight - 1e-12)
            self.assertLessEqual(weight, CANDIDATE.max_weight + 1e-12)

    def test_an_unchallenged_path_raises_rather_than_reversing_nothing(self) -> None:
        with self.assertRaises(ValueError):
            fp.reversed_path([None] * 50)


class WhatTheDepositFrameSays(unittest.TestCase):
    """A measured result pinned as a wiring guard, not as a forecast. The sign of these gaps
    moves with the market; the relationships between rows should not, and if they do it is
    the harness that changed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spy = dict(fp.score("SPY", "full"))

    def test_the_candidate_cut_the_drawdown_it_claims_to_cut(self) -> None:
        """A trend gate is a claim about crashes. If it does not survive contact with the
        engine's own drawdown column, nothing else in this table is worth reading."""

        self.assertGreater(self.spy["candidate (as traded)"].max_drawdown,
                           self.spy[fp.COMPARATOR].max_drawdown * 0.65)

    def test_the_comparator_pays_the_comparator_own_costs(self) -> None:
        """DCA into a fund is not free, and it is not expensive either: one entry per deposit
        and the sleeve's expense ratio. If this row ever shows a large cost figure, something
        is rebalancing an account that was specified never to."""

        comparator = self.spy[fp.COMPARATOR]
        self.assertLess(comparator.cost_paid, 200.0)
        # Not exactly zero, and the reason is worth knowing: an unlevered buy pays its entry
        # fee out of the cash that funded it, which puts the cash line a fee's worth in debit
        # for one session, and the engine charges that debit the borrow spread. Over 33 years
        # it comes to fractions of a cent — but a "DCA pays no financing" assertion would have
        # failed on it, so the number is pinned at its real magnitude instead.
        self.assertLess(comparator.carry_paid, 0.05,
                        "the unlevered comparator incurred real borrow cost")
        self.assertEqual(comparator.margin_calls, 0)

    def test_no_row_in_the_table_went_bust(self) -> None:
        for label, res in self.spy.items():
            self.assertFalse(res.ruined, f"{label} went to zero")
            self.assertGreater(res.ending, 0.0)


if __name__ == "__main__":
    unittest.main()
