"""The single supported way to obtain market data for a configuration.

Gating and truncation live here rather than in the command line so that the
seal is a property of obtaining data, not a step a future caller might forget.
"""

from __future__ import annotations

from boring_alpha.config import AppConfig
from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.data.market import MarketData
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
    return data
