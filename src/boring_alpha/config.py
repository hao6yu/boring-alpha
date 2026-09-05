"""Validated TOML configuration for BoringAlpha experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import tomllib

from boring_alpha.domain import GAINS_CLASSES, REBALANCE_SCHEDULES, validate_horizon_inputs


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    strategy_id: str
    name: str
    symbols: tuple[str, ...]
    lookback_months: int
    sleeve_weight: float
    horizons: tuple[int, ...] | None = None
    warmup_months: int | None = None


@dataclass(frozen=True, slots=True)
class PortfolioConfig:
    initial_cash: float


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    cost_bps: float


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """The gating benchmark's target exposure and rebalancing schedule.

    Optional. When present, the strategy is judged against static equal-weight
    scaled to `exposure` with the remainder in cash, rebalanced on `rebalance`,
    instead of the fully invested monthly static allocation. Both values are
    part of what is being tested, so both enter the strategy spec hash.
    """

    exposure: float
    rebalance: str


@dataclass(frozen=True, slots=True)
class TaxConfig:
    """Stylized tax policy for the after-tax overlay (spec §4.9).

    Federal-only rates declared for the record; the account holder's real rates
    belong in an untracked local file. `qualified_fraction` is the base set;
    the scenario grid also runs every income-paying symbol at
    `qualified_fraction_low`. The path names the distributions file; it is not
    part of the policy's identity.
    """

    distributions_path: Path
    ordinary_rate: float
    long_term_rate: float
    collectibles_rate: float
    qualified_fraction_low: float
    qualified_fraction: dict[str, float]
    gains_class: dict[str, str]


COLLECTIBLES_RATE_CAP = 0.28
_TAX_KEYS = frozenset(
    {
        "distributions_path", "ordinary_rate", "long_term_rate", "collectibles_rate",
        "qualified_fraction_low", "qualified_fraction", "gains_class",
    }
)


@dataclass(frozen=True, slots=True)
class DataConfig:
    source: str
    start: date | None = None
    end: date | None = None
    seed: int = 0
    annual_cash_rate: float = 0.0
    regime: str = "trending"
    methodology: str = ""
    prices_path: Path | None = None
    cash_path: Path | None = None


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    period: str
    start: date | None
    end: date | None
    review_dir: Path

    @property
    def is_evidence(self) -> bool:
        """Exploratory runs exercise the lab; they say nothing about the strategy."""

        return self.period != "exploratory"


@dataclass(frozen=True, slots=True)
class ReportConfig:
    output_dir: Path


@dataclass(frozen=True, slots=True)
class ResearchConfig:
    """Locations, not approvals: loading config does not read these artifacts.

    Their independently verified semantic content is consumed by research
    preflight; a path or mere file presence can never authorize execution.
    """

    calendar_path: Path
    freeze_path: Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    strategy: StrategyConfig
    portfolio: PortfolioConfig
    execution: ExecutionConfig
    data: DataConfig
    backtest: BacktestConfig
    evaluation: EvaluationConfig
    report: ReportConfig
    quality_overrides: dict[str, float]
    clusters: dict[str, tuple[str, ...]]
    benchmark: BenchmarkConfig | None
    tax: TaxConfig | None
    strategy_spec_sha256: str
    path: Path
    raw_bytes: bytes
    research: ResearchConfig | None = None


_SCHEMA: dict[str, frozenset[str]] = {
    "strategy": frozenset({"id", "name", "symbols", "lookback_months", "sleeve_weight", "horizons", "warmup_months"}),
    "portfolio": frozenset({"initial_cash"}),
    "execution": frozenset({"cost_bps"}),
    "data": frozenset(
        {
            "source", "start", "end", "seed", "annual_cash_rate", "regime",
            "methodology", "prices_path", "cash_path",
        }
    ),
    "backtest": frozenset({"start", "end"}),
    "evaluation": frozenset({"period", "periods_path", "review_dir"}),
    # Names must match QualityThresholds; defaults live there, not here.
    "quality": frozenset(
        {
            "max_session_return", "max_open_gap", "min_cash_rate", "max_cash_rate",
            "max_calendar_gap_days", "max_stale_closes",
        }
    ),
    "report": frozenset({"output_dir"}),
    "benchmark": frozenset({"exposure", "rebalance"}),
    "tax": _TAX_KEYS,
    "research": frozenset({"calendar_path", "freeze_path"}),
}

# Cluster names are chosen per strategy, so this table's keys are open.
_OPEN_TABLES = frozenset({"clusters"})

PERIODS = ("development", "validation", "sealed", "exploratory")
UNBOUNDED_PERIOD = "exploratory"
DATASET_END = "dataset"

_DATA_KEYS_BY_SOURCE: dict[str, frozenset[str]] = {
    "synthetic": frozenset({"start", "end", "seed", "annual_cash_rate", "regime"}),
    "csv": frozenset({"prices_path", "cash_path", "methodology"}),
}


def _check_schema(raw: dict[str, object]) -> None:
    unknown_tables = sorted(set(raw) - set(_SCHEMA) - _OPEN_TABLES)
    if unknown_tables:
        raise ValueError(f"unknown table(s) in configuration: {', '.join(unknown_tables)}")
    for table, allowed in _SCHEMA.items():
        if table in _OPEN_TABLES:
            continue
        section = raw.get(table, {})
        if not isinstance(section, dict):
            raise ValueError(f"[{table}] must be a table")
        unknown_keys = sorted(set(section) - allowed)
        if unknown_keys:
            raise ValueError(f"unknown key(s) in [{table}]: {', '.join(unknown_keys)}")


def _require(section: dict[str, object], table: str, key: str) -> object:
    if key not in section:
        raise ValueError(f"{table}.{key} is required")
    return section[key]


def _finite(value: float, field: str) -> float:
    """Reject NaN and infinity, which slip past every `<= 0` guard."""

    if not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return value


def _strategy_spec_hash(
    strategy: StrategyConfig,
    portfolio: PortfolioConfig,
    execution: ExecutionConfig,
    data: DataConfig,
    benchmark: BenchmarkConfig | None,
) -> str:
    """Fingerprint of what the strategy IS, independent of the window it ran over.

    Two sweeps may only be combined into a verdict if this matches. The
    evaluation window is deliberately excluded — development and validation
    differ in exactly that and nothing else. Symbols are sorted because
    reordering the universe does not change the strategy. The benchmark table
    is included only when present, so configurations written before it existed
    keep the hash their archived runs recorded.
    """

    spec: dict[str, object] = {
        "strategy_id": strategy.strategy_id,
        "symbols": sorted(strategy.symbols),
        "lookback_months": strategy.lookback_months,
        "sleeve_weight": strategy.sleeve_weight,
        "initial_cash": portfolio.initial_cash,
        "cost_bps": execution.cost_bps,
        "data_source": data.source,
        # How the inputs were built is part of what was run. The fetcher lives
        # outside code_fingerprint(), so a change of price adjustment or cash
        # series would otherwise be invisible to the run's identity.
        "data_methodology": data.methodology,
    }
    if benchmark is not None:
        spec["benchmark"] = {"exposure": benchmark.exposure, "rebalance": benchmark.rebalance}
    if strategy.horizons is not None:
        spec["horizons"] = list(strategy.horizons)
        spec["warmup_months"] = strategy.warmup_months
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{field} must be an ISO date, not a datetime")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date, got {value!r}") from exc
    raise ValueError(f"{field} must be an ISO date")


def _resolve_path(value: object, root: Path, field: str) -> Path:
    """Resolve a configured path; relative paths are anchored at the config's directory."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_config(path: str | Path) -> AppConfig:
    """Load and validate a BoringAlpha TOML configuration."""

    config_path = Path(path).resolve()
    raw_bytes = config_path.read_bytes()
    raw = tomllib.loads(raw_bytes.decode("utf-8"))
    _check_schema(raw)
    root = config_path.parent

    strategy_raw = raw.get("strategy", {})
    symbols_raw = _require(strategy_raw, "strategy", "symbols")
    if not isinstance(symbols_raw, list):
        raise ValueError("strategy.symbols must be a list of symbols")
    horizons = None
    warmup_months = None
    lookback_raw = _require(strategy_raw, "strategy", "lookback_months")
    if "horizons" in strategy_raw:
        horizons_raw = strategy_raw["horizons"]
        if not isinstance(horizons_raw, list):
            raise ValueError("strategy.horizons must be a list of positive integers")
        warmup_months = strategy_raw.get("warmup_months", 15)
        horizons = validate_horizon_inputs(horizons_raw, warmup_months)
        if type(lookback_raw) is not int or lookback_raw != warmup_months:
            raise ValueError("strategy.lookback_months must equal the integer strategy.warmup_months")
    elif "warmup_months" in strategy_raw:
        raise ValueError("strategy.warmup_months requires strategy.horizons")
    strategy = StrategyConfig(
        strategy_id=str(_require(strategy_raw, "strategy", "id")).strip(),
        name=str(_require(strategy_raw, "strategy", "name")).strip(),
        symbols=tuple(str(symbol).upper() for symbol in symbols_raw),
        lookback_months=int(lookback_raw),
        sleeve_weight=_finite(float(_require(strategy_raw, "strategy", "sleeve_weight")), "strategy.sleeve_weight"),
        horizons=horizons,
        warmup_months=warmup_months,
    )

    portfolio_raw = raw.get("portfolio", {})
    portfolio = PortfolioConfig(
        initial_cash=_finite(float(_require(portfolio_raw, "portfolio", "initial_cash")), "portfolio.initial_cash")
    )

    execution_raw = raw.get("execution", {})
    execution = ExecutionConfig(
        cost_bps=_finite(float(_require(execution_raw, "execution", "cost_bps")), "execution.cost_bps")
    )

    data_raw = raw.get("data", {})
    source = str(_require(data_raw, "data", "source")).lower()
    if source in _DATA_KEYS_BY_SOURCE:
        irrelevant = sorted(set(data_raw) - {"source"} - _DATA_KEYS_BY_SOURCE[source])
        if irrelevant:
            raise ValueError(
                f"[data] keys {', '.join(irrelevant)} do not apply to source '{source}'"
            )
    data = DataConfig(
        source=source,
        start=_parse_date(data_raw["start"], "data.start") if "start" in data_raw else None,
        end=_parse_date(data_raw["end"], "data.end") if "end" in data_raw else None,
        seed=int(data_raw.get("seed", 0)),
        annual_cash_rate=_finite(float(data_raw.get("annual_cash_rate", 0.0)), "data.annual_cash_rate"),
        regime=str(data_raw.get("regime", "trending")).lower(),
        methodology=str(data_raw.get("methodology", "")).strip(),
        prices_path=(
            _resolve_path(data_raw["prices_path"], root, "data.prices_path")
            if "prices_path" in data_raw
            else None
        ),
        cash_path=(
            _resolve_path(data_raw["cash_path"], root, "data.cash_path")
            if "cash_path" in data_raw
            else None
        ),
    )

    backtest_raw = raw.get("backtest", {})
    backtest = BacktestConfig(
        start=_parse_date(_require(backtest_raw, "backtest", "start"), "backtest.start"),
        end=_parse_date(_require(backtest_raw, "backtest", "end"), "backtest.end"),
    )

    evaluation_raw = raw.get("evaluation", {})
    evaluation = _load_evaluation(evaluation_raw, root, strategy.strategy_id, backtest)

    report_raw = raw.get("report", {})
    report = ReportConfig(
        output_dir=_resolve_path(
            _require(report_raw, "report", "output_dir"), root, "report.output_dir"
        )
    )

    benchmark = _load_benchmark(raw.get("benchmark"))
    tax = _load_tax(raw.get("tax"), strategy.symbols, root)
    research = _load_research(raw.get("research"), root)

    _validate(strategy, portfolio, execution, data, backtest)
    return AppConfig(
        strategy=strategy,
        portfolio=portfolio,
        execution=execution,
        data=data,
        backtest=backtest,
        evaluation=evaluation,
        report=report,
        quality_overrides=_load_quality_overrides(raw.get("quality", {})),
        clusters=_load_clusters(raw.get("clusters", {}), strategy.symbols),
        benchmark=benchmark,
        tax=tax,
        strategy_spec_sha256=_strategy_spec_hash(strategy, portfolio, execution, data, benchmark),
        path=config_path,
        raw_bytes=raw_bytes,
        research=research,
    )


_POSITIVE_THRESHOLDS = frozenset(
    {"max_session_return", "max_open_gap", "max_calendar_gap_days", "max_stale_closes"}
)


def _load_research(raw: dict[str, object] | None, root: Path) -> ResearchConfig | None:
    if raw is None:
        return None
    return ResearchConfig(**{
        key: _resolve_path(_require(raw, "research", key), root, f"research.{key}")
        for key in ("calendar_path", "freeze_path")
    })


def _load_quality_overrides(raw: dict[str, object]) -> dict[str, float]:
    """A NaN threshold silently disables its check, since NaN fails every
    ordered comparison — a worse outcome than not overriding at all."""

    overrides: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"quality.{key} must be a number")
        number = _finite(float(value), f"quality.{key}")
        if key in _POSITIVE_THRESHOLDS and number <= 0.0:
            raise ValueError(f"quality.{key} must be positive, got {number!r}")
        overrides[key] = number
    return overrides


def _load_clusters(
    raw: dict[str, object], symbols: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    clusters: dict[str, tuple[str, ...]] = {}
    seen: dict[str, str] = {}
    for name, members in raw.items():
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            raise ValueError(f"clusters.{name} must be a list of symbols")
        cluster = tuple(member.upper() for member in members)
        unknown = sorted(set(cluster) - set(symbols))
        if unknown:
            raise ValueError(f"clusters.{name} names symbols outside the universe: {unknown}")
        for symbol in cluster:
            if symbol in seen:
                raise ValueError(
                    f"{symbol} appears in clusters {seen[symbol]} and {name}; "
                    "clusters must not overlap or attribution double-counts"
                )
            seen[symbol] = name
        clusters[name] = cluster
    return clusters


def _load_benchmark(raw: dict[str, object] | None) -> BenchmarkConfig | None:
    if raw is None:
        return None
    exposure = _finite(
        float(_require(raw, "benchmark", "exposure")), "benchmark.exposure"
    )
    if not 0.0 < exposure <= 1.0:
        raise ValueError(f"benchmark.exposure must be in (0, 1], got {exposure!r}")
    rebalance = str(_require(raw, "benchmark", "rebalance")).lower()
    if rebalance not in REBALANCE_SCHEDULES:
        raise ValueError(
            f"benchmark.rebalance must be one of {', '.join(REBALANCE_SCHEDULES)}, got {rebalance!r}"
        )
    return BenchmarkConfig(exposure, rebalance)


def _rate(raw: dict[str, object], key: str) -> float:
    value = _finite(float(_require(raw, "tax", key)), f"tax.{key}")
    if not 0.0 <= value < 1.0:
        raise ValueError(f"tax.{key} must be in [0, 1), got {value!r}")
    return value


def _load_symbol_table(
    raw: dict[str, object], name: str, symbols: tuple[str, ...], kind: str
) -> dict[str, object]:
    """`[tax.<name>]`: one entry per symbol of the universe, no extras."""

    table = _require(raw, "tax", name)
    if not isinstance(table, dict):
        raise ValueError(f"tax.{name} must be a table of symbol = value")
    result: dict[str, object] = {}
    for symbol, value in table.items():
        upper = symbol.upper()
        if upper not in symbols:
            raise ValueError(f"tax.{name} names {symbol}, which is not in strategy.symbols")
        if kind == "fraction":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"tax.{name}.{symbol} must be a number in [0, 1]")
            number = _finite(float(value), f"tax.{name}.{symbol}")
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"tax.{name}.{symbol} must be in [0, 1], got {value!r}")
            result[upper] = number
        else:
            label = str(value).lower()
            if label not in GAINS_CLASSES:
                raise ValueError(
                    f"tax.{name}.{symbol} must be one of {', '.join(GAINS_CLASSES)}, got {value!r}"
                )
            result[upper] = label
    missing = sorted(set(symbols) - set(result))
    if missing:
        raise ValueError(f"tax.{name} is missing {', '.join(missing)}")
    return result


def _load_tax(
    raw: dict[str, object] | None, symbols: tuple[str, ...], root: Path
) -> TaxConfig | None:
    if raw is None:
        return None
    unknown = sorted(set(raw) - _TAX_KEYS)
    if unknown:
        raise ValueError(f"unknown key(s) in [tax]: {', '.join(unknown)}")
    ordinary = _rate(raw, "ordinary_rate")
    long_term = _rate(raw, "long_term_rate")
    collectibles = _rate(raw, "collectibles_rate")
    cap = min(ordinary, COLLECTIBLES_RATE_CAP)
    if collectibles > cap + 1e-12:
        raise ValueError(
            f"tax.collectibles_rate must not exceed min(ordinary_rate, {COLLECTIBLES_RATE_CAP}) "
            f"= {cap:.4f}, got {collectibles!r}; the statutory rule is the ordinary rate "
            "capped at 28%"
        )
    low = _finite(
        float(_require(raw, "tax", "qualified_fraction_low")), "tax.qualified_fraction_low"
    )
    if not 0.0 <= low <= 1.0:
        raise ValueError(f"tax.qualified_fraction_low must be in [0, 1], got {low!r}")
    fractions = _load_symbol_table(raw, "qualified_fraction", symbols, "fraction")
    classes = _load_symbol_table(raw, "gains_class", symbols, "class")
    path = _resolve_path(
        _require(raw, "tax", "distributions_path"), root, "tax.distributions_path"
    )
    return TaxConfig(
        distributions_path=path,
        ordinary_rate=ordinary,
        long_term_rate=long_term,
        collectibles_rate=collectibles,
        qualified_fraction_low=low,
        qualified_fraction={k: float(v) for k, v in fractions.items()},
        gains_class={k: str(v) for k, v in classes.items()},
    )


def load_tax_policy(path: str | Path, symbols: tuple[str, ...]) -> TaxConfig:
    """A standalone policy file: exactly one `[tax]` table, validated for `symbols`.

    Used by the `aftertax` command, which scores archived sweeps whose own
    configuration carried no tax table.
    """

    policy_path = Path(path).resolve()
    raw = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    if set(raw) != {"tax"} or not isinstance(raw["tax"], dict):
        raise ValueError(f"{policy_path} must contain only a [tax] table")
    tax = _load_tax(raw["tax"], tuple(symbol.upper() for symbol in symbols), policy_path.parent)
    assert tax is not None
    return tax


def _load_evaluation(
    raw: dict[str, object], root: Path, strategy_id: str, backtest: BacktestConfig
) -> EvaluationConfig:
    period = str(_require(raw, "evaluation", "period")).lower()
    if period not in PERIODS:
        raise ValueError(f"evaluation.period must be one of {', '.join(PERIODS)}")
    review_dir = _resolve_path(
        raw.get("review_dir", "../docs/reviews"), root, "evaluation.review_dir"
    )
    if period == UNBOUNDED_PERIOD:
        return EvaluationConfig(period, None, None, review_dir)

    periods_path = _resolve_path(
        raw.get("periods_path", "evaluation_periods.toml"), root, "evaluation.periods_path"
    )
    if not periods_path.is_file():
        raise ValueError(f"evaluation period registry not found: {periods_path}")
    registry = tomllib.loads(periods_path.read_text(encoding="utf-8"))
    bounds = registry.get(strategy_id, {}).get(period)
    if not isinstance(bounds, dict):
        raise ValueError(f"{periods_path} defines no {period} period for {strategy_id}")
    label = f"{strategy_id}.{period}"
    start = _parse_date(_require(bounds, label, "start"), "period start")
    raw_end = _require(bounds, label, "end")
    # A charter may end a period at "the latest complete dataset" rather than a
    # date. DATASET_END means no truncation and no upper bound to check.
    end = None if raw_end == DATASET_END else _parse_date(raw_end, "period end")
    if end is not None and start > end:
        raise ValueError(f"{strategy_id} {period} period starts after it ends")
    # An evidence period must be run whole. Accepting a narrower window would let
    # a favourable sub-period be reported under the period's name, which is the
    # cherry-picking the charter's protocol exists to prevent. A period ending at
    # DATASET_END has no registered end to match, so only its start is fixed.
    if backtest.start != start:
        raise ValueError(
            f"a {period} run must start on the {period} period start {start}, "
            f"not {backtest.start}"
        )
    if end is not None and backtest.end != end:
        raise ValueError(
            f"a {period} run must cover the {period} period exactly "
            f"({start}..{end}); got {backtest.start}..{backtest.end}"
        )
    return EvaluationConfig(period, start, end, review_dir)


def _validate(
    strategy: StrategyConfig,
    portfolio: PortfolioConfig,
    execution: ExecutionConfig,
    data: DataConfig,
    backtest: BacktestConfig,
) -> None:
    if not strategy.strategy_id or not strategy.name:
        raise ValueError("strategy.id and strategy.name must be non-empty")
    if not strategy.symbols or len(set(strategy.symbols)) != len(strategy.symbols):
        raise ValueError("strategy.symbols must be non-empty and unique")
    if strategy.lookback_months <= 0:
        raise ValueError("strategy.lookback_months must be positive")
    if not 0.0 < strategy.sleeve_weight <= 1.0:
        raise ValueError("strategy.sleeve_weight must be in (0, 1]")
    if strategy.sleeve_weight * len(strategy.symbols) > 1.0 + 1e-12:
        raise ValueError("configured sleeves exceed 100% gross exposure")
    if portfolio.initial_cash <= 0.0:
        raise ValueError("portfolio.initial_cash must be positive")
    if execution.cost_bps < 0.0:
        raise ValueError("execution.cost_bps cannot be negative")
    if backtest.start > backtest.end:
        raise ValueError("backtest.start must not follow backtest.end")
    if data.source == "synthetic":
        if data.regime not in ("trending", "random_walk"):
            raise ValueError("data.regime must be 'trending' or 'random_walk'")
        if data.start is None or data.end is None or data.start >= data.end:
            raise ValueError("synthetic data requires data.start < data.end")
        if data.start > backtest.start or data.end < backtest.end:
            raise ValueError("synthetic data must cover the backtest period and warm-up")
        if data.annual_cash_rate <= -1.0:
            raise ValueError("data.annual_cash_rate must be greater than -100%")
    elif data.source == "csv":
        if data.prices_path is None or data.cash_path is None:
            raise ValueError("CSV data requires prices_path and cash_path")
        if not data.methodology:
            raise ValueError(
                "data.methodology is required for CSV data: name how the series were "
                "built, e.g. 'yahoo-adjusted-v1+dgs3mo-v1'. It becomes part of the "
                "run's identity, because the tool that builds the data is not covered "
                "by the code fingerprint."
            )
    else:
        raise ValueError("data.source must be 'synthetic' or 'csv'")
