"""At what withdrawal does risk have a price? The same six constructions, scored at payouts that bind.

Run: .venv/bin/python tools/binding_payout.py [--capital 100000] [--json]

Rounds 73 to 76 kept losing to the same clause. A brake is supposed to buy the left tail, and every time the tail was
measured the answer was 0.0% — at the published $435.47/mo per $100,000, nothing holding growth over ten years fails, so the
repository's chosen measure of risk could not see the thing risk reductions are for, while its measure of capacity priced
their cost to the cent. That asymmetry is not a verdict on the brakes. It is a verdict on asking a question at a level where
it has no answer.

So this file asks the same question at withdrawal levels that do bind, expressed as multiples of the static 50/50 blend's own
capacity — because after round 75 the blend, not the index, is the thing to beat:

  0.90x  1.00x  1.10x  1.25x  1.50x  2.00x  of what the control can safely withdraw

**The decision rule, fixed before the first run:** risk has a measurable price, and the brake earns the right to be
discussed, if some construction's failure probability is strictly below the control's at the same withdrawal **at a multiple
no larger than 1.25x** on the long record. Above 1.25x a plan is being asked to withdraw more than its own capacity, and a
low failure probability there is a fact about arithmetic rather than about a strategy — which is why every row also prints
its own capacity as a multiple of the control's, so the reader can see which cells are inside the envelope and which are not.

Everything else is the machinery the last two rounds published: the same shared calendar, the same marks from
`tilt_brake.brake_mark` and `rotation_search.held_for` (no rule is re-typed here), the same `multi_asset_path` costs, the same
payout model.
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

import rotation_search as rse                                # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import sleeve_table as sw                                    # noqa: E402
import tilt_brake as tb                                      # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

YEARS = 10
CONTROL = "blend_sq"
MULTIPLES = (0.90, 1.00, 1.10, 1.25, 1.50, 2.00)
MAX_CLAIMED = 1.25
CONSTRUCTIONS = ("spy_only", "qqq_only", "blend_sq", "brake_both", "brake_either", "dm12_sq")


def marks_for(name: str, sig: dict, series: dict, dates: list) -> dict:
    """Target weights per month, from the same functions that priced rounds 75 and 76."""

    if name in tb.RULES or name in ("spy_only", "qqq_only"):
        return tb.brake_mark(sig, sig, name, "start")
    if name == "dm12_sq":
        want = rse.held_for("dm12_sq", series, dates, "start")
        return {k: ({rse.SHELTER: 1.0} if v == rse.SHELTER else ({"SPY": 0.5, "QQQ": 0.5} if v == "SPY+QQQ" else {v: 1.0}))
                for k, v in want.items()}
    raise KeyError(name)


def grid(capital: float, years: int) -> dict:
    """Two passes, because the ruler is one of the things being measured: the multiples are expressed against the control's
    capacity, which is only known after it has been priced, so the control is priced once to set the scale and again to be
    scored on it. `rotation_search.score` takes the payout levels as an argument rather than this file recomputing anything,
    so the same function that priced rounds 75 and 76 is still the only thing that prices a plan."""

    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    dates = rse.shared_calendar(data)
    series = {s: sl.legs(data, s) for s in rse.RISK + (rse.SHELTER,)}
    recent = max(sw.common_start(data), dates[0])
    sig = {c: {s: sl.month_signal(sorted(sl.legs(data, s)), sl.legs(data, s), c)
               for s in tb.TILT} for c in ("start", "end")}["start"]
    out = {"since": dates[0], "recent": recent, "rows": [], "payouts": {}}
    base, cells = {}, {}
    for window, since in (("long", dates[0]), ("recent", recent)):
        use = [d for d in dates if d >= since]
        w_ctl = tb.weights_from_marks(series, use, marks_for(CONTROL, sig, series, use))
        base[window] = rse.score(series, use, w_ctl, capital, years)["safe"]
        targets = tuple(round(m * base[window], 2) for m in MULTIPLES)
        out["payouts"][window] = dict(zip(MULTIPLES, targets))
        for name in CONSTRUCTIONS:
            w = tb.weights_from_marks(series, use, marks_for(name, sig, series, use))
            c = rse.score(series, use, w, capital, years, targets=targets)
            c["p_fails"] = dict(zip(MULTIPLES, (c["p_fails"][t] for t in targets)))
            cells[(name, window)] = c
    for name in CONSTRUCTIONS:
        row = {"name": name, "windows": {}}
        for window in ("long", "recent"):
            c = cells[(name, window)]
            ctl = cells[(CONTROL, window)]
            row["windows"][window] = {
                "multiple": c["safe"] / base[window], "safe": c["safe"], "n": c["n"], "switches": c["switches"],
                "duty": c["duty"], "p_fails": dict(c["p_fails"]),
                "counts": {m: int(round(c["p_fails"][m] * c["n"])) for m in MULTIPLES},
                "ctl_counts": {m: int(round(ctl["p_fails"][m] * ctl["n"])) for m in MULTIPLES},
                "inside": {m: c["safe"] >= m * base[window] - 1e-9 for m in MULTIPLES},
                "beats_control": {m: c["p_fails"][m] < ctl["p_fails"][m] for m in MULTIPLES}}
        row["claim"] = bool(any(row["windows"]["long"]["beats_control"][m] for m in (1.10, 1.25)))
        row["verdict"] = ("fails less than the control where the claim is allowed" if row["claim"] and name != CONTROL else
                          "the control itself" if name == CONTROL else
                          "never fails less than the control at any tested payout")
        out["rows"].append(row)
    out["base"] = base
    return out


def report(o: dict) -> None:
    print("  binding payout · one calendar from %s · month-start readings · failure probability at a withdrawal expressed" % o["since"])
    print("  as a multiple of the static 50/50 blend's own capacity ($%.2f/mo long, $%.2f/mo recent, per $100,000) · the"
          % (o["base"]["long"], o["base"]["recent"]))
    print("  decision rule allows a claim only at or below %.2fx, because past a plan's own capacity the number describes" % MAX_CLAIMED)
    print("  the withdrawal, not the strategy\n")
    for window in ("long", "recent"):
        print("  %s record" % window)
        print("  %s%s  %s  %s" % ("construction".ljust(13), "".join("%8.2fx" % m for m in MULTIPLES),
                                 "own cap".rjust(9), "beats control · outside own capacity"))
        print("  " + "-" * (27 + 8 * len(MULTIPLES) + 40))
        for r in o["rows"]:
            w = r["windows"][window]
            marks = "".join("%9.1f%%" % (100 * w["p_fails"][m]) for m in MULTIPLES)
            beat = [f"{m:g}" for m in MULTIPLES if w["beats_control"][m]]
            out = [f"{m:g}" for m in MULTIPLES if not w["inside"][m]]
            print(f"  {r['name']:13}{marks}{w['multiple']:>9.3f}x  beats "
                  + ("-" if not beat else ",".join(beat))
                  + "  outside " + ("-" if not out else ",".join(out))
                  + f"   at 1.10x: {w['counts'][1.10]} of {w['n']} windows fail, control "
                  + f"{w['ctl_counts'][1.10]}")
        print("")
    claim = [r["name"] for r in o["rows"] if r["claim"]]
    print(f"  {'Nothing' if not claim else ', '.join(claim)} fails less often than the control at a withdrawal the decision")
    print("  rule lets anyone claim (≤ 1.25x). `outside` lists the columns above that construction's own capacity: a cell that")
    print("  wins out there is winning at a withdrawal the plan cannot fund, which is arithmetic, not a strategy. The 2.00x")
    print("  column is printed so a reader can watch the numbers stop meaning anything. The counts beside each row are raw")
    print("  ten-year windows out of the sample; they overlap each other, so no confidence interval is computed on them here.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--years", type=int, default=YEARS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    o = grid(args.capital, args.years)
    if args.json:
        print(json.dumps({"since": str(o["since"]), "recent": str(o["recent"]),
                          "base": {k: float(v) for k, v in o["base"].items()},
                          "rows": [{"name": r["name"], "claim": r["claim"], "verdict": r["verdict"],
                                    "windows": {w: {"multiple": v["multiple"], "safe": v["safe"], "n": v["n"],
                                                    "switches": v["switches"], "duty": v["duty"],
                                                    "p_fails": {str(k): float(x) for k, x in v["p_fails"].items()},
                                                    "counts": {str(k): x for k, x in v["counts"].items()},
                                                    "ctl_counts": {str(k): x for k, x in v["ctl_counts"].items()},
                                                    "inside": {str(k): x for k, x in v["inside"].items()},
                                                    "beats_control": {str(k): x for k, x in v["beats_control"].items()}}
                                                for w, v in r["windows"].items()}} for r in o["rows"]]},
                         indent=2, sort_keys=True))
    else:
        report(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
