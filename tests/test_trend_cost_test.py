"""Round 55: the short-horizon rules the objective asks about, tested without lookahead at four cost levels.

This file exists because its tool was wrong twice, in the two directions that flatter a timing rule hardest. Both
numbers are pinned here, not buried: an off-risk leg that read a daily factor as a monthly rate (MA200 reported
2036% CAGR while the benchmark stayed perfectly correct at 10.77%), and a signal applied to the return of the day
that produced it (20.33%). With both removed the same rule makes 8.86% and loses to holding.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class TheLegsAreWhatTheyClaim(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.days, cls.rets, cls.cl, cls.bills, cls.expense = tc.daily_legs(cls.data, "SPY")

    def test_the_daily_bill_leg_reproduces_the_monthly_one_by_a_different_route(self):
        """The sentinel for the bug that made MA200 earn 2036% a year: `cash_factors` holds a daily FACTOR, and
        compounding it across a month must reproduce the monthly factor every other tool in the repository uses.
        Reading the factor as a monthly rate and dividing by days paid roughly 190% a year to any rule that held
        cash — and the buy-and-hold benchmark, which never holds cash, stayed exactly right at 10.77%, so the table
        looked healthy. A control cannot detect a corruption that only appears in the treated arms."""

        month = (self.days[200].year, self.days[200].month)
        idx = [i for i, d in enumerate(self.days) if (d.year, d.month) == month]
        compounded = 1.0
        for i in idx:
            compounded *= (1.0 + self.bills[i])
        ser = {x: self.data.by_date[x]["SPY"].close for x in self.data.by_date if "SPY" in self.data.by_date[x]}
        _r, cash, keys = wc.monthly(ser, self.data.cash_factors)
        want = [c for k, c in zip(keys, cash) if (k.year, k.month) == month][0]
        self.assertAlmostEqual(compounded - 1.0, want, places=12,
                               msg="the off-risk leg is no longer the one the rest of the repository uses")
        self.assertLess(max(self.bills) * 252.0, 0.10, "the off-risk leg is paying double-digit annualised")

    def test_a_rule_that_never_holds_equity_earns_bills_and_nothing_else(self):
        """The second sentinel: an entirely out-of-market rule must land near the bill yield, not near the equity
        yield. This is the check that generalises the bug above to any future refactor."""

        cash_only = tc.run(self.rets, self.bills, [0.0] * len(self.rets), 0.0, 1)
        self.assertGreater(cash_only["cagr"], 0.005)
        self.assertLess(cash_only["cagr"], 0.05,
                        f"an all-cash rule made {cash_only['cagr']:.1%} a year: the off-risk leg is broken again")
        held = tc.run(self.rets, self.bills, [1.0] * len(self.rets), 0.0, 1)
        self.assertGreater(held["cagr"], cash_only["cagr"] * 2)

    def test_the_archive_is_deep_enough_for_the_rules_and_not_every_sleeve(self):
        self.assertGreater(len(self.rets), 7000)
        voo_days, voo_rets, *_ = tc.daily_legs(self.data, "VOO")
        self.assertLess(len(voo_rets), 4500, "VOO's own record is still a decade and a bit; the file must say so")
        self.assertGreater(voo_days[0].year, 2009)


class ThereIsNoLookahead(unittest.TestCase):
    """Everything else in the file is downstream of the shift, so the shift gets its own arithmetic."""

    def test_a_signal_computed_at_the_close_cannot_earn_the_return_of_that_same_day(self):
        """Three days by hand. The rule is 'get in tomorrow' — exposure 0, then 1 — so the path must earn day 3's
        return and nothing else. If `expo[i]` were applied to `rets[i]`, this would earn day 2 instead, and the two
        answers differ by a factor of eleven."""

        rets = [0.10, -0.50, 0.60, 0.02]
        bills = [0.0, 0.0, 0.0, 0.0]
        expo = [0.0, 1.0, 1.0, 1.0]
        out = tc.run(rets, bills, expo, 0.0, 1)
        # Day 1 earns nothing (flat, and the entry cost is not yet owed). Day 2's -50% is avoided. The entry cost
        # falls on day 3's factor, where the position is first held, and day 4 is captured clean.
        want = (1.0 + 0.60 - wc.TURNOVER_COST) * (1.0 + 0.02) - 1.0
        self.assertAlmostEqual(out["wealth"] - 1.0, want, places=10,
                               msg="the signal is being applied to the day that produced it")

    def test_the_warm_up_period_holds_cash_rather_than_guessing(self):
        """A 200-day average does not exist on day 1. Treating 'unknown' as 'in' would put the rule into the market
        at the start of every sample for no reason at all."""

        flat = [100.0] * 150
        e = tc.exposures("ma200", flat, [0.0] * 149)
        self.assertEqual(set(e), {0.0})
        rising = [100.0 * (1.01 ** i) for i in range(400)]
        e2 = tc.exposures("ma200", rising, [rising[i] / rising[i - 1] - 1.0 for i in range(1, 400)])
        self.assertEqual(e2[150], 0.0, "still warming up and already in the market")
        self.assertEqual(e2[250], 1.0, "a rising series must eventually be in")

    def test_the_volatility_target_stays_inside_its_own_bounds_and_turns_every_day(self):
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        days, rets, cl, bills, expense = tc.daily_legs(data, "SPY")
        e = tc.exposures("voltarget", cl, rets)
        self.assertTrue(all(0.0 <= x <= 2.0 for x in e), "the target escapes its clip")
        r = tc.run(rets, bills, e, expense, 1)
        self.assertGreater(r["switches"], len(rets) * 0.9,
                           "a daily-rebalanced target that barely trades would mean the signal is dead")
        del days, expense


class TheVerdictsHold(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.days, cls.rets, cls.cl, cls.bills, cls.expense = tc.daily_legs(cls.data, "SPY")
        cls.expo = {r: tc.exposures(r, cls.cl, cls.rets) for r in tc.RULES}
        cls.res = {r: tc.run(cls.rets, cls.bills, cls.expo[r], cls.expense, 1) for r in tc.RULES}

    def test_every_tested_rule_loses_to_plain_buy_and_hold_at_the_posted_cost(self):
        """The objective's hypothesis, scored. Five rules, one archive, 8,457 days, no lookahead, real costs: all
        five lose. If a future change makes one of these win, re-read the note before believing it — two of the
        three times this number moved, the cause was a bug in this file."""

        bh = self.res["hold"]["cagr"]
        for rule in tc.RULES:
            if rule == "hold":
                continue
            self.assertLess(self.res[rule]["cagr"], bh,
                            f"{rule} now beats buy-and-hold: {self.res[rule]['cagr']:.2%} vs {bh:.2%}."
                            " Check the shift, the bill leg and the cost multiplier before the result")

    def test_the_rules_buy_drawdown_reduction_and_nothing_else(self):
        """The one thing the timing family genuinely delivers: MA200 halves the worst drawdown and returns 1.9pp
        less a year. That is what holding bills does, and it can be had for free without a signal."""

        bh, ma = self.res["hold"], self.res["ma200"]
        self.assertLess(ma["max_dd"], bh["max_dd"] * 0.6, "MA200 stopped buying the drawdown; re-check the signal")
        self.assertLess(ma["cagr"], bh["cagr"])
        mp = tc.matched_passive(self.rets, self.bills, ma["mean_expo"], self.expense, 1)
        self.assertLess(ma["cagr"], mp["cagr"] + 0.03,
                        "MA200 now beats a passive sleeve of its own average exposure by an implausible margin")

    def test_cost_multiplier_only_ever_makes_things_worse(self):
        for rule in tc.RULES:
            ladder = [tc.run(self.rets, self.bills, self.expo[rule], self.expense, m)["cagr"]
                      for m in tc.COST_MULTS]
            self.assertEqual(ladder, sorted(ladder, reverse=True), f"{rule}: CAGR rose with costs")
        hold = [tc.run(self.rets, self.bills, self.expo["hold"], self.expense, m)["cagr"] for m in tc.COST_MULTS]
        self.assertLess(abs(hold[0] - hold[-1]), 0.001, "buy-and-hold pays turnover it does not incur")

    def test_the_constant_comparator_is_invariant_to_the_shift_that_moves_every_rule(self):
        """A constant exposure series is shift-invariant, which is why the alignment bug moved the rules and left
        their benchmark exactly where it was."""

        a = tc.matched_passive(self.rets, self.bills, 0.6, self.expense, 1)
        b = tc.run(self.rets, self.bills, [0.6] * len(self.rets), self.expense, 1)
        self.assertAlmostEqual(a["wealth"], b["wealth"], places=12)

    def test_an_undeclared_rule_is_an_error_rather_than_a_quiet_zero(self):
        with self.assertRaises(ValueError):
            tc.exposures("rsi_14_divergence", self.cl, self.rets)

    def test_a_one_day_path_raises_instead_of_returning_a_cagr(self):
        with self.assertRaises(ValueError):
            tc.run([0.01], [0.0], [1.0, 1.0], 0.0, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
