"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from boring_alpha.backtest import Backtester
from boring_alpha.config import AppConfig, load_config
from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.metrics import calculate_metrics
from boring_alpha.report import write_report
from boring_alpha.signals import CashAllocation, FixedAllocation, MultiAssetTrend


def _load_data(config: AppConfig):
    if config.data.source == "synthetic":
        assert config.data.start is not None and config.data.end is not None
        return generate_synthetic_market_data(
            config.strategy.symbols,
            config.data.start,
            config.data.end,
            seed=config.data.seed,
            annual_cash_rate=config.data.annual_cash_rate,
        )
    assert config.data.prices_path is not None and config.data.cash_path is not None
    return load_csv_market_data(config.data.prices_path, config.data.cash_path)


def _percentage(value: float) -> str:
    return f"{value * 100:8.2f}%"


def run_backtest(config_path: Path) -> int:
    config = load_config(config_path)
    data = _load_data(config)
    engine = Backtester(
        data,
        config.strategy.symbols,
        initial_cash=config.portfolio.initial_cash,
        cost_bps=config.execution.cost_bps,
        start=config.backtest.start,
        end=config.backtest.end,
    )
    strategy = engine.run(
        MultiAssetTrend(
            config.strategy.symbols,
            config.strategy.lookback_months,
            config.strategy.sleeve_weight,
        )
    )
    benchmark = engine.run(
        FixedAllocation(
            config.strategy.symbols,
            config.strategy.lookback_months,
            config.strategy.sleeve_weight,
        )
    )
    cash = engine.run(CashAllocation(config.strategy.symbols))
    strategy_metrics = calculate_metrics(strategy, data)
    benchmark_metrics = calculate_metrics(benchmark, data)
    cash_metrics = calculate_metrics(cash, data)
    run_id, run_dir = write_report(
        config,
        data,
        strategy,
        benchmark,
        cash,
        strategy_metrics,
        benchmark_metrics,
        cash_metrics,
    )

    print(f"BoringAlpha run {run_id}")
    print("SYNTHETIC DATA — OUTPUT HAS NO ECONOMIC MEANING" if config.data.source == "synthetic" else data.source)
    print(f"{'Metric':<24}{'Strategy':>14}{'Static':>14}{'Cash':>14}")
    print(f"{'Total return':<24}{_percentage(float(strategy_metrics['total_return'])):>14}{_percentage(float(benchmark_metrics['total_return'])):>14}{_percentage(float(cash_metrics['total_return'])):>14}")
    print(f"{'CAGR':<24}{_percentage(float(strategy_metrics['cagr'])):>14}{_percentage(float(benchmark_metrics['cagr'])):>14}{_percentage(float(cash_metrics['cagr'])):>14}")
    print(f"{'Volatility':<24}{_percentage(float(strategy_metrics['annualized_volatility'])):>14}{_percentage(float(benchmark_metrics['annualized_volatility'])):>14}{_percentage(float(cash_metrics['annualized_volatility'])):>14}")
    print(f"{'Max drawdown':<24}{_percentage(float(strategy_metrics['max_drawdown'])):>14}{_percentage(float(benchmark_metrics['max_drawdown'])):>14}{_percentage(float(cash_metrics['max_drawdown'])):>14}")
    print(f"{'Sharpe vs cash':<24}{float(strategy_metrics['sharpe_vs_cash']):>14.2f}{float(benchmark_metrics['sharpe_vs_cash']):>14.2f}{float(cash_metrics['sharpe_vs_cash']):>14.2f}")
    print(f"Artifacts: {run_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boring-alpha", description="No free lunch. No magic backtests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    backtest = subparsers.add_parser("backtest", help="run a configured backtest")
    backtest.add_argument("config", type=Path, help="path to a TOML configuration")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "backtest":
            raise SystemExit(run_backtest(args.config))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
