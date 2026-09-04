"""The pre-registered evaluation grid for one period.

The charter fixes what must be run: the 12-month rule, twice the base cost, the
neighbouring lookbacks, and the strategy without its largest-contributing
sleeve. Running them together, from one command, is what stops the stability
checks from becoming a menu of results to choose from after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path

from boring_alpha.backtest import Backtester
from boring_alpha.config import AppConfig
from boring_alpha.criteria import (
    BASE,
    DOUBLE_COST,
    DROP_TOP_SLEEVE,
    LOOKBACK_15,
    LOOKBACK_9,
    PeriodOutcome,
    evaluate_period,
)
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult
from boring_alpha.metrics import (
    calculate_metrics,
    excess_return_series,
    sharpe_difference_interval,
)
from boring_alpha.report import ARTIFACT_SCHEMA, json_text, write_once
from boring_alpha.signals import (
    CashAllocation,
    ExcludingSleeve,
    FixedAllocation,
    MultiAssetTrend,
    ScaledAllocation,
)

GRID = (BASE, DOUBLE_COST, LOOKBACK_9, LOOKBACK_15, DROP_TOP_SLEEVE)
BOOTSTRAP_SEED = 20260904


@dataclass(frozen=True)
class SweepResult:
    variants: dict[str, dict[str, dict[str, float]]]
    outcome: PeriodOutcome
    contributions: dict[str, float]
    clusters: dict[str, float]
    top_sleeve: str
    exposure_matched: dict[str, float]
    sharpe_interval: dict[str, float]
    warnings: tuple[str, ...] = ()
    grid: dict[str, str] = field(default_factory=dict)


def _engine(config: AppConfig, data: MarketData, cost_bps: float) -> Backtester:
    return Backtester(
        data,
        config.strategy.symbols,
        initial_cash=config.portfolio.initial_cash,
        cost_bps=cost_bps,
        start=config.backtest.start,
        end=config.backtest.end,
    )


def _pair(
    config: AppConfig,
    data: MarketData,
    *,
    lookback: int,
    cost_bps: float,
    exclude: str | None = None,
) -> tuple[BacktestResult, BacktestResult]:
    symbols, weight = config.strategy.symbols, config.strategy.sleeve_weight
    engine = _engine(config, data, cost_bps)
    policy = MultiAssetTrend(symbols, lookback, weight)
    strategy = engine.run(ExcludingSleeve(policy, exclude) if exclude else policy)
    # The benchmark is always the charter's full static allocation, including
    # for C5: the question is whether the strategy clears the bar without its
    # best sleeve, not whether a handicapped benchmark is easier to beat.
    static = engine.run(FixedAllocation(symbols, lookback, weight))
    return strategy, static


def run_sweep(config: AppConfig, data: MarketData) -> SweepResult:
    lookback = config.strategy.lookback_months
    cost = config.execution.cost_bps
    grid = {
        BASE: f"{lookback}-month lookback at {cost:g} bps (pre-registered)",
        DOUBLE_COST: f"{lookback}-month lookback at {2 * cost:g} bps",
        LOOKBACK_9: f"9-month lookback at {cost:g} bps",
        LOOKBACK_15: f"15-month lookback at {cost:g} bps",
        DROP_TOP_SLEEVE: f"{lookback}-month lookback at {cost:g} bps, top sleeve in cash",
    }

    base_strategy, base_static = _pair(config, data, lookback=lookback, cost_bps=cost)
    contributions = dict(base_strategy.contributions)
    top_sleeve = max(contributions, key=lambda symbol: contributions[symbol])

    runs = {
        BASE: (base_strategy, base_static),
        DOUBLE_COST: _pair(config, data, lookback=lookback, cost_bps=2.0 * cost),
        LOOKBACK_9: _pair(config, data, lookback=9, cost_bps=cost),
        LOOKBACK_15: _pair(config, data, lookback=15, cost_bps=cost),
        DROP_TOP_SLEEVE: _pair(config, data, lookback=lookback, cost_bps=cost, exclude=top_sleeve),
    }
    variants = {
        name: {
            "strategy": calculate_metrics(strategy, data),
            "static": calculate_metrics(static, data),
        }
        for name, (strategy, static) in runs.items()
    }

    base_metrics = variants[BASE]["strategy"]
    matched = _engine(config, data, cost).run(
        ScaledAllocation(
            config.strategy.symbols,
            lookback,
            config.strategy.sleeve_weight,
            float(base_metrics["average_gross_exposure"]),
        )
    )
    cash = _engine(config, data, cost).run(CashAllocation(config.strategy.symbols))

    clusters = {
        name: sum(contributions.get(symbol, 0.0) for symbol in symbols)
        for name, symbols in config.clusters.items()
    }
    warnings = list(base_strategy.warnings)
    covered = {symbol for symbols in config.clusters.values() for symbol in symbols}
    uncovered = sorted(set(config.strategy.symbols) - covered)
    if config.clusters and uncovered:
        warnings.append(f"sleeves outside every cluster: {', '.join(uncovered)}")

    return SweepResult(
        variants=variants,
        outcome=evaluate_period(variants),
        contributions=contributions,
        clusters=clusters,
        top_sleeve=top_sleeve,
        exposure_matched=calculate_metrics(matched, data),
        sharpe_interval=sharpe_difference_interval(
            excess_return_series(base_strategy, data),
            excess_return_series(base_static, data),
            seed=BOOTSTRAP_SEED,
        ),
        warnings=tuple(warnings) + tuple(cash.warnings[:0]),
        grid=grid,
    )


def _summary(config: AppConfig, sweep: SweepResult) -> str:
    evaluation = config.evaluation
    lines = [
        f"# {config.strategy.strategy_id} sweep — {evaluation.period} period",
        "",
        f"Window: {config.backtest.start} to {config.backtest.end}. "
        f"Base cost: {config.execution.cost_bps:g} bps per side.",
        "",
        "## Pre-registered result",
        "",
        f"The {config.strategy.lookback_months}-month rule is the hypothesis under test. "
        "Everything below it is a stability check on this result, not a menu: "
        "the charter forbids selecting a lookback or a cost after seeing outcomes.",
        "",
        "| Metric | Strategy | Static | Exposure-matched |",
        "|---|---:|---:|---:|",
    ]
    base = sweep.variants[BASE]
    for label, key in (
        ("Total return", "total_return"),
        ("CAGR", "cagr"),
        ("Volatility", "annualized_volatility"),
        ("Max drawdown", "max_drawdown"),
        ("Sharpe vs cash", "sharpe_vs_cash"),
        ("Worst month", "worst_month"),
        ("Time in market", "time_in_market"),
        ("Avg gross exposure", "average_gross_exposure"),
        ("One-way turnover", "one_way_turnover"),
        ("Cost drag (bps/yr)", "cost_drag_bps"),
    ):
        lines.append(
            f"| {label} | {float(base['strategy'][key]):.4f} | "
            f"{float(base['static'][key]):.4f} | {float(sweep.exposure_matched[key]):.4f} |"
        )

    interval = sweep.sharpe_interval
    lines += [
        "",
        f"Sharpe difference against static: {interval['point']:+.3f} "
        f"({interval['confidence']:.0%} interval {interval['low']:+.3f} to {interval['high']:+.3f}, "
        f"{int(interval['resamples'])} block resamples, seed {int(interval['seed'])}).",
    ]
    if interval["low"] <= 0.0 <= interval["high"]:
        lines.append(
            "The interval contains zero: this sample cannot distinguish the two on "
            "risk-adjusted return."
        )
    lines += ["", "## Advancement criteria", "", "| Criterion | Passed | Detail |", "|---|---|---|"]
    for criterion in sweep.outcome.criteria:
        lines.append(
            f"| {criterion.name}: {criterion.description} | "
            f"{'yes' if criterion.passed else 'NO'} | {criterion.detail} |"
        )
    lines += [
        "",
        f"All criteria passed for this period: {'yes' if sweep.outcome.passed else 'NO'}. "
        "A verdict needs both the development and validation periods; run `classify`.",
        "",
        "## Stability checks",
        "",
        "| Variant | Description | Strategy drawdown | Strategy Sharpe |",
        "|---|---|---:|---:|",
    ]
    for name in GRID:
        metrics = sweep.variants[name]["strategy"]
        lines.append(
            f"| {name} | {sweep.grid[name]} | {float(metrics['max_drawdown']):.4f} | "
            f"{float(metrics['sharpe_vs_cash']):.4f} |"
        )

    lines += ["", "## Attribution", "", "| Sleeve | Contribution |", "|---|---:|"]
    for symbol, value in sorted(sweep.contributions.items(), key=lambda item: -item[1]):
        marker = " (largest)" if symbol == sweep.top_sleeve else ""
        lines.append(f"| {symbol}{marker} | {value:.2f} |")
    if sweep.clusters:
        lines += ["", "| Cluster | Contribution |", "|---|---:|"]
        for name, value in sorted(sweep.clusters.items(), key=lambda item: -item[1]):
            lines.append(f"| {name} | {value:.2f} |")
    if sweep.warnings:
        lines += ["", "## Warnings", ""] + [f"- {warning}" for warning in sweep.warnings]
    return "\n".join(lines) + "\n"


def write_sweep_report(
    config: AppConfig, data: MarketData, sweep: SweepResult
) -> tuple[str, Path]:
    from boring_alpha.report import code_fingerprint

    evaluation = config.evaluation
    identity = ":".join(
        (
            hashlib.sha256(config.raw_bytes).hexdigest(),
            data.fingerprint(),
            code_fingerprint(),
            f"{evaluation.period}:{evaluation.start}:{evaluation.end}",
            "|".join(GRID),
        )
    )
    sweep_id = hashlib.sha256(identity.encode("ascii")).hexdigest()[:16]
    sweep_dir = config.report.output_dir / config.strategy.strategy_id / "sweeps" / sweep_id
    sweep_dir.mkdir(parents=True, exist_ok=True)

    write_once(
        sweep_dir / "manifest.json",
        json_text(
            {
                "artifact_schema": ARTIFACT_SCHEMA,
                "sweep_id": sweep_id,
                "strategy_id": config.strategy.strategy_id,
                "evaluation_period": evaluation.period,
                "evaluation_start": evaluation.start,
                "evaluation_end": evaluation.end,
                "backtest_start": config.backtest.start,
                "backtest_end": config.backtest.end,
                "grid": sweep.grid,
                "config_toml": config.raw_bytes.decode("utf-8"),
                "data_sha256": data.fingerprint(),
                "data_source": data.source,
                "warnings": list(sweep.warnings) + list(data.warnings),
            }
        ),
    )
    write_once(
        sweep_dir / "criteria.json",
        json_text(
            {
                "evaluation_period": evaluation.period,
                "passed": sweep.outcome.passed,
                "criteria": [
                    {
                        "name": criterion.name,
                        "description": criterion.description,
                        "passed": criterion.passed,
                        "detail": criterion.detail,
                    }
                    for criterion in sweep.outcome.criteria
                ],
                "variants": sweep.variants,
                "top_sleeve": sweep.top_sleeve,
                "contributions": sweep.contributions,
                "clusters": sweep.clusters,
                "exposure_matched": sweep.exposure_matched,
                "sharpe_interval": sweep.sharpe_interval,
            }
        ),
    )
    write_once(sweep_dir / "summary.md", _summary(config, sweep))
    return sweep_id, sweep_dir
