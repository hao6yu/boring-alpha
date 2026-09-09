"""Tests for the mix sweep, whose whole purpose is a sample boundary.

The claim under test is not a ranking — it is that the earliest date this two-fund family can be scored at all produces a
different answer than the calendar the last four rounds used. So the tests pin the date, the boundary behaviour it exposes,
the drawdown arithmetic, and the fact that the same machinery reproduces the published recent-window numbers when pointed at
the same window.
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

import binding_payout as bp                                  # noqa: E402
import mix_sweep as ms                                       # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import tilt_brake as tb                                      # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402


class SampleBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = ms.grid(100_000.0, 10)
        cls.rows = {r["name"]: r for r in cls.o["rows"]}
        cls.bp = bp.grid(100_000.0, 10)

    def w(self, name, window="deep"):
        return self.rows[name]["windows"][window]

    def test_the_start_is_the_data_own_limit_and_not_a_date_chosen_for_its_outcome(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        series = {s: sl.legs(d, s) for s in ("SPY", "QQQ")}
        self.assertEqual(self.o["deep"], max(sorted(series[s])[sl.WARMUP] for s in ("SPY", "QQQ")))
        self.assertLess(self.o["deep"], dt.date(2002, 8, 1), "the round's premise is that scoring starts before 2002-08")

    def test_the_growth_collapse_is_inside_the_window_it_was_put_there_to_test(self):
        self.assertLessEqual(abs(self.w("mix_100")["dd"]), 1.0)
        self.assertLess(self.w("mix_100")["dd"], -0.80, "no −82% episode in the record; the grid is testing the wrong decade")
        self.assertGreater(self.w("mix_00")["dd"], -0.60, "the S&P leg fell more than the 2000-02 record allows")

    def test_drawdown_is_measured_on_the_balance_and_not_on_a_price(self):
        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=k) for k in range(5)]
        self.assertAlmostEqual(ms.drawdown(dates, [1.1, 1.2, 0.6, 0.9, 1.3]), 0.6 / 1.2 - 1.0, places=12)
        self.assertAlmostEqual(ms.drawdown(dates, [1.0, 2.0, 4.0]), 0.0)

    def test_no_static_mix_meets_the_failure_budget_on_the_deep_record_at_any_payout(self):
        """The finding, as an assertion. Every static mix fails on at least 5% of ten-year windows even when the withdrawal
        is one dollar a month, which means the budget is unreachable rather than merely tight — and every capacity number
        that looked comfortable in rounds 75 to 77 was comfortable on a sample starting 2005-09-06."""

        for name, weight, brake in ms.MIXES:
            if brake:
                continue
            d = self.w(name)
            self.assertFalse(d["capacity_meets_budget"], name)
            self.assertGreaterEqual(d["floor_fail"], 0.05, name)

    def test_the_only_rows_that_fund_the_deep_record_are_the_braked_ones(self):
        funded = [r["name"] for r in self.o["rows"] if self.w(r["name"])["capacity_meets_budget"]]
        self.assertEqual(funded, ["brake_50", "brake_75"])
        for name in funded:
            self.assertGreater(self.w(name)["floor_fail"], 0.0 - 1e-12)
            self.assertGreater(self.w(name)["dd"], -0.35, f"{name}: a brake that still falls 80% is not a brake")
            self.assertLess(self.w(name)["safe"], 0.5 * self.o["scale"], f"{name} costs most of the recent capacity")

    def test_failure_at_a_dollar_a_month_rises_with_the_growth_weight(self):
        """The tilt's premium is payment for tail risk, visible the moment the tail is inside the sample. Measured at $1/mo,
        where the withdrawal itself cannot be the cause of a failure."""

        static = sorted((r for r in self.o["rows"] if not r["brake"]), key=lambda r: r["qqq"])
        p = [self.w(r["name"])["floor_fail"] for r in static]
        self.assertEqual(p, sorted(p), f"not monotone: {p}")
        self.assertGreater(p[-1], p[0])
        self.assertTrue(ms._monotone(static))

    def test_the_recent_window_still_reproduces_the_numbers_three_rounds_published(self):
        """The point of the exercise was to widen the sample, not to break the old one. The same three books, priced through
        this file's marks and through `binding_payout`'s, must land on the same capacity on the window both can see."""

        for name, other in (("mix_00", "spy_only"), ("mix_50", bp.CONTROL), ("mix_100", "qqq_only")):
            row = next(r for r in self.bp["rows"] if r["name"] == other)
            self.assertAlmostEqual(self.w(name, "recent")["safe"], row["windows"]["recent"]["safe"], places=6, msg=name)

    def test_the_payout_levels_are_dollars_and_more_withdrawal_never_buys_safety(self):
        for m, dollars in self.o["payouts"].items():
            self.assertAlmostEqual(dollars, m * self.o["scale"], places=2)
            self.assertGreater(dollars, 100.0)
        for r in self.o["rows"]:
            for window in ("deep", "recent"):
                p = [self.w(r["name"], window)["p_fails"][m] for m in ms.MULTIPLES]
                self.assertEqual(p, sorted(p), f"{r['name']} {window}")

    def test_the_tail_flags_are_the_cells_recomputed_rather_than_a_second_opinion(self):
        ctl = self.w(bp.CONTROL if bp.CONTROL in self.rows else ms.CONTROL)
        for name in self.rows:
            d = self.w(name)
            self.assertEqual(self.rows[name]["worse_tail"], d["p_fails"][1.00] > ctl["p_fails"][1.00], name)
            self.assertEqual(self.rows[name]["safer_tail"], d["p_fails"][1.00] < ctl["p_fails"][1.00], name)
            self.assertIn(str(d["counts"][1.00]), self.rows[name]["verdict"], name)

    def test_the_verdict_names_the_capacity_the_cell_holds(self):
        for name in ("mix_50", "brake_50"):
            d = self.w(name)
            want = "none" if not d["capacity_meets_budget"] else "$%.2f" % d["safe"]
            self.assertTrue(self.rows[name]["verdict"].startswith(want), self.rows[name]["verdict"])


class Marks(unittest.TestCase):
    def setUp(self):
        # QQQ has no reading for February, and both sleeves are under in March.
        self.sig = {"SPY": {(2020, 1): 1.0, (2020, 2): 0.0, (2020, 3): 0.0},
                    "QQQ": {(2020, 1): 1.0, (2020, 3): 0.0}}

    def test_a_static_mix_is_the_same_every_month_and_always_fully_invested(self):
        mk = ms.mark_for(0.25, False, self.sig, [(2020, 1), (2020, 2), (2020, 3)])
        self.assertEqual(sorted(mk), [(2020, 1), (2020, 2), (2020, 3)])
        for v in mk.values():
            self.assertAlmostEqual(sum(v.values()), 1.0)
            self.assertAlmostEqual(v["QQQ"], 0.25)

    def test_a_brake_needs_both_averages_and_goes_to_nothing_not_to_a_guess(self):
        mk = ms.mark_for(0.5, True, self.sig, [(2020, 1), (2020, 2), (2020, 3)])
        self.assertEqual(mk[(2020, 1)], {"SPY": 0.5, "QQQ": 0.5})
        self.assertNotIn((2020, 2), mk, "one sleeve answered and the other was silent; the month must produce no decision")
        self.assertIn((2020, 2), ms.mark_for(0.5, False, self.sig, [(2020, 2)]),
                      "the same month needs no signal at all when nothing is braked")
        self.assertEqual(mk[(2020, 3)], {}, "both sleeves under: the book goes to cash, which is an empty dict")

    def test_weights_never_exceed_the_book_and_the_brake_reaches_zero(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        series = {s: sl.legs(d, s) for s in ("SPY", "QQQ")}
        sig = {s: sl.month_signal(sorted(series[s]), series[s], "start") for s in ("SPY", "QQQ")}
        dates = [x for x in sorted(set(series["SPY"]) & set(series["QQQ"])) if x >= ms.deep_start(series)]
        months = sorted({(x.year, x.month) for x in dates})
        for name, weight, brake in ms.MIXES:
            w = tb.weights_from_marks(series, dates, ms.mark_for(weight, brake, sig, months))
            tot = [sum(w[s][i] for s in w) for i in range(len(dates))]
            self.assertLessEqual(max(tot), 1.0 + 1e-12, name)
            self.assertGreaterEqual(min(tot), -1e-12, name)
            if brake:
                self.assertLess(min(tot), 0.01, f"{name}: the brake never reached cash")

    def test_the_result_is_serialisable_so_the_next_round_can_read_it(self):
        o = ms.grid(100_000.0, 10)
        back = json.loads(json.dumps({k: str(v) if isinstance(v, dt.date) else v for k, v in o.items()
                                      if k != "rows"}, default=str))
        self.assertEqual(back["scale"], o["scale"])
        self.assertEqual(sorted(back["payouts"]), [str(m) for m in ms.MULTIPLES])


if __name__ == "__main__":
    unittest.main()
