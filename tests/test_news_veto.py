"""Tests for the news-veto test itself.

The finding of `tools/news_veto.py` is a null, and a null is only worth anything if the apparatus around it is sound: the
veto has to be able to fire, it has to be forbidden from inventing exposure, it has to be shifted by exactly one month,
the dollar sign has to mean what it says, and the classifier must not be able to promote a one-month anecdote. Those are
what this file checks, in that order, plus the corpus' own boundary.
"""

from __future__ import annotations

import contextlib
import io
import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import attention_bar as ab                                   # noqa: E402
import news_veto as nv                                       # noqa: E402


def months(n, y=2016, m=1):
    out = []
    for i in range(n):
        t = m + i
        out.append((y + (t - 1) // 12, (t - 1) % 12 + 1))
    return out


class TheVeto(unittest.TestCase):
    def setUp(self):
        self.marks = {k: 1.0 for k in months(6)}
        self.z = {k: (3.0 if i == 2 else 0.0) for i, k in enumerate(months(6))}

    def test_the_z_scores_come_from_the_tool_that_defines_them(self):
        fin, ctl = nv.z_by_month()
        days, raw_fin, _raw_ctl = ab.load_panel()
        direct = {(d.year, d.month): v for d, v in ab.monthly(days, raw_fin).items()}
        self.assertEqual(fin, direct, "the veto test has started computing attention on its own")

    def test_a_veto_applies_to_the_month_after_the_reading_and_not_to_the_month_of_it(self):
        out = nv.vetoed(self.marks, self.z, 1.0, "warning")
        keys = months(6)
        self.assertEqual(out[keys[2]], 1.0, "the reading month must keep its own exposure: it was not knowable at its")
        self.assertEqual(out[keys[3]], 0.0, "start; a same-month veto is lookahead, which is how this file's answer")

    def test_a_veto_can_only_flatten_and_only_where_the_plan_held_equities(self):
        marks = dict(self.marks)
        marks[months(6)[4]] = 0.0                       # the plan is already in the shelter that month
        out = nv.vetoed(marks, self.z, 1.0, "warning")
        for k in marks:
            self.assertLessEqual(out[k], marks[k], f"{k}: a veto raised exposure, which it is not allowed to do")
        self.assertEqual(out[months(6)[5]], 1.0, "the veto must be a one-month pulse, not a ratchet")

    def test_the_collapse_reading_is_the_mirror_of_the_warning_reading(self):
        low = {k: (-3.0 if i == 2 else 0.0) for i, k in enumerate(months(6))}
        self.assertEqual(nv.vetoed(self.marks, low, 1.0, "collapse")[months(6)[3]], 0.0)
        self.assertEqual(nv.vetoed(self.marks, low, 1.0, "warning")[months(6)[3]], 1.0)

    def test_no_reading_means_no_veto(self):
        self.assertEqual(nv.vetoed(self.marks, {}, 0.5, "warning"), self.marks)


class TheMoney(unittest.TestCase):
    def test_a_veto_that_underperforms_every_month_reports_a_negative_number(self):
        """The sign convention, which the first draft had upside down: it credited the veto with the return of the
        months it stepped aside from."""

        p = nv.paired([0.01] * 12, [0.0] * 12)
        self.assertLess(p["dollars"], 0.0)
        self.assertAlmostEqual(p["dollars"], -0.01 * 100_000.0, places=6)
        self.assertEqual(p["n"], 12)

    def test_a_veto_that_beats_the_plan_reports_a_positive_one(self):
        p = nv.paired([0.0] * 12, [0.004, 0.006] * 6)
        self.assertAlmostEqual(p["dollars"], 0.005 * 100_000.0, places=6)
        self.assertGreater(p["t"], 0.0, "a constant outperformance has no dispersion, so it needs varying months to")
        p2 = nv.paired([0.01, 0.02, 0.03], [0.01, 0.02, 0.03])
        self.assertEqual(p2["t"], 0.0, "have a t; a zero-dispersion pair reports 0 rather than dividing by nothing")

    def test_a_pair_of_identical_plans_is_worth_exactly_nothing(self):
        p = nv.paired([0.01, 0.02, -0.01], [0.01, 0.02, -0.01])
        self.assertEqual(p["dollars"], 0.0)
        self.assertEqual(p["t"], 0.0)


class TheClassifier(unittest.TestCase):
    def test_an_eleven_month_cell_is_not_a_cell(self):
        self.assertIn("too few", nv.grade(nv.MIN_MONTHS - 1, 500.0, 0.0))

    def test_a_control_reproducing_half_the_effect_refutes_the_candidate(self):
        self.assertIn("REFUTED", nv.grade(30, 100.0, 50.0))
        self.assertIn("REFUTED", nv.grade(30, -100.0, -50.0))

    def test_a_positive_cell_under_the_noise_floor_is_noise(self):
        self.assertIn("noise floor", nv.grade(30, ab.NOISE_FLOOR - 1.0, 0.0))

    def test_a_veto_that_lost_money_says_so_instead_of_being_a_candidate(self):
        self.assertIn("cost money", nv.grade(30, -500.0, 0.0))

    def test_only_a_large_positive_unreproduced_cell_is_called_a_candidate(self):
        self.assertIn("CANDIDATE", nv.grade(30, 500.0, 0.0))


class TheCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = nv.run()

    def test_the_first_tradable_month_is_the_month_after_the_first_usable_z(self):
        """Not the month the corpus starts, and not the month the z-scores start: the z needs a year of history, and the
        decision needs the month before the one it governs. Two months of the corpus are therefore unusable by
        construction, which is disclosed rather than quietly absorbed."""

        days, fin, _ctl = ab.load_panel()
        first = min((d.year, d.month) for d, _v in ab.monthly(days, fin).items())
        want = dt.date(first[0] + (first[1] == 12), 1 if first[1] == 12 else first[1] + 1, 1)
        self.assertEqual(self.o["first"], want)
        self.assertEqual(self.o["first"], dt.date(2016, 2, 1), "the corpus' first usable month is 2016-01, so nothing")
        self.assertEqual((self.o["first"] - dt.date(2015, 7, 1)).days, 215, "before February 2016 can be traded on it")

    def test_the_record_is_too_short_for_a_plan_level_claim_and_the_tool_says_so(self):
        self.assertLess(self.o["windows"], nv.CAP_WINDOWS)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            nv.report(self.o)
        self.assertIn("UNRESOLVABLE", buf.getvalue())

    def test_every_financial_cell_on_this_record_is_negative(self):
        cells = [r for r in self.o["rows"] if r["basket"] == "financial"]
        self.assertEqual(len(cells), 6, "2 readings x 3 thresholds, each with its control: 12 rows, 6 candidates")
        self.assertEqual(len(self.o["rows"]), 12)
        for r in cells:
            self.assertLess(r["dollars"], 0.0, f"{r['mode']} at θ={r['threshold']}")

    def test_the_control_basket_is_never_more_positive_than_the_financial_one(self):
        for mode in ("warning", "collapse"):
            for th in ab.THRESHOLDS:
                f = next(r for r in self.o["rows"] if r["mode"] == mode and r["threshold"] == th
                         and r["basket"] == "financial")
                c = next(r for r in self.o["rows"] if r["mode"] == mode and r["threshold"] == th
                         and r["basket"] == "control")
                self.assertGreater(c["dollars"], f["dollars"],
                                   f"{mode} θ={th}: the control lost less than the financial basket, so the input")

    def test_attention_does_not_cluster_at_the_rules_turning_points(self):
        self.assertLess(self.o["turn_abs_z"], self.o["all_abs_z"] + 0.2,
                        "H3 would be back in play; re-read the note before quoting this file")


if __name__ == "__main__":
    unittest.main()
