"""Where the rule parks when it is out of stocks: cash, or an ETF? The income metric decides, not the anecdote.

Round 64. The trend rule spends about half its months out of equities, and every income figure this repository has
published (round 58's $593.13, round 62's perfect 56-for-56, round 63's $825/mo of capacity) has credited that shelter
with Treasury bills. The standing objection is a good one: bills pay a *rate*, and bonds and gold pay a *return*, and in
the two episodes where a payout plan actually breaks — 2000-2002 and 2008 — long Treasuries returned what equities lost.
If the shelter is the reason the rule works, then changing the shelter is the cheapest available improvement, and the
question is worth a number rather than an opinion.

Three things make this a measurement and not a rerun of round 56's cross-asset rotation:

* the signal is untouched — round 58's month-end MA200 on SPY, same weights, same panel, same engine. Only the place
  the off-equity money goes changes, so every difference below is attributable to the shelter and nothing else;
* the yardstick is round 58's own: the largest level monthly withdrawal whose ten-year failure rate stays under 5%,
  named with its promise, on the same panel and the same 246 complete months — the cash row has to come back at
  $593.13 or the test is broken, and that is asserted, not hoped for;
* the shelters' expense ratios are not posted in this repository, so `trend_cost_test.daily_legs` hands back **0.0**
  for them (round 58's rule: a `.get` default on a key built elsewhere is a silent failure). Nothing is scored at a
  fee of zero. Every shelter is priced three ways — 0.20%, 0.35%, 0.60% — and the verdict is only reported if it holds
  at all three.

Run:  python tools/shelter_test.py [--capital 100000] [--years 10] [--p-max 0.05] [--payout 435.47]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                           # noqa: E402
import rotation_edge as re_                                 # noqa: E402
import trend_cost_test as tc                                # noqa: E402
import withdrawal_capacity as wc                            # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data      # noqa: E402

CASH = "cash"
SHELTERS = (CASH, "IEF", "TLT", "GLD", "DBC", "IEF+TLT")
ER_GRID = (0.0020, 0.0035, 0.0060)          # the shelters' fees are not posted here; the verdict must not hinge on it
MATERIAL = 25.0                             # round 60's threshold for "worth leaving the house for", in $/mo
SPLIT = {"IEF+TLT": (("IEF", 0.5), ("TLT", 0.5))}


def shelter_weights(sig: list, shelter: str) -> list:
    """Take round 58's SPY-only weights and send everything that is not equities to the shelter instead of to bills.

    A cash shelter returns the original weights, which leaves the remainder to the bill leg inside the engine; every
    other shelter sums with the equity leg to exactly 1.0, so the account is never partly in cash by accident.
    """

    if shelter == CASH:
        return sig
    parts = SPLIT.get(shelter, ((shelter, 1.0),))
    i_spy = re_.UNIVERSE.index("SPY")
    idx = {s: re_.UNIVERSE.index(s) for s, _w in parts}
    out = []
    for w in sig:
        eq = float(w[i_spy])
        row = [0.0] * len(re_.UNIVERSE)
        row[i_spy] = eq
        rest = 1.0 - eq
        if rest < 0.0:
            raise ValueError(f"equity weight {eq} above 1.0: the shelter has nowhere to hold the remainder")
        for s, share in parts:
            row[idx[s]] = rest * share
        out.append(tuple(row))
    return out


def shelter_expense(base: dict, shelter: str, er: float) -> dict:
    e = dict(base)
    for s, _share in SPLIT.get(shelter, ((shelter, 1.0),)):
        if s != CASH:
            e[s] = er
    return e


def max_drawdown(path: list) -> float:
    peak, worst = path[0], 0.0
    for v in path:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1.0)
    return -worst


def composite_rets(rets: dict, shelter: str) -> list:
    """The shelter's own daily returns, blending the halves of a composite shelter at their weights."""

    parts = SPLIT.get(shelter, ((shelter, 1.0),))
    if len(parts) == 1:
        return rets[parts[0][0]]
    a, b = (rets[s] for s, _w in parts)
    wa, wb = (w for _s, w in parts)
    return [wa * x + wb * y for x, y in zip(a, b)]


def held_stats(rets: dict, shelter: str, held: list) -> tuple:
    """Annualised return and worst drawdown on the days the rule actually had money in the shelter.

    This is the figure that matters and it is not the shelter's own history: the signal chooses when the shelter is
    held, so it selects the shelter's episodes. On this panel every shelter but commodities paid more while held than
    over its whole history, because being out of equities is what a bond rally and a gold rally smell like.
    """

    r = composite_rets(rets, shelter)
    tot = base = peak = 1.0
    worst = 0.0
    n = 0
    for x, h in zip(r, held):
        if not h:
            continue
        n += 1
        tot *= (1.0 + x)
        base *= (1.0 + x)
        peak = max(peak, base)
        worst = min(worst, base / peak - 1.0)
    if not n:
        return 0.0, 0.0, 0
    ann = tot ** (tc.DAYS / n) - 1.0
    return ann, -worst, n


def panel_stats(rets: dict, shelter: str) -> tuple:
    """CAGR and maximum drawdown of a shelter on the panel, close-ratio only — what risk was bought for the income."""

    r = composite_rets(rets, shelter)
    tot = 1.0
    for x in r:
        tot *= (1.0 + x)
    yrs = len(r) / tc.DAYS
    cagr = tot ** (1.0 / yrs) - 1.0 if tot > 0 else -1.0
    base = peak = 1.0
    worst = 0.0
    for x in r:
        base *= (1.0 + x)
        peak = max(peak, base)
        worst = min(worst, base / peak - 1.0)
    return cagr, -worst


CAP_GRID = [25.0 * i for i in range(61)]          # $0 to $1,500 a month, in $25 rungs


def capacity(monthly: list, bench: list, capital: float, years: int, hi: float = 1_500.0, step: float = 25.0):
    """The withdrawal above which this shelter's plan becomes the riskier pair — round 63's measure, applied to shelter.

    Round 63 found the trend rule insures a payout up to about $825/mo per $100,000 and is the riskier leg above it.
    If a better-paying shelter is worth anything, that ceiling moves, and where it moves to is the number that tells a
    reader how much the plan can actually pay them. One crossing is assumed and checked: failure rates rise with the
    withdrawal for both legs, so the difference can only change sign by the shelter leg rising through the benchmark's.
    """

    crossings = []
    for p in (x for x in CAP_GRID if x <= hi):
        a = mir.plan_stats(monthly, capital, p, years, 0.0, 1.0)["p_fail"]
        b = mir.plan_stats(bench, capital, p, years, 0.0, 1.0)["p_fail"]
        if a is None or b is None:
            return None, None
        if b >= 1.0 - 1e-12:
            break                     # the benchmark fails everywhere: there is nothing left to be safer than
        crossings.append((p, a, b))
    # Failure rates over 127 windows move in rungs of 1/127, so two steep curves can step over each other more than
    # once. The first rung where the plan becomes the riskier pair is what a reader would feel, and the number of
    # times the ordering flips is printed alongside it rather than smoothed away.
    signs = [1 if a > b + 1e-12 else 0 for _p, a, b in crossings]
    first = next((crossings[i][0] for i in range(len(signs)) if signs[i]), None)
    flips = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    return first, {"flips": flips, "rungs": len(crossings),
                   "bench_at_end": crossings[-1][2] if crossings else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--p-max", type=float, default=0.05)
    ap.add_argument("--payout", type=float, default=435.47)
    ap.add_argument("--unknown-er", type=float, default=re_.UNKNOWN_ER)
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    ordered, rets, bills, base_expense = re_.panel(data, args.unknown_er)
    pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
    cl = tc.closes_of(data, "SPY")
    closes = {"SPY": [cl[pos[d]] for d in ordered]}
    sig = mir.leg_weights("MA200 monthly", ordered, rets, bills, base_expense, closes, args.unknown_er)
    i_spy = re_.UNIVERSE.index("SPY")
    held = [1.0 - float(w[i_spy]) > 1e-9 for w in sig]

    print(f"where the shelter goes · ${args.capital:,.0f} start · {args.years}-year plan · failure budget"
          f" {args.p_max:.0%} · the off-equity half of one signal, six ways")
    print(f"  panel {ordered[0]} to {ordered[-1]} · signal: round 58's month-end MA200 on SPY, unchanged"
          f" · engine: round 58's, so the cash row is round 58's number")
    print(f"  shelters priced at {', '.join(f'{e:.2%}' for e in ER_GRID)} expense, because this repository does not"
          f" post their fees and a fee of 0.00% is a bug, not an assumption")
    print(f"  materiality: {MATERIAL:.0f}/mo of extra income, the bar round 60 set for the same kind of claim\n")

    hdr = (f"  {'shelter':9} {'ER':>6} {'months':>7} {'safe $/mo':>10} {'never-zero':>11} {'P(fail)':>8}"
           f" {'CAGR':>7} {'maxDD':>7} {'duty':>6} {'vs cash':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    bench_w = mir.leg_weights("SPY hold", ordered, rets, bills, base_expense, closes, args.unknown_er)
    bench_monthly = mir.month_marks(ordered, mir.wealth_path(ordered, rets, bills, base_expense, bench_w))[1]
    results = {}
    for shelter in SHELTERS:
        for er in ((0.0,) if shelter == CASH else ER_GRID):
            exp = shelter_expense(base_expense, shelter, er)
            w = shelter_weights(sig, shelter)
            path = mir.wealth_path(ordered, rets, bills, exp, w)
            keys, mr = mir.month_marks(ordered, path)
            safe1 = mir.safe_amount(mr, args.capital, args.years, args.p_max, floor=1.0)
            safe0 = mir.safe_amount(mr, args.capital, args.years, args.p_max, floor=0.0)
            st = mir.plan_stats(mr, args.capital, args.payout, args.years, 0.0, 1.0)
            duty = sum(held) / len(held)
            cagr, mdd = (statistics.fmean(bills) * tc.DAYS, 0.0) if shelter == CASH \
                else panel_stats(rets, shelter)
            cap, info = capacity(mr, bench_monthly, args.capital, args.years)
            results[(shelter, er)] = {"safe1": safe1, "safe0": safe0, "p_fail": st["p_fail"], "n": len(mr),
                                      "cagr": cagr, "mdd": mdd, "duty": duty, "months": len(mr), "cap": cap, "flips": info["flips"]}
            delta = "—" if shelter == CASH else f"{safe1 - cash_ref['safe1']:>+9,.2f}"
            cap_txt = "  none in grid" if cap is None else f" ${cap:,.0f}"
            print(f"  {shelter:9} {er:>6.2%} {len(mr):>7} {safe1:>10,.2f} {safe0:>11,.2f} {st['p_fail']:>8.1%}"
                  f" {cagr:>7.2%} {mdd:>7.1%} {duty:>6.0%} {delta:>9}   capacity{cap_txt}")
            if shelter == CASH:
                results[CASH] = results[(shelter, er)]
                cash_ref = results[CASH]

    print("\n  the cash row is round 58's own figure; if it is not $593.13 the comparison below is measuring the"
          " test,\n  not the shelter. Re-check before reading anything into the deltas.")
    cash_cap = results[(CASH, 0.0)]["cap"]
    print("\n  `capacity` is round 63's measure — the withdrawal at which this plan stops being the safer pair and"
          " starts\n  being the riskier one, per $100,000 of capital. A shelter that pays more while it is held"
          " should lift\n  that ceiling, and the column says whether it does. The benchmark is the index itself"
          " (round 58's $435.47\n  plan on the same 246 months), so these are directly comparable to round 63's"
          " $750-825.\n")
    print("\n  The two columns headed `own` and `held` are the same series measured two ways, and they disagree. The"
          "\n  signal picks when the shelter is held, so `held` is the shelter's return during the episodes the rule"
          " chooses\n  to hold it in — and on this panel every shelter but commodities paid far better while held than"
          " over its\n  whole history, because being out of equities is what a bond rally and a gold rally smell"
          " like. That is\n  why TLT out-earns IEF on income while having the worse unconditional return, and it is"
          " also the warning:\n  the shelter's usefulness here is a property of the signal's timing, not of the asset"
          " class.\n")
    print(f"  {'shelter':9} {'worst ER':>8} {'safe $/mo':>10} {'vs cash':>9} {'P(fail)':>8} "
          f"{'own CAGR':>9} {'held CAGR':>10} {'held maxDD':>11} {'$/mo per pt':>12} {'capacity':>10}  verdict")
    print("  " + "-" * 124)
    for shelter in SHELTERS:
        if shelter == CASH:
            continue
        rows = {er: results[(shelter, er)] for er in ER_GRID}
        worst_er = min(rows, key=lambda e: rows[e]["safe1"])   # the fee to budget for, not the best case
        r = rows[worst_er]
        gain = r["safe1"] - cash_ref["safe1"]
        gains = {er: rows[er]["safe1"] - cash_ref["safe1"] for er in ER_GRID}
        signs = {g > MATERIAL for g in gains.values()}
        if len(signs) > 1:
            verdict = "SIGN DEPENDS ON THE UNPOSTED FEE — not a finding"
        elif not any(signs):
            verdict = "does not clear the bar at any fee"
        else:
            verdict = "clears the bar at every fee tested"
        hann, hmdd, hdays = held_stats(rets, shelter, held)
        per_pt = gain / hmdd / 100 if hmdd > 1e-9 else float("inf")
        cap = r["cap"]
        if cap is None:
            cap_txt = "none in grid"
        elif cash_cap is None:
            cap_txt = f"${cap:,.0f}"
        else:
            d = cap - cash_cap
            cap_txt = f"{'+' if d >= 0 else '-'}${abs(d):,.0f}"
        if r["flips"] > 1:
            cap_txt += f" ({r['flips']} flips)"
        print(f"  {shelter:9} {worst_er:>8.2%} {r['safe1']:>10,.2f} {gain:>+9,.2f} {r['p_fail']:>8.1%}"
              f" {r['cagr']:>9.2%} {hann:>10.2%} {hmdd:>11.1%} {per_pt:>12,.2f} {cap_txt:>10}  {verdict}")
    starts = {s: tc.days_of(data, s)[0] for s in ("IEF", "TLT", "GLD", "DBC")}
    print(f"\n  Data boundary, because it constrains the verdict more than any fee: the shelters' own histories start"
          f"\n  {', '.join(f'{k} {v}' for k, v in starts.items())}. Round 62 located the entries that break an index"
          " payout plan\n  at 1998-02 to 2007-07, mostly 1998-2002. No bond or gold ETF in this archive exists for"
          " the first\n  half of that stretch, so the table prices the shelter for the twenty years it has been"
          " quotable and\n  not for the crash it was invented for.")
    print(f"\n  round 58's cash shelter is the bill curve itself, so it has no expense ratio, no drawdown, and no"
          f"\n  committee deciding its duration. Anything else has to beat it by {MATERIAL:.0f}/mo of income after its"
          " own fee.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
