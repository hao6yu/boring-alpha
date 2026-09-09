"""What a model is worth when you are putting money IN rather than taking it out.

Round 60. Rounds 52, 54 and 58 priced withdrawal plans: a lump sum, a level payout, a failure budget. That is the
right frame for a retirement and the wrong frame for this objective, which is "earn extra each month" — a person with
a job, a monthly contribution, and an account that is still growing. In that frame sequence risk works in your favour,
the terminal figure is dominated by the money you added rather than by the order it arrived in, and the question
changes shape completely.

Plan: start with `--capital`, add `--contribution` every month for `--years`, take nothing out. Four legs, the same
ones round 58 used, on the same panel and the same monthly marks, so the two tables can be read against each other.
Windows are every 10-year stretch of the panel, as before.

Three statistics, and the first one is the only honest headline for a contribution plan:

  * **the model's advantage, as dollars a month** — median terminal wealth for the leg minus median for the index,
    divided by the number of months. Everything else is decoration around this.
  * **P(terminal < total contributed)** — the plan returned less than you put in. Not a drawdown, not a loss on the
    screen: the actual failure of a contribution plan, which is that fifteen years of saving ended smaller than the
    saving itself.
  * **the median multiple of contributions** — how much each dollar saved became.

Run:  python tools/contribution_race.py [--capital 20000] [--contribution 1000] [--years 10]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                        # noqa: E402
import plan_survival as ps                               # noqa: E402
import rates_gate as rg                                  # noqa: E402
import rotation_edge as re_                              # noqa: E402
import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

CAPITALS = (0.0, 20_000.0, 50_000.0, 100_000.0, 250_000.0)
CONTRIBUTIONS = (500.0, 1_000.0, 2_000.0)
ERAS = (("1993-2004", 1993, 2004), ("2005-2015", 2005, 2015), ("2016-now", 2016, 2100))


def long_record(data, contribution: float, years: int, era_years_len: int) -> dict:
    """The same plan on SPY's whole record, from 1993.

    Round 58 was a lesson about sample boundaries and this file's panel starts in 2006 — the exact stretch in which
    trend timing lost (rounds 55, 56, 59). Quoting the panel alone would repeat that mistake, so the panel figure is
    read against the long record and both era splits are printed. This block uses the monthly convention of
    `rates_gate`, which round 59 measured at 0.027pp of CAGR and $6.38 a month against the panel engine.
    """

    out, keys, eq, cash, _y, _sg = rg.series(data, years, 100_000.0, 0.05)
    series = {"SPY hold": out["SPY hold"]["m"], "MA200 monthly": out["MA200 monthly"]["m"],
              "static 60/40": [0.6 * a + 0.4 * b for a, b in zip(eq[1:], cash[1:])]}
    era_years = {}
    for label, lo, hi in ERAS:
        era_years[label] = {}
        for leg, m in series.items():
            months = era_years_len * 12
            idx = [i for i in range(0, len(m) - months + 1) if lo <= keys[1 + i].year <= hi]
            if len(idx) < 12:
                era_years[label][leg] = {"n": len(idx), "median": None}
                continue
            terms = sorted(ps.simulate(m[i:i + months], 0.0, 0.0, contribution, 0.0)["terminal"] for i in idx)
            era_years[label][leg] = {"n": len(idx), "median": statistics.median(terms)}
            era_years[label][leg]["years"] = era_years_len
    whole = {leg: summary(run_windows(m, 0.0, contribution, years), 0.0, contribution, years)
             for leg, m in series.items()}
    return {"legs": series, "eras": era_years, "whole": whole}


def run_windows(monthly: list, c0: float, contribution: float, years: int) -> list:
    """Every window of the plan's length, simulated with the contribution stream and no withdrawal."""

    months = years * 12
    out = []
    for i in range(0, len(monthly) - months + 1):
        r = ps.simulate(monthly[i:i + months], c0, 0.0, contribution, 0.0)
        out.append(r)
    return out


def summary(out: list, c0: float, contribution: float, years: int) -> dict:
    n = len(out)
    if not n:
        return {"n": 0, "median": None, "p_under": None, "mult": None, "min": None}
    total = c0 + contribution * years * 12
    terms = sorted(o["terminal"] for o in out)
    return {"n": n,
            "median": statistics.median(terms),
            "min": terms[0],
            "p_under": sum(1 for o in out if o["terminal"] < total - 1e-9) / n,
            "mult": statistics.median(terms) / total,
            "total": total}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=20_000.0)
    ap.add_argument("--contribution", type=float, default=1_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--unknown-er", type=float, default=re_.UNKNOWN_ER)
    ap.add_argument("--era-years", type=int, default=5,
                    help="plan length for the era block: a 10-year plan leaves too few recent windows to score")
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    ordered, rets, bills, expense = re_.panel(data, args.unknown_er)
    pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
    cl = tc.closes_of(data, "SPY")
    closes = {"SPY": [cl[pos[d]] for d in ordered]}
    marks = {}
    for leg in mir.LEGS:
        w = mir.leg_weights(leg, ordered, rets, bills, expense, closes, args.unknown_er)
        keys, mr = mir.month_marks(ordered, mir.wealth_path(ordered, rets, bills, expense, w))
        marks[leg] = mr
    nmonths = len(marks["SPY hold"])
    print(f"a contribution plan · {ordered[0]} to {ordered[-1]} · {nmonths} months · legs {list(mir.LEGS)}")
    print(f"  nothing is withdrawn; the only cash flow in is ${args.contribution:,.0f} a month for"
          f" {args.years} years; every leg on the same {nmonths} months\n")

    print(f"  ${args.capital:,.0f} start + ${args.contribution:,.0f}/mo for {args.years} years"
          f"  (total in: ${args.capital + args.contribution * 12 * args.years:,.0f})\n")
    print(f"  {'leg':17} {'median end':>12} {'x contributed':>14} {'P(< contributed)':>17} {'worst end':>12}"
          f"   {'advantage over index':>21}")
    print("  " + "-" * 96)
    base = summary(run_windows(marks["SPY hold"], args.capital, args.contribution, args.years),
                   args.capital, args.contribution, args.years)
    for leg in mir.LEGS:
        s = summary(run_windows(marks[leg], args.capital, args.contribution, args.years),
                    args.capital, args.contribution, args.years)
        adv = s["median"] - base["median"]
        note = "the bar" if leg == "SPY hold" else f"{adv / (args.years * 12):+,.2f}/mo"
        print(f"  {leg:17} {s['median']:>12,.0f} {s['mult']:>14.3f} {s['p_under']:>17.1%} {s['min']:>12,.0f}"
              f"   {note:>21}")

    print("\n  the model's advantage as dollars a month, at every capital and every contribution rate")
    print("  (the same four legs, so the pattern is the arithmetic of it, not one leg's luck)")
    print(f"  {'$/mo in':>9} {'start':>10} " + " ".join(f"{leg[:13]:>14}" for leg in mir.LEGS[1:])
          + f"  {'best of the three':>18}")
    print("  " + "-" * 88)
    for contrib in CONTRIBUTIONS:
        for c0 in CAPITALS:
            cells, vals = [], []
            for leg in mir.LEGS[1:]:
                s = summary(run_windows(marks[leg], c0, contrib, args.years), c0, contrib, args.years)
                b = summary(run_windows(marks["SPY hold"], c0, contrib, args.years), c0, contrib, args.years)
                v = (s["median"] - b["median"]) / (args.years * 12)
                vals.append((v, leg))
                cells.append(f"{v:>+14,.2f}")
            best = max(vals)
            print(f"  {contrib:>9,.0f} {c0:>10,.0f} " + " ".join(cells)
                  + f"  {best[1][:13]:>11} {best[0]:>+6.2f}")
    print("  A contribution stream is a large fixed annuity with a small investment return attached to it, and the")
    print("  second block is what the investment part of that sentence is worth. Where the model's figure is close to")
    print("  zero, it is close to zero because the contributions are doing the work.")
    print("")
    print("  the same plan on SPY's whole record from 1993, because this panel starts in 2006 — the one stretch of")
    print("  the record in which trend timing is known to lose (rounds 55, 56, 59). $0 start, no withdrawal.")
    lh = long_record(data, args.contribution, args.years, args.era_years)
    b = lh["whole"]["SPY hold"]["median"]
    print(f"  {'leg':17} {'median end':>12} {'x contributed':>14} {'P(< contributed)':>17}"
          f"   {'advantage over index':>21}")
    print("  " + "-" * 78)
    for leg, s in lh["whole"].items():
        note = "the bar" if leg == "SPY hold" else f"{(s['median'] - b) / (args.years * 12):+,.2f}/mo"
        print(f"  {leg:17} {s['median']:>12,.0f} {s['mult']:>14.3f} {s['p_under']:>17.1%}   {note:>21}")
    print("")
    print(f"  by era of window start, advantage over the index in $/mo, same ${args.contribution:,.0f}/mo"
          f" contributed, over a {args.era_years}-year plan:")
    print(f"  {'leg':17} " + " ".join(f"{lbl:>18}" for lbl, _lo, _hi in ERAS))
    print("  " + "-" * 60)
    for leg in lh["legs"]:
        cells = []
        for label, _lo, _hi in ERAS:
            e = lh["eras"][label][leg]
            base = lh["eras"][label]["SPY hold"]["median"]
            if e["median"] is None or base is None:
                cells.append(f"{'untested':>11} (n={e['n']:<2})")
            elif leg == "SPY hold":
                cells.append(f"{'the bar':>11} (n={e['n']:<2})")
            else:
                cells.append(f"{(e['median'] - base) / (e['years'] * 12):>+11,.0f} (n={e['n']:<2})")
        print(f"  {leg:17} " + " ".join(cells))

    print("")
    print("  the question the objective actually asks: how much money has to be at work before a model is worth")
    print(f"  building at all? The figure is the best of the three non-index legs, at ${args.contribution:,.0f}/mo"
          " of contributions.")
    for target in (25.0, 50.0, 100.0, 250.0):
        hit = None
        for c0 in CAPITALS:
            b = summary(run_windows(marks["SPY hold"], c0, args.contribution, args.years),
                        c0, args.contribution, args.years)
            v = max(summary(run_windows(marks[leg], c0, args.contribution, args.years),
                            c0, args.contribution, args.years)["median"] - b["median"]
                    for leg in mir.LEGS[1:]) / (args.years * 12)
            if v >= target:
                hit = c0
                break
        if hit is None:
            where = "not anywhere in the range tested (up to $%s)" % f"{CAPITALS[-1]:,.0f}"
        else:
            where = "at $%s of start capital" % f"{hit:,.0f}"
        print(f"    to clear ${target:>5,.0f} a month: {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
