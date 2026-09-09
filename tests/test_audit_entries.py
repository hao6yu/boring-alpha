"""Every check in the entry audit has to fire on the defect it names, and stay silent on a chain that is merely small.

`tools/audit_entries.py` is the command behind stopping rule 4 — "any sealed entry whose plan line contradicts its own numbers" —
and it exists because round 87 sealed an interval that did exactly that: a note admitting a cent borrowed, a `plan` field
promising the book never borrows, and an empty `violations` tuple. An audit whose negative results are never provoked is
indistinguishable from an audit that does nothing, so each check below is provoked by one fabricated defect, on an entry that is
otherwise consistent. The one exception is the round-87 entry itself, rebuilt from the numbers the rehearsal reported and
expected to be caught by name.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import audit_entries as ae                               # noqa: E402
import paper                                             # noqa: E402
import rehearse_forward as rf                            # noqa: E402
from boring_alpha import journal                                  # noqa: E402

START = dt.date(2026, 9, 4)
MODEL = {"model": "tilt_band", "model_key": "tilt_band", "monthly": 500.0, "opening": 5000.0,
         "comparator": {"name": "100% VOO", "weights": {"VOO": 1.0}, "expense_ratio": 0.0003}}
CLEAN_NOTE = "deposit 500.00, bought 500.00, sold 0.00, expense 0.61 on 5497.00 fund value (SPY 0.31, QQQ 0.30)"


def entry(index: int, month: int, arrived: float, holdings: tuple, closing: float, fee: float = 1.50,
          note: str = CLEAN_NOTE, violations: tuple = (), posted: dt.date | None = None,
          days: int = 0) -> journal.Entry:
    asof = START + dt.timedelta(days=30 * month)
    quotes = [journal.Quote("SPY", 100.0), journal.Quote("QQQ", 100.0), journal.Quote("VOO", 100.0)]
    return journal.Entry(index=index, asof=asof, prior_hash="0" * 64, plan="a plan that never borrows",
                              plan_posted_on=posted or (asof - dt.timedelta(days=30)),
                              opening_value=5000.0 if index == 0 else 0.0, cash_arrived=arrived, invested=arrived,
                              days_to_invest=days, fee_paid=fee, closing_value=closing, quotes=tuple(quotes),
                              holdings=tuple(journal.Holding(s, u) for s, u in holdings),
                              violations=violations, note=note)


def anchor(**kwargs) -> journal.Entry:
    return entry(0, 0, 0.0, (), 5000.0, fee=0.0, note="anchored", **kwargs)


def sealed(holdings=(("SPY", 25.0), ("QQQ", 25.0)), closing=5495.50, arrived=500.0, month=1, **kwargs) -> journal.Entry:
    """The second interval of an otherwise honest book: 5,000 paid in, 500 arrived, holdings worth 5,497, 1.50 of cost."""

    return entry(1, month, arrived, holdings, closing, **kwargs)


def kinds(chain: tuple) -> list:
    return [f["kind"] for f in ae.audit(chain, MODEL)]


class ACleanChainIsReportedClean(unittest.TestCase):
    def test_two_honest_entries_produce_nothing(self):
        self.assertEqual(kinds((anchor(), sealed())), [])

    def test_a_second_interval_that_skipped_a_month_is_honest_too(self):
        # Two months' money arrived, so the book is worth roughly 6,000: holdings of 5,994 and three dollars of cash dust.
        late = entry(1, 2, 1000.0, (("SPY", 29.97), ("QQQ", 29.97)), 5997.0, fee=3.0, days=30,
                     note="deposit 1000.00, bought 1000.00, sold 0.00, expense 1.22 on 5997.00 fund value (SPY 0.61, QQQ 0.61)")
        self.assertEqual(kinds((anchor(), late)), [])

    def test_a_levered_model_may_borrow_when_it_says_so(self):
        note = CLEAN_NOTE.replace("deposit 500.00", "deposit 500.00, borrow 1.20 at 5.91% on 200.00 borrowed")
        chain = (anchor(), sealed(holdings=(("SPY", 30.0), ("QQQ", 30.0)), closing=5795.50, note=note))
        self.assertEqual(ae.audit(chain, {**MODEL, "model": "shelter", "model_key": "shelter"}), [],
                         "the shelter ladder borrows by design; flagging that is not an audit, it is a misunderstanding")


class EachDefectFiresItsOwnCheck(unittest.TestCase):
    def test_the_round_eighty_seven_entry_is_caught_by_name(self):
        """Closing 5,497.06 against holdings of 5,497.08, a note admitting a cent, `violations` empty, on a plan that forbids it."""

        note = "deposit 500.00, bought 549.98, sold 49.98, borrow 0.00 at 5.91% on 0.01 borrowed, expense 0.61 on 5497.08 fund value (SPY 0.31, QQQ 0.30)"
        bad = entry(1, 1, 500.0, (("SPY", 27.50), ("QQQ", 27.4708)), 5497.06, fee=1.51, note=note)
        self.assertIn("leverage", kinds((anchor(), bad)))

    def test_a_loan_that_no_field_admits(self):
        bad = sealed(holdings=(("SPY", 30.0), ("QQQ", 30.0)), closing=5395.50)
        self.assertIn("undeclared-loan", kinds((anchor(), bad)))

    def test_a_free_trade(self):
        bad = sealed(fee=0.0)
        self.assertIn("free-trade", kinds((anchor(), bad)))

    def test_a_forgotten_transfer(self):
        bad = sealed(arrived=0.0, closing=4997.0, fee=0.61,
                     note=CLEAN_NOTE.replace("deposit 500.00", "deposit 0.00").replace("bought 500.00", "bought 0.00"))
        self.assertIn("cadence", kinds((anchor(), bad)))

    def test_an_unreported_idle_month(self):
        # Two months since the anchor, so 1,000 is due and the first 500 has sat uninvested for thirty days.
        bad = entry(1, 2, 1000.0, (("SPY", 29.97), ("QQQ", 29.97)), 5997.0, fee=3.0, days=0)
        self.assertIn("idle", kinds((anchor(), bad)))

    def test_a_plan_read_after_the_interval_it_governs_cannot_be_audited_because_it_cannot_be_read(self):
        """The protocol's own dataclass refuses this entry, so the finding is that the ledger is unreadable — not a clean pass,
        and not a traceback either."""

        import tempfile
        scratch = Path(tempfile.mkdtemp(prefix="audit-lookahead-"))
        book = scratch / "books" / "future"
        book.mkdir(parents=True)
        line = ('{"index": 0, "asof": "2026-09-30", "prior_hash": "' + "0" * 64 + '", "plan": "p",'
                ' "plan_posted_on": "20261030", "opening_value": 5000.0, "cash_arrived": 0.0, "invested": 0.0,'
                ' "days_to_invest": 0, "fee_paid": 0.0, "closing_value": 5000.0, "quotes": [], "holdings": [],'
                ' "violations": [], "note": "x"}\n')
        (book / "ledger.jsonl").write_text(line)
        saved_dir = paper.PAPER_DIR
        paper.PAPER_DIR = scratch
        try:
            report = ae.audit_book("future")
        finally:
            paper.PAPER_DIR = saved_dir
            shutil.rmtree(scratch, ignore_errors=True)
        self.assertEqual([f["kind"] for f in report["findings"]], ["unreadable"])
        self.assertIn("a plan cannot be posted after the interval it plans closes", report["findings"][0]["detail"])

    def test_a_holding_that_cannot_be_priced(self):
        bad = sealed(holdings=(("SPY", 25.0), ("QQQ", 25.0), ("DBC", 0.0), ("TLT", 4.0)))
        self.assertIn("priced", kinds((anchor(), bad)))

    def test_a_ledger_with_a_hole_in_it(self):
        self.assertIn("sequence", kinds((anchor(), entry(3, 1, 500.0, (("SPY", 25.0), ("QQQ", 25.0)), 5495.50))))

    def test_an_anchor_that_arrived_already_invested(self):
        self.assertIn("anchor", kinds((entry(0, 0, 0.0, (("SPY", 25.0),), 5000.0, fee=0.0, note="anchored"),)))

    def test_an_anchor_that_is_worth_more_than_was_paid_in(self):
        self.assertIn("anchor", kinds((entry(0, 0, 0.0, (), 5100.0, fee=0.0, note="anchored"),)))

    def test_a_confessed_violation_is_listed_rather_than_hidden(self):
        bad = sealed(violations=("gross exposure passed the cap",))
        findings = ae.audit((anchor(), bad), MODEL)
        self.assertEqual([f["kind"] for f in findings], ["violation"])
        self.assertIn("passed the cap", findings[0]["detail"])


class TheCommandBehaves(unittest.TestCase):
    def test_it_names_the_findings_on_the_screen_and_exits_nonzero(self):
        # A patched finding, because the live books are clean: the screen must print the kind and the detail, and exit 1.
        findings = [{"kind": "cadence", "index": 1, "asof": "2026-10-30", "detail": "500.00 arrived where the schedule owed 1,000.00"}]
        saved = ae.audit
        ae.audit = lambda chain, model: findings
        try:
            saved_argv, sys.argv = sys.argv, ["audit_entries.py", "--book", "tilt"]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ae.main()
            sys.argv = saved_argv
        finally:
            ae.audit = saved
        self.assertEqual(code, 1)
        self.assertIn("cadence", out.getvalue())
        self.assertIn("Stopping rule 4", out.getvalue())

    def test_a_clean_audit_says_so_rather_than_printing_nothing(self):
        saved_argv, sys.argv = sys.argv, ["audit_entries.py"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = ae.main()
        finally:
            sys.argv = saved_argv
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("clean", text)
        self.assertIn("root", text)
        self.assertIn("0 finding", text)

    def test_the_json_reports_the_count_it_earned_and_no_more(self):
        saved_argv, sys.argv = sys.argv, ["audit_entries.py", "--json"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                ae.main()
        finally:
            sys.argv = saved_argv
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["findings"], 0)
        self.assertEqual(len(payload["books"]), 5)

    def test_it_refuses_to_audit_a_chain_that_does_not_verify(self):
        import shutil
        import tempfile
        scratch = Path(tempfile.mkdtemp(prefix="audit-tamper-"))
        try:
            book = scratch / "books" / "tampered"
            book.mkdir(parents=True)
            source = paper.PAPER_DIR / "books" / "tilt" / "ledger.jsonl"
            tampered = source.read_text().replace('"closing_value": 5000', '"closing_value": 4999', 1)
            self.assertNotEqual(tampered, source.read_text())
            (book / "ledger.jsonl").write_text(tampered)
            shutil.copy(paper.PAPER_DIR / "books" / "tilt" / "model.json", book / "model.json")
            saved_dir, saved_argv = paper.PAPER_DIR, sys.argv
            paper.PAPER_DIR = scratch
            sys.argv = ["audit_entries.py", "--book", "tampered"]
            try:
                with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
                    ae.main()
            finally:
                paper.PAPER_DIR, sys.argv = saved_dir, saved_argv
            self.assertIn("does not verify", str(caught.exception))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class ItHasMetTheEngineItsOwnChecks(unittest.TestCase):
    """The audit is validated against real seals, not only against this file's fixtures.

    `rehearse_forward` drives the actual CLI over a manufactured corpus — trades, a band breach, a skipped month, a crash — and
    now runs this audit as one of its own checks. That check passing is the evidence that the audit does not cry wolf on the
    engine's own output; this test is the receipt.
    """

    def test_every_rehearsal_scenario_passes_the_audit_check(self):
        for scenario in ("flat", "divergent", "skipped", "crash"):
            checks = rf.run(scenario, 5000.0, 500.0)
            named = [c for c in checks if "no sealed entry contradicts itself" in c[0]]
            self.assertEqual(len(named), 1, f"{scenario} never ran the audit")
            self.assertTrue(named[0][1], f"{scenario}: {named[0][2]}")


if __name__ == "__main__":
    unittest.main()
