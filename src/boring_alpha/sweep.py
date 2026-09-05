"""The pre-registered evaluation grid for one period.

The charter fixes what must be run: the 12-month rule, twice the base cost, the
neighbouring lookbacks, and the strategy without its largest-contributing
sleeve. Running them together, from one command, is what stops the stability
checks from becoming a menu of results to choose from after the fact. When a
configuration carries a [tax] table, every run is also scored after tax under
the fixed scenario grid and the result is written beside the criteria.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import gzip
import hashlib
import io
import json
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
)
from boring_alpha.data.distributions import FINGERPRINT_VERSION, DistributionTable, load_distributions
from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult
from boring_alpha.metrics import (
    calculate_metrics,
    excess_return_series,
    sharpe_difference_interval,
)
from boring_alpha.report import (
    ARTIFACT_SCHEMA,
    append_provenance,
    code_fingerprint,
    decisions_json,
    equity_csv,
    json_text,
    run_warnings,
    trades_csv,
    write_once,
    write_once_bytes,
)
from boring_alpha.profiles import VariantSpec, profile_for
from boring_alpha.signals import CashAllocation, FixedAllocation, ScaledAllocation
from boring_alpha.tax import OVERLAY_VERSION, policy_sha256, run_scenarios

# BA-001's variant order; kept for callers that iterate it.
GRID = (BASE, DOUBLE_COST, LOOKBACK_9, LOOKBACK_15, DROP_TOP_SLEEVE)
BOOTSTRAP_SEED = 20260904


@dataclass(frozen=True)
class SweepResult:
    variants: dict[str, dict[str, dict[str, float]]]
    outcome: PeriodOutcome
    contributions: dict[str, float]
    excess_contributions: dict[str, float]
    clusters: dict[str, float]
    top_sleeve: str
    exposure_matched: dict[str, float]
    cash: dict[str, float]
    sharpe_interval: dict[str, float]
    warnings: tuple[str, ...] = ()
    grid: dict[str, str] = field(default_factory=dict)
    runs: dict[str, tuple] = field(default_factory=dict)
    static_full: dict[str, float] | None = None
    """Metrics of the fully invested monthly static allocation when a
    target-exposure benchmark gates; None when full static is the benchmark."""
    tax: dict | None = None
    """Every run under every scenario, plus the policy and distributions identity;
    None when the configuration has no [tax] table."""
    distributions: DistributionTable | None = None
    distributions_provenance: dict | None = None


def _engine(config: AppConfig, data: MarketData, cost_bps: float) -> Backtester:
    return Backtester(
        data,
        config.strategy.symbols,
        initial_cash=config.portfolio.initial_cash,
        cost_bps=cost_bps,
        start=config.backtest.start,
        end=config.backtest.end,
    )


TAX_BASE_SCENARIO = "hifo-deferral-base"


def _distributions_for(config: AppConfig, data: MarketData) -> tuple[DistributionTable, dict, dict]:
    """The distributions table a tax run uses, truncated like the market data,
    and the manifest block that travels into the sweep so it is self-contained."""

    assert config.tax is not None
    path = config.tax.distributions_path
    manifest_path = path.parent / "manifest.json"
    if config.data.prices_path is not None and path.parent != config.data.prices_path.parent:
        raise ValueError(
            f"tax.distributions_path {path} must sit in the same snapshot directory as "
            f"data.prices_path {config.data.prices_path}: distributions and prices must "
            "come from one fetch"
        )
    if not manifest_path.is_file():
        raise ValueError(f"no manifest.json beside {path.name}; a v2 snapshot is required for tax")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    table = load_distributions(path, manifest_path=manifest_path).through(data.dates[-1])
    table.require_coverage(data, config.strategy.symbols)
    block = {
        "methodology": table.methodology,
        "splits": table.splits,
        "sha256": table.sha256,
        "csv_sha256": table.csv_sha256,
        "fingerprint_version": FINGERPRINT_VERSION,
    }
    provenance = {
        "source_sha256": table.source_sha256,
        "source_path": str(path),
        "created_at": manifest.get("created_at"),
        "methodology": manifest.get("methodology"),
    }
    return table, block, provenance


def run_sweep(config: AppConfig, data: MarketData) -> SweepResult:
    profile = profile_for(config.strategy.strategy_id)
    specs = profile.grid(config)
    if BASE not in specs:
        raise ValueError(f"{profile.strategy_id}'s grid defines no '{BASE}' variant")
    grid = {name: spec.description for name, spec in specs.items()}
    cost = config.execution.cost_bps
    lookback = config.strategy.lookback_months

    def run_variant(
        spec: VariantSpec, top_sleeve: str | None
    ) -> tuple[BacktestResult, BacktestResult]:
        engine = _engine(config, data, spec.cost_bps)
        strategy = engine.run(spec.strategy(config, top_sleeve))
        # Every variant is judged against the gating benchmark, including the
        # one without its best sleeve: the question is whether the strategy
        # clears the bar handicapped, not whether a handicapped benchmark is
        # easier to beat.
        benchmark = engine.run(spec.benchmark(config))
        return strategy, benchmark

    base_strategy, base_static = run_variant(specs[BASE], None)
    contributions = dict(base_strategy.contributions)
    # The charter ranks sleeves by share of excess return over cash, not by raw
    # profit: a sleeve held almost always at roughly the cash rate earns a large
    # raw number while contributing nothing the portfolio could not have had by
    # sitting in cash.
    excess_contributions = dict(base_strategy.excess_contributions)
    top_sleeve = max(excess_contributions, key=lambda symbol: excess_contributions[symbol])

    runs: dict[str, tuple[BacktestResult, BacktestResult]] = {BASE: (base_strategy, base_static)}
    for name, spec in specs.items():
        if name == BASE:
            continue
        runs[name] = run_variant(spec, top_sleeve if spec.needs_top_sleeve else None)
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
    cash_metrics = calculate_metrics(cash, data)

    static_full_result: BacktestResult | None = None
    static_full: dict[str, float] | None = None
    if config.benchmark is not None:
        # The gating benchmark is the target-exposure allocation; the fully
        # invested monthly static stays as a secondary row so the reader can
        # still see the comparison BA-001 was judged on.
        static_full_result = _engine(config, data, cost).run(
            FixedAllocation(config.strategy.symbols, lookback, config.strategy.sleeve_weight)
        )
        static_full = calculate_metrics(static_full_result, data)

    tax: dict | None = None
    table: DistributionTable | None = None
    distributions_provenance: dict | None = None
    if config.tax is not None:
        table, block, distributions_provenance = _distributions_for(config, data)
        code_hash = code_fingerprint()
        tax_runs: dict[str, BacktestResult] = {
            "strategy": base_strategy,
            "benchmark": base_static,
            "exposure_matched": matched,
            "cash": cash,
        }
        if static_full_result is not None:
            tax_runs["static_full"] = static_full_result
        for name, (strategy, _) in runs.items():
            if name != BASE:
                tax_runs[f"variant:{name}"] = strategy
        tax = {
            "tax_policy_sha256": policy_sha256(config.tax),
            "distributions_sha256": table.sha256,
            "distributions_manifest": block,
            "overlay_version": OVERLAY_VERSION,
            "runs": {
                name: run_scenarios(
                    result, data, table, config.tax,
                    initial_cash=config.portfolio.initial_cash, code_sha256=code_hash,
                )
                for name, result in tax_runs.items()
            },
        }

    clusters = {
        name: sum(excess_contributions.get(symbol, 0.0) for symbol in symbols)
        for name, symbols in config.clusters.items()
    }
    # Variants warm up differently — the 15-month rule needs three more months
    # of anchor history than the base rule — so every variant's warnings are
    # recorded and tagged, not just the pre-registered one's.
    warnings = [
        f"{name}: {warning}"
        for name, (strategy, static) in runs.items()
        for warning in tuple(strategy.warnings) + tuple(static.warnings)
    ]
    covered = {symbol for symbols in config.clusters.values() for symbol in symbols}
    uncovered = sorted(set(config.strategy.symbols) - covered)
    if config.clusters and uncovered:
        warnings.append(f"sleeves outside every cluster: {', '.join(uncovered)}")

    return SweepResult(
        variants=variants,
        outcome=profile.evaluate_period(variants, {"tax": tax, "static_full": static_full}),
        contributions=contributions,
        excess_contributions=excess_contributions,
        clusters=clusters,
        top_sleeve=top_sleeve,
        exposure_matched=calculate_metrics(matched, data),
        cash=cash_metrics,
        runs={
            **runs,
            "exposure_matched": (matched, cash),
            **({"static_full": (static_full_result, cash)} if static_full_result is not None else {}),
        },
        sharpe_interval=sharpe_difference_interval(
            excess_return_series(base_strategy, data),
            excess_return_series(base_static, data),
            seed=BOOTSTRAP_SEED,
        ),
        warnings=tuple(warnings),
        grid=grid,
        static_full=static_full,
        tax=tax,
        distributions=table,
        distributions_provenance=distributions_provenance,
    )


def benchmark_description(config: AppConfig) -> str:
    if config.benchmark is None:
        return "Static allocation, monthly rebalanced"
    return (
        f"{config.benchmark.exposure:.0%} target exposure, "
        f"{'annually' if config.benchmark.rebalance == 'annual' else 'monthly'} rebalanced"
    )


def _summary(config: AppConfig, sweep: SweepResult) -> str:
    evaluation = config.evaluation
    lines = [
        f"# {config.strategy.strategy_id} sweep — {evaluation.period} period",
        "",
        f"Window: {config.backtest.start} to {config.backtest.end}. "
        f"Base cost: {config.execution.cost_bps:g} bps per side.",
        f"Benchmark: {benchmark_description(config)}.",
        "",
        "## Pre-registered result",
        "",
        f"The {config.strategy.lookback_months}-month rule is the hypothesis under test. "
        "Everything below it is a stability check on this result, not a menu: "
        "the charter forbids selecting a lookback or a cost after seeing outcomes.",
        "",
        "| Metric | Strategy | Static | Exposure-matched | Cash |",
        "|---|---:|---:|---:|---:|",
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
            f"{float(base['static'][key]):.4f} | {float(sweep.exposure_matched[key]):.4f} | "
            f"{float(sweep.cash[key]):.4f} |"
        )

    if sweep.static_full is not None:
        lines += [
            "",
            "Full static (fully invested, rebalanced monthly), the comparison BA-001 was "
            "judged on, kept as a secondary row: "
            f"CAGR {float(sweep.static_full['cagr']):.4f}, "
            f"max drawdown {float(sweep.static_full['max_drawdown']):.4f}, "
            f"Sharpe vs cash {float(sweep.static_full['sharpe_vs_cash']):.4f}.",
        ]

    interval = sweep.sharpe_interval
    lines += [
        "",
        f"Sharpe difference against static: {interval['point']:+.3f} "
        f"({interval['confidence']:.0%} percentile interval {interval['low']:+.3f} to "
        f"{interval['high']:+.3f}, {int(interval['resamples'])} stationary block resamples, "
        f"seed {int(interval['seed'])}).",
    ]
    if interval["low"] <= 0.0 <= interval["high"]:
        lines.append(
            "The interval contains zero: this sample cannot distinguish the two on "
            "risk-adjusted return."
        )
    else:
        lines.append(
            "The interval excludes zero. Read it with the charter's prior-evidence "
            "discount in mind: this rule was published before this test, the interval "
            "is one of several reported here, and it says nothing about the sealed period."
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
    for name in sweep.grid:
        metrics = sweep.variants[name]["strategy"]
        lines.append(
            f"| {name} | {sweep.grid[name]} | {float(metrics['max_drawdown']):.4f} | "
            f"{float(metrics['sharpe_vs_cash']):.4f} |"
        )

    lines += [
        "",
        "## Attribution",
        "",
        "C5 ranks on excess over cash, which is the charter's definition; raw P&L "
        "is shown beside it because the two can disagree.",
        "",
        "| Sleeve | Excess over cash | Raw P&L |",
        "|---|---:|---:|",
    ]
    for symbol, value in sorted(sweep.excess_contributions.items(), key=lambda item: -item[1]):
        marker = " (largest)" if symbol == sweep.top_sleeve else ""
        lines.append(f"| {symbol}{marker} | {value:.2f} | {sweep.contributions[symbol]:.2f} |")
    if sweep.clusters:
        lines += ["", "| Cluster | Excess over cash |", "|---|---:|"]
        for name, value in sorted(sweep.clusters.items(), key=lambda item: -item[1]):
            lines.append(f"| {name} | {value:.2f} |")
    lines += _after_tax_lines(sweep)
    if sweep.warnings:
        lines += ["", "## Warnings", ""] + [f"- {warning}" for warning in sweep.warnings]
    return "\n".join(lines) + "\n"


def _after_tax_lines(sweep: SweepResult) -> list[str]:
    if sweep.tax is None:
        return []
    tax = sweep.tax
    lines = [
        "",
        "## After tax",
        "",
        f"Overlay {tax['overlay_version']}; policy {tax['tax_policy_sha256'][:12]}; "
        f"distributions {tax['distributions_sha256'][:12]}. Eight scenarios: lot method × "
        "commodity-pool treatment × qualified set. An after-tax conclusion must hold under "
        "every scenario; the worst and best are shown.",
        "",
        "| Run | Pre-tax CAGR | After-tax CAGR (worst) | Worst scenario | After-tax CAGR (best) "
        "| Tax drag, worst (bps) | Wash-sale disallowed |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    failed_checks: list[str] = []
    for name, scenarios in tax["runs"].items():
        # A post-liquidation wealth that is not positive leaves after_tax_cagr
        # (and tax_drag_bps) None; None is treated as worst, never best, so a
        # scenario that fails to sustain positive wealth cannot hide as "best".
        def rank(key: str, scenarios: dict = scenarios) -> float:
            cagr = scenarios[key]["metrics"]["after_tax_cagr"]
            return cagr if cagr is not None else float("-inf")

        worst_key = min(scenarios, key=rank)
        best_key = max(scenarios, key=rank)
        worst, best, base = scenarios[worst_key], scenarios[best_key], scenarios[TAX_BASE_SCENARIO]
        worst_cagr = worst["metrics"]["after_tax_cagr"]
        best_cagr = best["metrics"]["after_tax_cagr"]
        worst_drag = worst["metrics"]["tax_drag_bps"]
        lines.append(
            f"| {name} | {worst['metrics']['pre_tax_cagr']:.4f} | "
            f"{'n/a' if worst_cagr is None else f'{worst_cagr:.4f}'} | {worst_key} | "
            f"{'n/a' if best_cagr is None else f'{best_cagr:.4f}'} | "
            f"{'n/a' if worst_drag is None else f'{worst_drag:.1f}'} | "
            f"{base['totals']['wash_sale_disallowed_total']:.2f} |"
        )
        for scenario_name, scenario in scenarios.items():
            for check in ("share_identity_passed", "income_plus_gain_passed", "implied_price_check_passed"):
                if not scenario["identity_checks"][check]:
                    failed_checks.append(f"{name} / {scenario_name}: {check} is false")
    policy = next(iter(next(iter(tax["runs"].values())).values()))["policy"]
    lines += [
        "",
        f"Rates: ordinary {policy['ordinary_rate']:.0%}, long-term {policy['long_term_rate']:.0%}, "
        f"collectibles {policy['collectibles_rate']:.0%}; a federal-only stylized scenario. "
        f"{policy['nav_convention']} Drawdown is pre-tax throughout.",
    ]
    if failed_checks:
        lines += ["", "**Identity checks failed:** " + "; ".join(failed_checks) + "."]
    return lines


def _price_rows(data: MarketData) -> list[list[str]]:
    rows = [["date", "symbol", "tr_open", "tr_close"]]
    for day in data.dates:
        for symbol in sorted(data.by_date[day]):
            bar = data.by_date[day][symbol]
            rows.append([day.isoformat(), symbol, repr(bar.open), repr(bar.close)])
    return rows


def _cash_rows(data: MarketData) -> list[list[str]]:
    return [["date", "cash_factor"]] + [
        [day.isoformat(), repr(data.cash_factors[day])] for day in data.dates
    ]


def _gzip_csv(rows: list[list[str]]) -> bytes:
    """Deterministic gzip: mtime zeroed so the same data yields the same bytes."""

    text = io.StringIO()
    csv.writer(text, lineterminator="\n").writerows(rows)
    return _gzip_bytes(text.getvalue().encode("utf-8"))


def _gzip_bytes(content: bytes) -> bytes:
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as handle:
        handle.write(content)
    return raw.getvalue()


def write_sweep_report(
    config: AppConfig,
    data: MarketData,
    sweep: SweepResult,
    unseal_reason: str | None = None,
) -> tuple[str, Path]:
    evaluation = config.evaluation
    code_hash = code_fingerprint()
    archive: dict[str, bytes] = {
        "input_prices.csv.gz": _gzip_csv(_price_rows(data)),
        "input_cash.csv.gz": _gzip_csv(_cash_rows(data)),
    }
    if sweep.distributions is not None:
        archive["input_distributions.csv.gz"] = _gzip_bytes(sweep.distributions.canonical_csv())
    for name, (strategy, benchmark) in sweep.runs.items():
        prefix = f"variants/{name}"
        archive.update({
            f"{prefix}/strategy_equity.csv": equity_csv(strategy).encode("utf-8"),
            f"{prefix}/strategy_trades.csv": trades_csv(strategy).encode("utf-8"),
            f"{prefix}/strategy_decisions.json": decisions_json(strategy).encode("utf-8"),
            f"{prefix}/benchmark_equity.csv": equity_csv(benchmark).encode("utf-8"),
            f"{prefix}/benchmark_trades.csv": trades_csv(benchmark).encode("utf-8"),
        })
    identity = ":".join(
        (
            hashlib.sha256(config.raw_bytes).hexdigest(),
            data.fingerprint(),
            code_hash,
            f"{evaluation.period}:{evaluation.start}:{evaluation.end}",
            "|".join(sweep.grid),
            *(
                (sweep.tax["distributions_sha256"],)
                if sweep.tax is not None else ()
            ),
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
                "benchmark": benchmark_description(config),
                "config_toml": config.raw_bytes.decode("utf-8"),
                "data_sha256": data.fingerprint(),
                "data_source": data.source,
                "data_start": data.dates[0],
                "data_end": data.dates[-1],
                "code_sha256": code_hash,
                "artifacts_sha256": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in archive.items()
                },
                "warnings": run_warnings(config, data, ()) + list(sweep.warnings),
                **(
                    {
                        "tax_policy_sha256": sweep.tax["tax_policy_sha256"],
                        "distributions_sha256": sweep.tax["distributions_sha256"],
                        "distributions_manifest": sweep.tax["distributions_manifest"],
                    }
                    if sweep.tax is not None
                    else {}
                ),
            }
        ),
    )
    write_once(
        sweep_dir / "criteria.json",
        json_text(
            {
                "artifact_schema": ARTIFACT_SCHEMA,
                "sweep_id": sweep_id,
                "strategy_id": config.strategy.strategy_id,
                "strategy_spec_sha256": config.strategy_spec_sha256,
                "code_sha256": code_hash,
                "lookback_months": config.strategy.lookback_months,
                "cost_bps": config.execution.cost_bps,
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
                "excess_contributions": sweep.excess_contributions,
                "clusters": sweep.clusters,
                "exposure_matched": sweep.exposure_matched,
                "sharpe_interval": sweep.sharpe_interval,
                **(
                    {
                        "tax_policy_sha256": sweep.tax["tax_policy_sha256"],
                        "distributions_sha256": sweep.tax["distributions_sha256"],
                        "static_full": sweep.static_full,
                    }
                    if sweep.tax is not None
                    else ({"static_full": sweep.static_full} if sweep.static_full is not None else {})
                ),
            }
        ),
    )
    write_once(sweep_dir / "summary.md", _summary(config, sweep))

    if sweep.tax is not None:
        write_once(
            sweep_dir / "tax.json",
            json_text(
                {
                    "artifact_schema": ARTIFACT_SCHEMA,
                    "sweep_id": sweep_id,
                    "strategy_id": config.strategy.strategy_id,
                    "code_sha256": code_hash,
                    **sweep.tax,
                }
            ),
        )

    for name, content in archive.items():
        path = sweep_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write_once_bytes(path, content)

    append_provenance(sweep_dir, unseal_reason)
    if sweep.distributions_provenance is not None:
        with (sweep_dir / "distributions_provenance.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sweep.distributions_provenance, sort_keys=True) + "\n")
    return sweep_id, sweep_dir
