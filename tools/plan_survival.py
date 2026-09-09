"""Does an income plan actually survive? Simulated on every window, not inferred from an average.

Round 52. Round 51 priced the *required return* and counted how many historical windows fell under it. That count is
a shortcut, and a specific kind of wrong: once money leaves the account on a schedule, terminal wealth is not a
function of the window's compound return. Two windows with the same CAGR and different orderings produce different
endings — the +30%/−50% pair in the tests differs by $1,600 on the same $50,000 with the same withdrawals. So the
statistic that decides whether a plan is safe has to be computed on paths, and reported as a probability, not as a
required number that hides a distribution behind a point estimate.

Three quantities come out of the same simulation and they disagree with each other, which is the point:

  * **required capital at the median** — what usually works;
  * **required capital at a stated failure budget** (P(fail) ≤ 5%) — what works nearly always;
  * **required capital at zero failures** — what works always, which is round 50's guarantee and lands 2-3x above
    the median figure on the same archive and the same plan.

Run:  python tools/plan_survival.py [--target 500] [--years 10] [--contribution 0] [--floor 1.0]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

SLEEVES = ("VOO", "SPY", "QQQ", "VTI")
CAPITALS = (20_000.0, 50_000.0, 100_000.0, 137_215.0, 250_000.0, 500_000.0)
BUDGETS = (0.10, 0.05, 0.0)


def simulate(monthly, c0: float, target: float, contribution: float, expense: float,
             floor: float = 1.0) -> dict:
    """One path. Returns the terminal balance, whether the plan survived, and the lowest the account ever got.

    "Survived" is two conditions, not one: the balance is never allowed to reach zero — a plan that ends whole
    after a month at −$4,000 has already been liquidated — and it must finish at or above `floor` x the start.
    """

    wealth = c0
    trough = c0
    for r in monthly:
        wealth = wealth * (1.0 + r - expense) + contribution - target
        if wealth <= 0.0:
            return {"terminal": wealth, "survived": False, "trough": 0.0, "destroyed": True}
        trough = min(trough, wealth)
    return {"terminal": wealth, "survived": wealth >= floor * c0 - 1e-9, "trough": trough, "destroyed": False}


def windows(data, symbol: str, years: int) -> list:
    """Every window of the plan's length in the sleeve's record, as raw monthly returns. Complete months only
    (round 47), and the count is returned with them (round 50)."""

    series = {d: data.by_date[d][symbol].close for d in data.by_date if symbol in data.by_date[d]}
    rets, _cash, keys = wc.monthly(series, data.cash_factors)
    last = max(data.by_date)
    if keys and last < wc.last_business_day(keys[-1].year, keys[-1].month):
        rets = rets[:-1]
    months = years * 12
    return [rets[i:i + months] for i in range(0, len(rets) - months + 1)]


def survival(data, symbol: str, c0: float, target: float, years: int, contribution: float = 0.0,
             floor: float = 1.0) -> dict:
    """P(failure) over every window, plus the terminal-wealth distribution, for one plan."""

    expense = wc.EXPENSE.get(symbol, 0.0) / 12.0
    out = [simulate(w, c0, target, contribution, expense, floor) for w in windows(data, symbol, years)]
    n = len(out)
    if not n:
        # Untested is not the same as failed, and the difference matters: reading an empty sample as a failure would
        # put VOO's 20-year "never" in the same column as SPY's arithmetic impossibility.
        return {"n": 0, "survived": 0, "p_fail": None, "destroyed": 0, "median_terminal": None,
                "min_terminal": None, "max_terminal": None, "worst_trough": None}
    survived = [o for o in out if o["survived"]]
    terminals = sorted(o["terminal"] for o in out)
    return {"n": n, "survived": len(survived), "p_fail": 1.0 - len(survived) / n,
            "destroyed": sum(1 for o in out if o["destroyed"]),
            "median_terminal": statistics.median(terminals), "min_terminal": terminals[0],
            "max_terminal": terminals[-1], "worst_trough": min(o["trough"] for o in out)}


def capital_for(data, symbol: str, target: float, years: int, p_max: float,
                contribution: float = 0.0, floor: float = 1.0) -> float:
    """The smallest capital whose historical failure probability is at or under `p_max`.

    Legal to bisect: terminal wealth is affine in the starting capital with a positive multiplier, so it is strictly
    increasing in it for every path, and a larger account can never fail where a smaller one survived.
    """

    lo, hi = 1_000.0, 5e8
    if not windows(data, symbol, years):
        return None
    if survival(data, symbol, hi, target, years, contribution, floor)["p_fail"] > p_max:
        return float("inf")
    if survival(data, symbol, lo, target, years, contribution, floor)["p_fail"] <= p_max:
        return lo
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if survival(data, symbol, mid, target, years, contribution, floor)["p_fail"] > p_max:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=float, default=500.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--contribution", type=float, default=0.0)
    ap.add_argument("--sleeve", default="SPY")
    ap.add_argument("--floor", type=float, default=1.0)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)

    print(f"plan survival · ${args.target:,.0f}/mo for {args.years} years, principal intact,"
          f" simulated on every window in the record\n")
    print(f"  {'sleeve':7} {'windows':>8} " + " ".join(f"{f'{c:,.0f}':>12}" for c in CAPITALS))
    print("  " + "-" * (19 + 13 * len(CAPITALS)))
    for sym in SLEEVES:
        row = []
        for c0 in CAPITALS:
            s = survival(data, sym, c0, args.target, args.years, args.contribution, args.floor)
            row.append(f"{'untested':>11}" if not s["n"] else f"{s['p_fail']:>11.0%}")
        n = survival(data, sym, CAPITALS[0], args.target, args.years, args.contribution, args.floor)["n"]
        print(f"  {sym:7} {n:>8} " + " ".join(row))
    print("  the cells are the fraction of historical windows in which the plan failed: the balance touched zero, or"
          " it\n  finished below where it started.")

    print(f"\n  required capital for ${args.target:,.0f}/mo over {args.years} years, by failure budget")
    print(f"  {'sleeve':7} {'p<=10%':>12} {'p<=5%':>12} {'p=0 (always)':>14} {'vs p<=5%':>10}")
    print("  " + "-" * 60)
    for sym in SLEEVES:
        caps = [capital_for(data, sym, args.target, args.years, b, args.contribution, args.floor)
                for b in BUDGETS]
        caps = [c if c is not None else float("inf") for c in caps]
        if caps[2] < 1e12 and caps[1] < 1e12:
            price = f"{caps[2] / caps[1]:>8.2f}x"
        elif caps[2] >= 1e12:
            price = f"{'unreachable':>11}"
        else:
            price = f"{'—':>11}"
        print(f"  {sym:7} " + " ".join(f"{c:>11,.0f}" if c < 1e12 else f"{'never':>11}" for c in caps)
              + f" {price}")
    print("  The last column is the price of the word 'always'. It is not a small premium, and it is the only one of"
          "\n  the three that does not depend on which sample of history gets to vote.")

    sym = args.sleeve
    s_mid = capital_for(data, sym, args.target, args.years, 0.10, args.contribution, args.floor)
    s_zero = capital_for(data, sym, args.target, args.years, 0.0, args.contribution, args.floor)
    if s_zero is None or s_mid is None:
        print(f"\n  {sym} has no {args.years}-year window in this archive: the plan is untested, not failed."
              " Nothing is being claimed.")
        return 0
    if s_zero < 1e12 and s_mid < 1e12:
        print(f"\n  at {sym}: a 10% failure budget costs {s_mid:,.0f}, certainty costs {s_zero:,.0f}"
              f" — {s_zero / s_mid:.2f}x the capital for the same cheque.")
    else:
        print(f"\n  at {sym}: a 10% failure budget costs {s_mid:,.0f} and certainty costs"
              " **no amount of money** — in the worst window in the record the index itself did not finish"
              "\n  where it started, so a level withdrawal plan cannot either, at any account size. Money buys"
              " a bigger\n  buffer; only a different asset buys a floor.")
    voo = survival(data, "VOO", 50_000.0, args.target, args.years, args.contribution, args.floor)
    spy = survival(data, "SPY", 50_000.0, args.target, args.years, args.contribution, args.floor)
    if voo["n"] and spy["n"] and voo["p_fail"] is not None and spy["p_fail"] is not None:
        print(f"  and the same $50,000 plan fails on {voo['p_fail']:.0%} of VOO's {voo['n']} windows against"
              f" {spy['p_fail']:.0%} of SPY's {spy['n']}: the benchmark's"
              "\n  record, not the plan, is what most often decides the answer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
