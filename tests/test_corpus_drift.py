"""`corpus_drift.py`: how far the vendor's re-derivation of history reaches, and where it stops.

The tool exists because round 8 fetched the same window twice and 72.6% of the rows disagreed, which is either trivia or a crack in the archive
depending on whether the published figures survive it. These tests cannot re-fetch — the suite is offline by design — so they pin the two things
the tool itself contributes: the row statistics, and the judgement about whether a delta reaches a published figure. The arithmetic it reports
comes from the spec functions, and a test below pins that it does not reimplement them.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import ba006                                 # noqa: E402
import corpus_drift as cd                    # noqa: E402

HEADER = "date,symbol,tr_open,tr_close\n"


def write_snapshot(where: Path, rows: list[tuple[str, str, float, float]]) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{d},{s},{o!r},{c!r}\n" for d, s, o, c in rows)
    (where / "market_daily.csv").write_text(HEADER + body)
    (where / "cash_daily.csv").write_text("date,cash_factor,rate,rate_pct,DGS3MO\n")
    return where


class TheRowDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_only_the_rows_that_moved_are_counted_and_measured(self):
        panel = [(f"2026-0{d}-01", s, 100.0, 200.0) for d in range(1, 5) for s in ("VOO", "QQQ")]
        a = write_snapshot(self.base / "a", panel)
        moved = [(d, s, o, c * (1 + 1e-6) if (d, s) == ("2026-02-01", "QQQ") else c) for d, s, o, c in panel]
        b = write_snapshot(self.base / "b", moved)
        d = cd.row_drift(a, b)
        self.assertEqual((d["rows_a"], d["rows_b"], d["shared"]), (8, 8, 8))
        self.assertEqual(d["differing"], 1, "eight rows, one of them moved; the count must say one")
        self.assertAlmostEqual(d["max_rel"], 1e-6, delta=1e-9)
        self.assertEqual(d["worst"], ("2026-02-01", "QQQ"), "the report has to name the worst row, not just a number")

    def test_a_panel_that_does_not_line_up_is_a_problem_not_a_small_difference(self):
        a = write_snapshot(self.base / "a", [("2026-01-01", "VOO", 1.0, 2.0), ("2026-01-02", "VOO", 1.0, 2.0)])
        b = write_snapshot(self.base / "b", [("2026-01-01", "VOO", 1.0, 2.0)])
        self.assertEqual(cd.row_drift(a, b)["only_one_side"], 1)


class TheJudgement(unittest.TestCase):
    """`compare` decides whether a re-fetch is the same archive. Its tolerance is the precision the figure is printed at (r112)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        panel = [("2026-01-01", "VOO", 100.0, 200.0)]
        self.a = write_snapshot(self.base / "a", panel)
        self.b = write_snapshot(self.base / "b", panel)
        self._figures = cd.figures
        self.addCleanup(setattr, cd, "figures", self._figures)

    def figures(self, first: dict, second: dict):
        def fake(_snapshot: Path) -> dict:
            return dict(first) if _snapshot == self.a else dict(second)
        cd.figures = fake
        return fake

    def test_noise_inside_the_printed_precision_is_reported_and_does_not_stop_the_run(self):
        """Round 8's actual result: every figure moved at the 1e-7 level and not one published digit changed."""

        base = {"last": "2026-09-04", "sessions": 8458, "p0_bill": 830.792908, "p0_median_multiple": 1.241437,
                "sleeve20_bill": 1044.734292, "sleeve20_drawdown": 0.2476060}
        moved = dict(base, p0_bill=830.792927, p0_median_multiple=1.241436, sleeve20_bill=1044.733526,
                     sleeve20_drawdown=0.2476061)
        self.figures(base, moved)
        report, problems = cd.compare(self.a, self.b)
        self.assertEqual(problems, [], f"sub-cent drift must not be reported as a changed archive: {problems}")
        self.assertAlmostEqual(report["figures"]["p0_bill"]["delta"], 1.9e-05, delta=1e-6)
        self.assertAlmostEqual(report["figures"]["sleeve20_bill"]["delta"], -7.66e-04, delta=1e-6)

    def test_a_figure_that_moves_more_than_its_printed_unit_is_named_with_its_tolerance(self):
        base = {"last": "2026-09-04", "sessions": 8458, "p0_bill": 830.0, "p0_median_multiple": 1.24,
                "sleeve20_bill": 1044.0, "sleeve20_drawdown": 0.2476}
        self.figures(base, dict(base, p0_bill=830.02))
        _report, problems = cd.compare(self.a, self.b)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("P0's affordable bill", problems[0])
        self.assertIn("tolerance $0.005", problems[0], "a judgement without the number that judged it is an opinion (r112)")

    def test_a_figure_sitting_near_zero_cannot_be_forgiven_by_printed_precision(self):
        """Printed tolerance is absolute, so it goes slack exactly where it matters: a $0.004 bill halved is still "unchanged to the cent"."""

        base = {"last": "2026-09-04", "sessions": 8458, "p0_bill": 0.004, "p0_median_multiple": 1.24,
                "sleeve20_bill": 1044.0, "sleeve20_drawdown": 0.2476}
        self.figures(base, dict(base, p0_bill=0.008))       # inside the cent tolerance, a doubling of the bill
        _report, problems = cd.compare(self.a, self.b)
        self.assertTrue(any("P0's affordable bill" in p for p in problems),
                        f"a doubled bill printed identically must still fail: {problems}")

    def test_two_corpora_ending_on_different_sessions_never_pass(self):
        base = {"last": "2026-09-04", "sessions": 8458, "p0_bill": 830.0, "p0_median_multiple": 1.24,
                "sleeve20_bill": 1044.0, "sleeve20_drawdown": 0.2476}
        self.figures(base, dict(base, last="2026-09-03"))
        _report, problems = cd.compare(self.a, self.b)
        self.assertTrue(any("different sessions" in p for p in problems), problems)


class TheToolDelegates(unittest.TestCase):
    def test_the_figures_come_from_the_spec_functions_not_a_second_implementation(self):
        """Every published figure has one implementation (r114); this tool must read through it or say nothing."""

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        snap = write_snapshot(Path(tmp.name) / "s", [("2026-01-01", "VOO", 1.0, 2.0)])
        loaded, legs = cd.load_csv_market_data, ba006.price_legs
        boom = AssertionError("the tool grew its own arithmetic")
        try:
            cd.load_csv_market_data = lambda *_a, **_k: object()
            ba006.price_legs = lambda _md: (_ for _ in ()).throw(boom)
            with self.assertRaises(AssertionError) as caught:
                cd.figures(snap)
            self.assertIs(caught.exception, boom, "figures() must reach the spec's own leg builder")
        finally:
            cd.load_csv_market_data, ba006.price_legs = loaded, legs


class TheCommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_the_exit_code_is_the_verdict(self):
        panel = [("2026-01-01", "VOO", 100.0, 200.0)]
        a = write_snapshot(self.base / "a", panel)
        b = write_snapshot(self.base / "b", panel)
        original = cd.compare
        cd.compare = lambda *_a, **_k: ({"drift": {"rows_a": 1, "rows_b": 1, "shared": 1, "only_one_side": 0,
                                                   "differing": 0, "share": 0.0, "median_rel": 0.0, "max_rel": 0.0,
                                                   "worst": None},
                                        "first": _figs(), "second": _figs(), "figures": {}}, [])
        try:
            argv = ["corpus_drift", str(a), str(b)]
            sys.argv = argv
            self.assertEqual(cd.main(), 0)
        finally:
            cd.compare = original

    def test_a_dir_without_prices_is_refused_before_any_arithmetic(self):
        empty = self.base / "empty"
        empty.mkdir()
        sys.argv = ["corpus_drift", str(empty), str(empty)]
        with self.assertRaises(SystemExit) as caught:
            cd.main()
        self.assertIn("needs two snapshots", str(caught.exception))


def _figs() -> dict:
    return {"last": "2026-09-04", "sessions": 1, "p0_bill": 1.0, "p0_median_multiple": 1.0,
            "sleeve20_bill": 1.0, "sleeve20_drawdown": 0.1}


if __name__ == "__main__":
    unittest.main()
