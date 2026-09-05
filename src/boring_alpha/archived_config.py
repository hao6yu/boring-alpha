"""Validate schema-7's embedded config without opening original live paths.

The archive's contract supplies period bounds. Ordinary load_config would read
the current registry, potentially at a now-moved original location. This small
adapter instead parses semantic fields and reuses the existing spec-hash code.
It does not load market data, change files, or create an authorization record.
"""

from __future__ import annotations

from datetime import date
import math
import tomllib
from typing import Mapping

from boring_alpha.config import (
    BenchmarkConfig, DataConfig, ExecutionConfig, PortfolioConfig, StrategyConfig,
    _DATA_KEYS_BY_SOURCE, _check_schema, _load_clusters, _strategy_spec_hash,
)
from boring_alpha.domain import validate_horizon_inputs
from boring_alpha.research_contract import (
    ROWS, _validate_tax_policy, canonical_sha256, require_digest,
    require_exact_behavior, validate_contract,
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"archived {field} must be nonempty text")
    return value.strip()


def _numeric(value: object, field: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"archived {field} must be a finite number")
    return float(value)


def _iso(value: object, field: str) -> str:
    if type(value) is date:
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueError(f"archived {field} must be a fixed ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"archived {field} must be a fixed ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"archived {field} must be a canonical ISO date")
    return value


def validate_archived_config(manifest: Mapping, contract: Mapping) -> None:
    """Cross-check frozen behavior, own window/status and recomputed spec hash."""
    selected = validate_contract(contract)
    if not isinstance(manifest, Mapping):
        raise ValueError("archived manifest must be an object")
    try:
        raw = tomllib.loads(_text(manifest.get("config_toml"), "config_toml"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"archived config_toml is unreadable: {exc}") from exc
    # Old schema-7 archives retain their former configurable journal location.
    # It is inert provenance here, never a path to read or reuse for execution.
    if isinstance(raw.get("research"), dict) and "journal_path" in raw["research"]:
        _text(raw["research"].pop("journal_path"), "research.journal_path")
    _check_schema(raw)
    required = {"strategy", "portfolio", "execution", "data", "backtest", "evaluation", "benchmark", "tax", "report", "research"}
    if not required.issubset(raw):
        raise ValueError("archived BA-002 config is missing required sections")
    if raw.get("quality"):
        raise ValueError("BA-002 quality overrides are not part of the frozen research contract")

    strategy_raw = raw["strategy"]
    symbols_raw = strategy_raw.get("symbols")
    if not isinstance(symbols_raw, list) or any(not isinstance(symbol, str) for symbol in symbols_raw):
        raise ValueError("archived strategy.symbols must be an exact symbol list")
    symbols = tuple(symbol.upper() for symbol in symbols_raw)
    if sorted(symbols) != sorted(selected["symbols"]):
        raise ValueError("archived strategy.symbols differ from the contract universe")
    horizons_raw = strategy_raw.get("horizons")
    if not isinstance(horizons_raw, list):
        raise ValueError("archived strategy.horizons are required")
    warmup = strategy_raw.get("warmup_months", 15)
    horizons = validate_horizon_inputs(horizons_raw, warmup)
    lookback = strategy_raw.get("lookback_months")
    if type(lookback) is not int or lookback != warmup:
        raise ValueError("archived strategy.lookback_months must equal the common integer warmup")
    strategy = StrategyConfig(
        strategy_id=_text(strategy_raw.get("id"), "strategy.id"),
        name=_text(strategy_raw.get("name"), "strategy.name"),
        symbols=symbols, lookback_months=lookback,
        sleeve_weight=_numeric(strategy_raw.get("sleeve_weight"), "strategy.sleeve_weight"),
        horizons=horizons, warmup_months=warmup,
    )
    portfolio = PortfolioConfig(_numeric(raw["portfolio"].get("initial_cash"), "portfolio.initial_cash"))
    execution = ExecutionConfig(_numeric(raw["execution"].get("cost_bps"), "execution.cost_bps"))
    benchmark = BenchmarkConfig(
        _numeric(raw["benchmark"].get("exposure"), "benchmark.exposure"),
        _text(raw["benchmark"].get("rebalance"), "benchmark.rebalance").lower(),
    )
    for field, actual, expected in (
        ("strategy_id", strategy.strategy_id, selected["strategy_id"]),
        ("manifest.strategy_id", manifest.get("strategy_id"), selected["strategy_id"]),
        ("horizons", list(horizons), selected["rule"]["horizons"]),
        ("warmup_months", warmup, selected["rule"]["warmup_months"]),
        ("sleeve_weight", strategy.sleeve_weight, selected["rule"]["sleeve_weight"]),
        ("initial_cash", portfolio.initial_cash, selected["initial_cash"]),
        ("cost_bps", execution.cost_bps, selected["grid"]["base"]["cost_bps"]),
        ("benchmark.exposure", benchmark.exposure, selected["benchmark"]["exposure"]),
        ("benchmark.rebalance", benchmark.rebalance, selected["benchmark"]["rebalance"]),
    ):
        require_exact_behavior(actual, expected, f"archived {field}")

    data_raw = raw["data"]
    source = _text(data_raw.get("source"), "data.source").lower()
    expected_source = "synthetic" if selected["synthetic"] else "csv"
    if source != expected_source:
        raise ValueError("archived data.source disagrees with the contract's synthetic provenance")
    if set(data_raw) - {"source"} - _DATA_KEYS_BY_SOURCE[source]:
        raise ValueError("archived data configuration contains source-incompatible fields")
    recorded_source = _text(manifest.get("data_source"), "manifest.data_source")
    if recorded_source != source and not recorded_source.startswith(source + ":"):
        raise ValueError("archived manifest data_source disagrees with embedded config provenance")
    methodology = str(data_raw.get("methodology", "")).strip()
    if ("synthetic-v1" if source == "synthetic" else methodology) != selected["data_methodology"]:
        raise ValueError("archived data methodology differs from the selected contract")
    if source == "synthetic":
        data_start = _iso(data_raw.get("start"), "data.start")
        data_end = _iso(data_raw.get("end"), "data.end")
        if data_start >= data_end:
            raise ValueError("archived synthetic data window is reversed")
        seed = data_raw.get("seed", 0)
        if type(seed) is not int:
            raise ValueError("archived synthetic seed must be an integer")
        if _numeric(data_raw.get("annual_cash_rate", 0.0), "data.annual_cash_rate") <= -1:
            raise ValueError("archived synthetic cash rate must exceed -100%")
        if str(data_raw.get("regime", "trending")).lower() not in ("trending", "random_walk"):
            raise ValueError("archived synthetic regime is unknown")
    else:
        _text(data_raw.get("prices_path"), "data.prices_path")
        _text(data_raw.get("cash_path"), "data.cash_path")
    data = DataConfig(source=source, methodology=methodology)

    # TaxConfig's file path is not policy identity. Validate the full raw policy
    # without resolving that path or reading anything beside it.
    tax_raw = dict(raw["tax"])
    _text(tax_raw.pop("distributions_path", None), "tax.distributions_path")
    # Match the ordinary loader's case normalization for symbol tables/classes.
    for field in ("qualified_fraction", "gains_class"):
        table = tax_raw.get(field)
        if not isinstance(table, dict):
            raise ValueError(f"archived tax.{field} requires an exact symbol table")
        normalized = {symbol.upper(): value for symbol, value in table.items()}
        if len(normalized) != len(table):
            raise ValueError(f"archived tax.{field} has duplicate normalized symbols")
        tax_raw[field] = normalized
    tax_raw["gains_class"] = {symbol: value.lower() if isinstance(value, str) else value for symbol, value in tax_raw["gains_class"].items()}
    _validate_tax_policy(tax_raw)
    # The normal loader stores all policy numbers as floats before hashing.
    for field in ("ordinary_rate", "long_term_rate", "collectibles_rate", "qualified_fraction_low"):
        tax_raw[field] = float(tax_raw[field])
    tax_raw["qualified_fraction"] = {symbol: float(value) for symbol, value in tax_raw["qualified_fraction"].items()}
    tax_digest = canonical_sha256(tax_raw)
    if tax_digest != selected["tax_policy_sha256"] or tax_digest != manifest.get("tax_policy_sha256"):
        raise ValueError("archived tax policy differs from its frozen policy identity")
    if "tax_policy" in selected:
        require_exact_behavior(tax_raw, selected["tax_policy"], "archived tax policy")

    period = _text(raw["evaluation"].get("period"), "evaluation.period").lower()
    if period != manifest.get("evaluation_period") or period not in selected["periods"]:
        raise ValueError("archived evaluation period disagrees with manifest or contract")
    bounds = selected["periods"][period]
    for endpoint in ("start", "end"):
        expected = bounds[endpoint]
        if _iso(raw["backtest"].get(endpoint), f"backtest.{endpoint}") != expected:
            raise ValueError("archived backtest window differs from the complete contracted period")
        for prefix in ("backtest", "evaluation"):
            if _iso(manifest.get(f"{prefix}_{endpoint}"), f"manifest.{prefix}_{endpoint}") != expected:
                raise ValueError("archived manifest window differs from embedded config and contract")
    if source == "synthetic" and (data_start > bounds["start"] or data_end < bounds["end"]):
        raise ValueError("archived synthetic data configuration does not cover the evaluation")
    status = "synthetic" if selected["synthetic"] else bounds["status"]
    if manifest.get("evidence_status") != status:
        raise ValueError("archived evidence status differs from the selected contract")
    if not isinstance(manifest.get("grid"), Mapping) or set(manifest["grid"]) != set(ROWS):
        raise ValueError("archived BA-002 grid has missing or extra gating rows")
    require_digest(manifest.get("strategy_spec_sha256"), "strategy_spec_sha256")
    if _strategy_spec_hash(strategy, portfolio, execution, data, benchmark) != manifest["strategy_spec_sha256"]:
        raise ValueError("archived strategy_spec_sha256 does not match its embedded behavioral config")

    # These are locations and diagnostic groupings, not sources of frozen state.
    _text(raw["report"].get("output_dir"), "report.output_dir")
    for key in ("calendar_path", "freeze_path"):
        _text(raw["research"].get(key), f"research.{key}")
    for key in ("review_dir", "periods_path"):
        if key in raw["evaluation"]:
            _text(raw["evaluation"][key], f"evaluation.{key}")
    clusters = raw.get("clusters", {})
    if not isinstance(clusters, dict):
        raise ValueError("archived clusters must be a diagnostic grouping table")
    _load_clusters(clusters, symbols)
