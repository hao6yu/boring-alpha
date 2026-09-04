"""Planning turns targets into order intents without touching the book."""

from datetime import date
import unittest

from boring_alpha.domain import Order
from boring_alpha.portfolio.account import Portfolio

DAY = date(2025, 2, 3)
PRICES = {"A": 10.0, "B": 20.0}
REFERENCES = {"A": 9.0, "B": 21.0}


class PlanRebalanceTests(unittest.TestCase):
    def test_a_flat_book_plans_one_buy_per_target(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        orders = portfolio.plan_rebalance(PRICES, {"A": 0.5, "B": 0.5}, REFERENCES, DAY)
        self.assertEqual(
            orders,
            [
                Order(DAY, "A", "BUY", 500.0, 9.0),
                Order(DAY, "B", "BUY", 500.0, 21.0),
            ],
        )

    def test_planning_does_not_mutate_cash_or_positions(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        portfolio.plan_rebalance(PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY)
        self.assertEqual(portfolio.cash, 1_000.0)
        self.assertEqual(portfolio.positions, {"A": 0.0, "B": 0.0})

    def test_an_overweight_holding_plans_a_sell(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        orders = portfolio.plan_rebalance(PRICES, {"A": 0.0, "B": 1.0}, REFERENCES, DAY)
        self.assertEqual(orders[0], Order(DAY, "A", "SELL", 1_000.0, 9.0))
        self.assertEqual(orders[1], Order(DAY, "B", "BUY", 1_000.0, 21.0))

    def test_a_holding_already_at_target_plans_nothing(self) -> None:
        portfolio = Portfolio(0.0, ("A", "B"))
        portfolio.positions["A"] = 100.0
        orders = portfolio.plan_rebalance(PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY)
        self.assertEqual(orders, [])

    def test_orders_are_planned_in_sorted_symbol_order(self) -> None:
        portfolio = Portfolio(1_000.0, ("B", "A"))
        orders = portfolio.plan_rebalance(PRICES, {"A": 0.5, "B": 0.5}, REFERENCES, DAY)
        self.assertEqual([order.symbol for order in orders], ["A", "B"])

    def test_the_reference_price_is_recorded_not_the_execution_price(self) -> None:
        portfolio = Portfolio(1_000.0, ("A", "B"))
        orders = portfolio.plan_rebalance(PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY)
        self.assertEqual(orders[0].reference_price, 9.0)
        self.assertNotEqual(orders[0].reference_price, PRICES["A"])


if __name__ == "__main__":
    unittest.main()
