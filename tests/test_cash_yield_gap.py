"""Tests for the cash-yield gap: that the arithmetic is the boring kind it claims to be, and that the audit
compares the right two quantities.

A tool whose whole claim is "this one has no variance" earns a harsher test bar than the stochastic tools, not a
looser one: a sign error in a rate difference is not hidden by a confidence interval, it simply states a false
fact in dollars. So the tests recompute every published line by hand from the same inputs, and the audit tests
pin the two quantities that must not be conflated — the yield the simulation *credited* versus the yield an
account *would have been paid* — because the whole finding is the difference between them.
"""

from __future__ import annotations

import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cash_yield_gap as cy                        # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheBillLegComesFromTheArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.b = cy.bill(cls.data)

    def test_every_window_is_present_and_named_for_what_it_measures(self):
        """`current3m` is a three-month annualisation and is not `last3y`; the first draft labelled it as the
        three-year figure and the output read as a contradiction with the same file's own table."""

        for key in ("current3m", "last1y", "last3y", "last10y", "sigma_mo"):
            self.assertIn(key, self.b)
        # Round 47 inverted this test. It used to recompute the windows from `wc.monthly(...)[-3:]`, which
        # included the partial September bucket and so *asserted the defect*: a four-day accrual compounded as a
        # month. The recomputation must come from the same complete-month series `bill()` uses, or this test
        # checks the arithmetic and not the window.
        _r, rates, _k = cy.cash_months(self.data)
        self.assertAlmostEqual(self.b["current3m"], (1 + statistics.fmean(rates[-3:])) ** 12 - 1.0, places=12)
        self.assertAlmostEqual(self.b["last1y"], (1 + statistics.fmean(rates[-12:])) ** 12 - 1.0, places=12)
        self.assertGreater(self.b["current3m"], 0.03, "the stub's four days must not return as the spot")

    def test_the_curve_is_quoted_in_a_sane_range_and_its_volatility_is_tiny(self):
        self.assertGreater(self.b["current3m"], 0.0)
        self.assertLess(self.b["current3m"], 0.10)
        # The claim of "no variance" is a claim about this number: a month's cash rate moves in basis points.
        self.assertLess(self.b["sigma_mo"], 0.002)


class TheArithmeticIsRecomputable(unittest.TestCase):
    def test_the_gain_line_is_the_rate_difference_times_the_balance_divided_by_twelve(self):
        balance, sweep = 20_000.0, cy.SWEEP_MEDIAN
        b = {"current3m": 0.0300, "last1y": 0.03, "last3y": 0.03, "last10y": 0.03, "sigma_mo": 0.0001}
        cons = balance * (b["current3m"] - cy.SGOV_ER - sweep) / 12.0
        self.assertAlmostEqual(cons, 20_000.0 * (0.03 - 0.0009 - 0.0002) / 12.0, places=6)
        self.assertGreater(cons, 45.0)
        self.assertLess(cons, 50.0)

    def test_the_break_even_is_the_bill_minus_the_expense_and_nothing_else(self):
        self.assertAlmostEqual(cy.SGOV_ER, 0.0009, places=8)
        self.assertGreater(cy.BIL_ER, cy.SGOV_ER, "SGOV is the cheaper leg and the tool's headline leg")

    def test_a_high_sweep_makes_the_switch_worth_nothing_rather_than_negative_praise(self):
        """A broker paying above break-even must show a gain of zero, not a negative number dressed as advice."""

        balance, bill_now, sweep = 20_000.0, 0.0288, 0.0350
        cons = max(0.0, bill_now - cy.SGOV_ER - sweep) * balance / 12.0
        self.assertEqual(cons, 0.0)


class TheAuditComparesTheRightTwoThings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.b = cy.bill(cls.data)
        cls.strat, cls.bench, cls.keys, cls.weights = cy.bp.net_strategy_returns(
            cls.data, "SPY", 3.0, float(wc.EXPENSE["SPY"]))

    def test_the_idle_fraction_is_the_positive_part_of_one_minus_the_weight(self):
        idle = [max(1.0 - w, 0.0) for w in self.weights]
        self.assertTrue(all(0.0 <= i <= 0.7 for i in idle))
        self.assertGreater(statistics.fmean(idle), 0.05, "the rule holds no cash; re-read the claim")
        # A rule whose mean weight exceeds one still holds cash in most months; idle and borrow coexist.
        borrow = [max(w - 1.0, 0.0) for w in self.weights]
        self.assertGreater(statistics.fmean(borrow), 0.0)

    def test_the_unearned_credit_is_larger_than_the_edge_it_sits_against(self):
        """The finding, pinned: the simulation paid the rule a bill yield on its idle slice and an account on
        a 0.02% sweep would not have received it. That single assumption is worth more than the whole measured
        edge, which is why this round exists."""

        idle = statistics.fmean([max(1.0 - w, 0.0) for w in self.weights])
        gap = idle * (self.b["current3m"] - cy.SWEEP_MEDIAN)
        self.assertGreater(gap, cy.RULE_EDGE_YR,
                           f"the cash assumption is now {gap:.4%} against an edge of "
                           f"{cy.RULE_EDGE_YR:.2%}: the edge may survive it, re-read the note")

    def test_the_tool_refuses_to_call_the_execution_spread_a_loan(self):
        """`paper.py` carries spread_bps 3.0, which is what a fill costs, not what a margin line costs. The
        cheapest posted desk is 4.90% and round 19 priced that; conflating them would flatter leverage by two
        orders of magnitude."""

        self.assertLess(3.0 / 10_000.0, 0.001)
        import income_frontier as ifr
        self.assertGreater(ifr.MENU_PUBLIC, 0.04)


class TheFloatOnADividendIsNotTheAccount(unittest.TestCase):
    """Round 27's negative result, pinned so it cannot return as an idea.

    A rate spread is only worth money on a balance that exists. Round 24's $46/mo applied the spread to the
    whole account; a dividend float applies the same spread to one cheque, which on SPY is a quarter of a
    1.65% yield. The hypothesis that "distributions sit in a 0.02% sweep, so the total-return backtests
    overstate returns" is the kind that appears to follow from the previous round's finding and does not.
    """

    @classmethod
    def setUpClass(cls):
        import collections
        import csv
        by = collections.defaultdict(list)
        for r in csv.DictReader((ROOT / "data/snapshots/20260906T203953Z/distributions_daily.csv").open()):
            if float(r["dividend"]) > 0:
                by[r["symbol"]].append((r["date"], float(r["dividend"]), float(r["close"])))
        cls.events = by
        cls.b = cy.bill(load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE))

    def _yield_and_events(self, symbol: str) -> tuple:
        import datetime as dt
        ev = self.events[symbol]
        yrs = (dt.date.fromisoformat(ev[-1][0]) - dt.date.fromisoformat(ev[0][0])).days / 365.25
        yld = sum(d for _, d, _ in ev) / (sum(c for _, _, c in ev) / len(ev)) / yrs
        return yld, len(ev) / yrs

    def test_a_month_of_delayed_reinvestment_costs_less_than_a_hundredth_of_a_basis_point(self):
        yld, per_year = self._yield_and_events("SPY")
        delay = (yld / per_year) * cy.SWEEP_MEDIAN * (30.0 / 365.25)
        self.assertLess(delay, 0.000001, f"a month's float on SPY now costs {delay:.3%}/yr")
        self.assertLess(delay * 20_000.0 / 12.0, 0.01, "$0.01/mo on $20,000 is the whole of it")

    def test_even_never_reinvesting_anything_costs_under_two_fifty_a_month(self):
        """The worst case is not a delay but a standing decision not to reinvest: a year's distributions sit
        as cash all year, forgoing the bill rate. Still under a twentieth of the idle-cash switch, because
        what is forgone is a spread on a yield rather than the yield."""

        worst = max(self._yield_and_events(s)[0] * (self.b["current3m"] - cy.SWEEP_MEDIAN)
                    for s in ("SPY", "QQQ", "TLT", "IEF", "EFA", "EEM"))
        # Measured $1.55/mo at the old stub-contaminated 2.88% spot, $2.11 at the corrected 3.91%. The threshold
        # moved because the number it tests moved, not to make the test pass.
        self.assertLess(worst, 0.0015)
        self.assertLess(worst * 20_000.0 / 12.0, 2.50)

    def test_the_bond_funds_pay_monthly_and_the_equity_funds_do_not_which_is_the_real_finding(self):
        """Cash-flow shape, not return. An income plan on TLT is handed a cheque every month and on SPY every
        quarter, and GLD hands over nothing at all; no round had opened this file before round 27."""

        self.assertGreater(self._yield_and_events("TLT")[1], self._yield_and_events("SPY")[1] * 2.5)
        self.assertNotIn("GLD", self.events, "GLD has started paying; the income note needs re-reading")

    def test_the_two_share_classes_distribute_alike_so_the_fee_is_the_whole_difference(self):
        y_voo, _ = self._yield_and_events("VOO")
        y_spy, _ = self._yield_and_events("SPY")
        self.assertLess(abs(y_voo - y_spy), 0.0005,
                        "round 18's share-class result was the expense ratio alone; if the distributions have "
                        "diverged that result needs re-pricing")


class TheSwitchIsAnOptionNotARate(unittest.TestCase):
    """Round 31. Round 30 established that a rate-dependent plan must be priced per window, and this file's own
    headline recommendation was priced off a spot quote. `path()` re-prices it across the whole record, and the
    claim it produces — that the switch is worth real money most of the time and almost nothing some of the time
    — has to survive the record being re-read, not survive my reading of it.
    """

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.p = cy.path(cls.data)

    def test_the_spot_quote_is_reported_alongside_where_it_sits_in_the_record(self):
        self.assertGreater(self.p["months"], 300, "the path should span most of the archive, not a window")
        self.assertGreater(self.p["percentile"], 0.30)
        self.assertLess(self.p["percentile"], 0.80, "today is mid-cycle; if that stops being true the headline "
                                                   "note needs re-reading, not re-quoting")
        self.assertLess(self.p["q1"], 0.01, "the record must still contain a near-zero-rate quartile, which is "
                                            "the whole content of the caveat")
        self.assertGreater(self.p["q3"], self.p["median"])

    def test_the_switch_worsted_out_somewhere_in_the_record_and_still_cleared_a_third_of_it(self):
        self.assertGreaterEqual(self.p["share_under_100"], 0.20)
        self.assertGreater(self.p["share_over_1k"], 0.40)
        self.assertLess(self.p["worth_at_q1"], 5.0, "$1.05/mo at the lower quartile is the honest downside")
        self.assertGreater(self.p["worth_spot"], 20.0)

    def test_the_median_month_is_worth_less_than_the_quoted_spot(self):
        """The recommendation is currently quoted at its best-adjacent number, so the test that keeps it honest
        is the one asserting the record's median is *lower* than today."""

        self.assertLess(self.p["worth_at_median"], self.p["worth_spot"])
        self.assertLess(self.p["median"], self.p["spot"])

class TheSwitchIsNotAHedge(unittest.TestCase):
    """Round 44. Everything this file had established about the switch was unconditional: what it pays on average,
    at each rate percentile, over the record. The goal asks for a monthly income, and an income that arrives when
    the account is also being hurt is worth less per dollar than one that arrives when it is not — so the
    conditional numbers are the ones a decision should be made from, and they run the wrong way."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.c = cy.contingency(cls.data, 20_000.0)
        cls.reg = {r["label"]: r for r in cls.c["regimes"]}

    def test_the_pay_is_lower_in_the_months_the_account_was_losing(self):
        self.assertLess(self.c["worst_decile"], self.c["mean"])
        self.assertLess(self.c["worst_decile"], self.c["best_decile"])
        self.assertLess(self.c["crash"], self.c["surge"])

    def test_the_monthly_correlation_is_small_so_the_deciles_are_the_evidence_not_the_correlation(self):
        """A hedge could be uncorrelated at monthly frequency and still pay in crises. The claim being refuted is
        about the conditional level, so the correlation is pinned as *uninformative* rather than as negative."""

        self.assertLess(abs(self.c["corr"]), 0.15)

    def test_in_the_two_worst_crises_it_paid_an_others_worth(self):
        for label in ("GFC", "march 2020"):
            r = self.reg[label]
            self.assertGreaterEqual(r["months"], 5, f"{label} barely overlaps the archive; check the window")
            self.assertLess(r["mean"], 0.25 * self.c["mean"], f"{label} paid {r['mean']:+.2f}, not a crisis wage")
        self.assertAlmostEqual(self.reg["GFC"]["mean"], 5.77, delta=0.05)
        self.assertLess(self.reg["GFC"]["min"], 0.0, "the switch cost money inside the GFC")

    def test_the_bull_market_that_covered_a_third_of_the_record_paid_almost_nothing(self):
        """144 of 404 months at $6.66. This is the finding that makes the headline figure a regime price rather
        than a rate of income."""

        r = self.reg["QE bull 2010-2021"]
        self.assertGreaterEqual(r["months"], 120)
        self.assertLess(r["mean"], 0.20 * self.c["mean"])
        self.assertGreater(self.reg["the whole archive"]["months"], 380)

    def test_the_worst_month_in_the_record_paid_less_than_a_quarter_of_the_average(self):
        worst = self.c["worst_months"][0]
        self.assertEqual(str(worst["date"])[:7], "2008-10", "SPY -16.52% must still be the worst month")
        self.assertAlmostEqual(worst["worth"], 10.66, delta=0.05)
        self.assertLess(worst["worth"], 0.30 * self.c["mean"])

    def test_every_named_episode_actually_found_months_and_the_total_reconciles(self):
        """A regime window with a typo returns nothing and prints nothing, which would quietly delete the
        evidence this class exists to present. And the 'whole archive' row must be the same mean the section
        opens with, or the conditioning and the unconditional figures are not the same quantity."""

        self.assertEqual({r["label"] for r in self.c["regimes"]}, {l for l, _a, _b in cy.REGIMES})
        self.assertAlmostEqual(self.reg["the whole archive"]["mean"], self.c["mean"], places=9)

    def test_scaling_the_balance_scales_the_pay_and_not_the_conclusion(self):
        big = cy.contingency(self.data, 40_000.0)
        self.assertAlmostEqual(big["mean"], 2 * self.c["mean"], places=6)
        self.assertAlmostEqual(big["corr"], self.c["corr"], places=9)

class CrisesEnumeratedNotChosen(unittest.TestCase):
    """Round 45. `contingency`'s episodes were dated by the author, and the archive's answer changed with the
    dates. This class re-runs the same claim with no date chosen at all — a bear month is one where the index sits
    more than D% below its own trailing peak, at three depths — and pins both weightings because they disagree."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.rows = {r["depth"]: r for r in cy.bear_sweep(cls.data, 20_000.0)}
        cls.mean = cls.rows[0.10]["record_mean"]
        cls.series = {k: v["SPY"].close for k, v in cls.data.by_date.items() if "SPY" in v}

    def test_a_deeper_drawdown_always_pays_less_and_no_date_was_chosen_to_get_that(self):
        pay = [self.rows[d]["bear_mean"] for d in cy.BEAR_DEPTHS]
        for a, b in zip(pay, pay[1:]):
            self.assertGreater(a, b, "the pay-depth relation is no longer monotone; re-read the finding")
        for d in cy.BEAR_DEPTHS:
            self.assertLess(self.rows[d]["bear_mean"], self.rows[d]["calm_mean"])
            self.assertLess(self.rows[d]["bear_mean"], self.mean)

    def test_the_episode_sets_nest_so_the_depth_sweep_is_one_story_not_three(self):
        counts = [self.rows[d]["months"] for d in cy.BEAR_DEPTHS]
        for a, b in zip(counts, counts[1:]):
            self.assertGreater(a, b)

    def test_the_two_weightings_disagree_and_that_disagreement_is_the_finding(self):
        """Month-weighted, a crisis pays $27.19. Episode-weighted, the same nine episodes average $32.54, because
        a two-month episode and a 32-month one are each 'one crisis'. The tool reports both, and this test fails
        if they ever converge — at which point the caveat can be deleted rather than carried."""

        r = self.rows[0.10]
        self.assertGreater(r["episode_median"], r["bear_mean"])
        self.assertLess(r["episode_min"], 0.0, "some episode paid negative money; the range must show it")

    def test_the_only_tightening_episode_paid_above_the_record_mean_while_the_index_was_falling(self):
        """The counterexample, pinned so the mechanism cannot silently degrade into 'crises pay badly'. In
        2022-04..2023-05 the index was down and the switch paid more than its own record average, because the bill
        rate was being raised. The switch tracks the Fed, not the market."""

        eps = {str(e["start"])[:7]: e for e in self.rows[0.10]["episodes_list"]}
        self.assertIn("2022-04", eps, "the tightening episode has moved; re-measure the counterexample")
        e = eps["2022-04"]
        self.assertEqual(e["path"], "tightening")
        self.assertGreater(e["pay"], self.mean)
        self.assertLess(e["index"], 0.0)

    def test_the_drawdown_series_sees_the_archive_s_own_crisis_and_a_calm_series_has_none(self):
        rets, _cash, _keys = wc.monthly(self.series, self.data.cash_factors)
        dd = cy.drawdown(rets)
        self.assertEqual(len(dd), len(rets))
        self.assertLess(min(dd), -0.45, "the archive's worst monthly drawdown should be near -52%")
        self.assertEqual(cy.drawdown([]), [])
        self.assertEqual([x for x in cy.drawdown([0.01] * 60) if x < 0], [],
                         "a rising series must produce no drawdown at all")

    def test_scaling_the_balance_scales_the_dollars_and_changes_no_count(self):
        big = {r["depth"]: r for r in cy.bear_sweep(self.data, 40_000.0)}
        for d in cy.BEAR_DEPTHS:
            self.assertAlmostEqual(big[d]["bear_mean"], 2 * self.rows[d]["bear_mean"], places=6)
            self.assertEqual(big[d]["months"], self.rows[d]["months"])
            self.assertEqual(big[d]["episodes"], self.rows[d]["episodes"])

class TheSealIsNotAMonth(unittest.TestCase):
    """Round 47. The archive seals after a session, so its final 'month' is usually a stub — four trading days as
    of the 2026-09-04 seal. `bill()` annualised the last three buckets by compounding their mean twelve times,
    which read a four-day accrual as a month and quoted 2.88% against the curve's own 3.81% for August. That
    number carried `worth_spot` and the percentile that produced the sentence 'today sits below the median of the
    record', so a published recommendation was being understated by a calendar artefact."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.p = cy.path(cls.data)
        cls.s = cy.sweep_sensitivity(cls.data, 20_000.0)

    def test_the_month_end_helper_knows_its_calendar(self):
        from datetime import date
        self.assertEqual(cy.last_business_day(2026, 9), date(2026, 9, 30))   # a Wednesday
        self.assertEqual(cy.last_business_day(2026, 2), date(2026, 2, 27))   # Feb, 28th is a Sunday
        self.assertEqual(cy.last_business_day(2026, 5), date(2026, 5, 29))   # 31st is a Sunday -> Friday 29th
        self.assertEqual(cy.last_business_day(2026, 10), date(2026, 10, 30)) # 31st is a Saturday

    def test_the_partial_bucket_is_gone_and_the_spot_is_no_longer_the_stub(self):
        self.assertEqual(self.p["months"], 403, "the trailing partial month is back; every spot number drifts")
        _r, factors, keys = cy.cash_months(self.data)
        last_full = factors[-1] * 12.0
        self.assertLess(abs(self.p["spot"] - last_full), 0.015,
                        f"spot {self.p['spot']:.2%} is far from the last complete month {last_full:.2%}")
        self.assertGreater(self.p["spot"], 0.03, "the stub's 0.73% must not return as 'today'")

    def test_the_corrected_spot_restates_the_published_headline(self):
        """The direction of the correction matters: it made the recommendation *better*, which is the only reason
        nobody noticed by the numbers going the wrong way."""

        self.assertGreater(self.p["worth_spot"], 60.0, "the $46.12 era is over; today prices nearer $63")
        self.assertGreater(self.p["percentile"], 0.60, "the 'below the median' sentence must never return")

    def test_the_switch_shrinks_monotonically_as_the_desk_pays_more(self):
        means = [r["mean"] for r in self.s["rows"]]
        for a, b in zip(means, means[1:]):
            self.assertGreater(a, b, "a richer sweep must not improve the ladder's case")
        rich = self.s["rows"][-1]
        self.assertLess(rich["spot"], 0.0, "at a 4% sweep the ladder must cost money today")
        self.assertLess(self.s["breakeven_median"], 0.03,
                        "the median month of the record cannot clear a 3% sweep")

    def test_the_break_even_is_an_identity_and_not_a_fourth_measurement(self):
        self.assertAlmostEqual(self.s["breakeven_spot"], self.s["spot"] - cy.SGOV_ER, places=12)

    def test_doubling_the_balance_doubles_every_column_and_changes_no_share(self):
        big = cy.sweep_sensitivity(self.data, 40_000.0)
        for a, b in zip(self.s["rows"], big["rows"]):
            self.assertAlmostEqual(b["mean"], 2 * a["mean"], places=6)
            self.assertAlmostEqual(b["spot"], 2 * a["spot"], places=6)
            self.assertAlmostEqual(b["share_positive"], a["share_positive"], places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
