"""Tests for the cadence sweep and for the generalised lag it is built on.

The sweep is only meaningful if a weekly plan and a monthly plan are charged the same delay between reading and trading, so
most of the effort here goes on `sl.cadence_carry` — reproduced against `sl.carry` day for day, with the two kinds of "no
answer" kept distinct — and on the claim that the sweep's own winner is not measurable. The finding is asserted as a number:
schedules clear the bar and none clears the spread of the family it was picked from.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cadence_sweep as cs                                   # noqa: E402
import correction_table as ct                                # noqa: E402
import mix_sweep as ms                                       # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import trend_cost_test as tc                                 # noqa: E402


class TheLag(unittest.TestCase):
    def setUp(self):
        self.dates = [dt.date(2019, 1, 1) + dt.timedelta(days=k) for k in range(400)]
        self.starts = [i for i, d in enumerate(self.dates)
                       if i == 0 or (d.year, d.month) != (self.dates[i - 1].year, self.dates[i - 1].month)]

    def marks(self, present=None):
        mk = {(self.dates[i].year, self.dates[i].month): (1.0 if self.dates[i].month % 3 else 0.0)
              for i in self.starts}
        if present is not None:
            mk = {k: v for k, v in mk.items() if k[1] in present}
        return mk

    def by_index(self, mk):
        return {i: ({"X": mk[k]} if (k := (self.dates[i].year, self.dates[i].month)) in mk else None)
                for i in self.starts}

    def test_the_generalised_lag_is_the_published_one_exactly(self):
        """Round 69's rule: a reimplementation is not trusted, it is differentially tested. Every day of the synthetic
        record must agree with `carry`, which is what every published number in this repository was produced with."""

        mk = self.marks()
        self.assertEqual(sl.carry(mk, self.dates),
                         sl.cadence_carry(self.dates, self.by_index(mk), ("X",))["X"])
        sparse = self.marks(present=(1, 2, 4, 7, 8, 9, 10, 12))
        self.assertEqual(sl.carry(sparse, self.dates),
                         sl.cadence_carry(self.dates, self.by_index(sparse), ("X",))["X"])

    def test_no_answer_and_an_answer_to_sell_everything_are_different_things(self):
        """One series, four scheduled days, every case: nothing held before the first decision, the first decision in force
        one period later, a declined day holding, and an empty decision flattening the book only once its own period has
        passed. Conflating "declined" with "flat" would let a missing reading sell the portfolio."""

        got = sl.cadence_carry(self.dates, {0: {"X": 1.0}, 10: None, 20: {}, 30: {"X": 1.0}, 40: None}, ("X",))["X"]
        self.assertEqual(got[0:10], [0.0] * 10, "before any decision answered, nothing is held")
        self.assertEqual(set(got[10:20]), {1.0}, "the decision read at day 0 is in force in the next period")
        self.assertEqual(set(got[20:30]), {1.0}, "a scheduled day that declined holds the previous weight")
        self.assertEqual(got[30:40], [0.0] * 10, "an empty decision is flat, which is not the same as declining")
        self.assertEqual(set(got[40:50]), {1.0}, "the decision read at day 30 arrives a period late, as every one does")

    def test_nothing_before_the_first_decision_is_held(self):
        got = sl.cadence_carry(self.dates, {50: {"X": 1.0}}, ("X",))["X"]
        self.assertEqual(got[:60], [0.0] * 60)

    def test_a_reading_never_trades_on_the_day_it_was_taken(self):
        """The no-lookahead property, tested directly rather than inherited from a convention: on a decision day and the day
        after it, the weight in force is still the previous period's."""

        mk = {0: {"X": 0.0}, 10: {"X": 1.0}, 20: {"X": 0.0}}
        got = sl.cadence_carry(self.dates, mk, ("X",))["X"]
        self.assertEqual(got[10], 0.0, "the weight on the day the decision is read must not be that decision")
        self.assertEqual(got[11], 0.0)
        self.assertEqual(got[20], 1.0, "the previous decision is what is in force, one period after it was read")


class TheSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = cs.grid(100_000.0, 10)
        cls.rows = {(r["plan"], r["cadence"]): r for r in cls.o["rows"]}
        cls.mix = ms.grid(100_000.0, 10)

    def row(self, plan, cadence):
        return self.rows[(plan, cadence)]

    def test_the_static_rows_reproduce_the_previous_round_through_different_machinery(self):
        """The sweep builds constant weights by hand; round 78 built them through monthly marks. Two constructions of the
        same book must give the same capacity, or one of the two files is quietly charging something the other is not."""

        mixed = {r["name"]: r for r in self.mix["rows"]}
        for name, plan in (("mix_50", "static_50"), ("mix_100", "static_100")):
            for window in ("deep", "recent"):
                self.assertAlmostEqual(self.row(plan, None)["windows"][window]["safe"],
                                       mixed[name]["windows"][window]["safe"], places=6, msg=f"{plan} {window}")
                self.assertAlmostEqual(self.row(plan, None)["windows"][window]["p_fails"][round(self.o["scale"], 2)],
                                       mixed[name]["windows"][window]["p_fails"][1.00], places=6)

    def test_the_calendar_comparator_is_read_from_the_tool_that_measured_it(self):
        mixed = {r["name"]: r for r in self.mix["rows"]}
        self.assertAlmostEqual(self.o["calendar_brake"]["recent"],
                               mixed["brake_50"]["windows"]["recent"]["safe"], places=6)
        self.assertAlmostEqual(self.o["calendar_brake"]["deep"], mixed["brake_50"]["windows"]["deep"]["safe"], places=6)

    def test_anchoring_the_same_signal_to_the_calendar_moves_capacity_more_than_the_bar_does(self):
        """Schedule anchoring is not a modelling detail; it is larger than the effect the sweep is looking for, which is why
        the sweep declines to promote a winner."""

        there = self.row("brake_50", 21)["windows"]["recent"]["safe"]
        self.assertGreater(abs(self.o["calendar_brake"]["recent"] - there), ct.BAR,
                           "the report claims anchoring outweighs the bar; the claim must be true")

    def test_the_finding_is_pinned_and_it_is_not_a_winner(self):
        self.assertEqual(self.o["pass_spread"], 0, "a schedule cleared its family spread; the round's conclusion changed")
        self.assertGreater(self.o["pass_bar"], 0, "the pre-registered bar was met by nobody, which is also news")
        self.assertLess(self.o["pass_bar"], sum(1 for r in self.o["rows"] if r["cadence"] is not None))

    def test_a_spread_is_reported_for_every_plan_and_is_the_family_recomputed(self):
        for plan in set(r["plan"] for r in self.o["rows"]):
            family = [r for r in self.o["rows"] if r["plan"] == plan]
            want = max(r["windows"]["recent"]["safe"] for r in family) - \
                min(r["windows"]["recent"]["safe"] for r in family)
            for r in family:
                self.assertAlmostEqual(r["spread"], want, places=9, msg=plan)

    def test_reading_more_often_switches_more_often(self):
        for plan in cs.PLANS:
            per_year = [self.row(plan, k)["windows"]["recent"]["switches_yr"] for k in cs.CADENCES]
            self.assertGreaterEqual(per_year[0], per_year[-1], plan)
            self.assertGreater(per_year[0], 0.0, plan)

    def test_no_weight_ever_exceeds_the_book_and_a_brake_actually_flattens_it(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        import withdrawal_capacity as wc
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        series = {s: sl.legs(data, s) for s in ("SPY", "QQQ")}
        dates = [d for d in sorted(set(series["SPY"]) & set(series["QQQ"])) if d >= cs.ms.deep_start(series)]
        for plan in cs.PLANS:
            for cadence in cs.CADENCES:
                w = cs.weights_for(plan, series, dates, cadence)
                tot = [w["SPY"][i] + w["QQQ"][i] for i in range(len(dates))]
                self.assertLessEqual(max(tot), 1.0 + 1e-12, f"{plan} {cadence}")
                self.assertGreaterEqual(min(tot), -1e-12, f"{plan} {cadence}")
                self.assertLess(min(tot), 0.01, f"{plan} {cadence}: never went flat, so never took the risk off")

    def test_a_schedule_stays_in_cash_until_its_longest_lookback_can_answer(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        import withdrawal_capacity as wc
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        series = {s: sl.legs(data, s) for s in ("SPY", "QQQ")}
        dates = [d for d in sorted(set(series["SPY"]) & set(series["QQQ"])) if d >= cs.ms.deep_start(series)]
        for plan, need in cs.LOOKBACKS.items():
            w = cs.weights_for(plan, series, dates, 5)
            self.assertEqual(sum(w["SPY"][:need]) + sum(w["QQQ"][:need]), 0.0, plan)

    def test_the_scheduled_days_are_the_schedule_and_nothing_else(self):
        self.assertEqual(cs.decision_days(23, 5), [0, 5, 10, 15, 20])
        self.assertEqual(cs.decision_days(4, 21), [0])

    def test_the_moving_average_is_a_trailing_mean_and_stays_silent_until_it_is_full(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        got = cs.moving_average(xs, 3)
        self.assertEqual(got[:2], [None, None])
        self.assertEqual(got[2:], [2.0, 3.0, 4.0])

    def test_a_mark_inside_a_lookback_is_no_mark_and_a_flat_mark_is_a_mark(self):
        dates = [dt.date(2000, 1, 2) + dt.timedelta(days=k) for k in range(300)]
        lin = [100.0 * (1.001 ** k) for k in range(300)]
        falls = [100.0 * (0.999 ** k) for k in range(300)]
        closes = {"SPY": lin, "QQQ": falls}
        mas = {s: cs.moving_average(closes[s], sl.WARMUP) for s in closes}
        self.assertIsNone(cs.mark_at("brake_50", {}, dates, 10, closes, mas))
        self.assertEqual(cs.mark_at("brake_50", {}, dates, 250, closes, mas), {"SPY": 0.5, "QQQ": 0.5},
                         "one sleeve above its average is not a reason to sell everything")
        under = {"SPY": falls, "QQQ": falls}
        mas2 = {s: cs.moving_average(under[s], sl.WARMUP) for s in under}
        self.assertEqual(cs.mark_at("brake_50", {}, dates, 250, under, mas2), {}, "both under: flat is the decision")
        self.assertEqual(cs.mark_at("static_50", {}, dates, 1, closes, mas), {"SPY": 0.5, "QQQ": 0.5})

    def test_the_result_is_serialisable(self):
        back = json.loads(json.dumps({k: (str(v) if isinstance(v, dt.date) else v)
                                      for k, v in self.o.items() if k != "rows"}, default=str))
        self.assertAlmostEqual(back["scale"], self.o["scale"], places=6)
        self.assertEqual(sorted(back["calendar_brake"]), ["deep", "recent"])


if __name__ == "__main__":
    unittest.main()
