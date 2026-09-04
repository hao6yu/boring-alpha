"""Dependency-free performance metrics."""

from __future__ import annotations

import math
import statistics

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult


def excess_return_series(result: BacktestResult, data: MarketData) -> list[float]:
    """Daily returns net of the session cash rate, aligned to the equity curve."""

    curve = result.equity_curve
    if not curve:
        return []
    series = [curve[0].equity / result.initial_equity - 1.0]
    series.extend(
        curve[index].equity / curve[index - 1].equity
        - 1.0
        - (data.cash_factors[curve[index].date] - 1.0)
        for index in range(1, len(curve))
    )
    return series


def calculate_metrics(result: BacktestResult, data: MarketData) -> dict[str, float | int]:
    curve = result.equity_curve
    if len(curve) < 2:
        raise ValueError("at least two equity observations are required")

    start_equity = result.initial_equity
    end_equity = curve[-1].equity
    total_return = end_equity / start_equity - 1.0
    elapsed_days = (curve[-1].date - curve[0].date).days + 1
    cagr = (end_equity / start_equity) ** (365.2425 / elapsed_days) - 1.0

    daily_returns = [curve[0].equity / start_equity - 1.0] + [
        curve[index].equity / curve[index - 1].equity - 1.0
        for index in range(1, len(curve))
    ]
    # The portfolio starts at the first session's open, so it does not earn the
    # overnight cash factor on that initial day.
    excess_returns = [daily_returns[0]] + [
        daily_returns[index] - (data.cash_factors[curve[index].date] - 1.0)
        for index in range(1, len(curve))
    ]
    volatility = statistics.stdev(daily_returns) * math.sqrt(252.0)
    excess_std = statistics.stdev(excess_returns)
    sharpe = (
        statistics.mean(excess_returns) / excess_std * math.sqrt(252.0)
        if excess_std > 0.0
        else 0.0
    )

    peak = start_equity
    max_drawdown = 0.0
    for point in curve:
        peak = max(peak, point.equity)
        max_drawdown = min(max_drawdown, point.equity / peak - 1.0)

    # Calendar-month returns, the first measured from the opening equity.
    month_end_equity: dict[tuple[int, int], float] = {}
    for point in curve:
        month_end_equity[(point.date.year, point.date.month)] = point.equity
    previous_equity = start_equity
    monthly_returns: list[float] = []
    for month in sorted(month_end_equity):
        monthly_returns.append(month_end_equity[month] / previous_equity - 1.0)
        previous_equity = month_end_equity[month]
    worst_month = min(monthly_returns) if monthly_returns else 0.0

    time_in_market = sum(1 for point in curve if point.gross_exposure > 0.0) / len(curve)
    average_equity = statistics.mean(point.equity for point in curve)
    years = max((curve[-1].date - curve[0].date).days, 1) / 365.2425

    total_cost = sum(fill.cost for fill in result.fills)
    traded_notional = sum(fill.notional for fill in result.fills)
    average_exposure = statistics.mean(
        point.gross_exposure / point.equity for point in curve if point.equity > 0.0
    )
    return {
        "start_equity": start_equity,
        "end_equity": end_equity,
        "total_return": total_return,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe_vs_cash": sharpe,
        "max_drawdown": max_drawdown,
        "average_gross_exposure": average_exposure,
        "time_in_market": time_in_market,
        "worst_month": worst_month,
        # traded_notional sums both sides; one-way turnover counts one.
        "one_way_turnover": traded_notional / 2.0 / average_equity / years,
        "cost_drag_bps": total_cost / average_equity / years * 10_000.0,
        "trade_count": len(result.fills),
        "traded_notional": traded_notional,
        "total_cost": total_cost,
    }
