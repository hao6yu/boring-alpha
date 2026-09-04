"""Dependency-free performance metrics."""

from __future__ import annotations

import math
import statistics

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult


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

    total_cost = sum(trade.cost for trade in result.trades)
    traded_notional = sum(trade.notional for trade in result.trades)
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
        "trade_count": len(result.trades),
        "traded_notional": traded_notional,
        "total_cost": total_cost,
    }
