"""Validated TOML configuration for BoringAlpha experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
class ReportConfig:
    output_dir: Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    strategy: StrategyConfig
    portfolio: PortfolioConfig
    execution: ExecutionConfig
    data: DataConfig
    backtest: BacktestConfig
    report: ReportConfig
    path: Path
    raw_bytes: bytes


def _parse_date(value: object, field: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date, got {value!r}") from exc
    raise ValueError(f"{field} must be an ISO date")


def _resolve_path(value: object, root: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_config(path: str | Path) -> AppConfig:
    """Load and validate a BoringAlpha TOML configuration."""

    config_path = Path(path).resolve()
    raw_bytes = config_path.read_bytes()
    raw = tomllib.loads(raw_bytes.decode("utf-8"))
    root = config_path.parent.parent

    strategy_raw = raw.get("strategy", {})
    symbols = tuple(str(symbol).upper() for symbol in strategy_raw.get("symbols", ()))
    strategy = StrategyConfig(
        strategy_id=str(strategy_raw.get("id", "")).strip(),
        name=str(strategy_raw.get("name", "")).strip(),
        symbols=symbols,
        lookback_months=int(strategy_raw.get("lookback_months", 0)),
        sleeve_weight=float(strategy_raw.get("sleeve_weight", 0.0)),
    )

    portfolio_raw = raw.get("portfolio", {})
    portfolio = PortfolioConfig(initial_cash=float(portfolio_raw.get("initial_cash", 0.0)))

    execution_raw = raw.get("execution", {})
    execution = ExecutionConfig(cost_bps=float(execution_raw.get("cost_bps", -1.0)))

    data_raw = raw.get("data", {})
    source = str(data_raw.get("source", "")).lower()
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
        start=_parse_date(backtest_raw.get("start"), "backtest.start"),
        end=_parse_date(backtest_raw.get("end"), "backtest.end"),
    )

    report_raw = raw.get("report", {})
    report = ReportConfig(
        output_dir=_resolve_path(
            report_raw.get("output_dir", "experiments"), root, "report.output_dir"
        )
    )

    _validate(strategy, portfolio, execution, data, backtest)
    return AppConfig(
        strategy=strategy,
        portfolio=portfolio,
        execution=execution,
        data=data,
        backtest=backtest,
        report=report,
        path=config_path,
        raw_bytes=raw_bytes,
    )


def _validate(
    strategy: StrategyConfig,
    portfolio: PortfolioConfig,
    execution: ExecutionConfig,
    data: DataConfig,
    backtest: BacktestConfig,
) -> None:
    if not strategy.strategy_id or not strategy.name:
        raise ValueError("strategy.id and strategy.name are required")
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
