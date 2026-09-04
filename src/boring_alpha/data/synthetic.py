"""Deterministic synthetic data used only to exercise the laboratory."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import math
import random

from boring_alpha.domain import PriceBar
from boring_alpha.data.market import MarketData

TRENDING = "trending"
RANDOM_WALK = "random_walk"
REGIMES = (TRENDING, RANDOM_WALK)


def _business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def generate_synthetic_market_data(
    symbols: tuple[str, ...],
    start: date,
    end: date,
    *,
    seed: int,
    annual_cash_rate: float,
    regime: str = TRENDING,
) -> MarketData:
    """Generate reproducible price paths; never use this output as market evidence.

    `trending` builds slow regime cycles that any trend rule will trade well, so
    it exercises the machinery but flatters the strategy. `random_walk` is the
    negative control: driftless and memoryless, it is the series on which a
    trend rule should earn nothing and still pay costs.
    """

    if regime not in REGIMES:
        raise ValueError(f"regime must be one of {', '.join(REGIMES)}")

    days = _business_days(start, end)
    daily_cash_factor = (1.0 + annual_cash_rate) ** (1.0 / 252.0)
    cash_factors = {day: daily_cash_factor for day in days}
    bars: list[PriceBar] = []

    for symbol_index, symbol in enumerate(symbols):
        stable = int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:8], "big")
        rng = random.Random(seed + stable)
        close = 80.0 + 7.0 * symbol_index
        for index, day in enumerate(days):
            if regime == TRENDING:
                cycle = math.sin(index / 180.0 + symbol_index * 0.7)
                drift = 0.00018 + 0.00045 * cycle
            else:
                drift = 0.0
            volatility = 0.007 + 0.001 * (symbol_index % 4)
            overnight = rng.gauss(drift * 0.25, volatility * 0.35)
            intraday = rng.gauss(drift * 0.75, volatility * 0.94)
            open_price = max(0.01, close * (1.0 + overnight))
            close = max(0.01, open_price * (1.0 + intraday))
            bars.append(PriceBar(day, symbol, open_price, close))

    return MarketData(
        bars,
        cash_factors,
        source=(
            f"synthetic:regime={regime}:seed={seed}:start={start}:end={end}"
            f":cash={annual_cash_rate}"
        ),
    )
