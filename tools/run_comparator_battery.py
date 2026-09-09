"""Comparator battery: what would doing nothing in each fund have paid?

BA-004's charter scored a strategy against its own index. That question is too
easy, and this tool exists because of it. The decision a real account actually
faces is not "am I tracking my index closely" but "should I be doing this at all,
or should I buy an ETF on a Sunday night and never look again". A strategy that
tracks its index perfectly and therefore matches plain DCA into that index has
delivered nothing except the fees it charged.

So this computes the plain-DCA outcome for every instrument in the archive, on
the identical contribution schedule, and prints the frontier. Anything the repo
proposes later has to beat a row in this table, net of its costs, using a
comparator chosen before the result is seen.

Costs here are the published expense ratios of the actual share classes behind
the archived prices (SPY charges 9.45 bps, not the 7 bps placeholder used in the
BA-004 grid — see the note in that result). No spread, no slippage, no platform
fee: this is the ceiling on doing nothing, so the comparison is generous to it.
"""

from __future__ import annotations

import calendar
import sys
from datetime import date
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "src"))

from boring_alpha.capture import Period
from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.metrics.cashflow import CashFlow, money_weighted_return
from run_ba004_audit import (  # noqa: E402
    CASH,
    SNAPSHOT,
    _grid_between,
    _month_add,
    flows,
    monthly_periods,
)

OPENING = 5_000.0
MONTHLY = 500.0

# Published net expense ratios, spot of the share class behind each archived
# price. Any figure here that is wrong makes the comparator *harder* to beat
# only if it is too low, so the conservative direction is to overstate them.
#: Round 94. The comment above this table claimed that any wrong figure here made the comparator harder to beat "only if it
#: is too low, so the conservative direction is to overstate them" — and the table then *understated* EEM by 40 bps and DBC
#: by 19, while overstating the two Treasuries by 23 and 33. Four of eight legs were wrong, two of them in the flattering
#: direction, in a file whose whole job is to price the bar. The values now come from `fund_fees.py`.
import fund_fees                                # noqa: E402

EXPENSE = {symbol: fund_fees.fee_for(symbol) for symbol in
           ("SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC")}

WINDOWS = {
    "seen A 2007-06..2017-12": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B 2018-01..2021-12": (date(2018, 1, 1), date(2021, 12, 31)),
}


def portfolio_periods(symbol_periods: dict[str, tuple[Period, ...]]) -> tuple[Period, ...]:
    """Rebalanced-to-equal-weight monthly, across whatever sleeves are present."""

    base = symbol_periods["SPY"]
    out = []
    for index, period in enumerate(base):
        legs = [
            sp[index].gross_return
            for sp in symbol_periods.values()
            if index < len(sp) and sp[index].start == period.start
        ]
        blended = sum(legs) / len(legs)
        out.append(Period(period.start, period.days, blended))
    return tuple(out)


def funded_path(
    periods: tuple[Period, ...],
    deposits: tuple[CashFlow, ...],
    opening: float,
    expense: float,
    period_factor,
) -> tuple[float, float, float]:
    """Ending value, money-weighted return, worst brokerage-app drawdown."""

    value = opening
    peak = opening
    worst = 0.0
    ordered = sorted(deposits, key=lambda flow: flow.date)
    cursor = 0
    for period in periods:
        while cursor < len(ordered) and ordered[cursor].date <= period.start:
            value += ordered[cursor].amount
            cursor += 1
        value *= period_factor(period) * ((1.0 - expense) ** (period.days / 365.2425))
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    while cursor < len(ordered):
        value += ordered[cursor].amount
    last = periods[-1].start
    period_end = last.replace(day=calendar.monthrange(last.year, last.month)[1])
    irr = money_weighted_return(periods[0].start, opening, period_end, value, deposits)
    return value, irr, worst


def main() -> None:
    print(f"schedule: ${OPENING:,.0f} opening + ${MONTHLY:,.0f}/month, all prices gross-of-tax\n")
    for name, bounds in WINDOWS.items():
        data = load_csv_market_data(SNAPSHOT, CASH, end=bounds[1])
        grid = _grid_between(bounds[0], bounds[1])
        per_symbol = {s: monthly_periods(data, s, grid) for s in EXPENSE}
        months = min(len(p) for p in per_symbol.values())
        deposits = tuple(
            CashFlow(_month_add(bounds[0], n), MONTHLY) for n in range(1, months)
        )
        total_in = OPENING + MONTHLY * (months - 1)

        candidates: list[tuple[str, tuple[Period, ...], float]] = [
            (s, p, EXPENSE[s]) for s, p in per_symbol.items()
        ]
        candidates.append(("equal-weight all 8, monthly", portfolio_periods(per_symbol), 0.0030))
        candidates.append((
            "all-weather-ish 40/20/20/20 (SPY/IEF/GLD/DBC)",
            _blend(per_symbol, {"SPY": 0.40, "IEF": 0.20, "GLD": 0.20, "DBC": 0.20}),
            0.0030,
        ))

        print(f"--- {name}: {months} months, ${total_in:,.0f} paid in ---")
        rows = []
        for label, periods, expense in candidates:
            end, irr, dd = funded_path(
                periods[:months], deposits, OPENING, expense, lambda p: 1.0 + p.gross_return
            )
            rows.append((end, irr, dd, label))
        best = max(end for end, _i, _d, _l in rows)
        for end, irr, dd, label in sorted(rows, reverse=True):
            gap = best - end
            print(
                f"  {label:<40} ${end:>10,.0f}  irr {irr*100:>6.2f}%  "
                f"worst dd {dd*100:>6.1f}%  vs best ${gap:>8,.0f}"
            )
        plain_spy = next(r for r in rows if r[3] == "SPY")
        print(f"  comparator to beat: SPY DCA at ${plain_spy[0]:,.0f} / {plain_spy[1]*100:.2f}%\n")


def _blend(per_symbol, weights):
    base = per_symbol["SPY"]
    out = []
    for index, period in enumerate(base):
        total = 0.0
        for symbol, weight in weights.items():
            sp = per_symbol[symbol]
            if index < len(sp) and sp[index].start == period.start:
                total += weight * sp[index].gross_return
        out.append(Period(period.start, period.days, total))
    return tuple(out)


if __name__ == "__main__":
    main()
