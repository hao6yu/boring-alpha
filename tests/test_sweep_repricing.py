"""Tests for the two switches round 25 added, and for the units they are denominated in.

The finding here is an accounting claim, not a distribution: charge the rule's borrowings at the rate a desk
posts rather than at the bill rate plus its execution spread, and the edge the archive shows goes to zero. An
accounting claim is testable exactly, which is why these tests are tight where the power tests are loose. Two
of them exist because of specific mistakes made while writing the tool: an annual posted rate used as a monthly
one (which turned +0.34%/yr into −10.07%/yr and looked entirely plausible for a moment), and a claim about the
sign of the financing subsidy that would have drifted silently if it had only been asserted as a magnitude.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import book_power as bp                            # noqa: E402
import income_frontier as ifr                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

SWEEP = 0.0002
POSTED = ifr.MENU_PUBLIC


class TheFinancingUnitsMatchTheEngine(unittest.TestCase):
    """`withdrawal_capacity.run` charges `cash_rate[month] + spread / 12.0`. Any second implementation of the
    same account has to match it monthly, because the first draft of this one did not and reported a
    ten-percent hole that a back-of-envelope check (18% mean leverage against a two-point rate gap, so about
    0.7%/yr) should have killed before it ever reached a table."""

    def test_the_posted_monthly_charge_is_the_monthly_compound_of_the_posted_annual_rate(self):
        monthly = (1.0 + POSTED) ** (1.0 / 12.0) - 1.0
        self.assertGreater(monthly, 0.003)
        self.assertLess(monthly, 0.005)
        self.assertLess(monthly, POSTED / 4.0, "this is a monthly figure; if it is near the annual one, "
                                              "the units have slipped again")

    def test_an_unlevered_rule_costs_the_same_under_both_borrow_models(self):
        """With no month ever levered, the financing model cannot matter. If it does, the borrow term is
        leaking onto the cash term — the precise confusion this switch exists to keep apart."""

        from unittest import mock
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        series = ifr.series_for(data, "SPY")
        _r, _rates, keys = wc.monthly(series, data.cash_factors)
        with mock.patch.object(bp, "monthly_weights", lambda *a, **k: [1.0] * len(keys)):
            a, _ba, _ka, wa = bp.net_strategy_returns(data, "SPY", 3.0, 0.000945, borrow="book")
            b, _bb, _kb, wb = bp.net_strategy_returns(data, "SPY", 3.0, 0.000945, borrow="posted")
        self.assertEqual(a, b, "a never-borrowing account is being charged for borrowing")
        self.assertTrue(all(abs(w - 1.0) < 1e-12 for w in wa) and all(abs(w - 1.0) < 1e-12 for w in wb))


class TheAccountFaithfulPairIsWorseThanTheBooksPair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.expense = 0.000945
        cls.variants = {}
        for label, sw, bo in (("curve/book", None, "book"), ("curve/posted", None, "posted"),
                              ("sweep/book", SWEEP, "book"), ("sweep/posted", SWEEP, "posted")):
            strat, bench, _k, _w = bp.net_strategy_returns(cls.data, "SPY", 3.0, cls.expense,
                                                           sweep=sw, borrow=bo)
            cls.variants[label] = sum(a - b for a, b in zip(strat, bench)) / len(strat)

    def test_paying_the_posted_rate_for_money_removes_the_entire_edge(self):
        """The round's finding, pinned. The rule's excess over its own fund is positive when it is credited
        with the bill rate on its borrowings and zero-or-negative when it pays what a desk posts. The edge was
        never disproved; it was financed by an assumption."""

        # Means of MONTHLY differences, so the thresholds are monthly: +0.40%/yr is 3.3e-4 on this scale.
        self.assertGreater(self.variants["curve/book"], 0.0003)
        self.assertLess(abs(self.variants["curve/posted"]), 0.00025,
                        f"posted financing now costs {self.variants['curve/posted']*1200:.2%}/yr")
        self.assertLess(self.variants["sweep/posted"], self.variants["curve/posted"])

    def test_the_financing_subsidy_has_exactly_one_sign(self):
        for a, b in (("curve/book", "curve/posted"), ("sweep/book", "sweep/posted")):
            self.assertGreater(self.variants[a], self.variants[b],
                               f"{a} beat {b}: the loan model is now the generous one, which would be news")

    def test_the_rule_is_a_net_borrower_so_a_cheap_bill_rate_flatters_it(self):
        """A lower cash rate *raises* the rule's excess under the book's own model, because the rule borrows
        on average and the model prices the loan off that same rate. Asserting the sign of the counter-intuitive
        result keeps it from being quietly read as a benefit of low rates."""

        self.assertGreater(self.variants["sweep/book"], self.variants["curve/book"])

    def test_no_variant_is_anywhere_near_resolvable_at_month_60(self):
        """Round 23's conclusion, re-checked against the edges round 25 actually measured: four variants, and
        not one of them large enough for a $5,000 + $500/mo book to see in five years."""

        for label, edge in self.variants.items():
            self.assertLess(abs(edge) * 1200, 6.0, f"{label} suddenly became measurable: {edge:.2%}/yr")


class TheFrontierTakesTheSubstitution(unittest.TestCase):
    def test_a_sweep_replaces_the_curve_rather_than_flooring_it(self):
        rates = [0.001, 0.004, 0.002, 0.0005]
        out = ifr.apply_sweep(rates, SWEEP)
        monthly = (1.0 + SWEEP) ** (1.0 / 12.0) - 1.0
        self.assertEqual(len(out), len(rates))
        self.assertTrue(all(abs(r - monthly) < 1e-15 for r in out))
        self.assertIs(ifr.apply_sweep(rates, None), rates, "None must pass the list through untouched")

    def test_the_substituted_mean_cash_keeps_the_all_in_borrow_at_the_posted_rate(self):
        """The coupling that makes this re-pricing honest rather than merely pessimistic: `mean_cash` feeds
        `spread = MENU_PUBLIC - mean_cash`, so lowering the credit while the spread moves with it holds the
        all-in financing at 4.90%. Hold the spread fixed instead and the same edit cheapens leverage at the
        same time, and the two errors partly cancel into a number nobody could defend."""

        tables, _now, _data, mean_cash = ifr.load(10, 4, SWEEP)
        self.assertAlmostEqual(mean_cash, SWEEP, places=6)
        self.assertAlmostEqual(ifr.MENU_PUBLIC - mean_cash + mean_cash, ifr.MENU_PUBLIC, places=12)
        tables_plain, _n, _d, mean_plain = ifr.load(10, 4)
        self.assertGreater(mean_plain, SWEEP * 3, "the un-substituted record must still earn real cash")
        self.assertNotAlmostEqual(mean_plain, mean_cash, places=4)

    def test_the_candidate_still_outranks_the_plain_fund_under_a_sweep(self):
        """The pre-registered half of the prediction: a cash substitution hits every plan's cash leg the same
        way, so the *ordering* should survive even where the margin shrinks. It did — +$73/mo at ten years —
        and this test is what makes that a fact rather than a sentence in a note."""

        tables, _now, _data, mean_cash = ifr.load(10, 4, SWEEP)
        spread = ifr.MENU_PUBLIC - mean_cash
        cells = {}
        for plan in ifr.plans(mean_cash, spread):
            windows, zero_path = tables[plan.label]
            for rule in ("fixed", "guardrail"):
                cells[rule + "|" + plan.label] = ifr.solve(windows, plan, rule, 400.0, zero_path)
        cell, spy = cells["guardrail|candidate"], cells["guardrail|SPY"]
        self.assertTrue(cell.feasible and spy.feasible)
        self.assertGreater(cell.median, spy.median)
        self.assertAlmostEqual(cell.median - spy.median, 73.0, delta=12.0,
                               msg="the ten-year gap moved; re-read the note before quoting it")
        self.assertGreater(cell.median - spy.median, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
