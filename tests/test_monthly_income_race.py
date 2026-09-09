"""Round 58: the objective's two halves priced in one table, and the checks that make the table mean anything.

The regression test that matters is `test_the_trend_series_is_not_the_bill_series_in_disguise`. A dict built on
`(year, month)` tuples was read back with `date` keys, and `.get(k, 0.0)` answered every miss with "hold cash", so
the long-history MA200 row was the bill yield wearing a trend rule's name. It printed $31.04, the same figure as the
bill blend in the row below it, and that coincidence is the only reason it was caught.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                        # noqa: E402
import rotation_edge as re_                              # noqa: E402
import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class Harness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.ordered, cls.rets, cls.bills, cls.expense = re_.panel(cls.data)
        pos = {d: i for i, d in enumerate(tc.days_of(cls.data, "SPY"))}
        cl = tc.closes_of(cls.data, "SPY")
        cls.closes = {"SPY": [cl[pos[d]] for d in cls.ordered]}
        cls.weight = {leg: mir.leg_weights(leg, cls.ordered, cls.rets, cls.bills, cls.expense, cls.closes,
                                           re_.UNKNOWN_ER) for leg in mir.LEGS}
        cls.path = {leg: mir.wealth_path(cls.ordered, cls.rets, cls.bills, cls.expense, cls.weight[leg])
                    for leg in mir.LEGS}
        cls.marks = {leg: mir.month_marks(cls.ordered, cls.path[leg]) for leg in mir.LEGS}
        cls.bill_map = mir.bill_months(cls.data, cls.ordered)


class ThePathRunnerMatchesTheEngine(Harness):

    def test_every_legs_path_ends_exactly_where_the_engine_says_it_ends(self):
        """A runner that returns a balance is new in the repository, and every window statistic in this file is
        built from it. It is duplicated arithmetic, so it is pinned to the arithmetic it duplicates."""

        for leg in mir.LEGS:
            want = re_.run_weights(self.ordered, self.rets, self.bills, self.expense, self.weight[leg])["wealth"]
            self.assertAlmostEqual(self.path[leg][-1], want, places=10,
                                   msg=f"{leg}: the path runner has drifted from run_weights")

    def test_the_marks_reproduce_the_path_and_drop_both_partial_ends(self):
        keys, mr = self.marks["SPY hold"]
        compound = 1.0
        for r in mr:
            compound *= (1.0 + r)

        def last_day_of(y, m):
            return max(i for i, d in enumerate(self.ordered) if (d.year, d.month) == (y, m))

        # The denominator is the end of the month the panel STARTED in — which is dropped as a mark, so the first
        # mark's own month is not where compounding begins.
        first_end = last_day_of(self.ordered[0].year, self.ordered[0].month)
        last_mark = last_day_of(*keys[-1])
        # path[i-1] is the balance at ordered[i]. The product cannot reach the terminal balance, because the panel's
        # last few days belong to an unfinished month and no mark claims them.
        self.assertAlmostEqual(compound, self.path["SPY hold"][last_mark - 1]
                               / self.path["SPY hold"][first_end - 1], places=10,
                               msg="the monthly marks do not compound back to the daily path")
        self.assertLess(last_mark, len(self.ordered) - 1, "a trailing partial month was marked after all")
        self.assertNotEqual((self.ordered[0].year, self.ordered[0].month), keys[0],
                            "the first mark covers a part-month and is a month-shaped lie")
        last = self.ordered[-1]
        self.assertNotEqual((last.year, last.month), keys[-1],
                            "the trailing partial month survived: round 47, again")

    def test_every_leg_is_measured_on_the_same_months(self):
        ns = {leg: len(self.marks[leg][0]) for leg in mir.LEGS}
        self.assertEqual(len(set(ns.values())), 1, f"a leg got a longer sample than another: {ns}")
        self.assertGreater(ns[mir.LEGS[0]], 240)

    def test_a_bill_weight_of_one_is_the_bill_series_and_nothing_else(self):
        # month_marks returns (month keys, monthly returns), in that order.
        keys, eq = self.marks["SPY hold"]
        b = mir.blend(eq, [self.bill_map[k] for k in keys], 1.0)
        self.assertEqual(b, [self.bill_map[k] for k in keys])

    def test_an_undeclared_leg_is_an_error_rather_than_the_index(self):
        with self.assertRaises(ValueError):
            mir.leg_weights("news_sentiment", self.ordered, self.rets, self.bills, self.expense,
                            self.closes, re_.UNKNOWN_ER)


class TheBugThatLookedLikeAResult(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.lh = mir.long_history(cls.data, 100_000.0, 10, 0.05)
        last = max(cls.data.by_date)
        ser = {d: cls.data.by_date[d]["SPY"].close for d in cls.data.by_date if "SPY" in cls.data.by_date[d]}
        cls.eq, cls.cash, cls.keys = wc.monthly_complete(ser, cls.data.cash_factors, last)

    def test_the_trend_series_is_not_the_bill_series_in_disguise(self):
        """Keyed by tuples, read with dates, defaulted to cash: the failure was silent and the numbers looked
        plausible, because a trend rule that holds bills sometimes is exactly what MA200 does."""

        sig = mir.long_history(self.data, 100_000.0, 10, 0.05)
        ma_amt = sig["MA200 monthly"]["amount"]
        self.assertGreater(ma_amt, 300.0,
                           f"MA200's long-history safe income is ${ma_amt:,.2f}: it has started matching the "
                           "bill yield again, which is how the tuple/date key mismatch announced itself")
        self.assertNotAlmostEqual(ma_amt, sig["MA200 +25% bills"]["amount"], places=2,
                                  msg="a leg and its own bill blend agree to the cent; something is aliasing")

    def test_the_trend_rule_was_in_the_market_most_of_the_record(self):
        days, closes = tc.days_of(self.data, "SPY"), tc.closes_of(self.data, "SPY")
        me = {}
        for i, d in enumerate(days):
            me[(d.year, d.month)] = i
        in_month = sum(1 for k, i in me.items()
                       if tc.sma(closes, 200, i) is not None and closes[i] > tc.sma(closes, 200, i))
        self.assertGreater(in_month / len(me), 0.60,
                           "MA200 was out of the market more than 40% of months since 1993; re-check the signal")

    def test_plain_spy_cannot_meet_the_ends_whole_promise_at_any_withdrawal(self):
        v = self.lh["SPY hold"]
        self.assertEqual(v["amount"], 0.0, "a safe withdrawal has appeared for plain SPY under 'ends whole'")
        self.assertGreater(v["p_fail_at_zero"], 0.05,
                           "the promise no longer fails on its own, so the $0.00 in this table needs re-explaining")
        self.assertGreater(v["loose"], 500.0,
                           "under the weaker promise plain SPY does not price above $500/mo; check the simulation")

    def test_a_weaker_promise_never_prices_lower_than_a_stronger_one(self):
        for label, v in self.lh.items():
            self.assertGreaterEqual(v["loose"], v["amount"], f"{label}: the looser promise priced lower")

    def test_the_rule_beats_the_index_on_income_on_the_long_record_under_both_promises(self):
        r, i = self.lh["MA200 monthly"], self.lh["SPY hold"]
        self.assertGreater(r["amount"], i["amount"], "the trend rule no longer beats the index on withdrawable"
                           " income on the long record; re-read the note before restating the claim")
        self.assertGreater(r["loose"], i["loose"])
        self.assertLess(r["stats"]["median_mult"], i["stats"]["median_mult"],
                        "the rule now grows more than the index too, which contradicts round 57")


class ThePlanArithmetic(unittest.TestCase):

    def test_failure_is_monotone_in_the_withdrawal(self):
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        last = max(data.by_date)
        ser = {d: data.by_date[d]["SPY"].close for d in data.by_date if "SPY" in data.by_date[d]}
        eq, cash, _k = wc.monthly_complete(ser, data.cash_factors, last)
        rates = [mir.plan_stats(eq, 100_000.0, amt, 10)["p_fail"] for amt in (0.0, 200.0, 400.0, 600.0, 900.0)]
        self.assertEqual(rates, sorted(rates), f"failure rate fell as the withdrawal grew: {rates}")
        self.assertGreater(rates[-1], rates[1])

    def test_a_sample_with_no_complete_window_is_untested_not_safe(self):
        self.assertIsNone(mir.safe_amount([0.01] * 24, 100_000.0, 10, 0.05))
        st = mir.plan_stats([0.01] * 24, 100_000.0, 100.0, 10)
        self.assertEqual(st["n"], 0)
        self.assertIsNone(st["p_fail"], "an empty sample was read as a zero failure rate")

    def test_the_bisected_amount_actually_meets_its_own_budget(self):
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        ordered, rets, bills, expense = re_.panel(data)
        w = re_.constant_weights("SPY", len(ordered))
        keys, mr = mir.month_marks(ordered, mir.wealth_path(ordered, rets, bills, expense, w))
        bm = mir.bill_months(data, ordered)
        amt = mir.safe_amount(mr, 100_000.0, 10, 0.05)
        st = mir.plan_stats(mr, 100_000.0, amt, 10)
        self.assertLessEqual(st["p_fail"], 0.05 + 1.0 / st["n"],
                             f"the bisection returned P(fail) {st['p_fail']:.2%} against a 5% budget")
        just_over = mir.plan_stats(mr, 100_000.0, amt + 50.0, 10)
        self.assertGreater(just_over["p_fail"], st["p_fail"], "the amount was not the largest that fits")
        del bm


if __name__ == "__main__":
    unittest.main(verbosity=2)
