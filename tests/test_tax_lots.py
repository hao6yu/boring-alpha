"""Tax lots are kept in real shares with unadjusted-dollar basis (spec §4.2)."""

from datetime import date
import unittest

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.tax.lots import LotBook, Realized, adjustment_factor

D0, D1, D2, D3 = date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)


def _market(prices: dict[str, list[float]], days=(D0, D1, D2, D3)) -> MarketData:
    """Adjusted bars with open equal to close."""

    bars = [
        PriceBar(day, symbol, price, price)
        for symbol, series in prices.items()
        for day, price in zip(days, series)
    ]
    return MarketData(bars, {day: 1.0 for day in days}, source="test")


def _table(closes: dict[str, list[float]], dividends: dict[str, list[float]] | None = None,
           days=(D0, D1, D2, D3)) -> DistributionTable:
    """Unadjusted closes and per-share dividends, zero unless given."""

    rows = []
    for symbol, series in closes.items():
        paid = (dividends or {}).get(symbol, [0.0] * len(series))
        rows.extend((day, symbol, close, dividend) for day, close, dividend in zip(days, series, paid))
    return DistributionTable(rows, splits={symbol: [] for symbol in closes}, sha256="0" * 64, source="test")


class AdjustmentFactorTests(unittest.TestCase):
    def test_factor_is_adjusted_over_unadjusted_close(self) -> None:
        data = _market({"A": [50.0, 50.0, 50.0, 50.0]})
        table = _table({"A": [100.0, 100.0, 100.0, 100.0]})
        self.assertAlmostEqual(adjustment_factor(data, table, D0, "A"), 0.5)
        # Ten engine units at a factor of 0.5 are five real shares: the past is
        # adjusted downwards, so old lots hold fewer real shares than units.
        self.assertAlmostEqual(10.0 * adjustment_factor(data, table, D0, "A"), 5.0)


class BuyTests(unittest.TestCase):
    def test_a_buy_opens_a_lot_with_full_replacement_capacity(self) -> None:
        book = LotBook("fifo")
        lot = book.buy("A", D0, 10.0, 1001.0)
        self.assertEqual(lot.lot_id, 1)
        self.assertEqual((lot.opened, lot.acquired, lot.source), (D0, D0, "buy"))
        self.assertAlmostEqual(lot.basis_per_share, 100.1)
        self.assertAlmostEqual(lot.replacement_capacity, 10.0)
        self.assertEqual(book.open_lots("A"), (lot,))
        self.assertAlmostEqual(book.shares_held("A"), 10.0)

    def test_tacked_opening_and_attached_basis_are_honoured(self) -> None:
        book = LotBook("fifo")
        lot = book.buy("A", D2, 4.0, 400.0, opened=D0, extra_basis=25.0, replacement_capacity=1.0)
        self.assertEqual((lot.opened, lot.acquired), (D0, D2))
        self.assertAlmostEqual(lot.basis, 425.0)
        self.assertAlmostEqual(lot.disallowed_attached, 25.0)
        self.assertAlmostEqual(lot.replacement_capacity, 1.0)

    def test_non_positive_shares_or_negative_basis_are_refused(self) -> None:
        book = LotBook("fifo")
        with self.assertRaisesRegex(ValueError, "shares"):
            book.buy("A", D0, 0.0, 1.0)
        with self.assertRaisesRegex(ValueError, "basis"):
            book.buy("A", D0, 1.0, -1.0)

    def test_an_unknown_method_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "lot method"):
            LotBook("lifo")


class SellTests(unittest.TestCase):
    """Two lots: 10 shares at 1001 (100.1 each) on D0, 10 shares at 1200 (120 each) on D1.
    Fifteen shares sold on D3 for 1650 net of cost."""

    def _book(self, method: str) -> LotBook:
        book = LotBook(method)
        book.buy("A", D0, 10.0, 1001.0)
        book.buy("A", D1, 10.0, 1200.0)
        return book

    def test_fifo_sells_the_earliest_lot_first_and_splits_the_second(self) -> None:
        book = self._book("fifo")
        records = book.sell("A", D3, 15.0, 1650.0)
        self.assertEqual([(r.lot_id, r.shares) for r in records], [(1, 10.0), (2, 5.0)])
        self.assertAlmostEqual(records[0].proceeds, 1100.0)
        self.assertAlmostEqual(records[0].basis, 1001.0)
        self.assertAlmostEqual(records[0].gain, 99.0)
        self.assertAlmostEqual(records[1].proceeds, 550.0)
        self.assertAlmostEqual(records[1].basis, 600.0)
        self.assertAlmostEqual(records[1].gain, -50.0)
        remaining = book.open_lots("A")
        self.assertEqual([lot.lot_id for lot in remaining], [2])
        self.assertAlmostEqual(remaining[0].shares, 5.0)
        self.assertAlmostEqual(remaining[0].basis, 600.0)
        self.assertEqual(book.lots[1].closed, D3)
        self.assertIsNone(book.lots[2].closed)

    def test_hifo_sells_the_highest_basis_per_share_first(self) -> None:
        book = self._book("hifo")
        records = book.sell("A", D3, 15.0, 1650.0)
        self.assertEqual([(r.lot_id, r.shares) for r in records], [(2, 10.0), (1, 5.0)])
        self.assertAlmostEqual(records[0].gain, -100.0)
        self.assertAlmostEqual(records[1].basis, 500.5)
        self.assertAlmostEqual(records[1].gain, 49.5)
        remaining = book.open_lots("A")
        self.assertEqual([lot.lot_id for lot in remaining], [1])
        self.assertAlmostEqual(remaining[0].basis, 500.5)

    def test_records_carry_opening_and_sale_dates(self) -> None:
        records = self._book("fifo").sell("A", D3, 15.0, 1650.0)
        self.assertEqual((records[0].opened, records[0].sold), (D0, D3))
        self.assertEqual(records[1].opened, D1)

    def test_selling_reduces_replacement_capacity_to_what_remains(self) -> None:
        book = self._book("fifo")
        book.sell("A", D3, 15.0, 1650.0)
        self.assertAlmostEqual(book.lots[1].replacement_capacity, 0.0)
        self.assertAlmostEqual(book.lots[2].replacement_capacity, 5.0)

    def test_selling_more_than_held_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "only 20"):
            self._book("fifo").sell("A", D3, 20.5, 1.0)

    def test_a_rounding_sliver_over_the_holding_is_tolerated(self) -> None:
        records = self._book("fifo").sell("A", D3, 20.0 + 1e-10, 2200.0)
        self.assertAlmostEqual(sum(r.shares for r in records), 20.0)

    def test_gain_is_proceeds_less_basis_plus_disallowed(self) -> None:
        record = Realized("A", 1, D0, D3, 1.0, 90.0, 100.0, disallowed=6.0)
        self.assertAlmostEqual(record.gain, -4.0)


if __name__ == "__main__":
    unittest.main()
