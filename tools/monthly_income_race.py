"""The objective in its own units: dollars a month that survive, and whether the index is beaten while paying them.

Round 58. The objective asks for two things at once — "earn extra each month" and "beat VOO, QQQ". Rounds 51 to 57
priced each half separately against different metrics, so they never had to meet. Here they meet, in one table, on one
sample, under one plan.

Four equity legs, all at the frequency round 57 found best (monthly), all on the same panel so no leg gets a friendlier
sample than another (round 51's rule):

  * `SPY hold`        — the index the objective names. VOO is not in the panel because it starts in 2010; over this
                        window the two are the same exposure, and SPY is the one with a record.
  * `MA200 monthly`   — round 55's trend rule, at round 57's optimum frequency.
  * `mom_top1 monthly`— round 56's rotation rule, at the same frequency.
  * `static 60/40`    — no signal, and the control round 56 showed reproduces the rotation's drawdown for an eighth
                        of the cost.

Each leg is then held at four bill weights, blended monthly — the allocation lever round 54 measured, applied to legs
that were not built by it.

The plan is round 52's: start with $100,000, take the same amount every month for 10 years, add nothing, and a plan
fails if the balance ever reaches zero or ends below where it started. Two views are reported for every cell, because
they answer different questions and disagree:

  * **the most each cell can pay** — the largest monthly amount whose historical failure rate is at most 5%;
  * **the same amount for everyone** — every cell asked to pay what the index pays, and scored on failure rate and
    terminal wealth. This is the view that shows whether a better-paying strategy is actually a better plan.

Run:  python tools/monthly_income_race.py [--capital 100000] [--years 10] [--p-max 0.05]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import frequency_cost as fc                                              # noqa: E402
import plan_survival as ps                                               # noqa: E402
import rotation_edge as re_                                              # noqa: E402
import trend_cost_test as tc                                             # noqa: E402
import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

LEGS = ("SPY hold", "MA200 monthly", "mom_top1 monthly", "static 60/40")
BILLS = (0.0, 0.25, 0.50, 0.65)
FREQ = "monthly"


def leg_weights(leg: str, ordered, rets, bills, expense, closes, unknown_er) -> list:
    """Weights on the ten-sleeve panel. `SPY hold` is a leg like any other, so every row is priced by one engine."""

    if leg == "SPY hold":
        return re_.constant_weights("SPY", len(ordered))
    if leg == "static 60/40":
        return re_.weights_for("static_60_40", ordered, rets, bills, unknown_er)
    if leg == "MA200 monthly":
        return fc.weights_for_family("ma200", ordered, rets, bills, expense, closes, FREQ, unknown_er)
    if leg == "mom_top1 monthly":
        return fc.weights_for_family("mom_top1", ordered, rets, bills, expense, closes, FREQ, unknown_er)
    raise ValueError(f"undeclared leg: {leg}")


def wealth_path(ordered, rets, bills, expense, weights, cost_mult=1) -> list:
    """The daily balance, day by day, from the same arithmetic as `rotation_edge.run_weights`.

    Duplicated on purpose — a runner that returns a path is the one thing the repository did not have, and the
    alternative (re-deriving monthly returns from a terminal number) would have made the window statistics lie about
    path order, which is round 52's whole point. `tests/test_monthly_income_race.py` pins this against `run_weights`
    to ten places so the duplication cannot drift.
    """

    wts = [tuple(float(x) for x in w) for w in weights]
    out = []
    wealth, prev = 1.0, tuple(0.0 for _ in re_.UNIVERSE)
    for i in range(1, len(ordered)):
        w = wts[i - 1]
        gross = sum(w[k] * (rets[s][i] - expense[s] / tc.DAYS) for k, s in enumerate(re_.UNIVERSE))
        turn = sum(abs(w[k] - prev[k]) for k in range(len(re_.UNIVERSE)))
        wealth *= (1.0 + gross + (1.0 - sum(w)) * bills[i]
                   - turn * wc.TURNOVER_COST * cost_mult)
        prev = w
        out.append(wealth)
    return out


def month_marks(ordered: list, path: list) -> tuple:
    """End-of-month balances for calendar months that finished inside the path.

    The path starts on the second day of the panel, so `ordered` is offset by one. A month whose last weekday has not
    arrived yet is dropped — round 47's lesson, that a trailing partial month is a four-day return dressed as a month.
    """

    # `path[i-1]` is the balance at `ordered[i]`, so the index into `path` is one less than the index into `ordered`.
    # Writing this as `i + 1` and then subtracting 1 at the use site made every month-end mark the balance one
    # TRADING DAY after the month end — a month of marks that is subtly not a month of marks.
    path_of = {d: i - 1 for i, d in enumerate(ordered)}
    last = max(ordered)
    by_month, keys = {}, []
    for d in ordered:
        key = (d.year, d.month)
        if key not in by_month:
            keys.append(key)
        by_month[key] = d
    out_keys, out = [], []
    prev_bal = 1.0
    for j, k in enumerate(keys):
        d = by_month[k]
        if path_of[d] < 0:
            continue
        # The panel starts mid-month, so the first mark covers a few days and would be a month-shaped observation
        # built from a week of prices. Same defect, opposite end of the record.
        if j == 0:
            prev_bal = path[path_of[d]]
            continue
        if (d.year, d.month) == (last.year, last.month) and d < wc.last_business_day(*k):
            continue
        bal = path[path_of[d]]
        out_keys.append(k)
        out.append(bal / prev_bal - 1.0)
        prev_bal = bal
    keep = [i for i, x in enumerate(out) if x is not None]
    return [out_keys[i] for i in keep], [out[i] for i in keep]


def bill_months(data, ordered) -> tuple:
    """Monthly bill returns keyed the same way as the equity marks, so a blend never mixes months."""

    ser = {d: data.by_date[d]["SPY"].close for d in data.by_date if "SPY" in data.by_date[d]}
    _r, cash, keys = wc.monthly_complete(ser, data.cash_factors, max(ordered))
    return {(k.year, k.month): c for k, c in zip(keys, cash)}


def blend(eq: list, cash: dict, w: float) -> list:
    return [(1.0 - w) * r + w * c for r, c in zip(eq, cash)]


def plan_stats(monthly: list, c0: float, target: float, years: int, expense: float = 0.0,
               floor: float = 1.0) -> dict:
    """Failure rate and terminal distribution over every window. `floor` is the promise: 1.0 means the plan must end
    at or above where it started, 0.0 means only that it must never be liquidated. Round 54's rule applies — a
    withdrawal figure without its promise named is not a figure."""

    months = years * 12
    out = [ps.simulate(monthly[i:i + months], c0, target, 0.0, expense, floor)
           for i in range(0, len(monthly) - months + 1)]
    n = len(out)
    if not n:
        return {"n": 0, "p_fail": None, "median_mult": None, "p_erase": None}
    return {"n": n, "p_fail": sum(1 for o in out if not o["survived"]) / n,
            "median_mult": statistics.median(sorted(o["terminal"] for o in out)) / c0,
            "p_erase": sum(1 for o in out if o["trough"] < 0.5 * c0) / n,
            "p_destroyed": sum(1 for o in out if o["destroyed"]) / n}


def safe_amount(monthly: list, c0: float, years: int, p_max: float, floor: float = 1.0) -> float:
    """Largest level monthly withdrawal whose simulated failure rate is at most `p_max`. Monotone in the amount, so
    bisection is legal; `None` when the sample holds no complete window."""

    if len(monthly) < years * 12:
        return None
    lo, hi = 0.0, c0 * 0.02
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if plan_stats(monthly, c0, mid, years, floor=floor)["p_fail"] <= p_max:
            lo = mid
        else:
            hi = mid
    return lo


def long_history(data, capital: float, years: int, p_max: float) -> dict:
    """The same plan on SPY's whole record, at monthly resolution, for the two legs that exist before 2006.

    The convention differs here and that is stated rather than hidden: signals are taken at month end and applied to
    the following month, expense is charged monthly on the equity leg, and turnover is charged once when the signal
    flips. The panel block above charges expense daily. The difference is a few basis points a year; the difference in
    SAMPLE is thirty years of history the panel never sees, including the decade this plan is most likely to be asked
    to survive.
    """

    last = max(data.by_date)
    ser = {d: data.by_date[d]["SPY"].close for d in data.by_date if "SPY" in data.by_date[d]}
    eq, cash, keys = wc.monthly_complete(ser, data.cash_factors, last)
    days, closes = tc.days_of(data, "SPY"), tc.closes_of(data, "SPY")
    month_end = {}
    for i, d in enumerate(days):
        month_end[(d.year, d.month)] = i
    er = wc.EXPENSE["SPY"]
    sig = {}
    for k, i in month_end.items():
        m = tc.sma(closes, 200, i)
        sig[k] = 1.0 if m is not None and closes[i] > m else 0.0
    # STRICT lookup, and keys of one type only. This function originally built `sig` keyed by (year, month) tuples
    # and read it back with the date objects `monthly_complete` returns, and `sig.get(k, 0.0)` answered every miss
    # with "cash". The MA200 row printed the bill series and nobody's eyebrow rose until two rows agreed to the cent.
    ma, prev = [], 0.0
    for j, k in enumerate(keys):
        k = (k.year, k.month)
        if k not in sig:
            continue
        e = sig[k]
        turn = abs(e - prev)
        prev = e
        nxt = keys[j + 1] if j + 1 < len(keys) else None
        if nxt is None:
            continue
        # Signal at month k's close earns month k+1's return, one month late, exactly as the panel engine does it.
        ma.append(e * eq[j + 1] + (1.0 - e) * cash[j + 1] - e * er / 12.0 - turn * wc.TURNOVER_COST)
    out = {}
    ma_cash = [c for k, c in zip(keys, cash) if (k.year, k.month) in sig][1:]
    for label, m in (("SPY hold", eq), ("SPY hold +65% bills", [0.35 * r + 0.65 * c for r, c in zip(eq, cash)]),
                     ("MA200 monthly", ma),
                     ("MA200 +25% bills", [0.75 * r + 0.25 * c for r, c in zip(ma, ma_cash)])):
    #  `ma_cash` is the bill return for the month AFTER the signal month, which is the month the position is held.`
        amt = safe_amount(m, capital, years, p_max)
        st = plan_stats(m, capital, amt, years) if amt is not None else None
        zero = plan_stats(m, capital, 0.0, years)
        loose = safe_amount(m, capital, years, p_max, floor=0.0)
        out[label] = {"amount": amt, "stats": st, "p_fail_at_zero": zero["p_fail"], "n": zero["n"],
                      "loose": loose, "windows": len(m) - years * 12 + 1}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--p-max", type=float, default=0.05)
    ap.add_argument("--unknown-er", type=float, default=re_.UNKNOWN_ER)
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    ordered, rets, bills, expense = re_.panel(data, args.unknown_er)
    pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
    cl = tc.closes_of(data, "SPY")
    closes = {"SPY": [cl[pos[d]] for d in ordered]}
    bill_map = bill_months(data, ordered)

    print(f"the objective's two halves, in one table · ${args.capital:,.0f} start"
          f" · {args.years}-year plan · failure budget {args.p_max:.0%}")
    print(f"  legs {LEGS}")
    print(f"  every leg on the same panel: {ordered[0]} to {ordered[-1]}, and the same bill returns in the"
          " same months")
    print(f"  a plan fails if the balance ever reaches zero or ends below the start (round 52's rule)\n")

    marks = {}
    for leg in LEGS:
        w = leg_weights(leg, ordered, rets, bills, expense, closes, args.unknown_er)
        path = wealth_path(ordered, rets, bills, expense, w)
        keys, mr = month_marks(ordered, path)
        cash = [bill_map.get(k, 0.0) for k in keys]
        common = [(r, c) for r, c, k in zip(mr, cash, keys) if k in bill_map]
        marks[leg] = ([r for r, _c in common], [c for _r, c in common], keys and len(common))
    ns = {leg: len(marks[leg][0]) for leg in LEGS}
    if len(set(ns.values())) != 1:
        raise SystemExit(f"legs disagree on sample length: {ns}")
    print(f"  complete months available to every leg: {ns[LEGS[0]]}"
          f"  ({ns[LEGS[0]] - args.years * 12 + 1} windows of {args.years} years)\n")

    eq0, cash0, _n = marks["SPY hold"]
    index_safe = safe_amount(blend(eq0, cash0, 0.0), args.capital, args.years, args.p_max)

    print(f"  {'leg':17} {'bills':>6} {'own best $/mo':>14} {'P(fail) there':>14} {'med term':>9}"
          f" {'P(erase)':>9}   at the index's ${index_safe:,.0f}/mo")
    print("  " + "-" * 96)
    rows = {}
    for leg in LEGS:
        eq, cash, _n = marks[leg]
        for w in BILLS:
            m = blend(eq, cash, w)
            amt = safe_amount(m, args.capital, args.years, args.p_max)
            own = plan_stats(m, args.capital, amt, args.years) if amt is not None else None
            at_idx = plan_stats(m, args.capital, index_safe, args.years)
            rows[(leg, w)] = (amt, own, at_idx)
            print(f"  {leg:17} {w:>6.0%} {amt:>14,.2f} {own['p_fail']:>14.0%} {own['median_mult']:>9.2f}"
                  f" {own['p_erase']:>9.0%}   {at_idx['p_fail']:>9.0%} {at_idx['median_mult']:>8.2f}x"
                  f" {at_idx['p_erase']:>8.0%}")
        print()
    print(f"  The index's own affordable amount is ${index_safe:,.2f}/mo at P(fail)<={args.p_max:.0%}."
          " The right-hand block holds")
    print("  every cell to that same figure, which is the only column where a claim to be a better *plan* can be")
    print("  checked against the thing it is supposed to replace.")

    lh = long_history(data, args.capital, args.years, args.p_max)
    print("\n  the same plan on SPY's whole record, because the panel above starts in 2006 and cannot see 2000-2009")
    print(f"  {'leg':22} {'ends whole':>11} {'never zero':>11} {'med term':>9} {'P(erase)':>9}"
          f" {'P(fail) at $0':>14} {'windows':>8}")
    print("  " + "-" * 82)
    for label, v in lh.items():
        print(f"  {label:22} {v['amount']:>11,.2f} {v['loose']:>11,.2f} {v['stats']['median_mult']:>9.2f}"
              f" {v['stats']['p_erase']:>9.0%} {v['p_fail_at_zero']:>14.0%} {v['windows']:>8}")
    print("  Two promises, two prices. 'ends whole' also requires finishing at or above the starting balance, and on")
    print("  the long record plain SPY breaks that promise in 8% of 10-year windows BEFORE taking anything out, so no")
    print("  withdrawal at all fits the budget and the row reads $0.00. Under 'never zero' the same sleeve prices at")
    print("  a positive number. The difference between the two columns is not arithmetic, it is which promise the")
    print("  reader thought they were buying.")

    print("\n  growth without any withdrawal at all — the 'beat VOO' half, on the same legs")
    print(f"  {'leg':17} {'CAGR':>8} {'max DD':>8}   note")
    print("  " + "-" * 66)
    for leg in LEGS:
        w = leg_weights(leg, ordered, rets, bills, expense, closes, args.unknown_er)
        r = re_.run_weights(ordered, rets, bills, expense, w)
        note = "the bar" if leg == "SPY hold" else ("no signal, no turnover" if leg == "static 60/40" else "")
        print(f"  {leg:17} {r['cagr']:>8.2%} {r['max_dd']:>8.1%}   {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
