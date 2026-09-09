"""Tests for the decision sheet.

The sheet exists because hand-written summaries drift, so the tests are built around one idea: nothing on the page may be a
number the tools did not produce. That is checked three ways — the source carries no dollar literal, every figure in the
rendered text is present in the data the renderer was handed, and the sheet's figures are differential-tested against the tools
themselves. The refusal paths matter just as much: a sheet that cannot say no is a brochure.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import decision_sheet as ds                                  # noqa: E402
import mix_sweep as ms                                       # noqa: E402
import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402


def leaves(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from leaves(v)
    elif isinstance(value, list):
        for v in value:
            yield from leaves(v)
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        yield float(value)


class SourceDiscipline(unittest.TestCase):
    def test_the_sheet_contains_no_dollar_amount_of_its_own(self):
        src = pathlib.Path(ds.__file__).read_text()
        self.assertIsNone(re.search(r"\$\s?\d", src),
                          "a typed figure in the sheet is a figure nobody measured")

    def test_the_sheet_types_no_share_of_paid_in(self):
        """Every share-of-paid-in on the page must be interpolated, never typed: round 100 found the typed sentence inverted."""

        src = pathlib.Path(ds.__file__).read_text()
        self.assertIsNone(re.search(r"\d+(\.\d+)?% of paid in", src),
                          "a percentage of paid in written into the renderer is a figure nobody recomputes")

    def test_the_friction_figures_arrive_from_the_engine_and_are_printed_as_given(self):
        o = ds.sheet(100_000.0, None, "income", "recent", None)
        fr = o["execution"]["friction"]
        self.assertEqual(sorted(fr), ["bill_recent_pct", "bill_record_pct", "drift_record_pct", "times_the_bill"])
        self.assertGreater(fr["times_the_bill"], 100.0, "the policy was published as a *fraction* of the bill for four years")
        text = ds.render(o)
        self.assertIn(f"{fr['drift_record_pct']:.2f}%", text)
        self.assertIn(f"{fr['bill_record_pct']:.3f}%", text)

    def test_every_figure_the_sheet_prints_came_from_the_data_it_was_handed(self):
        o = ds.sheet(100_000.0, 900.0, "income", "recent", None)
        have = sorted(leaves(o))
        text = ds.render(o)
        figures = [float(f.replace(",", "").lstrip("$-").replace("$", ""))
                   for f in re.findall(r"\$?-?[\d,]+\.\d\d", text)]
        self.assertGreater(len(figures), 10, "the sheet printed almost nothing; the test would pass vacuously")
        # The renderer prints a negative premium as a minus sign and a positive magnitude, so both are the same fact.
        for f in figures:
            self.assertTrue(any(abs(f - abs(v)) <= 0.005 + 0.0001 * abs(v) for v in have),
                            f"{f:,.2f} appears on the page and nowhere in the data")

    def test_each_section_names_the_tool_that_measured_it(self):
        text = ds.render(ds.sheet(100_000.0, None, "insurance", "deep", None))
        for tool in ("mix_sweep.py", "rotation_search.py", "tilt_brake.py"):
            self.assertIn(tool, text)
        self.assertIn("REFUSES", text)


class Numbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = ds.sheet(100_000.0, 900.0, "income", "recent", None)
        cls.big = ds.sheet(250_000.0, 2000.0, "income", "recent", None)

    def test_the_sheet_agrees_with_the_tool_it_reads(self):
        rot = rse.grid(100_000.0, 10)
        for label, name in (("control", "blend_sq"), ("plain SPY", "spy_only"), ("plain QQQ", "qqq_only")):
            there = next(r for r in rot["rules"] if r["rule"] == name)["cells"][("start", "recent")]["safe"]
            self.assertAlmostEqual(self.o["must_beat"][label]["recent"], there, places=6, msg=label)

    def test_everything_scales_linearly_and_nothing_else_changes(self):
        for name in self.o["positions"]:
            for window in ("deep", "recent"):
                self.assertAlmostEqual(self.big["positions"][name]["capacity"][window],
                                       2.5 * self.o["positions"][name]["capacity"][window], places=6,
                                       msg=f"{name} {window}")

    def test_the_sheet_says_when_it_last_looked_at_the_data(self):
        from boring_alpha.data.csv_loader import load_csv_market_data
        last = max(sl.legs(load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE), "SPY"))
        self.assertEqual(self.o["as_of"], last.isoformat())
        self.assertEqual(self.o["deep_start"], ms.grid(100_000.0, 10)["deep"].isoformat())

    def test_the_ask_is_priced_at_the_withdrawal_asked_and_not_at_the_nearest_grid_point(self):
        q = self.o["asked"]
        self.assertAlmostEqual(q["as_multiple_of_control_recent"], 900.0 / self.o["must_beat"]["control"]["recent"],
                               places=9)
        self.assertTrue(0.0 <= q["p_fail"] <= 1.0)
        again, n = ds._p_fail_at(100_000.0, 900.0, self.o["book"], "recent")
        self.assertEqual(q["p_fail"], again)
        self.assertEqual(q["n"], n)
        other, _ = ds._p_fail_at(100_000.0, 1090.0, self.o["book"], "recent")
        self.assertGreaterEqual(other, q["p_fail"], "a larger withdrawal at exactly the sheet's own measure")

    def test_the_income_position_is_the_tilt_and_the_insurance_position_is_the_brake(self):
        self.assertEqual(self.o["book"], "mix_100")
        ins = ds.sheet(100_000.0, None, "insurance", "deep", None)
        self.assertEqual(ins["book"], "brake_75")
        self.assertGreater(self.o["positions"]["mix_100"]["capacity"]["recent"],
                           self.o["positions"]["mix_00"]["capacity"]["recent"])
        self.assertFalse(self.o["positions"]["mix_100"]["meets_budget"]["deep"])
        self.assertTrue(ins["positions"]["brake_75"]["meets_budget"]["deep"])

    def test_the_result_is_serialisable(self):
        back = json.loads(json.dumps(self.o, sort_keys=True, default=str))
        self.assertEqual(back["book"], "mix_100")
        self.assertIn("brake_75", back["positions"])


class Refusals(unittest.TestCase):
    def test_every_refused_request_names_the_missing_thing_and_what_would_change_it(self):
        for ask in ds.REFUSED_ASKS:
            with self.assertRaises(ds.Refused) as got:
                ds.sheet(100_000.0, None, "income", "recent", ask)
            self.assertTrue(got.exception.fix, ask)
            self.assertIn(ask, ds.REFUSED_ASKS)

    def test_an_unrecognised_ask_refuses_rather_than_defaulting_to_income(self):
        with self.assertRaises(ds.Refused):
            ds.sheet(100_000.0, None, "income", "recent", "crypto")

    def test_a_withdrawal_the_book_cannot_fund_refuses_and_prints_the_ceiling(self):
        with self.assertRaises(ds.Refused) as got:
            ds.sheet(100_000.0, 900.0, "insurance", "deep", None)
        self.assertIn("466.68", str(got.exception))

    def test_the_income_position_on_the_deep_record_refuses_and_points_at_the_only_book_that_qualifies(self):
        with self.assertRaises(ds.Refused) as got:
            ds.sheet(100_000.0, 500.0, "income", "deep", None)
        self.assertIn("insurance", got.exception.fix)
        self.assertIn("466.68", got.exception.fix)

    def test_nonsense_parameters_refuse_before_anything_is_priced(self):
        for bad in (dict(capital=0.0), dict(capital=-5.0), dict(want=0.0), dict(want=-1.0),
                    dict(position="both"), dict(horizon="week")):
            args = dict(capital=100_000.0, want=None, position="income", horizon="recent", ask=None)
            args.update(bad)
            with self.assertRaises(ds.Refused, msg=str(bad)):
                ds.sheet(**args)

    def test_main_exits_three_on_a_refusal_and_prints_the_reason_where_it_can_be_read(self):
        argv = sys.argv
        err, out = io.StringIO(), io.StringIO()
        sys.argv = ["decision_sheet.py", "--ask", "options"]
        try:
            with redirect_stderr(err), redirect_stdout(out):
                code = ds.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 3)
        self.assertIn("REFUSED", err.getvalue())
        self.assertNotIn("REFUSED", out.getvalue())

    def test_main_exits_zero_on_a_sheet_and_tells_the_reader_how_to_regenerate_it(self):
        argv = sys.argv
        out = io.StringIO()
        sys.argv = ["decision_sheet.py", "--capital", "100000", "--position", "income", "--want", "900"]
        try:
            with redirect_stdout(out):
                code = ds.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 0)
        self.assertIn("regenerate with", out.getvalue())
        self.assertIn("--want 900", out.getvalue())


if __name__ == "__main__":
    unittest.main()
