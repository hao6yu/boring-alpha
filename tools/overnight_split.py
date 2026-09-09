"""Where an index ETF's return actually accrues: overnight, or intraday.

Run: .venv/bin/python tools/overnight_split.py [--symbol SPY]

This exists to answer a question that decides the shape of the whole search, and
that nobody in this repository has measured. Any strategy that is flat when the
market is closed pays a round trip for every night it wants exposure to. So the
first thing worth knowing is how much return those nights actually carry, and
whether it can possibly survive the toll.

The decomposition is exact, not approximate:

    close(t) / close(t-1)  =  [open(t) / close(t-1)]  *  [close(t) / open(t)]
        full day                     overnight                 intraday

Two caveats that matter, both stated rather than buried. The archive holds
total-return series, so distributions are reinvested into the adjustment and land
on their ex-date; the split will attribute them wherever that day's bar opens,
which puts a small, spiky bias on the overnight leg. And a strategy that captures
only the overnight leg is not *adding* that return relative to holding: the holder
already owns it. This table measures the size of a prize and the toll to collect
it, nothing more.

    .venv/bin/python tools/overnight_split.py --cost-bps 0.5 --cost-bps 1 --cost-bps 2
"""

from __future__ import annotations

import argparse
import math
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boring_alpha.data.csv_loader import load_csv_market_data

SNAPSHOT = ROOT / "data" / "snapshots" / "20260904T192633Z" / "market_daily.csv"
CASH_FILE = ROOT / "data" / "snapshots" / "20260904T192633Z" / "cash_daily.csv"

WINDOWS = {
    "full 1993..2026": (date(1993, 1, 1), date(2026, 9, 30)),
    "seen A 2007-06..2017-12": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B 2018..2021": (date(2018, 1, 1), date(2021, 12, 31)),
    "recent 2022..2026": (date(2022, 1, 1), date(2026, 9, 30)),
}
DAILY_TURNOVER = 252.0


def legs(data, symbol: str, bounds):
    dates = [d for d in data.dates if d >= bounds[0] and symbol in data.by_date[d]]
    overnight, intraday, full = [], [], []
    for index in range(1, len(dates)):
        prior, day = data.by_date[dates[index - 1]][symbol], data.by_date[dates[index]][symbol]
        on = day.open / prior.close - 1.0
        intra = day.close / day.open - 1.0
        if on <= -1.0 or intra <= -1.0:
            continue
        overnight.append(on)
        intraday.append(intra)
        full.append(day.close / prior.close - 1.0)
    return overnight, intraday, full


def annualised(returns):
    if not returns:
        return 0.0, 0.0
    total = math.prod(1.0 + r for r in returns)
    years = len(returns) / DAILY_TURNOVER
    return total ** (1.0 / years) - 1.0, total


def sharpe(returns):
    """Annualised, no cash deduction: this compares two legs of the same asset."""

    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    deviation = math.sqrt(variance * DAILY_TURNOVER)
    return mean * DAILY_TURNOVER / deviation if deviation else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--cost-bps", type=float, action="append", default=None,
                        help="one-way cost per leg, repeatable")
    args = parser.parse_args()
    costs = args.cost_bps or [0.3, 1.0, 2.0]
    data = load_csv_market_data(SNAPSHOT, CASH_FILE, end=date(2026, 9, 30))

    print(f"{args.symbol}: overnight vs intraday, and the toll to trade the nights\n")
    for label, bounds in WINDOWS.items():
        overnight, intraday, full = legs(data, args.symbol, bounds)
        if len(full) < 200:
            continue
        on_ann, on_total = annualised(overnight)
        in_ann, in_total = annualised(intraday)
        full_ann, full_total = annualised(full)
        print(f"=== {label}  ({len(full)} sessions) ===")
        print(f"  overnight  close->open   {on_ann * 100:>7.2f}%/yr   growth {on_total:>9.1f}x   "
              f"sharpe {sharpe(overnight):>5.2f}")
        print(f"  intraday   open->close   {in_ann * 100:>7.2f}%/yr   growth {in_total:>9.1f}x   "
              f"sharpe {sharpe(intraday):>5.2f}")
        print(f"  held all day            {full_ann * 100:>7.2f}%/yr   growth {full_total:>9.1f}x   "
              f"sharpe {sharpe(full):>5.2f}")
        share = (math.log1p(on_ann) / math.log1p(full_ann) * 100.0) if full_ann > 0 else 0.0
        print(f"  the nights are {share:.0f}% of the compounding")
        print("  a nightly round trip costs, at 252 trips a year:")
        for one_way in costs:
            drag = 2.0 * one_way / 10_000.0 * DAILY_TURNOVER
            net = on_ann - drag
            print(f"    {one_way:>4.1f} bps/leg -> {drag * 100:>6.1f}%/yr toll   "
                  f"overnight-only net {net * 100:>+6.2f}%/yr   "
                  f"{'clears' if net > full_ann else 'BELOW'} just holding ({full_ann * 100:.2f}%)")
        print()

    print("The overnight leg is not additive: a holder already owns it. So the")
    print("night-only row can only ever matter if it beats the holder, and the toll")
    print("is the reason it is hard. What the split *is* good for is telling a")
    print("session-aware model which half of the day to be long in.")


if __name__ == "__main__":
    main()
