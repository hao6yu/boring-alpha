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
class Order:
    """An intent to trade, priced at the moment the decision was made.

    `reference_price` is the decision-time price — for BA-001 the month-end
    close — not the price the order will fill at. The gap between the two is
    slippage, and recording it is what lets a paper fill be compared with a
    modelled one.

    `intended_notional` is sized at execution prices, not at `reference_price`,
    so a quantity must never be derived from their ratio.
    """

    date: date
    symbol: str
    side: str
    intended_notional: float
    reference_price: float


@dataclass(frozen=True, slots=True)
class Fill:
    """What actually happened to an order.

    Flat, and matched to its order by (date, symbol, side): a broker returns
    fills that know nothing about our objects, so the link is a key rather than
    a reference. `intended_notional` and `reference_price` are carried here too
    because they are what the trade ledger needs.
    """

    date: date
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float
    cost: float
    intended_notional: float
    reference_price: float


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    as_of: date
    target_weights: dict[str, float]
    asset_returns: dict[str, float]
    cash_return: float
    name: str
    # "Keep the current allocation." The engine treats a hold on an empty book
    # as a normal rebalance to `target_weights`, because there is nothing to
    # keep; otherwise it records the decision and places no orders.
    hold: bool = False


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
    fills: tuple[Fill, ...]
    decisions: tuple[SignalSnapshot, ...]
    warnings: tuple[str, ...] = ()
    contributions: dict[str, float] = field(default_factory=dict)
    excess_contributions: dict[str, float] = field(default_factory=dict)
    cash_interest: float = 0.0
    orders: tuple[Order, ...] = ()
