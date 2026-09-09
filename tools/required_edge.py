"""What net edge a model would actually need, priced against the benchmark the objective named.

Round 51. The objective is a monthly income and a bar ("beat VOO, QQQ or whatever"). Round 50 established the
capital required at today's engines; this round asks the only question left that could change the plan: **how good
does a trading model have to be, in percentage points, before the target is reachable at the capital you have?**

Two distributions are needed to answer that and neither is a point estimate:

  1. the benchmark's own rolling record — every window of the horizon length in the archive, with its count, per
     round 50's rule that a minimum without a sample size is a slogan;
  2. the plan's required return, solved by bisection on a recurrence that is monotone in the rate, so the solution
     is unique and round-trips.

The headline is not the required edge. It is the asymmetry in (1): **VOO's rolling record contains no lost decade
at all.** Its worst 10-year window is +11.08%/yr, on 72 windows, because VOO's entire history is 2010 onwards. The
same-length SPY record has 284 windows, a median of +8.79% and a minimum of −3.45%. A bar set at "beat VOO" is a bar
set on the most flattering 16 years in the archive, and the arithmetic below says so in both readings.

Run:  python tools/required_edge.py [--target 500] [--contribution 500] [--years 10] [--floor 1.0]
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

CAPITALS = (20_000.0, 50_000.0, 100_000.0, 250_000.0)
CONTRIBUTIONS = (0.0, 500.0, 1_000.0)
BENCHMARKS = ("VOO", "SPY", "QQQ")

# The largest net edge this repository has ever measured, with its provenance, so the feasibility verdict is
# falsifiable rather than rhetorical: a constant 1.25x book financed at a posted desk rate, over the VOO era.
BEST_MEASURED_EDGE_PP = 1.63
BEST_MEASURED_SRC = "constant 1.25x book, posted borrow, VOO era (ledger r29, r46)"

# And the largest edge measured at all, from the financing survey: not a signal, a rate card.
BEST_ANY_EDGE_PP = (12.00 - 4.90) * 0.25
BEST_ANY_SRC = "the financing rate card, at 1.25x (r46, r49)"


def monthly_returns(data, symbol: str) -> tuple:
    """Complete-month returns and keys for one sleeve: round 47's rule, no partial trailing bucket."""

    series = {d: data.by_date[d][symbol].close for d in data.by_date if symbol in data.by_date[d]}
    if not series:
        raise ValueError(f"{symbol} is not in this archive")
    rets, _cash, keys = wc.monthly(series, data.cash_factors)
    last = max(data.by_date)
    if keys and last < wc.last_business_day(keys[-1].year, keys[-1].month):
        rets, keys = rets[:-1], keys[:-1]
    return rets, keys


def rolling_cagr(data, symbol: str, years: int) -> dict:
    """Every window of `years` in the sleeve's record, annualised. The count travels with the numbers."""

    rets, _keys = monthly_returns(data, symbol)
    months = years * 12
    out = []
    for i in range(0, len(rets) - months + 1):
        path = 1.0
        for r in rets[i:i + months]:
            path *= 1.0 + r
        if path > 0:
            out.append((path ** (12.0 / months) - 1.0) * 100.0)
    if not out:
        return {"n": 0, "symbol": symbol, "years": years}
    out.sort()

    def at(q):
        return out[min(int(q * (len(out) - 1)), len(out) - 1)]

    return {"n": len(out), "symbol": symbol, "years": years, "min": out[0], "q1": at(0.25),
            "median": statistics.median(out), "q3": at(0.75), "max": out[-1], "windows": out}


def terminal_wealth(c0: float, rate: float, contribution: float, target: float, months: int) -> float:
    """End-of-plan cash, one month per step: grow, contribute, withdraw."""

    r = rate / 12.0
    wealth = c0
    for _ in range(months):
        wealth = wealth * (1.0 + r) + contribution - target
    return wealth


def required_cagr(c0: float, contribution: float, target: float, years: int, floor: float = 1.0) -> float:
    """The annual return that leaves the plan at `floor` x the starting capital after `years`.

    Bisection is legal here: terminal wealth is strictly increasing in the rate whenever any wealth survives, so
    the root is unique. Returns `None` when no rate up to 200%/yr clears the floor — a plan that is infeasible at
    any return is a real answer and the tool must be able to print it.
    """

    months = years * 12
    lo, hi = -0.80, 2.00
    if terminal_wealth(c0, hi, contribution, target, months) < floor * c0:
        return None
    if terminal_wealth(c0, lo, contribution, target, months) >= floor * c0:
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if terminal_wealth(c0, mid, contribution, target, months) < floor * c0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0 * 100.0


def feasibility(required_pp: float, benchmark: dict) -> str:
    """Verdict against the two edges this repository has actually measured."""

    if required_pp is None:
        return "infeasible at any return up to 200%/yr"
    gap_spy = required_pp - benchmark["median"]
    for edge, src in ((BEST_MEASURED_EDGE_PP, BEST_MEASURED_SRC), (BEST_ANY_EDGE_PP, BEST_ANY_SRC)):
        if edge >= gap_spy:
            return f"reached by {src} (+{edge:.2f}pp vs the +{gap_spy:.2f}pp needed)"
    return (f"NO measured edge reaches it: need +{gap_spy:.2f}pp over {benchmark['symbol']}, "
            f"best is +{BEST_MEASURED_EDGE_PP:.2f}pp")


def table(data, target: float, years: int, floor: float, sleeve: str) -> None:
    bench = rolling_cagr(data, sleeve, years)
    print(f"  the benchmark first: every {years}-year window in {sleeve}'s own record")
    print(f"  {'sleeve':7} {'n':>4} {'worst':>8} {'q1':>8} {'median':>8} {'q3':>8} {'best':>8}")
    print("  " + "-" * 51)
    for sym in BENCHMARKS:
        r = rolling_cagr(data, sym, years)
        if r["n"] == 0:
            print(f"  {sym:7}    0    (not enough history in this archive)")
            continue
        print(f"  {sym:7} {r['n']:>4} {r['min']:>+7.2f}% {r['q1']:>+7.2f}% {r['median']:>+7.2f}% "
              f"{r['q3']:>+7.2f}% {r['max']:>+7.2f}%")
    spy_ref, voo_ref = rolling_cagr(data, "SPY", years), rolling_cagr(data, "VOO", years)
    if voo_ref["n"]:
        print(f"  VOO has {voo_ref['n']} windows because it has existed since 2010, and its worst decade is"
              f" {voo_ref['min']:+.2f}%/yr\n  for that same reason: this archive holds no lost decade for that"
              f" ticker. SPY's {spy_ref['n']} windows\n  reach {spy_ref['min']:+.2f}%."
              " Beating the ticker the objective names is easy on its own record and harder\n  on the history.")

    print(f"\n  the required return, to withdraw ${target:,.0f}/mo for {years} years and end at"
          f" {floor:.0%} of the starting capital")
    print(f"  {'capital':>11} {'contrib/mo':>11} {'required':>10} {'vs VOO med':>12} {'vs SPY med':>12}"
          f"{'  verdict':>4}")
    print("  " + "-" * 96)
    spy = rolling_cagr(data, "SPY", years)
    voo = rolling_cagr(data, "VOO", years)
    rows = []
    for c0 in CAPITALS:
        for m in CONTRIBUTIONS:
            need = required_cagr(c0, m, target, years, floor)
            rows.append((c0, m, need))
            if need is None:
                print(f"  {c0:>11,.0f} {m:>11,.0f} {'never':>10} {'—':>12} {'—':>12}")
                continue
            print(f"  {c0:>11,.0f} {m:>11,.0f} {need:>+9.2f}% "
                  f"{need - voo['median']:>+11.2f}pp {need - spy['median']:>+11.2f}pp")
    print("\n  the columns are the edge a model must produce, net of every cost, over the benchmark's own median."
          " Nothing\n  in this repository has ever measured more than "
          f"+{BEST_MEASURED_EDGE_PP:.2f}pp net ({BEST_MEASURED_SRC}), and the\n  largest edge of any kind is the"
          f" financing rate card at +{BEST_ANY_EDGE_PP:.2f}pp.")

    print(f"\n  feasibility at the smallest capital, against {sleeve}'s median {years}-year return of"
          f" {bench['median']:+.2f}%:")
    for c0, m, need in rows:
        if c0 != CAPITALS[0]:
            continue
        print(f"    contrib ${m:>7,.0f}/mo -> {feasibility(need, bench)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=float, default=500.0)
    ap.add_argument("--contribution", type=float, default=-1.0, help="price one contribution only")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--floor", type=float, default=1.0)
    ap.add_argument("--sleeve", default="VOO")
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    print(f"the required edge · what a model must beat, and by how much, before the target is real\n")
    table(data, args.target, args.years, args.floor, args.sleeve)
    if args.contribution >= 0:
        spy = rolling_cagr(data, "SPY", args.years)
        print("\n  the same arithmetic, one row only:")
        for c0 in CAPITALS:
            need = required_cagr(c0, args.contribution, args.target, args.years, args.floor)
            print(f"    capital {c0:>10,.0f}, contrib ${args.contribution:>7,.0f}/mo -> "
                  + (f"{need:+.2f}% required, {feasibility(need, spy)}" if need is not None else "never"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
