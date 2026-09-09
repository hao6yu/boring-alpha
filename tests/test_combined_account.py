"""Tests for the composed account.

The load-bearing test here is not about the sweep at all, it is the cross-artifact one: this tool's 1.25× stance on
SPY must reproduce `action_ledger.py`'s loan row to the cent. Two files that price the same stance and disagree are
worse than one file that is wrong, because the disagreement is invisible. That requirement comes from r29 and is the
reason `combined_account.py` imports `action_ledger` rather than restating its numbers.

The rest pin the shape of the sweep: it must be monotone in cash, the cash switch must be worth exactly zero at a
fully invested account (it is a multiplication by `(1 - w)`, not a small effect), and any cross-symbol comparison
must be shown to share a window — because in this archive the series start years apart, and a difference measured
across two different samples is a statement about the calendar.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import action_ledger as al                         # noqa: E402
import combined_account as ca                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheComposedAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.rows = ca.sweep_capital(cls.data, 0.0288)
        cls.by_w = {r["weight"]: r for r in cls.rows}

    def test_this_tool_and_the_ledger_price_the_same_loan_the_same_way(self):
        """Cross-artifact consistency. The ledger's constant-leverage row is +27.24/mo on SPY; this file prices
        the identical stance from scratch and must land on it, or the two files describe different accounts."""

        loan = [a for a in al.ACTIONS if "1.25x" in a[0]][0]
        mine = ca.legs(self.data, 1.25, ca.DEFAULT_SWEEP, symbol="SPY")
        self.assertAlmostEqual(mine["mo"], loan[2], places=2,
                               msg="combined_account and action_ledger no longer agree on the same stance")

    def test_holding_cash_always_loses_to_the_benchmark_and_gets_worse_monotonically(self):
        """The sweep's headline. If a middling cash weight ever beat full investment, the 'borrow or don't'
        conclusion would need re-reading, so monotonicity is pinned rather than observed once."""

        downs = [self.by_w[w]["switched"]["excess"] for w in (0.0, 0.25, 0.50, 0.75, 0.90)]
        for a, b in zip(downs, downs[1:]):
            self.assertLess(a, b)
        self.assertLess(downs[-1], 0.0)
        self.assertGreater(downs[0], -0.20, "all cash should cost roughly the equity risk premium, not more")

    def test_the_cash_switch_is_exactly_worthless_at_a_fully_invested_account(self):
        """Not 'small' — exactly zero, because the engine multiplies the cash leg by `(1 - w)`. This is the whole
        reason the ledger's top row and its loan row cannot be added together."""

        full = ca.legs(self.data, 1.0, 0.0288)
        base = ca.legs(self.data, 1.0, ca.DEFAULT_SWEEP)
        self.assertAlmostEqual(full["excess"], base["excess"], places=12)

    def test_the_switch_gets_worth_more_the_more_cash_is_held_proving_the_rows_have_opposite_owners(self):
        # `switch_value` is in the engine's annualised-percent units; convert to dollars exactly as the tool
        # prints it. The first draft of this test compared that quantity straight against a dollar threshold.
        dollars = {r["weight"]: r["switch_value"] / 1200.0 * 20_000.0 for r in self.rows if r["weight"] <= 1.0}
        seq = [dollars[w] for w in (0.0, 0.25, 0.50, 0.75, 0.90, 1.0)]
        for a, b in zip(seq, seq[1:]):
            self.assertGreater(a, b, "less idle money must make the switch worth less")
        self.assertGreater(seq[0], 40.0, "at all-cash the switch should be the ledger's headline figure")
        self.assertAlmostEqual(seq[-1], 0.0, places=6)

    def test_only_leverage_beats_the_index(self):
        winners = [r for r in self.rows if r["switched"]["excess"] > 0]
        self.assertTrue(winners)
        for r in winners:
            self.assertGreater(r["weight"], 1.0, f"{r['weight']}x beat the index without borrowing; re-examine")


class ComparisonsMustShareAWindow(unittest.TestCase):
    """Round 38's closing claim — that ~0.79%/yr of the loan's edge is "which fund the tool named" — was measured
    by differencing SPY over 404 months against VOO over 192. That is a decade test wearing a fund test's clothes,
    and the test that pinned it passed, because it was comparing unequal samples and calling the difference a
    choice. These tests assert the corrected version: on a shared window two index funds must agree to *within*
    their fee gap, and the era they cover must be what moves the number."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.n = ca.common_months(cls.data)
        cls.spy_c = ca.legs(cls.data, 1.25, ca.DEFAULT_SWEEP, symbol="SPY", last=cls.n)
        cls.voo_c = ca.legs(cls.data, 1.25, ca.DEFAULT_SWEEP, symbol="VOO", last=cls.n)
        cls.spy_full = ca.legs(cls.data, 1.25, ca.DEFAULT_SWEEP, symbol="SPY")

    def test_the_archive_does_not_hand_every_symbol_the_same_window(self):
        """The precondition for the whole class. If the series are ever aligned upstream this must fail loudly,
        rather than let the old conclusion quietly become true again."""

        self.assertEqual(self.spy_full["months"], 404)
        self.assertEqual(self.voo_c["months"], self.n)
        self.assertLess(self.n, self.spy_full["months"] - 100)

    def test_on_a_shared_window_two_funds_on_one_index_agree_tighter_than_their_fee_gap(self):
        """The corrected claim, and the opposite of the one round 38 pinned. 0.024% measured against a 0.065%
        fee gap: two funds tracking one index cannot be allowed to differ by more than the fee that separates
        them, and they don't."""

        gap = abs(self.voo_c["excess"] - self.spy_c["excess"])
        fee = wc.EXPENSE["SPY"] - wc.EXPENSE["VOO"]
        self.assertLess(gap, fee, "two funds on one index must not diverge beyond the fee separating them")
        self.assertLess(gap, 0.001)

    def test_the_sample_period_moves_the_edge_by_more_than_anything_a_fund_choice_can_do(self):
        """One policy, one fund, two windows: the era is worth ~0.83%/yr, about half the edge. This caveat belongs
        on every excess figure in the project, not on a fund-selection footnote."""

        era = abs(self.spy_c["excess"] - self.spy_full["excess"])
        self.assertGreater(era, 0.005)
        self.assertGreater(era, abs(self.spy_full["excess"]) / 2.5)
        self.assertGreater(self.spy_c["excess"], self.spy_full["excess"],
                           "the recent window should flatter a levered equity policy")

    def test_common_months_reports_the_shortest_series_not_the_longest(self):
        """The guard against a future author comparing unequal windows by accident."""

        self.assertEqual(self.n, min(404, 192))
        self.assertLess(ca.common_months(self.data, ("SPY", "QQQ")), self.spy_full["months"])

class TheMeanIsNotTheExperience(unittest.TestCase):
    """Round 40. The goal says "earn extra each month", and every figure this project has ever printed for the
    loan is an annualised mean. This class prices the shape instead, because the shape is what disqualifies the
    plan as income even though the mean clears the bar."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.keys, cls.edge = ca.monthly_edge(cls.data, 1.25, ca.DEFAULT_SWEEP, symbol="SPY")
        cls.st = ca.streaks(cls.edge, cls.keys)

    def test_the_monthly_series_reconciles_with_the_annualised_row(self):
        mean = self.st["mean_month"]
        loan = [a for a in al.ACTIONS if "1.25x" in a[0]][0]
        # Tolerance is one dollar a year, not less: the ledger stores its row rounded to cents, and the
        # unrounded figure differs by exactly that rounding (measured gap $0.0514/yr).
        self.assertAlmostEqual(mean * 12 * al.BASE_CAPITAL, loan[2] * 12, delta=1.0,
                               msg="the monthly shape and the yearly row must describe one account")

    def test_the_loan_is_negative_in_more_than_a_third_of_its_months(self):
        """The finding. A plan that pays on average and loses in two of five months is not a monthly income."""

        self.assertGreater(self.st["share_negative"], 0.33)
        self.assertLess(self.st["mean_month"], 0.002, "and the average month is small enough that the variance dominates it")

    def test_its_worst_single_month_costs_more_than_a_year_of_its_average_pay(self):
        pay = self.st["mean_month"] * 12
        self.assertLess(self.st["worst_month"] / pay, -2.0, "measured: -4.23% vs +1.63%/yr")
        self.assertGreaterEqual(self.st["worst_streak"], 4)

    def test_the_excess_itself_has_a_drawdown_and_it_spans_the_2000s(self):
        """A levered account can be behind plain holding for nine years while the market does its own damage
        separately. The nine years is the point: it is 2000-04 to 2009-02, so the holder sits through dot-com and
        the financial crisis in the same single hole, and a plan whose mean is quoted without this sentence is
        quoting the part that flatters it."""

        self.assertLess(self.st["cum_trough"], -0.15)
        self.assertEqual(self.st["trough_years"], 9)
        self.assertEqual(self.st["trough_from"].year, 2000)
        self.assertEqual(self.st["trough_to"].year, 2009)

    def test_the_rolling_hit_rate_worsens_at_five_years_and_repairs_by_ten(self):
        """The counter-intuitive part: five-year windows have the lowest hit rate of any horizon, because they are
        the ones that straddle 2000-03 and 2008. Time does repair it — but only by a decade."""

        w = {y: ca.rolling_edge(self.edge, y) for y in (1, 3, 5, 10)}
        hit = {y: sum(1 for x in v if x > 0) / len(v) for y, v in w.items()}
        self.assertLess(hit[5], hit[10])
        self.assertLess(hit[5], 0.75)
        self.assertLess(min(w[1]), -0.10, "there exists a year in which the loan cost 10%+ versus doing nothing")
        self.assertGreater(min(w[10]), min(w[1]), "longer windows must be kinder, or the metric is wrong")

    def test_the_streak_function_returns_nothing_for_a_series_that_never_goes_backwards(self):
        """Control: the function must be able to report an untroubled plan, or its alarms mean nothing."""

        s = ca.streaks([0.01] * 40)
        self.assertEqual(s["worst_streak"], 0)
        self.assertEqual(s["share_negative"], 0.0)
        self.assertEqual(s["cum_trough"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
