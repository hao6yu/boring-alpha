"""BA-004 scenario grid, run exactly once, against the pre-registered protocol.

Protocol: docs/reviews/BA-004-test-protocol.md. Nothing here selects, reorders or
reinterprets a scenario after seeing a result; the grid and the predictions were
pinned first, and predictions that turned out wrong are printed as wrong.
"""

from __future__ import annotations

import calendar
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boring_alpha.capture import CapturePolicy, Period, audit
from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.metrics.cashflow import CashFlow

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots" / "20260904T192633Z"
SNAPSHOT = SNAPSHOT_DIR / "market_daily.csv"
CASH = SNAPSHOT_DIR / "cash_daily.csv"
SYMBOL = "SPY"
CASH_ANNUAL = 0.04

WINDOWS = {
    "synthetic trending": None,
    "synthetic random walk": None,
    "seen A 2007-06..2017-12": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B 2018-01..2021-12": (date(2018, 1, 1), date(2021, 12, 31)),
}

SCENARIOS = {
    "S-CLEAN": dict(),
    "S-CASH-1": dict(target_cash_weight=0.01),
    "S-CASH-3": dict(target_cash_weight=0.03),
    "S-CASH-8": dict(target_cash_weight=0.08),
    "S-MARKET-ORDER": dict(spread_bps=12.0),
    "S-LATE-10": dict(latency_days=10),
    "S-FIXED-FEE": dict(platform_fee_monthly=10.0),
    "S-BEHAVIOUR-1": dict(violations=1),
    "S-EXPENSIVE-FUND": dict(expense_ratio=0.0042),
}
TEN_X_ONLY = {"S-CLEAN", "S-CASH-3", "S-FIXED-FEE", "S-EXPENSIVE-FUND"}


def month_grid(start: date, months: int) -> list[tuple[date, int]]:
    out, year, month = [], start.year, start.month
    for _ in range(months):
        out.append((date(year, month, 1), calendar.monthrange(year, month)[1]))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def monthly_periods(data, symbol: str, grid: list[tuple[date, int]]) -> tuple[Period, ...]:
    """Close-to-close total return per calendar month, against the prior month's close."""

    closes: dict[tuple[int, int], float] = {}
    for day, bars in data.by_date.items():
        if symbol in bars:
            closes.setdefault((day.year, day.month), bars[symbol].close)
            closes[(day.year, day.month)] = bars[symbol].close
    ordered = sorted(closes)
    lookup = dict(zip(ordered, [closes[key] for key in ordered]))

    periods = []
    for start, days in grid:
        key = (start.year, start.month)
        if key not in lookup:
            continue
        prior = [candidate for candidate in ordered if candidate < key]
        if not prior:
            continue
        previous = lookup[prior[-1]]
        end_year, end_month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
        boundary = [candidate for candidate in ordered if candidate < (end_year, end_month)]
        if not boundary:
            continue
        value = lookup[boundary[-1]]
        periods.append(Period(start, days, value / previous - 1.0))
    return tuple(periods)


def flows(months: int, amount: float, start: date) -> tuple[CashFlow, ...]:
    out, cursor = [], _month_add(start, 1)
    for _ in range(months - 1):
        out.append(CashFlow(cursor, amount))
        cursor = _month_add(cursor, 1)
    return tuple(out)


def _month_add(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 + months
    return date(total // 12, total % 12 + 1, min(day.day, 28))


def window_periods(name: str, grid: list[tuple[date, int]]) -> tuple[Period, ...]:
    bounds = WINDOWS[name]
    if bounds is None:
        regime = "trending" if "trending" in name else "random_walk"
        data = generate_synthetic_market_data(
            (SYMBOL,), grid[0][0], grid[-1][0], seed=20_260_905,
            annual_cash_rate=CASH_ANNUAL, regime=regime,
        )
        return monthly_periods(data, SYMBOL, grid)
    data = load_csv_market_data(SNAPSHOT, CASH, end=bounds[1])
    return monthly_periods(data, SYMBOL, _grid_between(bounds[0], bounds[1]))


def _grid_between(start: date, end: date) -> list[tuple[date, int]]:
    out, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append((date(year, month, 1), calendar.monthrange(year, month)[1]))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def main() -> None:
    report: dict[str, object] = {"scenarios": {}, "regimes": {}}
    scales = {"1x": (2_000.0, 500.0), "10x": (20_000.0, 5_000.0)}

    for scenario, overrides in SCENARIOS.items():
        rows = []
        for regime, bounds in WINDOWS.items():
            grid = (
                month_grid(date(2015, 1, 1), 120)
                if bounds is None
                else _grid_between(bounds[0], bounds[1])
            )
            periods = window_periods(regime, grid)
            if not periods:
                continue
            for scale, (opening, contribution) in scales.items():
                if scale == "10x" and scenario not in TEN_X_ONLY:
                    continue
                policy = CapturePolicy(cash_return=CASH_ANNUAL, **overrides)
                deposit_stream = flows(len(periods), contribution, periods[0].start)
                result = audit(
                    policy, periods, deposit_stream, opening,
                    periods[-1].start.replace(
                        day=calendar.monthrange(periods[-1].start.year, periods[-1].start.month)[1]
                    ),
                )
                rows.append({
                    "scenario": scenario, "regime": regime, "scale": scale,
                    "months": result.periods,
                    "tier2_shortfall_bps": round(result.tier2_shortfall_bps, 3),
                    "tier1_tier2_bps": round(result.tier1_tier2_bps, 3),
                    "residual_bps": round(result.residual_bps, 4),
                    "dietz_check_bps": round(result.dietz_cross_check_bps, 4),
                    "binding_channel": result.binding_channel,
                    "attribution": {k: round(v, 3) for k, v in result.attribution.items()},
                    "passes": result.passes_gate,
                    "closing": round(result.closing_value, 2),
                    "invested": round(result.total_invested, 2),
                })
        report["scenarios"][scenario] = rows

    print(json.dumps(report, indent=2, sort_keys=True))
    digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    print(f"\nresult digest sha256={digest}", file=sys.stderr)
    (ROOT / "experiments" / "BA-004-grid.json").write_text(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
