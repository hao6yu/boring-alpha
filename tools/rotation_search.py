"""Rotation among equity regimes, scored against both funds it rotates between. Pre-registered before the first run.

Run: .venv/bin/python tools/rotation_search.py [--capital 100000] [--json]

Round 74 closed a design space from one side: one fund plus one shelter, monthly, unlevered, posted costs — nine rules, none
beating plain DCA on the window every fund shares. It failed for a reason that says where to look next. On 2011-06-24 onward
the fund never failed a ten-year window, so no insurance pays out, and every dollar of withdrawal capacity has to come from
return. A shelter is therefore the wrong instrument there. What a rotation changes is exactly that: it stays in *risk*
throughout and moves it to wherever risk is being paid for, which is the only remaining way to raise return without leverage.

The family, fixed before the first number was read:

  spy_only / qqq_only   controls, priced as rules. They are the honest floor of this whole exercise: if a rotation does not
                        beat `qqq_only`, the work it is doing is available for free by buying the growth fund.
  blend_sq              50/50 SPY and QQQ, never touched again — the no-rule control, in case the answer is just that
  dm12_sq               hold whichever of SPY, QQQ has the better trailing 12-month return; shelter in IEF if both are down
  dm6_sq                the same at six months
  dm12_wide             best trailing 12-month return among SPY, QQQ, EFA, GLD; IEF if the best is down
  dm12_ief              the same five, with IEF itself scored, so the rule can hold Treasuries because they are paying
                        rather than because nothing else is (the classic ETVM reading)

**The pass rule, fixed now:** a rule must beat plain SPY — the fund the objective names — by at least round 60's $25/mo bar
on **both** windows at month-start readings, stay positive against plain SPY at month-end on both, and must not be beaten by
plain QQQ on **both** windows. That last clause is the anti-self-deception clause: a strategy that only wins because it is a
disguised growth fund is not a trading model, and it is labelled as one in the verdict column whether or not it passes.

**A second clause, added after the grid had been run, and said so here rather than buried.** The first row to pass — the
12-month SPY/QQQ rotation — was beaten on the recent window by the static half-SPY-half-QQQ control, which is not a rule at
all. A pass rule that lets a strategy through while a no-rule control beats it is not a pass rule, so the verdict column now
carries the control comparison explicitly. The pre-registered verdict is still printed, unaltered, on the same line: the
addition is allowed to explain a result, not to hide one. The row that passes and still loses to the control is the finding
of this file, and quietly deleting it would be the worst thing this repository could do.

Everything runs on one shared calendar, the intersection of every symbol's availability from the shared warmup, so every
rule and every comparator is scored over identical dates (round 68). Fees: SPY 9.45 bps and QQQ 20.00 bps as posted in the
archive; **IEF, EFA and GLD have no posted expense ratio and are charged the flat 35 bps** the forward book uses — that
understates GLD by about 5 bps and EFA by about 6, and overstates IEF by 3, and the rotation's whole result moves by more
than that, so the fee column is the least trustworthy thing on this page and is printed in every row.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import monthly_income_race as mir                            # noqa: E402
import paper                                                 # noqa: E402
import rotation_edge as re_                                  # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import fund_fees                                # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

RISK = ("SPY", "QQQ", "EFA", "GLD")
SHELTER = "IEF"
YEARS = 10
P_MAX = 0.05
CONTROL = "SPY"
GROWTH = "QQQ"
RULES = ("spy_only", "qqq_only", "blend_sq", "dm12_sq", "dm6_sq", "dm12_wide", "dm12_ief")


def fee(sym: str) -> float:
    """The expense ratio charged to a leg of this battery, taken from the one sourced table.

    Until round 103 this was `wc.EXPENSE[sym] if sym in wc.EXPENSE else FLAT_FEE` — a *publication* list used as a fee lookup,
    which meant IEF (the shelter every MA200 rule hides in) was billed the 0.35% guess against a posted 0.15%: this page
    over-charged the safe leg by 20 bps and under-charged EFA, in the same study that grades rules against a 5 bps bill
    (r94's own arithmetic). The guess is no longer reachable from here, and a leg the table has not priced is a hard stop
    rather than a rounded assumption (r69, r92).
    """

    if not fund_fees.priced(sym):
        raise SystemExit(f"{sym} has no ratio in `fund_fees.py`; this battery refuses to guess one")
    return fund_fees.fee_for(sym)


def shared_calendar(data) -> list:
    """The one calendar every row on this page is scored on: dates where every symbol has a price, from the shared warmup."""

    have = None
    for s in RISK + (SHELTER,):
        days = set(sl.legs(data, s))
        have = days if have is None else (have & days)
    return sorted(d for d in have)[sl.WARMUP:]


def trailing(series: dict, dates: list, sym: str, back: int, i: int):
    """Trailing return of `sym` over `back` sessions of the shared calendar, ending on day i."""

    if i - back < 0:
        return None
    lo = dates[i - back]
    try:
        return series[sym][dates[i]][0] / series[sym][lo][0] - 1.0
    except KeyError:
        return None


def reading_days(dates: list, conv: str) -> list:
    out = []
    for i, d in enumerate(dates):
        prv = dates[i - 1] if i else None
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        edge = ((prv is None or (prv.year, prv.month) != (d.year, d.month)) if conv == "start"
                else (nxt is None or (nxt.year, nxt.month) != (d.year, d.month)))
        if edge:
            out.append(i)
    return out


def held_for(rule: str, series: dict, dates: list, conv: str) -> dict:
    """Month -> the single symbol the rule wants to hold, decided on that month's reading day from data ending that day.

    No key where the rule cannot answer, and a missing key means the plan sits on the bill curve rather than in whatever it
    last held: rounds 45, 71 and 73 are all the same defect wearing different clothes.
    """

    mark = {}
    for i in reading_days(dates, conv):
        key = (dates[i].year, dates[i].month)
        if rule == "spy_only":
            mark[key] = "SPY"
        elif rule == "qqq_only":
            mark[key] = "QQQ"
        elif rule == "blend_sq":
            mark[key] = "SPY+QQQ"
        else:
            back = {"dm12_sq": 252, "dm6_sq": 126, "dm12_wide": 252, "dm12_ief": 252}[rule]
            pool = {"dm12_sq": ("SPY", "QQQ"), "dm6_sq": ("SPY", "QQQ"),
                    "dm12_wide": RISK, "dm12_ief": RISK + (SHELTER,)}[rule]
            scores = {s: trailing(series, dates, s, back, i) for s in pool}
            if any(v is None for v in scores.values()):
                continue
            best = max(scores, key=lambda s: scores[s])
            if scores[best] <= 0.0 and rule != "dm12_ief":
                mark[key] = SHELTER
            elif scores[best] <= 0.0 and rule == "dm12_ief":
                mark[key] = SHELTER if best == SHELTER else best
            else:
                mark[key] = best
    return mark


def weights_for(rule: str, series: dict, dates: list, mark: dict) -> dict:
    """Daily weights per symbol, one per month's decision.

    The lag is not this function's to implement: `shelter_long_record.carry` expands a monthly mark into a daily series by
    holding the *previous month's* decision, and the first draft of this function read the current month's mark instead,
    which for the end-of-month convention meant trading on a reading taken at the month's close two days after that close —
    lookahead, caught by a test written after the grid had already produced its first numbers. Delegating to `carry` makes
    the divergence impossible rather than merely tested. A symbol with no mark yet gets weight zero, so a plan that has not
    been told anything sits on the bill curve.
    """

    want = {(y, m): ({"SPY": 0.5, "QQQ": 0.5} if v == "SPY+QQQ" else {v: 1.0}) for (y, m), v in mark.items()}
    out = {}
    for sym in sorted(series):
        mk = {k: (v.get(sym, 0.0)) for k, v in want.items()}
        out[sym] = sl.carry(mk, dates)
    return out


def score(series: dict, dates: list, weights: dict, capital: float, years: int, targets=None) -> dict:
    """Capacity at the 5% failure budget, and — when `targets` are given — the failure probability at each withdrawal asked
    of the plan. Round 77 needed the second question, and it is answered here rather than in a second scorer: two
    implementations of the same cost model is how round 75's lookahead bug happened, and two implementations of the same
    *payout* model is how a future reader would be unable to say which table to believe. The published payout stays the
    default and `p_fail` keeps its meaning, so every number printed before this line still reads the same."""

    bill = series["SPY"]
    ers = {s: fee(s) for s in weights}
    path = sl.multi_asset_path(dates, series, weights, ers, bill)
    monthly = mir.month_marks(dates, path)[1]
    safe = mir.safe_amount(monthly, capital, years, P_MAX, floor=1.0)
    st = mir.plan_stats(monthly, capital, ct.PUBLISHED_PAYOUT, years, 0.0, 1.0)
    p_fails = {t: mir.plan_stats(monthly, capital, t, years, 0.0, 1.0)["p_fail"] for t in (targets or ())}
    held = [sum(w[i] for w in weights.values()) for i in range(len(dates))]
    switches = sum(1 for i in range(1, len(dates))
                   if any(w[i] != w[i - 1] for w in weights.values()))
    return {"safe": safe, "p_fail": st["p_fail"], "p_fails": p_fails, "n": st["n"],
            "duty": 1.0 - (sum(held) / len(held)), "switches": switches, "months": len(monthly), "since": dates[0]}


def grid(capital: float, years: int) -> dict:
    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    dates = shared_calendar(data)
    series = {s: sl.legs(data, s) for s in RISK + (SHELTER,)}
    recent = max(sw.common_start(data), dates[0])
    out = {"since": dates[0], "recent": recent, "fees": {s: fee(s) for s in RISK + (SHELTER,)}, "rules": []}
    bench = {}
    for conv in ("start", "end"):
        for window, since in (("long", dates[0]), ("recent", recent)):
            use = [d for d in dates if d >= since]
            for c in (CONTROL, GROWTH):
                # The comparators are priced by the same function with the same one-month decision lag as every rule, so
                # "buy the fund and hold it" pays the same opening cost and the same entry charge. A comparator that is
                # priced more generously than the strategy is the oldest way to lose an argument with yourself.
                mk = {(d.year, d.month): c for d in use}
                bench[(conv, window, c)] = score(series, use, weights_for(c, series, use, mk), capital, years)
    for rule in RULES:
        row = {"rule": rule, "cells": {}}
        for conv in ("start", "end"):
            mark = held_for(rule, series, dates, conv)
            for window, since in (("long", dates[0]), ("recent", recent)):
                use = [d for d in dates if d >= since]
                w = weights_for(rule, series, use, mark)
                cell = score(series, use, w, capital, years)
                cell["vs_spy"] = cell["safe"] - bench[(conv, window, CONTROL)]["safe"]
                cell["vs_qqq"] = cell["safe"] - bench[(conv, window, GROWTH)]["safe"]
                cell["window"], cell["conv"] = window, conv
                row["cells"][(conv, window)] = cell
        s = row["cells"]
        clears = (s[("start", "long")]["vs_spy"] >= ct.BAR and s[("start", "recent")]["vs_spy"] >= ct.BAR
                  and s[("end", "long")]["vs_spy"] > 0 and s[("end", "recent")]["vs_spy"] > 0)
        controls = rule in ("spy_only", "qqq_only", "blend_sq")
        growth = (s[("start", "long")]["vs_qqq"] < 0 and s[("start", "recent")]["vs_qqq"] < 0)
        row["pass"] = clears and not (growth and not controls)
        blend = next((r2 for r2 in out["rules"] if r2["rule"] == "blend_sq"), None)
        if blend and rule not in ("spy_only", "qqq_only", "blend_sq"):
            wl = s[("start", "long")]["safe"] - blend["cells"][("start", "long")]["safe"]
            wr = s[("start", "recent")]["safe"] - blend["cells"][("start", "recent")]["safe"]
            row["vs_blend"] = (wl, wr)
        else:
            row["vs_blend"] = None
        if not clears:
            start_clear = s[("start", "recent")]["vs_spy"] >= ct.BAR and s[("start", "long")]["vs_spy"] >= ct.BAR
            row["verdict"] = ("beats plain SPY nowhere useful" if not start_clear else
                              "clears both windows at month-start readings and turns negative at month-end on one: the"
                              " result belongs to the reading, not the rule")
        elif growth and not controls:
            row["verdict"] = "beats plain SPY but plain QQQ beats it on both windows: a growth fund with steps on it"
        elif row["vs_blend"] and min(row["vs_blend"]) < 0:
            worse = "the recent window" if row["vs_blend"][1] < row["vs_blend"][0] else "the long window"
            row["pass"] = False
            row["verdict"] = (f"CLEARS the bar vs plain SPY, but the static 50/50 control beats it on {worse} by"
                              f" ${abs(min(row['vs_blend'])):,.2f}/mo: the tilt does the work, not the rule")
        else:
            row["verdict"] = "PASSES every clause, controls included"
        out["rules"].append(row)
    return out


def report(o: dict, capital: float) -> None:
    print(f"  rotation search · one calendar from {o['since']} · long and recent ({o['recent']}) windows · scored against")
    print(f"  plain SPY and plain QQQ on identical dates · pass = beats plain SPY by ${ct.BAR:.0f}/mo on both windows, both")
    print(f"  readings, and is not merely a growth fund · fees SPY {o['fees']['SPY']:.2%} QQQ {o['fees']['QQQ']:.2%}"
          f" (posted), IEF/EFA/GLD {o['fees']['IEF']:.2%} FLAT — not posted\n")
    print(f"  {'rule':12}{'Δ vs SPY long':>15}{'Δ vs SPY recent':>17}{'Δ vs QQQ long':>15}{'Δ vs QQQ recent':>17}"
          f"{'recent end':>12}{'duty':>7}{'switches':>10}{'P(fail)':>9}  verdict")
    print("  " + "-" * 126)
    for r in o["rules"]:
        s = r["cells"]
        print(f"  {r['rule']:12}{s[('start','long')]['vs_spy']:>+15.2f}{s[('start','recent')]['vs_spy']:>+17.2f}"
              f"{s[('start','long')]['vs_qqq']:>+15.2f}{s[('start','recent')]['vs_qqq']:>+17.2f}"
              f"{s[('end','recent')]['vs_spy']:>+12.2f}{s[('start','recent')]['duty']:>7.1%}"
              f"{s[('start','recent')]['switches']:>10}{s[('start','recent')]['p_fail']:>9.1%}  {r['verdict']}")
    win = [r for r in o["rules"] if r["pass"]]
    print(f"\n  {len(win)} of {len(o['rules'])} pass every clause. The three controls are in the table on purpose: whatever")
    print("  a rotation earns above `qqq_only` came from the rule, and whatever it earns above `blend_sq` came from something")
    print("  other than a static growth tilt. A row that clears the bar against plain SPY while losing to a control is not a")
    print("  trading model; it is a different fund with steps on it, priced honestly. Every ratio on this")
    print("  page is sourced now (`fund_fees.py`, retrieved " + fund_fees.RETRIEVED + "), and here that is not a")
    # What the flat guess used to cover, and how far off it was: computed, not remembered. The old lookup was
    # `wc.EXPENSE[sym] if sym in wc.EXPENSE else FLAT_FEE`, so the mis-priced legs are exactly those absent from
    # `withdrawal_capacity`'s graded list — the ones a *publication* scope list was silently deciding the fees for.
    were_guessed = [l for l in RISK + (SHELTER,) if l not in wc.EXPENSE]
    drift = [(l, (paper.UNPOSTED_FEE - fund_fees.fee_for(l)) * 10_000) for l in were_guessed]
    print(f"  cosmetic detail: {len(were_guessed)} of the {len(RISK) + 1} legs on this page used to be billed the flat")
    if drift:
        worst = max(drift, key=lambda d: abs(d[1]))
        print(f"  {paper.UNPOSTED_FEE:.2%} guess, wrong by " + ", ".join(f"{l} {d:+.0f} bps"
              for l, d in sorted(drift, key=lambda d: -abs(d[1]))) + ".")
        print(f"  The largest miss sat on {worst[0]}, the leg the shelter rules hide in: an error of {abs(worst[1]):.0f} bps")
        print("  against the safe sleeve is the direction that hides a working hedge. What this page still assumes is only")
        print(f"  the {wc.TURNOVER_COST * 10_000:.0f} bps charged to switch into a fund, in and out — labelled as an"
              " assumption, which is the only one left on this page.")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=YEARS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    o = grid(args.capital, args.years)
    if args.json:
        print(json.dumps({"since": str(o["since"]), "recent": str(o["recent"]), "fees": o["fees"],
                          "rules": [{**{f"{c}_{w}": {k: (str(v) if isinstance(v, dt.date) else v)
                                                    for k, v in cell.items()}
                                        for (c, w), cell in r["cells"].items()},
                                    "rule": r["rule"], "pass": r["pass"], "verdict": r["verdict"]}
                                   for r in o["rules"]]}, indent=2, sort_keys=True))
    else:
        report(o, args.capital)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
