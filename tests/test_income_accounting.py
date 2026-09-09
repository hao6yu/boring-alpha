"""Tests for the two-order-statistic reconciliation.

The load-bearing assertion in this file is not any single number, it is that **the ranking of the leverage grid
differs between the two columns**. That one claim is the artifact's whole purpose, and it is the kind of claim a
test can silently stop testing if it is written as "both columns return positive numbers". Everything else here
either pins a figure against the tool that produced it, or pins a refusal.

Runtime note: `capacity()` bisects 40 steps against every start date in the record, so these tests price SPY and
QQQ and let the remaining sleeves be the CLI's problem.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import income_accounting as ia                  # noqa: E402
import withdrawal_capacity as wc                # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class TheTwoColumnsDisagree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.cap = wc.START
        cls.rows = {r["lever"]: r for r in ia.table(cls.data, cls.cap, 20, sleeves=("SPY",))}

    def test_the_mean_rises_with_leverage_on_every_sleeve_tested(self):
        m = [self.rows[l]["mean"] for l in ia.GRID]
        for a, b in zip(m, m[1:]):
            self.assertLess(a, b)

    def test_the_guarantee_falls_with_leverage_on_spy(self):
        g = [self.rows[l]["guarantee"] for l in ia.GRID]
        for a, b in zip(g, g[1:]):
            self.assertGreater(a, b, "the guarantee must fall as leverage rises, or the finding has changed")

    def test_the_two_columns_rank_the_grid_differently(self):
        """The artifact's claim, stated as an ordering rather than a number so it cannot be satisfied by a
        constant."""

        best_mean = max(self.rows.values(), key=lambda r: r["mean"])["lever"]
        best_guar = max(self.rows.values(), key=lambda r: r["guarantee"])["lever"]
        self.assertEqual(best_mean, 2.00)
        self.assertEqual(best_guar, 1.00)
        self.assertNotEqual(best_mean, best_guar)

    def test_a_full_leverage_row_at_one_times_pays_no_excess_by_construction(self):
        """The mean column is an excess, so its 1.0× cell must be exactly zero — not small, zero. If it is not,
        the two columns are not describing the same comparator and the comparison is void."""

        self.assertAlmostEqual(self.rows[1.00]["mean"], 0.0, places=9)
        self.assertAlmostEqual(self.rows[1.00]["delta"], 0.0, places=6)

    def test_the_guarantee_at_one_times_reproduces_withdrawal_capacity_on_its_own_grid(self):
        """Cross-artifact consistency, pinned on the *other* file's grid rather than this one's.
        `withdrawal_capacity.py` publishes $378.52/mo as SPY's smallest cheque, sampled every third month;
        this file must reproduce it exactly when run the same way, and must then say why that figure is the
        flattering one."""

        same_grid = ia.guarantee("SPY", 1.0, self.cap, 20, self.data, stride=3)
        self.assertAlmostEqual(same_grid["cheque"], 378.52, delta=0.05)
        self.assertEqual(same_grid["starts"], 55)

    def test_the_dense_grid_is_the_lower_bound_and_the_coarse_one_is_the_flattering_one(self):
        """Round 42. A guarantee is a minimum, so sampling more starts cannot raise it — and on this archive the
        month that ends the promise is April 2000, which a stride of 3 steps straight over. The coarse figure is
        not a noisier estimate of the same number, it is a biased one."""

        dense = ia.guarantee("SPY", 1.0, self.cap, 20, self.data, stride=1)
        coarse = ia.guarantee("SPY", 1.0, self.cap, 20, self.data, stride=3)
        self.assertAlmostEqual(dense["cheque"], 364.45, delta=0.05)
        self.assertLess(dense["cheque"], coarse["cheque"])
        self.assertEqual(str(dense["binding"])[:7], "2000-04", "the dense grid must find April 2000")
        self.assertEqual(str(coarse["binding"])[:7], "2000-05", "and the coarse grid must demonstrably miss it")
        self.assertGreater(coarse["starts"], 0)

    def test_the_sign_of_the_finding_survives_every_grid_even_though_the_level_does_not(self):
        """The level moves by ~$26/mo across grids; the difference between the two columns never changes sign.
        This is the test that decides whether the round's conclusion is a grid artefact, and it is deliberately
        written as a sign test rather than a band."""

        deltas = []
        for st in (1, 2, 3, 6, 12):
            a = ia.guarantee("SPY", 1.0, self.cap, 20, self.data, stride=st)
            b = ia.guarantee("SPY", 1.25, self.cap, 20, self.data, stride=st)
            deltas.append(b["cheque"] - a["cheque"])
        for d in deltas:
            self.assertLess(d, 0.0)
        self.assertLess(max(deltas) - min(deltas), 10.0, "the delta is grid-robust to within $10/mo")
        # No ordering is asserted on the deltas themselves: they are not monotone across strides, and a test
        # that invented one here would fail uselessly the next time the archive is resealed.

    def test_the_binding_start_is_the_dot_com_window_on_spy(self):
        """The same era r39 and r40 identified as binding, arriving independently through a decumulation engine
        that never sees the price series the other tools use."""

        self.assertIn("2000", str(self.rows[1.25]["binding"]))


class ASleeveCanRefuse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_qqq_pays_a_positive_mean_and_a_guarantee_that_collapses_but_never_vanishes(self):
        """Round 41 published this cell as 'exactly $0.00, not small, zero' and was wrong. The zero was the
        bisection's smallest probe rung ($150/mo on a $100k lump): anything below it prints as zero. Refined, the
        guarantee declines in a graded, credible way — 171, 112, 68, 39, 20 — which is a far more useful fact than
        a cliff, and the delta against 1.0x is larger than the one reported, not smaller.

        Round 104 moved the levered rungs and left the un-levered one alone, which is the fingerprint of the loan price:
        `withdrawal_capacity.BORROW_SPREAD` had been typing 150 bps while the forward engine had carried the posted desk
        quote of 202 bps since round 30. Sourcing it cost this frontier $1.25 a month at 1.25x, $1.50 at 1.5x, and nothing
        at all at 1.0x — a flattery that only applied to the books that borrow."""

        rows = {r["lever"]: r for r in ia.table(self.data, wc.START, 20, sleeves=("QQQ",))}
        self.assertAlmostEqual(rows[1.25]["guarantee"], 112.50, delta=0.05)   # 113.75 at the pre-round-104 loan price
        self.assertAlmostEqual(rows[2.00]["guarantee"], 20.00, delta=0.05)
        g = [rows[l]["guarantee"] for l in ia.GRID]
        for a, b in zip(g, g[1:]):
            self.assertGreater(a, b, "the guarantee must decline monotonically, not fall off a cliff")
        self.assertTrue(rows[1.25]["flag"], "a refined figure must arrive with its provenance attached")

    def test_the_unrefined_engine_really_does_report_zero_where_the_frontier_is_positive(self):
        """The artefact itself, pinned. This test asserts that a real tool returns a wrong-looking number under
        its own defaults, so that nobody 'fixes' the refinement by trusting the engine again. The $0.00 and the
        refined figure are both produced by the same function; the only difference is whether anyone probed below the
        first rung. (Round 104's loan correction moved the refined figure to $112.50; the artefact is the zero, not its
        neighbour's cents.)"""

        series = {k: v["QQQ"].close for k, v in self.data.by_date.items() if "QQQ" in v}
        rets, cash, keys = wc.monthly(series, self.data.cash_factors)
        windows = wc.windows_for(rets, cash, keys, 20, 1)
        coarse = wc.capacity(windows, 1.25, wc.EXPENSE["QQQ"])
        self.assertEqual(coarse[0], 0.0, "the coarse probe no longer reports zero; the artefact may be gone")
        self.assertEqual(coarse[2], "none")
        fine = wc.capacity(windows, 1.25, wc.EXPENSE["QQQ"], ceiling=0.002, steps=40)
        self.assertGreater(fine[0] * wc.START, 100.0)
        self.assertEqual(fine[2], "2000-04", "the refined binding start must name a date, not 'none'")

    def test_voo_refuses_rather_than_printing_a_short_window(self):
        """Round 39's lesson in the other direction: VOO has 192 months and a 20-year plan needs 240. The tool
        must decline, not quietly price a 16-year window against a 33-year one."""

        row = ia.table(self.data, wc.START, 20, sleeves=("VOO",))[0]
        self.assertIn("refused", row)
        self.assertIsNone(ia.guarantee("VOO", 1.25, wc.START, 20, self.data)["cheque"])

    def test_a_shorter_plan_gives_voo_a_number_after_all(self):
        """The refusal must be about the window length, not a blanket ban on the sleeve the goal named."""

        self.assertIsNotNone(ia.guarantee("VOO", 1.25, wc.START, 12, self.data)["cheque"])

    def test_an_unknown_sleeve_raises_rather_than_returning_zero(self):
        """Zero is a result in this file, so an absent sleeve must not be allowed to look like one."""

        with self.assertRaises(ValueError):
            ia.guarantee("NOPE", 1.25, wc.START, 20, self.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
