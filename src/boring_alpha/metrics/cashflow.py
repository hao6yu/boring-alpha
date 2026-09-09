"""Money-weighted returns for accounts that are funded rather than self-financing.

The engine's existing `metrics.performance.calculate_metrics` computes a
time-weighted CAGR as `(end_equity / start_equity) ** (365.2425 / days) - 1`.
That is correct for a self-financing account and meaningless for one that is
contributed to monthly: a funded account's outcome is dominated by when money
arrived, not by how the asset behaved. This module is the missing counterpart.

SIGN CONVENTIONS, because a sign error here is silent and permanent:

* `CashFlow.amount` is positive when money enters the account: a deposit.
  A withdrawal is negative. This is the account's point of view.
* `net_present_value` and `money_weighted_return` evaluate in the investor's
  point of view, where money paid into the account is negative and the closing
  valuation is received back positive. Both convert for you; never pass
  already-signed investor flows.
* `modified_dietz` works in the account's point of view, deposits positive.

`money_weighted_return` and `modified_dietz` are independent estimates of the
same quantity. Both are reported because they disagree when an implementation is
wrong, and agreement between two different formulas is the cheapest available
evidence that neither is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

DAYS_PER_YEAR = 365.2425
SOLVE_FLOOR = -0.9999
SOLVE_CEILING = 50.0
SOLVE_TOLERANCE = 1e-13
SOLVE_MAX_STEPS = 300


@dataclass(frozen=True, slots=True)
class CashFlow:
    """External money crossing the account boundary, from the account's view.

    Positive is a deposit. An internal transfer between cash and positions is
    not a cash flow and must never be recorded as one.
    """

    date: date
    amount: float


class AmbiguousCashFlows(ValueError):
    """An intermediate withdrawal can make the internal rate of return
    multi-valued. Refusing is the correct behaviour: reporting one of several
    roots as if it were the answer is exactly the failure this repository is
    built to prevent."""


def _validate_bounds(opening_value: float, closing_value: float) -> None:
    if opening_value <= 0.0:
        raise ValueError(f"opening value must be positive, got {opening_value}")
    if closing_value < 0.0:
        raise ValueError(f"closing value cannot be negative, got {closing_value}")


def _deposits_only(deposits: tuple[CashFlow, ...]) -> tuple[CashFlow, ...]:
    flows = tuple(flow for flow in deposits if flow.amount)
    if any(flow.amount < 0.0 for flow in flows):
        raise AmbiguousCashFlows(
            "intermediate withdrawal present: with more than one sign change the "
            "internal rate of return can have multiple roots, so no single figure "
            "may be reported. Net the withdrawal against the closing valuation or "
            "split the period at the withdrawal and chain the results."
        )
    return flows


def _discount(period_start: date, day: date) -> float:
    if day < period_start:
        raise ValueError(f"flow dated {day} precedes the period start {period_start}")
    return (day - period_start).days / DAYS_PER_YEAR


def net_present_value(
    period_start: date,
    opening_value: float,
    closing_date: date,
    closing_value: float,
    deposits: tuple[CashFlow, ...],
    rate: float,
) -> float:
    """Investor-convention present value at `rate`: outlays negative, receipt positive."""

    _validate_bounds(opening_value, closing_value)
    if rate <= -1.0:
        raise ValueError(f"rate must exceed -1, got {rate}")
    if closing_date < period_start:
        raise ValueError("closing date cannot precede the period start")
    value = -opening_value
    for flow in deposits:
        if flow.amount:
            value -= flow.amount / (1.0 + rate) ** _discount(period_start, flow.date)
    # The closing valuation is money handed back to the investor, so it enters
    # with the opposite sign to the outlays. Flipping this is the classic silent
    # defect in this calculation: the equation then has no root near the true one.
    value += closing_value / (1.0 + rate) ** _discount(period_start, closing_date)
    return value


def money_weighted_return(
    period_start: date,
    opening_value: float,
    closing_date: date,
    closing_value: float,
    deposits: tuple[CashFlow, ...] = (),
) -> float:
    """Annualised internal rate of return on a funded account.

    With no external flows this reduces exactly to the time-weighted CAGR the rest
    of the repository reports. That identity is the test that the two metrics
    describe one account rather than two.
    """

    _validate_bounds(opening_value, closing_value)
    flows = _deposits_only(deposits)
    elapsed = (closing_date - period_start).days
    if elapsed <= 0:
        raise ValueError("period must span at least one day")
    for flow in flows:
        if flow.date > closing_date:
            raise ValueError(f"deposit dated {flow.date} falls after {closing_date}")
    if not flows:
        return (closing_value / opening_value) ** (DAYS_PER_YEAR / elapsed) - 1.0
    if closing_value == 0.0:
        raise ValueError("a total loss leaves the internal rate of return undefined")

    low, high = SOLVE_FLOOR, SOLVE_CEILING
    low_value = net_present_value(
        period_start, opening_value, closing_date, closing_value, flows, low
    )
    high_value = net_present_value(
        period_start, opening_value, closing_date, closing_value, flows, high
    )
    if low_value * high_value > 0.0:
        raise ValueError(
            f"internal rate of return is not bracketed on ({low}, {high}): "
            f"NPV is {low_value} at the floor and {high_value} at the ceiling"
        )
    for _ in range(SOLVE_MAX_STEPS):
        middle = (low + high) / 2.0
        value = net_present_value(
            period_start, opening_value, closing_date, closing_value, flows, middle
        )
        if value * low_value > 0.0:
            low, low_value = middle, value
        else:
            high = middle
        if high - low < SOLVE_TOLERANCE:
            break
    return (low + high) / 2.0


def modified_dietz(
    period_start: date,
    opening_value: float,
    closing_date: date,
    closing_value: float,
    deposits: tuple[CashFlow, ...] = (),
) -> float:
    """Annualised Modified Dietz return: the independent cross-check.

    Weighting a deposit by the fraction of the period it was present is linear
    where the internal rate of return is multiplicative, so the two diverge as
    flows grow large or late. That divergence is diagnostic, not an error to
    average away. Withdrawals are permitted here, and weighted negative.
    """

    _validate_bounds(opening_value, closing_value)
    elapsed = (closing_date - period_start).days
    if elapsed <= 0:
        raise ValueError("period must span at least one day")
    denominator = opening_value + sum(
        flow.amount * (closing_date - flow.date).days / elapsed
        for flow in deposits
        if flow.amount
    )
    if denominator <= 0.0:
        raise ValueError(
            f"weighted average capital is not positive ({denominator}); Dietz is undefined"
        )
    period_return = (
        closing_value - opening_value - sum(flow.amount for flow in deposits)
    ) / denominator
    if period_return <= -1.0:
        raise ValueError("period return is not annualisable; the account was wiped out")
    return (1.0 + period_return) ** (DAYS_PER_YEAR / elapsed) - 1.0


def shortfall_bps(candidate: float, reference: float) -> float:
    """Shortfall of one annualised return against another, in basis points a year.

    Subtraction, never a ratio: a capture ratio explodes or turns meaningless
    whenever the reference return sits near zero or negative, which would make
    the metric measure rising markets rather than retention.
    """

    return (reference - candidate) * 10_000.0
