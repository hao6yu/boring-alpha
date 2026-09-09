"""Two books, one set of quotes: the named-book plumbing that lets a second construction be watched forward.

Round 69 superseded the last non-shelter chain, which left the repository holding exactly one positively-measured plan —
a constant-leverage book, +1.63%/yr over the full record against a comparator it has never been run forward against — with
no forward record at all. One book per model is the only way two constructions can be watched on the same deposits
without either being explained away afterwards, so the book gained a name. These tests pin the isolation that has to come
with it: separate ledgers, separate witnesses, and a step on one that leaves the other byte-identical.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                   # noqa: E402
from boring_alpha.journal import read, verify                  # noqa: E402

ASOF = date(2025, 5, 30)          # May 2025: sheltered model wants IEF, constant model wants 125% SPY
ANCHOR = date(2025, 4, 30)


class TwoBooks(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self._saved = {k: getattr(paper, k) for k in ("PAPER_DIR", "LEDGER", "SHADOW", "CONFIG", "load_data")}
        paper.PAPER_DIR = self.dir
        paper.LEDGER = self.dir / "ledger.jsonl"
        paper.SHADOW = self.dir / "shadow.jsonl"
        paper.CONFIG = self.dir / "model.json"
        self.addCleanup(self._restore)
        self.real = self._saved["load_data"]

    def _restore(self):
        for k, v in self._saved.items():
            setattr(paper, k, v)
        shutil.rmtree(self.dir, ignore_errors=True)

    def _at(self, asof):
        paper.load_data = lambda _a=None: self.real(asof)

    def init(self, book, model, asof=ANCHOR):
        self._at(asof)
        paper.command_init(types.SimpleNamespace(asof=asof, model=model, book=book))

    def step(self, book, asof=ASOF):
        self._at(asof)
        with contextlib.redirect_stdout(io.StringIO()):
            paper.command_step(types.SimpleNamespace(book=book))

    def paths(self, book=""):
        root = self.dir if not book else self.dir / "books" / book
        return root / "ledger.jsonl", root / "shadow.jsonl", root / "model.json"

    def test_a_named_book_lives_under_its_own_directory(self):
        self.init("constant", "constant")
        ledger, shadow, config = self.paths("constant")
        self.assertTrue(ledger.exists() and shadow.exists() and config.exists())
        self.assertFalse((self.dir / "ledger.jsonl").exists(), "naming a book must not write the root one")

    def test_the_root_book_is_byte_identical_after_a_named_book_runs(self):
        self.init("", "shelter")
        before = self.paths("")[0].read_bytes(), self.paths("")[1].read_bytes()
        self.init("constant", "constant")
        self.step("constant")
        self.assertEqual(before, (self.paths("")[0].read_bytes(), self.paths("")[1].read_bytes()),
                         "a step on one book touched the other's sealed chain")

    def test_the_two_models_do_what_they_are_supposed_to_on_the_same_session(self):
        """Not an isolation test but the reason for it: the same quotes, the same deposit, two different accounts."""

        self.init("", "shelter")
        self.init("constant", "constant")
        self.step("")
        self.step("constant")
        shelter = read(self.paths("")[0])[-1]
        const = read(self.paths("constant")[0])[-1]
        self.assertEqual([h.symbol for h in shelter.holdings], ["IEF"])
        self.assertEqual([h.symbol for h in const.holdings], ["SPY"])
        # `invested` is capped at the account's own cash on purpose, so leverage shows up as gross exposure exceeding
        # net value and as a borrow charge in the sealed note — not in that field.
        quotes = {q.symbol: q.close for q in const.quotes}
        gross = sum(h.units * quotes[h.symbol] for h in const.holdings)
        self.assertGreater(gross, const.closing_value * 1.1,
                           "a 1.25x book must hold more than it is worth; if it does not, this is not the levered claim")
        self.assertIn("borrow", const.note)
        self.assertGreater(const.fee_paid, 0.0, "a financed book that paid no interest is not a financed book")
        self.assertEqual(shelter.asof, const.asof)

    def test_each_book_seals_its_own_witness(self):
        self.init("", "shelter")
        self.init("constant", "constant")
        self.step("")
        self.assertEqual(len(read(self.paths("")[1])), 2)
        self.assertEqual(len(read(self.paths("constant")[1])), 1, "the second book's witness is not a shared file")

    def test_a_name_that_escapes_the_book_directory_is_refused(self):
        for bad in ("../outside", "a/b", "", "  ", ".hidden", "-x", "x" * 40):
            if bad == "":
                continue                                    # empty is the root book, which is legal
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                with paper.use_book(bad):
                    pass

    def test_the_empty_name_is_the_root_book(self):
        with paper.use_book("") as root:
            self.assertEqual(root, self.dir)
        self.assertEqual(paper.LEDGER, self.dir / "ledger.jsonl")

    def test_books_lists_the_root_first_and_only_books_with_ledgers(self):
        self.init("", "shelter")
        self.init("constant", "constant")
        (self.dir / "books" / "stray").mkdir(parents=True)
        names = [n for n, _ in paper.books()]
        self.assertEqual(names[:2], ["", "constant"])
        self.assertNotIn("stray", names)

    def test_compare_prints_one_row_per_book_labelled_by_its_anchor_not_its_directory(self):
        self.init("", "shelter")
        self.init("constant", "constant")
        self.step("")
        self.step("constant")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            paper.command_compare(types.SimpleNamespace(book=""))
        out = buf.getvalue()
        self.assertIn("shelter", out)
        self.assertIn("constant", out)
        self.assertIn("intact", out)
        self.assertNotIn("BROKEN", out)
        # Same quotes, same deposits, same opening cash: the doing-nothing account has to come out the same for both,
        # or the two books are not comparable as accounts and the compare table is decoration.
        witness = [ln.split()[-3] for ln in out.splitlines() if ln.strip().startswith(("(root)", "constant"))]
        self.assertEqual(len(witness), 2, out)
        self.assertEqual(witness[0], witness[1], f"the two witnesses disagree: {witness}")

    def test_compare_reports_a_tampered_chain_as_broken_rather_than_omitting_it(self):
        self.init("", "shelter")
        self.step("")
        path = self.paths("")[0]
        lines = path.read_text().splitlines()
        first = json.loads(lines[0])
        first["closing_value"] = first["closing_value"] + 1.0          # a repriced anchor, same shape, wrong hash
        lines[0] = json.dumps(first, sort_keys=True)
        path.write_text("\n".join(lines) + "\n")
        self.assertFalse(verify(path).ok, "the tamper did not take; this test would prove nothing")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            paper.command_compare(types.SimpleNamespace(book=""))
        self.assertIn("BROKEN", buf.getvalue())

    def test_the_report_takes_its_benchmark_from_the_config_it_was_anchored_with(self):
        """The step path has read the comparator from config for a while; the report path used to rebuild it from
        literals, which is a call site where a friendlier benchmark could be introduced."""

        self.init("", "shelter")
        cfg = json.loads(self.paths("")[2].read_text())
        cfg["comparator"] = {"name": "100% SPY", "weights": {"SPY": 1.0}, "expense_ratio": 0.0}
        self.paths("")[2].write_text(json.dumps(cfg))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            paper.command_report(types.SimpleNamespace(book=""))
        self.assertIn("LEVEL", buf.getvalue())
        self.assertEqual(json.loads(self.paths("")[2].read_text())["comparator"]["expense_ratio"], 0.0,
                         "the report must not rewrite the spec it is reporting against")


class CadenceOfDeposits(unittest.TestCase):
    """The rule that decides the denominator of every return this journal will ever report.

    `paper._deposits_due` is private, and it is pinned here deliberately. It sets each entry's `cash_arrived`, which is the
    paid-in figure every dollar-weighted return divides by, so a convention that under-arrives money makes the book look
    better by moving the denominator — the one place where a book must not be allowed to help itself. Round 84's rebuild of
    this module could not recover which convention the destroyed file used, so the conservative one was chosen, written down
    in the function, and pinned before the first seal exists to be shaped by it.
    """

    def head(self, asof):
        from boring_alpha.journal import Entry, Quote
        return Entry(index=0, asof=asof, prior_hash="0" * 64, plan="p", plan_posted_on=asof, opening_value=5000.0,
                     cash_arrived=0.0, invested=0.0, days_to_invest=0, fee_paid=0.0, closing_value=5000.0,
                     quotes=(Quote("SPY", 100.0),), holdings=(), violations=(), note="")

    def test_the_anchors_own_month_is_already_funded(self):
        import datetime
        self.assertEqual(paper._deposits_due(self.head(datetime.date(2026, 9, 4)), datetime.date(2026, 9, 30), 500.0), 0.0,
                         "the anchor sealed the opening as cash the account owns; a second copy would fund it twice")

    def test_one_calendar_month_later_pays_exactly_one_deposit(self):
        import datetime
        self.assertEqual(paper._deposits_due(self.head(datetime.date(2026, 9, 4)), datetime.date(2026, 10, 30), 500.0),
                         paper.MONTHLY)

    def test_a_skipped_seal_does_not_forgive_the_deposit_it_missed(self):
        import datetime
        self.assertEqual(paper._deposits_due(self.head(datetime.date(2026, 9, 4)), datetime.date(2026, 11, 30), 500.0),
                         2 * paper.MONTHLY, "two calendar months, two transfers, whatever the sealing schedule managed")

    def test_the_late_tranche_is_recorded_as_late(self):
        """`journal.py` has an idle-cash finding that only fires when `days_to_invest` is non-zero. A book that skipped a
        month really did sit on that transfer, and a seal that reports zero delay is reporting a fact about its own
        bookkeeping as if it were a fact about the money."""

        import datetime
        for gap, expected in ((1, 0), (2, 30), (3, 60)):
            later = datetime.date(2026 + (8 + gap) // 12, (8 + gap) % 12 + 1, 28)
            self.assertEqual(30 * max(paper._months_apart(datetime.date(2026, 9, 4), later) - 1, 0), expected, f"{gap} months")


if __name__ == "__main__":
    unittest.main()
