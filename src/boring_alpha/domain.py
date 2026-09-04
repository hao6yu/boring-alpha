"""Core immutable domain records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class PriceBar:
    date: date
    symbol: str
    open: float
    close: float


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    as_of: date
    target_weights: dict[str, float]
    asset_returns: dict[str, float]
    cash_return: float
    name: str


@dataclass(frozen=True, slots=True)
class Trade:
    date: date
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float
    cost: float


@dataclass(frozen=True, slots=True)
class EquityPoint:
    date: date
    equity: float
    cash: float
    gross_exposure: float


@dataclass(frozen=True)
class BacktestResult:
    name: str
    initial_equity: float
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[Trade, ...]
    decisions: tuple[SignalSnapshot, ...]
    warnings: tuple[str, ...] = ()
    contributions: dict[str, float] = field(default_factory=dict)
    cash_interest: float = 0.0
