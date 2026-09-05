"""BA-001 trend signal and its static benchmark."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import math

from boring_alpha.data.market import MarketData
from boring_alpha.domain import (
    HorizonEvidence, REBALANCE_SCHEDULES, SignalSnapshot, validate_horizon_inputs,
)


def month_offset(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    year, month_zero = divmod(total, 12)
    return year, month_zero + 1


def anchor_month_end(
    data: MarketData, symbols: tuple[str, ...], as_of: date, lookback_months: int
) -> date | None:
    """Final shared session of the calendar month `lookback_months` before `as_of`."""

    year, month = month_offset(as_of.year, as_of.month, -lookback_months)
    return data.last_shared_session_in_month(symbols, year, month)


class MultiAssetTrend:
    def __init__(
        self, symbols: tuple[str, ...], lookback_months: int, sleeve_weight: float
    ) -> None:
        self.symbols = symbols
        self.lookback_months = lookback_months
        self.sleeve_weight = sleeve_weight
        self.name = "BA-001 Multi-Asset Trend"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        anchor = anchor_month_end(data, self.symbols, as_of, self.lookback_months)
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


class MultiHorizonTrend:
    """Equal asset-versus-cash votes with a separate common readiness window.

    Inactive votes keep their capital in cash; weights are never renormalized
    across active assets. Removing a horizon changes the vote denominator, not
    the common readiness window or any remaining horizon's cash anchor.
    """

    def __init__(
        self,
        symbols: tuple[str, ...],
        horizons: tuple[int, ...],
        sleeve_weight: float,
        warmup_months: int = 15,
    ) -> None:
        self.horizons = validate_horizon_inputs(horizons, warmup_months)
        if not symbols or any(not isinstance(symbol, str) or not symbol for symbol in symbols):
            raise ValueError("symbols must be non-empty strings")
        if len(set(symbols)) != len(symbols):
            raise ValueError("symbols must be unique")
        if isinstance(sleeve_weight, bool) or not isinstance(sleeve_weight, (int, float)):
            raise ValueError("sleeve_weight must be a finite number")
        if not math.isfinite(sleeve_weight) or not 0 < sleeve_weight <= 1:
            raise ValueError("sleeve_weight must be finite and in (0, 1]")
        if len(symbols) * sleeve_weight > 1 + 1e-12:
            raise ValueError("configured sleeves exceed 100% gross exposure")
        self.symbols = tuple(symbols)
        self.sleeve_weight = sleeve_weight
        self.warmup_months = warmup_months
        self.lookback_months = warmup_months
        label = "/".join(str(horizon) for horizon in self.horizons)
        self.name = f"BA-002 Multi-Horizon Trend ({label} months)"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        if anchor_month_end(data, self.symbols, as_of, self.warmup_months) is None:
            return None
        evidence: list[HorizonEvidence] = []
        targets = {symbol: 0.0 for symbol in self.symbols}
        vote_weight = self.sleeve_weight / len(self.horizons)
        for horizon in self.horizons:
            anchor = anchor_month_end(data, self.symbols, as_of, horizon)
            if anchor is None:
                return None
            cash_return = data.cash_index[as_of] / data.cash_index[anchor] - 1.0
            returns = {
                symbol: data.bar(as_of, symbol).close / data.bar(anchor, symbol).close - 1.0
                for symbol in self.symbols
            }
            votes = {symbol: returns[symbol] > cash_return for symbol in self.symbols}
            contributions = {
                symbol: vote_weight if votes[symbol] else 0.0 for symbol in self.symbols
            }
            for symbol in self.symbols:
                targets[symbol] += contributions[symbol]
            evidence.append(HorizonEvidence(
                horizon_months=horizon,
                anchor_date=anchor,
                asset_returns=returns,
                cash_return=cash_return,
                votes=votes,
                target_weights=contributions,
            ))
        return SignalSnapshot(
            as_of=as_of,
            target_weights=targets,
            asset_returns={},
            cash_return=None,
            name=self.name,
            horizon_evidence=tuple(evidence),
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
        anchor = anchor_month_end(data, self.symbols, as_of, self.lookback_months)
        if anchor is None:
            return None
        return SignalSnapshot(
            as_of=as_of,
            target_weights={symbol: self.sleeve_weight for symbol in self.symbols},
            asset_returns={},
            cash_return=data.cash_index[as_of] / data.cash_index[anchor] - 1.0,
            name=self.name,
        )


class ScaledAllocation(FixedAllocation):
    """Static weights scaled to a target gross exposure, remainder in cash.

    Comparing a half-invested strategy with a fully invested benchmark flatters
    the strategy on drawdown and penalises it on return. This benchmark removes
    that difference so the comparison is about selection, not exposure.
    """

    def __init__(
        self,
        symbols: tuple[str, ...],
        lookback_months: int,
        sleeve_weight: float,
        exposure: float,
    ) -> None:
        super().__init__(symbols, lookback_months, sleeve_weight)
        self.exposure = min(max(exposure, 0.0), 1.0)
        self.name = f"Exposure-Matched Benchmark ({self.exposure:.0%})"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        snapshot = super().snapshot(data, as_of)
        if snapshot is None:
            return None
        gross = sum(snapshot.target_weights.values())
        scale = self.exposure / gross if gross > 0.0 else 0.0
        return replace(
            snapshot,
            target_weights={
                symbol: weight * scale for symbol, weight in snapshot.target_weights.items()
            },
            name=self.name,
        )


class TargetExposureAllocation(ScaledAllocation):
    """Static weights at a target exposure fixed in advance, on a declared schedule.

    Unlike the exposure-matched diagnostic, nothing about a strategy's realized
    exposure feeds this: the number and the schedule come from the charter. On
    an annual schedule every month-end but December is a hold, so the
    allocation drifts between Januaries the way a passive holder's would. The
    engine treats a hold on an empty book as a normal rebalance, so a run that
    starts mid-year still enters on its first session.
    """

    def __init__(
        self,
        symbols: tuple[str, ...],
        lookback_months: int,
        sleeve_weight: float,
        exposure: float,
        rebalance: str,
    ) -> None:
        if rebalance not in REBALANCE_SCHEDULES:
            raise ValueError(
                f"rebalance must be one of {', '.join(REBALANCE_SCHEDULES)}, got {rebalance!r}"
            )
        super().__init__(symbols, lookback_months, sleeve_weight, exposure)
        self.rebalance = rebalance
        self.name = f"Target-Exposure Benchmark ({self.exposure:.0%}, {rebalance})"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        snapshot = super().snapshot(data, as_of)
        if snapshot is None:
            return None
        hold = self.rebalance == "annual" and as_of.month != 12
        return replace(snapshot, name=self.name, hold=hold)


class ExcludingSleeve:
    """A policy with one sleeve held permanently in cash, for C5."""

    def __init__(self, policy, symbol: str) -> None:
        self.policy = policy
        self.symbol = symbol
        self.name = f"{policy.name} without {symbol}"

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None:
        snapshot = self.policy.snapshot(data, as_of)
        if snapshot is None:
            return None
        return replace(
            snapshot,
            target_weights={**snapshot.target_weights, self.symbol: 0.0},
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
