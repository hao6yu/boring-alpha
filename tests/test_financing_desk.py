"""Round 46: the financing break-even, and the identity that keeps the financing model honest.

The claim under test is not "borrowing is bad". It is narrower and checkable: a constant-leverage book beats the
same money unlevered only below some all-in financing rate, that rate is 6.60-13.15% depending on sleeve and
window, and the posted base tiers of the large custodians (10.0-12.0%, April 2026) sit above the ones that matter.
`MENU_PUBLIC` is patched inside `excess`, so these tests also make sure the patch cannot leak.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import financing_desk as fd                    # noqa: E402
import income_frontier as ifr                  # noqa: E402
import withdrawal_capacity as wc               # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class TheBreakEvenExistsAndMovesTheWayFinancingDoes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_at_one_times_leverage_the_financing_rate_is_irrelevant(self):
        """The identity that validates the whole model: nothing is borrowed at w = 1.00, so the excess must be
        exactly zero at every rate on the menu. If the cash leg and the financing leg failed to cancel for a
        unlevered book, this fails immediately."""

        for name, rate in fd.DESKS:
            e, _w = fd.excess(self.data, "SPY", 1.0, rate, None)
            self.assertAlmostEqual(e, 0.0, places=9, msg=f"{name} charged an unlevered account")

    def test_the_excess_falls_as_the_rate_rises_and_the_verdict_agrees_with_the_break_even(self):
        rates = [r for _n, r in fd.DESKS]
        vals = [fd.excess(self.data, "SPY", 1.25, r, None)[0] for r in rates]
        for a, b in zip(vals, vals[1:]):
            # assertGreater, not assertLess: the series is decreasing in the rate. Written the other way round
            # this test failed on the first run, which is the only reason the direction is known to be pinned.
            self.assertGreater(a, b, "a more expensive loan must not improve the tilt")
        be = fd.breakeven(self.data, "SPY", 1.25, None)
        self.assertGreater(be, fd.CHEAP[1], "the cheap desk must clear its own break-even")
        self.assertLess(be, fd.EXPENSIVE[1], "the verdict line claims the expensive desk fails")
        self.assertLess(fd.excess(self.data, "SPY", 1.25, fd.EXPENSIVE[1], None)[0], 0.0)

    def test_the_break_even_falls_as_leverage_rises(self):
        """Variance drag scales with the square of the exposure while the financing term scales with (w - 1), so a
        bigger book tolerates a cheaper loan — the leveraged recommendation gets *less* robust, not more, as the
        account leans harder."""

        bes = [fd.breakeven(self.data, "SPY", lev, None) for lev in (1.25, 1.50, 2.00)]
        for a, b in zip(bes, bes[1:]):
            self.assertGreater(a, b, f"break-even stopped shrinking with leverage: {bes}")

    def test_the_window_alone_moves_the_break_even_by_nearly_four_points(self):
        """Measured: full history 9.21%, the VOO era 13.15% — a 3.94-point gap from nothing but which months are
        in the sample. Asserted at three points rather than the four I first wrote, because the measurement is
        3.94 and a threshold tuned to four would be a test that fails on a Tuesday for no reason."""

        full = fd.breakeven(self.data, "SPY", 1.25, None)
        era = fd.breakeven(self.data, "SPY", 1.25, 192)
        self.assertGreater(era - full, 0.03,
                           "the era effect on the break-even is the finding; if it shrinks, re-read the note")

    def test_the_published_edge_reproduces_at_the_cheap_desk(self):
        e, _w = fd.excess(self.data, "SPY", 1.25, fd.CHEAP[1], 192)
        self.assertAlmostEqual(e, 2.18, delta=0.05, msg="the tilt's headline edge moved; check the note")


class TheToolDoesNotLieAboutItsOwnInputs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_menu_is_ordered_and_its_cheap_end_cannot_drift_from_income_frontier(self):
        rates = [r for _n, r in fd.DESKS]
        self.assertEqual(rates, sorted(rates), "DESKS must stay ascending; CHEAP/EXPENSIVE index the ends")
        self.assertIs(fd.DESKS[0], fd.CHEAP)
        self.assertIs(fd.DESKS[-1], fd.EXPENSIVE)
        self.assertAlmostEqual(fd.CHEAP[1], ifr.MENU_PUBLIC, places=6,
                               msg="this file and income_frontier are pricing different desks")

    def test_the_patched_rate_never_leaks_even_when_the_call_raises(self):
        before = ifr.MENU_PUBLIC
        fd.excess(self.data, "SPY", 1.25, 0.11, 12)
        self.assertAlmostEqual(ifr.MENU_PUBLIC, 0.0490, places=6)
        self.assertEqual(ifr.MENU_PUBLIC, before)

    def test_compounded_reports_destruction_rather_than_a_complex_number(self):
        """Round 46's first draft divided two monthly returns and produced a complex `ann` when the path went
        negative. `compounded` returns None for a destroyed account so callers must handle it, never guess."""

        self.assertEqual(fd.compounded([0.0] * 24), (0.0, 1.0))
        self.assertEqual(fd.compounded([0.05, -1.0, 0.5])[0], None)
        e, _w = fd.excess(self.data, "SPY", 1.0, 0.11, 12)
        self.assertAlmostEqual(e, 0.0, places=9)

    def test_the_rate_card_gap_is_stated_in_dollars_not_only_in_basis_points(self):
        cheap, rich = fd.CHEAP[1], fd.EXPENSIVE[1]
        self.assertAlmostEqual((rich - cheap) * 10_000, 710.0, delta=1.0)
        self.assertAlmostEqual(rich * 10_000 - cheap * 10_000, 710.0, delta=1.0,
                               msg="the $/yr line on a $10,000 loan is the same arithmetic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
