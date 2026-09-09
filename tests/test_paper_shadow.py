"""The benchmark must be witnessed, not inferred by the party being graded.

`comparator_return` recomputes doing-nothing from the strategy's own quotes. It is
reproducible, so it is not weak — but it is computed by the code under evaluation,
from that code's own data, and the P0 dominance rule is the one claim here that
must not rest on the graded party's arithmetic. The shadow chain seals the
comparator as its own account, priced from the same quotes and the same deposits,
bound to the strategy entry it closes against.

The tests below are mostly about symmetry, which is the property that makes the
comparison mean anything: two accounts with different costs are not a comparison,
and a benchmark priced more expensively than the strategy it judges retires a
strategy for the same reason one priced more cheaply advances it.
"""

import contextlib
import io
import json
import re
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper  # noqa: E402
from boring_alpha.journal import Comparator, entry_hash, read, verify  # noqa: E402

MONTH_ENDS = (date(2024, 2, 29), date(2024, 3, 28), date(2024, 4, 30),
              date(2024, 5, 31), date(2024, 6, 28))


class TwoChains(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        saved = (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW, paper.CONFIG,
                 paper.load_data)
        paper.PAPER_DIR = self.dir
        paper.LEDGER = self.dir / "ledger.jsonl"
        paper.SHADOW = self.dir / "shadow.jsonl"
        paper.CONFIG = self.dir / "model.json"
        self.original_load = paper.load_data

        def restore():
            (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW, paper.CONFIG,
             paper.load_data) = saved

        self.addCleanup(restore)
        paper.command_init(types.SimpleNamespace(
            asof=date(2024, 1, 31), model="voltarget"))

    def advance(self, through):
        for stamp in MONTH_ENDS[:through]:
            paper.load_data = (lambda _a=None, _s=stamp: self.original_load(_s))
            with contextlib.redirect_stdout(io.StringIO()):
                paper.command_step(types.SimpleNamespace())
        paper.load_data = self.original_load

    def test_init_anchors_both_chains(self):
        self.assertTrue(paper.LEDGER.exists())
        self.assertTrue(paper.SHADOW.exists())
        self.assertEqual(read(paper.SHADOW)[0].closing_value, paper.OPENING)

    def test_both_chains_advance_the_same_number_of_intervals(self):
        self.advance(4)
        self.assertEqual(len(read(paper.LEDGER)), len(read(paper.SHADOW)))

    def test_every_interval_is_priced_from_identical_quotes(self):
        """Same quotes on both chains, or the comparison is between two markets."""

        self.advance(4)
        for strategy, shadow in zip(read(paper.LEDGER), read(paper.SHADOW)):
            own = {q.symbol: q.close for q in strategy.quotes}
            theirs = {q.symbol: q.close for q in shadow.quotes}
            self.assertEqual(own, theirs, f"entry {strategy.index}")
            self.assertEqual(strategy.asof, shadow.asof)

    def test_both_accounts_receive_identical_cash(self):
        """One deposit, two books. A richer benchmark is not a benchmark."""

        self.advance(4)
        for strategy, shadow in zip(read(paper.LEDGER), read(paper.SHADOW)):
            self.assertAlmostEqual(strategy.cash_arrived, shadow.cash_arrived,
                                   places=6)

    def test_the_comparator_never_borrows(self):
        """An unlevered account must never end an interval owing anybody.

        The first version charged the expense ratio against a cash line already at
        zero, which put a never-borrowing benchmark into a never-borrowing
        overdraft. The `max(0.0, cash)` that hid it was worse than the bug, because
        a clamp that forgives a fee biases the number used to judge everything.
        """

        self.advance(4)
        for entry in read(paper.SHADOW)[1:]:
            prices = {q.symbol: q.close for q in entry.quotes}
            held = sum(h.units * prices[h.symbol] for h in entry.holdings)
            implied = entry.closing_value - held
            # Tolerance is the ledger's own 2dp rounding of closing_value, not a
            # fudge: at $7,000 the rounding can move a cent, and nothing more.
            self.assertGreater(implied, -0.02, f"entry {entry.index} went into overdraft")

    def test_the_comparator_pays_no_borrow_interest(self):
        self.advance(4)
        # Stepped entries only: the anchor holds no positions and pays nothing,
        # so it carries no fee breakdown to assert on.
        for entry in read(paper.SHADOW)[1:]:
            self.assertNotIn("borrow", entry.note)
            self.assertIn("expense_fee=", entry.note)

    def test_the_shadow_entry_names_the_strategy_entry_it_closed_against(self):
        """Without the back-reference the two chains can be swapped independently."""

        self.advance(2)
        strategy = read(paper.LEDGER)[1]
        shadow = read(paper.SHADOW)[1]
        self.assertIn(entry_hash(strategy)[:16], shadow.note)

    def test_the_shadow_chain_verifies(self):
        self.advance(4)
        report = verify(paper.SHADOW)
        self.assertTrue(report.ok, report.reason)

    def test_the_expense_ratio_actually_bites_the_benchmark(self):
        """The clamp-hiding test.

        A fee that is computed, reported in the note, and then swallowed by
        `max(0.0, cash)` leaves the closing value untouched, so no single-run
        assertion on closing_value can see it. Running the identical book twice,
        once with the fund's real expense ratio and once without, is the only
        check that proves the fee moved the account.
        """

        self.advance(4)
        with_fee = read(paper.SHADOW)[-1].closing_value

        # Second book, identical everything, fee-free benchmark.
        other = Path(tempfile.mkdtemp())
        saved = (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW, paper.CONFIG)
        paper.PAPER_DIR = other
        paper.LEDGER = other / "ledger.jsonl"
        paper.SHADOW = other / "shadow.jsonl"
        paper.CONFIG = other / "model.json"
        config = json.loads((saved[3]).read_text())
        config["comparator"]["expense_ratio"] = 0.0
        paper.command_init(types.SimpleNamespace(
            asof=date(2024, 1, 31), model="voltarget"))
        (other / "model.json").write_text(json.dumps(config))
        for stamp in MONTH_ENDS[:4]:
            paper.load_data = (lambda _a=None, _s=stamp: self.original_load(_s))
            with contextlib.redirect_stdout(io.StringIO()):
                paper.command_step(types.SimpleNamespace())
        (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW,
         paper.CONFIG) = saved
        without_fee = read(other / "shadow.jsonl")[-1].closing_value

        self.assertLess(with_fee, without_fee,
                        "the expense ratio was charged, reported, and then forgiven")
        # Nine and a half bps a year on ~$7k over four months is a few dollars.
        gap = without_fee - with_fee
        self.assertGreater(gap, 1.0)
        self.assertLess(gap, 60.0)

    def test_the_benchmark_pays_the_same_expense_ratio_as_the_strategy(self):
        """Fee symmetry, asserted rather than assumed.

        A benchmark priced below the strategy it judges is a rig in the strategy's
        favour, and the direction of that rig retires nothing — it advances things
        that should not be advanced.
        """

        self.advance(4)
        entry = read(paper.SHADOW)[-1]
        prices = {q.symbol: q.close for q in entry.quotes}
        held = sum(h.units * prices[h.symbol] for h in entry.holdings)
        expense = float(re.search(r"expense_fee=([\d.]+)", entry.note).group(1))
        implied = expense * 12.0 / held
        self.assertAlmostEqual(implied, paper.EXPENSE_RATIO, places=6)

    def test_the_witness_never_pays_more_than_the_book_it_judges(self):
        """Direction check, narrowed to the half that is always true.

        This test used to assert that the trading book sat *behind* the witness, and its own docstring allowed the exception
        — "unless it was paid to trade by the market". Round 82 found that both chains had been unable to compound, so the
        assertion held for a structural reason and not an economic one: it was measuring the defect. Once the mark-to-market
        error is gone the market pays or does not pay, and no four-month slice of an archive can be pinned in advance. The
        cost half of the claim is what cannot legitimately reverse, so that is what is asserted: a benchmark charged more
        than the strategy it judges retires a strategy for free, and one charged less buys it a win for nothing. That the
        books may now separate in either direction is tested where it belongs, in `test_paper_compounding.py`.
        """

        self.advance(4)
        strategy, shadow = read(paper.LEDGER)[-1], read(paper.SHADOW)[-1]
        self.assertGreater(sum(e.fee_paid for e in read(paper.LEDGER)),
                           sum(e.fee_paid for e in read(paper.SHADOW)))
        self.assertGreater(strategy.fee_paid, 0.0)
        self.assertNotEqual(strategy.closing_value, shadow.closing_value)


class Tamper(unittest.TestCase):
    def test_editing_the_shadow_ledger_breaks_its_chain(self):
        """A witnessed benchmark is only evidence if it can be falsified."""

        import json as _json

        self.dir = Path(tempfile.mkdtemp())
        saved = (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW, paper.CONFIG,
                 paper.load_data)
        paper.PAPER_DIR = self.dir
        paper.LEDGER = self.dir / "ledger.jsonl"
        paper.SHADOW = self.dir / "shadow.jsonl"
        paper.CONFIG = self.dir / "model.json"
        original_load = paper.load_data

        def restore():
            (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW, paper.CONFIG,
             paper.load_data) = saved

        self.addCleanup(restore)
        paper.command_init(types.SimpleNamespace(
            asof=date(2024, 1, 31), model="voltarget"))
        paper.load_data = lambda _a=None: original_load(MONTH_ENDS[0])
        with contextlib.redirect_stdout(io.StringIO()):
            paper.command_step(types.SimpleNamespace())
        paper.load_data = original_load

        lines = paper.SHADOW.read_text().splitlines()
        row = _json.loads(lines[1])
        row["closing_value"] = row["closing_value"] + 500.0
        lines[1] = _json.dumps(row, sort_keys=True)
        paper.SHADOW.write_text("\n".join(lines) + "\n")

        report = verify(paper.SHADOW)
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
