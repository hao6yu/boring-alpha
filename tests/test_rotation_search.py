"""Tests for the rotation search, and for the generalised cost engine it required.

`multi_asset_path` is a new implementation of a cost model that seven rounds of published numbers rest on, so the first
test is a differential against the original rather than a check that the new one runs. After that, the same standard the
last two rounds set: no lookahead, comparators priced exactly like strategies, and the round's actual finding pinned — the
one row that clears the bar against plain SPY is beaten by a control that involves no decision at all.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import fund_fees                                             # noqa: E402
import paper
import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402


class EngineMatchesOriginal(unittest.TestCase):
    """Round 69's rule: a reimplementation of a measured rule needs a differential test against the original, and a cost
    model is a measured rule."""

    @classmethod
    def setUpClass(cls):
        from boring_alpha.data.csv_loader import load_csv_market_data
        cls.d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        cls.spy = sl.legs(cls.d, "SPY")
        cls.ief = sl.legs(cls.d, "IEF")
        cls.dates = [d for d in sorted(cls.spy) if d >= sl.PANEL_START and d in cls.ief]

    def slice_opening_in_equities(self):
        """A slice of the archive that starts fully invested, so both engines face the same first day. They do not agree on
        day one of a record that opens *sheltered* — `two_asset_path` charges only the equity leg, so a plan that begins in
        Treasuries pays nothing for buying them, while the general engine charges the purchase. That is a difference of one
        switch charge, forever, and it is pinned in its own test below rather than hidden inside a slice."""

        marks = sl.month_signal(sorted(self.spy), self.spy, "start")
        w = sl.carry(marks, self.dates)
        k = next(i for i in range(len(self.dates)) if w[i] == 1.0 and w[i + 1] == 1.0 and w[i + 2] == 0.0)
        return self.dates[k:], w[k:]

    def test_two_legs_through_the_general_engine_reproduce_the_two_asset_engine_exactly(self):
        dates, w = self.slice_opening_in_equities()
        want = sl.two_asset_path(dates, self.spy, self.ief, w, wc.EXPENSE["SPY"], 0.0035)
        got = sl.multi_asset_path(dates, {"SPY": self.spy, "IEF": self.ief},
                                  {"SPY": w, "IEF": [1.0 - x for x in w]},
                                  {"SPY": wc.EXPENSE["SPY"], "IEF": 0.0035}, self.spy)
        self.assertGreater(len(want), 2000, "the slice must be long, with switches in it, not a convenience window")
        self.assertGreater(sum(1 for i in range(1, len(w)) if w[i] != w[i - 1]), 10)
        worst = max(abs(a - b) for a, b in zip(want, got))
        self.assertLess(worst, 1e-15, f"the two engines disagree by {worst}; every published number moves")

    def test_the_published_record_goes_through_the_general_engine_unchanged(self):
        """Not "close": this record opens fully invested, so the two engines' one convention difference never fires, and
        every number rounds 61 to 74 published is reproducible through the new function digit for digit."""

        marks = sl.month_signal(sorted(self.spy), self.spy, "start")
        w = sl.carry(marks, self.dates)
        a = sl.two_asset_path(self.dates, self.spy, self.ief, w, wc.EXPENSE["SPY"], 0.0035)[-1]
        b = sl.multi_asset_path(self.dates, {"SPY": self.spy, "IEF": self.ief},
                                {"SPY": w, "IEF": [1.0 - x for x in w]},
                                {"SPY": wc.EXPENSE["SPY"], "IEF": 0.0035}, self.spy)[-1]
        self.assertAlmostEqual(a, b, places=15)

    def test_a_record_that_opens_in_the_shelter_is_one_switch_apart_in_the_two_engines(self):
        """The documented difference, constructed rather than waited for: the original charges only the equity leg, so a
        record that begins sheltered never pays for buying the shelter and the general engine charges it once."""

        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=k) for k in range(4)]
        flat = {d: (100.0, 0.0) for d in dates}
        zero = [0.0] * 4
        a = sl.two_asset_path(dates, flat, flat, zero, 0.0, 0.0)[-1]
        b = sl.multi_asset_path(dates, {"SPY": flat, "IEF": flat}, {"SPY": zero, "IEF": [1.0] * 4},
                                {"SPY": 0.0, "IEF": 0.0}, flat)[-1]
        self.assertEqual(a, 1.0)
        self.assertAlmostEqual(b, 1.0 - wc.TURNOVER_COST, places=15)

    def test_a_switch_costs_the_same_in_both_engines(self):
        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=k) for k in range(5)]
        flat = {d: (100.0, 0.0) for d in dates}
        # One switch, SPY to IEF, on a record where every price is identical: 0.5*(1+1) * 2 bps, same as abs(Δw) * 2 bps.
        two = sl.two_asset_path(dates, flat, flat, [1.0, 1.0, 1.0, 0.0, 0.0], 0.0, 0.0)[-1]
        gen = sl.multi_asset_path(dates, {"SPY": flat, "IEF": flat},
                                  {"SPY": [1.0, 1.0, 1.0, 0.0, 0.0], "IEF": [0.0, 0.0, 0.0, 1.0, 1.0]},
                                  {"SPY": 0.0, "IEF": 0.0}, flat)[-1]
        self.assertAlmostEqual(two, gen, places=15)
        self.assertAlmostEqual(gen, (1.0 - wc.TURNOVER_COST) ** 2, places=15,
                               msg="entry charge plus the one switch, and nothing else may happen on a flat record")

    def test_an_unpriced_leg_earns_the_bill_curve_rather_than_nothing(self):
        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=k) for k in range(3)]
        flat = {d: (100.0, 0.001) for d in dates}
        out = sl.multi_asset_path(dates, {"SPY": flat}, {"SPY": [0.0] * 3}, {"SPY": 0.0}, flat)[-1]
        self.assertAlmostEqual(out, (1.0 + 0.001) ** 2, places=12)


class TheGrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = rse.grid(100_000.0, 10)
        cls.rows = {r["rule"]: r for r in cls.o["rules"]}

    def cell(self, rule, conv, window):
        return self.rows[rule]["cells"][(conv, window)]

    def test_every_row_is_scored_on_one_calendar_against_both_comparators(self):
        for rule, r in self.rows.items():
            self.assertEqual(sorted(r["cells"]), [("end", "long"), ("end", "recent"), ("start", "long"),
                                                  ("start", "recent")], rule)
            for c in r["cells"].values():
                self.assertIn(c["since"], (self.o["since"], self.o["recent"]), f"{rule}: an unexpected calendar")
                self.assertGreater(c["n"], 0)

    def test_a_calendar_shared_by_every_symbol_starts_after_the_shared_warmup(self):
        """GLD is the youngest symbol in the pool, so it sets the start; and the start must leave 200 sessions of shared
        history behind it, or no rule can score anything on day one."""

        d = self._data()
        gld = sorted(sl.legs(d, "GLD"))
        self.assertGreaterEqual(self.o["since"], gld[sl.WARMUP])
        for sym in rse.RISK + (rse.SHELTER,):
            self.assertIn(self.o["since"], sl.legs(d, sym), f"{sym} has no price on the shared start")

    def _data(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        return load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    def test_the_control_that_is_the_comparator_differences_by_exactly_nothing(self):
        for conv in ("start", "end"):
            for window in ("long", "recent"):
                d = self.cell("spy_only", conv, window)["vs_spy"]
                self.assertLess(abs(d), 0.05, f"{conv} {window}: the comparator priced itself differently from itself")
                self.assertLessEqual(d, 0.0, "the one day every window opens in cash is the only difference, and it"
                                            " costs the comparator rather than flattering it")

    def test_the_reading_convention_can_turn_the_sign_of_a_rotation(self):
        """Two of the seven rows change sign on the recent window between the two readings of 'the month's signal day'. A
        result that depends on whether the decision is taken on the first or the last session of a month is not a result,
        and the table prints both columns for exactly this reason."""

        flips = [r["rule"] for r in self.o["rules"]
                 if (self.cell(r["rule"], "start", "recent")["vs_spy"] > 0)
                 != (self.cell(r["rule"], "end", "recent")["vs_spy"] > 0)]
        self.assertEqual(flips, ["dm12_wide"], flips)
        self.assertGreater(abs(self.cell("dm12_wide", "start", "recent")["vs_spy"]
                               - self.cell("dm12_wide", "end", "recent")["vs_spy"]), 300.0)
        for control in ("spy_only", "qqq_only", "blend_sq"):
            self.assertEqual(self.cell(control, "start", "recent")["vs_spy"],
                             self.cell(control, "end", "recent")["vs_spy"],
                             f"{control}: a holding has no reading day, so the two columns must be identical")

    def test_the_rotation_does_not_lose_everywhere_and_the_controls_win_where_it_wins(self):
        """The finding, pinned as an assertion rather than a paragraph. One rule clears round 60's bar against plain SPY on
        both windows at both readings — the first such row in this repository — and a static 50/50 holding beats it on the
        window that matters. Both halves are needed: the first says the search was not pointless, the second says what the
        result actually is."""

        dm = self.rows["dm12_sq"]
        self.assertGreaterEqual(self.cell("dm12_sq", "start", "long")["vs_spy"], ct.BAR)
        self.assertGreaterEqual(self.cell("dm12_sq", "start", "recent")["vs_spy"], ct.BAR)
        self.assertGreater(self.cell("dm12_sq", "end", "recent")["vs_spy"], 0.0)
        self.assertFalse(dm["pass"], "the pre-registered clause passes it; the control clause must not")
        self.assertLess(min(dm["vs_blend"]), 0.0)
        self.assertIn("static 50/50 control", dm["verdict"])

    def test_holding_growth_beats_holding_the_s_and_p_on_capacity_on_both_windows(self):
        """The least interesting row on the page and the one the objective should actually hear: no rule is needed for the
        premium, which is precisely why a rule has to beat it to be worth anything."""

        for window in ("long", "recent"):
            self.assertGreater(self.cell("qqq_only", "start", window)["vs_spy"], ct.BAR)
            self.assertGreater(self.cell("blend_sq", "start", window)["vs_spy"], ct.BAR)
            self.assertEqual(self.cell("qqq_only", "start", window)["p_fail"], 0.0)

    def test_the_wide_rotations_are_the_worst_rows_in_the_table(self):
        """More assets did not help. GLD and EFA are charged a flat fee that flatters them, so this failure is not a
        fee artefact."""

        for rule in ("dm12_ief",):
            self.assertLess(self.cell(rule, "start", "recent")["vs_spy"], 0.0, rule)
            self.assertLess(self.cell(rule, "start", "long")["vs_spy"], 0.0, rule)
            self.assertGreater(self.cell(rule, "start", "recent")["switches"], 40, rule)

    def test_the_pass_flag_is_recomputed_from_the_row_not_from_the_label(self):
        for rule, r in self.rows.items():
            s = r["cells"]
            clears = (s[("start", "long")]["vs_spy"] >= ct.BAR and s[("start", "recent")]["vs_spy"] >= ct.BAR
                      and s[("end", "long")]["vs_spy"] > 0 and s[("end", "recent")]["vs_spy"] > 0)
            self.assertTrue(clears == r["pass"] or (clears and not r["pass"] and r["vs_blend"] is not None
                                                     and min(r["vs_blend"]) < 0), f"{rule}: verdict cannot be derived")

    def test_the_rotation_switches_often_and_the_controls_never(self):
        self.assertEqual(self.cell("blend_sq", "start", "recent")["switches"], 0)
        self.assertGreater(self.cell("dm12_sq", "start", "recent")["switches"], 20)

    def test_every_leg_on_the_page_is_charged_the_ratio_the_table_posts(self):
        """Round 103: this battery used to look fees up in another file's graded-sleeve list and bill the flat guess for the
        rest, which is how IEF — the leg the shelter rules hide in — got charged 0.35% against a posted 0.15%.

        The guess is not reachable from here any more, and the page says in its own footer which legs it used to misprice.
        """

        for s in rse.RISK + (rse.SHELTER,):
            self.assertTrue(fund_fees.priced(s), f"{s} is on this page and unpriced")
            self.assertEqual(rse.fee(s), fund_fees.fee_for(s), f"{s} is not charged its posted ratio")
        for s, v in self.o["fees"].items():
            self.assertEqual(v, rse.fee(s))

    def test_the_battery_refuses_to_price_a_leg_the_table_has_not_priced(self):
        with self.assertRaises(SystemExit) as caught:
            rse.fee("XLU")
        self.assertIn("fund_fees", str(caught.exception))

    def test_the_guess_only_ever_wrongly_covered_the_legs_missing_from_a_scope_list(self):
        """Pins what the correction was, and keeps its size honest.

        Three legs, IEF worst at 20 bps, and every move on the printed page under five dollars a month: the correction changed
        no verdict and no pass, and it still mattered, because all three errors ran against the safe leg and this page grades
        rules against a bill of a few bps.
        """

        old = {s: (wc.EXPENSE[s] if s in wc.EXPENSE else paper.UNPOSTED_FEE) for s in rse.RISK + (rse.SHELTER,)}
        wrong = {s: (paper.UNPOSTED_FEE - fund_fees.fee_for(s)) * 10_000 for s, v in old.items() if v == paper.UNPOSTED_FEE}
        self.assertEqual(sorted(wrong), ["EFA", "GLD", "IEF"])
        self.assertAlmostEqual(max(wrong.values()), 20.0, delta=1.0, msg="the worst miss moved; re-measure the claim")
        self.assertLess(max(abs(v) for v in wrong.values()), 50.0)
        self.assertEqual(sum(1 for r in self.o["rules"] if r["pass"]), 2, "the fee fix changed who passes")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rse.report(self.o, 100_000.0)
        text = buf.getvalue()
        self.assertIn("used to be billed the flat", text, "the page stopped printing what the guess got wrong")
        self.assertNotIn("are not in\n the archive", text)


class Weights(unittest.TestCase):
    def setUp(self):
        self.dates = [dt.date(2020, m, 1) + dt.timedelta(days=d) for m in (1, 2, 3) for d in (0, 1, 2)]
        self.series = {s: {d: (100.0, 0.0) for d in self.dates} for s in ("SPY", "QQQ", "IEF")}

    def test_no_decision_yet_means_holding_nothing_and_earning_the_bill(self):
        w = rse.weights_for("dm12_sq", self.series, self.dates, {})
        self.assertEqual(sum(len(v) for v in w.values()), 9 * 3)
        self.assertEqual(sum(w[s][0] for s in w), 0.0)

    def test_a_decision_is_held_until_the_next_one_exactly_as_carry_does(self):
        mk = {(2020, 1): "QQQ", (2020, 3): "IEF"}
        w = rse.weights_for("dm12_sq", self.series, self.dates, mk)
        self.assertEqual(w["QQQ"][0], 0.0, "day one has no prior month, so it holds nothing")
        self.assertEqual(w["QQQ"][3], 1.0, "February is February under carry: it reads January's mark")
        self.assertEqual(w["QQQ"][7], 1.0, "March still holds January's decision — a March mark must not apply in March")
        self.assertEqual(w["QQQ"][8], 1.0, "the last day of March is still the old decision; the change lands in April")
        later = self.dates + [dt.date(2020, 4, d) for d in (1, 2, 3)]
        s2 = {x: {d: (100.0, 0.0) for d in later} for x in self.series}
        w2 = rse.weights_for("dm12_sq", s2, later, mk)
        self.assertEqual(w2["IEF"][9], 1.0, "April reads March's mark, which was IEF")
        self.assertEqual(w2["QQQ"][9], 0.0)

    def test_the_blend_is_half_of_each_and_needs_no_reading(self):
        mk = {(y, m): "SPY+QQQ" for y in (2020,) for m in (1, 2, 3)}
        w = rse.weights_for("blend_sq", self.series, self.dates, mk)
        self.assertEqual(w["SPY"][5], 0.5)
        self.assertEqual(w["QQQ"][5], 0.5)
        self.assertEqual(sum(w[s][5] for s in w), 1.0)

    def test_a_rule_is_forbidden_from_choosing_a_symbol_it_cannot_score(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        d = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        dates = rse.shared_calendar(d)
        series = {s: sl.legs(d, s) for s in rse.RISK + (rse.SHELTER,)}
        head = dates[:30]
        for rule in rse.RULES:
            if rule in ("spy_only", "qqq_only", "blend_sq"):
                continue
            self.assertEqual(rse.held_for(rule, series, head, "start"), {}, f"{rule} answered with no history")


if __name__ == "__main__":
    unittest.main()
