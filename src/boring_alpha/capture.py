"""BA-004 retention audit: a funded account, six leakage channels, and an audit.

This is deliberately not the trading engine. BA-004 holds one fund and issues no
signals, so importing `backtest.engine` would borrow machinery it neither needs
nor should be forced to validate. What BA-004 needs is a funded account, dated
contributions, independently injectable cost channels, and an audit that can name
which channel moved the number.

Monthly resolution is a declared approximation. Ordering inside a month is pinned
and is part of the model rather than an implementation detail: platform fee, then
contribution invested at the period open, then rebalance to the declared cash
target, then accrual. Cash earns the declared cash rate rather than zero, so an
idle-cash finding is a genuine opportunity cost and not an artefact of pretending
cash is worthless.

Every channel is expressed as a haircut on the position that channel touches, so
that each cost compounds forward from the month it was incurred. A cost deducted
once at the end of a ten-year run would understate itself, and understating a
leak is the one error a retention audit must not be capable of.

Attribution is by single-channel ablation: run once with everything on, then once
per channel with that channel alone disabled. That is not a unique decomposition,
because channels interact, so a residual is computed and reported rather than
buried in the largest channel. A residual the size of the gate would mean the
audit is not additive, and the residual is the only way that would be seen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from boring_alpha.metrics.cashflow import CashFlow, modified_dietz, money_weighted_return

INSTRUMENT_FEE = "instrument selection"
SPREAD = "spread and execution"
CASH_DRAG = "idle cash"
LATENCY = "contribution latency"
PLATFORM_FEE = "platform fee"
BEHAVIOUR = "behavioural violation"
TIER2_CHANNELS = (SPREAD, CASH_DRAG, LATENCY, PLATFORM_FEE)
ABLATED = (INSTRUMENT_FEE,) + TIER2_CHANNELS


@dataclass(frozen=True, slots=True)
class Period:
    """One month: its first day, its day count, and the fund's gross index return."""

    start: date
    days: int
    gross_return: float


@dataclass(frozen=True, slots=True)
class CapturePolicy:
    expense_ratio: float = 0.0007
    spread_bps: float = 3.0
    target_cash_weight: float = 0.0
    latency_days: int = 0
    platform_fee_monthly: float = 0.0
    cash_return: float = 0.04
    violations: int = 0

    @property
    def spread_rate(self) -> float:
        return self.spread_bps / 10_000.0

    def disabled(self, name: str) -> CapturePolicy:
        """The same policy with exactly one channel switched off, for ablation."""

        if name == INSTRUMENT_FEE:
            return replace(self, expense_ratio=0.0)
        if name == SPREAD:
            return replace(self, spread_bps=0.0)
        if name == CASH_DRAG:
            return replace(self, target_cash_weight=0.0)
        if name == LATENCY:
            return replace(self, latency_days=0)
        if name == PLATFORM_FEE:
            return replace(self, platform_fee_monthly=0.0)
        raise ValueError(f"no channel available to disable named {name!r}")


@dataclass(frozen=True, slots=True)
class AuditResult:
    candidate_irr: float
    reference_irr: float
    tier2_shortfall_bps: float
    tier1_tier2_bps: float
    attribution: dict[str, float]
    residual_bps: float
    dietz_cross_check_bps: float
    violations: int
    closing_value: float
    reference_closing_value: float
    total_invested: float
    periods: int

    @property
    def binding_channel(self) -> str:
        return max(self.attribution, key=lambda name: abs(self.attribution[name]))

    @property
    def passes_gate(self) -> bool:
        return self.tier2_shortfall_bps <= 30.0 and self.violations == 0


def _cash_rate(cash_return: float, period: Period) -> float:
    return (1.0 + cash_return) ** (period.days / 365.2425) - 1.0


def _latency_haircut(policy: CapturePolicy, period: Period) -> float:
    """Fractional loss from holding a contribution out of the market for `latency_days`.

    Reference is fully invested for the whole month. The alternative holds cash
    for the latency window and is invested for the remainder, so the cost is the
    return gap across that window and not the whole return on the money.
    """

    held = min(policy.latency_days, period.days)
    if held <= 0 or period.gross_return <= -1.0:
        return 0.0
    idle = 1.0 + _cash_rate(policy.cash_return, period) * held / period.days
    exposed = 1.0 + period.gross_return * (period.days - held) / period.days
    return max(0.0, 1.0 - idle * exposed / (1.0 + period.gross_return))


def _invest(
    units: float, nav: float, amount: float, haircut: float
) -> float:
    """Put external money to work at the period open, net of that month's haircuts."""

    if amount <= 0.0:
        return units
    return units + amount * (1.0 - haircut) / nav


def _rebalance_to_cash(
    cash: float, units: float, nav: float, target_weight: float, spread_rate: float
) -> tuple[float, float]:
    """Move to the declared idle-cash weight, paying the spread on what moves."""

    if target_weight <= 0.0:
        return cash, units
    value = cash + units * nav
    trade = value * target_weight - cash
    if trade > 1e-9:
        notional = trade / (1.0 + spread_rate)
        units -= notional / nav
        cash += notional * (1.0 - spread_rate)
    elif trade < -1e-9:
        notional = -trade / (1.0 + spread_rate)
        units += notional / nav
        cash -= notional * (1.0 + spread_rate)
    return cash, units


def simulate(
    policy: CapturePolicy,
    periods: tuple[Period, ...],
    deposits: tuple[CashFlow, ...],
    opening_value: float,
) -> float:
    """Closing value of the leaky account. Produces a number; explains nothing."""

    if not periods:
        raise ValueError("at least one period is required")
    if opening_value <= 0.0:
        raise ValueError("opening value must be positive")
    if any(flow.date < periods[0].start for flow in deposits):
        raise ValueError("a deposit predates the first period")
    if any(flow.date == periods[0].start for flow in deposits):
        raise ValueError(
            "a deposit dated on the opening date duplicates the opening value; "
            "fold it into the opening value or date it to a later period"
        )
    by_date: dict[date, float] = {}
    for flow in deposits:
        by_date[flow.date] = by_date.get(flow.date, 0.0) + flow.amount

    nav = 1.0
    arrival_haircut = policy.spread_rate + _latency_haircut(policy, periods[0])
    units = _invest(0.0, nav, opening_value, arrival_haircut)
    cash = 0.0

    for index, period in enumerate(periods):
        if policy.platform_fee_monthly:
            cash -= policy.platform_fee_monthly
            if cash < 0.0:
                notional = -cash / (nav * (1.0 - policy.spread_rate))
                units -= notional
                cash += notional * nav * (1.0 - policy.spread_rate)

        if index > 0:
            arrival = by_date.get(period.start, 0.0)
            if arrival:
                units = _invest(
                    units,
                    nav,
                    arrival,
                    policy.spread_rate + _latency_haircut(policy, period),
                )

        cash, units = _rebalance_to_cash(
            cash, units, nav, policy.target_cash_weight, policy.spread_rate
        )

        nav *= (1.0 + period.gross_return) * (
            (1.0 - policy.expense_ratio) ** (period.days / 365.2425)
        )
        cash *= 1.0 + _cash_rate(policy.cash_return, period)

    return cash + units * nav


def _funded_reference(
    periods: tuple[Period, ...],
    deposits: tuple[CashFlow, ...],
    opening_value: float,
    period_factor,
) -> float:
    """A leak-free account carrying identical deposits. A yardstick, not a candidate."""

    value = opening_value
    ordered = sorted(deposits, key=lambda flow: flow.date)
    cursor = 0
    for period in periods:
        while cursor < len(ordered) and ordered[cursor].date <= period.start:
            value += ordered[cursor].amount
            cursor += 1
        value *= period_factor(period)
    while cursor < len(ordered):
        value += ordered[cursor].amount
        cursor += 1
    return value


def audit(
    policy: CapturePolicy,
    periods: tuple[Period, ...],
    deposits: tuple[CashFlow, ...],
    opening_value: float,
    period_end: date,
) -> AuditResult:
    """Measure retention, decompose it, and cross-check the measurement against itself."""

    if not periods:
        raise ValueError("at least one period is required")
    start = periods[0].start
    tier2 = _funded_reference(
        periods, deposits, opening_value, lambda p: (1.0 + p.gross_return) * (
            (1.0 - policy.expense_ratio) ** (p.days / 365.2425)
        )
    )
    tier1 = _funded_reference(
        periods, deposits, opening_value, lambda p: 1.0 + p.gross_return
    )

    irr = money_weighted_return
    closing = simulate(policy, periods, deposits, opening_value)
    candidate_irr = irr(start, opening_value, period_end, closing, deposits)
    reference_irr = irr(start, opening_value, period_end, tier2, deposits)
    gross_irr = irr(start, opening_value, period_end, tier1, deposits)
    dietz_candidate = modified_dietz(start, opening_value, period_end, closing, deposits)
    dietz_reference = modified_dietz(start, opening_value, period_end, tier2, deposits)

    shortfall = (reference_irr - candidate_irr) * 10_000.0
    attribution: dict[str, float] = {}
    for name in TIER2_CHANNELS:
        relieved = simulate(policy.disabled(name), periods, deposits, opening_value)
        attribution[name] = (
            irr(start, opening_value, period_end, relieved, deposits) - candidate_irr
        ) * 10_000.0
    attribution[INSTRUMENT_FEE] = (gross_irr - reference_irr) * 10_000.0

    reported = sum(attribution[name] for name in TIER2_CHANNELS)
    return AuditResult(
        candidate_irr=candidate_irr,
        reference_irr=reference_irr,
        tier2_shortfall_bps=shortfall,
        tier1_tier2_bps=(gross_irr - reference_irr) * 10_000.0,
        attribution=attribution,
        residual_bps=shortfall - reported,
        dietz_cross_check_bps=abs(
            (dietz_reference - dietz_candidate) * 10_000.0 - shortfall
        ),
        violations=policy.violations,
        closing_value=closing,
        reference_closing_value=tier2,
        total_invested=opening_value + sum(flow.amount for flow in deposits),
        periods=len(periods),
    )
