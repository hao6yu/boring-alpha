"""Hand-computed interactions that aggregate P&L identities cannot validate."""

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from boring_alpha.config import TaxConfig
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, PriceBar
from boring_alpha.tax.lots import LotBook, WashSaleLedger
from boring_alpha.tax.overlay import apply_overlay
from boring_alpha.tax.policy import Scenario


def _overlay(days, adjusted, unadjusted, dividends, transactions, initial_cash, *, book=None):
    """Build a self-financing zero-cost account without using the tax code."""

    fills = [Fill(day, "A", side, quantity, price, quantity * price, 0.0,
                  quantity * price, price)
             for day, side, quantity, price in transactions]
    cash, units = initial_cash, 0.0
    curve = []
    for day, close in zip(days, adjusted):
        for fill in fills:
            if fill.date == day:
                direction = 1 if fill.side == "BUY" else -1
                units += direction * fill.quantity
                cash -= direction * fill.notional
        curve.append(EquityPoint(day, cash + units * close, cash, units * close))
    result = BacktestResult(name="interaction", equity_curve=tuple(curve), fills=tuple(fills),
                            decisions=(), initial_equity=initial_cash)
    data = MarketData([PriceBar(day, "A", close, close) for day, close in zip(days, adjusted)],
                      {day: 1.0 for day in days}, source="synthetic-interaction")
    table = DistributionTable(
        [(day, "A", close, dividend) for day, close, dividend in zip(days, unadjusted, dividends)],
        splits={"A": []}, sha256="d" * 64, source="synthetic-interaction",
    )
    tax = TaxConfig(Path("unused.csv"), 0.35, 0.20, 0.28, 0.5, {"A": 1.0}, {"A": "standard"})
    arguments = (result, data, table, tax, Scenario("fifo", "deferral", "base"))
    if book is not None:
        with patch("boring_alpha.tax.overlay.LotBook", return_value=book):
            return apply_overlay(*arguments, initial_cash=initial_cash, code_sha256="c" * 64)
    return apply_overlay(*arguments, initial_cash=initial_cash, code_sha256="c" * 64)


class ReplacementSliceTests(unittest.TestCase):
    def test_existing_partial_replacement_keeps_four_adjusted_and_six_unadjusted_shares(self):
        book = LotBook("hifo")
        wash = WashSaleLedger(book)
        book.buy("A", date(2022, 1, 1), 4.0, 400.0)
        book.buy("A", date(2024, 1, 20), 10.0, 900.0)
        wash.sell(book.sell("A", date(2024, 2, 1), 4.0, 360.0))
        matched, untouched = book.open_lots("A")
        self.assertEqual((matched.shares, untouched.shares), (4.0, 6.0))
        self.assertAlmostEqual(matched.basis, 400.0)
        self.assertAlmostEqual(untouched.basis, 540.0)
        self.assertEqual(untouched.opened, date(2024, 1, 20))
        sale = book.sell("A", date(2024, 4, 1), 4.0, 440.0)[0]
        self.assertAlmostEqual(sale.basis, 400.0)
        self.assertAlmostEqual(sale.gain, 40.0)
        self.assertEqual(book.open_lots("A"), (untouched,))

    def test_future_partial_replacement_has_the_same_per_share_treatment(self):
        book = LotBook("hifo")
        wash = WashSaleLedger(book)
        book.buy("A", date(2022, 1, 1), 4.0, 400.0)
        wash.sell(book.sell("A", date(2024, 2, 1), 4.0, 360.0))
        book.buy("A", date(2024, 2, 15), 10.0, 900.0)
        wash.purchase(date(2024, 2, 15), "A")
        matched, untouched = book.open_lots("A")
        self.assertAlmostEqual(matched.basis, 400.0)
        self.assertAlmostEqual(untouched.basis, 540.0)
        self.assertEqual(untouched.opened, date(2024, 2, 15))
        self.assertEqual(untouched.replacement_capacity, 6.0)
        self.assertAlmostEqual(book.sell("A", date(2024, 4, 1), 4.0, 440.0)[0].gain, 40.0)

    def test_fifo_purchase_order_does_not_change_when_a_holding_period_is_tacked(self):
        book = LotBook("fifo")
        wash = WashSaleLedger(book)
        book.buy("A", date(2020, 1, 1), 10.0, 1000.0)
        older = book.buy("A", date(2023, 1, 1), 10.0, 900.0)
        replacement = book.buy("A", date(2024, 1, 20), 10.0, 900.0)
        wash.sell(book.sell("A", date(2024, 2, 1), 10.0, 900.0))
        self.assertLess(replacement.opened, older.opened)
        sale = book.sell("A", date(2024, 4, 1), 1.0, 100.0)[0]
        self.assertEqual(sale.lot_id, older.lot_id)
        self.assertAlmostEqual(sale.basis, 90.0)

    def test_chained_partial_washes_preserve_each_remaining_basis_slice(self):
        book = LotBook("hifo")
        wash = WashSaleLedger(book)
        book.buy("A", date(2022, 1, 1), 4.0, 400.0)
        wash.sell(book.sell("A", date(2024, 1, 10), 4.0, 360.0))
        book.buy("A", date(2024, 1, 11), 10.0, 900.0)
        wash.purchase(date(2024, 1, 11), "A")
        wash.sell(book.sell("A", date(2024, 2, 1), 2.0, 160.0))
        slices = sorted((lot.shares, round(lot.basis, 8)) for lot in book.open_lots("A"))
        self.assertEqual(slices, [(2.0, 200.0), (2.0, 220.0), (4.0, 360.0)])
        self.assertAlmostEqual(sum(record.disallowed for record in wash.realized), 80.0)
        final = book.sell("A", date(2024, 4, 1), 8.0, 800.0)
        self.assertAlmostEqual(sum(record.gain for record in final), 20.0)


class DividendOwnershipTests(unittest.TestCase):
    def test_only_retained_shares_qualify_after_an_early_partial_sale(self):
        days = [date(2024, 5, 20), date(2024, 6, 14), date(2024, 6, 17), date(2024, 12, 31)]
        out = _overlay(days, [99.0] * 4, [100.0, 99.0, 99.0, 99.0], [0.0, 1.0, 0.0, 0.0],
                       [(days[0], "BUY", 10.0, 99.0), (days[2], "SELL", 5.0, 99.0)], 990.0)
        year = out["by_year"][0]
        self.assertAlmostEqual(year["qualified_income"], 4.9)
        self.assertAlmostEqual(year["ordinary_income"], 5.0)
        self.assertAlmostEqual(year["income_tax"], 4.9 * 0.20 + 5.0 * 0.35)
        self.assertTrue(out["identity_checks"]["share_identity_passed"])
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])

    def test_a_later_wash_split_preserves_prior_dividend_entitlements(self):
        book = LotBook("fifo")
        wash = WashSaleLedger(book)
        book.buy("A", date(2022, 1, 1), 4.0, 400.0)
        acquired = date(2024, 5, 20)
        book.buy("A", acquired, 10.0, 900.0)
        book.distribute("A", date(2024, 6, 1), 1.0, 1.01, return_of_capital=False)
        wash.sell(book.sell("A", date(2024, 6, 10), 4.0, 360.0))
        book.sell("A", date(2024, 6, 20), 4.0, 440.0)
        book.sell("A", date(2024, 7, 31), 6.0, 600.0)
        holdings = [holding for holding in book.dividend_holdings() if holding.acquired == acquired]
        self.assertEqual(len(holdings), 2)
        self.assertEqual([(holding.closed, holding.cash) for holding in holdings],
                         [(date(2024, 6, 20), 4.0), (date(2024, 7, 31), 6.0)])


class ChronologicalPurchaseTests(unittest.TestCase):
    def test_earlier_drip_receives_loss_before_a_later_known_buy(self):
        days = [date(2024, 1, 2), date(2024, 4, 1), date(2024, 4, 10),
                date(2024, 4, 20), date(2024, 7, 20)]
        book = LotBook("fifo")
        out = _overlay(days, [100.0, 90.0, 90.0, 90.0, 90.0],
                       [101.0, 90.9, 90.0, 90.0, 90.0], [0.0, 0.0, 0.9, 0.0, 0.0],
                       [(days[0], "BUY", 10.0, 100.0), (days[1], "SELL", 4.0, 90.0),
                        (days[3], "BUY", 4.0, 90.0)], 1000.0, book=book)
        attached = {day: sum(lot.disallowed_attached for lot in book.open_lots("A")
                             if lot.acquired == day) for day in days}
        self.assertAlmostEqual(attached[days[2]], 0.60)
        self.assertAlmostEqual(attached[days[3]], 39.40)
        self.assertAlmostEqual(out["totals"]["wash_sale_disallowed_total"], 40.0)
        self.assertTrue(out["identity_checks"]["share_identity_passed"])
        self.assertTrue(out["identity_checks"]["income_plus_gain_passed"])

    def test_a_january_replacement_updates_the_prior_december_tax_year(self):
        days = [date(2023, 1, 2), date(2023, 12, 20), date(2024, 1, 10), date(2024, 6, 30)]
        out = _overlay(days, [100.0, 90.0, 90.0, 110.0], [100.0, 90.0, 90.0, 110.0], [0.0] * 4,
                       [(days[0], "BUY", 10.0, 100.0), (days[1], "SELL", 10.0, 90.0),
                        (days[2], "BUY", 10.0, 90.0)], 1000.0)
        prior = out["by_year"][0]
        self.assertAlmostEqual(prior["wash_disallowed"], 100.0)
        self.assertAlmostEqual(prior["short_losses"], 0.0)
        self.assertAlmostEqual(prior["short_carry_out"], 0.0)
        # Replacement basis is 1000, terminal proceeds 1100, with long-term tack.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 20.0)

    def test_one_future_buy_keeps_the_two_sold_lots_holding_periods_separate(self):
        days = [date(2022, 1, 2), date(2024, 1, 2), date(2024, 2, 1),
                date(2024, 2, 15), date(2024, 12, 1)]
        out = _overlay(days, [100.0, 100.0, 90.0, 90.0, 110.0],
                       [100.0, 100.0, 90.0, 90.0, 110.0], [0.0] * 5,
                       [(days[0], "BUY", 4.0, 100.0), (days[1], "BUY", 6.0, 100.0),
                        (days[2], "SELL", 10.0, 90.0), (days[3], "BUY", 10.0, 90.0)], 2000.0)
        # The first four replacement shares inherit the 2022 holding period;
        # the other six remain short-term at liquidation. Each gains $10.
        self.assertAlmostEqual(out["totals"]["tax_liquidation"], 4.0 * 10.0 * 0.20 + 6.0 * 10.0 * 0.35)

    def test_zero_quantity_fills_do_not_create_lots(self):
        days = [date(2024, 1, 2), date(2024, 12, 31)]
        out = _overlay(days, [100.0, 100.0], [100.0, 100.0], [0.0, 0.0],
                       [(days[0], "BUY", 0.0, 100.0), (days[1], "SELL", 0.0, 100.0)], 1000.0)
        self.assertEqual(out["totals"]["open_lots_at_end"], 0)
        self.assertAlmostEqual(out["wealth"]["after_tax_post_liquidation"], 1000.0)


if __name__ == "__main__":
    unittest.main()
