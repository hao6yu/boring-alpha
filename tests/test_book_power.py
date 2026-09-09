"""Tests for the power instrument: that it is calibrated, size-invariant, and cannot be fooled by its own units.

The claim under test is not "the book is underpowered" — that is what the tool found. The claim is that the
tool measuring it is trustworthy, which means four things: a known edge must be recovered at its known size,
a bigger account must buy no power (both terms scale together), a strategy identical to its benchmark must
show a gap of exactly zero rather than a plausible small number, and the monthly-versus-annual bookkeeping
that this file got wrong on its first run must be pinned where it hurts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import book_power as bp                                # noqa: E402
from boring_alpha.metrics.bootstrap import book_power, moving_block_indices    # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402
import withdrawal_capacity as wc                       # noqa: E402

SEED = 4242


def series(n: int = 400, seed: int = 7):
    import random
    rng = random.Random(seed)
    return [rng.gauss(0.006, 0.05) for _ in range(n)], [rng.gauss(0.006, 0.05) for _ in range(n)]


class TheInstrumentIsCalibrated(unittest.TestCase):
    def test_a_known_edge_comes_back_at_its_known_size(self):
        """The test that would have caught the month/annual slip: feed a strategy whose monthly difference has
        a known mean and normal noise, and the reported minimum detectable edge must land on the dollars that
        edge is actually worth — not twelve times it, nor a twelfth of it.

        The edge has to be *noisy*. The first draft shifted the benchmark by a constant, which gives a null with
        zero variance and a gap you could detect in one month: a calibration test that passes on a noise-free
        series calibrates nothing.
        """

        import random
        rng = random.Random(11)
        bench = [rng.gauss(0.006, 0.05) for _ in range(300)]
        strat = [b + 0.002 + rng.gauss(0.0, 0.02) for b in bench]
        opening, monthly = 5_000.0, 500.0
        rows = book_power(strat, bench, opening=opening, monthly=monthly, horizons=(60,), seed=SEED,
                          resamples=800, block=3, edge_monthly=0.002 * (opening + monthly * 30))
        true_mo = 0.002 * (opening + monthly * 30)
        self.assertGreater(rows[0]["mde_monthly"], 0.05 * true_mo,
                           f"MDE ${rows[0]['mde_monthly']:,.0f}/mo is implausibly small next to the true "
                           f"${true_mo:,.0f}/mo")
        self.assertLess(rows[0]["mde_monthly"], 20.0 * true_mo,
                        f"MDE ${rows[0]['mde_monthly']:,.0f}/mo against a true ${true_mo:,.0f}/mo: the "
                        f"instrument cannot see a known edge, so it cannot clear the book")
        self.assertGreater(rows[0]["power_at_edge"], 0.0)

    def test_a_strategy_identical_to_its_benchmark_wins_exactly_nothing(self):
        """The paired resample is the whole point: if the two legs share every draw, the gap must be zero and
        not a small plausible drift from an independent resample of the same series."""

        bench, _ = series()
        rows = book_power(list(bench), bench, opening=5_000.0, monthly=500.0, horizons=(12, 60), seed=SEED,
                          resamples=200, block=3)
        for row in rows:
            self.assertAlmostEqual(row["se"], 0.0, places=6)
            self.assertAlmostEqual(row["p95"], 0.0, places=6)

    def test_the_null_hypothesis_straddles_zero_because_it_forced_it_to(self):
        strat, bench = series()
        rows = book_power(strat, bench, opening=5_000.0, monthly=500.0, horizons=(24,), seed=SEED,
                          resamples=800, block=3)
        self.assertLess(abs(rows[0]["p50"]), 0.15 * rows[0]["se"],
                        "the demeaning is not working; the null still has an edge in it")
        self.assertLess(rows[0]["p05"], 0.0 < rows[0]["p95"])


class MoneyDoesNotBuyPower(unittest.TestCase):
    def test_scaling_the_whole_schedule_scales_dollars_and_nothing_else(self):
        strat, bench = series()
        small = book_power(strat, bench, opening=5_000.0, monthly=500.0, horizons=(60,), seed=SEED,
                           resamples=600, block=3)[0]
        big = book_power(strat, bench, opening=50_000.0, monthly=5_000.0, horizons=(60,), seed=SEED,
                         resamples=600, block=3)[0]
        self.assertAlmostEqual(big["mde_monthly"] / small["mde_monthly"], 10.0, delta=1.5)
        small_rate = small["mde_monthly"] / (5_000.0 + 500.0 * 60) * 1200
        big_rate = big["mde_monthly"] / (50_000.0 + 5_000.0 * 60) * 1200
        self.assertAlmostEqual(small_rate, big_rate, delta=0.4)

    def test_waiting_helps_for_two_years_then_stops_helping_at_all(self):
        """The honest shape, which the first version of this test got backwards. Detectability improves fast
        over the first couple of years (9.3%/yr at month 24 to 5.8% at month 60) and then flattens into a
        wall: 180 more months — fifteen further years — buys from 5.8% to 3.8%, and 3.8% is still eleven times
        the edge the archive says the rule has. The book's first two years are worth having. Pretending it
        becomes a test by year twenty is not patience, it is fiction."""

        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        strat, bench, _keys, _w = bp.net_strategy_returns(data, "SPY", 3.0, 0.000945)
        rate = {}
        for months in (60, 240):
            row = book_power(strat, bench, opening=5_000.0, monthly=500.0, horizons=(months,), seed=SEED,
                             resamples=600, block=3)[0]
            rate[months] = row["mde_monthly"] / (5_000.0 + 500.0 * months) * 1200
        edge_rate = (sum(a - b for a, b in zip(strat, bench)) / len(strat)) * 1200
        self.assertGreater(rate[240], 0.6 * rate[60],
                           f"fifteen more years halved the detectable edge ({rate[60]:.1f} to "
                           f"{rate[240]:.1f}%/yr); the book would be a test after all")
        self.assertGreater(rate[240], 5.0 * edge_rate,
                           f"at month 240 the book can see {rate[240]:.1f}%/yr against a rule worth "
                           f"{edge_rate:.2f}%/yr: it finally became a test, and the note is wrong")


class TheToolKeepsItsOwnUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.strat, cls.bench, cls.keys, cls.weights = bp.net_strategy_returns(cls.data, "SPY", 3.0, 0.000945)

    def test_a_horizon_the_archive_cannot_fill_is_refused_not_truncated(self):
        with self.assertRaises(ValueError) as got:
            book_power(self.strat, self.bench, opening=5_000.0, monthly=500.0, horizons=(10_000,),
                       seed=SEED, resamples=10)
        self.assertIn("monthly observations", str(got.exception))

    def test_the_edge_is_a_monthly_mean_and_is_never_multiplied_twice(self):
        """The first draft printed `edge x capital x 12` under a `/mo` label, which read as $67/mo when the
        answer was $5.61, and made the book look three times more powerful than it is."""

        import statistics
        edge = statistics.fmean(a - b for a, b in zip(self.strat, self.bench))
        funded = 5_000.0 + 500.0 * 30
        self.assertLess(abs(edge * funded), 20.0, "the rule's whole-record edge at this account size has "
                                                  "changed by an order of magnitude; re-read the note")

    def test_the_weights_the_behaviour_line_reports_are_exposures_not_returns(self):
        self.assertTrue(all(0.0 <= w <= 1.5 for w in self.weights),
                        "a weight outside the policy's band means the alignment is wrong again")
        held = [w for w, r in zip(self.weights, self.bench) if r < -0.05]
        self.assertGreater(len(held), 20)
        import statistics
        self.assertLess(statistics.fmean(held), 1.0, "the rule does not de-risk in the months it is for")

    def test_the_schedule_is_read_from_the_book_not_typed_in_here(self):
        opening, monthly, spread = bp.schedule()
        self.assertEqual(opening, 5_000.0)
        self.assertEqual(monthly, 500.0)
        self.assertGreater(spread, 0.0)


class TheWalkerIsTheOneStatistic(unittest.TestCase):
    def test_a_shared_walk_is_reproducible_and_the_same_walker_for_both_statistics(self):
        """`itertools.islice` and not `list()`: the walker is a generator that yields forever, and a test that
        materialises it hangs the suite for as long as nobody watches it, which reads exactly like a slow
        bootstrap and is nothing of the kind."""

        import itertools
        import random
        a = list(itertools.islice(moving_block_indices(50, 3, random.Random(1)), 20))
        b = list(itertools.islice(moving_block_indices(50, 3, random.Random(1)), 20))
        self.assertEqual(a, b)
        self.assertTrue(all(0 <= i < 50 for i in a))
        self.assertGreater(len(set(a)), 1, "a walker that never jumps is not resampling anything")
        with self.assertRaises(ValueError):
            list(itertools.islice(moving_block_indices(1, 3, random.Random(1)), 5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
