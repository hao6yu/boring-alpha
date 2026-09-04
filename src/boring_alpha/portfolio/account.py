"""Cash, positions, and deterministic target-weight rebalancing."""

from __future__ import annotations

from datetime import date

from boring_alpha.data.market import MarketData
from boring_alpha.domain import Order, Trade


class AccountingError(RuntimeError):
    """Raised when the cash-only accounting invariant is violated."""


class Portfolio:
    def __init__(self, initial_cash: float, symbols: tuple[str, ...]) -> None:
        self.cash = initial_cash
        self.positions = {symbol: 0.0 for symbol in symbols}

    def accrue_cash(self, factor: float) -> None:
        self.cash *= factor

    def equity_at_open(self, data: MarketData, day: date) -> float:
        return self.cash + sum(
            quantity * data.bar(day, symbol).open
            for symbol, quantity in self.positions.items()
        )

    def equity_at_close(self, data: MarketData, day: date) -> tuple[float, float]:
        exposure = sum(
            quantity * data.bar(day, symbol).close
            for symbol, quantity in self.positions.items()
        )
        return self.cash + exposure, exposure

    def plan_rebalance(
        self,
        prices: dict[str, float],
        target_weights: dict[str, float],
        reference_prices: dict[str, float],
        day: date,
    ) -> list[Order]:
        """Targets and holdings in, order intents out. Pure: nothing is mutated.

        Sizing uses equity at execution prices, which is what the engine fills
        at. No cost model appears here; costs belong to execution.
        """

        equity = self.cash + sum(
            quantity * prices[symbol] for symbol, quantity in self.positions.items()
        )
        orders: list[Order] = []
        for symbol in sorted(self.positions):
            current = self.positions[symbol] * prices[symbol]
            difference = equity * target_weights.get(symbol, 0.0) - current
            if abs(difference) <= 1e-10:
                continue
            orders.append(
                Order(
                    day,
                    symbol,
                    "BUY" if difference > 0.0 else "SELL",
                    abs(difference),
                    reference_prices[symbol],
                )
            )
        return orders

    def rebalance(
        self,
        data: MarketData,
        day: date,
        target_weights: dict[str, float],
        cost_bps: float,
    ) -> list[Trade]:
        """Sell first, then scale all buys pro rata to remain cash-only."""

        rate = cost_bps / 10_000.0
        equity = self.equity_at_open(data, day)
        current_values = {
            symbol: quantity * data.bar(day, symbol).open
            for symbol, quantity in self.positions.items()
        }
        target_values = {
            symbol: equity * target_weights.get(symbol, 0.0)
            for symbol in self.positions
        }
        trades: list[Trade] = []

        for symbol in sorted(self.positions):
            difference = target_values[symbol] - current_values[symbol]
            if difference >= -1e-10:
                continue
            price = data.bar(day, symbol).open
            notional = -difference
            quantity = notional / price
            cost = notional * rate
            self.positions[symbol] -= quantity
            self.cash += notional - cost
            trades.append(Trade(day, symbol, "SELL", quantity, price, notional, cost))

        buy_requests: dict[str, float] = {}
        for symbol in sorted(self.positions):
            current = self.positions[symbol] * data.bar(day, symbol).open
            difference = target_values[symbol] - current
            if difference > 1e-10:
                buy_requests[symbol] = difference

        required = sum(notional * (1.0 + rate) for notional in buy_requests.values())
        scale = min(1.0, self.cash / required) if required > 0.0 else 1.0
        for symbol, requested in buy_requests.items():
            notional = requested * scale
            price = data.bar(day, symbol).open
            quantity = notional / price
            cost = notional * rate
            self.positions[symbol] += quantity
            self.cash -= notional + cost
            trades.append(Trade(day, symbol, "BUY", quantity, price, notional, cost))

        if self.cash < -1e-7:
            raise AccountingError(f"cash-only portfolio became negative: {self.cash}")
        if abs(self.cash) < 1e-9:
            self.cash = 0.0
        return trades
