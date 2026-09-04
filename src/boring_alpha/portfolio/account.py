"""Cash, positions, and deterministic target-weight rebalancing."""

from __future__ import annotations

from datetime import date

from boring_alpha.data.market import MarketData
from boring_alpha.domain import Fill, Order


class AccountingError(RuntimeError):
    """Raised when the cash-only accounting invariant is violated."""


class Portfolio:
    def __init__(self, initial_cash: float, symbols: tuple[str, ...]) -> None:
        self.cash = initial_cash
        self.positions = {symbol: 0.0 for symbol in symbols}

    def accrue_cash(self, factor: float) -> None:
        self.cash *= factor

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

        for symbol in self.positions:
            price = prices[symbol]
            if price <= 0.0:
                raise ValueError(f"non-positive price for {symbol}: {price}")

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

    def apply(self, fills: list[Fill]) -> None:
        """Book fills against cash and positions, preserving the cash-only rule."""

        for fill in fills:
            if fill.side == "SELL":
                self.positions[fill.symbol] -= fill.quantity
                self.cash += fill.notional - fill.cost
            else:
                self.positions[fill.symbol] += fill.quantity
                self.cash -= fill.notional + fill.cost
        if self.cash < -1e-7:
            raise AccountingError(f"cash-only portfolio became negative: {self.cash}")
        if abs(self.cash) < 1e-9:
            self.cash = 0.0
