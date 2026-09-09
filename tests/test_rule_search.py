"""Tests for the rule search: the method, not the ranking.

A grid of nine rules is a machine for producing the best-looking number, so nothing here pins a ranking. What is pinned is
the apparatus that keeps the grid honest: no rule may see the future, every rule must decline where it has no data, the
cost engine must actually charge the chatty rows, the pass flag must be a function of the row's own two numbers, and the
result this family produced — nine rows, none clearing the window round 73 named — must survive as a fact rather than as a
paragraph.
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
import rule_search as rs                                     # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402


class NoLookahead(unittest.TestCase):
    """The differential test round 69 demands of any reimplementation of a measured rule: recompute each month's decision
    from a record truncated at that month's own reading day, and require the same answer. A rule that peeks fails this and
    passes every number-looking test."""

    @classmethod
    def setUpClass(cls):
        cls.data = sw.data()
        cls.spy = sl.legs(cls.data, rs.SLEEVE)
        cls.dates = sorted(cls.spy)
        cls.conv = "start"
        cls.marks = {r: rs.marks_for(r, cls.spy, cls.dates, cls.conv) for r in rs.RULES}

    def test_each_rule_decides_the_same_month_from_a_truncated_record(self):
        for rule in rs.RULES:
            full = self.marks[rule]
            keys = sorted(full)
            for key in keys[5:12]:                  # a window in the middle, not a flattering sample
                i = next(k for k, d in enumerate(self.dates) if (d.year, d.month) == key)
                if self.conv == "start":
                    cut = i + 1                     # the record stops on the day the decision was taken
                else:
                    cut = i + 1
                trunc = rs.marks_for(rule, self.spy, self.dates[:cut], self.conv)
                self.assertIn(key, trunc, f"{rule}: {key} decided on the full record but not on its own day")
                self.assertEqual(trunc[key], full[key],
                                 f"{rule} answered {trunc[key]} for {key} with data ending that day and"
                                 f" {full[key]} with everything after it")

    NEED = {"voltarget": 21, "ma50": 50, "ma100": 100, "mom_12_1": 231}

    def test_no_rule_answers_before_its_own_average_exists(self):
        """Each rule is held to the history it actually needs — 200 sessions for an MA200, 21 for a realised-volatility
        step — because a blanket 200 would let a fast rule that peeked nothing off free and would accuse a slow one that
        declined properly."""

        for rule in rs.RULES:
            keys = sorted(self.marks[rule])
            self.assertTrue(keys, f"{rule} produced no marks at all")
            first_day = next(d for d in self.dates if (d.year, d.month) == keys[0])
            self.assertGreaterEqual(self.dates.index(first_day), self.NEED.get(rule, 200),
                                    f"{rule} decided {keys[0]} with too little history to know anything")

    def test_a_long_lookback_rule_asked_at_the_start_of_the_archive_has_no_opinion(self):
        legs = sl.legs(self.data, rs.SLEEVE)
        early = self.dates[:60]
        for rule in rs.RULES:
            if self.NEED.get(rule, 200) <= 60:
                continue
            self.assertEqual(rs.marks_for(rule, legs, early, "start"), {}, f"{rule} invented an answer")
        self.assertTrue(rs.marks_for("voltarget", legs, early, "start"),
                        "vol targeting needs three weeks, and refusing it a mark would be its own kind of error")


class CostsCharged(unittest.TestCase):
    def setUp(self):
        self.dates = [dt.date(2020, 1, 1) + dt.timedelta(days=k) for k in range(41)]
        self.spy = {d: (100.0, 0.0) for d in self.dates}
        self.shelter = {d: (100.0, 0.0) for d in self.dates}

    def test_a_chatty_plan_is_charged_for_every_switch_it_makes(self):
        flat = [1.0] * len(self.dates)
        calm = sl.two_asset_path(self.dates, self.spy, self.shelter, flat, 0.0, 0.0)[-1]
        w = [1.0 if i % 2 == 0 else 0.0 for i in range(len(self.dates))]
        chat = sl.two_asset_path(self.dates, self.spy, self.shelter, w, 0.0, 0.0)[-1]
        # Every price on this record is identical, so the only thing that can happen to either plan is the switch charge:
        # the calm plan pays it once, to get in, and the chatty one 40 times.
        self.assertAlmostEqual(calm, 1.0 - wc.TURNOVER_COST, places=12)
        self.assertAlmostEqual(chat, (1.0 - wc.TURNOVER_COST) ** 40, places=12)
        self.assertLess(chat, calm)

    def test_holding_the_shelter_costs_the_shelters_fee_and_nothing_else(self):
        out = sl.two_asset_path(self.dates, self.spy, self.shelter, [0.0] * len(self.dates), 0.000945, 0.0035)
        self.assertAlmostEqual(out[-1], (1.0 - 0.0035 / 252.0 * (len(self.dates) - 1)), delta=1e-6)

    def test_a_plan_that_never_leaves_the_fund_differs_from_the_comparator_by_exactly_nothing(self):
        """Not an approximation: the comparator is the same fund at the same fee, so a full-weight rule must tie it to the
        cent, and a row that beats it while fully invested is a bug in the pricing, not an alpha."""

        legs = sl.legs(sw.data(), "SPY")
        dates = sorted(legs)
        full = {(d.year, d.month): 1.0 for d in dates if d >= ct.SINCE}
        s = rs.score(sw.data(), legs, sl.legs(sw.data(), rs.SHELTER), full, ct.SINCE, "start", 100_000.0, 10)
        self.assertAlmostEqual(s["delta"], 0.0, delta=0.05, msg="a fully invested rule and the comparator are the same"
                               " plan, and any premium between them is the pricing, not the market")
        self.assertLess(s["duty"], 0.006, "carry needs a prior month's decision, so a fully invested plan opens")
        self.assertIn(s["switches"], (1, 2), "month and nothing after it")


class TheGrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = rs.grid(100_000.0, 10)

    def row(self, rule):
        return next(r for r in self.g if r["rule"] == rule)

    def test_every_rule_is_priced_on_both_readings_and_all_three_windows(self):
        self.assertEqual(len(self.g), len(rs.RULES))
        for r in self.g:
            for conv in ("start", "end"):
                self.assertEqual(sorted(r[conv]), ["long", "panel", "recent"])
                for w in ("long", "panel", "recent"):
                    self.assertGreater(r[conv][w]["n"], 0)
                    self.assertGreaterEqual(r[conv][w]["since"], ct.SINCE)

    def test_nothing_in_this_family_clears_the_window_that_matters(self):
        """The round's finding, pinned as a fact about the archive rather than as prose in a note: nine pre-registered
        monthly rules, single fund plus shelter, no leverage, real costs — none beats plain DCA on the shared recent
        window. Anyone who believes a better moving-average length is around the corner should run this file."""

        self.assertEqual([r["rule"] for r in self.g if r["pass"]], [])
        for r in self.g:
            self.assertLess(r["start"]["recent"]["delta"], 0.0, r["rule"])

    def test_the_pass_flag_is_recomputed_from_its_own_row_and_not_from_a_label(self):
        for r in self.g:
            s, e = r["start"], r["end"]
            want = (s["long"]["delta"] >= ct.BAR and s["recent"]["delta"] >= ct.BAR
                    and e["long"]["delta"] > 0 and e["recent"]["delta"] > 0)
            self.assertEqual(r["pass"], want, r["rule"])

    def test_the_family_is_told_its_own_size(self):
        rec = [r["start"]["recent"]["delta"] for r in self.g]
        self.assertGreater(max(rec) - min(rec), 200.0, "nine rules that all land in the same $50 band would be a")
        self.assertLess(max(rec), ct.BAR, "suspiciously correlated family")

    def test_the_two_rules_that_lose_least_on_the_recent_window_pay_for_it_on_the_long_record(self):
        """Not a coincidence and not a trade-off the file pretends away: the rows closest to breaking even where the fund
        never failed are the rows that stand aside least, which is also what makes them best where it did fail."""

        best_recent = max(self.g, key=lambda r: r["start"]["recent"]["delta"])["rule"]
        self.assertEqual(best_recent, "ma200_slope")
        self.assertGreater(self.row("ma200_slope")["start"]["long"]["delta"], self.row("ma200")["start"]["long"]["delta"])

    def test_vol_target_never_leverages_and_only_steps_in_halves(self):
        legs = sl.legs(sw.data(), rs.SLEEVE)
        mk = rs.marks_for("voltarget", legs, sorted(legs), "start")
        for v in mk.values():
            self.assertLessEqual(v, 1.0)
            self.assertIn(v, {0.0, 0.5, 1.0})

    def test_the_band_hysteresis_switches_less_than_the_bare_average_and_loses_more_by_it(self):
        bare, band = self.row("ma200"), self.row("ma200_band")
        self.assertLess(band["start"]["recent"]["switches"], bare["start"]["recent"]["switches"])
        self.assertLess(band["start"]["recent"]["delta"], bare["start"]["recent"]["delta"],
                        "fewer switches did not buy a better recent window; the whipsaws were not what it cost")

    def test_the_search_names_its_own_shelter_and_fee_so_no_row_can_claim_a_free_ride(self):
        self.assertEqual(rs.SHELTER, "IEF")
        self.assertEqual(rs.SHELTER_FEE, max(sl.ER_GRID))
        self.assertEqual(rs.SLEEVE, "SPY")


class Cheap(unittest.TestCase):
    def test_reading_days_are_the_first_or_last_session_of_each_month(self):
        legs = sl.legs(sw.data(), rs.SLEEVE)
        dates = sorted(legs)[200:280]
        st = rs.reading_days(dates, "start")
        en = rs.reading_days(dates, "end")
        self.assertEqual(dates[st[0]], dates[0], "the first day of the record is a first-of-month reading")
        self.assertEqual(dates[en[-1]], dates[-1], "the last day of the record is an end-of-month reading")
        self.assertGreater(len(st), 2)

    def test_trailing_statistics_decline_rather_than_guessing(self):
        c = [100.0 + k for k in range(300)]
        self.assertIsNone(rs.ret(c, 252, 100))
        self.assertIsNone(rs.real_vol(c, 20, 5))
        self.assertAlmostEqual(rs.ret(c, 2, 10), c[10] / c[8] - 1.0, places=12)
        self.assertAlmostEqual(rs.drawdown(c, 252, 299), 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
