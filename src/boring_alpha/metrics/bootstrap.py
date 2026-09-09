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


def moving_block_indices(count: int, block: int, rng: random.Random):
    """Indices of a moving-block resample, yielded one at a time, same draw order as always.

    The walker stays inside a block with probability `1 - 1/block` and jumps otherwise, which is what makes
    the resample stationary: every observation gets a chance to start a block, and the average block length is
    `block`. Extracted from `sharpe_difference_interval` so a second statistic can share one resampling
    discipline rather than invent a second one — a repository with two bootstraps eventually reports two
    different amounts of doubt about the same fact.
    """

    if count < 2:
        raise ValueError("at least two observations are required")
    if block < 1:
        raise ValueError("block length must be at least one session")
    continuation = 1.0 - 1.0 / block
    index = rng.randrange(count)
    while True:
        yield index
        # Draw in this order and no other: the sequence of random numbers is what makes a seeded
        # interval reproducible, and a reordered draw silently changes every published figure.
        if rng.random() < continuation:
            index = (index + 1) % count
        else:
            index = rng.randrange(count)


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
    differences: list[float] = []
    for _ in range(resamples):
        strategy_draw: list[float] = []
        benchmark_draw: list[float] = []
        walk = moving_block_indices(count, block, rng)
        for _ in range(count):
            at = next(walk)
            strategy_draw.append(strategy_excess[at])
            benchmark_draw.append(benchmark_excess[at])
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


def book_power(strategy_returns: list[float], benchmark_returns: list[float], *, opening: float,
               monthly: float, horizons: tuple[int, ...], seed: int, resamples: int = DEFAULT_RESAMPLES,
               block: int = 3, power: float = 0.80, edge_monthly: float = 0.0) -> list[dict]:
    """What a paper book can detect, month by month, before it is asked to mean anything.

    A journal that reports "underpowered — 23 more entries" has said one true thing and left the useful
    question unasked: *how much edge would it take, at this deposit schedule, for this book to see it?* The
    answer is a property of the schedule and the volatility, not of the strategy, so it can be computed now —
    and it is computed here so that a future null result can be read as a fact about the instrument rather
    than as news.

    Method. Monthly returns are resampled in pairs by `moving_block_indices`, so the correlation between the
    strategy and its benchmark survives and the null hypothesis has no edge to find: the strategy series is
    shifted so its mean difference against the benchmark is exactly zero. Each resample is then run as an
    account — `opening` at month zero, `monthly` deposited at the start of every month, into both books — and
    the terminal *dollar* gap is recorded. The minimum detectable edge is the constant monthly dollar subsidy
    that would be exceeded by the observed gap with probability `power`, against the 95th percentile of that
    null. Subsidies are compounded at the simulated strategy's own returns, because an edge delivered in month
    one is worth more than the same edge in month thirty, and a power analysis that ignores that flatters the
    book.
    """

    if len(strategy_returns) != len(benchmark_returns):
        raise ValueError("both series must have the same length")
    if len(strategy_returns) < 2:
        raise ValueError("at least two observations are required")
    if resamples < 1:
        raise ValueError("at least one resample is required")
    if not 0.0 < power < 1.0:
        raise ValueError("power must lie strictly between 0 and 1")
    longest = max(int(h) for h in horizons)
    if longest < 1:
        raise ValueError("a book one month old detects nothing, including this")

    shift = statistics.fmean(a - b for a, b in zip(strategy_returns, benchmark_returns))
    null_strategy = [r - shift for r in strategy_returns]
    rng = random.Random(seed)
    if longest > len(null_strategy):
        # Truncating silently would report a 120-month power figure computed on 60 months of history, which
        # reads like a far stronger instrument than the archive can support.
        raise ValueError(f"a {longest}-month horizon needs {longest} monthly observations, the series has "
                         f"{len(null_strategy)}")
    # gaps[h][i] = terminal dollar gap, subsidy_factor[h][i] = what $1 a month compounding to month h became
    gaps: dict[int, list[float]] = {int(h): [] for h in horizons}
    factors: dict[int, list[float]] = {int(h): [] for h in horizons}
    for _ in range(resamples):
        walk = moving_block_indices(len(null_strategy), block, rng)
        strat_value = bench_value = opening
        subsidy = 0.0                     # units: "one dollar a month, compounded at the strategy's returns"
        for month in range(1, longest + 1):
            at = next(walk)
            r_s, r_b = null_strategy[at], benchmark_returns[at]
            # Deposit at the start of the month, so the month's return is earned on the deposit too: the same
            # convention the book uses when a transfer arrives on a session rather than after it.
            strat_value = (strat_value + monthly) * (1.0 + r_s)
            bench_value = (bench_value + monthly) * (1.0 + r_b)
            subsidy = subsidy * (1.0 + r_s) + 1.0
            if month in gaps:
                gaps[month].append(strat_value - bench_value)
                factors[month].append(subsidy)
    out = []
    for month in sorted(gaps):
        observed = gaps[month]
        if not observed:
            continue
        ordered = sorted(observed)
        threshold = _percentile(ordered, 0.95)
        se = statistics.pstdev(observed)
        scaled = sorted(g + edge_monthly * f for g, f in zip(observed, factors[month]))
        achieved = sum(1 for g in scaled if g > threshold) / len(scaled)
        mde = _mde(observed, factors[month], threshold, power)
        out.append({"months": month, "se": se, "p05": _percentile(ordered, 0.05),
                    "p50": _percentile(ordered, 0.50), "p95": threshold, "mde_monthly": mde,
                    "power_at_edge": achieved, "edge_monthly": edge_monthly, "resamples": float(resamples),
                    "block": float(block), "seed": float(seed)})
    return out


def _mde(observed: list[float], factors: list[float], threshold: float, power: float) -> float:
    """Smallest constant monthly dollar edge whose gap clears `threshold` `power` of the time."""

    lo, hi = 0.0, 1.0
    while _achieved(observed, factors, threshold, hi) < power and hi < 1e7:
        hi *= 2.0
    if hi >= 1e7:
        return float("inf")
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _achieved(observed, factors, threshold, mid) >= power:
            hi = mid
        else:
            lo = mid
    return hi


def _achieved(observed: list[float], factors: list[float], threshold: float, edge: float) -> float:
    return sum(1 for g, f in zip(observed, factors) if g + edge * f > threshold) / len(observed)
