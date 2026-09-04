from datetime import date
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.portfolio.account import AccountingError, Portfolio


DAY = date(2025, 1, 2)


def _data(prices: dict[str, float]) -> MarketData:
    bars = [PriceBar(DAY, symbol, price, price) for symbol, price in prices.items()]
    return MarketData(bars, {DAY: 1.0}, source="test")


class PortfolioTests(unittest.TestCase):
    def test_negative_cash_raises_a_runtime_error_subclass(self) -> None:
        portfolio = Portfolio(1_000.0, ("A",))
        portfolio.cash = -1.0
        with self.assertRaises(AccountingError) as caught:
            portfolio.rebalance(_data({"A": 10.0}), DAY, {"A": 0.0}, 0.0)
        self.assertIsInstance(caught.exception, RuntimeError)

    def test_buys_scale_pro_rata_when_costs_exceed_cash(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        trades = portfolio.rebalance(_data({"A": 10.0, "B": 10.0}), DAY, {"A": 0.5, "B": 0.5}, 100.0)
        expected_notional = 500.0 * (1_000.0 / 1_010.0)
        self.assertEqual([t.side for t in trades], ["BUY", "BUY"])
        for trade in trades:
            self.assertAlmostEqual(trade.notional, expected_notional)
        self.assertAlmostEqual(portfolio.positions["A"], portfolio.positions["B"])
        self.assertEqual(portfolio.cash, 0.0)

    def test_sale_proceeds_fund_purchases_in_the_same_rebalance(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        trades = portfolio.rebalance(_data({"A": 10.0, "B": 20.0}), DAY, {"A": 0.0, "B": 1.0}, 0.0)
        self.assertEqual([(t.symbol, t.side) for t in trades], [("A", "SELL"), ("B", "BUY")])
        self.assertAlmostEqual(portfolio.positions["A"], 0.0)
        self.assertAlmostEqual(portfolio.positions["B"], 50.0)
        self.assertEqual(portfolio.cash, 0.0)


if __name__ == "__main__":
    unittest.main()
