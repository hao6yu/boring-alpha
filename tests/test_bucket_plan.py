"""Round 53: the cash bucket, priced. It buys the operational benefit it claims and no survival whatsoever.

Tests 1 and 10 are the finding in both directions: the benefit is enormous and costs almost nothing to measure, and
it moves the survivability of the plan not at all. The identity in test 5 is the sanity check that keeps the rest
honest.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import bucket_plan as bp                                 # noqa: E402
import cash_yield_gap as cy                              # noqa: E402
import plan_survival as ps                               # noqa: E402
import required_edge as re_                              # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

SLEEVE, C0, TARGET, YEARS = "SPY", 100_000.0, 500.0, 20


class TheBenefitIsReal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.base = bp.evaluate(cls.data, SLEEVE, C0, TARGET, YEARS, 0, "all-equity")
        cls.b12 = bp.evaluate(cls.data, SLEEVE, C0, TARGET, YEARS, 12, "refill-only")

    def test_an_unbuffered_plan_is_forced_to_sell_every_single_month(self):
        """With no cash leg there is no other way to pay the cheque. Pinned on a synthetic surviving path rather than
        on the archive average, which is 237.3 and not 240 solely because destroyed windows stop counting at the
        month they die — a mean over a mixture of truncated and complete runs is not an identity."""

        out = bp.simulate_bucket([0.0] * 120, [0.0] * 120, C0, TARGET, 0, "all-equity", 0.0)
        self.assertEqual(out["forced"], 120)
        self.assertGreater(self.base["forced_mean"], 12 * YEARS - 5)

    def test_a_twelve_month_buffer_all_but_eliminates_forced_selling(self):
        self.assertLess(self.b12["forced_mean"], 1.0,
                        f"the bucket left {self.b12['forced_mean']:.1f} forced months; it is not doing its job")

    def test_the_benefit_costs_depth_in_the_account_and_the_depth_is_two_points(self):
        """The folklore promises a shallower hole. It delivers one, and the size is the story: a 237-month
        improvement in forced selling buys two percentage points of trough depth."""

        gain = self.b12["median_trough"] - self.base["median_trough"]
        self.assertGreater(gain, 0.0, "the bucket was supposed to make the hole shallower")
        self.assertLess(gain, 0.05, f"the trough moved {gain:+.2f}: re-read the round's conclusion")
        self.assertGreater(self.base["forced_mean"] / max(self.b12["forced_mean"], 1e-9), 50.0)


class TheBenefitIsNotSurvival(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_no_buffer_size_at_any_tested_parameter_reduces_the_failure_probability(self):
        """Nine capital/target/horizon combinations, four buffer sizes, 36 comparisons. Not one reduces failure —
        and several make it worse, because the buffer is a permanent short position in the return."""

        strict = 0
        for c0 in (100_000.0, 250_000.0, 500_000.0):
            for target, years in ((500.0, 10), (500.0, 20), (2_000.0, 20)):
                base = bp.evaluate(self.data, SLEEVE, c0, target, years, 0, "all-equity")["p_fail"]
                for months in (6, 12, 24, 36):
                    r = bp.evaluate(self.data, SLEEVE, c0, target, years, months, "refill-only")
                    if not r["n"] or r["p_fail"] is None:
                        continue
                    self.assertGreaterEqual(r["p_fail"], base - 1e-12,
                                            f"buffer {months}mo at {c0:.0f}/{target:.0f}/{years}y undercut"
                                            f" the unbuffered plan: {r['p_fail']:.2%} vs {base:.2%}")
                    strict += r["p_fail"] > base
        self.assertGreater(strict, 10, "the buffer never cost anything either; check the cash leg")

    def test_the_capital_buys_the_floor_that_the_buffer_cannot(self):
        """At $250k/$500/20y the unbuffered plan already never fails — round 52's $188k threshold with room to
        spare — so the bucket has literally nothing left to protect, and everything to lose."""

        base = bp.evaluate(self.data, SLEEVE, 250_000.0, 500.0, 20, 0, "all-equity")
        b12 = bp.evaluate(self.data, SLEEVE, 250_000.0, 500.0, 20, 12, "refill-only")
        self.assertEqual(base["p_fail"], 0.0)
        self.assertEqual(b12["p_fail"], 0.0)
        self.assertLess(b12["median_mult"], base["median_mult"],
                        "free money in this tool would mean the cash leg is earning something it should not")

    def test_the_cost_of_the_benefit_rises_monotonically_with_the_buffer(self):
        mults = [bp.evaluate(self.data, SLEEVE, C0, TARGET, YEARS, m, "refill-only")["median_mult"]
                 for m in (0, 6, 12, 24, 36, 60)]
        self.assertEqual(mults, sorted(mults, reverse=True), f"terminal multiples out of order: {mults}")
        self.assertLess(mults[-1], mults[0] * 0.5, "a 60-month buffer stopped being expensive; re-check the legs")


class ThePoliciesAreOnePolicy(unittest.TestCase):
    """Round 53's second finding: the refill/sweep/rebalance debate is inert for anyone taking money out."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_refill_only_and_two_way_agree_exactly_at_every_band(self):
        for band in (0.0, 0.5, 0.9):
            a = bp.evaluate(self.data, SLEEVE, C0, TARGET, YEARS, 12, "refill-only", band)
            b = bp.evaluate(self.data, SLEEVE, C0, TARGET, YEARS, 12, "two-way", band)
            self.assertEqual(a["median_mult"], b["median_mult"], f"the policies diverged at band {band}")
            self.assertEqual(a["p_fail"], b["p_fail"])

    def test_constant_weight_ignores_the_band_because_it_has_none(self):
        runs = [bp.evaluate(self.data, SLEEVE, C0, TARGET, YEARS, 12, "constant-weight", b)
                for b in (0.0, 0.5, 0.9)]
        self.assertEqual(len({r["median_mult"] for r in runs}), 1)

    def test_a_wider_band_buys_back_cost_without_buying_benefit(self):
        """A 90% band means most months leave the cash leg alone, so more money sits in equities: the same lever as
        a smaller buffer, seen from the other side. It moves the terminal and not the trough."""

        narrow = bp.evaluate(self.data, SLEEVE, C0, TARGET, YEARS, 12, "refill-only", 0.0)
        wide = bp.evaluate(self.data, SLEEVE, C0, TARGET, YEARS, 12, "refill-only", 0.9)
        self.assertGreater(wide["median_mult"], narrow["median_mult"])
        self.assertAlmostEqual(wide["median_trough"], narrow["median_trough"], delta=0.02)


class TheArithmeticHolds(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_only_leak_in_a_flat_market_is_the_fund_you_hold_the_bucket_in(self):
        """Zero returns, zero equity expense, one decade: the ending balance is capital minus spending minus
        SGOV's 9bp on the bucket, exactly — `er x buffer x years`, to the cent, at four buffer sizes. My first draft
        of this test predicted no leak at all and measured a $54 shortfall on a 12-month bucket: the difference is
        not a bug but the price of the wrapper, and it is now the identity. Note the 240-month version of the same
        plan is destroyed on spending alone ($120,000 through a $100,000 account), which is why the horizon is 10
        years and not the plan's 20."""

        years = 10
        path_eq, path_cash = [0.0] * (12 * years), [0.0] * (12 * years)
        flat = bp.simulate_bucket(path_eq, path_cash, C0, TARGET, 0, "all-equity", 0.0)
        self.assertAlmostEqual(flat["terminal"], C0 - TARGET * 12 * years, places=6)
        for months in (6, 12, 24, 36):
            out = bp.simulate_bucket(path_eq, path_cash, C0, TARGET, months, "refill-only", 0.0)
            drag = flat["terminal"] - out["terminal"]
            self.assertAlmostEqual(drag, bp.CASH_ER * TARGET * months * years, places=6,
                                   msg=f"buffer {months}mo: the leak is not the expense on the bucket")

    def test_a_buffer_larger_than_the_capital_is_refused_rather_than_simulated(self):
        """60 months of $2,000 is $120,000, which does not fit inside $100,000. Silently running that would put a
        negative equity leg into a table of probabilities."""

        with self.assertRaises(ValueError):
            bp.simulate_bucket([0.0] * 12, [0.0] * 12, 100_000.0, 2_000.0, 60, "refill-only", 0.0)
        self.assertTrue(bp.evaluate(self.data, SLEEVE, 100_000.0, 2_000.0, 20, 60, "refill-only")
                        .get("infeasible"))

    def test_a_destroyed_run_reports_its_trough_at_zero(self):
        eq = [-0.60] * 24
        out = bp.simulate_bucket(eq, [0.0] * 24, 50_000.0, 4_000.0, 6, "refill-only", 0.0)
        self.assertFalse(out["survived"])
        self.assertEqual(out["trough_mult"], 0.0)

    def test_the_two_legs_travel_together_and_the_window_count_matches_the_other_tools(self):
        """Three tools now slice the same record. A cash leg misaligned by one month would earn the bill curve a
        month before it existed, and only a shared count would catch it."""

        w = bp.paired_windows(self.data, SLEEVE, YEARS)
        self.assertTrue(all(len(e) == len(c) == 12 * YEARS for e, c in w))
        self.assertEqual(len(w), len(ps.windows(self.data, SLEEVE, YEARS)))
        self.assertEqual(len(w), re_.rolling_cagr(self.data, SLEEVE, YEARS)["n"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
