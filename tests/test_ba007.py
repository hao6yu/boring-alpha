"""Offline tests for the BA-007 cross-sectional engine: synthetic panels with hand-checkable answers, no archive, no network.

The fixtures are built so the charter's mechanics are visible to the cent: a rank-persistent world where momentum must win and its
reversal must lose; a flat-price world where only funding and fees move the book; a delisting mid-week; a volume order that decides who is
eligible and when. What is pinned is not that a strategy works — it is that the engine computes the construction the charter locked.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import math
import statistics
import sys
import tempfile
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
        funding_map[sym] = {day: funding[idx] if funding is not None else 0.0 for day in series}
    return closes, volumes, funding_map, sessions


def run(closes, volumes, funding_map, sessions, signal="MOM", **kwargs):
    traversal = engine.build_traversal(closes)
    rebalances = engine.weekly_rebalance_dates(sessions)
    weeks = engine.prepare_weeks(closes, traversal, volumes, funding_map, sessions, rebalances, signal)
    return engine.run_book(weeks, closes, traversal, funding_map, sessions, **kwargs)


class TheUniverseIsPointInTime(unittest.TestCase):
    def test_volume_order_decides_the_universe(self):
        """Top 30 of 40 by trailing median quote volume: the ten lowest-volume symbols are never eligible."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=100, extra_symbols=10)
        universe = engine.eligible_universe(closes, engine.build_traversal(closes), volumes, sessions[-1])
        self.assertEqual(len(universe), 30)
        self.assertNotIn("SYM39", universe)
        self.assertIn("SYM00", universe)

    def test_the_history_floor_excludes_young_symbols_regardless_of_volume(self):
        """A symbol listed 30 days ago with the highest volume in the panel is still ineligible: 60 days of life is the charter's price."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=100)
        young = f"SYM{30:02d}"
        closes[young] = {day: 100.0 + i for i, day in enumerate(sessions[-30:])}
        volumes[young] = {day: 99_000_000.0 for day in closes[young]}        # the highest volume in the panel
        universe = engine.eligible_universe(closes, engine.build_traversal(closes), volumes, sessions[-1])
        self.assertNotIn(young, universe)

    def test_fewer_than_the_minimum_eligible_skips_the_week(self):
        """Below MIN_ELIGIBLE scored symbols, prepare_weeks emits no week: the book simply does not exist that week."""

        closes, volumes, funding_map, sessions = make_panel(n=5, days=100)   # five symbols: below the floor of 12
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, engine.build_traversal(closes), volumes, funding_map, sessions, rebalances, "MOM")
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
        # Until the next trade the $0.5 long and $0.5 short notionals stay
        # constant at flat prices, while equity declines from payments.
        for row in live[1:7]:
            self.assertAlmostEqual(row["funding_paid"], 0.005, places=12)
        self.assertAlmostEqual(live[1]["funding"], 0.005 / 0.9995, places=12)

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
        # A full flip includes drifted notionals. It is not always exactly 2x
        # yesterday's equity; the independently tested quantity ledger prices it.
        self.assertGreater(max(flip_day_fees), 0.0009)
        self.assertAlmostEqual(book2["fees_paid_cash"], book2["traded_notional"] * 0.0005, places=12)

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
        weeks = engine.prepare_weeks(closes, engine.build_traversal(closes), volumes, funding_map, sessions, rebalances, "MOM")
        first = engine.run_book(weeks, closes, engine.build_traversal(closes), funding_map, sessions, fee_bps=5.0, scramble_seed=3)["annualized_net"]
        again = engine.run_book(weeks, closes, engine.build_traversal(closes), funding_map, sessions, fee_bps=5.0, scramble_seed=3)["annualized_net"]
        other = engine.run_book(weeks, closes, engine.build_traversal(closes), funding_map, sessions, fee_bps=5.0, scramble_seed=4)["annualized_net"]
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)

    def test_weekly_scrambles_trade_even_when_the_universe_is_unchanged(self):
        days = [START + timedelta(days=i) for i in range(15)]
        names = [f"S{i:02d}" for i in range(30)]
        closes = {name: dict.fromkeys(days, 100.0) for name in names}
        weeks = [{"date": day, "universe": names, "scores": {name: i for i, name in enumerate(names)}}
                 for day in (days[0], days[7], days[14])]
        funding = {sym: dict.fromkeys(days, 0.0) for sym in closes}
        fixed = engine.run_book(weeks, closes, engine.build_traversal(closes), funding, days, 0)
        scrambled = engine.run_book(weeks, closes, engine.build_traversal(closes), funding, days, 0, scramble_seed=3)
        self.assertAlmostEqual(fixed["turnover_one_way"], 1.0)
        self.assertGreater(scrambled["turnover_one_way"], 1.0)

    def test_weekly_book_preserves_a_flat_round_trip_in_asset_prices(self):
        days = [START + timedelta(days=i) for i in range(3)]
        closes = {"A": dict(zip(days, [100, 200, 100])),
                  "B": dict.fromkeys(days, 100), "C": dict.fromkeys(days, 100)}
        weeks = [{"date": days[0], "universe": ["A", "B", "C"], "scores": {"A": 3, "B": 2, "C": 1}}]
        funding = {sym: dict.fromkeys(days, 0.0) for sym in closes}
        book = engine.run_book(weeks, closes, engine.build_traversal(closes), funding, days, 0)
        self.assertAlmostEqual(book["terminal_equity"], 1.0)
        self.assertAlmostEqual(math.prod(1 + row["net"] for row in book["daily"]), 1.0)

    def test_absent_funding_series_cannot_be_assumed_zero(self):
        days = [START + timedelta(days=i) for i in range(2)]
        closes = {sym: dict.fromkeys(days, 100.0) for sym in ("A", "B", "C")}
        weeks = [{"date": days[0], "universe": list(closes), "scores": {"A": 3, "B": 2, "C": 1}}]
        with self.assertRaisesRegex(engine.MissingMark, "missing funding observation"):
            engine.run_book(weeks, closes, engine.build_traversal(closes), {}, days, 0)

    def test_reversed_book_is_the_exact_mirror_of_the_sides(self):
        """Same preparation, sides swapped: the reversed book's gross is the negative of the candidate's, to the float."""

        drift = [0.003 - 0.0003 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=90, drift=drift)
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, engine.build_traversal(closes), volumes, funding_map, sessions, rebalances, "MOM")
        base = engine.run_book(weeks, closes, engine.build_traversal(closes), funding_map, sessions, fee_bps=0.0)
        mirror = engine.run_book(weeks, closes, engine.build_traversal(closes), funding_map, sessions, fee_bps=0.0, reverse=True)
        # Before the second rebalance, quantities are exact negatives. Cash
        # P&L mirrors; percentage returns differ as the accounts' equity moves.
        for a, b in zip(base["daily"], mirror["daily"]):
            if a["date"] >= weeks[1]["date"]:
                break
            self.assertAlmostEqual(a["gross_pnl"], -b["gross_pnl"], places=15)


class TheBookSurvivesADelisting(unittest.TestCase):
    def test_a_disappearing_symbol_requires_verified_settlement_data(self):
        """An archive ending does not establish an executable exit price."""

        drift = [0.004 - 0.0004 * i for i in range(30)]
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, drift=drift,
                                                            dead_after=lambda idx: START + timedelta(days=70) if idx == 0 else None)
        with self.assertRaisesRegex(engine.MissingMark, "SYM00"):
            run(closes, volumes, funding_map, sessions, signal="MOM", fee_bps=5.0)

    def test_a_symbol_whose_window_contains_silence_is_not_ranked_that_week(self):
        """Silence is not a price: a symbol with no closes in its momentum window scores nothing and is excluded, not defaulted."""

        closes, volumes, funding_map, sessions = make_panel(n=30, days=90)
        holes = closes["SYM00"]
        for day in list(holes)[-9:-1]:                                       # eight of the last nine days before the end
            del holes[day]
        scores = engine.prepare_weeks(closes, engine.build_traversal(closes), volumes, funding_map, sessions, [sessions[-2]], "MOM")
        self.assertNotIn("SYM00", scores[0]["scores"])


class TheSignalDirectionsAreTheCharters(unittest.TestCase):
    def test_seven_day_return_is_not_yesterdays_return(self):
        days = [START + timedelta(days=i) for i in range(8)]
        prices = dict(zip(days, [100, 110, 120, 130, 140, 150, 160, 170]))
        self.assertAlmostEqual(engine.momentum(prices, days[-1]), 0.70)
        del prices[days[3]]
        self.assertIsNone(engine.momentum(prices, days[-1]))

    def test_missing_funding_is_not_a_zero_funding_signal(self):
        day = START + timedelta(days=3)
        self.assertIsNone(engine.carry_sum({}, day))
        observed = {day - timedelta(days=i): 0.0 for i in range(3)}
        self.assertEqual(engine.carry_sum(observed, day), 0.0)

    def test_signal_is_observed_before_execution_and_cannot_use_execution_price(self):
        closes, volumes, funding_map, sessions = make_panel(n=30, days=90)
        decision = sessions[70]
        first = engine.prepare_weeks(closes, engine.build_traversal(closes), volumes,
                                     funding_map, sessions, [decision], "MOM")
        self.assertEqual(first[0]["date"], decision + timedelta(days=1))
        self.assertEqual(first[0]["signal_date"], decision)
        closes["SYM00"][decision + timedelta(days=1)] *= 100
        second = engine.prepare_weeks(closes, engine.build_traversal(closes), volumes,
                                      funding_map, sessions, [decision], "MOM")
        self.assertEqual(first, second)

    def test_carry_longs_the_lowest_funding_as_charter_section_4_registers(self):
        """Charter §4: 'Rank ascending: the most negative ... ranks first (long side).' The first sweep graded this signal's mirror
        because the negation was missing — this pin exists so the direction can never silently flip again."""

        funding_tilt = [0.00005 * i for i in range(30)]                      # SYM00 lowest funding ... SYM29 highest
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, funding=funding_tilt)
        traversal = engine.build_traversal(closes)
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, traversal, volumes, funding_map, sessions, rebalances, "CARRY")
        self.assertTrue(weeks)
        long_side, short_side = engine.terciles(weeks[0]["universe"], weeks[0]["scores"])
        self.assertEqual(sorted(long_side), [f"SYM{i:02d}" for i in range(10)])   # the lowest-funding tercile is the long side
        self.assertEqual(sorted(short_side), [f"SYM{i:02d}" for i in range(20, 30)])

    def test_momentum_longs_the_biggest_winners_as_charter_section_4_registers(self):
        """Charter §4: momentum ranks descending — the strongest 7-day return is the long side."""

        drift = [0.004 - 0.0004 * i for i in range(30)]                      # SYM00 the strongest week
        closes, volumes, funding_map, sessions = make_panel(n=30, days=120, drift=drift)
        traversal = engine.build_traversal(closes)
        rebalances = engine.weekly_rebalance_dates(sessions)
        weeks = engine.prepare_weeks(closes, traversal, volumes, funding_map, sessions, rebalances, "MOM")
        long_side, short_side = engine.terciles(weeks[1]["universe"], weeks[1]["scores"])
        self.assertIn("SYM00", long_side)
        self.assertIn("SYM29", short_side)


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


class TheSweepEndsInArtifacts(unittest.TestCase):
    """main() is the Phase 3 entry point: the real archive sweep must produce its artifacts on the first try, so it is rehearsed offline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "perps"
        self._swap = (engine.PERPS, engine.BACKTESTS)
        engine.PERPS, engine.BACKTESTS = root, root / "backtests"
        self.addCleanup(lambda: (setattr(engine, "PERPS", self._swap[0]), setattr(engine, "BACKTESTS", self._swap[1])))
        engine.BOOTSTRAP_RESAMPLES = 100
        self.addCleanup(setattr, engine, "BOOTSTRAP_RESAMPLES", 2_000)

        global START
        START = date(2019, 11, 1)                                            # the panel must span the charter's own windows
        self.addCleanup(setattr, __import__("test_ba007"), "START", date(2024, 1, 1))
        closes, volumes, funding_map, _ = make_panel(n=30, days=2_200, drift=[0.003 - 0.0003 * i for i in range(30)],
                                                     funding=[0.0001] * 30)
        closes["BTCUSDT"] = {day: 100.0 * (1.0 + 0.0005) ** i for i, day in
                             enumerate(sorted(closes["SYM00"]))}                # the beta benchmark the real archive carries
        volumes["BTCUSDT"] = {day: 50_000_000.0 for day in closes["BTCUSDT"]}
        funding_map["BTCUSDT"] = {day: 0.0001 for day in closes["BTCUSDT"]}
        directory = engine.PERPS
        directory.mkdir(parents=True)
        with (directory / "perps_daily.csv").open("w", newline="") as handle:
            handle.write("date,symbol,open,high,low,close,base_volume,quote_volume\n")
            for sym in closes:
                for day, price in closes[sym].items():
                    handle.write(f"{day.isoformat()},{sym},{price:.8g},{price:.8g},{price:.8g},{price:.8g},1.0,"
                                 f"{volumes[sym][day]:.10g}\n")
        with (directory / "funding_events.csv").open("w", newline="") as handle:
            handle.write("ts_utc,symbol,interval_hours,rate\n")
            for sym in closes:
                for day in closes[sym]:
                    stamp = f"{day.isoformat()}T08:00:00Z"
                    handle.write(f"{stamp},{sym},8,{funding_map[sym][day]:.12g}\n")

    def test_main_writes_metrics_and_daily_csvs_for_both_signals_and_periods(self):
        argv = sys.argv
        sys.argv = ["ba007"]                                                   # main parses the process argv; the rehearsal has none
        self.addCleanup(setattr, sys, "argv", argv)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(engine.main(), 0)
        output = buffer.getvalue()
        self.assertIn("MOM verdict", output)
        self.assertIn("CARRY verdict", output)
        backtests = list(engine.BACKTESTS.iterdir())
        self.assertEqual(len(backtests), 1)
        metrics = json.loads((backtests[0] / "metrics.json").read_text())
        for name in ("MOM", "CARRY"):
            self.assertIn(name, metrics)
            self.assertIn(metrics[name]["verdict"]["verdict"], ("PASS", "FAIL"))
            for period in ("development", "validation"):
                self.assertNotIn("daily", metrics[name][period]["base"])   # the manifest stays slim; the CSVs carry the rows
                self.assertLess((backtests[0] / f"daily-{period}-{name}-base.csv").stat().st_size, 10_000_000)
                with (backtests[0] / f"daily-{period}-{name}-base.csv").open() as handle:
                    rows = list(csv.DictReader(handle))
                self.assertTrue(rows)
                for row in rows:
                    self.assertAlmostEqual(float(row["net"]),
                                           float(row["gross"]) - float(row["funding"]) - float(row["fees"]), places=15)

    def test_beta_is_in_the_metrics_when_btcusdt_is_in_the_panel(self):
        """The real archive carries BTCUSDT; the rehearsal panel must too, and beta must be a number, not a nan."""

        argv = sys.argv
        sys.argv = ["ba007"]
        self.addCleanup(setattr, sys, "argv", argv)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            engine.main()
        metrics = json.loads(next(engine.BACKTESTS.iterdir()).joinpath("metrics.json").read_text())
        for name in ("MOM", "CARRY"):
            self.assertFalse(math.isnan(metrics[name]["development"]["base"]["beta_vs_btc"]))


class TheSealedRevealIsDeliberate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "perps"
        self._swap = (engine.PERPS, engine.BACKTESTS)
        engine.PERPS, engine.BACKTESTS = root, root / "backtests"
        self.addCleanup(lambda: (setattr(engine, "PERPS", self._swap[0]), setattr(engine, "BACKTESTS", self._swap[1])))
        engine.BOOTSTRAP_RESAMPLES = 100
        self.addCleanup(setattr, engine, "BOOTSTRAP_RESAMPLES", 2_000)

        global START
        START = date(2019, 11, 1)
        self.addCleanup(setattr, __import__("test_ba007"), "START", date(2024, 1, 1))
        closes, volumes, funding_map, _ = make_panel(n=30, days=2_200, drift=[0.003 - 0.0003 * i for i in range(30)],
                                                     funding=[0.0001] * 30)
        closes["BTCUSDT"] = {day: 100.0 * (1.0 + 0.0005) ** i for i, day in enumerate(sorted(closes["SYM00"]))}
        volumes["BTCUSDT"] = {day: 50_000_000.0 for day in closes["BTCUSDT"]}
        funding_map["BTCUSDT"] = {day: 0.0001 for day in closes["BTCUSDT"]}
        directory = engine.PERPS
        directory.mkdir(parents=True)
        with (directory / "perps_daily.csv").open("w", newline="") as handle:
            handle.write("date,symbol,open,high,low,close,base_volume,quote_volume\n")
            for sym in closes:
                for day, price in closes[sym].items():
                    handle.write(f"{day.isoformat()},{sym},{price:.8g},{price:.8g},{price:.8g},{price:.8g},1.0,"
                                 f"{volumes[sym][day]:.10g}\n")
        with (directory / "funding_events.csv").open("w", newline="") as handle:
            handle.write("ts_utc,symbol,interval_hours,rate\n")
            for sym in closes:
                for day in closes[sym]:
                    handle.write(f"{day.isoformat()}T08:00:00Z,{sym},8,{funding_map[sym][day]:.12g}\n")
        self.panel = (closes, volumes, funding_map)

    def test_a_reveal_without_a_reason_is_refused_before_it_reads_a_sealed_bar(self):
        closes, volumes, funding = self.panel
        with self.assertRaises(SystemExit):
            engine.run_reveal("   ", closes, volumes, funding)

    def test_the_sealed_window_opens_only_for_carry_and_only_past_2025(self):
        closes, volumes, funding = self.panel
        out = engine.run_reveal("BA-007 section 11: both seen windows passed", closes, volumes, funding)
        self.assertNotIn("MOM", out)                                          # the failed signal's sealed sessions stay sealed
        sealed = out["sealed"]["base"]
        self.assertGreaterEqual(date.fromisoformat(sealed["first"]), date(2025, 1, 1))
        self.assertEqual(out["reveal"]["signal"].startswith("XS-CARRY"), True)

    def test_sealed_verdict_is_arithmetic(self):
        good = {"annualized_net": 0.10, "bootstrap_low": 0.03}
        result = engine.sealed_verdict(good, {"annualized_net": -0.05}, [0.01, 0.02],
                                       {"annualized_net": 0.08, "bootstrap_low": 0.02})
        self.assertEqual(result["verdict"], "PASS")
        bad = engine.sealed_verdict({"annualized_net": -0.10, "bootstrap_low": -0.20}, {"annualized_net": 0.05},
                                    [0.01], {"annualized_net": -0.08, "bootstrap_low": -0.15})
        self.assertEqual(bad["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
