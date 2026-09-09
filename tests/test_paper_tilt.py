"""Tests for the live income book, which is the first artefact in this repository that has to face forward.

Everything else in the tools directory reads the past. A paper book is different: it makes a claim a calendar will judge. So
these tests are not about performance — there is nothing to perform yet, and that is the point — they are about whether the
book can be *read honestly* later: where its weight came from, what fee its witness is charged, whether a caller can quietly
change either, and whether the two books on disk are the books the tools say they are.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import mix_sweep as ms                                       # noqa: E402
import fund_fees                                        # noqa: E402
import paper                                                 # noqa: E402


class TheWeight(unittest.TestCase):
    def test_the_tilt_weight_is_measured_and_not_chosen_here(self):
        """The live book's only parameter, pinned to the tool that measured it. If `mix_sweep`'s control row ever moves,
        the book that carries its weight has to move with it or a test has to be told why."""

        row = next(r for r in ms.MIXES if r[0] == ms.CONTROL)
        self.assertEqual(paper.TILT_WEIGHT, row[1])
        self.assertFalse(row[2], "the control has no brake, and the live book must not quietly add one")

    def test_the_book_holds_the_two_funds_the_measurement_used(self):
        w = paper.tilt_weights()
        self.assertEqual(set(w), set(paper.TILT_SERIES))
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["QQQ"], paper.TILT_WEIGHT)
        self.assertLess(sum(w.values()), 1.0 + 1e-12, "a tilt that borrows is a different claim than the one measured")

    def test_a_caller_may_not_choose_the_weight(self):
        argv = sys.argv
        sys.argv = ["paper.py", "init", "--book", "scratch", "--model", "tilt", "--tilt", "0.70"]
        try:
            with self.assertRaises(SystemExit) as got, redirect_stdout(io.StringIO()):
                paper.main()
        finally:
            sys.argv = argv
        self.assertIn("not a caller's choice", str(got.exception))


class TheSignal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = paper.load_data(dt.date(2026, 9, 4))
        cls.sig = paper.signal_for(cls.data, dt.date(2026, 9, 4), "tilt")

    def test_it_forecasts_nothing_and_hurdles_nothing(self):
        self.assertEqual(self.sig.target_weights, paper.tilt_weights())
        self.assertEqual(self.sig.asset_returns, {}, "a balance has no view to disclose")
        self.assertEqual(self.sig.cash_return, 0.0)

    def test_its_name_says_what_it_is_and_charges_each_fund_its_own_fee(self):
        name = self.sig.name
        self.assertIn("not a signal", name)
        order = sorted(self.sig.target_weights, key=lambda k: (-self.sig.target_weights[k], k))
        want = " / ".join(f"{paper.fee_for(s):.3%}" for s in order)
        self.assertIn(f"at {want}", name, f"fees must be listed in the order the funds are listed: {name}")
        for s in order:
            self.assertIn(f"{self.sig.target_weights[s]:.0%} {s}", name)

    def test_the_shelter_model_still_reports_its_reading_date_and_this_one_has_none_to_report(self):
        self.assertIsNone(paper.signal_for(self.data, dt.date(2026, 9, 4), "tilt").asset_returns.get("SPY"))
        shelter = paper.signal_for(self.data, dt.date(2026, 9, 4), "shelter")
        self.assertIn("MA200 read", shelter.name)
        self.assertEqual(paper.book_sleeves("tilt"), paper.TILT_SERIES)
        self.assertEqual(paper.book_sleeves("shelter"), ("SPY", paper.SHELTER))
        self.assertEqual(paper.book_sleeves("constant"), (paper.CANDIDATE_SERIES,))
        self.assertEqual(len(paper.book_sleeves("trend")), 8)


class TheWitness(unittest.TestCase):
    def test_every_posted_fund_can_witness_a_book_at_its_own_fee(self):
        for sym in sorted(paper.POSTED):
            spec = paper.comparator_spec(sym)
            self.assertEqual(spec["weights"], {sym: 1.0})
            self.assertAlmostEqual(spec["expense_ratio"], paper.FEES[sym], places=8, msg=sym)
            self.assertEqual(spec["name"], f"100% {sym}")

    def test_the_income_book_s_witness_is_charged_the_benchmark_s_own_fee_not_the_book_s(self):
        """Round 81's finding, kept as an assertion rather than a memory.

        The tilt holds two funds and pays a weighted fee for them; its witness holds one fund and must be charged that fund's
        fee. Charging the book's blended 14.7 bps to a benchmark that costs 3 bps manufactures three quarters of the tilt's
        measured edge out of a spreadsheet, which is the most expensive kind of edge there is.
        """

        spec = paper.comparator_spec("VOO")
        weighted = sum(w * paper.FEES[s] for s, w in paper.tilt_weights().items())
        self.assertAlmostEqual(spec["expense_ratio"], paper.FEES["VOO"], places=10)
        self.assertLess(spec["expense_ratio"], weighted,
                        f"the witness is being charged {spec['expense_ratio']:.5%} against a book at {weighted:.5%}")
        self.assertAlmostEqual(weighted, 0.0014725, delta=1e-9, msg="the tilt's blended fee moved; so did every friction figure")

    def test_a_fund_with_no_source_still_cannot_witness_and_one_with_a_source_can(self):
        """The refusal's reason moved in round 94, and the refusal itself did not.

        It used to bite four named funds, because this repository had no source for their ratios and a benchmark charged a
        fee nobody posted is a benchmark nobody can verify (round 81). All twelve legs the archive quotes now have a
        published ratio in `fund_fees.py`, so those four may witness at their own fee — which is what round 81 was asking
        for, not a permanent ban. What is still refused is a ticker with no source at all.
        """

        for sym in ("IEF", "EFA", "GLD", "DBC"):
            self.assertIn(sym, paper.POSTED, f"{sym} has a sourced ratio and may witness")
            self.assertAlmostEqual(paper.posted_fee(sym), fund_fees.fee_for(sym), places=10, msg=sym)
        for sym in ("XLU", "IEFH", "VTIP"):
            self.assertNotIn(sym, paper.POSTED, f"{sym} is not in the sourced table")
            with self.assertRaises(SystemExit, msg=sym):
                paper.posted_fee(sym)


class TheBooksOnDisk(unittest.TestCase):
    """The artefacts this round produced. Asserted rather than assumed, because a claim about a forward record is worth
    nothing if the record it refers to is not the one being kept."""

    names = ("tilt", "tilt_qqq")

    def cfg(self, name):
        return json.loads((ROOT / "data" / "paper" / "books" / name / "model.json").read_text())

    def test_both_income_books_exist_and_witness_the_two_indexes_the_objective_names(self):
        for name, sym in (("tilt", "VOO"), ("tilt_qqq", "QQQ")):
            self.assertTrue((ROOT / "data" / "paper" / "books" / name / "ledger.jsonl").exists(), msg=name)
            cfg = self.cfg(name)
            self.assertEqual(cfg["model_key"], "tilt", msg=name)
            self.assertEqual(cfg["comparator"]["weights"], {sym: 1.0}, msg=name)
            self.assertAlmostEqual(cfg["comparator"]["expense_ratio"], paper.FEES[sym], places=8, msg=name)

    def test_the_two_books_run_one_construction_so_the_only_difference_is_the_witness(self):
        a, b = (self.cfg(n) for n in self.names)
        self.assertEqual(a["fees"], b["fees"])
        self.assertEqual(a["sleeves"], b["sleeves"])
        self.assertEqual(a["opening"], b["opening"])
        self.assertEqual(a["monthly"], b["monthly"])
        self.assertEqual(a["spread_bps"], b["spread_bps"])
        self.assertNotEqual(a["comparator"], b["comparator"])

    def test_every_book_on_disk_shares_the_anchor_so_the_books_stay_comparable_as_accounts(self):
        roots = [ROOT / "data" / "paper"] + [(ROOT / "data" / "paper" / "books" / d.name)
                                            for d in (ROOT / "data" / "paper" / "books").iterdir() if d.is_dir()]
        asofs = set()
        for r in roots:
            ledger = r / "ledger.jsonl"
            if not ledger.exists():
                continue
            first = json.loads(ledger.read_text().splitlines()[0])
            asofs.add(first["asof"])
            self.assertTrue((r / "shadow.jsonl").exists(), f"{r.name} has no witness chain")
            witness = json.loads((r / "shadow.jsonl").read_text().splitlines()[0])
            self.assertEqual(witness["opening_value"], first["opening_value"], f"{r.name}: the witness starts elsewhere")
        self.assertEqual(len(asofs), 1, f"books anchored on different dates cannot be compared: {asofs}")

    def test_no_book_claims_a_verdict_before_an_interval_has_elapsed(self):
        for name in self.names:
            out = io.StringIO()
            argv = sys.argv
            sys.argv = ["paper.py", "report", "--book", name]
            try:
                with redirect_stdout(out):
                    paper.main()
            finally:
                sys.argv = argv
            text = out.getvalue()
            self.assertIn("chain intact", text, msg=name)
            self.assertRegex(text, r"LEVEL with doing-nothing|underpowered",
                             f"{name} is one entry old and must not render a verdict")
            self.assertNotIn("DOMINATED", text, msg=name)

    def test_the_tilt_books_config_is_regenerated_not_edited_by_the_report_that_reads_it(self):
        """Round 70's rule, tested on the live artefact: the report may not rebuild its benchmark from literals, so two
        readings of the same config must produce the same comparator."""

        cfg = self.cfg("tilt")
        spec = paper.comparator_spec(cfg["comparator"]["weights"].popitem()[0])
        self.assertEqual(spec["name"], cfg["comparator"]["name"])


if __name__ == "__main__":
    unittest.main()
