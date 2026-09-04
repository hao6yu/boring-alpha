"""Validated TOML configuration for BoringAlpha experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    strategy_id: str
    name: str
    symbols: tuple[str, ...]
    lookback_months: int
    sleeve_weight: float


@dataclass(frozen=True, slots=True)
class PortfolioConfig:
    initial_cash: float


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    cost_bps: float


@dataclass(frozen=True, slots=True)
class DataConfig:
    source: str
    start: date | None = None
    end: date | None = None
    seed: int = 0
    annual_cash_rate: float = 0.0
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
class AppConfig:
    strategy: StrategyConfig
    portfolio: PortfolioConfig
    execution: ExecutionConfig
    data: DataConfig
    backtest: BacktestConfig
    evaluation: EvaluationConfig
    report: ReportConfig
    path: Path
    raw_bytes: bytes


_SCHEMA: dict[str, frozenset[str]] = {
    "strategy": frozenset({"id", "name", "symbols", "lookback_months", "sleeve_weight"}),
    "portfolio": frozenset({"initial_cash"}),
    "execution": frozenset({"cost_bps"}),
    "data": frozenset(
        {"source", "start", "end", "seed", "annual_cash_rate", "prices_path", "cash_path"}
    ),
    "backtest": frozenset({"start", "end"}),
    "evaluation": frozenset({"period", "periods_path", "review_dir"}),
    "report": frozenset({"output_dir"}),
}

PERIODS = ("development", "validation", "sealed", "exploratory")
UNBOUNDED_PERIOD = "exploratory"

_DATA_KEYS_BY_SOURCE: dict[str, frozenset[str]] = {
    "synthetic": frozenset({"start", "end", "seed", "annual_cash_rate"}),
    "csv": frozenset({"prices_path", "cash_path"}),
}


def _check_schema(raw: dict[str, object]) -> None:
    unknown_tables = sorted(set(raw) - set(_SCHEMA))
    if unknown_tables:
        raise ValueError(f"unknown table(s) in configuration: {', '.join(unknown_tables)}")
    for table, allowed in _SCHEMA.items():
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
    strategy = StrategyConfig(
        strategy_id=str(_require(strategy_raw, "strategy", "id")).strip(),
        name=str(_require(strategy_raw, "strategy", "name")).strip(),
        symbols=tuple(str(symbol).upper() for symbol in symbols_raw),
        lookback_months=int(_require(strategy_raw, "strategy", "lookback_months")),
        sleeve_weight=float(_require(strategy_raw, "strategy", "sleeve_weight")),
    )

    portfolio_raw = raw.get("portfolio", {})
    portfolio = PortfolioConfig(
        initial_cash=float(_require(portfolio_raw, "portfolio", "initial_cash"))
    )

    execution_raw = raw.get("execution", {})
    execution = ExecutionConfig(cost_bps=float(_require(execution_raw, "execution", "cost_bps")))

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
        annual_cash_rate=float(data_raw.get("annual_cash_rate", 0.0)),
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

    _validate(strategy, portfolio, execution, data, backtest)
    return AppConfig(
        strategy=strategy,
        portfolio=portfolio,
        execution=execution,
        data=data,
        backtest=backtest,
        evaluation=evaluation,
        report=report,
        path=config_path,
        raw_bytes=raw_bytes,
    )


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
    start = _parse_date(_require(bounds, f"{strategy_id}.{period}", "start"), "period start")
    end = _parse_date(_require(bounds, f"{strategy_id}.{period}", "end"), "period end")
    if start > end:
        raise ValueError(f"{strategy_id} {period} period starts after it ends")
    if backtest.start < start or backtest.end > end:
        raise ValueError(
            f"backtest window {backtest.start}..{backtest.end} falls outside the "
            f"{period} period {start}..{end}"
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
        if data.start is None or data.end is None or data.start >= data.end:
            raise ValueError("synthetic data requires data.start < data.end")
        if data.start > backtest.start or data.end < backtest.end:
            raise ValueError("synthetic data must cover the backtest period and warm-up")
        if data.annual_cash_rate <= -1.0:
            raise ValueError("data.annual_cash_rate must be greater than -100%")
    elif data.source == "csv":
        if data.prices_path is None or data.cash_path is None:
            raise ValueError("CSV data requires prices_path and cash_path")
    else:
        raise ValueError("data.source must be 'synthetic' or 'csv'")
