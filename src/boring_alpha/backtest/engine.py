"""Daily mark-to-market engine with next-session execution."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, SignalSnapshot, Trade
from boring_alpha.portfolio.account import Portfolio


class SignalPolicy(Protocol):
    name: str

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None: ...


def month_end_dates(dates: tuple[date, ...]) -> set[date]:
    result: set[date] = set()
    for index, day in enumerate(dates):
        if index == len(dates) - 1 or dates[index + 1].month != day.month:
            result.add(day)
    return result


class Backtester:
    def __init__(
        self,
        data: MarketData,
        symbols: tuple[str, ...],
        *,
        initial_cash: float,
        cost_bps: float,
        start: date,
        end: date,
    ) -> None:
        self.data = data
        self.symbols = symbols
        self.initial_cash = initial_cash
        self.cost_bps = cost_bps
        self.start = start
        self.end = end
        data.require_complete_calendar(symbols, data.dates[0], end)
        if not any(start <= day <= end for day in data.dates):
            raise ValueError("no market sessions fall inside the backtest period")

    def run(self, policy: SignalPolicy) -> BacktestResult:
        portfolio = Portfolio(self.initial_cash, self.symbols)
        trades: list[Trade] = []
        decisions: list[SignalSnapshot] = []
        curve: list[EquityPoint] = []
        pending: SignalSnapshot | None = None
        started = False
        month_ends = month_end_dates(self.data.dates)

        for day in self.data.dates:
            if day > self.end:
                break

            if day < self.start:
                if day in month_ends:
                    pending = policy.snapshot(self.data, day)
                continue

            if started:
                portfolio.accrue_cash(self.data.cash_factors[day])
            else:
                started = True

            if pending is not None:
                trades.extend(
                    portfolio.rebalance(
                        self.data,
                        day,
                        pending.target_weights,
                        self.cost_bps,
                    )
                )
                decisions.append(pending)
                pending = None

            equity, exposure = portfolio.equity_at_close(self.data, day)
            curve.append(EquityPoint(day, equity, portfolio.cash, exposure))

            if day in month_ends:
                pending = policy.snapshot(self.data, day)

        return BacktestResult(
            name=policy.name,
            initial_equity=self.initial_cash,
            equity_curve=tuple(curve),
            trades=tuple(trades),
            decisions=tuple(decisions),
        )
