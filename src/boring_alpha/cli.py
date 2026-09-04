"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from boring_alpha.backtest import Backtester
from boring_alpha.config import DATASET_END, UNBOUNDED_PERIOD, AppConfig, load_config
from boring_alpha.data import load_market_data
from boring_alpha.evaluation import SealedRunError, check_evaluation_gates
from boring_alpha.metrics import calculate_metrics
from boring_alpha.report import ARTIFACT_SCHEMA, write_report
from boring_alpha.criteria import Verdict, classify
from boring_alpha.signals import CashAllocation, FixedAllocation, MultiAssetTrend
from boring_alpha.sweep import run_sweep, write_sweep_report

__all__ = ["SealedRunError", "check_evaluation_gates", "build_parser", "main", "run_backtest"]


def _banners(config: AppConfig) -> list[str]:
    """Everything a reader must not miss about what this run is worth.

    Printed above and below the metrics table, because the table is where a
    reader forms an impression that a footnote will not undo.
    """

    banners: list[str] = []
    if config.data.source == "synthetic":
        banners.append("SYNTHETIC DATA — OUTPUT HAS NO ECONOMIC MEANING")
    if not config.evaluation.is_evidence:
        banners.append(
            f"EXPLORATORY RUN — NOT EVIDENCE ABOUT {config.strategy.strategy_id} "
            "(unbounded window, no sealing)"
        )
    return banners


def _percentage(value: float) -> str:
    return f"{value * 100:8.2f}%"


def run_backtest(config_path: Path, unseal_reason: str | None = None) -> int:
    config = load_config(config_path)
    data = load_market_data(config, unseal_reason)
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
        unseal_reason=unseal_reason,
    )

    banners = _banners(config)
    print(f"BoringAlpha run {run_id}")
    for banner in banners:
        print(banner)
    if config.data.source != "synthetic":
        print(data.source)
    period = config.evaluation.period
    window = (
        "unbounded"
        if period == UNBOUNDED_PERIOD
        else f"{config.evaluation.start}..{config.evaluation.end or DATASET_END}"
    )
    print(f"Evaluation period: {period} ({window})")
    print(f"{'Metric':<24}{'Strategy':>14}{'Static':>14}{'Cash':>14}")
    print(f"{'Total return':<24}{_percentage(float(strategy_metrics['total_return'])):>14}{_percentage(float(benchmark_metrics['total_return'])):>14}{_percentage(float(cash_metrics['total_return'])):>14}")
    print(f"{'CAGR':<24}{_percentage(float(strategy_metrics['cagr'])):>14}{_percentage(float(benchmark_metrics['cagr'])):>14}{_percentage(float(cash_metrics['cagr'])):>14}")
    print(f"{'Volatility':<24}{_percentage(float(strategy_metrics['annualized_volatility'])):>14}{_percentage(float(benchmark_metrics['annualized_volatility'])):>14}{_percentage(float(cash_metrics['annualized_volatility'])):>14}")
    print(f"{'Max drawdown':<24}{_percentage(float(strategy_metrics['max_drawdown'])):>14}{_percentage(float(benchmark_metrics['max_drawdown'])):>14}{_percentage(float(cash_metrics['max_drawdown'])):>14}")
    print(f"{'Sharpe vs cash':<24}{float(strategy_metrics['sharpe_vs_cash']):>14.2f}{float(benchmark_metrics['sharpe_vs_cash']):>14.2f}{float(cash_metrics['sharpe_vs_cash']):>14.2f}")
    warnings = list(data.warnings) + [
        warning for result in (strategy, benchmark, cash) for warning in result.warnings
    ]
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
    if unseal_reason:
        print(f"SEALED RUN unsealed: {unseal_reason}")
        print(f"Record this run in the {config.strategy.strategy_id} charter change log.")
    for banner in banners:
        print(banner)
    print(f"Artifacts: {run_dir}")
    return 0


def run_sweep_command(config_path: Path, unseal_reason: str | None = None) -> int:
    config = load_config(config_path)
    data = load_market_data(config, unseal_reason)
    sweep = run_sweep(config, data)
    sweep_id, sweep_dir = write_sweep_report(config, data, sweep, unseal_reason=unseal_reason)

    banners = _banners(config)
    print(f"BoringAlpha sweep {sweep_id} ({config.evaluation.period} period)")
    for banner in banners:
        print(banner)
    for criterion in sweep.outcome.criteria:
        print(f"  {criterion.name} {'pass' if criterion.passed else 'FAIL'}: {criterion.detail}")
    print(f"All criteria passed for this period: {'yes' if sweep.outcome.passed else 'NO'}")
    print("A verdict needs both periods: boring-alpha classify <development> <validation>")
    for warning in list(data.warnings) + list(sweep.warnings):
        print(f"  - {warning}")
    if unseal_reason:
        print(f"SEALED SWEEP unsealed: {unseal_reason}")
        print(f"Record this sweep in the {config.strategy.strategy_id} charter change log.")
    for banner in banners:
        print(banner)
    print(f"Artifacts: {sweep_dir}")
    return 0


def _read_criteria(sweep_dir: Path, expected_period: str) -> dict:
    try:
        criteria = json.loads((sweep_dir / "criteria.json").read_text(encoding="utf-8"))
        period = criteria["evaluation_period"]
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"{sweep_dir} does not hold a readable sweep: {exc}") from exc
    if period != expected_period:
        raise ValueError(f"{sweep_dir} holds a {period} sweep, expected {expected_period}")
    return criteria


def run_classify(development_dir: Path, validation_dir: Path) -> int:
    development = _read_criteria(development_dir, "development")
    validation = _read_criteria(validation_dir, "validation")

    # A verdict combining two unrelated sweeps would be confidently wrong. The
    # inputs must agree on everything except the window they cover, and a field
    # that is merely absent proves nothing — so absence is refused too, rather
    # than skipped.
    for field, message in (
        ("artifact_schema", "different artifact schemas"),
        ("strategy_id", "different strategies"),
        ("strategy_spec_sha256", "different strategy definitions"),
        ("code_sha256", "different code revisions"),
    ):
        for label, criteria in (("development", development), ("validation", validation)):
            if field not in criteria:
                raise ValueError(
                    f"the {label} sweep records no {field}; it predates the checks that "
                    "make a verdict trustworthy. Re-run the sweep on current code."
                )
        if development[field] != validation[field]:
            raise ValueError(
                f"refusing to classify {message}: "
                f"{field} is {development[field]!r} in the development sweep and "
                f"{validation[field]!r} in the validation sweep"
            )
    if development["artifact_schema"] != ARTIFACT_SCHEMA:
        raise ValueError(
            f"these sweeps use artifact schema {development['artifact_schema']}, but this "
            f"code writes schema {ARTIFACT_SCHEMA}. Re-run them rather than comparing "
            "artifacts across schema versions."
        )
    verdict = classify(development["variants"], validation["variants"])

    print(f"BA-001 classification: {verdict.value.upper()}")
    for label, criteria in (("development", development), ("validation", validation)):
        print(f"\n{label}:")
        for criterion in criteria["criteria"]:
            print(
                f"  {criterion['name']} {'pass' if criterion['passed'] else 'FAIL'}: "
                f"{criterion['detail']}"
            )
    if verdict is Verdict.INCONCLUSIVE:
        print(
            "\nInconclusive is a real outcome, not a failure to decide. "
            "Record it in the charter rather than searching for a variant that advances."
        )
    print("\nWrite the decision under docs/reviews/ without changing the charter retroactively.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boring-alpha", description="No free lunch. No magic backtests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    backtest = subparsers.add_parser("backtest", help="run a configured backtest")
    backtest.add_argument("config", type=Path, help="path to a TOML configuration")
    backtest.add_argument(
        "--unseal",
        metavar="REASON",
        help="run a sealed evaluation period; the reason is recorded in the provenance log",
    )

    sweep = subparsers.add_parser(
        "sweep", help="run the charter's pre-registered grid for one period"
    )
    sweep.add_argument("config", type=Path, help="path to a TOML configuration")
    sweep.add_argument(
        "--unseal",
        metavar="REASON",
        help="run a sealed evaluation period; the reason is recorded in the provenance log",
    )

    classify_parser = subparsers.add_parser(
        "classify", help="classify a strategy from its development and validation sweeps"
    )
    classify_parser.add_argument("development", type=Path, help="development sweep directory")
    classify_parser.add_argument("validation", type=Path, help="validation sweep directory")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "backtest":
            raise SystemExit(run_backtest(args.config, unseal_reason=args.unseal))
        if args.command == "sweep":
            raise SystemExit(run_sweep_command(args.config, unseal_reason=args.unseal))
        if args.command == "classify":
            raise SystemExit(run_classify(args.development, args.validation))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
