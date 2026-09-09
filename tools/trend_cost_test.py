"""Do short-term trading rules beat the index? Tested with no lookahead, at four cost levels, against a fairer
benchmark than "do nothing".

Round 55. The objective's own hypothesis is short-term trading on trend and news, so this is the hypothesis the
previous fifty-four rounds have circled and never tested head-on. Six rules are pre-declared below and all six are
reported, including the ones that fail, because the number of rules tried is the first thing a good result owes an
explanation for.

Two benchmarks, not one, is the point of the file:

  * **plain buy-and-hold** — what the objective names as the thing to beat;
  * **exposure-matched passive** — the same sleeve held at the rule's own *average* exposure, the remainder in bills,
    rebalanced daily. A rule that spends 60% of its time out of the market has not avoided risk, it has de-levered,
    and de-levering is free. **A timing rule must beat this second comparator or it has not beaten anything: it has
    only been levered in a direction that happened to suit the sample.**

Signals are computed on day t's close and applied to day t+1's return. The shift is applied inside `run()`, not at
signal construction, because the first version of this file asserted the shift in its prose and did the opposite in
its code: it applied the signal to the return of the day that produced it. Costs: the repo's posted 0.0002 one-way on every change of
exposure, run at 1x, 2x, 4x and 8x for slippage honesty; the sleeve's expense charged daily against the equity leg
only. The off-risk leg accrues the monthly DGS3MO factor divided across the trading days of its own month — bills do
accrue daily, and the error against a true daily bill curve cannot exceed a month's interest.

Run:  python tools/trend_cost_test.py [--sleeve SPY] [--cost-multiplier 1] [--start 2010-01-01] [--end 2019-12-31]
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

RULES = ("hold", "ma200", "ma50x200", "mom3m", "mom12m", "voltarget")
ERAS = (("whole", None, None), ("1993-2009", None, "2009-12-31"), ("2010-2019", "2010-01-01", "2019-12-31"),
        ("2020-now", "2020-01-01", None))
COST_MULTS = (1, 2, 4, 8)
VOL_TARGET = 0.10
DAYS = 252.0


def closes_of(data, symbol: str) -> list:
    return [data.by_date[d][symbol].close for d in sorted(data.by_date)
            if symbol in data.by_date[d] and data.by_date[d][symbol].close]


def days_of(data, symbol: str) -> list:
    return [d for d in sorted(data.by_date) if symbol in data.by_date[d] and data.by_date[d][symbol].close]


def daily_legs(data, symbol: str) -> tuple:
    """Dates, next-day returns, the off-risk daily rate, the close at the end of each return's day, and the expense.

    `cash_factors` is keyed by trading day and holds a daily **factor**, so the daily rate is `factor - 1` and no
    approximation is needed. Round 55's first version of this function instead read the factor as a monthly rate and
    divided it by the days in the month, which paid the off-risk leg about 190% a year and made every rule that ever
    held cash look extraordinary — while the buy-and-hold benchmark, which never holds cash, stayed exactly correct
    at 10.77%. A control cannot detect a corruption that only appears in the treated arms.
    """

    days = days_of(data, symbol)
    closes = closes_of(data, symbol)
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    bills = [data.cash_factors[x] - 1.0 for x in days[1:]]
    return days[1:], rets, closes[1:], bills, wc.EXPENSE.get(symbol, 0.0)


def sma(values, n, i):
    return sum(values[i - n + 1:i + 1]) / n if i >= n - 1 else None


def exposures(rule: str, cl: list, rets: list) -> list:
    """Fraction of the account in the sleeve, decided at close i and held to close i+1."""

    out = []
    for i in range(len(rets)):
        c = cl[i]
        if rule == "hold":
            e = 1.0
        elif rule == "ma200":
            m = sma(cl, 200, i)
            e = 1.0 if m is not None and c > m else 0.0
        elif rule == "ma50x200":
            a, b = sma(cl, 50, i), sma(cl, 200, i)
            e = 1.0 if a is not None and b is not None and a > b else 0.0
        elif rule == "mom3m":
            e = 1.0 if i >= 63 and c > cl[i - 63] else 0.0
        elif rule == "mom12m":
            e = 1.0 if i >= 252 and c > cl[i - 252] else 0.0
        elif rule == "voltarget":
            if i < 21:
                e = 0.0
            else:
                vol = statistics.pstdev(rets[i - 20:i + 1]) or 1e-9
                e = min(2.0, max(0.0, VOL_TARGET / (vol * math.sqrt(DAYS))))
        else:
            raise ValueError(f"undeclared rule: {rule}")
        out.append(e)
    return out


def run(rets, bills, expo, expense, cost_mult: int = 1) -> dict:
    """Compound the daily path. Cost falls on every change of exposure; expense on the equity leg only."""

    # The shift is the whole honesty of the file: `expo[i]` is decided at the close of the day whose return is
    # `rets[i]`, so it can only be held over the NEXT day. Applying `expo[i]` to `rets[i]` is one day of lookahead,
    # which this function did on its first run while its own docstring claimed the opposite.
    n = len(rets) - 1
    if n < 1:
        raise ValueError("a path of one day cannot carry a shifted signal")
    # Starting flat: the first day's entry is charged, because you pay to get in.
    wealth, prev, cost_paid = 1.0, 0.0, 0.0
    peak, max_dd, switches = 1.0, 0.0, 0
    for r, b, e in zip(rets[1:], bills[1:], expo[:-1]):
        d = abs(e - prev)
        if d > 1e-12:
            switches += 1
            cost_paid += d * wc.TURNOVER_COST * cost_mult
        wealth *= (1.0 + e * (r - expense / DAYS) + (1.0 - e) * b - d * wc.TURNOVER_COST * cost_mult)
        prev = e
        peak = max(peak, wealth)
        max_dd = max(max_dd, 1.0 - wealth / peak)
        if wealth <= 0.0:
            return {"days": n, "years": n / DAYS, "cagr": -1.0, "max_dd": 1.0, "switches": switches,
                    "cost_drag": cost_paid / (n / DAYS), "mean_expo": statistics.fmean(expo[:-1]), "wealth": 0.0}
    years = n / DAYS
    return {"days": n, "years": years, "cagr": wealth ** (1.0 / years) - 1.0, "max_dd": max_dd,
            "switches": switches, "cost_drag": cost_paid / years, "mean_expo": statistics.fmean(expo[:-1]),
            "wealth": wealth}


def matched_passive(rets, bills, frac, expense, cost_mult=1):
    """The comparator a timing rule must actually beat: the same average exposure, held passively. A constant series
    is shift-invariant, so the comparator is untouched by the alignment fix that moves the rules."""

    return run(rets, bills, [frac] * len(rets), expense, cost_mult)


def verdict(r, bh, mp):
    d_bh, d_mp = r["cagr"] - bh["cagr"], r["cagr"] - mp["cagr"]
    if d_bh <= 0:
        return f"loses to plain buy-and-hold ({d_bh * 100:+.2f}pp)"
    if d_mp <= 0:
        return f"beats hold {d_bh * 100:+.2f}pp but NOT its exposure-matched twin ({d_mp * 100:+.2f}pp): leverage"
    return f"beats both: {d_bh * 100:+.2f}pp vs hold, {d_mp * 100:+.2f}pp vs matched exposure"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sleeve", default="SPY")
    ap.add_argument("--cost-multiplier", type=int, default=1)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    days, rets, cl, bills, expense = daily_legs(data, args.sleeve)

    if args.start or args.end:
        lo, hi = args.start or str(days[0]), args.end or str(days[-1])
        keep = [i for i, d in enumerate(days) if lo <= str(d) <= hi]
        days = [days[i] for i in keep]
        rets = [rets[i] for i in keep]
        cl = [cl[i] for i in keep]
        bills = [bills[i] for i in keep]

    print(f"{args.sleeve} · {len(rets)} trading days · {days[0]} to {days[-1]} · expense {expense:.4%}"
          f" · turnover {wc.TURNOVER_COST:.2%} one-way at {args.cost_multiplier}x · signals applied the next day\n")
    expo = {rule: exposures(rule, cl, rets) for rule in RULES}
    res = {rule: run(rets, bills, expo[rule], expense, args.cost_multiplier) for rule in RULES}
    bh = res["hold"]

    print(f"  {'rule':11} {'expo':>6} {'switches':>9} {'CAGR':>8} {'max DD':>8} {'cost/yr':>9}   verdict")
    print("  " + "-" * 100)
    for rule in RULES:
        r = res[rule]
        mp = matched_passive(rets, bills, r["mean_expo"], expense, args.cost_multiplier)
        tail = "(the benchmark)" if rule == "hold" else verdict(r, bh, mp)
        print(f"  {rule:11} {r['mean_expo']:>6.0%} {r['switches']:>9} {r['cagr']:>8.2%} {r['max_dd']:>8.1%}"
              f" {r['cost_drag']:>9.4%}   {tail}")

    print("\n  the cost ladder — CAGR as the one-way cost is multiplied, because a short-horizon rule is a turnover"
          " bet\n  before it is anything else")
    print(f"  {'rule':11} " + " ".join(f"{m:>9}x" for m in COST_MULTS))
    print("  " + "-" * 56)
    for rule in RULES:
        cells = " ".join(f"{run(rets, bills, expo[rule], expense, m)['cagr']:>9.2%}" for m in COST_MULTS)
        print(f"  {rule:11} {cells}")

    print("\n  by era, at the posted cost — the same six rules, and the sample each one gets to speak for")
    print(f"  {'era':11} {'days':>6} " + " ".join(f"{r:>10}" for r in RULES))
    print("  " + "-" * (19 + 11 * len(RULES)))
    for label, lo, hi in ERAS:
        keep = [i for i, d in enumerate(days)
                if (lo is None or str(d) >= lo) and (hi is None or str(d) <= hi)]
        if len(keep) < 300:
            print(f"  {label:11} {len(keep):>6}   — not enough days in this sample to score a rule")
            continue
        row = [run([rets[i] for i in keep], [bills[i] for i in keep], [expo[r][i] for i in keep], expense,
                   args.cost_multiplier)["cagr"] for r in RULES]
        print(f"  {label:11} {len(keep):>6} " + " ".join(f"{v:>10.2%}" for v in row))
    print("  2010-2019 is the only span in which the ticker named by the objective exists, and it is also the"
          " friendliest\n  decade in the record — so a rule that only works there has told you about the decade,"
          " not about itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
