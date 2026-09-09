"""Quantity-based accounting for linear, cash-settled futures research.

Prices and funding marks must be supplied by the caller. No execution, margin
model, interest, or missing-data interpolation is implied by this ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math


class MissingMark(ValueError):
    """A held instrument has no verified valuation price."""


def positive(value: float, name: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


@dataclass
class FuturesAccount:
    """Equity includes variation P&L; signed quantities stay fixed until traded."""

    equity: float = 1.0
    quantities: dict[str, float] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    fees_paid: float = 0.0
    traded_notional: float = 0.0

    def __post_init__(self) -> None:
        positive(self.equity, "initial equity")

    def mark(self, prices: dict[str, float]) -> float:
        missing = set(self.quantities) - prices.keys()
        if missing:
            raise MissingMark(f"missing held price: {', '.join(sorted(missing))}; "
                              "a missing bar is not an executable exit or a delisting")
        for symbol in self.quantities:
            positive(prices[symbol], f"{symbol} mark")
        pnl = sum(quantity * (prices[symbol] - self.marks[symbol])
                  for symbol, quantity in self.quantities.items())
        self.equity += pnl
        self.marks.update({symbol: prices[symbol] for symbol in self.quantities})
        return pnl

    def fund(self, symbol: str, rate: float, mark_price: float) -> float:
        """Return the signed payment: a long pays positive funding."""
        positive(mark_price, "funding mark")
        if not math.isfinite(rate):
            raise ValueError("funding rate must be finite")
        payment = self.quantities.get(symbol, 0.0) * mark_price * rate
        self.equity -= payment
        return payment

    def trade(self, targets: dict[str, float], prices: dict[str, float],
              fee_bps: float) -> tuple[float, float]:
        """Set target quantities at supplied fills; charge every changed unit.

        Held positions must already be marked to these fills. That explicit
        ordering prevents a rebalance from erasing intervening P&L.
        """
        positive(self.equity, "pre-trade equity")
        if not math.isfinite(fee_bps) or fee_bps < 0:
            raise ValueError("fee_bps must be finite and nonnegative")
        symbols = set(targets) | set(self.quantities)
        for symbol in symbols:
            if symbol not in prices:
                raise MissingMark(f"missing execution price: {symbol}")
            positive(prices[symbol], f"{symbol} fill")
            if not math.isfinite(targets.get(symbol, 0.0)):
                raise ValueError("target quantities must be finite")
            if symbol in self.quantities and self.marks[symbol] != prices[symbol]:
                raise ValueError("mark held positions to execution prices before trading")
        notional = sum(abs(targets.get(s, 0.0) - self.quantities.get(s, 0.0)) * prices[s]
                       for s in symbols)
        fee = notional * fee_bps / 10_000
        if fee >= self.equity:
            raise ValueError("trade fees exhaust account equity")
        self.equity -= fee
        self.fees_paid += fee
        self.traded_notional += notional
        self.quantities = {s: q for s, q in targets.items() if q != 0.0}
        self.marks = {s: prices[s] for s in self.quantities}
        return notional, fee
