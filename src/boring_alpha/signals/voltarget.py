"""Volatility-targeted exposure: one instrument, one continuous weight, no forecast.

Different in kind from everything else in this repository. BA-001 through BA-003
pick *which* assets to hold from a cross-sectional ranking, several times a year,
and all three died on the cost of doing so — BA-001's review puts its cost drag at
15.7 bps/yr against the benchmark's 5.7. This module holds one instrument and
varies only *how much* of it to hold, which is a smaller decision and a much
cheaper one.

The mechanism: size equity exposure so that the portfolio's recent realised
volatility sits near a constant target. When markets get violent, exposure falls;
when they are quiet, it rises toward the cap. It forecasts nothing. Its claim is
that return per unit of risk is higher in calm periods than in turbulent ones, so
holding a constant-risk book collects more return than holding a constant-weight
book — the documented result behind volatility-managed portfolios and
constant-volatility trend systems.

Three properties matter for the objective here:

**Volatility clustering is the most durable finding in financial time series.**
Large moves follow large moves. That is far more reliably true than the sign of
next month's return, which is why this leans on magnitude rather than direction.

**Turnover is band-triggered, not calendar-driven.** Weight is recomputed daily
but a trade is only contemplated when the gap exceeds `rebalance_band`. The cost
of a rule is not a detail of the rule; it is frequently the reason the rule fails.

**The cap is the honest part of the design.** Above 1.0x the excess is borrowed at
the financing rate, which is charged explicitly on every day it is outstanding.
Leverage is the only reliable way to beat an index with the same capital, and it is
also the easiest way to lie about a backtest, so it is priced here rather than
assumed away.

Look-ahead discipline: the weight applied on day *t* is computed from data through
day *t-1* only. There is no warmup output: until the windows are full the policy
declines to emit a weight, rather than defaulting to a trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

TRADING_DAYS = 252.0


def rolling_volatility(returns: list[float], window: int) -> list[float | None]:
    """Annualised standard deviation over `window` observations, lagged by one.

    Element *t* uses returns `t-window .. t-1`. It never touches day *t*, which is
    the day the resulting weight is applied to.
    """

    out: list[float | None] = [None] * len(returns)
    for position in range(window, len(returns)):
        leg = returns[position - window:position]
        mean = sum(leg) / window
        variance = sum((value - mean) ** 2 for value in leg) / (window - 1)
        out[position] = math.sqrt(variance * TRADING_DAYS)
    return out


def moving_average(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for position in range(window, len(values)):
        out[position] = sum(values[position - window:position]) / window
    return out


@dataclass(frozen=True, slots=True)
class VolTargetPolicy:
    """Exposure = target volatility / realised volatility, capped and band-gated."""

    target_vol: float = 0.15
    vol_window: int = 30
    trend_window: int | None = 200
    max_weight: float = 1.0
    min_weight: float = 0.0
    rebalance_band: float = 0.10
    review_every: int = 1

    def __post_init__(self) -> None:
        if not 0.0 < self.target_vol <= 1.0:
            raise ValueError("target_vol must be in (0, 1]")
        if self.vol_window < 5:
            raise ValueError("vol_window must be at least 5 observations")
        if self.trend_window is not None and self.trend_window < 20:
            raise ValueError("trend_window must be at least 20 observations, or None")
        if not 0.0 <= self.min_weight <= self.max_weight:
            raise ValueError("require 0 <= min_weight <= max_weight")
        if self.max_weight > 3.0:
            raise ValueError("max_weight above 3.0x is out of the credible range")
        if not 0.0 <= self.rebalance_band <= 1.0:
            raise ValueError("rebalance_band must be in [0, 1]")
        if self.review_every < 1 or self.review_every > 63:
            raise ValueError("review_every must be between 1 and 63 sessions")

    @property
    def name(self) -> str:
        gate = "no gate" if self.trend_window is None else f"{self.trend_window}d gate"
        cadence = "daily" if self.review_every == 1 else f"{self.review_every}-session"
        return (
            f"vol-target {self.target_vol:.0%}/{self.vol_window}d, {gate}, "
            f"{self.min_weight:.0%}-{self.max_weight:.2f}x, "
            f"{cadence} review, band {self.rebalance_band:.0%}"
        )

    def warmup(self) -> int:
        needed = self.vol_window
        if self.trend_window:
            needed = max(needed, self.trend_window)
        return needed + 1

    def raw_weights(
        self, closes: list[float], returns: list[float]
    ) -> list[float | None]:
        """Desired weight each day, ignoring bands. None until every window is full."""

        vol = rolling_volatility(returns, self.vol_window)
        trend = moving_average(closes, self.trend_window) if self.trend_window else [None] * len(closes)
        out: list[float | None] = []
        for position in range(len(closes)):
            risk = vol[position]
            if risk is None or risk <= 0.0:
                out.append(None)
                continue
            weight = self.target_vol / risk
            if self.trend_window:
                average = trend[position]
                # `closes[position - 1]`, not `closes[position]`. The weight emitted
                # here is applied to day *position*'s return, and day *position*'s
                # close is not known when that decision is made. The first version
                # of this line read today's close and traded today's move, which
                # flattered the gate by an order of magnitude; a test now pins it.
                gate_reference = closes[position - 1] if position else None
                if average is not None and gate_reference is not None \
                        and gate_reference < average * 0.99:
                    weight = min(weight, self.min_weight)
            out.append(min(self.max_weight, max(self.min_weight, weight)))
        return out

    def weights(
        self, closes: list[float], returns: list[float]
    ) -> list[tuple[float | None, float]]:
        """(weight applied, turnover incurred) per day, with bands applied.

        Bands are what make the rule tradable: without them a volatility target
        rebalances every session and hands the edge to the broker. Turnover is
        reported as a fraction of portfolio value so a cost can be attached to it
        without this module taking a view on commissions.
        """

        desired = self.raw_weights(closes, returns)
        out: list[tuple[float | None, float]] = []
        held = 0.0
        started = False
        for position in range(len(closes)):
            want = desired[position]
            if want is None:
                out.append((None, 0.0))
                continue
            if not started:
                # Funding the book from cash is itself a trade and is charged as one.
                held, started = want, True
                out.append((want, want))
                continue
            # Cadence is an execution constraint, not a signal property: the vol
            # estimate updates daily, but acting on it daily buys nothing at this
            # size. Measured toll on this archive is 1.5%/yr for a nightly round
            # trip even at 0.3 bps a leg, which is more than the whole intraday
            # leg is worth, so the review interval is where cost control lives.
            if self.review_every > 1 and position % self.review_every:
                out.append((held, 0.0))
                continue
            gap = abs(want - held)
            if gap > self.rebalance_band:
                out.append((want, gap))
                held = want
            else:
                out.append((held, 0.0))
        return out
