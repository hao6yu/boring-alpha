"""Tests for the round that found neither sealed chain could compound.

`shadow_step` and `command_step` both recovered their cash line by taking the previous entry's total and subtracting the
holdings priced at *today's* prices. Those two prices are different numbers. The difference — the month's mark-to-market —
landed in the cash line, which the month's orders then invested or swept, so the interval closed worth what had been
deposited into it. A benchmark with that defect reports the deposits whatever the market does, which means every rising
market hands the strategy a win it did not earn and every falling market hands it a loss it did not suffer. The dominance
rule is this repository's central claim, and it was being computed against a witness that cannot move.

Found while differential-testing a new study's simulator against the sealed witness (`tests/test_power_horizon.py`), which
is the whole argument for round 69's rule stated as it stands: the reimplementation was the act of writing down what the
original does, and the original was wrong.

Nothing in this file asserts a market outcome. Every test asserts that the ledger moves when prices move, which is a
property the code either has or does not.
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                 # noqa: E402
from boring_alpha.journal import Comparator                  # noqa: E402

ANCHOR = dt.date(2020, 1, 31)
OPENING, MONTHLY = paper.OPENING, paper.MONTHLY
VOO = Comparator("100% VOO", {"VOO": 1.0}, paper.FEES["VOO"])


def quotes(price: float) -> dict:
    return {s: price for s in ("VOO", "SPY", "QQQ")}


def walk(path, arrived=MONTHLY):
    """Step the witness through a price path, one month-end per price, and return every entry."""

    entry = paper.shadow_anchor(ANCHOR, quotes(path[0]))
    chain = (entry,)
    for i, price in enumerate(path[1:], start=1):
        entry = paper.shadow_step(chain, dt.date(2020 + (i + 3) // 12, (i - 1) % 12 + 1, 28),
                                  arrived, quotes(price), VOO, "0" * 64)
        chain += (entry,)
    return chain


def paid_in(months):
    return OPENING + MONTHLY * months


class TheWitnessMoves(unittest.TestCase):
    """Four months in which the fund rose a third. Before the fix the witness gained nothing."""

    def setUp(self):
        self.chain = walk([100.0, 110.0, 121.0, 133.1])

    def test_the_witness_finishes_ahead_of_what_was_deposited(self):
        last, paid = self.chain[-1], paid_in(3)
        self.assertGreater(last.closing_value, paid,
                           "a benchmark that returns the deposits in a rising market gives every strategy a free win")

    def test_the_witness_finishes_behind_the_deposits_when_the_fund_falls(self):
        down = walk([100.0, 90.0, 81.0, 72.9])[-1]
        self.assertLess(down.closing_value, paid_in(3),
                        "the same defect must show up as a false loss, and a false loss retires a strategy for nothing")
        self.assertLess(down.closing_value, self.chain[-1].closing_value)

    def test_the_holdings_grow_every_month_of_a_rising_market_because_it_never_sells_its_gain(self):
        """The tell-tale. The defective version sized the account to the deposits, so an up month meant selling back into the
        target; a witness that compounds holds the same units and buys only the new deposit."""

        units = [sum(h.units for h in e.holdings) for e in self.chain[1:]]
        self.assertTrue(all(b >= a for a, b in zip(units, units[1:])), f"the witness sold into strength: {units}")

    def test_the_sealed_balance_matches_dollar_cost_averaging_computed_by_hand(self):
        """An independent oracle, written out longhand rather than by calling the code under test.

        The anchor holds cash and the first step buys with it, so on this path 5,500 is spent at 133.1 and 500 more at 100.0:
        41.3224 units plus 5.0000 units, worth 4,632.24 at the closing price, less about a fortnight of a 3 bp expense
        ratio. The defective code sold the 133.1 position down to the deposits at the peak and bought it back at 100, which
        puts a few hundred dollars of churn between that figure and the ledger.
        """

        trip = walk([100.0, 133.1, 100.0])[-1]
        expected = ((OPENING + MONTHLY) / 133.1 + MONTHLY / 100.0) * 100.0
        self.assertLess(trip.closing_value, expected, "the ledger may not exceed what the deposits bought")
        self.assertGreater(trip.closing_value, expected * 0.995,
                           f"expected {expected:,.2f} from dollar-cost averaging, got {trip.closing_value:,.2f}")

    def test_a_flat_market_still_computes_the_number_the_old_code_computed(self):
        """Nothing changes when prices do not move, which is the point: the fix repairs a mark-to-market error, it does not
        restate an accounting convention that was already right."""

        flat = walk([100.0, 100.0, 100.0, 100.0])[-1]
        paid = paid_in(3)
        self.assertLess(flat.closing_value, paid)
        self.assertGreater(flat.closing_value, paid * 0.99, f"a flat market should cost fees only: {flat.closing_value}")


class TheCashLine(unittest.TestCase):
    def test_the_cash_line_is_recovered_at_the_prices_the_ledger_sealed_not_todays(self):
        """The second entry of a flat-then-rising path: its holdings were sealed at 100.00 and are being read at 140.00, so
        the only defensible cash line is the sealed total less those units at 100.00."""

        entry = walk([100.0, 100.0, 140.0])[-2]
        units = {h.symbol: h.units for h in entry.holdings}
        sealed = sum(u * 100.0 for u in units.values())
        self.assertAlmostEqual(paper.recover_cash(entry, quotes(140.0), MONTHLY, units),
                               entry.closing_value + MONTHLY - sealed, places=4)

    def test_the_old_derivation_would_have_read_a_gain_as_a_shortfall(self):
        """Pinned so the fix cannot be quietly reverted: at +40% the subtraction the code used to do reads the month's whole
        gain as missing cash — about two fifths of the account — and would have sold it."""

        entry = walk([100.0, 100.0, 140.0])[-2]
        units = {h.symbol: h.units for h in entry.holdings}
        today = sum(u * 140.0 for u in units.values())
        naive = entry.closing_value + MONTHLY - today
        self.assertLess(naive, 0.0, f"the old line now reads positive ({naive}); the two marks have converged")
        self.assertGreater(paper.recover_cash(entry, quotes(140.0), MONTHLY, units), 0.0)

    def test_the_witness_and_the_strategy_recover_cash_from_one_implementation(self):
        """Two chains, one rule. If either grows its own copy of this arithmetic, the comparison between them stops
        meaning anything — which is how the defect in this file's title arrived in the first place."""

        src = (ROOT / "tools" / "paper.py").read_text()
        body = src[src.index("def command_step"):]
        self.assertIn("recover_cash(head", body[:2000], "command_step stopped using the shared recovery")
        self.assertIn("recover_cash(head", src[src.index("def shadow_step"):src.index("def shadow_step") + 3000])
        self.assertNotIn("cash = equity - held", src, "the defective derivation is back")
        self.assertNotIn("cash = opening + arrived - held", src, "the defective derivation is back")


if __name__ == "__main__":
    unittest.main()
