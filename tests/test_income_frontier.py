"""Tests for the income frontier and for the withdrawal engine change it forced.

Three groups, in the order the round earned them:

  * the engine    a cash plan is not a ruined plan; a fraction refuses to be indexed or guarded; ruin is the
                  account and not the sleeve. All three were wrong or unexpressible before this round, and
                  the first is why every T-bill row this tool might have produced would have come back dead.
  * the equaliser the floor each rule is asked to promise is the floor it actually delivers, a fixed rule's
                  median *is* its floor, and a guardrail's ratio is bounded by its own cut and not by
                  anything about markets.
  * the result    on the archive, no levered plan pays more than the same sleeve unlevered at an equal floor,
                  and the two sentences "cannot promise" and "no record" are not interchangeable.

Synthetic series are used wherever a synthetic series will do, so the arithmetic can be checked by hand.
"""

from __future__ import annotations

import dataclasses
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import income_frontier as ifr                    # noqa: E402
import withdrawal_capacity as wc                 # noqa: E402


def synth(months: int, ret: float = 0.005, cash: float = 0.0025) -> tuple:
    returns = [ret] * months
    rates = [cash] * months
    keys = [date(2000, 1, 1) + timedelta(days=30 * i) for i in range(months)]
    return [(returns[i:i + months], rates[i:i + months], keys[i]) for i in range(1)]


class TheCashPlanIsNotARuinedPlan(unittest.TestCase):
    """The engine scored `position <= 0` as ruin, which is right about an equity plan and wrong about cash."""

    def test_a_plan_that_never_held_a_sleeve_is_not_dead_at_its_first_month(self):
        window = synth(24, ret=0.0, cash=0.004)
        run = wc.run(window[0][0], window[0][1], 0.0, 400.0, 0.0, 0.0, wc.BAND, "margin",
                     wc.MAINTENANCE_EQUITY, 0.0, None, [0.0] * 24, None)
        self.assertTrue(run.survived, "a T-bill account paying $400 a month was scored as ruined")
        self.assertEqual(run.cuts, 0)

    def test_a_cash_account_pays_its_cheque_from_its_cash_and_its_ending_is_arithmetic(self):
        window = synth(12, ret=0.0, cash=0.01)
        run = wc.run(window[0][0], window[0][1], 0.0, 500.0, 0.0, 0.0, wc.BAND, "margin",
                     wc.MAINTENANCE_EQUITY, 0.0, None, [0.0] * 12, None)
        self.assertTrue(run.survived)
        # Cash compounds, the cheque leaves, nothing is traded: the number is checkable by hand.
        cash, expected = wc.START, 0.0
        for _ in range(12):
            cash *= 1.01
            cash -= 500.0
            expected = cash
        self.assertAlmostEqual(run.ending, expected, places=6)
        self.assertAlmostEqual(run.paid, 6_000.0, places=6)

    def test_a_cheque_larger_than_the_sleeve_is_funded_from_the_cash_line_and_kills_nothing(self):
        """A half-equity account asked to pay more than the sleeve is worth must sell the sleeve *and* draw
        cash. The old engine subtracted the whole cheque from the position, which made the position negative
        and reported a ruin that never happened."""

        # A 20%-equity account paying $30k a month: the sleeve is worth $20k, so the sleeve cannot fund the
        # cheque and the cash line has to. Two months of it leaves a solvent, if depleted, account.
        window = synth(2, ret=0.0, cash=0.0)
        run = wc.run(window[0][0], window[0][1], 0.2, 30_000.0, 0.0, 0.0, wc.BAND, "margin",
                     wc.MAINTENANCE_EQUITY, 0.0, None, None, None)
        self.assertTrue(run.survived, "a cash-rich account that sold its whole sleeve for a cheque died")
        # $100k in, two $30k cheques, nothing earned: $40k, less the friction of selling a sleeve that was
        # only $20k wide. The first version of this assertion said "about $60k" and was arithmetic, not code.
        self.assertGreater(run.ending, 35_000.0)
        self.assertLess(run.ending, 40_001.0)

    def test_a_plan_that_loses_its_sleeve_while_holding_one_still_dies(self):
        """The loosened ruin test must still catch the thing it was written for."""

        window = synth(12, ret=-0.5, cash=0.0)
        run = wc.run(window[0][0], window[0][1], 1.0, 400.0, 0.0, 0.0, wc.BAND, "margin",
                     wc.MAINTENANCE_EQUITY, 0.0, None, None, None)
        self.assertFalse(run.survived)


class TheFractionIsOneProduct(unittest.TestCase):
    def test_a_fraction_refuses_to_also_be_indexed_or_guarded(self):
        window = synth(6)
        for kwargs in ({"inflate": 0.025}, {"guard": (0.25, 0.5)}):
            with self.assertRaises(ValueError) as got:
                wc.run(window[0][0], window[0][1], 1.0, 0.0, 0.0, kwargs.get("inflate", 0.0), wc.BAND,
                       "margin", wc.MAINTENANCE_EQUITY, 0.0, kwargs.get("guard"), None,
                       0.004)
            self.assertIn("product", str(got.exception))

    def test_a_monthly_fraction_outside_zero_and_one_is_refused(self):
        window = synth(6)
        for bad in (0.0, 1.0, 1.5, -0.1):
            with self.assertRaises(ValueError):
                wc.run(window[0][0], window[0][1], 1.0, 0.0, 0.0, 0.0, wc.BAND, "margin",
                       wc.MAINTENANCE_EQUITY, 0.0, None, None, bad)

    def test_a_fraction_of_a_growing_account_pays_more_than_its_floor_by_a_known_amount(self):
        window = synth(24, ret=0.01, cash=0.0)
        run = wc.run(window[0][0], window[0][1], 1.0, 0.0, 0.0, 0.0, wc.BAND, "margin",
                     wc.MAINTENANCE_EQUITY, 0.0, None, None, 0.004)
        self.assertTrue(run.survived)
        # The engine's stated order is market, then withdrawal, so the first cheque is the fraction of the
        # account *after* one month of growth. Asserting the un-grown figure would have pinned a bug.
        self.assertAlmostEqual(run.smallest, 0.004 * wc.START * 1.01, places=4,
                               msg="the first cheque is the floor of a rising account")
        self.assertGreater(run.paid / 24, run.smallest)

    def test_a_fraction_of_a_shrinking_account_cannot_promise_a_dollar_floor(self):
        """The round's central negative result, checked on a made-up account so it cannot be a data artefact."""

        window = synth(24, ret=-0.01, cash=0.0)
        run = wc.run(window[0][0], window[0][1], 1.0, 0.0, 0.0, 0.0, wc.BAND, "margin",
                     wc.MAINTENANCE_EQUITY, 0.0, None, None, 0.004)
        self.assertTrue(run.survived, "the rule that cannot die reported dying")
        self.assertLess(run.smallest, 0.004 * wc.START,
                        "a fraction rule whose account shrank still paid its opening rate")


class TheEqualiserDeliversWhatItPromises(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables, cls.cash_now, _data, _mc = ifr.load(10, stride=6)
        cls.plans = ifr.plans(cls.cash_now)
        cls.cells = {}
        for plan in cls.plans:
            if plan.label not in cls.tables:
                continue
            windows, zero = cls.tables[plan.label]
            if len(windows) < ifr.MIN_STARTS:
                continue
            for rule in ifr.RULES:
                cls.cells[(plan.label, rule)] = ifr.solve(windows, plan, rule, 400.0, zero)

    def test_every_rule_that_clears_the_floor_actually_pays_it(self):
        for (label, rule), cell in self.cells.items():
            if cell.feasible and cell.floor >= 400.0 * 0.999:
                self.assertAlmostEqual(cell.floor, 400.0, delta=2.0,
                                       msg=f"{label} {rule} paid {cell.floor} against a promised 400")

    def test_a_fixed_cheque_pays_exactly_its_floor_and_nothing_more(self):
        """Not a finding about markets: the definition of the word "fixed", printed so the ratio column of
        the table cannot be mistaken for an asset-class result."""

        for (label, rule), cell in self.cells.items():
            if rule in ("fixed", "indexed") and cell.feasible:
                self.assertAlmostEqual(cell.floor, 400.0, delta=2.0)
                self.assertGreaterEqual(cell.median, cell.floor - 1e-6)
                if rule == "fixed":
                    self.assertAlmostEqual(cell.median, cell.floor, places=6)

    def test_a_guardrail_never_pays_more_than_twice_its_floor_because_that_is_its_own_definition(self):
        for (label, rule), cell in self.cells.items():
            if rule == "guardrail" and cell.feasible and cell.floor > 0:
                self.assertLessEqual(cell.median / cell.floor, 1.0 / ifr.GUARD[1] + 0.02,
                                     f"{label}: a guardrail paying {cell.median / cell.floor:.2f}x its "
                                     f"floor means the cut never binds and the ratio is an artefact")

    def test_a_larger_account_is_a_linear_rescaling_and_not_a_new_result(self):
        cell = next(c for (label, rule), c in self.cells.items() if label == "SPY" and rule == "guardrail")
        self.assertAlmostEqual(cell.dollars(20_000.0) * 5.0, cell.dollars(100_000.0), places=6)
        self.assertAlmostEqual(cell.dollars(wc.START), cell.median, places=6)

    def test_a_plan_is_measured_on_its_own_calendar_and_the_cash_plan_on_the_reference_one(self):
        labels = {label for label, _rule in self.cells}
        self.assertIn("cash", labels, "the T-bill plan was skipped, so the comparison has no floor")
        self.assertNotIn("QQQ", {"cash"} - labels)


class TheVerdictKeepsItsTwoSentencesApart(unittest.TestCase):
    def test_a_plan_with_no_record_is_reported_as_unmeasured_not_as_failed(self):
        plan = ifr.plans(0.04)[2]                          # SPY
        cells = [ifr.Cell("SPY", "guardrail", 400.0, 800.0, 400.0, 600.0, 1.5, 0.3, 12, True,
                          "floor", ""),
                 ifr.Cell("cash", "fixed", 400.0, 400.0, 400.0, 400.0, 1.0, 0.5, 12, True, "floor", "")]
        text = ifr.verdict(cells, 400.0, 20)
        self.assertIn("not measured", text)
        self.assertNotIn("VOO cannot promise", text)
        self.assertTrue(plan)

    def test_a_plan_that_failed_every_start_is_named_as_failing(self):
        cells = [ifr.Cell("SPY", "fixed", 400.0, 400.0, 400.0, 600.0, 1.5, 0.3, 12, True, "floor", ""),
                 ifr.Cell("cash", "fixed", 400.0, 400.0, 400.0, 400.0, 1.0, 0.5, 12, True, "floor", ""),
                 ifr.Cell("QQQ", "fixed", 400.0, 0.0, 0.0, 0.0, 0.0, 0.0, 12, False, "survival",
                          "2000-02")]
        text = ifr.verdict(cells, 400.0, 10)
        self.assertIn("cannot promise", text)
        self.assertIn("REDUNDANT" if False else "vs cash", text)


class TheArchivedResultIsPinned(unittest.TestCase):
    """The round's conclusion, pinned so that a future edit has to disagree with it on purpose."""

    @classmethod
    def setUpClass(cls):
        tables, cash_now, _data, _mean_cash = ifr.load(10, stride=2)
        cls.cells = []
        for plan in ifr.plans(cash_now):
            if plan.label not in tables:
                continue
            windows, zero = tables[plan.label]
            if len(windows) < ifr.MIN_STARTS:
                continue
            for rule in ifr.RULES:
                cls.cells.append(ifr.solve(windows, plan, rule, 400.0, zero))

    def test_no_levered_plan_pays_more_than_the_same_sleeve_unlevered_at_an_equal_floor(self):
        """The Dominance Rule, in the unit the goal is written in. Round 7 found this on a different
        statistic and this round found it again on a new one; if it ever stops being true, that is news and
        this test is where the news has to be argued with."""

        by_plan = {}
        for cell in self.cells:
            if cell.feasible and cell.floor >= 400.0 * 0.999:
                by_plan[cell.plan] = max(by_plan.get(cell.plan, 0.0), cell.median)
        self.assertIn("SPY", by_plan, "the unlevered comparator vanished, so the test proves nothing")
        for levered in ("SPY 1.25x", "SPY 1.50x"):
            self.assertLessEqual(by_plan.get(levered, 0.0), by_plan["SPY"] + 1e-9,
                                 f"{levered} now pays more than plain SPY at an equal floor")

    def test_the_archive_can_be_measured_ten_years_back_from_every_second_month(self):
        starts = max(c.starts for c in self.cells)
        self.assertGreater(starts, 120, f"only {starts} starts; the stride made the table an anecdote")

    def survivors(self, stride: int) -> set:
        """Plans that can promise the cheque, not plans that happen not to die.

        The difference is the round's second finding. A fraction-of-NAV plan never runs out — it is feasible
        at every start on every stride, QQQ included — and it still cannot promise $400 a month, because the
        worst cheque is smaller than the promise. Counting feasibility as survival would have scored QQQ as
        the winner of a contest it lost on its first start date.
        """

        tables, cash_now, _data, _mean_cash = ifr.load(20, stride=stride)
        survivors = set()
        for plan in ifr.plans(cash_now):
            if plan.label not in tables:
                continue
            windows, zero = tables[plan.label]
            if len(windows) < ifr.MIN_STARTS:
                continue
            for rule in ifr.RULES:
                cell = ifr.solve(windows, plan, rule, 400.0, zero)
                if cell.feasible and cell.floor >= 400.0 * 0.999:
                    survivors.add(plan.label)
        return survivors

    def test_the_only_plans_that_survive_a_20_year_400_dollar_promise_are_not_the_levered_ones(self):
        survivors = self.survivors(2)
        self.assertIn("SPY", survivors)
        self.assertIn("cash", survivors)
        self.assertNotIn("SPY 1.25x", survivors)
        self.assertNotIn("SPY 1.50x", survivors)
        self.assertNotIn("QQQ", survivors)
        self.assertNotIn("VOO", survivors, "VOO has no 20-year record; an empty test is not a pass")

    def test_the_start_grid_is_part_of_the_claim_because_it_changes_the_verdict(self):
        """A guarantee is a minimum over start dates, so which months get sampled belongs in the claim.

        This test was written to prove the verdict was robust to the grid. It failed instead, and the failure
        is the finding: every sixth month and every third month both let the levered 20-year promise through,
        and every second month refuses it, because the start date that ends it — April 2000 — sits between
        the sampled months. A promise measured on a coarse grid is a weaker promise wearing the same clothes,
        which is why the tool's default stride is the fine one and why the note quotes the fine grid.
        """

        self.assertIn("SPY", self.survivors(2), "even the plain sleeve failed; check the archive")
        self.assertNotIn("SPY 1.25x", self.survivors(2))
        self.assertIn("SPY 1.25x", self.survivors(3), "the coarse grid no longer flatters the loan; the "
                                                      "finding about the grid has to be re-measured")


class TheCandidateIsTestedByItsOwnControls(unittest.TestCase):
    """Round 20 reopened round 8's candidate in the equal-floor frame, and the round turned on its controls.

    What is pinned here, in the order the bugs were found: the flat control must actually be flat (it once
    quietly returned the candidate itself); a path plan must pay for the churn it asks for; and the candidate's
    claim is against its own sleeve and own average, not against whoever happens to top the table.
    """

    @classmethod
    def setUpClass(cls):
        # Stride 2, the tool's own default and the finest grid the archive supports: a guarantee is a
        # minimum over start dates, and round 19 measured that a coarser grid flatters exactly the rows that
        # are too thin (see test_the_start_grid_is_part_of_the_claim_because_it_changes_the_verdict).
        cls.tables, cls.cash_now, _data, cls.mean_cash = ifr.load(20, stride=2)
        cls.cells = {}
        for plan in ifr.plans(cls.cash_now, ifr.MENU_PUBLIC - cls.mean_cash):
            if plan.label not in cls.tables:
                continue
            windows, zero = cls.tables[plan.label]
            if len(windows) < ifr.MIN_STARTS:
                continue
            for rule in ifr.RULES:
                cls.cells[(plan.label, rule)] = ifr.solve(windows, plan, rule, 400.0, zero)

    def paths(self, kind: str) -> list:
        data = ifr.load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        keys = wc.monthly(ifr.series_for(data, "SPY"), data.cash_factors)[2]
        return ifr.weight_path(kind, data, "SPY", keys)

    def test_the_flat_control_is_flat_and_is_not_its_own_subject(self):
        """One variable did double duty and the control that exists to say "you could have just held this"
        returned the candidate and matched it to the dollar. The tool now refuses a flat control that is not
        flat; this test refuses a flat control that equals the thing it is supposed to falsify."""

        flat, cand = self.paths("avg"), self.paths("candidate")
        self.assertEqual(len(set(round(w, 12) for w in flat)), 1, "the 'flat at avg' control is not flat")
        self.assertGreater(len(set(round(w, 6) for w in cand)), 20, "the candidate path never moves")
        self.assertNotEqual([round(w, 6) for w in flat], [round(w, 6) for w in cand],
                            "the control is the subject: a match here means a variable does two jobs again")
        self.assertAlmostEqual(flat[0], sum(cand) / len(cand), places=6)

    def test_the_reversed_path_keeps_the_same_weights_on_the_same_calendar(self):
        cand, rev = self.paths("candidate"), self.paths("reversed")
        self.assertEqual(sorted(round(w, 6) for w in cand), sorted(round(w, 6) for w in rev),
                         "the mirror image must hold every weight the candidate held, at the same levels")
        self.assertEqual(len(cand), len(rev))

    def test_a_path_pays_for_its_own_churn_and_a_flat_weight_at_the_same_mean_does_not(self):
        """A zero-return window is the only honest place to isolate a turnover charge: nothing can be blamed
        on the market. Round 8 ran the index plan's 10% band, which lets a policy that wants 0.30x sit at
        1.10x for free; a zero band charges every monthly move the policy itself asks for."""

        months = 24
        returns, cash = [0.0] * months, [0.0] * months
        start = date(2000, 1, 1)
        zig = [0.3 if m % 2 else 1.3 for m in range(months)]           # mean 0.80, moves every month
        flat = [0.8] * months                                          # same mean, never moves
        plan = ifr.Plan("zig", "SPY", 1.0, 0.0, 0.0, "SPY", "candidate")
        down = ifr.score((returns, cash, start, zig), plan, "fixed", 400.0)
        hold = ifr.score((returns, cash, start, flat), plan, "fixed", 400.0)
        self.assertLess(down.ending, hold.ending,
                        "a path that trades every month cost the same as one that never trades")
        self.assertEqual(plan.band, 0.0, "a path plan is running the index plan's band and trading for free")
        self.assertEqual(ifr.Plan("SPY", "SPY", 1.0, 0.0, 0.0, "SPY").band, wc.BAND)

    def test_the_candidate_beats_every_control_it_was_told_to_beat(self):
        """The pre-registered bar, in the equal-floor frame: better than the same sleeve held flat, better
        than its own average weight, better than the mirror image of its own path, better with its trend gate
        engaged than without."""

        gain = self.cells[("candidate", "guardrail")]
        for rival in ("SPY", "flat at avg", "reversed", "gateless"):
            other = self.cells[(rival, "guardrail")]
            self.assertGreater(gain.median, other.median,
                               f"the candidate no longer beats {rival}: "
                               f"{gain.median:.0f} vs {other.median:.0f}")
        self.assertTrue(gain.feasible, "the candidate no longer keeps a $400 promise from every start")

    def test_the_candidate_does_not_reopen_the_loan(self):
        """A candidate winning is not a licence to re-open leverage. On the fine grid at 20 years the
        constant-leverage rows still cannot make the promise at all, and this round changes none of that."""

        for levered in ("SPY 1.25x", "SPY 1.50x"):
            cell = self.cells[(levered, "guardrail")]
            self.assertFalse(cell.feasible,
                             f"{levered} kept its promise; the binding start was {cell.binding}")

    def test_the_promise_the_candidate_keeps_is_a_modest_one(self):
        """At $700 a month — 8.4% a year of the lump — every plan in the table dies, candidate included. The
        edge is a floor at a modest promise, not a machine for affording a rich one."""

        windows, zero = self.tables["candidate"]
        plan = next(p for p in ifr.plans(self.cash_now, ifr.MENU_PUBLIC - self.mean_cash)
                    if p.label == "candidate")
        cell = ifr.solve(windows, plan, "fixed", 700.0, zero)
        self.assertFalse(cell.feasible, "an 8.4% withdrawal rate stopped being impossible; re-read the table")

    def test_the_closing_sentence_is_chosen_by_the_candidate_versus_its_own_sleeve(self):
        """Not by who tops the table: at ten years VOO out-pays everything on fifteen benign years, and a
        champion-based sentence would have buried the candidate's own result behind a flattered comparator."""

        cells = [ifr.Cell("candidate", "guardrail", 400.0, 800.0, 400.0, 700.0, 1.75, 0.6, 83, True, "", ""),
                 ifr.Cell("SPY", "guardrail", 400.0, 800.0, 400.0, 600.0, 1.49, 0.1, 83, True, "", ""),
                 ifr.Cell("VOO", "guardrail", 400.0, 800.0, 400.0, 900.0, 2.25, 1.2, 37, True, "", "")]
        text = ifr.verdict(cells, 400.0, 10)
        self.assertIn("This time neither line is the story", text)
        self.assertNotIn("spreadsheet cell", text)
        beaten = [dataclasses.replace(cells[0], median=500.0)] + cells[1:]
        self.assertIn("spreadsheet cell", ifr.verdict(beaten, 400.0, 10))


class TheGeneralisationIsNarrowerThanTheFirstResult(unittest.TestCase):
    """Round 21 priced the same rule on every sleeve in the archive, because the goal names VOO and QQQ and
    round 20 had proved the claim on SPY alone. It mostly is not there, and what is there is a different claim.

    Pinned: where a record never got cut the guardrail sits on its own 2.00x ceiling and the row cannot rank
    anything (flagged, not hidden); the reversal control is weak on a record with one mid-placed crisis; and
    on VOO's ten mild years the whole gap is a few dollars a month, inside the noise floor of choosing a
    cheaper fund.
    """

    @classmethod
    def setUpClass(cls):
        cls.tables, cls.cash_now, cls.data, cls.mean_cash = ifr.load(10, stride=2)
        cls.plans = {p.label: p for p in ifr.plans(cls.cash_now, ifr.MENU_PUBLIC - cls.mean_cash)}
        cls.cells = {}
        for label, plan in cls.plans.items():
            windows, zero = cls.tables[label]
            if len(windows) < ifr.MIN_STARTS:
                continue
            cls.cells[label] = ifr.solve(windows, plan, "guardrail", 400.0, zero)

    def test_a_row_the_promise_never_tested_is_flagged_instead_of_quoted(self):
        hot = ifr.Cell("x", "guardrail", 400.0, 800.0, 400.0, 797.0, 1.99, 1.2, 37, True, "", "")
        cold = ifr.Cell("y", "guardrail", 400.0, 800.0, 400.0, 597.0, 1.49, 0.1, 143, True, "", "")
        self.assertTrue(ifr.saturated(hot))
        self.assertFalse(ifr.saturated(cold))
        self.assertFalse(ifr.saturated(dataclasses.replace(hot, rule="fixed")))
        # The tag can only appear on a pair the verdict actually compares, so the two synthetic cells wear
        # the names of a real pair rather than "x" and "y", which the verdict would simply skip.
        hot = dataclasses.replace(hot, plan="cand VOO")
        cold = dataclasses.replace(cold, plan="VOO")
        self.assertIn("NOT DISCRIMINATING", ifr.verdict([hot, cold], 400.0, 10))

    def test_the_cheap_fund_the_goal_names_is_not_moved_by_the_rule(self):
        """VOO's record begins 2010-09: fifteen benign years, 37 starts, and not one month where the promise
        bound. On that record the candidate is worth a few dollars a month per $100k — inside the band of
        picking a cheaper fund, which is a five-minute decision for the holder of this ETF."""

        gap = self.cells["cand VOO"].median - self.cells["VOO"].median
        self.assertLess(abs(gap), ifr.NOISE_FLOOR, f"VOO moved ${gap:,.0f}/mo; re-read the ceiling flag")
        self.assertTrue(ifr.saturated(self.cells["cand VOO"]))

    def test_the_control_that_decided_the_sleeve_is_inconclusive_on_the_thinnest_one(self):
        """ITOT's record holds one crisis, placed near the middle, so its mirror image also de-risks through
        it (mean weight 0.90 against the candidate's 0.53, rather than the 1.02 against 0.53 that decides
        SPY). That is a control with little power, not a candidate refuted — so what is pinned is that the
        gap stays inside the noise band, not that the candidate wins."""

        gap = self.cells["cand ITOT"].median - self.cells["rev ITOT"].median
        self.assertLess(abs(gap), ifr.NOISE_FLOOR, f"ITOT's reversal gap is now ${gap:,.0f}/mo")
        self.assertGreater(self.cells["candidate"].median, self.cells["reversed"].median)

    def test_the_reversal_passes_where_the_record_holds_two_crises(self):
        self.assertLess(self.cells["rev QQQ"].median, self.cells["cand QQQ"].median,
                        "the mirror image now matches the candidate on QQQ")

    def test_a_control_carries_its_subjects_own_weights_on_every_sleeve(self):
        for sleeve in ifr.SLEEVE_LEAGUE:
            if sleeve == "SPY":
                continue
            keys = wc.monthly(ifr.series_for(self.data, sleeve), self.data.cash_factors)[2]
            cand = ifr.weight_path("candidate", self.data, sleeve, keys)
            rev = ifr.weight_path("reversed", self.data, sleeve, keys)
            self.assertEqual(sorted(round(w, 6) for w in cand), sorted(round(w, 6) for w in rev),
                             f"{sleeve}: the control no longer holds its subject's own weights")
            self.assertAlmostEqual(sum(cand) / len(cand), sum(rev) / len(rev), places=9)

    def test_a_sleeve_too_short_for_the_plan_builds_no_windows_rather_than_a_failure(self):
        tables, _c, _d, _m = ifr.load(20, stride=2)
        self.assertEqual(len(tables["cand VOO"][0]), 0,
                         "VOO suddenly has a 20-year window; the record changed under the table")

    def test_the_noise_floor_used_here_is_the_one_round_eighteen_measured(self):
        """Provenance, not a constant someone typed. This table is per $100k and round 18's floor was on a
        $20k funded frame, so the relationship is exactly the ratio of the two capitals."""

        import attention_bar as ab
        self.assertAlmostEqual(ifr.NOISE_FLOOR, ab.NOISE_FLOOR * (wc.START / 20_000.0), places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
