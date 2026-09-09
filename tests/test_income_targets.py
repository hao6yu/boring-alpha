"""Round 50: the income ladder, its inversions, and the grid artefact that made long plans look safer.

Two of these tests exist to pin a *defect* in a published statistic: the raw guarantee column rises from 25 to 30
years, which is arithmetically impossible for a plan that must survive one more year of the same path. Pinning it
is not an accident — it is what keeps anyone from "simplifying" the common-grid control away, since on the raw grid
the long-horizon number is the flattering one.
"""

import math
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import income_targets as it                              # noqa: E402
import income_accounting as ia                           # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402


class TheInversionIsExact(unittest.TestCase):
    """Every capital in the printed table is `target × 12 / rate`, so the inversion must round-trip exactly.
    A table of required capital that does not reproduce the target is decoration."""

    def test_capital_times_rate_returns_the_target(self):
        for rate in (0.0165, 0.0437, 0.0828):
            for target in (250.0, 500.0, 2000.0):
                back = it.required(rate, target) * rate / 12.0
                self.assertAlmostEqual(back, target, places=8)

    def test_a_rate_that_is_zero_never_clears_anything(self):
        for target in (0.01, 250.0, 10_000.0):
            self.assertTrue(math.isinf(it.required(0.0, target)))
            self.assertTrue(math.isinf(it.required(-0.02, target)))

    def test_required_capital_is_monotone_and_linear_in_the_target(self):
        base = it.required(0.0437, 500.0)
        self.assertAlmostEqual(it.required(0.0437, 1000.0), 2 * base, places=6)
        self.assertLess(it.required(0.0437, 250.0), base)


class TheEnginesAreDerived(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.rows = {e["name"]: e for e in it.engines(cls.data, "SPY", 20)}
        cls.lad = it.ladder_rate(cls.data)

    def test_the_distribution_yield_is_the_archive_s_own_and_not_a_number_typed_by_hand(self):
        yld, per_year = it.dist_yield("SPY")
        self.assertGreater(yld, 0.005)
        self.assertLess(yld, 0.030)
        self.assertGreater(per_year, 2.0, "SPY pays quarterly; a lower count means the file was read wrong")

    def test_the_ladder_rate_is_an_identity_off_the_bill_curve_not_a_fourth_measurement(self):
        self.assertAlmostEqual(self.lad["spot"] - cy_sgov(), self.rows["T-bill ladder, today's bill curve"]["rate"],
                               places=12)

    def test_the_sale_rate_is_invariant_to_capital_so_the_inversion_is_legal(self):
        """The whole table assumes `guarantee ∝ capital`. Verified at two sizes, not assumed."""

        small = ia.guarantee("SPY", 1.00, 40_000.0, 20, self.data, 1)["cheque"]
        large = ia.guarantee("SPY", 1.00, 250_000.0, 20, self.data, 1)["cheque"]
        self.assertAlmostEqual(small / 40_000.0, large / 250_000.0, places=10)

    def test_the_ladder_is_redundant_against_the_index_plus_a_sale_rule_at_the_median_month(self):
        """The P0 rule applied to income. At the record's median bill the ladder needs more than twice the capital
        the sale rule needs for the same cheque — and the ladder's number is the one that depends on the Fed."""

        sale = self.rows["systematic sale, SPY at 1.0x, 20y, worst start"]["rate"]
        median = self.rows["T-bill ladder, the record's median month"]["rate"]
        self.assertLess(median, sale, "the median-month ladder stopped being the dominated option")
        self.assertGreater(it.required(median, 500.0), 2 * it.required(sale, 500.0),
                           "the redundancy narrowed; re-state the recommendation rather than this threshold")

    def test_the_zero_rate_era_ladder_is_not_positive_after_costs(self):
        era = self.rows["T-bill ladder, the zero-rate era"]["rate"]
        self.assertLessEqual(era, 0.001,
                             f"the zero-rate era reads {era:+.2%}; the printed 'never' would now be false")
        self.assertTrue(math.isinf(it.required(era, 500.0)) or it.required(era, 500.0) > 2_000_000.0)


def cy_sgov():
    import cash_yield_gap as cy
    return cy.SGOV_ER


class TheGridArtefact(unittest.TestCase):
    """The round's real finding, pinned from both ends."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.rows = it.horizon_table(cls.data, "SPY")

    def test_the_raw_minimum_rises_at_the_long_end_and_that_is_the_artefact(self):
        raw = [r["rate"] for _y, r, _c in self.rows]
        self.assertGreater(raw[-1], raw[-2],
                           "the raw guarantee went monotone; check whether the archive grew before believing it")

    def test_the_common_grid_is_strictly_monotone_decreasing(self):
        com = [c["rate"] for _y, _r, c in self.rows]
        for a, b in zip(com, com[1:]):
            self.assertGreater(a, b, f"the comparable-horizon guarantee stopped falling: {com}")

    def test_the_common_grid_holds_one_sample_count_across_every_horizon(self):
        counts = {c["starts"] for _y, _r, c in self.rows}
        self.assertEqual(len(counts), 1, f"the control leaked: {counts}")
        self.assertLess(counts.pop(), 60, "the shared grid is meant to be small; that is the cost of the control")

    def test_the_control_moves_the_short_horizons_hard_and_the_longest_one_not_at_all(self):
        """The asymmetry is the tell. Conditioning on one start set removes every post-1996 start, which is what
        makes the short horizons' guarantees *rise* — they lose their worst starts. At 30 years the raw grid can
        only contain pre-1996 starts anyway, so the control is nearly a no-op there, and that is the cleanest
        proof that the two columns differ because of the sample and not the method. The raw 20-year number is the
        conservative one; the raw 30-year number is the lucky one."""

        first, mid, last = self.rows[0], self.rows[2], self.rows[-1]
        self.assertGreater(first[2]["rate"] / first[1]["rate"], 1.5,
                           "the 10-year control should lift the number a lot")
        self.assertGreater(mid[2]["rate"] / mid[1]["rate"], 1.5)
        self.assertLess(abs(last[2]["rate"] / last[1]["rate"] - 1.0), 0.02,
                        "the controls moved the 30-year row; the grids no longer coincide")

    def test_the_artefact_is_not_an_artifact_of_the_refinement(self):
        """`capacity` probes in rungs and refines zeros; the horizon claim must not depend on either."""

        for years in (20, 30):
            g = ia.guarantee("SPY", 1.00, 100_000.0, years, self.data, 1, until=it.COMMON_GRID_END)
            self.assertEqual(g["starts"], 44)
            self.assertFalse(g.get("flag"), f"a flag appeared at {years}y: {g.get('flag')}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
