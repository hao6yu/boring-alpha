"""A growth tilt with a trend brake, priced against the control it has to beat. Pre-registered before the first run.

Run: .venv/bin/python tools/tilt_brake.py [--capital 100000] [--json]

Round 75 ended on an uncomfortable symmetry. The strongest row on the page was a static half-SPY-half-QQQ blend that makes
no decisions at all (+$182.64/mo per $100k against plain SPY on the recent window, +$154.18 on the long one), and the rule
that finally cleared the old bar gave back $94.35/mo of that on the recent window while collecting +$252.10 on the record
that contains crashes. The obvious synthesis — keep the tilt, add the brake — is the hypothesis this file exists to kill or
keep, and it was written down in round 75's note before any number here was read.

**What has to be different this time is the bar.** Beating plain SPY is no longer the test: rounds 73 to 75 established that
almost anything holding growth clears it on this archive, which is why the comparator here is the **control the hypothesis
is an amendment to** — the static blend. Four clauses, fixed before the first run:

  1. beat the static blend by at least round 60's $25/mo on **both** windows, at month-start readings;
  2. stay no worse than the blend at month-end readings on both windows, so the result is not a calendar artefact;
  3. do not raise the failure probability at the published payout, since a brake that buys capacity by accepting more left
     tail is not a brake;
  4. and not be beaten by plain QQQ on both windows, carried over from round 75 — a strategy that is only a growth fund
     with steps on it is still only that.

The family, deliberately small, all built on the same tilt:

  brake_both      50/50 SPY/QQQ normally; the whole book to IEF when **both** sleeves are under their own 200-day average
  brake_half      the same trigger, but only half the book goes to IEF
  brake_either    per sleeve: a sleeve under its own average is replaced by IEF, so a split market runs 50/50 or half-sheltered
  brake_cash      `brake_both` with the brake in cash, isolating what the Treasury leg itself contributes
  blend_sq        the control, and the thing to beat
  spy_only / qqq_only   the two single-fund floors

Everything is priced by `shelter_long_record.multi_asset_path` through `rotation_search.score` — same fees, same turnover
convention, same shared calendar as the published round-75 table, so the two tables can be read against each other. A month
is scored only when both sleeves' averages exist; otherwise the rule declines and the plan keeps its prior position rather
than guessing.
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
import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

YEARS = 10
TILT = ("SPY", "QQQ")
CONTROL = "blend_sq"
RULES = ("brake_both", "brake_half", "brake_either", "brake_cash", "blend_sq", "spy_only", "qqq_only")
BRAKES = ("brake_both", "brake_half", "brake_either", "brake_cash")


def weights_from_marks(series: dict, dates: list, mark: dict) -> dict:
    """Daily weights per symbol from a monthly mark of weight dicts, with the lag taken from `carry`, not restated."""

    out = {}
    for sym in sorted(series):
        out[sym] = sl.carry({k: float(v.get(sym, 0.0)) for k, v in mark.items()}, dates)
    return out


def brake_mark(above_start: dict, above_end: dict, rule: str, conv: str) -> dict:
    """`above_start` / `above_end` are dicts of sleeve -> that sleeve's monthly MA200 signal, both sleeves required."""
    """Month -> target weights, from the two sleeves' own averages read on the prior month's signal day.

    A month is scored only when both sleeves can answer; a missing key means the plan holds what it already holds, which is
    the behaviour rounds 45, 71, 73 and 75 all demanded of a rule that does not know something.
    """

    sig_spy = {"start": above_start, "end": above_end}[conv]["SPY"]
    sig_qqq = {"start": above_start, "end": above_end}[conv]["QQQ"]
    mark = {}
    for key, spy_up in sorted(sig_spy.items()):
        qqq_up = sig_qqq.get(key)
        if qqq_up is None:
            continue
        both_up = spy_up == 1.0 and qqq_up == 1.0
        both_down = spy_up == 0.0 and qqq_up == 0.0
        if rule == "blend_sq":
            mark[key] = {"SPY": 0.5, "QQQ": 0.5}
        elif rule == "spy_only":
            mark[key] = {"SPY": 1.0}
        elif rule == "qqq_only":
            mark[key] = {"QQQ": 1.0}
        elif rule == "brake_both":
            mark[key] = {rse.SHELTER: 1.0} if both_down else {"SPY": 0.5, "QQQ": 0.5}
        elif rule == "brake_cash":
            mark[key] = {} if both_down else {"SPY": 0.5, "QQQ": 0.5}
        elif rule == "brake_half":
            mark[key] = ({"SPY": 0.25, "QQQ": 0.25, rse.SHELTER: 0.5} if both_down
                         else {"SPY": 0.5, "QQQ": 0.5})
        elif rule == "brake_either":
            if both_up:
                mark[key] = {"SPY": 0.5, "QQQ": 0.5}
            elif both_down:
                mark[key] = {rse.SHELTER: 1.0}
            elif spy_up == 1.0:
                mark[key] = {"SPY": 0.5, rse.SHELTER: 0.5}
            else:
                mark[key] = {"QQQ": 0.5, rse.SHELTER: 0.5}
    return mark


def grid(capital: float, years: int) -> dict:
    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    dates = rse.shared_calendar(data)
    series = {s: sl.legs(data, s) for s in rse.RISK + (rse.SHELTER,)}
    recent = max(sw.common_start(data), dates[0])
    # One signal per sleeve per convention, from the same function every published number in this repository uses.
    sig = {c: {s: sl.month_signal(sorted(sl.legs(data, s)), sl.legs(data, s), c)
               for s in TILT} for c in ("start", "end")}
    out = {"since": dates[0], "recent": recent, "fees": {s: rse.fee(s) for s in ("SPY", "QQQ", rse.SHELTER)},
           "rows": []}
    bench = {}
    for conv in ("start", "end"):
        for window, since in (("long", dates[0]), ("recent", recent)):
            use = [d for d in dates if d >= since]
            for who in (CONTROL, "qqq_only"):
                mk = brake_mark(sig[conv], sig[conv], who, conv)
                bench[(conv, window, who)] = rse.score(series, use, weights_from_marks(series, use, mk), capital, years)
    for rule in RULES:
        row = {"rule": rule, "cells": {}}
        for conv in ("start", "end"):
            for window, since in (("long", dates[0]), ("recent", recent)):
                use = [d for d in dates if d >= since]
                mk = brake_mark(sig[conv], sig[conv], rule, conv)
                cell = rse.score(series, use, weights_from_marks(series, use, mk), capital, years)
                b, q = bench[(conv, window, CONTROL)], bench[(conv, window, "qqq_only")]
                cell["vs_control"] = cell["safe"] - b["safe"]
                cell["vs_qqq"] = cell["safe"] - q["safe"]
                cell["dp_fail"] = cell["p_fail"] - b["p_fail"]
                cell["window"], cell["conv"] = window, conv
                row["cells"][(conv, window)] = cell
        s = row["cells"]
        c1 = (s[("start", "long")]["vs_control"] >= ct.BAR and s[("start", "recent")]["vs_control"] >= ct.BAR)
        c2 = (s[("end", "long")]["vs_control"] >= 0.0 and s[("end", "recent")]["vs_control"] >= 0.0)
        c3 = all(s[k]["dp_fail"] <= 1e-12 for k in (("start", "long"), ("start", "recent")))
        c4 = not (s[("start", "long")]["vs_qqq"] < 0 and s[("start", "recent")]["vs_qqq"] < 0)
        row["clauses"] = {"beats control": c1, "month-end holds": c2, "tail not worse": c3, "not just growth": c4}
        row["pass"] = bool(c1 and c2 and c3 and c4) and rule in BRAKES
        row["verdict"] = ("BEATS THE CONTROL on every clause" if row["pass"] else
                          "the control, priced as a row" if rule == CONTROL else
                          "a single fund, priced as a row" if rule in ("spy_only", "qqq_only") else
                          "beats the control nowhere" if s[("start", "recent")]["vs_control"] < ct.BAR else
                          "clears the bar at month-start and not at month-end" if not c2 else
                          "raises the failure probability, so it is not a brake" if not c3 else
                          "loses to plain QQQ on both windows")
        out["rows"].append(row)
    return out


def report(o: dict) -> None:
    print(f"  tilt + brake · one calendar from {o['since']} · long and recent ({o['recent']}) windows · the comparator is the")
    print(f"  static 50/50 blend itself, not the index · pass = beats the blend by ${ct.BAR:.0f}/mo on both windows and holds")
    print(f"  at month-end, does not raise P(fail), and is not beaten by plain QQQ twice · fees SPY {o['fees']['SPY']:.2%}")
    print(f"  QQQ {o['fees']['QQQ']:.2%} (posted), IEF {o['fees'][rse.SHELTER]:.2%} FLAT — not posted\n")
    print(f"  {'rule':13}{'Δ vs blend long':>17}{'Δ vs blend recent':>19}{'recent end':>12}{'Δ vs QQQ recent':>17}"
          f"{'P(fail)':>9}{'ΔP(fail)':>10}{'duty':>7}{'switches':>10}  verdict")
    print("  " + "-" * 130)
    for r in o["rows"]:
        s = r["cells"]
        print(f"  {r['rule']:13}{s[('start','long')]['vs_control']:>+17.2f}{s[('start','recent')]['vs_control']:>+19.2f}"
              f"{s[('end','recent')]['vs_control']:>+12.2f}{s[('start','recent')]['vs_qqq']:>+17.2f}"
              f"{s[('start','recent')]['p_fail']:>9.1%}{s[('start','recent')]['dp_fail']:>+10.1%}"
              f"{s[('start','recent')]['duty']:>7.1%}{s[('start','recent')]['switches']:>10}  {r['verdict']}")
    win = [r["rule"] for r in o["rows"] if r["pass"]]
    print(f"\n  {len(win)} of {len([r for r in o['rows'] if r['rule'] in BRAKES])} brake variants beat the control on every"
          " clause" + (f": {', '.join(win)}" if win else "."))
    print("  A brake that beats the blend on the long record and not the recent one is insurance, and round 73 already priced")
    print("  insurance. The clause that decides this page is the first one: the amendment has to pay for itself on the window")
    print("  the objective cares about, against the row that asks nothing of anyone.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=YEARS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    o = grid(args.capital, args.years)
    if args.json:
        print(json.dumps({"since": str(o["since"]), "recent": str(o["recent"]), "fees": o["fees"],
                          "rows": [{**{f"{c}_{w}": {k: (str(v) if isinstance(v, dt.date) else v)
                                                    for k, v in cell.items()}
                                        for (c, w), cell in r["cells"].items()},
                                    "rule": r["rule"], "pass": r["pass"], "verdict": r["verdict"],
                                    "clauses": r["clauses"]} for r in o["rows"]]}, indent=2, sort_keys=True))
    else:
        report(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
