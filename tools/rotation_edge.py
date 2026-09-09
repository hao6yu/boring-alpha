"""Cross-sectional rotation: does picking the strongest of many sleeves beat holding the one the objective names?

Round 56. Round 55 tested timing a single asset and found nothing since 2010. This round tests the other short-term
family — the one that does not try to predict the market at all: rank the sleeves, hold the strongest. It is the
family with the strongest prior evidence, and the one a "beat VOO" objective can actually act on.

Four rules are pre-declared and all four are reported:

  * `rs_top1`      — hold the single best sleeve by trailing 12-month return, monthly.
  * `rs_top3`      — hold the best three, equal weight.
  * `dual_top1`    — as `rs_top1`, but only if that sleeve also beats the bill yield. Absolute momentum on top of
                     relative: the version that is supposed to survive 2008.
  * `static_60_40` — SPY 60 / TLT 40, monthly rebalanced, **no signal at all**. The control a rotation must beat is
                     the allocation a person could choose while asleep.

Three comparators, all reported: plain SPY (the objective's bar, since VOO has no history before 2010), plain VOO on
VOO's own record, and the static 60/40 control.

**Costs.** Five sleeves have posted expense ratios here (SPY, VOO, VTI, ITOT, QQQ). The rest do not, and this file
does not invent figures it cannot source. Every unposted sleeve is charged `UNKNOWN_ER` (default 0.35%) and the whole
test is re-run at 0.70% — worse than any sleeve in this universe has ever cost. If a rotation's edge is smaller than
the gap between those two assumptions, the edge is not real, and this file says so rather than keeping the flattering
one. Historical ratios were generally higher than today's, so both settings understate the older part of the sample.

Signals are computed on the last trading day of a month and held through the next month; a signal on day t is applied
to day t+1. Turnover is charged at the repository's posted 0.0002 one-way on every unit traded.

Run:  python tools/rotation_edge.py [--unknown-er 0.0035]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import trend_cost_test as tc                                             # noqa: E402
import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

UNIVERSE = ("SPY", "QQQ", "IWM", "EFA", "EEM", "VTI", "IEF", "TLT", "GLD", "DBC")
CANDIDATES = ("SPY", "QQQ", "IWM", "EFA", "EEM", "VTI")      # eligible for the risk slots; bonds/gold/commodities are
RULES = ("rs_top1", "rs_top3", "dual_top1", "static_60_40")
LOOKBACK = 252
DAYS = 252.0
ERAS = (("2006-2009", "2006-02-06", "2009-12-31"), ("2010-2019", "2010-01-01", "2019-12-31"),
        ("2020-now", "2020-01-01", None))
UNKNOWN_ER = 0.0035


def panel(data, unknown_er: float = UNKNOWN_ER) -> tuple:
    """Daily returns for all ten sleeves on their common window, plus the bill leg and per-sleeve expense.

    Every series is indexed by DATE, never by position: sleeves start on different days, and aligning by row number
    would let a sleeve's return be measured against a day three weeks earlier. The window also drops any leading day
    that is a sleeve's own first day — a return needs a previous close, and `index - 1` on the first day is not a
    missing value but the last element of the list.
    """

    closes, ddays, pos = {}, {}, {}
    for s in UNIVERSE:
        ddays[s] = tc.days_of(data, s)
        closes[s] = tc.closes_of(data, s)
        pos[s] = {d: i for i, d in enumerate(ddays[s])}
    common = set(ddays[UNIVERSE[0]])
    for s in UNIVERSE[1:]:
        common &= set(ddays[s])
    ordered = sorted(common)
    start = 0
    for i, d in enumerate(ordered):
        if all(pos[s][d] >= 1 for s in UNIVERSE):
            start = i
            break
    ordered = ordered[start:]
    rets = {}
    for s in UNIVERSE:
        out = []
        for i, d in enumerate(ordered):
            j = pos[s][d]
            out.append(closes[s][j] / closes[s][j - 1] - 1.0 if j >= 1 else 0.0)
        rets[s] = out
    bills = [data.cash_factors[d] - 1.0 for d in ordered]
    expense = {s: wc.EXPENSE.get(s, unknown_er) for s in UNIVERSE}
    return ordered, rets, bills, expense


def month_end_indices(days: list) -> set:
    return {i for i in range(len(days) - 1)
            if (days[i + 1].year, days[i + 1].month) != (days[i].year, days[i].month)}


def compound(xs):
    out = 1.0
    for x in xs:
        out *= 1.0 + x
    return out


def weights_for(rule: str, ordered, rets, bills, unknown_er: float = UNKNOWN_ER) -> list:
    """A weight tuple per day, set at the previous month-end and held until the next one."""

    ends = month_end_indices(ordered)
    n = len(ordered)
    hold = {}
    out = []
    for i in range(n):
        if i in ends and i >= LOOKBACK:
            if rule == "static_60_40":
                hold = {"SPY": 0.60, "TLT": 0.40}
            else:
                # `compound` returns a GROWTH FACTOR. Both sides of every comparison below are net returns, so both
                # subtract 1. Omitting it on the sleeve side does not disturb the ranking — subtracting a constant
                # is monotone — but it does destroy the comparison against the bill yield, which made the absolute
                # overlay in `dual_top1` inert through the entire window including 2008, while every headline number
                # stayed correct. A units error that cannot break a ranking can still break a switch.
                ranked = sorted(((compound(rets[s][i - LOOKBACK + 1:i + 1]) - 1.0, s) for s in CANDIDATES),
                                key=lambda x: (-x[0], x[1]))
                bill_12m = compound(bills[max(0, i - LOOKBACK + 1):i + 1]) - 1.0
                if rule == "rs_top1":
                    hold = {ranked[0][1]: 1.0}
                elif rule == "rs_top3":
                    hold = {s: 1.0 / len(ranked[:3]) for _t, s in ranked[:3]}
                elif rule == "dual_top1":
                    hold = {ranked[0][1]: 1.0} if ranked[0][0] > bill_12m else {}
                else:
                    raise ValueError(f"undeclared rule: {rule}")
        out.append(tuple(float(hold.get(s, 0.0)) for s in UNIVERSE))
    return out


def run_weights(ordered, rets, bills, expense, weights, cost_mult=1, keep=None) -> dict:
    """Compound a daily weight schedule over the whole window, or over `keep` if one is given.

    `weights[i]` is set at the close of day i and is held over day i+1, so the schedule is applied shifted by one
    and the first day of the window is never traded.
    """

    idx = list(range(1, len(ordered))) if keep is None else [i for i in keep if i >= 1]
    wealth, peak, max_dd, cost_paid, turns = 1.0, 1.0, 0.0, 0.0, 0
    prev = tuple(0.0 for _ in UNIVERSE)
    for i in idx:
        w = weights[i - 1]
        gross = sum(w[k] * (rets[s][i] - expense[s] / DAYS) for k, s in enumerate(UNIVERSE))
        turn = sum(abs(w[k] - prev[k]) for k in range(len(UNIVERSE)))
        if turn > 1e-12:
            turns += 1
            cost_paid += turn * wc.TURNOVER_COST * cost_mult
        wealth *= (1.0 + gross + (1.0 - sum(w)) * bills[i] - turn * wc.TURNOVER_COST * cost_mult)
        prev = w
        peak = max(peak, wealth)
        max_dd = max(max_dd, 1.0 - wealth / peak)
        if wealth <= 0.0:
            break
    years = len(idx) / DAYS
    return {"days": len(idx), "cagr": max(-0.9999, wealth) ** (1.0 / years) - 1.0 if years else None,
            "max_dd": max_dd, "mean_expo": statistics.fmean(sum(weights[i - 1]) for i in idx),
            "switches": turns, "cost_drag": cost_paid / years if years else 0.0, "wealth": wealth}


def constant_weights(symbol: str, n: int) -> list:
    """All-in one sleeve, never traded. `symbol` must be in UNIVERSE — VOO is not, because its record starts in 2010
    and it cannot join a common window that starts in 2006; the bar it stands for is measured separately, on its own
    record, by `trend_cost_test`. A name missing from UNIVERSE is an error, not an all-cash portfolio."""

    if symbol not in UNIVERSE:
        raise ValueError(f"{symbol} is not in the rotation universe")
    return [tuple(1.0 if s == symbol else 0.0 for s in UNIVERSE) for _ in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unknown-er", type=float, default=UNKNOWN_ER)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    ordered, rets, bills, expense = panel(data, args.unknown_er)
    n = len(ordered)
    print(f"cross-sectional rotation · {len(UNIVERSE)} sleeves · common window {ordered[0]} to {ordered[-1]}"
          f" ({n} days)\n  signals at month-end held one month · unposted expenses {args.unknown_er:.2%}"
          f" · turnover {wc.TURNOVER_COST:.2%} one-way")
    print("  expenses: " + ", ".join(f"{s} {expense[s]:.2%}" for s in UNIVERSE) + "\n")

    wts = {r: weights_for(r, ordered, rets, bills, args.unknown_er) for r in RULES}
    spy = run_weights(ordered, rets, bills, expense, constant_weights("SPY", n))
    ctrl = run_weights(ordered, rets, bills, expense, wts["static_60_40"])
    vd, vr, vc, vb, vex = tc.daily_legs(data, "VOO")
    voo = tc.run(vr, vb, [1.0] * len(vr), vex, 1)
    print(f"  {'rule':13} {'expo':>6} {'trades':>7} {'CAGR':>8} {'max DD':>8} {'cost/yr':>9}"
          f"   {'vs SPY':>8} {'vs 60/40':>9}")
    print("  " + "-" * 74)
    for r in RULES:
        res = run_weights(ordered, rets, bills, expense, wts[r])
        print(f"  {r:13} {res['mean_expo']:>6.0%} {res['switches']:>7} {res['cagr']:>8.2%} {res['max_dd']:>8.1%}"
              f" {res['cost_drag']:>9.4%}   {res['cagr'] - spy['cagr']:>+8.2%} {res['cagr'] - ctrl['cagr']:>+9.2%}")
    print(f"  {'SPY hold':13} {spy['mean_expo']:>6.0%} {spy['switches']:>7} {spy['cagr']:>8.2%} {spy['max_dd']:>8.1%}"
          f" {spy['cost_drag']:>9.4%}   (the bar the objective names)")
    print(f"  {'VOO hold':13} {'':>6} {'':>7} {voo['cagr']:>8.2%}   its own record only: {voo['days']} days from"
          f" {vd[0]} (via trend_cost_test)")

    order2, rets2, bills2, exp2 = panel(data, 0.0070)
    print(f"\n  the same rules with every unposted sleeve at 0.70% — worse than any of them has ever cost")
    print(f"  {'rule':13} {'CAGR':>8} {'cost/yr':>9}   {'vs SPY':>8}   change vs the 0.35% block")
    print("  " + "-" * 60)
    for r in RULES:
        w2 = weights_for(r, order2, rets2, bills2, 0.0070)
        res = run_weights(order2, rets2, bills2, exp2, w2)
        base = run_weights(order2, rets2, bills2, exp2, constant_weights("SPY", len(order2)))
        before = run_weights(ordered, rets, bills, expense, wts[r])["cagr"]
        print(f"  {r:13} {res['cagr']:>8.2%} {res['cost_drag']:>9.4%}   {res['cagr'] - base['cagr']:>+8.2%}"
              f"   {res['cagr'] - before:>+7.2%}pp")
    print("  If the ranking is unchanged, the conclusion did not depend on the assumption. If it moved, the"
          " conclusion\n  was the assumption.")

    print("\n  by era — the same treatment the timing rules got, for the same reason")
    print(f"  {'era':11} {'days':>6} " + " ".join(f"{r:>12}" for r in RULES) + f"  {'SPY hold':>10}")
    print("  " + "-" * 78)
    for label, lo, hi in ERAS:
        keep = [i for i, d in enumerate(ordered)
                if (lo is None or str(d) >= lo) and (hi is None or str(d) <= hi)]
        if len(keep) < 400:
            print(f"  {label:11} {len(keep):>6}  — too few days to score a rule")
            continue
        cells = " ".join(f"{run_weights(ordered, rets, bills, expense, wts[r], keep=keep)['cagr']:>12.2%}"
                         for r in RULES)
        base = run_weights(ordered, rets, bills, expense, constant_weights("SPY", n), keep=keep)
        print(f"  {label:11} {base['days']:>6} {cells}  {base['cagr']:>10.2%}")
    print("  The common window begins in 2006, so the first era is a crisis and nothing before it. A rule that only"
          "\n  works in a crisis has described itself, which is not the same as showing that it works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
