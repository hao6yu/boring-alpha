"""Round 52: a withdrawal plan is a path, so the safety statistic has to be simulated, not averaged.

Test 1 is the reason the tool exists. Everything after it checks that the simulation is honest.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import plan_survival as ps                               # noqa: E402
import required_edge as re_                              # noqa: E402
import income_accounting as ia                           # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class OrderIsNotCosmetic(unittest.TestCase):
    """If two windows with the same compound return produce the same ending, this file's premise is wrong and the
    tool is unnecessary. They do not."""

    def test_two_paths_with_the_same_cagr_end_differently_once_money_leaves(self):
        front = [0.30, -0.50]
        back = [-0.50, 0.30]
        cagr_f = (1.30 * 0.50) ** 6 - 1.0
        cagr_b = (0.50 * 1.30) ** 6 - 1.0
        self.assertAlmostEqual(cagr_f, cagr_b, places=15, msg="the pair must have identical compound returns")
        a = ps.simulate(front, 50_000.0, 2_000.0, 0.0, 0.0)
        b = ps.simulate(back, 50_000.0, 2_000.0, 0.0, 0.0)
        self.assertGreater(a["terminal"], b["terminal"],
                           f"same CAGR, same plan, no ordering effect: {a['terminal']} vs {b['terminal']}")
        self.assertGreater(a["terminal"] - b["terminal"], 500.0,
                           "the effect is real but negligible; re-check the pair before citing it")

    def test_a_liquidated_window_is_failed_even_if_it_ends_whole(self):
        """A plan that dips to −$4,000 in month 30 and recovers to +$60,000 was closed by the broker in month 30."""

        path = [0.10, -0.995, 0.90, 0.90, 0.90, 0.90]
        out = ps.simulate(path, 10_000.0, 1_000.0, 0.0, 0.0)
        self.assertTrue(out["destroyed"])
        self.assertFalse(out["survived"])
        self.assertEqual(out["trough"], 0.0, "a destroyed run reports its trough at zero, not at the dip")


class TheSimulationIsArithmetic(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_with_no_withdrawals_and_no_costs_the_run_is_buy_and_hold(self):
        path = [0.01, -0.02, 0.03, 0.005]
        want = 50_000.0
        for r in path:
            want *= 1.0 + r
        out = ps.simulate(path, 50_000.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(out["terminal"], want, places=8)
        self.assertTrue(out["survived"])

    def test_matching_contribution_and_withdrawal_leaves_the_balance_flat_at_zero_return(self):
        out = ps.simulate([0.0] * 60, 40_000.0, 500.0, 500.0, 0.0)
        self.assertAlmostEqual(out["terminal"], 40_000.0, places=8)

    def test_the_expense_is_charged_every_month_and_only_every_month(self):
        """Exact identity at zero return: ten years of a monthly expense charge is (1 − er/12)^120 of the account.
        My first draft of this test predicted one year's fee and measured ten years of compounding, and failed at
        $1,702 against an expectation of $94 — the same error a spreadsheet makes in the other direction."""

        costly = ps.simulate([0.0] * 120, 100_000.0, 0.0, 0.0, wc.EXPENSE["SPY"] / 12.0)["terminal"]
        self.assertAlmostEqual(costly, 100_000.0 * (1.0 - wc.EXPENSE["SPY"] / 12.0) ** 120, places=6)
        self.assertLess(costly, 100_000.0 * (1.0 - 2.0 * wc.EXPENSE["SPY"]))

    def test_the_window_count_agrees_with_the_other_tool_that_counts_windows(self):
        """Two tools now slice the same record into windows. They must agree, or one of them has a different
        definition of a window and every number in both files is unanchored."""

        for sym, years in (("SPY", 10), ("QQQ", 10), ("SPY", 20)):
            self.assertEqual(len(ps.windows(self.data, sym, years)),
                             re_.rolling_cagr(self.data, sym, years)["n"], f"{sym} {years}y")


class TheProbabilityBehaves(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_failure_probability_falls_as_capital_rises_and_rises_as_the_target_rises(self):
        small = ps.survival(self.data, "SPY", 50_000.0, 500.0, 10)["p_fail"]
        mid = ps.survival(self.data, "SPY", 100_000.0, 500.0, 10)["p_fail"]
        big = ps.survival(self.data, "SPY", 250_000.0, 500.0, 10)["p_fail"]
        self.assertGreaterEqual(small, mid)
        self.assertGreaterEqual(mid, big)
        self.assertGreater(small, big, "capital must buy something here or the simulation is dead")
        hungrier = ps.survival(self.data, "SPY", 100_000.0, 2_000.0, 10)["p_fail"]
        self.assertGreater(hungrier, mid)

    def test_the_bisection_is_monotone_in_its_failure_budget(self):
        caps = [ps.capital_for(self.data, "SPY", 500.0, 20, b) for b in (0.10, 0.05, 0.0)]
        self.assertEqual(caps, sorted(caps), f"failure budgets out of order: {caps}")
        self.assertLess(caps[0], caps[2])

    def test_an_untested_plan_is_never_reported_as_failed(self):
        """VOO has 192 complete months: a 20-year plan on VOO has no sample at all."""

        s = ps.survival(self.data, "VOO", 100_000.0, 500.0, 20)
        self.assertEqual(s["n"], 0)
        self.assertIsNone(s["p_fail"], "an empty sample read as a failure would put VOO beside SPY's impossibility")
        self.assertIsNone(ps.capital_for(self.data, "VOO", 500.0, 20, 0.0))

    def test_no_amount_of_money_buys_certainty_on_spy_ten_years(self):
        """In the worst window the index itself finished below where it started, so a level withdrawal plan cannot
        finish there either, at $500m or $5bn. The only way to that floor is a different asset."""

        self.assertIsNone(ps.capital_for(self.data, "VOO", 500.0, 20, 0.0))
        self.assertTrue(
            ps.capital_for(self.data, "SPY", 500.0, 10, 0.0) is None
            or ps.capital_for(self.data, "SPY", 500.0, 10, 0.0) > 1e11,
            "SPY's 10-year certainty became purchasable; re-read the worst window before celebrating")

    def test_the_two_samples_disagree_at_the_same_plan_by_a_wide_margin(self):
        voo = ps.survival(self.data, "VOO", 50_000.0, 500.0, 10)["p_fail"]
        spy = ps.survival(self.data, "SPY", 50_000.0, 500.0, 10)["p_fail"]
        self.assertLess(voo, spy, "the friendlier sample stopped being friendlier")
        self.assertGreater(spy - voo, 0.20, f"the gap is only {spy - voo:.0%}; re-state the benchmark warning")


class AgainstTheGuaranteeEngine(unittest.TestCase):
    """Round 50's guarantee and this tool price the same promise with different code. They must be consistent in
    *direction*: this tool demands more (never liquidated AND ends whole) than `capacity` does (never liquidated),
    so its zero-failure capital must sit above the guarantee's implied capital — and the gap is exactly the price of
    the extra promise, which is worth knowing."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_two_engines_agree_on_the_order_of_magnitude_and_the_direction_of_the_gap(self):
        cheque = ia.guarantee("SPY", 1.00, 100_000.0, 20, self.data, 1)["cheque"]
        annual = cheque / 100_000.0 * 12.0          # $/mo per $1 of capital, times 12, is an annual rate
        guarantee_capital = 500.0 * 12.0 / annual
        mine = ps.capital_for(self.data, "SPY", 500.0, 20, 0.0)
        self.assertGreater(mine, guarantee_capital,
                           f"the stricter promise got cheaper: {mine:,.0f} vs {guarantee_capital:,.0f}")
        ratio = mine / guarantee_capital
        self.assertLess(ratio, 1.8, f"the engines drifted {ratio:.2f}x apart; reconcile before citing either")
        self.assertGreater(ratio, 1.10, "the stricter promise is free, which cannot be right")

    def test_the_guarantee_number_itself_has_not_moved(self):
        self.assertAlmostEqual(ia.guarantee("SPY", 1.00, 100_000.0, 20, self.data, 1)["cheque"], 364.45, delta=0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
