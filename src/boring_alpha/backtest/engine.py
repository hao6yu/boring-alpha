"""Daily mark-to-market engine with next-session execution."""

from __future__ import annotations

from bisect import bisect_left
from datetime import date
from typing import Protocol

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, SignalSnapshot, Trade
from boring_alpha.portfolio.account import Portfolio


class SignalPolicy(Protocol):
    name: str

    def snapshot(self, data: MarketData, as_of: date) -> SignalSnapshot | None: ...


def month_end_dates(dates: tuple[date, ...]) -> set[date]:
    """Sessions followed by a session in a different month.

    The final date of a dataset is never a month-end: the data cannot show
    whether its month actually ended, and a decision there could never execute.
    """

    result: set[date] = set()
    for index in range(len(dates) - 1):
        day, following = dates[index], dates[index + 1]
        if (following.year, following.month) != (day.year, day.month):
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
        sessions = [day for day in data.dates if start <= day <= end]
        if not sessions:
            raise ValueError("no market sessions fall inside the backtest period")
        # The first session in the window must open a month so that the pending
        # signal it executes is the preceding month-end's. A dataset that itself
        # begins mid-month cannot be checked and simply has no pending signal.
        first = sessions[0]
        index = bisect_left(data.dates, first)
        if index > 0:
            previous = data.dates[index - 1]
            if (previous.year, previous.month) == (first.year, first.month):
                raise ValueError(
                    "backtest.start must select the first session of a month; "
                    f"{first} follows {previous} in the same month "
                    "(use the first calendar day of the month)"
                )

    def run(self, policy: SignalPolicy) -> BacktestResult:
        portfolio = Portfolio(self.initial_cash, self.symbols)
        trades: list[Trade] = []
        decisions: list[SignalSnapshot] = []
        curve: list[EquityPoint] = []
        warnings: list[str] = []
        pending: SignalSnapshot | None = None
        prestart_warning: str | None = None
        started = False
        month_ends = month_end_dates(self.data.dates)

        def no_signal(day: date) -> str:
            return f"{policy.name}: no signal at month-end {day.isoformat()} (insufficient history)"

        for day in self.data.dates:
            if day > self.end:
                break

            if day < self.start:
                if day in month_ends:
                    pending = policy.snapshot(self.data, day)
                    prestart_warning = no_signal(day) if pending is None else None
                continue

            if prestart_warning is not None:
                warnings.append(prestart_warning)
                prestart_warning = None

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
                if pending is None:
                    warnings.append(no_signal(day))

        return BacktestResult(
            name=policy.name,
            initial_equity=self.initial_cash,
            equity_curve=tuple(curve),
            trades=tuple(trades),
            decisions=tuple(decisions),
            warnings=tuple(warnings),
        )
