"""Core immutable domain records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Rebalancing schedules a static benchmark may declare. Shared vocabulary for
# configuration and the signal layer, defined once so the two cannot diverge.
REBALANCE_SCHEDULES: tuple[str, ...] = ("annual", "monthly")

# How a symbol's capital gains are taxed in the after-tax overlay. Shared by
# configuration validation and the tax package, defined once.
GAINS_CLASSES: tuple[str, ...] = ("standard", "collectibles", "commodity_pool")


def validate_horizon_inputs(horizons: object, warmup_months: object) -> tuple[int, ...]:
    """Canonical equal-vote horizons and the distinct common readiness window.

    A vote is a countable month horizon, not a number to coerce from a boolean,
    float or string. The common window remains in force when a vote is removed.
    """

    if not isinstance(horizons, (tuple, list)) or not horizons:
        raise ValueError("horizons must be a non-empty sequence of positive integers")
    if any(type(horizon) is not int or horizon <= 0 for horizon in horizons):
        raise ValueError("horizons must contain only positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must be unique")
    if type(warmup_months) is not int or warmup_months <= 0:
        raise ValueError("warmup_months must be a positive integer")
    if warmup_months < max(horizons):
        raise ValueError("warmup_months must be at least the largest active horizon")
    return tuple(sorted(horizons))


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
class HorizonEvidence:
    """One equal vote and its contribution to the final sleeve targets."""

    horizon_months: int
    anchor_date: date
    asset_returns: dict[str, float]
    cash_return: float
    votes: dict[str, bool]
    target_weights: dict[str, float]


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    as_of: date
    target_weights: dict[str, float]
    asset_returns: dict[str, float]
    cash_return: float | None
    name: str
    # "Keep the current allocation." The engine treats a hold on an empty book
    # as a normal rebalance to `target_weights`, because there is nothing to
    # keep; otherwise it records the decision and places no orders.
    hold: bool = False
    # An ensemble has no single return or cash hurdle. Its legacy asset_returns
    # is empty and cash_return is None; the comparisons live here instead.
    horizon_evidence: tuple[HorizonEvidence, ...] | None = None


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
