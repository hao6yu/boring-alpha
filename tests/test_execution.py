"""Execution turns intents into fills: costs, cash limits, and ordering."""

from datetime import date
import unittest

from boring_alpha.domain import Order
from boring_alpha.execution import CostModel, execute
from boring_alpha.portfolio.account import AccountingError, Portfolio

DAY = date(2025, 2, 3)
PRICES = {"A": 10.0, "B": 20.0}
FREE = CostModel(0.0)


class ExecutionTests(unittest.TestCase):
    def test_a_buy_fills_at_the_execution_price(self) -> None:
        orders = [Order(DAY, "A", "BUY", 500.0, 9.0)]
        fills = execute(orders, PRICES, 1_000.0, FREE)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].price, 10.0)
        self.assertAlmostEqual(fills[0].quantity, 50.0)
        self.assertAlmostEqual(fills[0].notional, 500.0)
        self.assertAlmostEqual(fills[0].intended_notional, 500.0)
        self.assertEqual(fills[0].reference_price, 9.0)

    def test_costs_are_charged_at_the_configured_rate(self) -> None:
        fills = execute([Order(DAY, "A", "BUY", 100.0, 9.0)], PRICES, 1_000.0, CostModel(10.0))
        self.assertAlmostEqual(fills[0].cost, 0.10)

    def test_sells_execute_before_buys(self) -> None:
        orders = [
            Order(DAY, "B", "BUY", 100.0, 21.0),
            Order(DAY, "A", "SELL", 100.0, 9.0),
        ]
        fills = execute(orders, PRICES, 0.0, FREE)
        self.assertEqual([(f.symbol, f.side) for f in fills], [("A", "SELL"), ("B", "BUY")])

    def test_each_side_fills_in_sorted_symbol_order(self) -> None:
        orders = [
            Order(DAY, "B", "BUY", 100.0, 21.0),
            Order(DAY, "A", "BUY", 100.0, 9.0),
        ]
        fills = execute(orders, PRICES, 1_000.0, FREE)
        self.assertEqual([fill.symbol for fill in fills], ["A", "B"])

    def test_sale_proceeds_fund_a_purchase_in_the_same_batch(self) -> None:
        orders = [
            Order(DAY, "A", "SELL", 1_000.0, 9.0),
            Order(DAY, "B", "BUY", 1_000.0, 21.0),
        ]
        fills = execute(orders, PRICES, 0.0, FREE)
        self.assertAlmostEqual(fills[1].notional, 1_000.0)

    def test_buys_scale_pro_rata_when_cash_is_short(self) -> None:
        orders = [
            Order(DAY, "A", "BUY", 500.0, 9.0),
            Order(DAY, "B", "BUY", 500.0, 21.0),
        ]
        fills = execute(orders, PRICES, 1_000.0, CostModel(100.0))
        expected = 500.0 * (1_000.0 / 1_010.0)
        for fill in fills:
            self.assertAlmostEqual(fill.notional, expected)
            self.assertAlmostEqual(fill.intended_notional, 500.0)

    def test_a_partially_filled_order_reports_both_notionals(self) -> None:
        fills = execute([Order(DAY, "A", "BUY", 1_000.0, 9.0)], PRICES, 500.0, FREE)
        self.assertAlmostEqual(fills[0].notional, 500.0)
        self.assertAlmostEqual(fills[0].intended_notional, 1_000.0)
        self.assertLess(fills[0].notional, fills[0].intended_notional)

    def test_no_orders_means_no_fills(self) -> None:
        self.assertEqual(execute([], PRICES, 1_000.0, FREE), [])


class ApplyTests(unittest.TestCase):
    def test_applying_fills_moves_cash_and_positions(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        fills = execute([Order(DAY, "A", "BUY", 500.0, 9.0)], PRICES, 1_000.0, FREE)
        portfolio.apply(fills)
        self.assertAlmostEqual(portfolio.cash, 500.0)
        self.assertAlmostEqual(portfolio.positions["A"], 50.0)

    def test_a_sale_returns_proceeds_net_of_cost(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        fills = execute([Order(DAY, "A", "SELL", 1_000.0, 9.0)], PRICES, 0.0, CostModel(100.0))
        portfolio.apply(fills)
        self.assertAlmostEqual(portfolio.cash, 1_000.0 - 10.0)
        self.assertAlmostEqual(portfolio.positions["A"], 0.0)

    def test_overspending_raises_an_accounting_error(self) -> None:
        portfolio = Portfolio(100.0, ("A",))
        fills = execute([Order(DAY, "A", "BUY", 1_000.0, 9.0)], PRICES, 1_000.0, FREE)
        with self.assertRaises(AccountingError):
            portfolio.apply(fills)


if __name__ == "__main__":
    unittest.main()
