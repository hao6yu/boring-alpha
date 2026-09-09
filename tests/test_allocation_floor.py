"""Round 54: the allocation that buys the floor, and the conventions that were hiding its price.

Test 1 is the one that matters. Two implementations of the same promise, sharing no code, disagreeing by 18% until
the inflation convention was matched, and by ~1-3% after.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import allocation_floor as af                            # noqa: E402
import income_accounting as ia                           # noqa: E402
import plan_survival as ps                               # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

CAP, YEARS, SLEEVE = 100_000.0, 20, "SPY"


class TheTwoEnginesReconcile(unittest.TestCase):
    """`capacity` and this file compute the same guarantee with no shared code. They disagreed by 18% on the first
    run — not a bug in either, but the difference between a level cheque and one indexed at the 2.5% that
    `wc.capacity` has always applied. Reconciling the convention came before touching either implementation."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.engine = ia.guarantee(SLEEVE, 1.00, CAP, YEARS, cls.data, 1)["cheque"]
        cls.mine = af.safe_income(cls.data, SLEEVE, CAP, YEARS, 0.0, 0.0, 0.025)

    def test_the_two_implementations_agree_within_three_percent_on_the_matching_convention(self):
        self.assertLess(abs(self.mine - self.engine) / self.engine, 0.03,
                        f"engine ${self.engine:,.2f} vs this file ${self.mine:,.2f}")

    def test_the_disagreement_that_looked_like_a_bug_was_the_convention(self):
        level = af.safe_income(self.data, SLEEVE, CAP, YEARS, 0.0)
        self.assertGreater(abs(level - self.engine) / self.engine, 0.15,
                           "a level cheque now matches the indexed engine; the two conventions have merged and"
                           " one of them has stopped meaning what it says")

    def test_the_convention_is_worth_a_fifth_of_the_headline(self):
        level = af.safe_income(self.data, SLEEVE, CAP, YEARS, 0.0)
        self.assertGreater(level / self.mine, 1.15,
                           f"level ${level:,.0f} vs indexed ${self.mine:,.0f}: re-check which promise is quoted")


class TheCurveIsAnInteriorMaximum(unittest.TestCase):
    """The round's answer to "what buys the floor": bills, and not many of them — then it goes wrong."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.idx = {w: af.safe_income(cls.data, SLEEVE, CAP, YEARS, w, 0.0, 0.025) for w in af.WEIGHTS}
        cls.rows = {w: af.evaluate(cls.data, SLEEVE, CAP, 500.0, YEARS, w) for w in af.WEIGHTS}

    def test_the_safe_cheque_is_an_inverted_u_in_bills_not_a_slope(self):
        peak = max(self.idx.values())
        self.assertGreater(peak, self.idx[0.0], "bills bought no guaranteed income at all")
        self.assertGreater(peak, self.idx[1.0], "the pure-bill corner is not the worst case; re-read the curve")
        best = max(self.idx, key=self.idx.get)
        self.assertTrue(0.0 < best < 1.0, f"the optimum is at the corner {best}, which is not an interior maximum")
        self.assertIn(best, (0.50, 0.65, 0.80))

    def test_bills_alone_are_worse_than_bills_none_at_all(self):
        """The 20-year windows in this archive straddle ZIRP, where the bill leg paid 0.01% for a decade. A plan
        living off T-bills through 2012-2021 fails harder than one living off equities."""

        self.assertLess(self.idx[1.0], self.idx[0.0],
                        f"100% bills ${self.idx[1.0]:,.2f} beat no bills ${self.idx[0.0]:,.2f}")

    def test_liquidation_falls_with_bills_until_the_corner_where_it_worsens(self):
        seq = [self.rows[w]["p_liq"] for w in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.65, 0.80)]
        self.assertEqual(seq, sorted(seq, reverse=True), f"liquidation probability not monotone: {seq}")
        self.assertGreater(self.rows[1.0]["p_liq"], self.rows[0.80]["p_liq"],
                           "the pure-bill kink disappeared; the corner stopped being a warning")

    def test_the_cheque_maximising_allocation_makes_erasure_certain(self):
        best = max(self.idx, key=self.idx.get)
        self.assertEqual(self.rows[best]["p_erase"], 1.0,
                         f"at {best:.0%} bills erasure was not certain; the trade-off has changed shape")
        self.assertEqual(self.rows[best]["p_liq"], 0.0)

    def test_the_median_terminal_falls_strictly_with_every_point_of_bills(self):
        mults = [self.rows[w]["median_mult"] for w in af.WEIGHTS]
        self.assertEqual(mults, sorted(mults, reverse=True), f"terminal multiples out of order: {mults}")
        self.assertLess(mults[-1], 0.10, "the pure-bill corner stopped being a grind to nothing")

    def test_the_worst_trough_never_sits_above_the_worst_ending(self):
        for w in af.WEIGHTS:
            self.assertLessEqual(self.rows[w]["worst_trough"], self.rows[w]["min_mult"] + 1e-9,
                                 f"weight {w}: the trough is above the ending, so one of them is wrong")


class TheArithmeticHolds(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_at_zero_bills_this_engine_reproduces_the_path_simulator_window_for_window(self):
        """Two independent simulators of the same all-equity plan: identical median, identical failure counts. The
        two engines do differ in one documented place — a liquidated account ends at zero here and at its signed
        shortfall in `plan_survival`, which is a severity measure rather than an ending — so the minimum is compared
        by sign and not by value. That difference was found by writing the test, not by reading the code."""

        mine = af.evaluate(self.data, SLEEVE, CAP, 500.0, YEARS, 0.0)
        theirs = ps.survival(self.data, SLEEVE, CAP, 500.0, YEARS)
        self.assertAlmostEqual(mine["median_mult"], theirs["median_terminal"] / CAP, places=9)
        self.assertEqual(round(mine["p_liq"] * mine["n"]), theirs["destroyed"],
                         "the two engines disagree about how many accounts hit zero")
        self.assertEqual(round(mine["p_erase"] * mine["n"]), theirs["n"] - theirs["survived"],
                         "the two engines disagree about how many plans ended poorer than they started")
        self.assertEqual(mine["min_mult"], 0.0, "this engine clamps a liquidated account at zero")
        self.assertLess(theirs["min_terminal"], 0.0, "the other engine reports the signed shortfall")

    def test_at_full_bills_the_equity_leg_cannot_be_heard(self):
        eq_a, eq_b = [0.02] * 60, [-0.05] * 60
        cash = [0.002] * 60
        a = af.simulate_mix(eq_a, cash, CAP, 0.0, 1.0, wc.EXPENSE["SPY"])
        b = af.simulate_mix(eq_b, cash, CAP, 0.0, 1.0, wc.EXPENSE["SPY"])
        self.assertAlmostEqual(a["terminal"], b["terminal"], places=9)

    def test_a_bigger_failure_budget_can_never_cost_less_income(self):
        tight = af.safe_income(self.data, SLEEVE, CAP, YEARS, 0.30, 0.0, 0.025)
        loose = af.safe_income(self.data, SLEEVE, CAP, YEARS, 0.30, 0.05, 0.025)
        self.assertGreaterEqual(loose, tight, "the bisection's monotonicity assumption is false")

    def test_an_untested_sleeve_horizon_reports_no_windows_not_a_zero_probability(self):
        r = af.evaluate(self.data, "VOO", CAP, 500.0, 20, 0.30)
        self.assertEqual(r["n"], 0)
        self.assertIsNone(r["p_liq"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
