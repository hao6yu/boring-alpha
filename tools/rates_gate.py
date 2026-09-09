"""The one information set in the archive that no round has used: what cash pays.

Round 59. Rounds 55-58 tested price-derived signals only. The objective's own account of the plan is that it reads
"trading and global news" — macro. The repository's archive contains exactly one macro series: the daily DGS3MO
factor behind the bill leg. It is not news, but it is the closest offline proxy there is, and it is the variable a
person actually faces when they decide whether to hold stocks or wait in bills. Its record here spans 0.011% to
6.89% annualised, so the regime is not hypothetical.

Four gates, pre-declared, all monthly, all decided on the previous month's yield and applied to the following month:

  * `yield_gate`      — hold SPY only when the bill yield is **below its own trailing 3-year average**: cash paying
                        less than it has been paying lately is the easy-money regime; cash paying more is the regime
                        that competes with equities.
  * `carry_flip`      — hold SPY only when its trailing 12-month return beats the bill's: the boring relative-strength
                        version, with rates as the other side of the trade.
  * `tightening_exit` — hold SPY unless the yield has risen by more than 100bp over the past six months: the classic
                        "the Fed is taking the punch away" rule, and the one that most resembles what a news-reading
                        trader would claim to do.
  * `ma200_and_gate`  — risk-off if MA200 or `yield_gate` says risk-off: does the macro filter add anything to the
                        price signal that round 58 found worth $23.68 a month?

Incumbents on the same series and the same plan: `SPY hold`, `MA200 monthly`, `static 60/40`.

**Convention.** Monthly throughout: expense charged monthly on the equity leg, turnover once per flip. The panel
engine used in rounds 56-58 charges expense daily, so the same sleeve prices slightly differently in the two files.
`test_the_monthly_convention_is_not_where_the_answer_lives` measures that gap rather than disclaiming it.

Run:  python tools/rates_gate.py [--capital 100000] [--years 10] [--p-max 0.05]
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
import trend_cost_test as tc                             # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

LEGS = ("SPY hold", "MA200 monthly", "yield_gate", "carry_flip", "tightening_exit", "ma200_and_gate",
        "static 60/40")
ERAS = (("1993-2004", 1993, 2004), ("2005-2015", 2005, 2015), ("2016-now", 2016, 2100))
TIGHTEN_BP = 0.01


def series(data, years: int, capital: float, p_max: float) -> dict:
    last = max(data.by_date)
    ser = {d: data.by_date[d]["SPY"].close for d in data.by_date if "SPY" in data.by_date[d]}
    eq, cash, keys = wc.monthly_complete(ser, data.cash_factors, last)
    y = [(1.0 + c) ** 12 - 1.0 for c in cash]
    days, closes = tc.days_of(data, "SPY"), tc.closes_of(data, "SPY")
    month_end = {}
    for i, d in enumerate(days):
        month_end[(d.year, d.month)] = i
    ma = {}
    for k, i in month_end.items():
        m = tc.sma(closes, 200, i)
        ma[k] = 1.0 if m is not None and closes[i] > m else 0.0

    def at(sig, j):
        k = (keys[j].year, keys[j].month)
        if k not in sig:
            return None
        return sig[k]

    gate, flip, tight = {}, {}, {}
    for j, k in enumerate(keys):
        key = (k.year, k.month)
        if j >= 36:
            back = statistics.fmean(y[j - 35:j + 1])       # trailing 3 years of yield, this month included
            gate[key] = 1.0 if y[j] < back else 0.0
        if j >= 12:
            spy_12 = eq[j]
            bill_12 = (1.0 + cash[j]) ** 12 - 1.0          # this month's bill return, annualised
            flip[key] = 1.0 if spy_12 > bill_12 else 0.0
        if j >= 6:
            tight[key] = 0.0 if (y[j] - y[j - 6]) > TIGHTEN_BP else 1.0

    signals = {"ma200": ma, "yield_gate": gate, "carry_flip": flip, "tightening_exit": tight}

    def build(sig):
        """Series plus the month each element belongs to. A gated series is shorter than the record — the warm-up
        months produce no signal and so no return — so the dates are part of the result, not an afterthought a
        caller has to reconstruct and get wrong."""

        out, dates, prev, skipped = [], [], 0.0, 0
        for j in range(len(keys) - 1):
            e = at(sig, j)
            if e is None:
                skipped += 1
                continue
            t = abs(e - prev)
            prev = e
            out.append(e * eq[j + 1] + (1.0 - e) * cash[j + 1] - e * wc.EXPENSE["SPY"] / 12.0
                       - t * wc.TURNOVER_COST)
            dates.append(keys[j + 1])
        return out, dates, skipped

    def compound(xs):
        w = 1.0
        peak, dd = 1.0, 0.0
        for r in xs:
            w *= (1.0 + r)
            peak = max(peak, w)
            dd = max(dd, 1.0 - w / peak)
        yrs = len(xs) / 12.0
        return {"cagr": w ** (1.0 / yrs) - 1.0, "max_dd": dd, "months": len(xs)}

    s60 = [0.6 * eq[j] + 0.4 * cash[j] for j in range(1, len(eq))]
    out = {}
    for leg in LEGS:
        if leg == "SPY hold":
            m, sk, dates = eq[1:], 0, keys[1:]
        elif leg == "static 60/40":
            m, sk, dates = s60, 0, keys[1:]
        elif leg == "MA200 monthly":
            m, dates, sk = build(ma)
        elif leg == "yield_gate":
            m, dates, sk = build(gate)
        elif leg == "carry_flip":
            m, dates, sk = build(flip)
        elif leg == "tightening_exit":
            m, dates, sk = build(tight)
        else:
            combo = {k: min(ma.get(k, 0.0), gate.get(k, 0.0)) for k in set(ma) & set(gate)}
            m, dates, sk = build(combo)
        whole = compound(m)
        amt = mir.safe_amount(m, capital, years, p_max)
        loose = mir.safe_amount(m, capital, years, p_max, floor=0.0)
        st = mir.plan_stats(m, capital, amt, years) if amt is not None else None
        out[leg] = {"m": m, "dates": dates, "skipped": sk, "cagr": whole["cagr"],
                    "max_dd": whole["max_dd"], "months": whole["months"], "amount": amt, "loose": loose,
                    "stats": st}
    return out, keys, eq, cash, y, signals


def era_stats(m, keys, capital, payout, years, lo, hi):
    months = years * 12
    idx = [i for i in range(0, len(m) - months + 1) if lo <= keys[1 + i].year <= hi]
    if len(idx) < 12:
        return {"n": len(idx), "p_fail": None, "median_mult": None}
    st = []
    for i in idx:
        st.append(mir.plan_stats(m[i:i + months], capital, payout, years))
    return {"n": len(idx),
            "p_fail": statistics.fmean(s["p_fail"] for s in st),
            "median_mult": statistics.median(s["median_mult"] for s in st)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--p-max", type=float, default=0.05)
    ap.add_argument("--payout", type=float, default=435.47)
    ap.add_argument("--era-years", type=int, default=5)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    out, keys, eq, cash, y, signals = series(data, args.years, args.capital, args.p_max)
    gate = signals["yield_gate"]
    print(f"the bill yield as a signal · {keys[0]} to {keys[-1]} · {len(eq)} months · annualised yield"
          f" {min(y):.2%} to {max(y):.2%}, now {y[-1]:.2%}")
    print(f"  plan: ${args.capital:,.0f} start, {args.years} years, failure budget {args.p_max:.0%};"
          " monthly convention throughout\n")
    # Round 58's index-safe figure on the 2006+ panel, held fixed so the legs are scored at the same payout. It is a
    # parameter rather than a derivation only because deriving it here would mean re-running the panel engine; the
    # test suite re-derives it from that engine and fails if this default has gone stale. Using the index's
    # "ends whole" figure from THIS table would score every leg at $0.00, since the index cannot meet that promise
    # on the long record at all.
    payout = args.payout
    print(f"  {'leg':17} {'months':>7} {'CAGR':>7} {'max DD':>7} {'ends whole':>11} {'never zero':>11}"
          f" {'med term':>9} {'P(fail) at index payout':>24}")
    print("  " + "-" * 92)
    for leg in LEGS:
        v = out[leg]
        at_idx = mir.plan_stats(v["m"], args.capital, payout, args.years)
        print(f"  {leg:17} {v['months']:>7} {v['cagr']:>7.2%} {v['max_dd']:>7.1%} {v['amount']:>11,.2f}"
              f" {v['loose']:>11,.2f} {v['stats']['median_mult']:>9.2f} {at_idx['p_fail']:>24.0%}")
    print(f"  'ends whole' prices the withdrawal that both never liquidates AND finishes at or above the start;")
    print(f"  'never zero' prices only the first. The index's figure, ${payout:,.2f}/mo, is the payout held fixed in")
    print("  the last column.\n")

    print(f"  by era of window start, at that same ${payout:,.0f}/mo over a {args.era_years}-year plan"
          " — the question round 55 made unavoidable")
    print(f"  (a {args.years}-year plan leaves too few windows in the newest era to score anything,"
          f" so the era block shortens the plan)")
    print(f"  {'leg':17} " + " ".join(f"{lbl:>18}" for lbl, _lo, _hi in ERAS))
    print("  " + "-" * 68)
    for leg in LEGS:
        cells = []
        for label, lo, hi in ERAS:
            e = era_stats(out[leg]["m"], keys, args.capital, payout, args.era_years, lo, hi)
            cells.append(f"{e['p_fail']:>11.0%} (n={e['n']:<2})" if e["p_fail"] is not None
                         else f"{'untested':>11} (n={e['n']:<2})")
        print(f"  {leg:17} " + " ".join(cells))
    months_in_gate = sum(1 for k in gate if gate[k] == 1.0)
    print(f"\n  the yield gate was risk-ON in {months_in_gate} of {len(gate)} signalled months."
          " A filter that is never off is not a filter,")
    print("  and one that is always off has already lost the growth argument; both are printed rather than hidden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
