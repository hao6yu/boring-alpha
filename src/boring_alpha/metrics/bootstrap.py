"""Confidence interval for a Sharpe difference, by stationary block bootstrap.

Eleven years of monthly decisions is a small sample. A point estimate of "the
strategy's Sharpe beat the benchmark's by 0.15" invites a conclusion the data
cannot support, so the harness reports an interval beside it. Blocks preserve
the serial dependence in daily returns, and resampling the two series together
preserves the correlation between them.
"""

from __future__ import annotations

import math
import random
import statistics

DEFAULT_RESAMPLES = 2_000
DEFAULT_BLOCK = 21
DEFAULT_CONFIDENCE = 0.90


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    deviation = statistics.stdev(returns)
    if deviation <= 0.0:
        return 0.0
    return statistics.mean(returns) / deviation * math.sqrt(252.0)


def _percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def sharpe_difference_interval(
    strategy_excess: list[float],
    benchmark_excess: list[float],
    *,
    seed: int,
    resamples: int = DEFAULT_RESAMPLES,
    block: int = DEFAULT_BLOCK,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, float]:
    """Point estimate and interval for Sharpe(strategy) − Sharpe(benchmark)."""

    if len(strategy_excess) != len(benchmark_excess):
        raise ValueError("both series must have the same length")
    count = len(strategy_excess)
    if count < 2:
        raise ValueError("at least two observations are required")
    if block < 1:
        raise ValueError("block length must be at least one session")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between 0 and 1")
    if resamples < 1:
        raise ValueError("at least one resample is required")

    point = _sharpe(strategy_excess) - _sharpe(benchmark_excess)
    rng = random.Random(seed)
    continuation = 1.0 - 1.0 / block
    differences: list[float] = []
    for _ in range(resamples):
        strategy_draw: list[float] = []
        benchmark_draw: list[float] = []
        index = rng.randrange(count)
        for _ in range(count):
            strategy_draw.append(strategy_excess[index])
            benchmark_draw.append(benchmark_excess[index])
            # Stay inside the block with probability 1 - 1/block, else jump.
            index = (index + 1) % count if rng.random() < continuation else rng.randrange(count)
        differences.append(_sharpe(strategy_draw) - _sharpe(benchmark_draw))

    differences.sort()
    tail = (1.0 - confidence) / 2.0
    return {
        "point": point,
        "low": _percentile(differences, tail),
        "high": _percentile(differences, 1.0 - tail),
        "confidence": confidence,
        "resamples": float(resamples),
        "seed": float(seed),
    }
