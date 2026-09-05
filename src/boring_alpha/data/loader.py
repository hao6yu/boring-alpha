"""The single supported way to obtain market data for a configuration.

Gating and truncation live here rather than in the command line so that the
seal is a property of obtaining data, not a step a future caller might forget.
"""

from __future__ import annotations

import csv
from datetime import date
import io
import json

from boring_alpha.config import AppConfig
from boring_alpha.data.csv_loader import load_csv_market_data, load_csv_market_data_bytes
from boring_alpha.data.market import MarketData
from boring_alpha.data.quality import QualityThresholds, enforce, inspect
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.evaluation import check_evaluation_gates


def _check_methodology(config: AppConfig, inputs=None) -> list[str]:
    """Hold the declared methodology against the snapshot that produced the data.

    Requiring the string without checking it only proves someone typed
    something. The fetcher stamps the same identifier into each snapshot's
    manifest, so the two can be held against each other; data built by hand has
    no manifest, which is allowed but recorded as unverified.
    """

    assert config.data.prices_path is not None
    manifest_path = config.data.prices_path.parent / "manifest.json"
    manifest = inputs.manifest("prices") if inputs is not None else None
    missing = manifest is None if inputs is not None else not manifest_path.is_file()
    if missing:
        return [
            f"data methodology {config.data.methodology!r} is unverified: no "
            f"manifest.json beside {config.data.prices_path.name}"
        ]
    try:
        recorded = (
            manifest if inputs is not None else json.loads(manifest_path.read_text(encoding="utf-8"))
        ).get("methodology")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{manifest_path} could not be read: {exc}") from exc
    if recorded != config.data.methodology:
        raise ValueError(
            f"declared data.methodology {config.data.methodology!r} does not match the "
            f"snapshot at {manifest_path.parent}, which records {recorded!r}. The run "
            "identity would claim a provenance the data does not have."
        )
    return []


def _latest_shared_csv_date(config: AppConfig, inputs=None) -> date | None:
    """Inspect date/symbol metadata only, never prices outside authorized bounds."""
    by_symbol = {symbol: set() for symbol in config.strategy.symbols}
    handle_source = (
        io.StringIO(inputs.sources["prices"].decode("utf-8"), newline="") if inputs is not None
        else config.data.prices_path.open(newline="", encoding="utf-8")
    )
    with handle_source as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "").strip().upper()
            if symbol in by_symbol:
                by_symbol[symbol].add(date.fromisoformat(row["date"]))
    shared = set.intersection(*by_symbol.values())
    return max(shared) if shared else None


def load_market_data(config: AppConfig, unseal_reason: str | None = None, *, context=None) -> MarketData:
    """Return observations only; managed history uses open_run's explicit context.

    Legacy and synthetic callers keep the old return type. No lifecycle or
    approval state is attached to MarketData.
    """
    from boring_alpha.research_access import prepare_run
    if context is None:
        context = prepare_run(config, unseal_reason)
        if context.attempt is not None:
            context.finish(error="managed historical loading requires open_run")
            raise ValueError("use open_run for historical research and retain its explicit RunContext")
    context.verify()
    data = _load_market_data(config, context.inputs)
    context.verify()
    return data

def _load_market_data(config: AppConfig, inputs=None) -> MarketData:
    methodology_warnings: list[str] = []

    if config.data.source == "synthetic":
        assert config.data.start is not None and config.data.end is not None
        data = generate_synthetic_market_data(
            config.strategy.symbols,
            config.data.start,
            config.data.end,
            seed=config.data.seed,
            annual_cash_rate=config.data.annual_cash_rate,
            regime=config.data.regime,
        )
    else:
        assert config.data.prices_path is not None and config.data.cash_path is not None
        if config.evaluation.end is None and config.evaluation.is_evidence:
            latest = _latest_shared_csv_date(config, inputs)
            if latest is not None and config.backtest.end < latest:
                raise ValueError(
                    f"a {config.evaluation.period} run must extend through the latest "
                    f"complete session {latest}, but the configured window ends {config.backtest.end}"
                )
        # Even an explicitly authorized exploratory invocation only exposes its
        # configured scope. The low-level reader filters dates before floats.
        end = config.evaluation.end or config.backtest.end
        if inputs is None:
            data = load_csv_market_data(config.data.prices_path, config.data.cash_path, end=end)
        else:
            data = load_csv_market_data_bytes(inputs.sources["prices"], inputs.sources["cash"], end=end)
        methodology_warnings = _check_methodology(config, inputs)

    if config.evaluation.end is not None:
        data = data.through(config.evaluation.end)
    elif config.evaluation.is_evidence:
        # A period registered as ending at the dataset means exactly that. The
        # registry fixes only its start, so without this a sealed run could stop
        # early and report a favourable sub-period under the period's name.
        shared = data.shared_sessions(config.strategy.symbols)
        if shared and config.backtest.end < shared[-1]:
            raise ValueError(
                f"a {config.evaluation.period} run must extend through the latest "
                f"complete session {shared[-1]}, but the configured window ends "
                f"{config.backtest.end}. Update backtest.end, or trim the dataset "
                "if those sessions are not meant to be in scope."
            )

    # Inspect after truncation: findings should describe the data the run uses,
    # not data the seal has already discarded.
    thresholds = QualityThresholds(**config.quality_overrides)
    warnings = methodology_warnings + enforce(inspect(data, config.strategy.symbols, thresholds))

    # A bounded period declares a window; data that stops well short of it is a
    # gap in the dataset, not a legitimately short run.
    last = data.dates[-1]
    if last < config.backtest.end and (last - config.backtest.end).days < -5:
        warnings.append(
            f"data ends {last}, short of the declared window end "
            f"{config.backtest.end}; metrics cover the shorter period"
        )
    data.warnings = tuple(warnings)
    return data
