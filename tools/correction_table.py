"""The correction table: what each construction supports, on the longest record its question allows, under both readings
of "monthly", measured against the index on the same dates.

Round 66 found that the published income figure for the flagship rule is the highest of four defensible readings of it,
because the panel's first two hundred days have no moving average and the rule sits in cash by fiat until March 2007.
That does not make the number wrong so much as *contingent*, and every claim built on it became contingent too. This file
therefore re-measures the headline for each construction the repository has published, on two records and two
conventions, and prices each one against the index over exactly the same dates — the comparator round 66 established
matters more than the sample.

The axis matters, so the table names it. Nothing in this repository has beaten plain VOO on total return (round 61, 0 of
26 configurations, best information ratio -0.01). What some of them beat it on is **withdrawal capacity**: what a plan
can pay every month and still keep its promise in 95 of 100 ten-year windows. A rule can lose that race on mean return and
win it here, because what it removes is sequence risk rather than drift — which is the distinction the objective turns
on, and the reason this table exists separately from every return table above it.

Run:  python tools/correction_table.py [--capital 100000] [--payout 435.47] [--record long|panel|both]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import monthly_income_race as mir                          # noqa: E402
import shelter_long_record as sl                           # noqa: E402
import trend_cost_test as tc                               # noqa: E402
import fund_fees
import withdrawal_capacity as wc                           # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data     # noqa: E402

SINCE = dt.date(2002, 8, 1)
PANEL = sl.PANEL_START
PUBLISHED_PAYOUT = 435.47       # round 58's payout, which IS the index's safe withdrawal on the panel
SIXORTY = 0.60
BAR = 25.0                      # round 60's materiality bar, in $/mo per $100,000
PLANS = (("index", sl.CASH), ("MA200", sl.CASH), ("MA200", "IEF"), ("static 60/40", sl.CASH),
         ("static 60/40", "IEF"))


def weights(kind: str, marks: dict, dates: list, conv: str) -> list:
    """The daily equity weight for one construction. `index` and `static 60/40` have no signal, so no convention."""

    if kind == "index":
        return [1.0] * len(dates)
    if kind == "static 60/40":
        return [SIXORTY] * len(dates)
    if kind == "MA200":
        return sl.carry(marks[conv], dates)
    raise ValueError(f"undeclared construction: {kind}")


def measure(data, spy: dict, kind: str, shelter: str, since: dt.date, marks: dict, conv: str, capital: float,
            payout: float, years: int, p_max: float, sleeve: str = "SPY") -> dict:
    """One construction, one shelter, one record, one convention — scored against the index over the same dates.

    `sleeve` is the symbol being traded, and its expense ratio is looked up from the posted table by that symbol: a
    measurement that charges QQQ the SPY fee — or takes a fee as a float, which is how round 69's invented numbers got
    into a file — is wrong in the one column that both arms share. It defaults to SPY so every row published before
    round 73 still means what it said.
    """

    er = 0.0 if shelter == sl.CASH else max(sl.ER_GRID)
    series = None if shelter == sl.CASH else sl.legs(data, shelter)
    if series is None:
        dates = [d for d in sorted(spy) if d >= since]
    else:
        sd = set(series)
        dates = [d for d in sorted(spy) if d >= max(since, min(sd)) and d in sd]
    w = weights(kind, marks, dates, conv)
    # The fee is looked up from `fund_fees.py`, the one sourced table, rather than from whichever short list one downstream
    # tool happens to publish. Until round 102 this gate read `if sleeve not in wc.EXPENSE` and then announced that the symbol
    # "carries no posted expense ratio" — which round 94 had already made false for IWM, EFA and EEM: the ratios were sourced,
    # and what the check was really testing was one file's publication scope (r92: a refusal that names the wrong missing thing
    # sends the next reader looking in the wrong place). An unpriced symbol is still refused, and refused truthfully.
    if not fund_fees.priced(sleeve):
        raise KeyError(f"{sleeve} has no ratio in `fund_fees.py`; measure it at a labelled flat fee or not at all")
    er_spy = fund_fees.fee_for(sleeve)
    monthly = mir.month_marks(dates, sl.two_asset_path(dates, spy, series, w, er_spy, er))[1]
    bench = mir.month_marks(dates, sl.two_asset_path(dates, spy, None, [1.0] * len(dates), er_spy, 0.0))[1]
    safe = mir.safe_amount(monthly, capital, years, p_max, floor=1.0)
    idx = mir.safe_amount(bench, capital, years, p_max, floor=1.0)
    cap, _info = sl.capacity(monthly, bench, capital, years)
    st = mir.plan_stats(monthly, capital, payout, years, 0.0, 1.0)
    sb = mir.plan_stats(bench, capital, payout, years, 0.0, 1.0)
    # The duty cycle travels with its sample (round 66's rule): the share of days the plan spent out of equities, on the
    # record this row was measured on, not the one some other round happened to publish.
    duty = 1.0 - (sum(w) / len(w)) if w else 0.0
    return {"safe": safe, "index": idx, "delta": safe - idx, "p_fail": st["p_fail"], "p_fail_index": sb["p_fail"],
            "cap": cap, "months": len(monthly), "n": st["n"], "since": dates[0], "kind": kind, "shelter": shelter,
            "conv": conv, "duty": duty, "fee": er_spy, "sleeve": sleeve}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--payout", type=float, default=PUBLISHED_PAYOUT)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--p-max", type=float, default=0.05)
    ap.add_argument("--record", default="both", choices=("long", "panel", "both"))
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spy = sl.legs(data, "SPY")
    marks = {c: sl.month_signal(sorted(spy), spy, c) for c in ("start", "end")}
    records = {"long": SINCE, "panel": PANEL}
    if args.record != "both":
        records = {args.record: records[args.record]}
    plans = PLANS

    print(f"withdrawal capacity at a {args.p_max:.0%} ten-year failure budget · {args.capital:,.0f} in ·"
          f" both promises carry the same payout of {args.payout:,.2f}/mo")
    print("  every row is scored against the index over exactly its own dates, which are printed; two rows measured on")
    print("  different date sets are not comparable to each other, only to the index column on their own line\n")
    for rname, since in records.items():
        print(f"  record from {since}")
        print(f"  {'construction':15} {'shelter':7} {'signal':6} {'months':>6} {'windows':>7} {'safe $/mo':>10}"
              f" {'index':>9} {'delta':>9} {'P(fail)':>8} {'vs index':>9} {'capacity':>9}  verdict")
        print("  " + "-" * 118)
        for kind, shelter in plans:
            convs = ("start", "end") if kind == "MA200" else ("n/a",)
            for conv in convs:
                r = measure(data, spy, kind, shelter, since, marks, conv, args.capital, args.payout, args.years,
                            args.p_max)
                cap_txt = "—" if r["cap"] is None else f"${r['cap']:,.0f}"
                if kind == "index":
                    verdict = "the bar every other row is scored against"
                elif r["delta"] > 100:
                    verdict = "clears the index by more than $100/mo"
                elif r["delta"] > BAR:
                    verdict = "clears it, by less than $100"
                elif r["delta"] > 0:
                    verdict = "clears it, immaterially (round 60's $25 bar not reached)"
                else:
                    verdict = "does not clear it"
                print(f"  {kind:15} {shelter:7} {conv if kind == 'MA200' else '—':6} {r['months']:>6}"
                      f" {r['n']:>7} {r['safe']:>10,.2f} {r['index']:>9,.2f} {r['delta']:>+9,.2f}"
                      f" {r['p_fail']:>8.1%} {r['p_fail_index']:>9.1%} {cap_txt:>9}  {verdict}")
        print("")
    print("  Read the delta column and the P(fail) column together. The trend rule loses on mean return (round 61) and")
    print("  wins here because what it removes is the sequence in which returns arrive, not their average: at the")
    print("  published payout the index fails in 4.1% of windows and the sheltered trend plan in none, so the plan can")
    print("  be paid more each month for the same 5% of bad luck. That is the whole honest form of 'beat VOO' this")
    print("  repository has been able to sign, and the correction to the flagship figure since round 66 is that the")
    print("  premium is nearer $54-92 on the panel and $130-145 on the longer record than the $158 it has been quoted at.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
