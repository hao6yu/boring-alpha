"""Tests for `tools/correction_table.py` — the corrected income figures, and the verdicts that hang off them.

Two of these are load-bearing beyond the file. The first is that the index row on the 2006 panel comes back at $435.47:
that figure is round 58's published payout, which *was* the index's safe withdrawal, so if this table disagrees with it
the table is broken rather than the earlier round. The second is that the correction moves the flagship premium down and
not up, which is the finding and so belongs in a test.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data      # noqa: E402


class TheWeights(unittest.TestCase):
    def setUp(self):
        self.d = [dt.date(2020, 1, x) for x in (2, 3, 6, 7)]

    def test_the_two_static_constructions_ignore_the_convention_they_are_handed(self):
        for kind, want in (("index", 1.0), ("static 60/40", 0.6)):
            for conv in ("start", "end"):
                self.assertEqual(ct.weights(kind, {}, self.d, conv), [want] * 4)

    def test_an_undeclared_construction_raises_instead_of_defaulting_to_cash(self):
        with self.assertRaises(ValueError):
            ct.weights("mom_top1", {}, self.d, "start")


class TheTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.spy = sl.legs(cls.data, "SPY")
        cls.marks = {c: sl.month_signal(sorted(cls.spy), cls.spy, c) for c in ("start", "end")}
        cls.rows = {}
        for rname, since in (("long", ct.SINCE), ("panel", ct.PANEL)):
            for spec in ct.PLANS:
                kind, shelter = spec
                for conv in (("start", "end") if kind == "MA200" else ("n/a",)):
                    key = (rname, kind, shelter, conv)
                    cls.rows[key] = ct.measure(cls.data, cls.spy, kind, shelter, since, cls.marks, conv,
                                               100_000.0, ct.PUBLISHED_PAYOUT, 10, 0.05)

    def r(self, rname, kind, shelter, conv="n/a"):
        return self.rows[(rname, kind, shelter, conv)]

    def test_the_index_row_on_the_panel_is_the_payout_this_repository_has_been_using(self):
        """$435.47 is round 58's payout because it is the index's safe withdrawal. Reproduced independently here, the
        table and the payout are the same number by construction."""

        self.assertAlmostEqual(self.r("panel", "index", sl.CASH)["safe"], ct.PUBLISHED_PAYOUT, delta=0.01)

    def test_the_index_row_is_its_own_bar(self):
        for rname in ("long", "panel"):
            row = self.r(rname, "index", sl.CASH)
            self.assertEqual(row["delta"], 0.0)
            self.assertIsNone(row["cap"], "a plan cannot become the riskier pair against itself")

    def test_the_long_record_prices_the_index_a_dollar_and_thirty_higher_than_the_panel_does(self):
        """Both records, same construction, one year and forty-two windows apart: pinned because the two columns must
        not be read as each other's correction."""

        self.assertAlmostEqual(self.r("long", "index", sl.CASH)["safe"], 436.76, delta=0.01)
        self.assertEqual(self.r("long", "index", sl.CASH)["n"], 169)

    def test_the_trend_plan_clears_the_index_by_more_than_a_hundred_only_with_the_shelter(self):
        """The verdict column, pinned: the signal alone is material but under $100; the signal with IEF is over it, on
        either reading of monthly, on either record."""

        for rname in ("long", "panel"):
            for conv in ("start", "end"):
                signal_only = self.r(rname, "MA200", sl.CASH, conv)["delta"]
                with_shelter = self.r(rname, "MA200", "IEF", conv)["delta"]
                self.assertGreater(signal_only, ct.BAR, f"{rname} month-{conv}: the signal alone is not material")
                self.assertLess(signal_only, 100.0)
                self.assertGreater(with_shelter, 100.0, f"{rname} month-{conv}")
                self.assertGreater(with_shelter, signal_only)

    def test_the_correction_moved_the_flagship_premium_down_not_up(self):
        """Round 66's finding, restated as an invariant: whatever the truth is, it is smaller than what has been
        published. The published premium is 593.13 - 435.47 = 157.66."""

        published = sl.PANEL_PIN - ct.PUBLISHED_PAYOUT
        self.assertAlmostEqual(published, 157.66, delta=0.02)
        for conv in ("start", "end"):
            self.assertLess(self.r("panel", "MA200", sl.CASH, conv)["delta"], published, f"month-{conv}")

    def test_a_naive_balanced_portfolio_is_not_the_hedge_it_is_sold_as(self):
        """60/40 with the off-equity half in bills fails more often than 100% equities on this metric, on both records,
        and supports less. The bond leg only helps once it is the thing being held, not a static fifth of the account."""

        for rname in ("long", "panel"):
            naive = self.r(rname, "static 60/40", sl.CASH)
            self.assertLess(naive["delta"], 0.0, rname)
            self.assertGreater(naive["p_fail"], 0.15, rname)
            self.assertGreater(naive["p_fail"], self.r(rname, "index", sl.CASH)["p_fail"],
                               "a naive 60/40 at least fails less often than the index; re-read the verdict")
            sheltered = self.r(rname, "static 60/40", "IEF")
            self.assertGreater(sheltered["delta"], 0.0, f"{rname}: the same portfolio with a paying shelter")
            self.assertEqual(sheltered["p_fail"], 0.0)
            self.assertLess(sheltered["cap"], self.r(rname, "MA200", "IEF", "start")["cap"],
                            f"{rname}: the cheap alternative buys less capacity than the rule")

    def test_every_row_within_a_record_shares_its_date_set(self):
        for rname, since in (("long", ct.SINCE), ("panel", ct.PANEL)):
            months = {row["months"] for key, row in self.rows.items()
                      if key[0] == rname and key[1] != "index" and key[2] != "GLD"}
            self.assertEqual(months, {288 if rname == "long" else 246})
            for key, row in self.rows.items():
                if key[0] == rname:
                    self.assertGreaterEqual(row["since"], since)

    def test_loosening_the_failure_budget_supports_more_withdrawal_and_never_less(self):
        for key in (("long", "MA200", "IEF", "start"), ("long", "static 60/40", "IEF", "n/a")):
            tight = self.r(*key)
            loose = ct.measure(self.data, self.spy, key[1], key[2], ct.SINCE, self.marks, key[3], 100_000.0,
                               ct.PUBLISHED_PAYOUT, 10, 0.20)
            self.assertGreater(loose["safe"], tight["safe"])

    def test_the_plans_the_table_prints_are_the_plans_the_tests_score(self):
        self.assertEqual(ct.PLANS, (("index", sl.CASH), ("MA200", sl.CASH), ("MA200", "IEF"),
                                    ("static 60/40", sl.CASH), ("static 60/40", "IEF")))


if __name__ == "__main__":
    unittest.main()
