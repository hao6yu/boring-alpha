"""Round 56: cross-sectional rotation, priced against the bar the objective names — and against a control that
thinks nothing at all.

Test 1 is the reason to trust the rest. The ranking compared a growth FACTOR to a net RETURN: monotone, so every
headline number stayed right, but the comparison that mattered was between 0.63 and 0.01, and the absolute-momentum
overlay never once fired across a window containing 2008. An overlay that never fires is not evidence of safety.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import rotation_edge as re_                              # noqa: E402
import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


def loaded():
    return load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)


class ThePanelIsTheArchive(unittest.TestCase):
    """Everything downstream is only as good as the alignment of ten series that start on ten different days."""

    @classmethod
    def setUpClass(cls):
        cls.data = loaded()
        cls.ordered, cls.rets, cls.bills, cls.expense = re_.panel(cls.data)

    def test_every_sleeves_daily_return_matches_its_own_closes_on_its_own_calendar(self):
        for s in re_.UNIVERSE:
            cl = tc.closes_of(self.data, s)
            dy = tc.days_of(self.data, s)
            pos = {d: i for i, d in enumerate(dy)}
            for i in (10, 500, 2000, len(self.ordered) - 1):
                j = pos[self.ordered[i]]
                want = cl[j] / cl[j - 1] - 1.0
                self.assertAlmostEqual(self.rets[s][i], want, places=12,
                                       msg=f"{s} at day {i}: the panel is not the archive")

    def test_the_common_window_never_starts_on_a_sleeves_first_day(self):
        """`index - 1` on day zero is not a missing value; it is the last element of the list, and a silently
        wrapped index would manufacture a return out of the whole series."""

        for s in re_.UNIVERSE:
            pos = {d: i for i, d in enumerate(tc.days_of(self.data, s))}
            self.assertGreaterEqual(pos[self.ordered[0]], 1, f"{s} starts the window with a wrapped index")
        self.assertEqual(str(self.ordered[0])[:4], "2006", "the thinnest sleeve is DBC; the window moved without"
                         " anyone deciding it should")

    def test_the_off_risk_leg_is_the_same_daily_factor_the_rest_of_the_repository_uses(self):
        mean = sum(self.bills) / len(self.bills)
        self.assertGreater(mean, 0.0)
        self.assertLess(mean * 252.0, 0.08, f"the bill leg pays {mean * 252:.1%} a year annualised")
        self.assertEqual(len(self.bills), len(self.ordered))


class ThereIsNoLookahead(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = loaded()
        cls.ordered, cls.rets, cls.bills, cls.expense = re_.panel(cls.data)
        cls.w = re_.weights_for("rs_top1", cls.ordered, cls.rets, cls.bills)

    def test_the_decision_day_is_still_earning_what_it_held_before_the_decision(self):
        """A single-day run over the signal day must earn exactly the bill factor — nothing else. On 2007-02-28 the
        rule's brand-new position would have earned SPY +1.03%; the applied weight is the PREVIOUS one, all cash, so
        the run earns 0.0199% and not 1.03%. If the shift were ever removed this assertion fails by 80bp on one day,
        and a rule's whole edge in this family lives inside one-day errors."""

        ends = sorted(re_.month_end_indices(self.ordered))
        first = next(i for i in ends if i >= re_.LOOKBACK)
        self.assertEqual(self.w[first - 1], tuple(0.0 for _ in re_.UNIVERSE), "warm-up was not all-cash")
        self.assertNotEqual(self.w[first], tuple(0.0 for _ in re_.UNIVERSE), "no decision was taken at that close")
        one = re_.run_weights(self.ordered, self.rets, self.bills, self.expense, self.w, keep=[first])
        self.assertAlmostEqual(one["wealth"], 1.0 + self.bills[first], places=12,
                               msg="the decision traded the day that produced it")
        self.assertGreater(abs(self.rets["SPY"][first]), 0.005,
                           "the signal day was too quiet for this test to detect anything")
        self.assertEqual(self.w[first + 1], self.w[first], "a monthly rule traded within the month")
        self.assertEqual(self.w[first + 2], self.w[first], "a monthly rule traded within the month")

    def test_the_signal_count_is_what_the_window_implies(self):
        ends = [i for i in sorted(re_.month_end_indices(self.ordered)) if i >= re_.LOOKBACK]
        self.assertGreater(len(ends), 200)
        self.assertLess(len(ends), 260, f"{len(ends)} signalled month-ends: the window changed shape")


class TheOverlayActuallyFires(unittest.TestCase):
    """The bug this file was written to catch, kept caught."""

    @classmethod
    def setUpClass(cls):
        cls.data = loaded()
        cls.ordered, cls.rets, cls.bills, cls.expense = re_.panel(cls.data)
        cls.dual = re_.weights_for("dual_top1", cls.ordered, cls.rets, cls.bills)
        cls.rs = re_.weights_for("rs_top1", cls.ordered, cls.rets, cls.bills)

    def test_the_absolute_overlay_goes_to_cash_in_the_financial_crisis(self):
        idx = next(i for i, d in enumerate(self.ordered) if str(d) == "2008-12-31")
        ranked = sorted(((re_.compound(self.rets[s][idx - re_.LOOKBACK + 1:idx + 1]) - 1.0, s)
                         for s in re_.CANDIDATES), key=lambda x: (-x[0], x[1]))
        self.assertLess(ranked[0][0], 0.0, "the best risk sleeve in Dec 2008 was up; re-check the panel")
        self.assertEqual(self.dual[idx + 1], tuple(0.0 for _ in re_.UNIVERSE),
                         "dual_top1 stayed invested through Dec 2008: the overlay is comparing a factor to a return")

    def test_the_overlay_fires_more_than_once_and_the_two_rules_are_not_identical(self):
        cash_months = sum(1 for i in range(len(self.dual))
                         if self.dual[i] == tuple(0.0 for _ in re_.UNIVERSE) and i > re_.LOOKBACK + 30)
        self.assertGreater(cash_months, 100, f"only {cash_months} days in cash across twenty years")
        self.assertNotEqual(self.dual[::250], self.rs[::250])

    def test_the_overlay_buys_its_drawdown_with_some_return(self):
        d = re_.run_weights(self.ordered, self.rets, self.bills, self.expense, self.dual)
        r = re_.run_weights(self.ordered, self.rets, self.bills, self.expense, self.rs)
        self.assertLess(d["max_dd"], r["max_dd"] * 0.65, "the overlay stopped cutting the drawdown")
        self.assertLess(d["cagr"], r["cagr"], "the overlay is free, which would make the rest of this file wrong")
        self.assertLess(d["mean_expo"], r["mean_expo"] - 0.05)


class TheVerdictsHold(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = loaded()
        cls.ordered, cls.rets, cls.bills, cls.expense = re_.panel(cls.data)
        cls.n = len(cls.ordered)
        cls.w = {r: re_.weights_for(r, cls.ordered, cls.rets, cls.bills) for r in re_.RULES}
        cls.res = {r: re_.run_weights(cls.ordered, cls.rets, cls.bills, cls.expense, cls.w[r]) for r in re_.RULES}
        cls.spy = re_.run_weights(cls.ordered, cls.rets, cls.bills, cls.expense,
                                  re_.constant_weights("SPY", cls.n))
        o2, r2, b2, e2 = re_.panel(cls.data, 0.0070)
        cls.expensive = {r: re_.run_weights(o2, r2, b2, e2, re_.weights_for(r, o2, r2, b2, 0.0070)) for r in re_.RULES}
        cls.spy2 = re_.run_weights(o2, r2, b2, e2, re_.constant_weights("SPY", len(o2)))

    def test_no_rotation_beats_plain_spy_over_the_common_window(self):
        for r in re_.RULES:
            self.assertLess(self.res[r]["cagr"], self.spy["cagr"],
                            f"{r} now beats holding SPY ({self.res[r]['cagr']:.2%} vs {self.spy['cagr']:.2%}):"
                            " check the units of every comparison before believing it")

    def test_the_expense_assumption_is_not_what_decides_the_answer(self):
        """Both blocks, four rules. The whole conclusion moves by about a tenth of a point per decade when the
        unknown expense doubles, and the ordering of the rules does not move at all."""

        for r in re_.RULES:
            self.assertLess(abs(self.expensive[r]["cagr"] - self.res[r]["cagr"]), 0.0025,
                            f"{r} moved {(self.expensive[r]['cagr'] - self.res[r]['cagr']) * 100:+.2f}pp on the"
                            " assumption alone")
        order_lo = sorted(re_.RULES, key=lambda r: self.res[r]["cagr"])
        order_hi = sorted(re_.RULES, key=lambda r: self.expensive[r]["cagr"])
        self.assertEqual(order_lo, order_hi, "the ranking was the assumption, not the signal")
        for r in re_.RULES:
            self.assertLess(self.expensive[r]["cagr"], self.spy2["cagr"])

    def test_the_control_that_thinks_nothing_is_cheaper_than_everything_that_thinks(self):
        self.assertLess(self.res["static_60_40"]["cost_drag"], self.res["rs_top1"]["cost_drag"])
        self.assertLess(self.res["rs_top1"]["cagr"], self.spy["cagr"])
        self.assertGreater(self.res["rs_top1"]["cagr"], self.res["static_60_40"]["cagr"],
                           "the signal now adds nothing over the asleep control; that is a finding, not a bug")

    def test_costs_only_take(self):
        for mult in (2, 4, 8):
            r = re_.run_weights(self.ordered, self.rets, self.bills, self.expense, self.w["rs_top1"], mult)
            self.assertLess(r["cagr"], self.res["rs_top1"]["cagr"])

    def test_a_sleeve_outside_the_universe_is_an_error_not_an_all_cash_portfolio(self):
        with self.assertRaises(ValueError):
            re_.constant_weights("VOO", self.n)


if __name__ == "__main__":
    unittest.main(verbosity=2)
