"""Tests for the binding-payout sweep.

The subject is a scale: withdrawal levels expressed as multiples of one construction's capacity. Scales are where bugs live,
because a multiple passed where a dollar belongs produces a table of plausible-looking zeros — which is exactly what the
first version of this file printed. So the first tests check the ruler, and only then the answer.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import binding_payout as bp                                  # noqa: E402
import rotation_search as rse                                # noqa: E402
import tilt_brake as tb                                      # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402


class BindingPayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = bp.grid(100_000.0, 10)
        cls.rows = {r["name"]: r for r in cls.o["rows"]}
        cls.tb_grid = tb.grid(100_000.0, 10)
        cls.tb_rows = {r["rule"]: r for r in cls.tb_grid["rows"]}

    def w(self, name, window="long"):
        return self.rows[name]["windows"][window]

    def test_the_multiples_are_dollars_by_the_time_they_reach_the_payout_model(self):
        """The bug this test exists for: handing 0.90, 1.10, 2.00 to a scorer expecting dollars per month produces a plan
        that can never fail and a table of 0.0% cells. A sweep whose top row is 2x capacity must produce a failure."""

        for m, dollars in self.o["payouts"]["long"].items():
            self.assertAlmostEqual(dollars, m * self.o["base"]["long"], places=2)
            self.assertGreater(dollars, 100.0, f"{m}x reached the scorer as a multiple, not a payout")
        self.assertTrue(any(self.w(n)["p_fails"][2.00] > 0.2 for n in bp.CONSTRUCTIONS),
                        "nothing fails at twice capacity; the sweep is not binding at all")

    def test_failure_probability_never_falls_as_the_withdrawal_rises(self):
        for name in bp.CONSTRUCTIONS:
            for window in ("long", "recent"):
                p = [self.w(name, window)["p_fails"][m] for m in bp.MULTIPLES]
                self.assertEqual(p, sorted(p), f"{name} {window}: a larger withdrawal bought safety")

    def test_the_inside_flag_is_the_capacity_itself_and_not_a_second_opinion(self):
        for name in bp.CONSTRUCTIONS:
            for window in ("long", "recent"):
                w = self.w(name, window)
                for m in bp.MULTIPLES:
                    self.assertEqual(w["inside"][m], w["safe"] >= m * self.o["base"][window] - 1e-9,
                                     f"{name} {window} {m}x")

    def test_the_control_never_beats_itself(self):
        for window in ("long", "recent"):
            for m in bp.MULTIPLES:
                self.assertFalse(self.w(bp.CONTROL, window)["beats_control"][m], f"{window} {m}")
        self.assertEqual(self.w(bp.CONTROL)["counts"], self.w(bp.CONTROL)["ctl_counts"])

    def test_the_beat_flag_and_the_counts_are_recomputed_from_the_row(self):
        for name in bp.CONSTRUCTIONS:
            for window in ("long", "recent"):
                w = self.w(name, window)
                ctl = self.w(bp.CONTROL, window)
                for m in bp.MULTIPLES:
                    self.assertEqual(w["beats_control"][m], w["p_fails"][m] < ctl["p_fails"][m], f"{name} {window} {m}")
                    self.assertEqual(w["counts"][m], int(round(w["p_fails"][m] * w["n"])), f"{name} {window} {m}")

    def test_the_control_is_the_same_number_the_previous_round_published(self):
        """The scale for this whole file is the static blend's capacity, and round 76 published it. If a shared helper moves,
        the ruler moves, and this is where it shows."""

        for window in ("long", "recent"):
            self.assertAlmostEqual(self.w(bp.CONTROL, window)["safe"],
                                   self.tb_rows["blend_sq"]["cells"][("start", window)]["safe"], places=6, msg=window)

    def test_the_answer_that_only_appears_once_the_payout_binds(self):
        """Round 76 could not see any brake help, because at $435.47 nothing fails. At 1.10x of the control's capacity the
        same two brakes fail on 6 and 17 windows where the control fails on 22, and the count difference is printed for that
        reason — these windows overlap, so the counts are the raw material and no interval is claimed."""

        ctl = self.w(bp.CONTROL)["counts"][1.10]
        self.assertEqual(ctl, 22)
        self.assertLess(self.w("brake_either")["counts"][1.10], ctl)
        self.assertLess(self.w("brake_both")["counts"][1.10], ctl)
        self.assertEqual(self.w("dm12_sq")["counts"][1.10], 0)
        self.assertEqual(self.w("qqq_only")["counts"][1.10], 0)

    def test_the_same_protection_is_a_cost_on_the_recent_window(self):
        """The reversal, in both directions: on 2011-2026 the brakes are the worst rows on the page at the control's own
        capacity, and the brake's capacity there is below the control's. Any recommendation that quotes only the long table
        has to answer this one first."""

        for name in ("brake_both", "brake_either", "dm12_sq"):
            self.assertGreater(self.w(name, "recent")["p_fails"][1.00], self.w(bp.CONTROL, "recent")["p_fails"][1.00], name)
            self.assertLess(self.w(name, "recent")["multiple"], self.w(bp.CONTROL, "recent")["multiple"], name)
        self.assertLess(self.w("brake_both", "recent")["multiple"], 1.0,
                        "brake_both's long-window capacity is a hair above the control's; it is the recent one that is not")

    def test_dm12_sq_is_the_only_row_that_dominates_the_control_on_the_long_record_and_it_does_not_on_the_recent_one(self):
        w = self.w("dm12_sq")
        self.assertGreater(w["multiple"], 1.4)
        self.assertEqual(w["counts"][1.25], 0)
        self.assertLess(self.w("dm12_sq", "recent")["multiple"], 1.0)

    def test_the_calendar_never_tests_the_growth_fund_against_the_crash_it_survives(self):
        """QQQ-only fails 0 of 132 long windows and beats the control's capacity by 22%. None of that was tested against
        2000-2002, because the shared calendar starts when GLD's series and a 200-day warmup allow. The caveat is asserted
        so it cannot be forgotten by the next reader of the top row."""

        self.assertEqual(self.o["since"].year, 2005)
        self.assertGreater(self.w("qqq_only")["multiple"], 1.2)
        self.assertEqual(self.w("qqq_only")["counts"][1.10], 0)

    def test_an_unnamed_construction_refuses_rather_than_defaulting(self):
        with self.assertRaises(KeyError):
            bp.marks_for("ma200", {}, {}, [])

    def test_every_row_carries_every_window_and_every_multiple(self):
        for r in self.o["rows"]:
            self.assertEqual(sorted(r["windows"]), ["long", "recent"])
            for w in r["windows"].values():
                self.assertEqual(sorted(w["p_fails"]), sorted(bp.MULTIPLES))
                self.assertEqual(sorted(w["inside"]), sorted(bp.MULTIPLES))
                self.assertGreater(w["n"], 60)

    def test_no_row_is_scored_on_a_calendar_the_previous_rounds_did_not_use(self):
        rot = rse.grid(100_000.0, 10)
        self.assertEqual(self.o["since"], rot["since"])
        self.assertEqual(self.o["recent"], rot["recent"])


if __name__ == "__main__":
    unittest.main()
