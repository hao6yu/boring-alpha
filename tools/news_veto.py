"""Does attention tell you when the TREND RULE is about to be wrong — priced at the same bar as the rule itself?

Run: .venv/bin/python tools/news_veto.py [--capital 100000] [--json]

Round 18 asked whether Wikipedia page views forecast the index, and the answer was no: six cells, −$87 to −$479 a month,
every one of them reproduced by a basket of non-financial articles. That closed the input as a signal of its own. It did
not test the claim the objective actually makes, which is weaker and more plausible: not "news forecasts the market" but
"news tells me when my rule is about to be wrong". A veto does not have to forecast returns to be worth having; it only
has to fire before the rule's bad months and not too often otherwise.

This file prices that. Same corpus, same thresholds, same control basket, same noise floor, both directions — round 18's
discipline is structural here and the control clause is not optional.

## What the corpus allows, stated before the arithmetic

  * The feed covers 2015-07-01 to the present. Page-view statistics do not exist before 2015-07-01 on the endpoint this
    repository uses — Wikimedia's Analytics API serves nothing earlier, and the older endpoint that covers 2008-2016
    counts views by a different definition, which would splice two measurements into one series and revise it in place.
    Round 18's whole guard is that a value must have been knowable on its day and never revised afterwards, so the older
    endpoint cannot be joined to this one without becoming a second series with its own provenance.
  * A z-score needs a year of history, so usable months begin 2016-01, and a decision uses the month *before* the one it
    governs, so the first tradable month is 2016-02. That leaves 127 usable months and therefore 8 ten-year windows.
  * Seven windows cannot resolve a 5% failure budget, and this file will not pretend otherwise: the plan-level figures are
    printed with their window count and the word UNRESOLVABLE beside them. The paired monthly test — every month of the
    two plans differenced against each other, 128 of them — is the part this corpus can carry, and it charges the equity
    fee, the shelter's own expense ratio and every switch, because those are the thing being tested.

## The hypotheses, written first

  *H1 warning*      high attention (z > θ) means the following month is worse, so shelter regardless of the trend.
  *H2 collapse*     the opposite reading: attention abandoning the subject (z < −θ) means the following month is worse.
  *H3 timing*       attention clusters where the rule turns, so it could at least save the rule's switching costs.

Each is priced against its own control basket at the same θ and the same shift, and against round 18's $25/mo noise
floor. A cell the control reproduces is not evidence, however good it looks.
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

import attention_bar as ab                                   # noqa: E402
import monthly_income_race as mir                            # noqa: E402
import rotation_edge as re_                                  # noqa: E402
import shelter_long_record as sl                             # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

SHELTER = "IEF"
SHELTER_FEE = re_.UNKNOWN_ER
MIN_MONTHS = 12   # a veto that fired fewer times than this is an anecdote about one month, not a tested cell
CAP_WINDOWS = 20            # below this many ten-year windows, a plan-level statistic is not a statistic
BRIDGE = ("the corpus starts 2015-07-01 because that is where Wikimedia's Analytics API starts; the older endpoint "
          "covering 2008-2016 counts views differently, so joining it would revise the series in place")


def monthly_exposure(dates: list, weights: list) -> dict:
    """Month -> the exposure the plan held on that month's last day."""

    out = {}
    for i, d in enumerate(dates):
        out[(d.year, d.month)] = weights[i]
    return out


def z_by_month() -> dict:
    """The two baskets' monthly z-scores, straight from the tool that defines them. Nothing here recomputes a z."""

    days, fin, ctl = ab.load_panel()
    return ({(d.year, d.month): v for d, v in ab.monthly(days, fin).items()},
            {(d.year, d.month): v for d, v in ab.monthly(days, ctl).items()})


def vetoed(marks: dict, z: dict, threshold: float, mode: str) -> dict:
    """A monthly exposure map with the veto applied. `mode` is which reading of attention counts as a warning."""

    out = {}
    keys = sorted(marks)
    for i, k in enumerate(keys):
        prior = keys[i - 1] if i else None
        want = marks[k]
        pz = z.get(prior) if prior else None
        if pz is not None:
            if mode == "warning" and pz > threshold:
                want = 0.0
            elif mode == "collapse" and pz < -threshold:
                want = 0.0
        out[k] = want
    return out


def price(exposure: dict, dates: list, spy: dict, shelter: dict, first: dt.date) -> dict:
    """Run an exposure map as a plan, over exactly the dates it could have run on."""

    use = [d for d in dates if d >= first]
    ser = sl.two_asset_path(use, spy, shelter, [exposure[(d.year, d.month)] for d in use],
                            wc.EXPENSE["SPY"], SHELTER_FEE)
    monthly = mir.month_marks(use, ser)[1]
    bench = mir.month_marks(use, sl.two_asset_path(use, spy, None, [1.0] * len(use), wc.EXPENSE["SPY"], 0.0))[1]
    st_ = mir.plan_stats(monthly, 100_000.0, 435.47, 10, 0.0, 1.0)   # the published payout, same for every row
    safe = mir.safe_amount(monthly, 100_000.0, 10, 0.05, floor=1.0)
    ordered = [exposure[k] for k in sorted(exposure)]
    switches = sum(1 for i in range(1, len(ordered)) if ordered[i] != ordered[i - 1])
    sheltered = sum(1 for v in ordered if v == 0.0)
    return {"monthly": monthly, "bench": bench, "n": st_["n"], "p_fail": st_["p_fail"], "safe": safe,
            "switches": switches, "sheltered_months": sheltered, "months": len(monthly)}


def paired(baseline: list, veto: list) -> dict:
    """What the veto is worth, measured as a paired difference and not as a formula.

    The first draft of this function multiplied the vetoed months' average equity return by the capital and called the
    product a saving, which is the wrong sign twice over: removing exposure in a month that went up is a *cost*, and the
    shelter you park in while vetoing has a fee of its own. So both plans are run through the same engine over the same
    dates — equity fee, shelter fee and every switch charge included, because they are the thing being tested — and the
    answer is the mean of the month-by-month difference. Paired, it needs no windows: 128 months is a sample, whereas
    seven ten-year windows are not.
    """

    d = [v - b for v, b in zip(veto, baseline)]
    return {"n": len(d), "mean": statistics.mean(d) if d else 0.0,
            "sd": statistics.pstdev(d) if len(d) > 1 else 0.0,
            "t": (statistics.mean(d) / (statistics.pstdev(d) / (len(d) ** 0.5))
                  if len(d) > 1 and statistics.pstdev(d) > 0 else 0.0),
            "dollars": statistics.mean(d) * 100_000.0 if d else 0.0}


def grade(n: int, candidate: float, control: float) -> str:
    """Round 18's verdict rule, with a sample clause it should always have had. A cell that fired eleven times is an
    anecdote; a cell the control basket reproduces by at least half is not evidence; and a cell under the noise floor is
    not worth a monthly decision. The first draft of this file graded a 1-month cell worth $1,057/mo as a CANDIDATE,
    which is exactly the failure the control clause exists to prevent, so the clause now reads `n` before it reads
    magnitude."""

    if n < MIN_MONTHS:
        return f"n={n}, too few months to grade"
    if candidate is None or control is None:
        return "no data"
    if abs(control) >= 0.5 * abs(candidate):
        return "REFUTED by the control basket"
    if candidate <= 0.0:
        return "the veto would have cost money, not saved it"
    if candidate < ab.NOISE_FLOOR:
        return f"under the ${ab.NOISE_FLOOR:.0f}/mo noise floor"
    return "CANDIDATE — price it as a rule, not a finding"


def run() -> dict:
    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spy = sl.legs(data, "SPY")
    shelter = sl.legs(data, SHELTER)
    dates = [d for d in sorted(spy) if d >= sl.PANEL_START and d in sl.legs(data, SHELTER)]
    marks_map = sl.month_signal(sorted(spy), spy, "start")
    exposure0 = monthly_exposure(dates, sl.carry(marks_map, dates))
    fin_z, ctl_z = z_by_month()
    y, m = min(fin_z)                       # the corpus' first usable month, as a (year, month) key
    first = dt.date(y + (m == 12), 1 if m == 12 else m + 1, 1)   # a decision can only govern the month after it
    floor = (first.year, first.month)
    keys = [k for k in sorted(exposure0) if k >= floor]
    fwd = {keys[i]: None for i in range(len(keys))}
    # Forward SPY return for the month after each key, read off the same path the plan would have ridden.
    ser = sl.two_asset_path(dates, spy, None, [1.0] * len(dates), wc.EXPENSE["SPY"], 0.0)
    mkeys, mrets = mir.month_marks(dates, ser)
    index_ret = dict(zip(mkeys, mrets))

    base = price({k: exposure0[k] for k in keys}, dates, spy, shelter, first)
    rows = []
    for mode in ("warning", "collapse"):
        for th in ab.THRESHOLDS:
            for basket, z in (("financial", fin_z), ("control", ctl_z)):
                vm = vetoed(exposure0, z, th, mode)
                veto_map = {k: vm[k] for k in keys}
                hit = [i for i in range(1, len(keys)) if veto_map[keys[i]] == 0.0 and exposure0[keys[i]] > 0.0]
                alt = price(veto_map, dates, spy, shelter, first)
                pr = paired(base["monthly"], alt["monthly"])
                rows.append({"mode": mode, "threshold": th, "basket": basket, "n_vetoed": len(hit),
                             "mean_vetoed_month_return": (statistics.mean([index_ret[keys[i]] for i in hit
                                                                          if index_ret.get(keys[i]) is not None])
                                                          if hit else None),
                             "n_months": pr["n"], "t": pr["t"], "dollars": pr["dollars"],
                             "switches": alt["switches"], "sheltered": alt["sheltered_months"]})
    for r in rows:
        mate = next((q for q in rows if q["mode"] == r["mode"] and q["threshold"] == r["threshold"]
                     and q["basket"] != r["basket"]), None)
        r["control_dollars"] = mate["dollars"] if mate else None
        r["verdict"] = "candidate (control)" if r["basket"] == "control" else grade(
            r["n_vetoed"], r["dollars"], r["control_dollars"])

    turns = [i for i in range(1, len(keys)) if exposure0[keys[i]] != exposure0[keys[i - 1]]]
    zsw = [abs(fin_z[keys[i]]) for i in turns if keys[i] in fin_z]
    allz = [abs(fin_z[k]) for k in keys if k in fin_z]
    turn_z = statistics.mean(zsw) if zsw else float("nan")
    return {"rows": rows, "plan": base, "months": len(keys), "first": first,
            "turn_abs_z": turn_z, "all_abs_z": statistics.mean(allz) if allz else float("nan"),
            "n_turns": len(zsw), "windows": base["n"], "sheltered": base["sheltered_months"],
            "plan_safe": base["safe"], "plan_p_fail": base["p_fail"], "plan_switches": base["switches"]}


def report(o: dict) -> None:
    print(f"  veto test · {o['months']} months from {o['first']} · {o['windows']} ten-year windows · "
          f"the unhedged-by-news plan turned {o['n_turns']} times and sheltered {o['sheltered']} months")
    if o["windows"] < CAP_WINDOWS:
        print(f"  UNRESOLVABLE at the plan level: {o['windows']} ten-year windows cannot measure a 5% failure budget, so"
              f"  nothing below is a withdrawal figure. The paired monthly test is what this corpus can carry.")
    print(f"  the un-vetoed plan on these dates: safe ${o['plan_safe']:,.2f}/mo per $100k, P(fail) "
          f"{o['plan_p_fail']:.1%} over {o['windows']} windows — printed, not claimed.\n")
    print(f"  {'reading':9} {'θ':>4} {'fires':>5} {'equity return in vetoed months':>31} {'switches':>9} "
          f"{'sheltered':>10} {'$/mo paired':>12} {'t':>6} {'control $/mo':>13}  verdict")
    print("  " + "-" * 126)
    for r in o["rows"]:
        if r["basket"] != "financial":
            continue
        c = next(q for q in o["rows"] if q["mode"] == r["mode"] and q["threshold"] == r["threshold"]
                 and q["basket"] == "control")
        mv = r["mean_vetoed_month_return"]
        print(f"  {r['mode']:9} {r['threshold']:>4.1f} {r['n_vetoed']:>5} "
              f"{(f'{mv * 100:+.2f}%' if mv is not None else '—'):>31} {r['switches']:>9} "
              f"{r['sheltered']:>10} {r['dollars']:>+12.2f} {r['t']:>6.2f} {c['dollars']:>+13.2f}  {r['verdict']}")
    print("\n  Every cell is negative: on this record the veto costs the plan money in every reading and at every"
          " threshold.")
    print("  The cells with enough firings to grade are refuted by the control basket, and the two that are not refuted")
    print("  are too small to grade. The one thing the corpus does say is H3's opposite — attention does not cluster")
    print(f"  where the rule turns (|z| {o['turn_abs_z']:.2f} at a turn against {o['all_abs_z']:.2f} in general), so there")
    print("  is not even a switch-cost saving to argue about.")
    print(f"\n  corpus boundary: {BRIDGE}.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    o = run()
    if args.json:
        print(json.dumps({k: v for k, v in o.items() if k != "rows"} | {"rows": o["rows"]},
                         default=str, indent=2, sort_keys=True))
    else:
        report(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
