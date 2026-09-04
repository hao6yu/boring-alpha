"""Tax lots are kept in real shares with unadjusted-dollar basis (spec §4.2)."""

from datetime import date, timedelta
import unittest

from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.tax.lots import (
    FuturePurchase,
    LotBook,
    Realized,
    adjustment_factor,
    apply_wash_sales,
)

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

    def test_the_factor_is_sampled_once_per_ex_date_interval(self) -> None:
        # Unadjusted closes carry ~2e-7 relative jitter on D1 and D3 (the kind
        # Yahoo's ~7-significant-digit adjusted closes actually show); the
        # adjusted series is flat, so the raw per-day ratio would jitter too.
        # Sampled once per interval, D0/D1 share D0's ratio and D2/D3 share D2's.
        data = _market({"A": [99.0, 99.0, 99.0, 99.0]})
        table = _table(
            {"A": [100.0, 100.00002, 99.0, 99.00003]}, {"A": [0.0, 0.0, 1.0, 0.0]}
        )
        self.assertEqual(adjustment_factor(data, table, D0, "A"), 99.0 / 100.0)
        self.assertEqual(adjustment_factor(data, table, D1, "A"), 99.0 / 100.0)
        self.assertEqual(adjustment_factor(data, table, D2, "A"), 99.0 / 99.0)
        self.assertEqual(adjustment_factor(data, table, D3, "A"), 99.0 / 99.0)

    def test_the_reference_never_precedes_the_market_data(self) -> None:
        # The table's first session for A is D0, but the market data (and so
        # the run) only starts on D1: the reference must not reach back to a
        # date `data` cannot price.
        data = _market({"A": [99.0, 99.0, 99.0]}, days=(D1, D2, D3))
        table = _table({"A": [100.0, 99.0, 99.0, 99.0]}, days=(D0, D1, D2, D3))
        self.assertEqual(adjustment_factor(data, table, D1, "A"), 99.0 / 99.0)


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


class DistributionTests(unittest.TestCase):
    """Adjusted close 99 throughout; unadjusted 100, then 99 after a 1.00 dividend on D1.
    The factor A/P is 0.99 before the ex-date and 1.0 after, so growth is 1/0.99."""

    def setUp(self) -> None:
        self.data = _market({"A": [99.0, 99.0, 99.0, 99.0]})
        self.table = _table({"A": [100.0, 99.0, 99.0, 99.0]}, {"A": [0.0, 1.0, 0.0, 0.0]})
        before = adjustment_factor(self.data, self.table, D0, "A")
        after = adjustment_factor(self.data, self.table, D1, "A")
        self.growth = after / before

    def _buy_ten_units(self, book: LotBook):
        # Ten engine units bought on D0 for 990 are 9.9 real shares at 100.
        shares = 10.0 * adjustment_factor(self.data, self.table, D0, "A")
        return book.buy("A", D0, shares, 990.0)

    def test_income_opens_a_child_lot_and_leaves_the_parent_basis_alone(self) -> None:
        book = LotBook("fifo")
        parent = self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertAlmostEqual(event.cash, 9.9)
        self.assertFalse(event.return_of_capital)
        self.assertEqual((event.lot_id, event.lot_opened, event.ex_date), (parent.lot_id, D0, D1))
        child = book.lots[event.child_lot_id]
        self.assertAlmostEqual(child.shares, 0.1)
        self.assertAlmostEqual(child.basis, 9.9)
        self.assertEqual((child.opened, child.acquired, child.source), (D1, D1, "reinvest"))
        self.assertAlmostEqual(parent.basis, 990.0)
        # Real shares now equal the engine's ten units at the post-dividend factor.
        self.assertAlmostEqual(
            book.shares_held("A"), 10.0 * adjustment_factor(self.data, self.table, D1, "A")
        )
        # The reinvestment price the data implies is the unadjusted close.
        self.assertAlmostEqual(event.cash / child.shares, 99.0)

    def test_income_plus_gain_equals_the_adjusted_profit(self) -> None:
        book = LotBook("fifo")
        self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        # Sold on D3: ten engine units at 99 are 990, the same as ten real shares at 99.
        records = book.sell("A", D3, book.shares_held("A"), 990.0)
        income = sum(event.cash for event in events)
        gains = sum(record.gain for record in records)
        self.assertAlmostEqual(income, 9.9)
        self.assertAlmostEqual(gains, -9.9)
        self.assertAlmostEqual(income + gains, 990.0 - 990.0, places=9)

    def test_return_of_capital_reduces_the_parent_and_is_not_income(self) -> None:
        book = LotBook("fifo")
        parent = self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=True)
        self.assertTrue(events[0].return_of_capital)
        self.assertAlmostEqual(parent.basis, 980.1)
        self.assertAlmostEqual(book.lots[events[0].child_lot_id].basis, 9.9)
        self.assertAlmostEqual(sum(lot.basis for lot in book.open_lots("A")), 990.0)
        records = book.sell("A", D3, book.shares_held("A"), 990.0)
        self.assertAlmostEqual(sum(record.gain for record in records), 0.0, places=9)
        self.assertEqual(book.extra_realized, [])

    def test_return_of_capital_beyond_basis_is_a_gain_on_the_ex_date(self) -> None:
        book = LotBook("fifo")
        shares = 10.0 * adjustment_factor(self.data, self.table, D0, "A")
        lot = book.buy("A", D0, shares, 5.0)   # an implausibly low basis, to force the excess
        book.distribute("A", D1, 1.0, self.growth, return_of_capital=True)
        self.assertAlmostEqual(lot.basis, 0.0)
        self.assertEqual(len(book.extra_realized), 1)
        excess = book.extra_realized[0]
        self.assertAlmostEqual(excess.gain, 4.9)
        self.assertEqual((excess.shares, excess.sold, excess.opened), (0.0, D1, D0))

    def test_a_lot_bought_on_the_ex_date_receives_nothing(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D1, 10.0, 990.0)
        self.assertEqual(book.distribute("A", D1, 1.0, self.growth, return_of_capital=False), [])
        self.assertEqual(len(book.lots), 1)

    def test_child_lots_do_not_receive_the_distribution_that_created_them(self) -> None:
        book = LotBook("fifo")
        self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(book.lots), 2)

    def test_no_growth_means_no_child_lot_but_the_cash_is_still_recorded(self) -> None:
        book = LotBook("fifo")
        self._buy_ten_units(book)
        events = book.distribute("A", D1, 1.0, 1.0, return_of_capital=False)
        self.assertIsNone(events[0].child_lot_id)
        self.assertAlmostEqual(events[0].cash, 9.9)

    def test_a_negative_dividend_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "dividend"):
            LotBook("fifo").distribute("A", D1, -1.0, 1.0, return_of_capital=False)

    def test_two_lots_share_one_pooled_child_lot(self) -> None:
        """A sleeve held through many ex-dates must not double its lot count at each one."""

        book = LotBook("fifo")
        book.buy("A", D0, 9.9, 990.0)
        book.buy("A", D0, 4.95, 495.0)
        events = book.distribute("A", D1, 1.0, self.growth, return_of_capital=False)
        self.assertEqual(len(events), 2)
        child_ids = {event.child_lot_id for event in events}
        self.assertEqual(len(child_ids), 1, "both events must name the same pooled child lot")
        child_id = child_ids.pop()
        self.assertIsNotNone(child_id)
        # Two parent lots plus exactly one pooled child: no per-recipient doubling.
        self.assertEqual(len(book.lots), 3)
        child = book.lots[child_id]
        self.assertAlmostEqual(child.shares, (9.9 + 4.95) * (self.growth - 1.0))
        self.assertAlmostEqual(child.basis, 14.85)


class WashSaleTests(unittest.TestCase):
    """A 10-share lot bought at 1000 on D0 and sold on 2024-02-01 for 900: a 100 loss."""

    SOLD = date(2024, 2, 1)

    def _loss(self) -> tuple[LotBook, list[Realized]]:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        return book, book.sell("A", self.SOLD, 10.0, 900.0)

    def test_a_purchase_thirty_days_later_disallows_the_whole_loss(self) -> None:
        book, records = self._loss()
        future = FuturePurchase("A", self.SOLD + timedelta(days=30), 10.0, 10.0)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [future])
        self.assertAlmostEqual(adjusted[0].disallowed, 100.0)
        self.assertAlmostEqual(adjusted[0].gain, 0.0)
        self.assertAlmostEqual(future.pending_basis, 100.0)
        self.assertEqual(future.pending_tack_days, (self.SOLD - D0).days)
        self.assertAlmostEqual(future.replacement_capacity, 0.0)

    def test_thirty_one_days_later_is_outside_the_window(self) -> None:
        book, records = self._loss()
        future = FuturePurchase("A", self.SOLD + timedelta(days=31), 10.0, 10.0)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [future])
        self.assertAlmostEqual(adjusted[0].disallowed, 0.0)
        self.assertAlmostEqual(future.pending_basis, 0.0)

    def test_partial_replacement_disallows_a_proportional_share(self) -> None:
        book, records = self._loss()
        future = FuturePurchase("A", self.SOLD + timedelta(days=10), 4.0, 4.0)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [future])
        self.assertAlmostEqual(adjusted[0].disallowed, 40.0)
        self.assertAlmostEqual(adjusted[0].gain, -60.0)
        self.assertAlmostEqual(future.pending_basis, 40.0)

    def test_an_existing_lot_is_adjusted_immediately(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)                                 # lot 1, sold at a loss
        replacement = book.buy("A", date(2024, 1, 20), 10.0, 950.0)     # lot 2, inside the window
        records = book.sell("A", self.SOLD, 10.0, 900.0)                # fifo sells lot 1
        self.assertEqual(records[0].lot_id, 1)
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 100.0)
        self.assertAlmostEqual(replacement.basis, 1050.0)
        self.assertAlmostEqual(replacement.disallowed_attached, 100.0)
        self.assertEqual(
            replacement.opened, date(2024, 1, 20) - timedelta(days=(self.SOLD - D0).days)
        )
        self.assertEqual(replacement.acquired, date(2024, 1, 20))
        self.assertAlmostEqual(replacement.replacement_capacity, 0.0)

    def test_replacement_shares_are_matched_once(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        # Deliberately outside the wash-sale window (D1 is only 29 days before
        # SOLD, which is inside it) so this lot cannot itself serve as a
        # replacement, leaving lot 3 as the only one.
        book.buy("A", date(2024, 6, 1), 10.0, 1000.0)
        book.buy("A", date(2024, 1, 20), 10.0, 950.0)   # lot 3: the only replacement
        first = apply_wash_sales(book.sell("A", self.SOLD, 10.0, 900.0), book.open_lots("A"), [])
        second = apply_wash_sales(book.sell("A", self.SOLD, 10.0, 900.0), book.open_lots("A"), [])
        self.assertAlmostEqual(first[0].disallowed, 100.0)
        self.assertAlmostEqual(second[0].disallowed, 0.0)

    def test_the_shares_sold_do_not_replace_themselves(self) -> None:
        book = LotBook("fifo")
        book.buy("A", date(2024, 1, 25), 10.0, 1000.0)   # bought within 30 days of the sale
        records = book.sell("A", self.SOLD, 10.0, 900.0)  # and sold in full
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 0.0)

    def test_the_unsold_remainder_of_the_same_lot_does_replace(self) -> None:
        book = LotBook("fifo")
        book.buy("A", date(2024, 1, 25), 10.0, 1000.0)
        records = book.sell("A", self.SOLD, 4.0, 360.0)   # a 40 loss on four shares; six remain
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 40.0)
        self.assertAlmostEqual(book.lots[1].basis, 640.0)

    def test_gains_and_other_symbols_are_untouched(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        other = book.buy("B", D1, 10.0, 1000.0)
        records = book.sell("A", self.SOLD, 10.0, 1100.0)
        adjusted = apply_wash_sales(records, book.open_lots("A") + book.open_lots("B"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 0.0)
        self.assertAlmostEqual(other.basis, 1000.0)
        self.assertAlmostEqual(other.replacement_capacity, 10.0)

    def test_reinvested_lots_count_as_purchases(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 10.0, 1000.0)
        # A child lot of 0.1 shares opened by a distribution inside the window.
        book.distribute("A", date(2024, 1, 20), 1.0, 1.01, return_of_capital=False)
        records = book.sell("A", self.SOLD, 10.0, 900.0)   # fifo: the parent lot
        adjusted = apply_wash_sales(records, book.open_lots("A"), [])
        self.assertAlmostEqual(adjusted[0].disallowed, 100.0 * 0.1 / 10.0)

    def test_a_replacement_lot_is_tacked_once_per_call(self) -> None:
        book = LotBook("fifo")
        book.buy("A", D0, 5.0, 500.0)
        book.buy("A", D1, 5.0, 500.0)
        replacement = book.buy("A", date(2024, 1, 20), 10.0, 950.0)
        records = book.sell("A", self.SOLD, 10.0, 900.0)   # two loss records, one replacement lot
        apply_wash_sales(records, book.open_lots("A"), [])
        self.assertEqual(
            replacement.opened, date(2024, 1, 20) - timedelta(days=(self.SOLD - D0).days)
        )
        self.assertAlmostEqual(replacement.basis, 1050.0)


if __name__ == "__main__":
    unittest.main()
