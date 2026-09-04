"""BA-001 trend signal and its static benchmark."""

from __future__ import annotations

import calendar
from datetime import date

from boring_alpha.data.market import MarketData
from boring_alpha.domain import SignalSnapshot


def subtract_months(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) - months
    year, month_zero = divmod(total, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class MultiAssetTrend:
    def __init__(
        self, symbols: tuple[str, ...], lookback_months: int, sleeve_weight: float
    ) -> None:
        self.symbols = symbols
        self.lookback_months = lookback_months
        self.sleeve_weight = sleeve_weight
        self.name = "BA-001 Multi-Asset Trend"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        anchor_target = subtract_months(as_of, self.lookback_months)
        anchor = data.shared_date_on_or_before(self.symbols, anchor_target)
        if anchor is None:
            return None

        cash_return = data.cash_index[as_of] / data.cash_index[anchor] - 1.0
        asset_returns = {
            symbol: data.bar(as_of, symbol).close / data.bar(anchor, symbol).close - 1.0
            for symbol in self.symbols
        }
        target_weights = {
            symbol: self.sleeve_weight if asset_returns[symbol] > cash_return else 0.0
            for symbol in self.symbols
        }
        return SignalSnapshot(
            as_of=as_of,
            target_weights=target_weights,
            asset_returns=asset_returns,
            cash_return=cash_return,
            name=self.name,
        )


class FixedAllocation:
    """Static benchmark that begins after the same lookback warm-up."""

    def __init__(
        self, symbols: tuple[str, ...], lookback_months: int, sleeve_weight: float
    ) -> None:
        self.symbols = symbols
        self.lookback_months = lookback_months
        self.sleeve_weight = sleeve_weight
        self.name = "Static Equal-Weight Benchmark"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        anchor_target = subtract_months(as_of, self.lookback_months)
        anchor = data.shared_date_on_or_before(self.symbols, anchor_target)
        if anchor is None:
            return None
        return SignalSnapshot(
            as_of=as_of,
            target_weights={symbol: self.sleeve_weight for symbol in self.symbols},
            asset_returns={},
            cash_return=data.cash_index[as_of] / data.cash_index[anchor] - 1.0,
            name=self.name,
        )


class CashAllocation:
    """Zero-risk-asset allocation using the engine's supplied cash factors."""

    def __init__(self, symbols: tuple[str, ...]) -> None:
        self.symbols = symbols
        self.name = "Cash Benchmark"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot:
        return SignalSnapshot(
            as_of=as_of,
            target_weights={symbol: 0.0 for symbol in self.symbols},
            asset_returns={},
            cash_return=0.0,
            name=self.name,
        )
