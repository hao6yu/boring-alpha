"""Tests for the floating-loan tool: that the calibration is what it claims, that the two models are
*identical* in the month they were calibrated in, and that the spread sensitivity has the sign it must have.

The tool's whole argument is that the fixed-rate number and the floating-rate number agree today and disagree
only in history. That is a checkable identity rather than a mood, so it is tested as one: if the calibration
shifts, or if a wider spread ever *helps* a book that is short a rate, the tool has broken and the plan it
prices should not be signed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import floating_loan as fl                         # noqa: E402
import income_frontier as ifr                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402


class TheCalibrationIsTheToolOwns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_spread_is_the_menu_rate_minus_the_curve_and_is_positive(self):
        spread = fl.spread_bps_calibrated(self.data)
        self.assertGreater(spread, 0.0, "the posted menu rate must exceed the bill curve or nobody is borrowing")
        # The literal here was 0.0288 — round 47's four-day September stub, transcribed into a test that was
        # therefore checking the arithmetic of a wrong window. Derived from the engine now, on complete months.
        import cash_yield_gap as cyg
        curve = cyg.bill(self.data)["current3m"]
        self.assertAlmostEqual(spread, (ifr.MENU_PUBLIC - curve) * 10_000.0, delta=1.0)
        self.assertGreater(curve, 0.03, "the stub must not return as the calibration curve")
        self.assertLess(spread, 600.0, "a 6% spread over the curve is not a retail margin quote")


class TheTwoModelsAgreeWhereTheyAreCalibrated(unittest.TestCase):
    """The floating model is built so that its first month equals the posted rate. If that is not exactly true,
    every window comparison below it is comparing two different account sizes dressed as one."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.spread = fl.spread_bps_calibrated(cls.data)

    def test_a_constant_125x_book_is_identical_under_both_models_in_the_last_window(self):
        fixed = fl.excess(self.data, ifr.MENU_PUBLIC * 10_000.0, "posted", 1.25, 2022, 2026)
        floating = fl.excess(self.data, self.spread, "book", 1.25, 2022, 2026)
        self.assertGreater(fixed["months"], 24)
        self.assertAlmostEqual(fixed["excess"], floating["excess"], delta=1.2,
                               msg="the two models drifted apart in the window they were calibrated to")

    def test_an_unlevered_book_earns_nothing_either_way_because_there_is_no_loan(self):
        """The identity that tells you the financing model is only touching the financing."""

        for borrow in ("posted", "book"):
            e = fl.excess(self.data, 202.0, borrow, 1.00, 1993, 2026)
            self.assertAlmostEqual(e["excess"], 0.0, places=9,
                                   msg=f"an all-equity book picked up a financing effect under {borrow}")


class TheSensitivityHasTheRightSign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_a_wider_spread_always_makes_a_borrower_worse_off(self):
        base = fl.excess(self.data, 202.0, "book", 1.25, 1993, 2026)["excess"]
        wider = fl.excess(self.data, 402.0, "book", 1.25, 1993, 2026)["excess"]
        widest = fl.excess(self.data, 602.0, "book", 1.25, 1993, 2026)["excess"]
        self.assertGreater(base, wider)
        self.assertGreater(wider, widest)

    def test_the_penalty_grows_with_leverage_because_the_book_borrows_more(self):
        def drop(leverage: float) -> float:
            return (fl.excess(self.data, 202.0, "book", leverage, 1993, 2026)["excess"]
                    - fl.excess(self.data, 402.0, "book", leverage, 1993, 2026)["excess"])
        self.assertGreater(drop(2.0), drop(1.25))

    def test_the_full_record_flatters_the_loan_and_the_2008_window_is_the_binding_one(self):
        """The claim this file exists to make, pinned: the flattering number is the average and the decision is
        made in the worst window."""

        full = fl.excess(self.data, 202.0, "book", 1.25, 1993, 2026)["excess"]
        worst = fl.excess(self.data, 202.0, "book", 1.25, 2007, 2009)["excess"]
        self.assertGreater(full, 0.0)
        self.assertLess(worst, 0.0)
        self.assertLess(fl.excess(self.data, 202.0, "book", 1.25, 2007, 2009)["dd"], -0.50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
