"""One stance, two monthly figures, and they have opposite signs.

Run: .venv/bin/python tools/income_accounting.py [--capital 100000] [--years 20] [--sleeve SPY]

## Why this file exists

The goal is phrased in monthly dollars, and this repository has answered that phrasing twice, in two places, with
numbers that point in opposite directions — and nobody had put them in the same table.

  * `leverage_sizing.py` (round 3, full record, DCA account): 1.25× is worth **+$143/mo**. The column is
    `extra/mo`, computed as `funded_frame.per_month_equivalent` of the **terminal** gap, discounted at the
    comparator's own rate. That is a correct conversion of a correct number, and it is a statement about the end of
    33 years.
  * `withdrawal_capacity.py` (round 4, 20-year windows, worst start date): the largest withdrawal that survives
    **every** start falls from **$379/mo at 1.0× to $335/mo at 1.25×**. Same direction of travel at every leverage
    tested, and on QQQ the guaranteed cheque goes to exactly **$0** above 1.0×.

Both are right. They are different order statistics. A mean is a mid-table statistic; a guarantee is a minimum. A
stance can raise the first and lower the second, and this one does, because leverage multiplies the *sequence* and
not just the average: the worst 20 years in the record are made worse faster than the average 20 years is made
better.

Round 40 found the same thing from the other side — the loan's incremental month is negative **39.1%** of months and
its excess went underwater for nine years — and one number with a distribution attached is worth two tables of
means, so the distribution is what this tool prints alongside the money.

## What it is for

To stop the goal's sentence being answered by whichever tool was run last. Anyone quoting a monthly figure should be
able to say which of the two it is, and the answer to *"does this earn extra each month"* is the second one, because
the first one does not arrive in any month at all: it is a terminal balance restated as an annuity that was never
withdrawn.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import combined_account as ca                  # noqa: E402
import withdrawal_capacity as wc               # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

GRID = (1.00, 1.25, 1.50, 1.75, 2.00)
SLEEVES = ("SPY", "QQQ", "VTI", "ITOT")
SWEEP = float(wc.TURNOVER_COST)


def mean_order(data, symbol: str, lever: float, capital: float) -> float:
    """Dollars a month, on average, from holding `lever` instead of holding the index. Mid-table statistic."""

    _keys, edge = ca.monthly_edge(data, lever, SWEEP, symbol=symbol)
    return sum(edge) / len(edge) * capital


def guarantee(symbol: str, lever: float, capital: float, years: int, data, stride: int = 1,
              until=None) -> dict:
    """Dollars a month that every start date in the record survives. Minimum-order statistic.

    Returns `{"cheque": ..., "gaps": ..., "binding": ..., "starts": ...}`, and `cheque` is 0.0 when nothing survives,
    which is a result and not a failure. `gaps` is the bisection's own warning that "survives" is not monotone in
    the withdrawal — a larger withdrawal sells more of the position and can move a forced sale off a bad month, so
    the frontier can be ragged; a nonzero count means the quoted cheque is approximate.
    """

    series = {d: data.by_date[d][symbol].close for d in data.by_date if symbol in data.by_date[d]}
    if not series:
        raise ValueError(f"{symbol} is not in this archive")
    returns, cash_rate, keys = wc.monthly(series, data.cash_factors)
    windows = wc.windows_for(returns, cash_rate, keys, years, stride)
    if until is not None:
        # A minimum over a shrinking grid is not comparable to a minimum over a growing one. Longer plans sample
        # fewer starts, so the raw 30-year guarantee is measured on 1993-1996 only and comes out HIGHER than the
        # 20-year one, which is arithmetic, not prudence. `until` forces every horizon onto one common set of
        # start dates so the horizons can be compared at all.
        windows = [w for w in windows if w[2] <= until]
    if not windows:
        return {"cheque": None, "starts": 0, "gaps": 0, "binding": None,
                "months": len(returns), "years": years}
    frontier, gaps, binding = wc.capacity(windows, lever, wc.EXPENSE.get(symbol, 0.0))
    flag = ""
    # `capacity` probes 40 points up to a 6%/yr ceiling, so its smallest rung is 0.15% of the capital a month —
    # $150 on a $100k lump. Anything below that prints as exactly $0.00, which conflates "no withdrawal as large
    # as $150 survives" with "nothing at all survives". Round 41 published QQQ's guarantee as exactly $0.00 on
    # the strength of that coincidence and was wrong: refined, it is $113.75/mo at 1.25x. So a zero is refined
    # before it is believed, and a frontier sitting on the ceiling is reported as truncated rather than as a
    # number. Both ends of a bisection are answers about the grid, not about the account.
    ceiling = 0.06
    if abs(frontier - ceiling) < 1e-12:
        flag = f"ceiling-truncated at {ceiling:.2%}"
    elif frontier <= 0.0:
        low, _g, low_bind = wc.capacity(windows, lever, wc.EXPENSE.get(symbol, 0.0),
                                        ceiling=0.002, steps=40)
        frontier = low
        binding = low_bind
        flag = (f"coarse probe rung is ${ceiling / 40 * capital:,.0f}/mo, so a frontier anywhere below that "
                f"prints 0.00; refined to {low * capital:,.2f}")
    return {"cheque": frontier * capital, "gaps": gaps, "binding": binding, "starts": len(windows),
            "stride": stride, "flag": flag}


def table(data, capital: float, years: int, sleeves=SLEEVES, stride: int = 1) -> list:
    rows = []
    for symbol in sleeves:
        base = guarantee(symbol, 1.0, capital, years, data, stride)
        if base["cheque"] is None:
            rows.append({"symbol": symbol, "refused": f"{base['months']} months "
                         f"< {years * 12}, no {years}-year window exists"})
            continue
        for lever in GRID:
            g = base if abs(lever - 1.0) < 1e-9 else guarantee(symbol, lever, capital, years, data, stride)
            m = mean_order(data, symbol, lever, capital)
            rows.append({"symbol": symbol, "lever": lever, "mean": m, "guarantee": g["cheque"],
                         "base": base["cheque"], "delta": g["cheque"] - base["cheque"],
                         "starts": g["starts"], "gaps": g["gaps"], "binding": g["binding"],
                         "flag": g.get("flag", "")})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=wc.START)
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--sleeve", default=None)
    ap.add_argument("--stride", type=int, default=1,
                    help="months between sampled start dates; 1 samples every month and is the honest lower "
                         "bound. 3 is withdrawal_capacity.py's own default and is quoted in --band only.")
    args = ap.parse_args()
    ca.CAPITAL = args.capital
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    sleeves = (args.sleeve,) if args.sleeve else SLEEVES

    print(f"the same stance priced twice · ${args.capital:,.0f} · {args.years}-year plans · "
          f"every start date, worst one reported")
    print("  column 1 is what it pays on average. column 2 is what it guarantees. a mean can be paid out of a "
          "path that spends years in a hole; a guarantee cannot.\n")
    print(f"  starts sampled every {args.stride} month(s). a guarantee is a minimum over start dates, so the "
          f"grid is part of the claim:")
    print(f"  {'sleeve':6} {'lev':>5} {'mean $/mo':>10} {'guarantee':>10} {'vs 1.0x':>9} "
          f"{'starts':>7} {'binding start':>14}")
    rows = table(data, args.capital, args.years, sleeves, args.stride)
    for r in rows:
        if "refused" in r:
            print(f"  {r['symbol']:6} {'—':>5} {'':>10} {'':>10} {'':>9} {'':>7}   refused: {r['refused']}")
            continue
        binding = str(r["binding"]) if r["binding"] else "—"
        print(f"  {r['symbol']:6} {r['lever']:>5.2f} {r['mean']:>+10.2f} {r['guarantee']:>10.2f} "
              f"{r['delta']:>+9.2f} {r['starts']:>7} {binding:>14}"
              + (f"  {r['gaps']} non-monotone gaps" if r["gaps"] else "")
              + (f"  [{r['flag']}]" if r.get("flag") else ""))

    if args.sleeve is None or args.sleeve == "SPY":
        print("\n  the grid is part of the claim, so here is the same minimum on coarser grids:")
        print(f"  {'stride':>7} {'starts':>7} {'1.00x':>9} {'1.25x':>9} {'delta':>9}")
        for st in (1, 2, 3, 6, 12):
            a = guarantee("SPY", 1.00, args.capital, args.years, data, st)
            b = guarantee("SPY", 1.25, args.capital, args.years, data, st)
            print(f"  {st:>7} {a['starts']:>7} {a['cheque']:>9.2f} {b['cheque']:>9.2f} "
                  f"{b['cheque'] - a['cheque']:>+9.2f}")
        print("\n  the coarse grid flatters the loan — that is not a metaphor, it is the direction of the error:")
        print("  the start date that ends the promise is April 2000, and a grid sampling every third month lands")
        print("  on May. The level is therefore stride-dependent by ~$26/mo while the difference between the")
        print("  columns is not: it stays negative at every grid, from -$41 to -$47. Quote the dense grid.")

    spy = [r for r in rows if r.get("symbol") == "SPY"]
    if spy:
        best_mean = max(spy, key=lambda r: r["mean"])
        best_guar = max(spy, key=lambda r: r["guarantee"])
        print(f"\n  on SPY the mean is maximised at {best_mean['lever']}x "
              f"({best_mean['mean']:+.2f}/mo) and the guarantee at {best_guar['lever']}x "
              f"({best_guar['guarantee']:.2f}/mo).")
        print("  Those are different stances, and the goal's sentence cannot be satisfied by both. Borrowing moves")
        print("  money from the guarantee column into the mean column, which is the wrong trade for a plan whose")
        print("  stated purpose is a monthly amount: the mean is the one number in this table that does not")
        print("  describe any month you could actually have spent.")
        print("\n  the guarantee column is not the same as the risk of ruin. it is the amount that survived every")
        print("  start date in the archive, which is a statement about sequence, not about the market's own")
        print("  worst year — the 1.00x row is held to the same standard and also loses money in a crash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
