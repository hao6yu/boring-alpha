"""Round 57: the frequency axis, which is the one thing the objective actually specifies.

The finding worth defending is that neither family prefers the short term, and the reason differs by family: for
MA200 the information is frequency-independent and only the bill grows, while for momentum the information itself
degrades when it is read daily. Both are asserted below, separately, because a test that only checks "faster costs
money" would pass on a broken signal engine.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import frequency_cost as fc                              # noqa: E402
import rotation_edge as re_                              # noqa: E402
import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class Panel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.ordered, cls.rets, cls.bills, cls.expense = re_.panel(cls.data)
        pos = {d: i for i, d in enumerate(tc.days_of(cls.data, "SPY"))}
        cl = tc.closes_of(cls.data, "SPY")
        cls.closes = {"SPY": [cl[pos[d]] for d in cls.ordered]}
        cls.n = len(cls.ordered)
        cls.spy = re_.run_weights(cls.ordered, cls.rets, cls.bills, cls.expense,
                                  re_.constant_weights("SPY", cls.n))

    def weights(self, family, freq):
        return fc.weights_for_family(family, self.ordered, self.rets, self.bills, self.expense,
                                     self.closes, freq, re_.UNKNOWN_ER)

    def row(self, family, freq, mult=1):
        return re_.run_weights(self.ordered, self.rets, self.bills, self.expense, self.weights(family, freq), mult)


class TheSignalCalendarIsWhatItSays(Panel):

    def test_the_frequencies_nest_in_the_order_the_names_claim(self):
        sets = {f: set(fc.signal_days(self.ordered, f)) for f in fc.FREQS}
        self.assertTrue(sets["annual"] <= sets["quarterly"] <= sets["monthly"], "calendar frequencies do not nest")
        self.assertTrue(sets["biweekly"] <= sets["weekly"] <= sets["daily"], "sub-monthly frequencies do not nest")
        self.assertLess(len(sets["annual"]), len(sets["quarterly"]))
        self.assertLess(len(sets["quarterly"]), len(sets["monthly"]))
        self.assertLess(len(sets["weekly"]), len(sets["daily"]))

    def test_the_sub_monthly_counts_are_arithmetic_not_accidental(self):
        """Weekly and biweekly are counted in trading days from warm-up, so their sizes are arithmetic. If these
        ever move, someone swapped in a calendar rule and the sweep is measuring an accident instead of a rate."""

        # The last day of the panel is never a decision day: there is no next day's return to apply it to.
        self.assertEqual(len(fc.signal_days(self.ordered, "daily")), self.n - fc.WARMUP - 1)
        self.assertEqual(len(fc.signal_days(self.ordered, "weekly")), (self.n - 2 - fc.WARMUP) // 5 + 1)
        self.assertEqual(len(fc.signal_days(self.ordered, "biweekly")), (self.n - 2 - fc.WARMUP) // 10 + 1)

    def test_an_undeclared_frequency_is_an_error_rather_than_the_slowest_row(self):
        with self.assertRaises(ValueError):
            fc.signal_days(self.ordered, "on-the-hour")
        with self.assertRaises(ValueError):
            fc.weights_for_family("rsi_divergence", self.ordered, self.rets, self.bills, self.expense,
                                  self.closes, "daily", re_.UNKNOWN_ER)

    def test_the_average_waits_for_its_window_rather_than_padding_it(self):
        series = [float(i + 1) for i in range(300)]
        self.assertIsNone(fc.sma(series, 200, 198), "a 200-day average exists on day 199")
        self.assertAlmostEqual(fc.sma(series, 200, 199), sum(range(1, 201)) / 200, places=12)
        self.assertAlmostEqual(fc.sma(series, 200, 250), sum(range(52, 252)) / 200, places=12)

    def test_every_family_holds_cash_until_its_first_signal_at_every_frequency(self):
        for family in fc.FAMILIES:
            for freq in fc.FREQS:
                w = self.weights(family, freq)
                first = fc.signal_days(self.ordered, freq)[0]
                self.assertEqual(set(w[:first]), {tuple(0.0 for _ in re_.UNIVERSE)},
                                 f"{family} at {freq} was invested before its first signal")


class FasterIsNotBetter(Panel):

    def test_ma200_gross_is_flat_across_the_whole_axis_so_only_the_bill_moves(self):
        gross = [self.row("ma200", f, 0)["cagr"] for f in fc.FREQS]
        self.assertLess(max(gross) - min(gross), 0.015,
                        f"the MA200 answer swung {(max(gross) - min(gross)) * 100:.2f}pp on frequency alone:"
                        " the signal engine changed shape, it did not get smarter")

    def test_momentum_information_itself_degrades_when_it_is_read_daily(self):
        """Not just the cost of trading it: reading a 12-month ranking every day makes the ranking worse. Gross, so
        no invoice is doing this work."""
        self.assertGreater(self.row("mom_top1", "monthly", 0)["cagr"] - self.row("mom_top1", "daily", 0)["cagr"],
                           0.02, "daily momentum is no longer worse GROSS; the sweep is not measuring what it claims")

    def test_both_families_peak_at_the_slow_end_of_the_axis(self):
        for family in fc.FAMILIES:
            net = {f: self.row(family, f, 1)["cagr"] for f in fc.FREQS}
            self.assertEqual(max(net, key=net.get), "monthly",
                             f"{family} now prefers {max(net, key=net.get)}: best is {max(net.values()):.2%}")

    def test_going_from_best_to_daily_costs_more_than_a_third_of_a_point_and_up_to_three_and_a_half(self):
        for family, floor in (("ma200", 0.004), ("mom_top1", 0.02)):
            best = max(fc.FREQS, key=lambda f: self.row(family, f, 1)["cagr"])
            price = self.row(family, best, 1)["cagr"] - self.row(family, "daily", 1)["cagr"]
            self.assertGreater(price, floor, f"{family}: the short term cost only {price * 100:.2f}pp")

    def test_faster_momentum_is_worse_on_return_and_on_risk_at_the_same_time(self):
        m, d = self.row("mom_top1", "monthly"), self.row("mom_top1", "daily")
        self.assertLess(d["cagr"], m["cagr"])
        self.assertGreater(d["max_dd"], m["max_dd"], "daily momentum improved the drawdown; the axis may be real")

    def test_costs_are_linear_and_only_ever_take(self):
        for family in fc.FAMILIES:
            for freq in ("monthly", "daily"):
                g, one, four = (self.row(family, freq, m) for m in (0, 1, 4))
                self.assertGreaterEqual(g["cagr"], one["cagr"], f"{family} {freq}: trading costs paid you")
                self.assertGreaterEqual(one["cagr"], four["cagr"])
                self.assertAlmostEqual(four["cost_drag"], one["cost_drag"] * 4, places=10,
                                       msg="turnover cost is not linear in the multiplier")

    def test_neither_family_beats_holding_spy_at_any_frequency_on_the_posted_cost(self):
        for family in fc.FAMILIES:
            for freq in fc.FREQS:
                r = self.row(family, freq, 1)
                self.assertLess(r["cagr"], self.spy["cagr"],
                                f"{family} at {freq} beat SPY ({r['cagr']:.2%} vs {self.spy['cagr']:.2%})")

    def test_daily_momentum_at_four_times_slippage_is_the_objectives_hypothesis_in_one_number(self):
        r = self.row("mom_top1", "daily", 4)
        self.assertLess(r["cagr"], 0.06, f"daily momentum at 4x now makes {r['cagr']:.2%}")
        self.assertLess(r["cagr"], self.spy["cagr"] - 0.05,
                        "it is no longer five points behind doing nothing; re-read the note")


if __name__ == "__main__":
    unittest.main(verbosity=2)
