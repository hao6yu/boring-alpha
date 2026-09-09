"""Eight monthly rules, priced once each, on the window that broke the last one. Pre-registered before the first run.

Run: .venv/bin/python tools/rule_search.py [--capital 100000] [--conv start] [--json]

Round 73 left a binding constraint, and it is not "find a better shelter". On the window every fund can be scored on —
2011-06-24 onward — the MA200/IEF construction loses to holding the fund by about $159 a month per $100,000, while on the
long record from 2002 it wins by about $130. Whatever is worth running has to clear **both**, and the recent window is the
hard one, because there the plain fund never failed a single ten-year window and so pays out no insurance.

This file is the search, written down before it was run, because a grid searched after the returns have been read reports
the winner of a lottery. The rules were chosen to attack the specific way MA200 loses money on the recent record — it
stands aside during rallies and pays the shelter's fee — and not because any of them is expected to win:

  ma200         the incumbent, re-priced as one row among many rather than as a given
  ma100, ma50   faster averages, which re-enter sooner and pay for it in whipsaws
  ma200_band    hysteresis: leave only 2% below the average, re-enter only 2% above it — fewer switches, later exits
  ma200_slope   stay in while the average itself is rising, even under it — the repair for V-shaped recoveries
  mom12         hold while the trailing 12-month return is positive
  mom_12_1      the same, skipping the most recent month (the classic momentum composite, not a new idea)
  voltarget     exposure = min(1, 10% / annualised 20-day volatility), stepped to half-units, no leverage
  dd_stop       hold unless the price is 15% below its trailing 12-month peak

**The pass rule, fixed now:** a row passes if it beats the same fund unlevered by at least round 60's $25/mo bar on the
long record *and* on the recent window, at month-start readings, and does not go negative on either at month-end readings.
One window passing is a rule fitted to a decade. Anything that passes is a candidate to paper-trade, not a promotion:
eight rules were tried, the best of eight is optimistic by construction, and the spread of the family is printed beside the
winner so the size of the mining is visible.

Everything is priced by `shelter_long_record.two_asset_path`, which already charges `abs(Δw) × 2 bps` on the day the
weight moves and the shelter's expense ratio for every day it is held — so a chatty rule is charged for being chatty, and a
rule that hides in Treasuries through a bull market is charged for that too.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import correction_table as ct                                # noqa: E402
import monthly_income_race as mir                            # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import trend_cost_test as tc                                 # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

SHELTER = "IEF"
SHELTER_FEE = max(sl.ER_GRID)                               # the flat fee the archive carries for an unposted fund
SLEEVE = "SPY"
YEARS = 10
P_MAX = 0.05
BAND = 0.02
VOL_TARGET = 0.10
DD_LIMIT = 0.15


def closes(spy: dict, dates: list) -> list:
    return [spy[d][0] for d in dates]


def reading_days(dates: list, conv: str) -> list:
    """The trading day each month's decision is taken on: its first (`start`) or last (`end`) session."""

    out = []
    for i, d in enumerate(dates):
        prv = dates[i - 1] if i else None
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        edge = ((prv is None or (prv.year, prv.month) != (d.year, d.month)) if conv == "start"
                else (nxt is None or (nxt.year, nxt.month) != (d.year, d.month)))
        if edge:
            out.append(i)
    return out


def sma(closes: list, n: int, i: int):
    return tc.sma(closes, n, i)


def ret(closes: list, back: int, i: int):
    """Trailing return over `back` sessions, ending at i — readable on the evening of day i and no sooner."""

    if i - back < 0:
        return None
    return closes[i] / closes[i - back] - 1.0


def real_vol(closes: list, n: int, i: int):
    if i - n < 1:
        return None
    r = [closes[k] / closes[k - 1] - 1.0 for k in range(i - n + 1, i + 1)]
    return statistics.pstdev(r) * (tc.DAYS ** 0.5)


def drawdown(closes: list, back: int, i: int):
    lo = max(0, i - back)
    peak = max(closes[lo:i + 1])
    return closes[i] / peak - 1.0


def marks_for(rule: str, spy: dict, dates: list, conv: str) -> dict:
    """Monthly marks keyed (year, month), each decided on that month's reading day from data ending that day.

    Every rule omits its key where it cannot answer. That is not a stylistic choice: `carry` holds the previous month's
    decision, and a rule that reported an answer it did not have would be the same defect that opened a sheltered record
    in round 73 and reported a decision in round 45.
    """

    c = closes(spy, dates)
    mark, state = {}, 1.0
    for i in reading_days(dates, conv):
        key = (dates[i].year, dates[i].month)
        m200 = sma(c, 200, i)
        if rule.startswith("ma") and m200 is None:
            continue
        if rule == "mom12" or rule == "mom_12_1":
            back = 252 if rule == "mom12" else 231
            r = ret(c, back, i)
            if r is None:
                continue
            mark[key] = 1.0 if r > 0.0 else 0.0
        elif rule == "voltarget":
            v = real_vol(c, 20, i)
            if v is None or v <= 0:
                continue
            want = min(1.0, VOL_TARGET / v)
            mark[key] = round(want * 2) / 2.0
        elif rule == "dd_stop":
            if i < 252:
                continue
            mark[key] = 1.0 if drawdown(c, 252, i) > -DD_LIMIT else 0.0
        elif rule == "ma200_band":
            if c[i] > m200 * (1.0 + BAND):
                state = 1.0
            elif c[i] < m200 * (1.0 - BAND):
                state = 0.0
            mark[key] = state
        elif rule == "ma200_slope":
            then = sma(c, 200, i - 63) if i >= 63 else None
            rising = then is not None and m200 > then
            mark[key] = 1.0 if (c[i] > m200 or rising) else 0.0
        else:
            n = {"ma200": 200, "ma100": 100, "ma50": 50}[rule]
            m = sma(c, n, i) if rule != "ma200" else m200
            mark[key] = 1.0 if c[i] > m else 0.0
    return mark


RULES = ("ma200", "ma100", "ma50", "ma200_band", "ma200_slope", "mom12", "mom_12_1", "voltarget", "dd_stop")


def score(data: dict, spy: dict, shelter: dict, marks: dict, since: dt.date, conv: str, capital: float,
          years: int) -> dict:
    """A rule's marks, priced over the dates from `since`, against the same fund held unlevered over the same dates."""

    dates = [d for d in sorted(spy) if d >= since and d in shelter]
    w = sl.carry(marks, dates)
    er = wc.EXPENSE[SLEEVE]
    path = sl.two_asset_path(dates, spy, shelter, w, er, SHELTER_FEE)
    bench = sl.two_asset_path(dates, spy, None, [1.0] * len(dates), er, 0.0)
    monthly = mir.month_marks(dates, path)[1]
    index = mir.month_marks(dates, bench)[1]
    safe = mir.safe_amount(monthly, capital, years, P_MAX, floor=1.0)
    idx = mir.safe_amount(index, capital, years, P_MAX, floor=1.0)
    st = mir.plan_stats(monthly, capital, ct.PUBLISHED_PAYOUT, years, 0.0, 1.0)
    sb = mir.plan_stats(index, capital, ct.PUBLISHED_PAYOUT, years, 0.0, 1.0)
    switches = sum(1 for i in range(1, len(w)) if w[i] != w[i - 1])
    cap, _ = sl.capacity(monthly, index, capital, years)
    return {"safe": safe, "index": idx, "delta": safe - idx, "p_fail": st["p_fail"], "p_fail_index": sb["p_fail"],
            "cap": cap, "n": st["n"], "months": len(monthly), "since": dates[0], "duty": 1.0 - (sum(w) / len(w)),
            "switches": switches}


def grid(capital: float, years: int) -> list:
    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spy = sl.legs(data, SLEEVE)
    shelter = sl.legs(data, SHELTER)
    dates = sorted(spy)
    warm = dates[sl.WARMUP]
    windows = {"long": max(ct.SINCE, warm), "panel": max(ct.PANEL, warm), "recent": sw.common_start(data)}
    out = []
    for rule in RULES:
        row = {"rule": rule}
        for conv in ("start", "end"):
            mk = marks_for(rule, spy, dates, conv)
            for window, since in windows.items():
                s = score(data, spy, shelter, mk, since, conv, capital, years)
                s["window"], s["conv"] = window, conv
                row.setdefault(conv, {})[window] = s
        s = row["start"]
        clears = (s["long"]["delta"] >= ct.BAR and s["recent"]["delta"] >= ct.BAR
                  and row["end"]["long"]["delta"] > 0 and row["end"]["recent"]["delta"] > 0)
        row["pass"] = clears
        row["verdict"] = ("PASSES the pre-registered rule" if clears else
                          "fails the recent window" if s["recent"]["delta"] < ct.BAR else "fails the long record")
        out.append(row)
    return out


def report(rows: list, capital: float) -> None:
    print(f"  rule search · {SLEEVE} in {SHELTER} · {len(RULES)} rules, pre-registered · pass = beats the fund by"
          f" ${ct.BAR:.0f}/mo per ${capital:,.0f} on the long record AND the recent window, both readings\n")
    print(f"  {'rule':13}{'long $/mo':>11}{'Δ long':>10}{'recent $/mo':>13}{'Δ recent':>11}{'Δ recent(end)':>15}"
          f"{'duty':>7}{'switches':>10}{'P(fail)':>9}{'idx P(fail)':>13}  verdict")
    print("  " + "-" * 118)
    for r in rows:
        s, e = r["start"], r["end"]
        print(f"  {r['rule']:13}{s['long']['safe']:>11.2f}{s['long']['delta']:>+10.2f}{s['recent']['safe']:>13.2f}"
              f"{s['recent']['delta']:>+11.2f}{e['recent']['delta']:>+15.2f}{s['recent']['duty']:>7.1%}"
              f"{s['recent']['switches']:>10}{s['recent']['p_fail']:>9.1%}{s['recent']['p_fail_index']:>13.1%}"
              f"  {r['verdict']}")
    both = [r for r in rows if r["pass"]]
    rec = [r["start"]["recent"]["delta"] for r in rows]
    print(f"\n  {len(both)} of {len(rows)} rules clear the recent window. The family runs from {min(rec):+.2f} to"
          f" {max(rec):+.2f} on that window, a spread of {max(rec) - min(rec):+.2f} — which is the size of the mining this"
          f" table is, and the reason a winner is a candidate and not a promotion.")
    print(f"  The fund's own failure rate on the recent window is {rows[0]['start']['recent']['p_fail_index']:.1%}, so"
          f" every negative row here is insurance bought and never claimed, and any positive row is being paid for out of"
          f" return rather than out of safety. Round 73's law still holds: nothing in this family is free.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=YEARS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = grid(args.capital, args.years)
    if args.json:
        print(json.dumps(rows, default=str, indent=2, sort_keys=True))
    else:
        report(rows, args.capital)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
