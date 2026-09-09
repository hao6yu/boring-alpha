"""Tests for `cost_conventions.py`, the audit that prices the prices.

Round 104 wrote the tool after finding a five-file disagreement about what a loan costs (`paper` had been corrected from 150 to
202 bps in round 30; the research family had kept typing 150) and a runner that crashed because its `rows` list had been deleted
under it. Every test below either reprints a fact the tool publishes, or proves the check can fail — r93's rule that an audit must
meet the engine's own output and a check needs its negative test.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cost_conventions as cc                                   # noqa: E402
import fund_fees                                                # noqa: E402
import paper                                                    # noqa: E402
import withdrawal_capacity                                      # noqa: E402


class TheInventory(unittest.TestCase):
    def test_the_two_one_way_conventions_are_both_found_and_named(self):
        sides = {round(r["normalised"][0], 4) for r in cc.inventory()
                 if r["unit"] == "side" and r["literal"] and r["normalised"]}
        self.assertIn(2.0, sides, "the withdrawal/rotation family's 2 bps is missing from the inventory")
        self.assertIn(3.0, sides, "the paper engine's 3 bps is missing from the inventory")
        files = {r["file"] for r in cc.inventory() if r["name"] == "SPREAD_BPS"}
        self.assertIn("paper.py", files)

    def test_no_cost_fact_is_written_twice_with_two_answers(self):
        """The regression this round was written for: `BORROW_SPREAD` read 202 bps in the forward engine and 150 bps in two
        research files, which is 52 bps on the one input that decides whether leverage pays."""

        bad = [d for d in cc.duplicates(cc.inventory()) if not d["agree"]]
        self.assertEqual(bad, [], f"a trading cost has two answers: {bad}")

    def test_the_loan_price_is_one_fact_reachable_from_the_research_family(self):
        self.assertEqual(withdrawal_capacity.BORROW_SPREAD, paper.BORROW_SPREAD,
                         "the studies are pricing a loan the desk stopped quoting")
        self.assertGreater(paper.BORROW_SPREAD, 0.0)

    def test_the_prose_scan_sees_a_typed_figure_and_ignores_an_interpolated_one(self):
        scratch = {"made_up.py": 'print("borrow at cash + 150 bps")\n'
                                 'print(f"borrow at cash + {paper.BORROW_SPREAD * 10_000:.0f} bps")\n'}
        hits = cc.prose(scratch)
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0]["figure"], "150")

    def test_the_stale_loan_quote_is_not_reprinted_anywhere(self):
        offenders = [p.name for p in (ROOT / "tools").glob("*.py") if "cash + 150 bps" in p.read_text()]
        self.assertEqual(offenders, [], "the pre-round-30 desk quote came back, in prose")


class TheMeasurement(unittest.TestCase):
    """The tool's right to exit 0 comes from having re-run the battery, not from the constants agreeing."""

    @classmethod
    def setUpClass(cls):
        cls.m = cc.measure()

    def test_the_pass_set_survives_every_cost_the_tools_quote(self):
        self.assertTrue(self.m["verdicts_invariant"], f"a verdict moves with the convention: {self.m['runs']}")
        self.assertGreaterEqual(len(self.m["runs"]), 3, "the ladder has too few rungs to conclude anything")

    def test_the_widest_move_is_measured_across_runs_and_is_not_the_zero_it_once_printed(self):
        """Round 104's first draft computed the spread *within* each run, so it printed "$0.00" under a sentence about how far
        the figures travel. The number is only meaningful across the ladder."""

        self.assertGreater(self.m["widest_move_dollars_per_month"], 1.0,
                           "the widest move is back to a definitional zero")

    def test_the_sheet_the_reader_actually_uses_carries_the_same_passes_as_the_grid(self):
        names = self.m["runs"][0]["passes"]              # the rule names that cleared every clause
        for want in ("qqq_only", "blend_sq"):
            self.assertIn(want, names, "the two controls that pass stopped passing while this file was being written")


class ItCanFail(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.saved = cc.TOOLS

    def _write(self, name, body):
        (self.dir / name).write_text(body)

    def test_a_second_answer_for_the_same_cost_fails_the_audit(self):
        self._write("a.py", "BORROW_SPREAD = 0.0150\n")
        self._write("b.py", "BORROW_SPREAD = 0.0202\n")
        cc.TOOLS = self.dir
        try:
            dups = cc.duplicates(cc.inventory())
            self.assertTrue(any(d["name"] == "BORROW_SPREAD" and not d["agree"] for d in dups))
            self.assertEqual(cc.report_exit(dups, {"verdicts_invariant": True}), 1)
        finally:
            cc.TOOLS = self.saved

    def test_a_single_copy_of_a_fact_does_not_fail_the_audit(self):
        self._write("a.py", "BORROW_SPREAD = 0.0202\n")
        self._write("b.py", "BORROW_SPREAD = paper.BORROW_SPREAD\n")
        cc.TOOLS = self.dir
        try:
            self.assertEqual(cc.report_exit(cc.duplicates(cc.inventory()), {"verdicts_invariant": True}), 0)
        finally:
            cc.TOOLS = self.saved

    def test_a_verdict_that_moves_fails_the_audit_even_when_the_constants_agree(self):
        self.assertEqual(cc.report_exit([], {"verdicts_invariant": False, "widest_move_dollars_per_month": 12.0}), 1)


class TheRunnerThatWasDead(unittest.TestCase):
    def test_running_the_voltarget_scanner_plain_refuses_instead_of_crashing(self):
        """Round 104 found it printing a comparator line and then dying on a `rows` list whose policy grid had been deleted."""

        r = subprocess.run([sys.executable, str(ROOT / "tools" / "run_voltarget_scan.py")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("wide scan no longer exists", r.stderr + r.stdout)

    def test_the_candidate_path_still_prices_the_one_thing_it_knows(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "run_voltarget_scan.py"), "--candidate"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("comparator", r.stdout)


if __name__ == "__main__":
    unittest.main()
