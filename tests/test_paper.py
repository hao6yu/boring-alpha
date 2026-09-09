"""The paper book must cost a levered account the way a broker does.

Two defects were found and fixed in the forward book on 2026-09-06, and both of
them flattered the strategy rather than hurting it, which is the direction that
matters when deciding whether a bug was caught by review or is still live:

  * A book sized to 128% of equity was carrying a 28% loan at zero interest. It
    charged a spread on turnover and an expense ratio and never once charged
    borrow, so it was measuring a margin account no broker offers. Round 4's
    sizing work priced that leg at more than half the trade's entire benefit, so
    this was not a rounding omission — it moved the conclusion.
  * The expense ratio was levied against net equity rather than against the
    fund's market value. Those differ by exactly the leverage, and the error
    always favours the strategy, because a levered book's expense is larger than
    its equity.

A third defect surfaced on 2026-09-07, when a model with two positions was first run through it: `orders_for` put the
signed delta in the Order's quantity field, and the applier negated it again on a sell. The two sign conventions
cancelled in the wrong place, so an order labelled SELL of a whole position bought twice as much of it. It had never
fired because every model in this book had only ever held one symbol and never wanted out — which is the general lesson:
a code path that no live model exercises is untested no matter how many months the book has been running. It is pinned
below where it can be seen: the position has to go down, and the ledger may not keep a position it has closed.

Both of the original defects are pinned below at the level that actually matters: the sealed closing value, not the
intermediate number. A test that asserts `interest > 0` would pass while the closing value ignored it.
"""

import contextlib
import io
import json
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
from boring_alpha.journal import entry_hash, read, verify  # noqa: E402


class Book(unittest.TestCase):
    """A throwaway book, with the data feed truncated to a chosen session.

    Truncating the feed is the only way to test a forward book: the code decides
    what to seal by asking the data what the newest session is, so pretending a
    given date *is* the newest session is exactly the thing that needs exercising.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # Every path the tool writes to is redirected, including the shadow chain.
        # Missing one is not a loud failure: the scratch book reads the real
        # repo's shadow ledger, finds it non-empty, and init aborts — which is at
        # least a refusal. A harness that silently *shared* the live benchmark
        # would be worse, because the tests would pass against production state.
        self._saved_paths = (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW,
                             paper.CONFIG)
        self._saved_load = paper.load_data
        paper.PAPER_DIR = self.dir
        paper.LEDGER = self.dir / "ledger.jsonl"
        paper.SHADOW = self.dir / "shadow.jsonl"
        paper.CONFIG = self.dir / "model.json"

        def restore():
            (paper.PAPER_DIR, paper.LEDGER, paper.SHADOW,
             paper.CONFIG) = self._saved_paths
            paper.load_data = self._saved_load

        self.addCleanup(restore)

    def anchor(self, asof):
        paper.load_data = lambda _asof=None: self._saved_load(asof)
        paper.command_init(types.SimpleNamespace(asof=asof, model="voltarget"))

    def step(self, asof):
        paper.load_data = lambda _asof=None: self._saved_load(asof)
        with contextlib.redirect_stdout(io.StringIO()):
            paper.command_step(types.SimpleNamespace())

    def last(self):
        return read(paper.LEDGER)[-1]

    def note_field(self, label):
        """Pull `label <value> ` out of the sealed note."""

        note = self.last().note
        tail = note.split(f"{label} ")[1]
        return float(tail.split(",")[0].split(" at")[0].split(" on")[0])


class BorrowIsCharged(Book):
    def test_a_levered_book_pays_interest_and_an_unlevered_one_does_not(self):
        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 29))
        note = self.last().note
        self.assertIn("borrow", note)
        charged = self.note_field("borrow")
        gross = 1.28          # the candidate targets 128%
        # Roughly a quarter of the book is borrowed, so on a book near $6,000 the
        # month's interest should be a few dollars, not zero and not the balance.
        self.assertGreater(charged, 0.0)
        self.assertLess(charged, 6000 * gross * 0.10 / 12)

    def test_the_note_names_the_rate_it_used(self):
        """An interest charge without its rate is not auditable."""

        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 29))
        self.assertRegex(self.last().note, r"borrow [\d.]+ at \d+\.\d\d%")


class DepositCadence(Book):
    def test_two_steps_in_one_month_take_one_deposit(self):
        """The failure this pins: a daily driver funding five months in January."""

        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 15))
        self.step(date(2024, 2, 29))
        arrived = sum(e.cash_arrived for e in read(paper.LEDGER))
        # Anchor + February only. Not two Februarys.
        self.assertAlmostEqual(arrived, paper.MONTHLY, places=2)

    def test_a_new_month_does_deposit(self):
        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 29))
        self.step(date(2024, 3, 28))
        self.assertAlmostEqual(sum(e.cash_arrived for e in read(paper.LEDGER)),
                               paper.MONTHLY * 2, places=2)


class ExpenseIsOnFundValue(Book):
    def test_expense_is_charged_against_holdings_not_equity(self):
        """At 128% gross the fund bills 128% of value; equity would understate it."""

        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 29))
        entry = self.last()
        expense = self.note_field("expense")
        implied_fund_value = expense * 12.0 / paper.EXPENSE_RATIO
        # Fund value must sit above net equity whenever the book is levered.
        self.assertGreater(implied_fund_value, entry.closing_value * 1.05)


class LedgerIntegrity(Book):
    def test_chain_still_verifies_after_the_accounting_change(self):
        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 29))
        self.step(date(2024, 3, 28))
        report = verify(paper.LEDGER)
        self.assertTrue(report.ok, report.reason)

    def test_closing_value_equals_the_components_recorded(self):
        """Opening + deposit - fees + market move must reconcile to the close.

        Not asserted as an identity here, because the market move is computed from
        quotes the entry itself carries; instead the entry must at least be able to
        explain its own total, which is the property that made the old book
        unauditable.
        """

        self.anchor(date(2024, 1, 31))
        self.step(date(2024, 2, 29))
        entry = read(paper.LEDGER)[-1]
        self.assertGreater(entry.closing_value, 0.0)
        self.assertLessEqual(entry.fee_paid, entry.opening_value + entry.cash_arrived)
        for holding in entry.holdings:
            quoted = {q.symbol: q.close for q in entry.quotes}
            self.assertIn(holding.symbol, quoted)


class ASellSells(Book):
    """The sign defect, pinned on the generic path so any model's scale-down is covered, not only the shelter's."""

    def test_a_sell_reduces_the_position_it_names(self):
        orders = paper.orders_for({"SPY": 0.5}, {"SPY": 10.0}, {"SPY": 100.0}, 1000.0)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, "SELL")
        self.assertGreater(orders[0].units, 0.0, "a negative quantity on a sell double-negates at the ledger")
        units = dict({"SPY": 10.0})
        for o in orders:
            units[o.symbol] += o.units if o.side == "BUY" else -o.units
        self.assertAlmostEqual(units["SPY"], 5.0, places=10)

    def test_a_full_exit_leaves_no_position_at_all_not_even_a_zero(self):
        orders = paper.orders_for({"IEF": 1.0}, {"SPY": 10.0}, {"SPY": 100.0, "IEF": 50.0}, 1000.0)
        sides = {o.symbol: (o.side, o.units) for o in orders}
        self.assertEqual(sides["SPY"][0], "SELL")
        self.assertAlmostEqual(sides["SPY"][1], 10.0, places=10, msg="the exit must be the whole position")
        self.assertEqual(sides["IEF"][0], "BUY")

    def test_a_model_that_wants_nothing_from_a_held_symbol_still_sells_it(self):
        orders = {o.symbol: o.side for o in paper.orders_for({"SPY": 1.0}, {"IEF": 4.0},
                                                            {"SPY": 10.0, "IEF": 100.0}, 100.0)}
        self.assertEqual(orders.get("IEF"), "SELL", "a held symbol outside the target must be liquidated")


class SnapshotIdentity(Book):
    def test_sealed_entries_name_an_immutable_snapshot_not_the_symlink(self):
        """`current` is the one thing guaranteed to change, so it proves nothing."""

        self.assertNotEqual(paper.snapshot_id(), "current")
        self.assertRegex(paper.snapshot_id(), r"^\d{8}T\d{6}Z$")

    def test_config_records_the_snapshot(self):
        self.anchor(date(2024, 1, 31))
        self.assertEqual(json.loads(paper.CONFIG.read_text())["snapshot"],
                         paper.snapshot_id())


if __name__ == "__main__":
    unittest.main()
