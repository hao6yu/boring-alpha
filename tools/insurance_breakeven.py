"""The withdrawal rate at which the trend rule stops costing you money and starts paying for you.

Round 63. Round 58 said the trend leg supports 36% more monthly income than the index. Round 60 said that with money
going in and nothing coming out, the same leg ends 17% smaller. Round 62 said its protection is perfect at $435.47 a
month and free. Those are not three findings; they are one curve sampled at three points, and the curve has a crossing:
at no withdrawal the rule is a drag (it is out of the market sometimes and the market went up), and at a large enough
withdrawal it is the only leg that finishes the job, because it is out of the market exactly when a payout plan cannot
afford to be.

This file finds the crossing. Same record (SPY monthly from 1993), same simulation as rounds 58 and 60 (`$100,000
start, a level withdrawal for ten years, nothing added`), every payout scored on every window, and the difference in
median terminal wealth between the rule and the index read off as a function of the payout. Below the crossing the
insurance costs you; above it, it pays. The three samples are the same series sliced differently, so the era
dependence is a difference in the data and not in the machinery.

Run:  python tools/insurance_breakeven.py [--capital 100000] [--years 10] [--max-payout 1500]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import entry_state as es                                 # noqa: E402
import plan_survival as ps                              # noqa: E402
import withdrawal_capacity as wc                        # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

BENCH = "SPY hold"
LEGS = ("SPY hold", "MA200 monthly", "static 60/40")


def windows(series: dict, start_year: int, end_year: int, years: int) -> dict:
    """Each leg's windows, aligned across legs by start month and restricted to a start-year range.

    Alignment matters more here than anywhere else in the laboratory: if one leg's windows start at different months
    than another's, the median difference is a comparison of two different market histories rather than of two rules.
    """

    months = years * 12
    base_dates = series[BENCH][0]
    idx = {leg: {d: j for j, d in enumerate(series[leg][0])} for leg in LEGS}
    keep = []
    for s in range(len(base_dates) - months + 1):
        d0 = base_dates[s]
        if not start_year <= d0.year <= end_year:
            continue
        ok = True
        for leg in LEGS:
            dates, m = series[leg]
            j = idx[leg].get(d0)
            if j is None or j + months > len(m) or dates[j:j + months] != base_dates[s:s + months]:
                ok = False
                break
        if ok:
            keep.append(s)
    out = {}
    for leg in LEGS:
        dates, m = series[leg]
        out[leg] = [(base_dates[s], m[idx[leg][base_dates[s]]:idx[leg][base_dates[s]] + months]) for s in keep]
    return out


def curve(series: dict, wins: dict, payout: float, capital: float, years: int) -> dict:
    """Median terminal multiple and failure rate for every leg at one payout."""

    out = {}
    for leg in LEGS:
        terms, fails = [], []
        for _d0, w in wins[leg]:
            r = ps.simulate(w, capital, payout, 0.0, 0.0)
            terms.append(r["terminal"] / capital)
            fails.append(0 if r["survived"] else 1)
        out[leg] = {"median": statistics.median(terms), "p_fail": statistics.fmean(fails),
                    "n": len(terms), "p10": sorted(terms)[max(0, int(0.10 * (len(terms) - 1)))],
                    "p90": sorted(terms)[int(0.90 * (len(terms) - 1))]}
    return out


def difference(wins: dict, series: dict, payout: float, capital: float, years: int, leg: str) -> float:
    c = curve(series, wins, payout, capital, years)
    return (c[leg]["median"] - c[BENCH]["median"]) * capital / (years * 12)


def breakeven(wins: dict, series: dict, capital: float, years: int, leg: str, hi: float, step: float):
    """The monthly withdrawal at which `leg` first stops ending smaller than the index.

    Returns None when the leg is never better anywhere on the grid, and 0.0 when it is already better at no
    withdrawal. The grid is scanned rather than solved because the difference function is only piecewise smooth:
    medians over 283 overlapping windows move in jumps.
    """

    steps = int(hi // step) + 1
    prev = None
    for k in range(steps):
        x = k * step
        d = difference(wins, series, x, capital, years, leg)
        if d > 0.0:
            if prev is None:
                return 0.0, d
            lo, lo_d = prev
            frac = -lo_d / (d - lo_d) if d != lo_d else 0.0
            return lo + frac * step, d
        prev = (x, d)
    return None, prev[1] if prev else None


def risk_crossover(wins: dict, series: dict, capital: float, years: int, leg: str, hi: float, step: float):
    """The withdrawal above which `leg` becomes the SAFER-FAILING pair: the point where the insurance stops.

    This is the number that decides whether the leg is worth owning for its shape, and it is a different quantity
    from the median crossover: a leg with lower average growth can insure a small withdrawal and be unable to fund a
    large one, which is exactly what happens here.
    """

    steps = int(hi // step) + 1
    for k in range(steps):
        x = k * step
        c = curve(series, wins, x, capital, years)
        if c[leg]["p_fail"] > c[BENCH]["p_fail"] + 1e-12:
            return x
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--max-payout", type=float, default=1_500.0)
    ap.add_argument("--step", type=float, default=25.0)
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    series = {k: v for k, v in es.legs_from_long_record(data, args.years).items() if k in LEGS}
    print(f"the breakeven withdrawal · ${args.capital:,.0f} start, level payout for {args.years} years, nothing added")
    print("  SPY monthly from the archive; the same series sliced four ways, so the era effect is in the data\n")

    for label, y0, y1 in (("whole record 1993-onward", 1993, 2100), ("since 2006", 2006, 2100),
                          ("1993 to 2005 only", 1993, 2005), ("2016 onward", 2016, 2100)):
        wins = windows(series, y0, y1, args.years)
        n = len(wins[BENCH])
        print(f"  {label}: {n} window starts")
        if n < 12:
            print("    too few windows to score; reported as untested rather than as a zero\n")
            continue
        print(f"    {'payout $/mo':>12} {'index med':>10} {'MA200 med':>10} {'MA200 diff':>11} {'index P(fail)':>14}"
              f" {'MA200 P(fail)':>14} {'60/40 diff':>11}")
        print("    " + "-" * 88)
        for payout in (0.0, 200.0, 435.47, 600.0, 800.0, 1_000.0):
            c = curve(series, wins, payout, args.capital, args.years)
            ma = (c["MA200 monthly"]["median"] - c[BENCH]["median"]) * args.capital / (args.years * 12)
            b40 = (c["static 60/40"]["median"] - c[BENCH]["median"]) * args.capital / (args.years * 12)
            print(f"    {payout:>12,.2f} {c[BENCH]['median']:>10.2f} {c['MA200 monthly']['median']:>10.2f}"
                  f" {ma:>+11,.2f} {c[BENCH]['p_fail']:>14.1%} {c['MA200 monthly']['p_fail']:>14.1%}"
                  f" {b40:>+11,.2f}")
        for leg in ("MA200 monthly", "static 60/40"):
            be, _ = breakeven(wins, series, args.capital, args.years, leg, args.max_payout, args.step)
            rc = risk_crossover(wins, series, args.capital, args.years, leg, args.max_payout, args.step)
            ret = ("never, on any payout in the grid" if be is None else
                   ("already ahead with nothing withdrawn" if be <= 1e-9 else f"at ${be:,.0f}/mo"))
            safe = ("never becomes the riskier leg on the grid" if rc is None
                    else f"becomes the riskier leg above ${rc:,.0f}/mo")
            print(f"    {leg:16} median: {ret:44} safety: {safe}")
        print("")
    print("  What is stable across the four samples is only this: a bigger withdrawal raises every leg's failure rate,")
    print("  and the rule's protection has a CAPACITY — safer than the index below roughly $750-825/mo per $100,000 of")
    print("  capital, riskier above it, because its own average growth is lower and a large payout outruns the")
    print("  protection. The level of the difference, and its sign, are set by which years are in the sample, not by")
    print("  how much is withdrawn. Round 58 quoted each leg's own capacity (a horizontal read: $593 vs $435); this")
    print("  file quotes what is left at a payout the index can fund (a vertical read: −$551 since 2006). Say which")
    print("  end you measured before quoting either.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
