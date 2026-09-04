"""The single supported way to obtain market data for a configuration.

Gating and truncation live here rather than in the command line so that the
seal is a property of obtaining data, not a step a future caller might forget.
"""

from __future__ import annotations

from boring_alpha.config import AppConfig
from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.data.market import MarketData
from boring_alpha.data.quality import QualityThresholds, enforce, inspect
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.evaluation import check_evaluation_gates


def load_market_data(config: AppConfig, unseal_reason: str | None = None) -> MarketData:
    check_evaluation_gates(config, unseal_reason)

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
        data = load_csv_market_data(config.data.prices_path, config.data.cash_path)

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
    warnings = enforce(inspect(data, config.strategy.symbols, thresholds))

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
