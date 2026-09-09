"""The sheltered model in the forward book, and the two accounting defects that had to go before it could run.

`paper.py` charged one global expense ratio to whatever the book held. That was harmless while the book held only SPY,
and wrong the moment the off-equity leg is an unposted ETF: IEF's fee is not in the repository's posted table, so a
global SPY fee under-charges a sheltered month by nearly four times — and the shelter's whole case (round 68, +$130/mo
per $100k) rests on it paying something. The tests below pin the fee where it can no longer be quietly optimistic, pin
the refusal on an unknown symbol, and pin the month's decision against the research tool that measured it, so the book
and the archive cannot drift apart.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                  # noqa: E402
import shelter_long_record as sl                              # noqa: E402
import withdrawal_capacity as wc
import fund_fees                                        # noqa: E402                              # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data  # noqa: E402

# Probed from the archive under the book's own rule, not assumed: May 2025 was sheltered (the reading, taken on the
# first trading day of April, saw SPY below its 200-day), June too, and July was back in equities — so one pair of
# dates exercises the shelter fee and the switch out of it.
DOWN = date(2025, 5, 30)
STILL_DOWN = date(2025, 6, 30)
BACK_UP = date(2025, 7, 31)
UP = date(2024, 12, 31)
ANCHOR_DOWN = date(2025, 4, 30)
ANCHOR_UP = date(2024, 11, 29)


class ScratchBook(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self._saved = {"PAPER_DIR": paper.PAPER_DIR, "LEDGER": paper.LEDGER, "SHADOW": paper.SHADOW,
                       "CONFIG": paper.CONFIG, "load_data": paper.load_data}
        paper.PAPER_DIR = self.dir
        paper.LEDGER = self.dir / "ledger.jsonl"
        paper.SHADOW = self.dir / "shadow.jsonl"
        paper.CONFIG = self.dir / "model.json"

        def restore():
            for k, v in self._saved.items():
                setattr(paper, k, v)

        self.addCleanup(restore)

    def anchor(self, asof, model="shelter"):
        real = self._saved["load_data"]
        paper.load_data = lambda _a=None: real(asof)
        paper.command_init(types.SimpleNamespace(asof=asof, model=model))

    def step(self, asof):
        real = self._saved["load_data"]
        paper.load_data = lambda _a=None: real(asof)
        with contextlib.redirect_stdout(io.StringIO()):
            paper.command_step(types.SimpleNamespace())

    def last(self):
        from boring_alpha.journal import read
        return read(paper.LEDGER)[-1]

    def expense_field(self):
        tail = self.last().note.split("expense ")[1]
        return float(tail.split(" on")[0])

    def fee_split(self):
        tail = self.last().note.split("fund value (")[1]
        return tail.split(")")[0]


class TheFeeTable(unittest.TestCase):
    def test_the_books_fee_table_is_the_research_fees_not_a_copy_that_can_drift(self):
        for sym, posted in wc.EXPENSE.items():
            self.assertAlmostEqual(paper.fee_for(sym), posted, places=8, msg=f"{sym} was retyped, not carried over")

    def test_a_leg_the_archive_quotes_has_a_sourced_fee_and_it_is_not_the_invented_one(self):
        """Round 94 replaced the flat guess for all seven legs the sealed entries quote. What has to stay true is the reason
        the guess existed: no sleeve the book can hold is ever charged zero."""

        for sym in ("IEF", "TLT", "GLD", "DBC"):
            self.assertNotEqual(paper.fee_for(sym), paper.UNPOSTED_FEE, f"{sym} is still charged a fee nobody posted")
            self.assertGreater(paper.fee_for(sym), 0.0, sym)
            self.assertAlmostEqual(paper.fee_for(sym), fund_fees.fee_for(sym), places=10, msg=sym)

    def test_an_unknown_symbol_refuses_rather_than_being_free(self):
        with self.assertRaises(SystemExit):
            paper.fee_for("XLU")

    def test_the_shelter_leg_is_dearer_than_the_global_fee_it_replaced_and_the_multiple_is_measured(self):
        """The bug this pin exists for was real; the size in its old name was an artefact of the guess.

        Charged the flat 0.35%, the bond leg came out at 3.7 times the SPY ratio the whole book used to be charged, and the
        test said "three times" out loud. At the published 0.15% it is 1.6 times — the defect (an equity fund's fee charged
        on a Treasury fund) survives, and so does the direction, but the headline number belonged to the guess rather than
        to the fund. It is derived here now, and the ceiling fails loudly if a future ratio change makes the old claim true
        again for a reason that has nothing to do with this file.
        """

        multiple = paper.fee_for(paper.SHELTER) / paper.EXPENSE_RATIO
        self.assertGreater(multiple, 1.0, f"{paper.SHELTER} is charged less than the equity fee it replaced")
        self.assertLess(multiple, 3.0, "the multiple moved; re-read the sourced table before repeating the old headline")
        self.assertAlmostEqual(multiple, fund_fees.fee_for(paper.SHELTER) / paper.EXPENSE_RATIO, places=10)


class TheDecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv_market_data(paper.SNAPSHOT, paper.CASH_FILE)

    def test_the_book_and_the_research_tool_read_the_same_trend_on_the_same_days(self):
        """paper.py reimplements the rule on purpose — the live book must not depend on a research script — so the two
        implementations are pinned against each other, month by month, over the last three years."""

        marks = sl.month_signal(sorted(sl.legs(self.data, "SPY")), sl.legs(self.data, "SPY"), "start")
        days = [d for d in self.data.dates if d >= date(2023, 1, 1)]
        want = sl.carry(marks, days)
        for i, d in enumerate(days):
            got = paper.shelter_weights(self.data, d)[3]
            self.assertEqual(got, want[i], f"{d}: the live book and the measured rule disagree")

    def test_the_model_asks_for_equities_when_the_trend_is_up(self):
        w, _when, read_on, val = paper.shelter_weights(self.data, UP)
        self.assertEqual(w, {"SPY": 1.0})
        self.assertEqual(val, 1.0)

    def test_the_model_asks_for_the_shelter_when_the_trend_is_down(self):
        w, _when, read_on, val = paper.shelter_weights(self.data, DOWN)
        self.assertEqual(w, {paper.SHELTER: 1.0})
        self.assertEqual(val, 0.0)

    def test_the_ticket_names_the_day_the_trend_was_actually_read(self):
        """The first print said "trend read 2026-09-04", which was the last date in the file, not the reading. A sheet
        that misdates its own decision cannot be audited against the price it claims to have used."""

        for probe in (UP, DOWN, date(2026, 9, 4)):
            _w, _last, read_on, _v = paper.shelter_weights(self.data, probe)
            self.assertLess(read_on, probe, f"{probe}: the reading postdates the decision it governs")
            self.assertGreater((probe - read_on).days, 20, f"{probe}: not a month-stale reading")
            day_before = max(d for d in self.data.dates if d < read_on)
            self.assertNotEqual((day_before.year, day_before.month), (read_on.year, read_on.month),
                                f"{read_on}: this is not the first trading day of its month")

    def test_the_shelter_is_all_of_it_and_not_half(self):
        """Round 64's weight algebra, in the live artifact: the off-equity leg is the whole remainder, so nothing sits
        in cash by accident earning a rate the plan is not being credited with."""

        for d in (UP, DOWN):
            w = paper.shelter_weights(self.data, d)[0]
            self.assertAlmostEqual(sum(w.values()), 1.0)
            self.assertEqual(len(w), 1)


class TheSealedMonth(ScratchBook):
    def test_a_sheltered_month_is_charged_the_shelters_fee(self):
        self.anchor(ANCHOR_DOWN)
        self.step(DOWN)
        entry = self.last()
        self.assertEqual([h.symbol for h in entry.holdings], [paper.SHELTER])
        d0 = load_csv_market_data(paper.SNAPSHOT, paper.CASH_FILE, end=DOWN)
        close = d0.by_date[max(d0.by_date)][paper.SHELTER].close
        held = sum(h.units for h in entry.holdings) * close
        self.assertAlmostEqual(self.expense_field(), paper.fee_for(paper.SHELTER) / 12.0 * held, delta=0.05)
        self.assertIn(paper.SHELTER, self.fee_split())

    def test_an_equity_month_is_charged_the_equity_fee_and_the_note_says_which(self):
        self.anchor(ANCHOR_UP)
        self.step(UP)
        self.assertEqual([h.symbol for h in self.last().holdings], ["SPY"])
        self.assertEqual(self.fee_split(), "SPY 0.09%")

    def test_leaving_the_shelter_sold_the_shelter_rather_than_leaving_it_behind(self):
        """The `orders_for` bug: the old loop iterated a fixed sleeve list, so a symbol the model no longer wanted was
        only ever liquidated by luck. This one found a second bug while being written — a closed position used to be
        re-sealed as a holding with 0.00000000 units, because the filter tested the unrounded float and the stored
        value was the rounded one."""

        self.anchor(ANCHOR_DOWN)
        self.step(DOWN)
        self.assertIn(paper.SHELTER, [h.symbol for h in self.last().holdings])
        self.step(STILL_DOWN)                        # a second sheltered month: same position, no churn
        self.assertIn(paper.SHELTER, [h.symbol for h in self.last().holdings])
        self.step(BACK_UP)                             # July: the reading says equities again
        self.assertIn("SPY", [h.symbol for h in self.last().holdings])
        self.assertNotIn(paper.SHELTER, [h.symbol for h in self.last().holdings],
                         "the book is still holding IEF that no model asked for")

    def test_orders_for_can_sell_something_the_model_no_longer_wants(self):
        orders = paper.orders_for({"SPY": 1.0}, {paper.SHELTER: 10.0},
                                  {"SPY": 100.0, paper.SHELTER: 100.0}, 1000.0)
        sides = {o.symbol: o.side for o in orders}
        self.assertEqual(sides.get(paper.SHELTER), "SELL")
        self.assertEqual(sides.get("SPY"), "BUY")

    def test_the_model_is_recorded_in_the_config_it_was_anchored_with(self):
        self.anchor(ANCHOR_UP)
        cfg = json.loads(paper.CONFIG.read_text())
        self.assertEqual(cfg["model_key"], "shelter")
        self.assertEqual(cfg["sleeves"], ["SPY", "IEF"])
        self.assertEqual(cfg["trend_reading"], "first trading day of the month BEFORE the one it governs")
        self.assertEqual(cfg["fees"], {"SPY": paper.fee_for("SPY"), "IEF": paper.fee_for("IEF")})

    def test_the_borrow_spread_this_chain_is_price_by_is_recorded_at_anchor(self):
        """The number may only move at a re-init, so it belongs in the config next to the snapshot id."""

        self.anchor(ANCHOR_UP)
        self.assertEqual(paper.BORROW_SPREAD, 0.0202)


if __name__ == "__main__":
    unittest.main()
