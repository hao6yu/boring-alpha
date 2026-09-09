"""Tests for the 2x2 added to `tools/shelter_long_record.py` — round 62's insurance claim, re-scored on a longer record.

The claim is narrow and the tests make it stay narrow: at the published payout the trend plan covers every entry the
index plan fails at, and on this record those entries are three adjacent months of April 2003. Nothing here is allowed
to quietly become "56 entries spread over a decade", which is what round 62 measured on a record that starts in 1993.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                            # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import trend_cost_test as tc                                 # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data      # noqa: E402

SINCE = dt.date(2002, 8, 1)
PAYOUT = 435.47


def frames(data, spy, conv="start"):
    """The plans, the index, and the record's dates, scored once and shared by every test in this file."""

    out = {w: sl.record(data, spy, w, SINCE, 100_000.0, 10, 0.05, PAYOUT, conv) for w in sl.SHELTERS}
    plans = {w: out[w]["monthly"] for w in sl.SHELTERS}
    bench = out[sl.CASH]["bench_monthly"]
    return out, plans, bench


class TheFrame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.spy = sl.legs(cls.data, "SPY")
        cls.out, cls.plans, cls.bench = frames(cls.data, cls.spy)
        cls.grid = {}
        for pay, contrib in ((PAYOUT, 0.0), (700.0, 0.0), (900.0, 0.0), (PAYOUT, 1000.0)):
            cls.grid[(pay, contrib)] = sl.contingency(cls.plans, cls.bench, 100_000.0, pay, contrib, 10)

    def test_the_contribution_frame_cannot_test_this_claim_on_this_record(self):
        """Round 62's headline frame has the index failing in 56 of 283 starts because that record begins in 1993 and
        runs a plan through the lost decade. From 2002, $1,000 a month in never fails anywhere, so a table scored this
        way proves nothing about insurance."""

        c = self.grid[(PAYOUT, 1000.0)]
        self.assertEqual(c["__bench__"]["fails"], 0)
        for leg in ("cash", "IEF", "TLT"):
            self.assertEqual(c[leg]["insurance"] + c[leg]["redundant"] + c[leg]["cost"], 0)

    def test_the_cells_are_exhaustive_and_disjoint(self):
        for (_pay, _c), grid in self.grid.items():
            for leg, cell in grid.items():
                if leg == "__bench__" or cell.get("short"):
                    continue
                self.assertEqual(sum(cell[k] for k in sl.CELLS), cell["n"], f"{leg} at payout {_pay}")

    def test_a_leg_on_a_shorter_record_is_dropped_not_paired(self):
        c = self.grid[(PAYOUT, 0.0)]
        self.assertTrue(c["GLD"].get("short"), "GLD's record is shorter; pairing it by row number would be a lie")
        self.assertEqual(c["__bench__"]["skipped"], 1, "exactly one leg must be dropped for length")

    def test_at_the_published_payout_the_hedge_is_perfect_and_the_sample_is_three_months(self):
        """7/0/0 for every shelter: all seven entries the index fails at, none missed, none paid for in vain."""

        c = self.grid[(PAYOUT, 0.0)]
        self.assertEqual(c["__bench__"]["fails"], 7)
        for leg in ("cash", "IEF", "TLT"):
            self.assertEqual((c[leg]["insurance"], c[leg]["redundant"], c[leg]["cost"]), (7, 0, 0), leg)
        dates = self.out[sl.CASH]["dates"]
        lo, hi = c["IEF"]["spans"]
        first, last = dates[120 + lo], dates[120 + hi]
        self.assertEqual((first.year, first.month), (2003, 4), f"the covered entries start {first}, not April 2003")
        self.assertLessEqual((last - first).days, 40, "the failing entries have spread out; re-read the note")

    def test_above_the_ceiling_the_hedge_buys_nothing_at_all(self):
        """Round 63's and 65's capacity claim, told as a table: at $900/mo no leg covers a single entry, and each fails
        in four starts out of five, so the two things the hedge was bought for have both gone."""

        c = self.grid[(900.0, 0.0)]
        for leg in ("cash", "IEF", "TLT"):
            self.assertEqual(c[leg]["insurance"], 0, leg)
            self.assertGreater(c[leg]["p_fail_self"], 0.80, leg)

    def test_the_shelter_improves_the_risk_frame_not_only_the_income(self):
        """The reason IEF is the recommendation, in the frame that is not about income. At $700/mo it turns entries the
        index and the plan both failed at into entries the plan covered, and cuts the ones it pays for in vain."""

        cash, ief = self.grid[(700.0, 0.0)]["cash"], self.grid[(700.0, 0.0)]["IEF"]
        self.assertEqual(cash["insurance"], 11, "the bill-sheltered plan's cells have moved; re-measure")
        self.assertGreater(ief["insurance"], cash["insurance"])
        self.assertLess(ief["redundant"], cash["redundant"])
        self.assertLess(ief["cost"], cash["cost"])
        self.assertLess(ief["p_fail_self"], cash["p_fail_self"])
        self.assertGreater(ief["concordance"], 0.0, "concordance is quoted even when it is not flattering")

    def test_the_cell_a_hedge_can_occupy_is_a_hump_in_the_withdrawal_not_a_slope(self):
        """Wrong in the direction of comfort, so it is pinned. At the published payout the index fails in 7 starts, so
        there are at most 7 entries the hedge could cover. Raise the withdrawal and the index fails more often, which
        gives the hedge more to do — 42. Raise it past the plan's own ceiling and the hedge covers nothing again, 0.
        A claim of `insurance` has a payout band, and the published plan sits at the bottom edge of it."""

        grid = self.grid
        self.assertEqual([grid[p]["IEF"]["insurance"] for p in ((PAYOUT, 0.0), (700.0, 0.0), (900.0, 0.0))],
                         [7, 42, 0])
        self.assertGreater(grid[(700.0, 0.0)]["__bench__"]["fails"], grid[(PAYOUT, 0.0)]["__bench__"]["fails"])


class TheBenchRow(unittest.TestCase):
    def test_the_index_row_reports_its_own_failures_rather_than_a_fake_2x2(self):
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        spy = sl.legs(data, "SPY")
        _out, plans, bench = frames(data, spy)
        c = sl.contingency(plans, bench, 100_000.0, 700.0, 0.0, 10)
        self.assertEqual(c["__bench__"]["n"], 169)
        self.assertAlmostEqual(c["__bench__"]["fails"] / c["__bench__"]["n"], 0.426, delta=0.005)

    def test_the_bench_series_is_the_index_held_with_no_shelter_at_all(self):
        """The comparison leg must be plain VOO-in-all-but-name, or the 2x2 is scoring the hedge against itself."""

        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        spy = sl.legs(data, "SPY")
        dates = [d for d in sorted(spy) if d >= SINCE]
        bench = mir.month_marks(dates, sl.two_asset_path(dates, spy, None, [1.0] * len(dates),
                                                        wc.EXPENSE["SPY"], 0.0))[1]
        _out, _plans, got = frames(data, spy)
        self.assertEqual(len(bench), len(got))
        for a, b in zip(bench, got):
            self.assertAlmostEqual(a, b, places=12)


if __name__ == "__main__":
    unittest.main()
