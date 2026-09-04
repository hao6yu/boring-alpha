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


class NoTradeThresholdTests(unittest.TestCase):
    """Pins the no-trade threshold at 1e-10: nothing here can pass at 1e2 or 1e-2."""

    def test_a_difference_of_exactly_the_threshold_plans_nothing(self) -> None:
        # equity is exactly 1.0 (no position, no other cash), so
        # equity * target_weight lands on 1e-10 with no rounding to spare.
        portfolio = Portfolio(1.0, ("A",))
        orders = portfolio.plan_rebalance(
            {"A": 1.0}, {"A": 1e-10}, {"A": 1.0}, DAY
        )
        self.assertEqual(orders, [])

    def test_a_difference_just_above_the_threshold_plans_an_order(self) -> None:
        portfolio = Portfolio(1.0, ("A",))
        orders = portfolio.plan_rebalance(
            {"A": 1.0}, {"A": 1.1e-10}, {"A": 1.0}, DAY
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, "BUY")

    def test_a_one_cent_difference_against_a_thousand_dollar_book_plans_an_order(
        self,
    ) -> None:
        # cash 0.01 + 999.99 already in A: equity is exactly 1,000.00, and a
        # full-weight target moves A by exactly $0.01 — economically real,
        # nowhere near the 1e-10 floor, and still invisible if the guard were
        # ever loosened to a cent-scale tolerance.
        portfolio = Portfolio(0.01, ("A", "B"))
        portfolio.positions["A"] = 99.999
        orders = portfolio.plan_rebalance(
            PRICES, {"A": 1.0, "B": 0.0}, REFERENCES, DAY
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].symbol, "A")
        self.assertAlmostEqual(orders[0].intended_notional, 0.01)


class PriceValidationTests(unittest.TestCase):
    def test_a_zero_price_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-positive price for A: 0.0"):
            Portfolio(1_000.0, ("A", "B")).plan_rebalance(
                {"A": 0.0, "B": 20.0}, {"A": 0.5, "B": 0.5}, REFERENCES, DAY
            )

    def test_a_negative_price_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-positive price for B: -20.0"):
            Portfolio(1_000.0, ("A", "B")).plan_rebalance(
                {"A": 10.0, "B": -20.0}, {"A": 0.5, "B": 0.5}, REFERENCES, DAY
            )


if __name__ == "__main__":
    unittest.main()
