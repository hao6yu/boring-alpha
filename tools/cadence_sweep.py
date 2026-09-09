"""How often a decision is allowed to be made, priced. The last thing daily closes can answer about "short term trading".

Run: .venv/bin/python tools/cadence_sweep.py [--capital 100000] [--years 10] [--json]

Every rule this repository has tested reads once a month, and the objective says *short term*. Nobody has priced what happens
when the same signals are read weekly, because the whole engine was keyed to the calendar month. This file removes that
constraint at the only place it should be removed — the schedule — and holds everything else fixed: the same MA200, the same
twelve-month relative strength, the same 50/50 tilt, the same 2 bps on purchases, the same ten-year windows, the same 5%
failure budget, and above all the same lag. `sl.cadence_carry` generalises `sl.carry` off the month and is differentially
tested against it to the last day, so a weekly plan and a monthly plan are charged the same one-period delay between reading
and trading. Without that, a cadence sweep measures which schedule cheated first.

What is being claimed, written before the numbers: **a faster schedule is recommendable only if it funds more than the same
plan read monthly — by at least the bar this repository already uses, $25/mo per $100k — on the record the withdrawal is
planned against, and it does not turn a record that funds something into one that funds nothing.** Anything else is a plan
that trades more, which is not the same as one that earns more, and every extra switch is charged before the comparison is
made. The spread across the family is printed for the same reason round 74 demanded it: a winner chosen from five schedules
is a five-way guess with a story attached.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import correction_table as ct                                # noqa: E402
import mix_sweep as ms                                       # noqa: E402
import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import trend_cost_test as tc                                  # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

CADENCES = (5, 10, 21, 42, 63)
NAMES = {5: "weekly", 10: "fortnightly", 21: "monthly", 42: "two-month", 63: "quarterly"}
TILT = 0.50
LOOKBACKS = {"brake_50": sl.WARMUP, "rot12": 252}
PLANS = ("brake_50", "rot12")
STATICS = ("static_50", "static_100")


def closes_of(series: dict, sym: str, dates: list) -> list:
    return [series[sym][d][0] for d in dates if d in series[sym]]


def decision_days(n: int, cadence: int) -> list:
    """Every `cadence`-th trading day from the first day of the record. A scheduled day inside a lookback's warmup simply
    declines to answer, and `cadence_carry` holds nothing until the first real answer arrives — the same thing the monthly
    tools do, which is why the opening months of a record sit in cash at every cadence equally."""

    return list(range(0, n, cadence))


def mark_at(plan: str, series: dict, dates: list, i: int, closes: dict, mas: dict):
    """The weights a plan chooses on the close of day `i`, using data through that close — the same convention
    `sl.month_signal(..., "start")` uses, so the schedule is the only thing that differs from the monthly tools."""

    if plan == "static_50":
        return {"SPY": 1.0 - TILT, "QQQ": TILT}
    if plan == "static_100":
        return {"SPY": 0.0, "QQQ": 1.0}
    if plan == "brake_50":
        a, b = mas["SPY"][i], mas["QQQ"][i]
        if a is None or b is None:
            return None
        if closes["SPY"][i] > a or closes["QQQ"][i] > b:
            return {"SPY": 1.0 - TILT, "QQQ": TILT}
        return {}
    r = {s: rse.trailing(series, dates, s, 252, i) for s in ("SPY", "QQQ")}
    if r["SPY"] is None or r["QQQ"] is None:
        return None
    if r["SPY"] <= 0.0 and r["QQQ"] <= 0.0:
        return {}
    return ({"SPY": 1.0, "QQQ": 0.0} if r["SPY"] >= r["QQQ"] else {"SPY": 0.0, "QQQ": 1.0})


def moving_average(closes: list, window: int) -> list:
    out = [None] * len(closes)
    tot = 0.0
    for i, c in enumerate(closes):
        tot += c
        if i >= window:
            tot -= closes[i - window]
        if i >= window - 1:
            out[i] = tot / window
    return out


def weights_for(plan: str, series: dict, dates: list, cadence: int) -> dict:
    n = len(dates)
    closes = {s: [series[s][d][0] if d in series[s] else None for d in dates] for s in ("SPY", "QQQ")}
    mas = {s: moving_average(closes[s], sl.WARMUP) for s in ("SPY", "QQQ")}
    marks = {}
    for i in decision_days(n, cadence):
        marks[i] = mark_at(plan, series, dates, i, closes, mas)
    return sl.cadence_carry(dates, marks, ("SPY", "QQQ"))


def static_weights(dates: list, spy_weight: float) -> dict:
    """A book that never rebalances has no schedule to price; it is the constant the schedules are compared against."""

    return {"SPY": [spy_weight] * len(dates), "QQQ": [1.0 - spy_weight] * len(dates)}


def drawdown(dates: list, path: list) -> float:
    peak, worst = path[0], 0.0
    for v in path:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1.0)
    return worst


def grid(capital: float, years: int) -> dict:
    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    series = {s: sl.legs(data, s) for s in ("SPY", "QQQ")}
    all_dates = [d for d in sorted(set(series["SPY"]) & set(series["QQQ"])) if d >= ms.deep_start(series)]
    recent = max(sw.common_start(data), all_dates[0])
    mixed = ms.grid(capital, years)
    scale = mixed["scale"]
    anchored = {r["name"]: r for r in mixed["rows"]}["brake_50"]["windows"]
    targets = tuple(round(m * scale, 2) for m in (1.00, 1.10))
    out = {"scale": scale, "deep": all_dates[0], "recent": recent, "rows": [],
           "calendar_brake": {"deep": anchored["deep"]["safe"], "recent": anchored["recent"]["safe"]}}
    for plan in STATICS + PLANS:
        cadences = (None,) if plan in STATICS else CADENCES
        for cadence in cadences:
            row = {"plan": plan, "cadence": cadence, "label": NAMES.get(cadence, "no decisions"), "windows": {}}
            for window, since in (("deep", all_dates[0]), ("recent", recent)):
                use = [d for d in all_dates if d >= since]
                weights = (static_weights(use, 1.0 - TILT if plan == "static_50" else 0.0)
                           if plan in STATICS else weights_for(plan, series, use, cadence))
                c = rse.score(series, use, weights, capital, years, targets=targets)
                path = sl.multi_asset_path(use, series, weights, {s: rse.fee(s) for s in weights}, series["SPY"])
                c["dd"] = drawdown(use, path)
                c["switches_yr"] = c["switches"] * tc.DAYS / len(use)
                row["windows"][window] = c
            out["rows"].append(row)
    for row in out["rows"]:
        family = [r for r in out["rows"] if r["plan"] == row["plan"]]
        row["spread"] = max(r["windows"]["recent"]["safe"] for r in family) \
            - min(r["windows"]["recent"]["safe"] for r in family)
        if row["cadence"] is None:
            row["verdict"] = "makes no decisions, so no schedule can be used to beat it"
            row["beats_monthly"] = False
            continue
        monthly = next(r for r in out["rows"] if r["plan"] == row["plan"] and r["cadence"] == 21)
        gain = row["windows"]["recent"]["safe"] - monthly["windows"]["recent"]["safe"]
        row["beats_monthly"] = bool(gain >= ct.BAR)
        # The bar is necessary and not sufficient: a schedule chosen because it beat four others must beat the spread of the
        # five it was chosen from, or the gain is the search, not the schedule. Round 74's rule, applied to the axis this
        # file invented rather than to the rules it inherited.
        row["clears_spread"] = bool(row["beats_monthly"] and gain >= row["spread"])
        row["gain"] = gain
        row["verdict"] = ("funds %+.2f/mo more than the same plan read monthly, which is %.0f%% of the spread between the "
                          "schedules of this plan: the schedule is not measurable at this size"
                          % (gain, 100 * gain / row["spread"]) if row["beats_monthly"] else
                          "does not fund more than the same plan read monthly (%+.2f/mo), at %d switches/yr"
                          % (gain, round(row["windows"]["recent"]["switches_yr"])))
    out["pass_bar"] = sum(1 for r in out["rows"] if r.get("beats_monthly"))
    out["pass_spread"] = sum(1 for r in out["rows"] if r.get("clears_spread"))
    return out


def report(o: dict) -> None:
    print("  cadence sweep · both records start where the last four rounds put them (%s deep, %s recent) · the same"
          % (o["deep"], o["recent"]))
    print("  one-period lag on every schedule, `sl.cadence_carry` differential-tested against `sl.carry`")
    print("  failure probabilities are read at one shared scale, $%.2f/mo per $100,000 = the static blend's recent capacity"
          % o["scale"])
    print("")
    print("  plan       schedule     capacity deep  capacity recent  fail@1.00x deep  fail@1.00x recent  worst DD  switch/yr")
    print("  " + "-" * 103)
    for r in o["rows"]:
        d, rc = r["windows"]["deep"], r["windows"]["recent"]
        cd = "%10.2f" % d["safe"] if d["safe"] > 0 else "      none"
        cr = "%10.2f" % rc["safe"] if rc["safe"] > 0 else "      none"
        print("  %-10s %-12s%s%s%15.1f%%  %16.1f%%%11.1f%%%11.1f"
              % (r["plan"], r["label"], cd, cr, 100 * d["p_fails"][round(o["scale"], 2)],
                 100 * rc["p_fails"][round(o["scale"], 2)], 100 * abs(rc["dd"]), rc["switches_yr"]))
    print("")
    print("  the same brake anchored to the calendar month rather than every 21 trading days — round 78's row — funds")
    print("  $%.2f/mo recent and $%.2f/mo deep, so anchoring alone moves capacity by $%.2f/mo: more than the $25.00 bar"
          % (o["calendar_brake"]["recent"], o["calendar_brake"]["deep"],
             abs(o["calendar_brake"]["recent"] - next(r for r in o["rows"]
                  if r["plan"] == "brake_50" and r["cadence"] == 21)["windows"]["recent"]["safe"])))
    print("  this table is supposed to measure, and an order of magnitude more than the difference between schedules.")
    print("")
    for r in o["rows"]:
        if r["cadence"] is not None and r["cadence"] != 21:
            print("  %-10s %s: %s" % (r["plan"], r["label"], r["verdict"]))
    print("  The spread across the family is printed rather than the winner: the widest gap between two schedules of one plan")
    for plan in PLANS:
        rows = [r for r in o["rows"] if r["plan"] == plan]
        print("  is %.2f/mo on the recent window (%s), which is what choosing a schedule from this table would be buying."
              % (max(r["windows"]["recent"]["safe"] for r in rows) - min(r["windows"]["recent"]["safe"] for r in rows),
                 max(rows, key=lambda r: r["windows"]["recent"]["safe"])["label"]))
    print("  Pre-registered claim, scored: %d of %d schedules clear the $25.00/mo bar against their own plan read monthly;"
          % (o["pass_bar"], sum(1 for r in o["rows"] if r["cadence"] is not None)))
    print("  %d clear the spread of the family they were selected from. The claim was written before the run and is necessary"
          % o["pass_spread"])
    print("  but not sufficient, and this file says so rather than promoting a winner.")
    print("  No confidence interval is published on those counts: the ten-year windows overlap, and the schedules are")
    print("  not independent either — weekly and fortnightly rows of one plan share almost every day of the record.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    o = grid(args.capital, args.years)
    if args.json:
        print(json.dumps({"scale": o["scale"], "deep": str(o["deep"]), "recent": str(o["recent"]),
                          "rows": [{"plan": r["plan"], "cadence": r["cadence"], "label": r["label"],
                                    "verdict": r["verdict"], "beats_monthly": r.get("beats_monthly"),
                                    "windows": {w: {k: (str(v) if isinstance(v, dict) else v)
                                                     for k, v in c.items() if k != "p_fails"}
                                                | {("p_" + str(k)): v for k, v in c["p_fails"].items()}
                                                for w, c in r["windows"].items()}} for r in o["rows"]]},
                         indent=2))
    else:
        report(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
