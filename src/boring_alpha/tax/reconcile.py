"""Validate a replay against the archived account, independently of tax lots.

The tax identities alone cannot detect missing trades: both sides are built
from the same ledger. Reconstruct cash and adjusted-unit positions here, then
compare every session with the separately archived equity curve. This does not
run a strategy or infer any missing orders.
"""

from __future__ import annotations

from collections import defaultdict
import math

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult


# CSVs retain Python's round-trip float representation. These tolerances admit
# accumulated floating-point error and the engine's near-zero cash clamp,
# rather than rounding away discrepancies at brokerage statement precision.
RELATIVE_TOLERANCE = 1e-9
DOLLAR_TOLERANCE = 1e-7


def _finite(label: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"replay {label} must be finite, got {value!r}")


def _equal(label: str, actual: float, expected: float) -> None:
    if not math.isclose(
        actual, expected, rel_tol=RELATIVE_TOLERANCE, abs_tol=DOLLAR_TOLERANCE
    ):
        raise ValueError(
            f"replay {label} mismatch: archived {actual!r}, reconstructed {expected!r}"
        )


def validate_replay(result: BacktestResult, data: MarketData, initial_cash: float) -> None:
    """Refuse inconsistent, non-finite or incomplete archived account histories."""

    _finite("initial cash", initial_cash)
    _finite("initial equity", result.initial_equity)
    if initial_cash <= 0.0:
        raise ValueError("replay initial cash must be positive")
    _equal("initial equity", result.initial_equity, initial_cash)
    curve = result.equity_curve
    if len(curve) < 2:
        raise ValueError("replay needs at least two equity observations")
    sessions = tuple(point.date for point in curve)
    if tuple(sorted(set(sessions))) != sessions:
        raise ValueError("replay equity dates must be unique and chronological")
    expected_sessions = tuple(day for day in data.dates if sessions[0] <= day <= sessions[-1])
    if sessions != expected_sessions:
        raise ValueError("replay equity curve must cover every market session in its window")

    session_set = set(sessions)
    fills_by_date = defaultdict(list)
    seen = set()
    previous_fill_date = None
    for fill in result.fills:
        label = f"{fill.symbol} on {fill.date}"
        if fill.date not in session_set:
            raise ValueError(f"replay fill {label} is outside the equity curve")
        if previous_fill_date is not None and fill.date < previous_fill_date:
            raise ValueError("replay fills must be chronological")
        previous_fill_date = fill.date
        if (fill.date, fill.symbol) in seen:
            raise ValueError(f"replay has duplicate fills for {label}")
        seen.add((fill.date, fill.symbol))
        if fill.side not in ("BUY", "SELL"):
            raise ValueError(f"replay fill {label} has invalid side {fill.side!r}")
        for field in ("quantity", "price", "notional", "cost", "intended_notional", "reference_price"):
            value = getattr(fill, field)
            _finite(f"{label} {field}", value)
            if value < 0.0 or (field in ("price", "reference_price") and value == 0.0):
                raise ValueError(f"replay fill {label} has invalid {field}: {value!r}")
        _equal(f"{label} notional", fill.notional, fill.quantity * fill.price)
        _equal(f"{label} execution price", fill.price, data.bar(fill.date, fill.symbol).open)
        if fill.notional - fill.intended_notional > DOLLAR_TOLERANCE:
            raise ValueError(f"replay fill {label} exceeds its intended notional")
        fills_by_date[fill.date].append(fill)

    cash = initial_cash
    positions: dict[str, float] = defaultdict(float)
    for index, point in enumerate(curve):
        day = point.date
        for field in ("equity", "cash", "gross_exposure"):
            _finite(f"{day} {field}", getattr(point, field))
        if index:
            cash *= data.cash_factors[day]
        for fill in fills_by_date[day]:
            if fill.side == "BUY":
                positions[fill.symbol] += fill.quantity
                cash -= fill.notional + fill.cost
            else:
                positions[fill.symbol] -= fill.quantity
                cash += fill.notional - fill.cost
            if positions[fill.symbol] * fill.price < -DOLLAR_TOLERANCE:
                raise ValueError(f"replay sells more {fill.symbol} than held on {day}")
        if cash < -DOLLAR_TOLERANCE:
            raise ValueError(f"replay cash becomes negative on {day}: {cash!r}")
        # Match the account's documented floating-point clamp, not its archived
        # balance. The following comparisons remain independent of that balance.
        if abs(cash) < 1e-9:
            cash = 0.0
        exposure = sum(quantity * data.bar(day, symbol).close for symbol, quantity in positions.items())
        _equal(f"{day} cash", point.cash, cash)
        _equal(f"{day} exposure", point.gross_exposure, exposure)
        _equal(f"{day} equity", point.equity, cash + exposure)
