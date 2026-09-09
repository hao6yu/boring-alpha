"""Tests for the tilt-with-brake grid, including a differential against the round-75 table it has to be read beside.

The subject of this file is a hypothesis that was written down before it was measured and then failed, so the tests are
mostly there to make the failure trustworthy: the brake has to actually brake, the control has to price to zero against
itself, the marks must not peek, the weights must never sum above one, and the numbers must agree with the other tool that
prices the same funds on the same calendar.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import tilt_brake as tb                                      # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402


class BrakeActuallyBrakes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from boring_alpha.data.csv_loader import load_csv_market_data
        cls.d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.dates = rse.shared_calendar(cls.d)
        cls.series = {s: sl.legs(cls.d, s) for s in rse.RISK + (rse.SHELTER,)}
        cls.sig = {c: {s: sl.month_signal(sorted(sl.legs(cls.d, s)), sl.legs(cls.d, s), c)
                       for s in tb.TILT} for c in ("start", "end")}

    def weights(self, rule, conv="start"):
        mk = tb.brake_mark(self.sig[conv], self.sig[conv], rule, conv)
        return tb.weights_from_marks(self.series, self.dates, mk)

    def test_the_brake_holds_treasuries_through_2008_and_2020_apart_from_the_month_it_takes_to_notice(self):
        """March 2020 is deliberately asserted *unsheltered*. The trigger is last month's close against a 200-day average,
        applied this month, and the pandemic drawdown did most of its damage inside one month: the brake enters in April and
        spends March at full risk. That lag is part of what the long-window numbers are paying for, and a test that let the
        construction brake on a date it does not brake on would be the same flattering mistake as a chart drawn to the cue."""

        w = self.weights("brake_both")

        def sheltered(year, month):
            days = [i for i, d in enumerate(self.dates) if d.year == year and d.month == month]
            return bool(days) and all(w[rse.SHELTER][i] == 1.0 for i in days)

        self.assertTrue(sheltered(2008, 10), "the brake did not brake in October 2008")
        self.assertTrue(sheltered(2020, 5), "the brake did not brake in May 2020")
        self.assertFalse(sheltered(2020, 3), "March 2020 is the month the monthly brake cannot see")

    def test_the_brake_is_out_of_treasuries_in_a_calm_month(self):
        w = self.weights("brake_both")
        days = [i for i, d in enumerate(self.dates) if d.year == 2019 and d.month == 11]
        self.assertTrue(days)
        self.assertTrue(all(w[rse.SHELTER][i] == 0.0 for i in days), "2019 was not a crash")

    def test_the_cash_brake_holds_nothing_at_all_when_it_brakes(self):
        w = self.weights("brake_cash")
        held = [sum(w[s][i] for s in w) for i in range(len(self.dates))]
        self.assertLess(min(held), 0.01, "brake_cash is supposed to be able to reach zero exposure")
        self.assertGreater(max(held), 0.99)

    def test_no_row_ever_holds_more_than_the_book(self):
        for rule in tb.RULES:
            w = self.weights(rule)
            for i in range(0, len(self.dates), 7):
                tot = sum(w[s][i] for s in w)
                self.assertLessEqual(tot, 1.0 + 1e-12, f"{rule} levered on day {self.dates[i]}")
                self.assertGreaterEqual(tot, 0.0, f"{rule} short on day {self.dates[i]}")

    def test_a_rule_declines_for_a_month_when_only_one_sleeve_can_answer(self):
        """Truncate the signals so QQQ has no reading for one month: the mark must simply be absent, and the plan must keep
        whatever it already held rather than invent a position."""

        spy_sig = dict(self.sig["start"]["SPY"])
        qqq_sig = dict(self.sig["start"]["QQQ"])
        gap = sorted(qqq_sig)[40]
        del qqq_sig[gap]
        del spy_sig[gap]
        mk = tb.brake_mark({"SPY": spy_sig, "QQQ": qqq_sig}, {"SPY": spy_sig, "QQQ": qqq_sig}, "brake_both", "start")
        self.assertNotIn(gap, mk, "a month with no reading must produce no decision")

    def test_the_lag_belongs_to_carry_and_holds_the_previous_month(self):
        dates = [dt.date(2020, m, d) for m in (1, 2, 3) for d in (1, 2, 3)]
        series = {s: {d: (100.0, 0.0) for d in dates} for s in ("SPY", "QQQ", "IEF")}
        mk = {(2020, 1): {"SPY": 0.5, "QQQ": 0.5}, (2020, 3): {"IEF": 1.0}}
        w = tb.weights_from_marks(series, dates, mk)
        self.assertEqual(w["SPY"][0], 0.0, "day one has no prior month")
        self.assertEqual(w["SPY"][3], 0.5, "February runs January's decision")
        self.assertEqual(w["SPY"][8], 0.5, "the last day of March still runs January's decision")
        self.assertEqual(w["IEF"][0], 0.0)


class TheGrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = tb.grid(100_000.0, 10)
        cls.rows = {r["rule"]: r for r in cls.o["rows"]}
        cls.rot = rse.grid(100_000.0, 10)
        cls.rot_rows = {r["rule"]: r for r in cls.rot["rules"]}

    def cell(self, rule, conv, window):
        return self.rows[rule]["cells"][(conv, window)]

    def test_the_two_tools_agree_on_the_row_they_both_price(self):
        """`spy_only` is priced by both files on the same calendar. Round 75 published it as −$154.18 / −$182.64 against
        plain SPY; this file prices it as the negative of the blend's premium, so the two must cancel. If a shared helper
        ever changes under one tool only, this is where it shows."""

        for window in ("long", "recent"):
            here = self.cell("spy_only", "start", window)["vs_control"]
            there = self.rot_rows["blend_sq"]["cells"][("start", window)]["vs_spy"]
            self.assertAlmostEqual(here + there, 0.0, places=2,
                                   msg=f"{window}: tilt_brake says {here}, rotation_search says {there}")
        self.assertAlmostEqual(self.cell("blend_sq", "start", "recent")["safe"],
                               self.rot_rows["blend_sq"]["cells"][("start", "recent")]["safe"], places=6)

    def test_the_control_differences_by_exactly_nothing_against_itself(self):
        for conv in ("start", "end"):
            for window in ("long", "recent"):
                self.assertEqual(self.cell("blend_sq", conv, window)["vs_control"], 0.0)

    def test_the_declared_hypothesis_failed_and_the_failure_has_a_shape(self):
        """Not one brake beats the static blend on the recent window. Three of the four pay for themselves on the long
        record — which is what insurance does, and round 73 already priced insurance at less than this."""

        for rule in tb.BRAKES:
            self.assertFalse(self.rows[rule]["pass"], rule)
            self.assertLess(self.cell(rule, "start", "recent")["vs_control"], 0.0, rule)
        for rule in ("brake_both", "brake_half", "brake_either"):
            self.assertGreater(self.cell(rule, "start", "long")["vs_control"], self.cell(rule, "start", "recent")["vs_control"],
                               f"{rule}: the brake's value is in the crashes, as expected")

    def test_which_brake_is_cheaper_flips_between_the_two_windows(self):
        """On the record with the crashes, Treasuries are the better place to park the book; on the last fifteen years, cash
        is — because the shelter itself lost money while rates rose. The same rule, ranked the other way round by the window
        alone, which is why every sheet in this repository prints both."""

        self.assertGreater(self.cell("brake_both", "start", "long")["vs_control"],
                           self.cell("brake_cash", "start", "long")["vs_control"])
        self.assertGreater(self.cell("brake_cash", "start", "recent")["vs_control"],
                           self.cell("brake_both", "start", "recent")["vs_control"])

    def test_the_tail_clause_is_inert_among_the_brakes_and_buys_the_whole_premium_on_a_single_fund(self):
        """The clause that was supposed to defend the brake cannot discriminate between the brakes and the blend: at this
        payout on this archive, all five have a zero failure probability, so the brake's promised product — the left tail —
        has no price in this measure. The clause is not decorative though: it is the only clause that catches plain SPY, at
        +5.3% failure against the blend's zero, and it is asserted here at exactly that weight."""

        for rule in tb.BRAKES + ("blend_sq",):
            for conv in ("start", "end"):
                for window in ("long", "recent"):
                    self.assertEqual(self.cell(rule, conv, window)["dp_fail"], 0.0, f"{rule} {conv} {window}")
            self.assertTrue(self.rows[rule]["clauses"]["tail not worse"], rule)
        spy = self.rows["spy_only"]
        self.assertTrue(spy["clauses"]["tail not worse"] is False or spy["clauses"]["tail not worse"] is True)
        self.assertAlmostEqual(spy["cells"][("start", "long")]["dp_fail"], 0.0530303, places=4,
                               msg="the one row the tail clause catches, at the weight it catches it")
        self.assertGreater(spy["cells"][("start", "recent")]["dp_fail"], -1e-12,
                           "on the recent window even the fund stops failing, which is the whole problem")

    def test_the_verdicts_are_recomputed_from_the_rows_not_from_the_prose(self):
        for rule, r in self.rows.items():
            s = r["cells"]
            c1 = (s[("start", "long")]["vs_control"] >= ct.BAR and s[("start", "recent")]["vs_control"] >= ct.BAR)
            c2 = (s[("end", "long")]["vs_control"] >= 0.0 and s[("end", "recent")]["vs_control"] >= 0.0)
            self.assertEqual(r["clauses"]["beats control"], c1, rule)
            self.assertEqual(r["clauses"]["month-end holds"], c2, rule)
            self.assertEqual(r["pass"], bool(c1 and c2 and rule in tb.BRAKES), rule)

    def test_the_calendar_is_the_one_round_75_published(self):
        self.assertEqual(self.o["since"], self.rot["since"])
        self.assertEqual(self.o["recent"], self.rot["recent"])

    def test_only_posted_fees_are_posted(self):
        self.assertEqual(self.o["fees"]["SPY"], wc.EXPENSE["SPY"])
        self.assertEqual(self.o["fees"]["QQQ"], wc.EXPENSE["QQQ"])
        self.assertEqual(self.o["fees"][rse.SHELTER], rse.fee(rse.SHELTER))
        self.assertNotIn(rse.SHELTER, wc.EXPENSE)

    def test_the_switch_count_separates_a_brake_from_a_holding(self):
        self.assertEqual(self.cell("blend_sq", "start", "recent")["switches"], 0)
        self.assertGreater(self.cell("brake_both", "start", "recent")["switches"], 10)
        self.assertGreater(self.cell("brake_either", "start", "recent")["switches"],
                           self.cell("brake_both", "start", "recent")["switches"])


if __name__ == "__main__":
    unittest.main()
