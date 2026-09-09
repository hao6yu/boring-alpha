"""How much of the growth tilt's capacity is payment for a tail the last three rounds never saw?

Run: .venv/bin/python tools/mix_sweep.py [--capital 100000] [--json]

Round 77 found plain QQQ beating the static 50/50 blend on capacity and on failure probability, on both windows it tested, at
a posted 20 bps. It also recorded why that sentence cannot be trusted: the calendar every recent round has used begins
2005-09-06, set by the youngest leg of a five-asset pool plus a 200-day warmup, so the growth index's own collapse — 2000 to
2002, −82% — is in none of the windows measured. A tail that is never sampled cannot show up in a failure probability, and a
sweep that pays more capacity for a fund whose disaster is outside the sample is not a finding, it is a sampling artefact.

This file fixes the sample before asking the question. The two sleeves being compared are SPY and QQQ, and both can be scored
from **2000-01-06** — QQQ's first day plus the engine's own 200-day warmup — so the record used starts there, which makes it
the earliest date on which this family can be scored at all rather than a date chosen for its outcome (round 66: a start date
is a position, so it is set by the data's own limit and printed). It contains the dot-com unwind, 2008, 2009, 2020 and 2022.
The shared-calendar constraint that produced the 2005 start is gone because nothing here holds a shelter: the brake in this
grid parks in cash on the bill curve, which needs no price series, and that choice is stated in every row rather than hidden
— round 76 measured that a Treasury brake and a cash brake rank the other way round on the last fifteen years.

Seven pre-registered rows: five static mixes from all-SPY to all-QQQ in quarter steps, and the two braked versions of the 50/50
and 25/75 mixes (both sleeves under their own 200-day average ⇒ whole book to cash). `dm12_sq` is deliberately absent: it
shelters in Treasuries, whose warmup would push the start back to mid-2003 and cut off the very episode this grid exists to
test. Round 77 prices it.

**The claim, fixed before the first run:** a mix is recommendable only if it carries the lower failure probability at 1.00x of
the 50/50 control's capacity on the deep record *as well as* the higher capacity. If a mix buys capacity and sells failure
probability, the capacity is payment for the tail, and the row is labelled as that — which is the whole point of the exercise,
since that is what the 2005 calendar was structurally unable to say.
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
import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import tilt_brake as tb                                      # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

YEARS = 10
MULTIPLES = (0.90, 1.00, 1.10, 1.25, 1.50)
CONTROL = "mix_50"
MIXES = (("mix_00", 0.00, False), ("mix_25", 0.25, False), ("mix_50", 0.50, False), ("mix_75", 0.75, False),
         ("mix_100", 1.00, False), ("brake_50", 0.50, True), ("brake_75", 0.75, True))


def deep_start(series: dict) -> dt.date:
    """The earliest day this family can be scored: the later of the two sleeves' own warmup days. Not chosen for its outcome."""

    return max(sorted(series[s])[sl.WARMUP] for s in ("SPY", "QQQ"))


def drawdown(dates: list, path: list) -> float:
    """Worst peak-to-trough fall of the balance, reported because capacity and tail are the two halves of one question and
    only one of them fits in a `safe_amount`."""

    peak, worst = 1.0, 0.0
    for v in path:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1.0)
    return worst


def mark_for(w: float, brake: bool, sig: dict, months: list) -> dict:
    """Target weights per month. A braked row goes to cash — no shelter, no extra warmup, nothing to flatter."""

    out = {}
    for key in months:
        if brake:
            up_spy, up_qqq = sig["SPY"].get(key), sig["QQQ"].get(key)
            if up_spy is None or up_qqq is None:
                continue
            if up_spy == 0.0 and up_qqq == 0.0:
                out[key] = {}
                continue
        out[key] = {"SPY": 1.0 - w, "QQQ": w}
    return out


def grid(capital: float, years: int) -> dict:
    """Two passes, and one deliberate change of scale from round 77.

    The multiples used there were expressed against the control's capacity *on each window*, which works until a window where
    the control has no capacity at all — and on the deep record, the 50/50 blend cannot meet a 5% failure budget at any
    payout, so `safe_amount` correctly returns zero and every ratio against it is undefined. Here the dollar levels are set
    once, from the control's capacity on the recent window, and used unchanged on both records, so the two tables are the same
    withdrawal and the only thing that moves is the history it is asked to survive. A row's own capacity is still printed,
    including when it is no capacity at all.
    """

    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    series = {s: sl.legs(data, s) for s in ("SPY", "QQQ")}
    sig = {s: sl.month_signal(sorted(series[s]), series[s], "start") for s in ("SPY", "QQQ")}
    dates = [d for d in sorted(set(series["SPY"]) & set(series["QQQ"])) if d >= deep_start(series)]
    months = sorted({(d.year, d.month) for d in dates})
    recent = max(sw.common_start(data), dates[0])
    out = {"deep": dates[0], "recent": recent, "rows": []}
    ctl_recent = rse.score(series, [d for d in dates if d >= recent],
                           tb.weights_from_marks(series, [d for d in dates if d >= recent],
                                                 mark_for(0.50, False, sig, months)), capital, years)["safe"]
    if ctl_recent <= 0.0:
        raise SystemExit("the control has no capacity on the recent window either; the scale for this grid does not exist")
    scale = round(ctl_recent, 2)
    targets = tuple(round(m * scale, 2) for m in MULTIPLES)
    out["scale"] = scale
    out["payouts"] = dict(zip(MULTIPLES, targets))
    cells = {}
    for name, w, brake in MIXES:
        weights_by_window = {}
        for window, since in (("deep", dates[0]), ("recent", recent)):
            use = [d for d in dates if d >= since]
            weights = tb.weights_from_marks(series, use, mark_for(w, brake, sig, months))
            weights_by_window[window] = (use, weights)
            c = rse.score(series, use, weights, capital, years, targets=targets)
            c["dd"] = drawdown(use, sl.multi_asset_path(use, series, weights, {s: rse.fee(s) for s in weights},
                                                        series["SPY"]))
            c["floor_fail"] = mir.plan_stats(mir.month_marks(use, sl.multi_asset_path(
                use, series, weights, {s: rse.fee(s) for s in weights}, series["SPY"]))[1],
                capital, 1.0, years, 0.0, 1.0)["p_fail"]
            c["p_fails"] = dict(zip(MULTIPLES, (c["p_fails"][t] for t in targets)))
            cells[(name, window)] = c
    for name, w, brake in MIXES:
        row = {"name": name, "qqq": w, "brake": brake, "windows": {}}
        for window in ("deep", "recent"):
            c, ctl = cells[(name, window)], cells[(CONTROL, window)]
            row["windows"][window] = {
                "safe": c["safe"], "capacity_meets_budget": c["safe"] > 0.0, "floor_fail": c["floor_fail"],
                "dd": c["dd"], "duty": c["duty"], "switches": c["switches"], "n": c["n"], "p_fails": dict(c["p_fails"]),
                "counts": {m: int(round(c["p_fails"][m] * c["n"])) for m in MULTIPLES},
                "ctl_counts": {m: int(round(ctl["p_fails"][m] * ctl["n"])) for m in MULTIPLES}}
        d = row["windows"]["deep"]
        ctl_deep = cells[(CONTROL, "deep")]
        row["worse_tail"] = bool(d["p_fails"][1.00] > ctl_deep["p_fails"][1.00])
        row["safer_tail"] = bool(d["p_fails"][1.00] < ctl_deep["p_fails"][1.00])
        row["recommendable"] = bool(d["capacity_meets_budget"] and d["safe"] >= ctl_deep["safe"] + ct.BAR
                                    and not row["worse_tail"])
        cap = ("$%.2f" % d["safe"]) if d["capacity_meets_budget"] else "none"
        ctl_cap = ("$%.2f" % ctl_deep["safe"]) if ctl_deep["safe"] > 0 else "none"
        row["verdict"] = ("%s, fails %d/%d at 1.00x (control %d/%d), budget at $1/mo %.1f%% (control %.1f%%), worst drawdown"
                          " %.1f%%" % (cap, d["counts"][1.00], d["n"], d["ctl_counts"][1.00], d["n"],
                                       100 * d["floor_fail"], 100 * ctl_deep["floor_fail"], 100 * d["dd"]))
        out["rows"].append(row)
    return out


def _monotone(rows: list) -> bool:
    p = [(r["qqq"], r["windows"]["deep"]["floor_fail"]) for r in sorted(rows, key=lambda r: r["qqq"])]
    return all(p[i][1] <= p[i + 1][1] + 1e-12 for i in range(len(p) - 1))


def report(o: dict) -> None:
    print("  mix sweep · record from %s (QQQ warm-up, the earliest this family can be scored, not a date chosen for its"
          % o["deep"])
    print("  outcome) · brake parks in CASH on the bill curve, so no shelter's warm-up shortens the tail · failure")
    print("  probability at multiples of one shared dollar scale — the 50/50 control's own capacity on the recent window,")
    print("  $%.2f/mo per $100,000, the same withdrawal in both tables so only the history moves. A row's `capacity` is its"
          % o["scale"])
    print("  own maximum payout meeting a 5%% failure budget; `none` means no payout does, at any level.\n")
    for window in ("deep", "recent"):
        print("  %s record" % window)
        print("  %-9s%5s%6s%10s%9s%s%11s%9s%8s" % ("row", "QQQ", "brake", "capacity", "floor DD?",
                                                   "".join("%8.2fx" % m for m in MULTIPLES), "worst DD", "budget@1$", ""))
        print("  " + "-" * (35 + 8 * len(MULTIPLES) + 28))
        for r in o["rows"]:
            w = r["windows"][window]
            marks = "".join("%9.1f%%" % (100 * w["p_fails"][m]) for m in MULTIPLES)
            cap = "%10.2f" % w["safe"] if w["capacity_meets_budget"] else "%10s" % "none"
            print("  %-9s%4.0f%%%6s%s%s%s%11.1f%%%8.1f%%"
                  % (r["name"], 100 * r["qqq"], "yes" if r["brake"] else "-", cap, marks, "", 100 * w["dd"],
                     100 * w["floor_fail"]))
        print("")
    deep = [r for r in o["rows"] if r["windows"]["deep"]["capacity_meets_budget"]]
    static = [r for r in o["rows"] if not r["brake"]]
    print("  deep record, in words, computed from the cells above:")
    funded = len([r for r in static if r["windows"]["deep"]["capacity_meets_budget"]])
    print("    static mixes whose capacity meets the 5%% budget at any payout: %d of %d. On a record that starts where this"
          % (funded, len(static)))
    print("    family can start at all, the budget is unreachable: even a $1/mo withdrawal fails on %.1f%% of windows at"
          % (100 * min(r["windows"]["deep"]["floor_fail"] for r in static)))
    print("    best, and the failure rate at $1/mo %s with the QQQ weight (%.1f%% to %.1f%%)."
          % ("rises monotonically" if _monotone(static) else "does not rise monotonically",
             100 * min(r["windows"]["deep"]["floor_fail"] for r in static),
             100 * max(r["windows"]["deep"]["floor_fail"] for r in static)))
    for r in [x for x in o["rows"] if x["brake"]]:
        d = r["windows"]["deep"]
        print("    %s is one of %d rows on this page that fund the record at all: $%.2f/mo, %.2fx of the scale priced here,"
              " worst drawdown %.1f%%"
              % (r["name"], len(deep), d["safe"], d["safe"] / o["scale"], 100 * d["dd"]))
    print("  No confidence interval is published on those counts: the ten-year windows overlap, and 201 overlapping windows")
    print("  are not 201 trials. The `worst DD` column is the balance's own peak-to-trough fall, so capacity and the thing")
    print("  that produces it are printed on the same line.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=YEARS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    o = grid(args.capital, args.years)
    if args.json:
        def flat(d):
            return {str(k): v for k, v in d.items()}

        print(json.dumps({"deep": str(o["deep"]), "recent": str(o["recent"]),
                          "scale": o["scale"], "payouts": flat(o["payouts"]),
                          "rows": [{"name": r["name"], "qqq": r["qqq"], "brake": r["brake"], "verdict": r["verdict"],
                                    "worse_tail": r["worse_tail"], "safer_tail": r["safer_tail"],
                                    "recommendable": r["recommendable"],
                                    "windows": {w: {**{k: v for k, v in val.items()
                                                       if k not in ("p_fails", "counts", "ctl_counts")},
                                                    "p_fails": flat(val["p_fails"]), "counts": flat(val["counts"]),
                                                    "ctl_counts": flat(val["ctl_counts"])}
                                                for w, val in r["windows"].items()}} for r in o["rows"]]},
                         indent=2, sort_keys=True))
    else:
        report(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
