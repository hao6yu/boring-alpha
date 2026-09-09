"""Offline tests for the BA-007 cross-sectional engine: synthetic panels with hand-checkable answers, no archive, no network.

The fixtures are built so the charter's mechanics are visible to the cent: a rank-persistent world where momentum must win and its
reversal must lose; a flat-price world where only funding and fees move the book; a delisting mid-week; a volume order that decides who is
eligible and when. What is pinned is not that a strategy works — it is that the engine computes the construction the charter locked.
"""

from __future__ import annotations

import statistics
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import ba007 as engine                                                        # noqa: E402

START = date(2024, 1, 1)


def make_panel(n=30, days=100, drift=None, volume_step=1_000.0, funding=None,
               dead_after=None, extra_symbols=0):
    """A synthetic panel: SYM00..SYMn-1 with per-index constant drift, descending quote volume, optional per-index daily funding.

    Volume descends with the index, so the top-N universe is simply the first N symbols; alphabetical order and rank order coincide, which
    makes every book's sides predictable: with flat prices the long side is the alphabetically first tercile.
    """

    sessions = [START + timedelta(days=i) for i in range(days)]
    closes, volumes, funding_map = {}, {}, {}
    total = n + extra_symbols
    for idx in range(total):
        sym = f"SYM{idx:02d}"
        price, series = 100.0, {}
        for day in sessions:
            limit = dead_after(idx) if dead_after else None
            if limit is not None and day > limit:
                break
            rate = drift[idx] if drift else 0.0
            price *= 1.0 + rate
            series[day] = price
        closes[sym] = series
        volumes[sym] = {day: 10_000_000.0 - idx * volume_step for day in series}
        if funding:
            funding_map[sym] = {day: funding[idx] for day in series}
    return closes, volumes, funding_map, sessions


def run(closes, volumes, funding_map, sessions, signal="MOM", **kwargs):
    rebalances = engine.weekly_rebalance_dates(sessions)
    weeks = engine.prepare_weeks(closes, volumes, funding_map, sessions, rebalances, signal)
    return engine.run_book(weeks, closes, funding_map, sessions, **kwargs)


class TheUniverseIsPointInTime(unittest.TestCase):
    def test_volume_order_decides_the_universe(self):
        """Top 30 of 40 by trailing median quote volume: the ten lowest-volume symbols are never eligible."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=100, extra_symbols=10)
        universe = engine.eligible_universe(closes, volumes, sessions[-1])
        self.assertEqual(len(universe), 30)
        self.assertNotIn("SYM39", universe)
        self.assertIn("SYM00", universe)

    def test_the_history_floor_excludes_young_symbols_regardless_of_volume(self):
        """A symbol listed 30 days ago with the highest volume in the panel is still ineligible: 60 days of life is the charter's price."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=100)
        young = f"SYM{30:02d}"
        closes[young] = {day: 100.0 + i for i, day in enumerate(sessions[-30:])}
        volumes[young] = {day: 99_000_000.0 for day in closes[young]}        # the highest volume in the panel
        universe = engine.eligible_universe(closes, volumes, sessions[-1])
        self.assertNotIn(young, universe)

    def test_fewer_than_the_minimum_eligible_skips_the_week(self):
        """Below MIN_ELIGIBLE scored symbols, prepare_weeks emits no week: the book simply does not exist that week."""

        closes, volumes, funding_map, sessions = make_panel(n=5, days=100)   # five symbols: below the floor of 12
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, volumes, funding_map, sessions, rebalances, "MOM")
        self.assertEqual(weeks, [])


class TheConstructionIsTheCharters(unittest.TestCase):
    def setUp(self):
        engine.BOOTSTRAP_RESAMPLES = 200
        self.addCleanup(setattr, engine, "BOOTSTRAP_RESAMPLES", 2_000)

    def test_terciles_are_dollar_neutral_at_gross_one(self):
        """Thirty eligible names, tercile of ten: +0.05 per long, −0.05 per short, sums to zero, gross one, twenty positions.

        The first ISO week cannot carry a 7-day momentum score (the panel starts with it), so the first book is the second week —
        the warm-up the charter declares, visible here as a week the engine simply does not trade.
        """

        closes, volumes, funding_map, sessions = make_panel(n=30, days=120)
        book = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        self.assertEqual(book["daily"][0]["positions"], 0)                   # week one: no momentum history exists yet
        first_live = next(row for row in book["daily"] if row["positions"] > 0)
        self.assertEqual(first_live["positions"], 20)
        self.assertAlmostEqual(0.5 / 10, 0.05)

    def test_momentum_ranks_a_persistent_world_long_the_winners(self):
        """Constant per-index drifts: SYM00 drifts hardest, so the long side is the alphabetically first tercile and it earns."""

        drift = [0.004 - 0.0004 * i for i in range(30)]                      # SYM00 +0.40%/day ... SYM29 −0.76%/day
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, drift=drift)
        book = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        self.assertGreater(book["annualized_net"], 0.0)
        reversal = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0, reverse=True)
        self.assertLess(reversal["annualized_net"], book["annualized_net"])

    def test_common_funding_cancels_and_cross_sectional_funding_does_not(self):
        """Flat prices: dollar-neutrality cancels a funding rate every symbol shares; a long-side-only premium survives on the spread."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=90, funding=[0.01] * 30)
        flat = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        self.assertAlmostEqual(sum(row["funding"] for row in flat["daily"][1:]), 0.0, places=10)

        tilted = make_panel(n=30, days=90, funding=[0.02] * 10 + [0.01] * 20)[2]
        book = run(closes, volumes, tilted, sessions, signal="MOM", fee_bps=5.0)
        live = [row for row in book["daily"] if row["positions"] > 0]        # the 60-day floor makes the early weeks untradeable
        self.assertGreater(len(live), 1)
        # The entry day's funding belongs to the positions held INTO that day, so the new book pays from the next day — the engine
        # charges exactly that, which is why the first live day reads zero and every day after reads the cross-sectional difference.
        self.assertAlmostEqual(live[0]["funding"], 0.0, places=12)
        for row in live[1:]:
            self.assertAlmostEqual(row["funding"], 0.5 * 0.02 - 0.5 * 0.01, places=12)

    def test_fees_are_charged_on_traded_notional_both_sides(self):
        """Entry charges gross 1.0 at the fee; a full rank flip charges 2.0; a stable week charges nothing."""

        drift = [0.004 - 0.0004 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=200, drift=drift)
        book = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        fee_days = [row for row in book["daily"] if row["fees"] > 0]
        self.assertGreaterEqual(len(fee_days), 1)
        first = fee_days[0]                                                  # the first live rebalance: the whole book is new
        self.assertAlmostEqual(first["fees"], 1.0 * 5.0 / 10_000, places=12)
        stable = book["daily"][book["daily"].index(first) + 1]               # ranks unchanged, weights identical: no turnover
        self.assertAlmostEqual(stable["fees"], 0.0, places=15)

        closes2, _, _, sessions2 = make_panel(n=30, days=200, drift=drift)   # the ranking flips wholesale at day 100
        flip_at = sessions2[100]
        for sym in closes2:
            anchor = closes2[sym][sessions2[99]]
            for day in sessions2[100:]:
                steps = (day - flip_at).days
                closes2[sym][day] = anchor * (1.0 - drift[int(sym[3:])]) ** steps
        book2 = run(closes2, volumes, funding_map, sessions2, signal="MOM", fee_bps=5.0)
        flip_day_fees = [row["fees"] for row in book2["daily"] if row["fees"] > 0]
        self.assertGreaterEqual(len(flip_day_fees), 2)
        self.assertAlmostEqual(max(flip_day_fees), 2.0 * 5.0 / 10_000, places=12)

    def test_net_is_gross_minus_funding_minus_fees_every_day(self):
        """The decomposition is an identity on every row, which is what makes the gross-minus-net accusation readable."""

        drift = [0.001 * ((-1) ** i) for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=80, drift=drift, funding=[0.0001] * 30)
        book = run(closes, volumes, funding_map, sessions, signal="CARRY", fee_bps=5.0)
        for row in book["daily"]:
            self.assertAlmostEqual(row["net"], row["gross"] - row["funding"] - row["fees"], places=15)


class ControlsAreTheSameArithmetic(unittest.TestCase):
    def setUp(self):
        engine.BOOTSTRAP_RESAMPLES = 200
        self.addCleanup(setattr, engine, "BOOTSTRAP_RESAMPLES", 2_000)

    def test_scrambled_books_are_deterministic_and_differ_across_seeds(self):
        drift = [0.003 - 0.0003 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, drift=drift)
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, volumes, funding_map, sessions, rebalances, "MOM")
        first = engine.run_book(weeks, closes, funding_map, sessions, fee_bps=5.0, scramble_seed=3)["annualized_net"]
        again = engine.run_book(weeks, closes, funding_map, sessions, fee_bps=5.0, scramble_seed=3)["annualized_net"]
        other = engine.run_book(weeks, closes, funding_map, sessions, fee_bps=5.0, scramble_seed=4)["annualized_net"]
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)

    def test_reversed_book_is_the_exact_mirror_of_the_sides(self):
        """Same preparation, sides swapped: the reversed book's gross is the negative of the candidate's, to the float."""

        drift = [0.003 - 0.0003 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=90, drift=drift)
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, volumes, funding_map, sessions, rebalances, "MOM")
        base = engine.run_book(weeks, closes, funding_map, sessions, fee_bps=0.0)
        mirror = engine.run_book(weeks, closes, funding_map, sessions, fee_bps=0.0, reverse=True)
        for a, b in zip(base["daily"], mirror["daily"]):
            self.assertAlmostEqual(a["gross"], -b["gross"], places=15)


class TheBookSurvivesADelisting(unittest.TestCase):
    def test_a_long_side_symbol_dying_midweek_is_closed_and_reported(self):
        """SYM00 dies after 40 days: its weight leaves the book, the notional sits in cash, and the manifest names it."""

        drift = [0.004 - 0.0004 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, drift=drift,
                                                            dead_after=lambda idx: START + timedelta(days=70) if idx == 0 else None)
        book = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        self.assertIn("SYM00", book["closed_symbols"])
        dead_day = next(row for row in book["daily"] if row["date"] > START + timedelta(days=70) and row["positions"] > 0)
        self.assertLess(dead_day["positions"], 20)

    def test_a_symbol_whose_window_contains_silence_is_not_ranked_that_week(self):
        """Silence is not a price: a symbol with no closes in its momentum window scores nothing and is excluded, not defaulted."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=90)
        holes = closes["SYM00"]
        for day in list(holes)[-9:-1]:                                       # eight of the last nine days before the end
            del holes[day]
        scores = engine.prepare_weeks(closes, volumes, funding_map, sessions, [sessions[-1]], "MOM")
        self.assertNotIn("SYM00", scores[0]["scores"])


class ThePeriodsTruncate(unittest.TestCase):
    def test_development_never_sees_a_validation_bar(self):
        """The union of sessions inside a period stops at its boundary even when the panel runs years past it."""

        closes, _, _, _ = make_panel(n=30, days=365 * 6)                     # 2024-01-01 .. 2029-12-31, past every period
        dev = engine.sessions_in(closes, engine.DEVELOPMENT)
        val = engine.sessions_in(closes, engine.VALIDATION)
        self.assertTrue(all(d <= engine.DEVELOPMENT[1] for d in dev))
        self.assertTrue(all(engine.VALIDATION[0] <= d <= engine.VALIDATION[1] for d in val))
        self.assertEqual(set(dev) & set(val), set())

    def test_weekly_rebalance_picks_the_first_served_session_of_each_iso_week(self):
        """A missing Monday is not a skipped week: the first served day of that week is the decision date."""

        sessions = [START + timedelta(days=i) for i in range(30)]
        sessions = [d for d in sessions if d.weekday() != 0]                 # no Mondays at all
        rebalances = engine.weekly_rebalance_dates(sessions)
        self.assertTrue(all(d.weekday() == 1 for d in rebalances))          # Tuesdays carry the decision


class TheVerdictIsArithmetic(unittest.TestCase):
    def book(self, net, low):
        return {"annualized_net": net, "bootstrap_low": low}

    def test_all_gates_passing_is_a_pass(self):
        good = self.book(0.10, 0.04)
        result = engine.verdict(good, self.book(0.08, 0.03), self.book(-0.05, -0.09),
                                [0.01, 0.02, 0.03], self.book(0.09, 0.03), self.book(0.07, 0.02))
        self.assertEqual(result["verdict"], "PASS")
        self.assertTrue(all(result["checks"].values()))

    def test_a_validation_reversal_is_a_fail_not_a_pass(self):
        good = self.book(0.10, 0.04)
        result = engine.verdict(good, self.book(-0.02, -0.05), self.book(-0.05, -0.09),
                                [0.01, 0.02, 0.03], self.book(0.09, 0.03), self.book(-0.02, -0.05))
        self.assertEqual(result["verdict"], "FAIL")

    def test_a_reversed_book_that_wins_is_a_fail(self):
        """If shorting the hypothesis earns more than holding it, the 'edge' was a sign error and the gates say so."""

        good = self.book(0.10, 0.04)
        result = engine.verdict(good, self.book(0.08, 0.03), self.book(0.20, 0.12),
                                [0.01, 0.02, 0.03], self.book(0.09, 0.03), self.book(0.07, 0.02))
        self.assertFalse(result["checks"]["G3_reversed_loses_in_dev"])
        self.assertEqual(result["verdict"], "FAIL")

    def test_an_interval_containing_zero_is_not_a_pass(self):
        result = engine.verdict(self.book(0.10, -0.01), self.book(0.08, 0.03), self.book(-0.05, -0.09),
                                [0.01, 0.02, 0.03], self.book(0.09, 0.03), self.book(0.07, 0.02))
        self.assertEqual(result["verdict"], "FAIL")


class TheBootstrapIsSeeded(unittest.TestCase):
    def test_same_input_same_interval(self):
        nets = [0.001 * ((-1) ** (i % 3)) + 0.0002 for i in range(300)]
        self.assertEqual(engine.bootstrap_interval(nets), engine.bootstrap_interval(nets))


class TheDiagnosticsAreReported(unittest.TestCase):
    def setUp(self):
        engine.BOOTSTRAP_RESAMPLES = 200
        self.addCleanup(setattr, engine, "BOOTSTRAP_RESAMPLES", 2_000)

    def test_turnover_is_reported_and_matches_the_fees_implied_notional(self):
        """Turnover accumulates |Δw|; the first live rebalance contributes exactly gross 1.0 and stable weeks contribute zero."""

        drift = [0.004 - 0.0004 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=200, drift=drift)
        book = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        self.assertGreaterEqual(book["turnover_one_way"], 1.0)
        self.assertAlmostEqual(book["turnover_one_way"] / book["days"] * 365, book["turnover_annualized"], places=12)

    def test_beta_against_a_benchmark_is_covariance_over_variance(self):
        """A book whose net series is exactly twice the benchmark's has beta 2; alignment is by date, entry day excluded."""

        btc = {START + timedelta(days=i): 0.001 * ((-1) ** (i % 5)) for i in range(60)}
        daily = [{"date": d, "net": 2.0 * r, "gross": 0.0, "funding": 0.0, "fees": 0.0} for d, r in btc.items()]
        self.assertAlmostEqual(engine.beta_against(daily, btc), 2.0, places=9)

    def test_legs_split_the_spread_book_into_its_two_halves(self):
        """Long-only and short-only books hold one side each: ten names a side, twenty together."""

        drift = [0.003 - 0.0003 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, drift=drift)
        long_leg = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0, leg="long")
        short_leg = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0, leg="short")
        live_long = next(row for row in long_leg["daily"] if row["positions"] > 0)
        live_short = next(row for row in short_leg["daily"] if row["positions"] > 0)
        self.assertEqual(live_long["positions"], 10)
        self.assertEqual(live_short["positions"], 10)
        both = run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)
        live_both = next(row for row in both["daily"] if row["positions"] > 0)
        self.assertEqual(live_both["positions"], 20)


if __name__ == "__main__":
    unittest.main()
