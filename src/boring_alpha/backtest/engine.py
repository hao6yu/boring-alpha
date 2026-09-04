"""Daily mark-to-market engine with next-session execution."""

from __future__ import annotations

from bisect import bisect_left
from datetime import date
from typing import Protocol

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, Fill, Order, SignalSnapshot
from boring_alpha.execution import CostModel, execute
from boring_alpha.portfolio.account import Portfolio


class SignalPolicy(Protocol):
    """A policy must echo back the `as_of` date it was handed as the returned
    snapshot's `as_of`: the engine reads the reference price at
    `pending.as_of`, not at the date it happened to call `snapshot` from."""

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
        self.cost_model = CostModel(cost_bps)
        self.start = start
        self.end = end
        missing = set(symbols) - set(data.symbol_dates)
        if missing:
            raise ValueError(f"dataset is missing symbols: {sorted(missing)}")
        self.calendar = data.shared_sessions(symbols)
        if not self.calendar:
            raise ValueError("no session has bars for every configured symbol")
        # Sleeves may begin on different dates. From the first shared session
        # onward every sleeve must be present; a hole after that is a data
        # error, never an implicit move to cash.
        data.require_complete_calendar(symbols, self.calendar[0], end)
        sessions = [day for day in self.calendar if start <= day <= end]
        if not sessions:
            raise ValueError("no market sessions fall inside the backtest period")
        # The first session in the window must open a month so that the pending
        # signal it executes is the preceding month-end's. A calendar that
        # itself begins mid-month cannot be checked and has no pending signal.
        first = sessions[0]
        index = bisect_left(self.calendar, first)
        if index > 0:
            previous = self.calendar[index - 1]
            if (previous.year, previous.month) == (first.year, first.month):
                raise ValueError(
                    "backtest.start must select the first session of a month; "
                    f"{first} follows {previous} in the same month "
                    "(use the first calendar day of the month)"
                )

    def run(self, policy: SignalPolicy) -> BacktestResult:
        portfolio = Portfolio(self.initial_cash, self.symbols)
        fills: list[Fill] = []
        orders: list[Order] = []
        decisions: list[SignalSnapshot] = []
        curve: list[EquityPoint] = []
        warnings: list[str] = []
        # Attribution is accumulated as the run proceeds rather than
        # reconstructed afterwards, so it can account for every price change and
        # every cost exactly once.
        contributions = {symbol: 0.0 for symbol in self.symbols}
        # The charter defines a sleeve's contribution as its share of the
        # strategy's excess return over cash, so capital parked in a sleeve is
        # charged the cash it forwent while it sat there.
        cash_forgone = {symbol: 0.0 for symbol in self.symbols}
        cash_interest = 0.0
        previous_closes: dict[str, float] = {}
        pending: SignalSnapshot | None = None
        prestart_warning: str | None = None
        started = False
        month_ends = month_end_dates(self.calendar)

        def no_signal(day: date) -> str:
            return f"{policy.name}: no signal at month-end {day.isoformat()} (insufficient history)"

        for day in self.calendar:
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
                session_factor = self.data.cash_factors[day]
                before = portfolio.cash
                portfolio.accrue_cash(session_factor)
                cash_interest += portfolio.cash - before
            else:
                # The portfolio opens at the first session; nothing was held
                # overnight into it, so no cash was earned or forgone.
                session_factor = 1.0
                started = True

            # Held from the prior close to today's open, then at whatever the
            # rebalance leaves, through to today's close.
            held_overnight = dict(portfolio.positions)

            if pending is not None:
                prices = {
                    symbol: self.data.bar(day, symbol).open for symbol in self.symbols
                }
                references = {
                    symbol: self.data.bar(pending.as_of, symbol).close
                    for symbol in self.symbols
                }
                new_orders = portfolio.plan_rebalance(
                    prices, pending.target_weights, references, day
                )
                new_fills = execute(new_orders, prices, portfolio.cash, self.cost_model)
                portfolio.apply(new_fills)
                for fill in new_fills:
                    contributions[fill.symbol] -= fill.cost
                orders.extend(new_orders)
                fills.extend(new_fills)
                decisions.append(pending)
                pending = None

            for symbol in self.symbols:
                bar = self.data.bar(day, symbol)
                previous_close = previous_closes.get(symbol)
                if previous_close is not None:
                    contributions[symbol] += held_overnight[symbol] * (bar.open - previous_close)
                    cash_forgone[symbol] += (
                        held_overnight[symbol] * previous_close * (session_factor - 1.0)
                    )
                contributions[symbol] += portfolio.positions[symbol] * (bar.close - bar.open)
                previous_closes[symbol] = bar.close

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
            fills=tuple(fills),
            orders=tuple(orders),
            decisions=tuple(decisions),
            warnings=tuple(warnings),
            contributions=contributions,
            excess_contributions={
                symbol: contributions[symbol] - cash_forgone[symbol] for symbol in self.symbols
            },
            cash_interest=cash_interest,
        )
