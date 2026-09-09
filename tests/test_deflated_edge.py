"""Round 61: tests for the multiple-testing machinery itself.

The order matters. The statistics in `deflated_edge` are new to the repository and unvalidated by anything upstream,
so they are checked against hand-computed moments, against a seeded field of noise that must come out unremarkable,
and against a planted edge that must come out significant. A screening tool whose only output is "nothing" has not
been tested; it has been observed.
"""

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import deflated_edge as de                                 # noqa: E402
import trend_cost_test as tc                               # noqa: E402
import withdrawal_capacity as wc                           # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data     # noqa: E402


class TheNormalFunctions(unittest.TestCase):

    def test_phi_matches_the_usual_quantiles(self):
        self.assertAlmostEqual(de.phi(0.0), 0.5, places=12)
        self.assertAlmostEqual(de.phi(1.959964), 0.975, places=6)
        self.assertAlmostEqual(de.phi(-1.644854), 0.05, places=6)
        self.assertAlmostEqual(de.phi(3.0), 0.998650, places=6)

    def test_inv_phi_inverts_phi(self):
        for p in (0.001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999):
            self.assertAlmostEqual(de.phi(de.inv_phi(p)), p, places=8)
        self.assertAlmostEqual(de.inv_phi(0.975), 1.959964, places=5)
        self.assertAlmostEqual(de.inv_phi(0.025), -1.959964, places=5)

    def test_inv_phi_refuses_the_tails_it_cannot_represent(self):
        for p in (0.0, 1.0, -0.1, 1.5):
            with self.assertRaises(ValueError):
                de.inv_phi(p)


class TheExpectedMax(unittest.TestCase):

    def test_more_trials_needs_a_better_number(self):
        a = de.expected_max_sharpe(2, 246)
        b = de.expected_max_sharpe(27, 246)
        c = de.expected_max_sharpe(100, 246)
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertGreater(b, 0.0)

    def test_a_longer_sample_lowers_the_bar(self):
        self.assertGreater(de.expected_max_sharpe(27, 60), de.expected_max_sharpe(27, 246))
        self.assertGreater(de.expected_max_sharpe(27, 246), de.expected_max_sharpe(27, 2400))

    def test_a_single_trial_barely_clears_zero(self):
        """With one trial there is no selection at all, so the bar is the usual small-sample hurdle and nothing more."""

        self.assertLess(de.expected_max_sharpe(1, 246), 0.05)

    def test_it_refuses_impossible_inputs(self):
        with self.assertRaises(ValueError):
            de.expected_max_sharpe(0, 246)
        with self.assertRaises(ValueError):
            de.expected_max_sharpe(10, 2)


class TheMoments(unittest.TestCase):

    def test_hand_computed_moments_of_a_small_asymmetric_sample(self):
        """xs = [1,1,1,2]: mean 1.25, m2 0.1875, m3 0.087890625, m4 0.08203125, so skew 1.1547 (2/sqrt 3) and excess kurtosis
        −0.6667. The sample sd uses n−1 and is a different number again, which is the point of the test."""

        mu, sd, skew, kurt = de.moments([1.0, 1.0, 1.0, 2.0])
        self.assertAlmostEqual(mu, 1.25, places=12)
        self.assertAlmostEqual(sd, 0.5, places=12)
        self.assertAlmostEqual(skew, 1.154701, places=5)
        self.assertAlmostEqual(kurt, -0.666667, places=5)

    def test_a_symmetric_sample_has_no_skew(self):
        _mu, _sd, skew, kurt = de.moments([-1.0, 0.0, 1.0])
        self.assertAlmostEqual(skew, 0.0, places=12)
        self.assertAlmostEqual(kurt, -1.5, places=10)

    def test_a_flat_or_short_series_is_an_error_not_an_infinity(self):
        with self.assertRaises(ValueError):
            de.moments([0.01, 0.01, 0.01, 0.01])
        with self.assertRaises(ValueError):
            de.moments([0.01, 0.02])
        with self.assertRaises(ValueError):
            de.sharpe([0.01, 0.01, 0.01, 0.01])


class Calibration(unittest.TestCase):
    """The machinery must say "no" to noise and "yes" to an edge. Both."""

    def test_seeded_noise_with_26_columns_is_not_significant(self):
        for t in (120, 246):
            f = de.noise_field(26, t, seed=7)
            rc = de.block_bootstrap(f, [str(i) for i in range(26)], 12, 600, seed=7)
            self.assertGreater(rc["p"], 0.05,
                               f"a field of pure noise came back significant at p={rc['p']:.3f} on {t} months")

    def test_a_planted_edge_is_found_and_correctly_attributed(self):
        for t, ceiling in ((120, 0.05), (246, 0.01)):
            g = de.edge_field(26, t, seed=7, edge=0.012)
            rc = de.block_bootstrap(g, [str(i) for i in range(26)], 12, 600, seed=7)
            self.assertLess(rc["p"], ceiling,
                            f"a real 1.2%/mo edge was missed on {t} months (p={rc['p']:.3f}): this tool cannot"
                            " clear a strategy, only fail to")
            self.assertEqual(rc["winner"], "0", f"the edge was found in the wrong column: {rc['winner']}")

    def test_the_null_median_grows_with_the_number_of_columns(self):
        """More tries, higher expected maximum, even with the same data-generating process."""

        few = de.block_bootstrap(de.noise_field(4, 246, 3), [str(i) for i in range(4)], 12, 400, 3)
        many = de.block_bootstrap(de.noise_field(40, 246, 3), [str(i) for i in range(40)], 12, 400, 3)
        self.assertGreater(many["null_max_median"], few["null_max_median"])

    def test_the_seed_makes_the_answer_reproducible(self):
        f = de.noise_field(10, 246, 11)
        labels = [str(i) for i in range(10)]
        a = de.block_bootstrap(f, labels, 12, 300, 5)["p"]
        b = de.block_bootstrap(f, labels, 12, 300, 5)["p"]
        self.assertEqual(a, b)

    def test_a_ragged_panel_is_refused(self):
        with self.assertRaises(ValueError):
            de.block_bootstrap([[0.01] * 12, [0.01] * 13], ["a", "b"], 6, 20, 1)


class ArchiveFindings(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.cols, cls.keep, cls.distinct = de.trial_set(cls.data)

    def test_the_monthly_replay_of_a_daily_rule_ends_where_the_engine_says(self):
        """`trend_cost_test.run` returns aggregates, so this file replays its arithmetic to collect month ends. The
        replay must compound to the same terminal wealth, rule by rule."""

        days, rets, cl, bills, exp = tc.daily_legs(self.data, "SPY")
        for rule in tc.RULES:
            _k, m = de._monthly_from_daily(days[1:], de._daily_factors(self.data, rule), days[0])
            want = tc.run(rets, bills, tc.exposures(rule, cl, rets), exp)["wealth"]
            got = 1.0
            for r in m:
                got *= (1.0 + r)
            self.assertAlmostEqual(got, want, places=8, msg=f"{rule}: the monthly replay drifted from run()")

    def test_the_trial_set_is_what_rounds_55_to_60_ran(self):
        self.assertGreaterEqual(len(self.cols), 26)
        # Two configurations may legitimately realise the same path, so distinctness is not asserted. What is
        # asserted is that the duplication is small and that it is REPORTED rather than silently inflating N.
        n_series = len({tuple(v) for v in self.cols.values()})
        self.assertGreaterEqual(n_series, len(self.cols) - 2,
                                f"{len(self.cols)} columns collapsed to {n_series} series: too much duplication to"
                                " be real")
        self.assertIn(n_series, (len(self.cols), len(self.cols) - 1, len(self.cols) - 2))
        self.assertEqual(len(self.keep), 246)
        for v in self.cols.values():
            self.assertEqual(len(v), len(self.keep))

    def test_no_configuration_beats_the_index_on_excess_return(self):
        """The round's finding, pinned. Every information ratio is negative, so there is no best-of-N story to tell
        and the multiple-testing correction has nothing to bite on."""

        bench = self.cols[de.BENCH]
        best = None
        for label, v in self.cols.items():
            if label == de.BENCH:
                continue
            ex = [(1.0 + r) / (1.0 + b) - 1.0 for r, b in zip(v, bench)]
            mu, sd, _sk, _ku = de.moments(ex)
            if sd < 1e-3:
                continue                      # a second implementation of the benchmark itself
            ir = mu / sd
            best = ir if best is None else max(best, ir)
        self.assertIsNotNone(best)
        self.assertLess(best, 0.0,
                        f"some configuration now has a positive information ratio ({best:+.4f}) against the index;"
                        " the round's conclusion needs re-reading, not restating")

    def test_the_benchmarks_own_excess_is_exactly_zero(self):
        bench = self.cols[de.BENCH]
        ex = [(1.0 + r) / (1.0 + b) - 1.0 for r, b in zip(bench, bench)]
        self.assertEqual(max(abs(x) for x in ex), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
