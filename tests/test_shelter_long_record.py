"""Tests for `tools/shelter_long_record.py` — the two-asset engine, the two readings of "monthly", and the longer record.

The load-bearing test is the first one: this file's engine, handed round 58's own weights over round 58's own window,
must return $593.13. Everything else in the file is downstream of that, including the claim that the published figure is
the most flattering of four readings of the same rule.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                            # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import shelter_test as st                                    # noqa: E402
import trend_cost_test as tc                                 # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data      # noqa: E402

SINCE = dt.date(2002, 8, 1)


def synth(pairs, bills=None):
    """A date-keyed close series from (date, close) pairs, with an optional bill factor carried on each date."""

    bills = bills or {}
    return {d: (c, bills.get(d, 0.0)) for d, c in pairs}


class TheEngine(unittest.TestCase):
    def setUp(self):
        self.d = [dt.date(2020, 1, 2), dt.date(2020, 1, 3), dt.date(2020, 1, 6), dt.date(2020, 1, 7)]

    def test_full_equity_at_no_cost_reproduces_the_index_apart_from_entering_it(self):
        spy = synth(list(zip(self.d, [100.0, 102.0, 101.0, 104.0])))
        path = sl.two_asset_path(self.d, spy, None, [1.0] * 4, 0.0, 0.0)
        self.assertLess(path[-1], 1.04, "the account starts flat and buying once is not free")
        self.assertAlmostEqual(1.04 - path[-1], wc.TURNOVER_COST, delta=1e-5,
                               msg="one switch should cost one charge of the posted turnover cost")

    def test_the_cash_shelter_earns_the_bill_curve_and_nothing_else(self):
        bills = {d: 0.0001 for d in self.d}
        spy = synth(list(zip(self.d, [100.0, 999.0, 999.0, 999.0])), bills)
        path = sl.two_asset_path(self.d, spy, None, [0.0] * 4, 0.0, 0.0)
        self.assertAlmostEqual(path[-1], (1.0001) ** 3, places=12)

    def test_a_switch_is_charged_once_at_the_posted_turnover_cost(self):
        spy = synth(list(zip(self.d, [100.0] * 4)))
        one = sl.two_asset_path(self.d, spy, None, [0.0, 1.0, 1.0, 1.0], 0.0, 0.0)[-1]
        self.assertAlmostEqual(one, 1.0 - wc.TURNOVER_COST, places=12)
        two = sl.two_asset_path(self.d, spy, None, [0.0, 1.0, 0.0, 1.0], 0.0, 0.0)[-1]
        self.assertAlmostEqual(two, (1.0 - wc.TURNOVER_COST) ** 2, places=12)

    def test_an_expense_ratio_is_charged_on_what_is_held_not_on_what_is_not(self):
        spy = synth(list(zip(self.d, [100.0] * 4)))
        gold = synth(list(zip(self.d, [100.0] * 4)))
        flat = sl.two_asset_path(self.d, spy, gold, [0.0] * 4, 0.006, 0.0)[-1]
        self.assertAlmostEqual(flat, 1.0, places=12, msg="an equity fee landed on a bond day")
        held = sl.two_asset_path(self.d, spy, gold, [1.0] * 4, 0.006, 0.0)[-1]
        self.assertLess(held, 1.0)

    def test_the_shelter_is_paid_its_own_return_not_the_equitys(self):
        spy = synth(list(zip(self.d, [100.0, 110.0, 110.0, 110.0])))
        gold = synth(list(zip(self.d, [100.0, 100.0, 105.0, 105.0])))
        path = sl.two_asset_path(self.d, spy, gold, [0.0, 0.0, 0.0, 0.0], 0.0, 0.0)
        self.assertAlmostEqual(path[-1], 1.05, places=12)


class TheSignal(unittest.TestCase):
    def test_the_trend_is_read_on_the_last_trading_day_of_the_month_not_the_first(self):
        """Prices rise for ten months, then the last trading day of the tenth collapses below the average. A rule that
        read the trend anywhere else in that month would still say hold."""

        d, cur = [], dt.date(2010, 1, 4)
        while len(d) < 420:
            if cur.weekday() < 5:
                d.append(cur)
            cur += dt.timedelta(days=1)
        px = [100.0 * (1.001 ** i) for i in range(420)]
        warm = sorted({(x.year, x.month) for x in d[sl.WARMUP - 1:]})
        self.assertGreater(len(warm), 6, "the synthetic record is too short to have warmed months")
        target = warm[-2]
        px[max(i for i, x in enumerate(d) if (x.year, x.month) == target)] = 1.0
        mark = sl.month_signal(d, synth(list(zip(d, px))), "end")
        self.assertEqual(sorted(mark), warm, "one mark per month with a warmed average, no more")
        self.assertEqual(mark[warm[-3]], 1.0, "a rising market should read as hold")
        self.assertEqual(mark[target], 0.0, "the collapse on that month's last trading day was not read")
        self.assertEqual(sl.carry(mark, d)[-1], 0.0, "the decision did not carry into the following month")

    def test_carry_applies_the_previous_month_with_a_one_month_lag(self):
        d = [dt.date(2021, 1, 4), dt.date(2021, 1, 29), dt.date(2021, 2, 1), dt.date(2021, 2, 26),
             dt.date(2021, 3, 1), dt.date(2021, 3, 31), dt.date(2021, 4, 1)]
        mark = {(2021, 1): 1.0, (2021, 2): 0.0, (2021, 3): 1.0}
        w = sl.carry(mark, d)
        self.assertEqual(w[:2], [0.0, 0.0], "the account was invested before any decision existed")
        self.assertEqual(w[2:4], [1.0, 1.0], "January's decision did not reach February")
        self.assertEqual(w[4:6], [0.0, 0.0], "February's decision did not reach March")
        self.assertEqual(w[6], 1.0)

    def test_the_average_is_never_computed_on_a_window_slice(self):
        """Round 45's lesson, armed here: with fewer than 200 closes there is no average, and a tool that reads that as
        "sell" is reporting a data artefact as a decision. This file's answer is to mark nothing at all."""

        d = [dt.date(2020, 1, 1) + dt.timedelta(days=i) for i in range(120)]
        spy = synth(list(zip(d, [100.0 + i for i in range(120)])))
        self.assertEqual(sl.month_signal(d, spy, "end"), {})

    def test_on_the_real_archive_the_average_exists_from_1993(self):
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        marks = sl.month_signal(sorted(sl.legs(data, "SPY")), sl.legs(data, "SPY"), "end")
        self.assertLess(min(marks)[0], 1995, "the average is not being warmed from the start of the archive")


class TheMonthMarkTrap(unittest.TestCase):
    def test_handing_the_month_mapper_a_sliced_date_list_moves_the_answer(self):
        """`month_marks` indexes the path as `i - 1` against the list it is given, so the sliced list shifts every
        month-end by a trading day. Pinned so this trap cannot be walked into a fourth time."""

        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        spy = sl.legs(data, "SPY")
        dates = [d for d in sorted(spy) if d >= sl.PANEL_START]
        sig = [1.0] * len(dates)
        path = sl.two_asset_path(dates, spy, None, sig, wc.EXPENSE["SPY"], 0.0)
        full = mir.month_marks(dates, path)[1]
        sliced = mir.month_marks(dates[1:], path)[1]
        self.assertEqual(len(full), len(sliced))
        self.assertTrue(any(abs(a - b) > 1e-9 for a, b in zip(full, sliced)),
                        "the trap has been fixed inside month_marks; delete this test and re-read it")


class TheLongerRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.spy = sl.legs(cls.data, "SPY")
        cls.t = {}
        for conv in ("start", "end"):
            for shelter in sl.SHELTERS:
                cls.t[(conv, shelter)] = sl.record(cls.data, cls.spy, shelter, SINCE, 100_000.0, 10, 0.05,
                                                   435.47, conv)

    def test_the_record_is_the_one_the_panel_could_not_reach(self):
        cash = self.t[("start", sl.CASH)]
        self.assertEqual(cash["since"], SINCE, "the record does not start where the shelters' own history does")
        self.assertEqual(cash["months"], 288)
        self.assertEqual(cash["n"], 169, "the sample is no longer the one the note quotes")
        self.assertGreater(cash["n"], 127, "round 64's panel had 127 windows; this file exists to have more")

    def test_the_bond_shelter_beats_bills_under_both_readings_of_monthly(self):
        """"The recommendation, and the bar it has to clear: $25 a month (round 60) under either convention."""

        for conv in ("start", "end"):
            gain = self.t[(conv, "IEF")]["safe1"] - self.t[(conv, sl.CASH)]["safe1"]
            self.assertGreater(gain, st.MATERIAL, f"IEF's shelter gain is {gain:,.2f} under month-{conv}")

    def test_the_long_bond_clears_the_bar_on_one_reading_only_and_says_so(self):
        start = self.t[("start", "TLT")]["safe1"] - self.t[("start", sl.CASH)]["safe1"]
        end = self.t[("end", "TLT")]["safe1"] - self.t[("end", sl.CASH)]["safe1"]
        self.assertLess(start, st.MATERIAL, "TLT's gain under the conservative reading has moved above the bar;"
                                            " the round's central finding needs re-reading")
        self.assertGreater(end, st.MATERIAL)
        self.assertLess(self.t[("start", "TLT")]["hcagr"], 0.0,
                        "TLT no longer loses money while held under the conservative reading")

    def test_gold_still_pays_most_and_on_the_shortest_record(self):
        for conv in ("start", "end"):
            self.assertGreater(self.t[(conv, "GLD")]["safe1"], self.t[(conv, "IEF")]["safe1"])
            self.assertEqual(self.t[(conv, "GLD")]["months"], 261, "GLD's record has lengthened; re-date the caveat")

    def test_no_shelter_puts_the_published_payout_at_risk_on_the_longer_record(self):
        for conv in ("start", "end"):
            for shelter in sl.SHELTERS:
                self.assertEqual(self.t[(conv, shelter)]["p_fail"], 0.0, f"{shelter} under month-{conv}")

    def test_capacity_rises_with_the_shelter_under_both_readings(self):
        for conv in ("start", "end"):
            cash, ief = self.t[(conv, sl.CASH)]["cap"], self.t[(conv, "IEF")]["cap"]
            self.assertIsNotNone(cash)
            self.assertGreater(ief, cash, f"IEF did not lift the ceiling under month-{conv}")
            for r in (cash, ief):
                self.assertEqual(int(r) % 25, 0)

    def test_the_shelter_is_measured_while_it_is_held_not_over_the_record(self):
        """The conditional statistic round 64 pinned, on the longer record: the bond that looks worse outright is the
        one the rule holds better, under the reading that pays for the timing."""

        r = self.t[("end", "IEF")]
        self.assertGreater(r["hcagr"], 0.05)
        self.assertLess(r["hmdd"], 0.20)
        self.assertGreater(self.t[("end", "TLT")]["hmdd"], r["hmdd"])

    def test_the_signal_spends_a_quarter_of_the_record_outside_equities_under_both_readings(self):
        for conv in ("start", "end"):
            self.assertAlmostEqual(self.t[(conv, "IEF")]["duty"], 0.20, delta=0.015,
                                   msg="the rule's duty cycle has moved; the 25% quoted from round 64's panel and the"
                                       " 19.6% of this record are different samples, and every note that quotes one"
                                       " needs to say which")


class ThePin(unittest.TestCase):
    def test_this_engine_handed_round_58s_weights_returns_round_58s_number(self):
        import frequency_cost as fc
        import rotation_edge as re_
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        spy = sl.legs(data, "SPY")
        ordered, rets, bills, base = re_.panel(data, re_.UNKNOWN_ER)
        pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
        cl = tc.closes_of(data, "SPY")
        closes = {"SPY": [cl[pos[d]] for d in ordered]}
        wts = fc.weights_for_family("ma200", ordered, rets, bills, base, closes, "monthly", re_.UNKNOWN_ER)
        theirs = [float(w[re_.UNIVERSE.index("SPY")]) for w in wts]
        path = sl.two_asset_path(ordered, spy, None, theirs, wc.EXPENSE["SPY"], 0.0)
        monthly = mir.month_marks(ordered, path)[1]
        got = mir.safe_amount(monthly, 100_000.0, 10, 0.05, floor=1.0)
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got, sl.PANEL_PIN, delta=0.01,
                               msg="this file's engine no longer reproduces round 58; nothing below it can be quoted")

    def test_the_published_cell_is_the_highest_of_the_four_readings(self):
        import rotation_edge as re_
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        spy = sl.legs(data, "SPY")
        ordered, rets, bills, base = re_.panel(data, re_.UNKNOWN_ER)
        marks = {c: sl.month_signal(sorted(spy), spy, c) for c in ("start", "end")}
        cell = {}
        for conv in ("start", "end"):
            sig = sl.carry(marks[conv], ordered)
            cold = [0.0] * sl.WARMUP + sig[sl.WARMUP:]
            for state, s in (("warmed", sig), ("cold", cold)):
                path = sl.two_asset_path(ordered, spy, None, s, wc.EXPENSE["SPY"], 0.0)
                cell[(conv, state)] = mir.safe_amount(mir.month_marks(ordered, path)[1], 100_000.0, 10, 0.05,
                                                      floor=1.0)
        self.assertGreater(cell[("start", "warmed")], cell[("start", "cold")],
                           "forcing the warm-up hole in now HELPS, which is the opposite of the finding")
        # Immaterial is a claim about cents, not about bits. This was `assertEqual` until round 95's live fetch re-pulled
        # the corpus: same 5,177 sessions, same last date, one close revised by a hundredth of a basis point, and two
        # algebraically identical paths stopped being bit-identical. A pin on the exact bytes of a downloaded file is not a
        # test of the finding, it is a lock on the archive being frozen — which a monthly fetch exists to prevent.
        self.assertAlmostEqual(cell[("end", "warmed")], cell[("end", "cold")], delta=0.005,
                              msg="the month-end hole has stopped being immaterial; re-read the reason")
        self.assertLess(abs(cell[("end", "warmed")] - cell[("end", "cold")]) / cell[("end", "warmed")], 1e-9,
                        "the difference is no longer float noise, so it is a finding and not a rounding artefact")
        self.assertLess(max(cell.values()), sl.PANEL_PIN,
                        f"the best honest reading is now {max(cell.values()):,.2f} against a published "
                        f"{sl.PANEL_PIN:,.2f}; the gap finding is stale")
        self.assertGreater(sl.PANEL_PIN - min(cell.values()), 50.0,
                           "the four readings have converged; the convention no longer matters and the note lies")


if __name__ == "__main__":
    unittest.main()
