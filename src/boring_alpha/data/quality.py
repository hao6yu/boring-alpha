"""Plausibility checks for loaded market data.

A backtest is only as honest as its inputs, and a mis-built total-return series
fails quietly: it produces a number rather than an error. These checks look for
the shapes that mistake usually takes — an unadjusted split, a stale feed, a
calendar hole — and separate findings that should stop a run from findings that
should merely be recorded against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from boring_alpha.data.market import MarketData

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    """Defaults chosen so that real crisis sessions pass and data errors do not.

    The largest one-session moves in broad ETFs during 2008 and 2020 were well
    inside 40%, while an unadjusted split or a units mix-up is usually far
    outside it.
    """

    max_session_return: float = 0.40
    max_open_gap: float = 0.25
    min_cash_rate: float = -0.10
    max_cash_rate: float = 0.30
    max_calendar_gap_days: int = 5
    max_stale_closes: int = 10


def _business_days_between(earlier: date, later: date) -> int:
    day, count = earlier + timedelta(days=1), 0
    while day < later:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def _price_findings(
    data: MarketData, symbol: str, thresholds: QualityThresholds
) -> list[Finding]:
    findings: list[Finding] = []
    days = data.symbol_dates.get(symbol, ())
    stale_run = 0
    for index in range(1, len(days)):
        previous, current = data.bar(days[index - 1], symbol), data.bar(days[index], symbol)
        session_return = current.close / previous.close - 1.0
        if abs(session_return) > thresholds.max_session_return:
            findings.append(
                Finding(
                    ERROR,
                    "session_return",
                    f"{symbol} moved {session_return:+.1%} on {days[index]} "
                    f"(limit {thresholds.max_session_return:.0%}); check for an "
                    "unadjusted split or a units mix-up",
                )
            )
        open_gap = current.open / previous.close - 1.0
        if abs(open_gap) > thresholds.max_open_gap:
            findings.append(
                Finding(
                    ERROR,
                    "open_gap",
                    f"{symbol} opened {open_gap:+.1%} from the prior close on "
                    f"{days[index]} (limit {thresholds.max_open_gap:.0%}); check that "
                    "the open and close series share one adjustment basis",
                )
            )
        stale_run = stale_run + 1 if current.close == previous.close else 0
        if stale_run == thresholds.max_stale_closes:
            findings.append(
                Finding(
                    WARNING,
                    "stale_closes",
                    f"{symbol} closed unchanged for {stale_run + 1} consecutive "
                    f"sessions ending {days[index]}; the feed may be stale",
                )
            )
    return findings


def inspect(
    data: MarketData, symbols: tuple[str, ...], thresholds: QualityThresholds
) -> list[Finding]:
    """Findings for the configured symbols, in dataset order."""

    findings: list[Finding] = []
    for symbol in symbols:
        findings.extend(_price_findings(data, symbol, thresholds))

    for day, factor in sorted(data.cash_factors.items()):
        annual = factor**252.0 - 1.0
        if not thresholds.min_cash_rate <= annual <= thresholds.max_cash_rate:
            findings.append(
                Finding(
                    ERROR,
                    "cash_rate",
                    f"cash factor on {day} implies a {annual:+.1%} annual rate, "
                    f"outside {thresholds.min_cash_rate:+.0%}..{thresholds.max_cash_rate:+.0%}; "
                    "cash_factor is a one-session growth factor, not an annual rate",
                )
            )

    shared = [day for day in data.dates if all(symbol in data.by_date[day] for symbol in symbols)]
    for index in range(1, len(shared)):
        missing = _business_days_between(shared[index - 1], shared[index])
        if missing > thresholds.max_calendar_gap_days:
            findings.append(
                Finding(
                    WARNING,
                    "calendar_gap",
                    f"{missing} business days without a shared session between "
                    f"{shared[index - 1]} and {shared[index]}",
                )
            )
    return findings


def enforce(findings: list[Finding]) -> list[str]:
    """Raise on errors; return warning messages for the run to record."""

    errors = [finding for finding in findings if finding.severity == ERROR]
    if errors:
        detail = "\n".join(f"  [{finding.code}] {finding.message}" for finding in errors)
        raise ValueError(f"market data failed {len(errors)} plausibility check(s):\n{detail}")
    return [f"data quality [{finding.code}]: {finding.message}" for finding in findings]
