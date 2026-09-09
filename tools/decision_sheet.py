"""One page, generated. What to hold, what it costs, and what this archive refuses to answer.

Run: .venv/bin/python tools/decision_sheet.py [--capital 100000] [--want 900] [--position income|insurance]
         [--horizon recent|deep] [--commission 9.95] [--ask news-veto|intraday] [--json]

After seventy-eight rounds the repository does not need another grid. It needs the four grids it has to be read together, in
one sheet, with every figure traceable to the tool that measured it — and with the sheet able to say *no*, which is the part a
report can't do. Round 71's rule applies to this file exactly as it did to the shelter ticket: an instruction sheet is
regenerated from the tools that measured the claim, prints no number it did not read from one of them, and refuses when asked
for something the archive cannot support. There is not one dollar amount written in this file.

The four positions the evidence supports are not one position, and the sheet prints both rather than averaging them into
meaninglessness:

  income      withdraw well inside what the book can fund, over a horizon like the last fifteen years. Capacity is the only
              thing that binds; every candidate's failure probability is zero; growth-tilted books dominate.
  insurance   require a 5% failure budget over the whole record this family can score (1999-12-22 on). No static mix clears
              it at any payout; only a brake does, at a fraction of the capacity above.

Refusals are the other half of the product. Ask this sheet to beat the index with a news veto, or to price a five-day
strategy, or to fund a withdrawal from a book that cannot fund it, and it exits non-zero with the specific missing thing. The
archive is daily closes of fourteen ETFs and a bill curve. It has no intraday print, no quoted spread, and no labelled news,
and rounds 61, 72, 74, 75, 76 and 78 found no monthly-decision rule that beats a static book on capacity. A sheet that
pretended otherwise would be the most expensive document in this repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import binding_payout as bp                                  # noqa: E402
import mix_sweep as ms                                       # noqa: E402
import paper                                                  # noqa: E402
import power_horizon as ph                                    # noqa: E402
import rebalance_cost as rc                                  # noqa: E402
import rotation_search as rse                                # noqa: E402
import tilt_brake as tb                                      # noqa: E402
import withdrawal_capacity as wc                             # noqa: E402

POSITIONS = ("income", "insurance")
HORIZONS = ("recent", "deep")
REFUSED_ASKS = {"news-veto": ("attention-corpus veto (round 72)",
                              "the corpus peaks with rallies, and every priced veto cell was negative"),
                "intraday": ("intraday or multi-day trading",
                             "the archive holds daily closes, no intraday print and no quoted spread"),
                "options": ("options or any derivative", "no options data exists in the archive"),
                "single-stock": ("single-name selection", "the archive holds index ETFs and nothing else")}
HORIZON_FOR_POSITION = {"income": "recent", "insurance": "deep"}


class Refused(Exception):
    """The sheet's answer to a question it cannot price. Carries the reason and what would change it."""

    def __init__(self, reason: str, fix: str):
        super().__init__(reason)
        self.fix = fix


@functools.lru_cache(maxsize=1)
def _archive_end():
    """The last date in the sealed snapshot, read rather than remembered — a sheet that cannot say when it last looked at
    the data is a sheet that will be read a year from now as if it were current."""

    sys.path.insert(0, str(ROOT / "src"))
    import shelter_long_record as sl
    from boring_alpha.data.csv_loader import load_csv_market_data
    return max(sl.legs(load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE), "SPY"))


@functools.lru_cache(maxsize=8)
def _evidence() -> dict:
    return {"mix": ms.grid(100_000.0, 10), "bp": bp.grid(100_000.0, 10), "tb": tb.grid(100_000.0, 10),
            "rot": rse.grid(100_000.0, 10)}


def row(rows: list, key: str, name: str) -> dict:
    return next(r for r in rows if r[key] == name)


@functools.lru_cache(maxsize=None)
def _friction() -> dict:
    """What a rebalancing rule costs, twice over, both stated against the same denominator: money paid in.

    Until round 100 this file typed "the bill … is 0.003-0.054% of paid-in and the *policy* is worth 10.4% of it", which read as
    though the policy were a fraction of the bill. It is the other way round, by two orders of magnitude, and the sentence was
    untraceable to any function. Both figures are now computed from `rebalance_cost` here, at the window the runbook quotes them on.
    """
    record = ph.month_closes(None)
    rows = rc.grid(record, "the record", len(record))
    five = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 5)))
    rows += rc.grid(five, "five years", len(five))
    tax = rc.idealisations = rc.idealisation_tax(rows, "the record", "50% QQQ")
    recent = rc.idealisation_tax(rows, "five years", "50% QQQ")
    paid = rows[0]["paid_in"]
    plain = rc.by(rows, window="the record", construction="50% QQQ", regime=rc.PLAIN)[0]
    band = rc.by(rows, window="the record", construction="50% QQQ", regime="band 5 pts")[0]
    drift = 100.0 * (plain["value"] - band["value"]) / paid
    bill = 100.0 * tax["spread_cost_pct_paid_in"]
    return {"bill_record_pct": bill, "bill_recent_pct": 100.0 * recent["spread_cost_pct_paid_in"],
            "drift_record_pct": drift, "times_the_bill": drift / bill}


def _tiers(capital: float) -> list:
    """What each broker tier costs, expressed as the share of the two-year edge it eats at this size.

    A dollar figure would be comparable only at this capital; a share is comparable across sizes, and it is the number that
    tells a small account whether the second sleeve is worth its ticket. The free row is the denominator, so it is 1.0 by
    construction and printed as such rather than as a finding.
    """

    two = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 2)))
    free = rc.dominance(two, capital, 0.0)
    out = []
    for tier in rc.COMMISSIONS:
        cell = rc.dominance(two, capital, tier)
        out.append({"commission": tier, "gap": cell["gap"], "dominates": cell["dominates"],
                    "share_of_free_edge": (cell["gap"] / free["gap"]) if free["gap"] > 0.0 else None,
                    "tickets": cell["tilt_tickets"], "witness_tickets": cell["witness_tickets"]})
    return out


def sheet(capital: float, want: float | None, position: str, horizon: str, ask: str | None,
          commission: float | None = None) -> dict:
    """Everything the sheet will print, as data. The renderer adds no numbers of its own."""

    if ask:
        if ask not in REFUSED_ASKS:
            raise Refused(f"unknown request '{ask}'", f"this sheet can price only {', '.join(POSITIONS)}")
        what, why = REFUSED_ASKS[ask]
        raise Refused(f"cannot price {what}: {why}",
                      "acquire the data first; no amount of modelling substitutes for it")
    if capital <= 0:
        raise Refused("capital must be a positive number", "the sheet scales everything from it")
    if commission is not None and commission < 0:
        raise Refused("--commission cannot be negative", "a broker that pays you to trade is not in the archive either")
    if position not in POSITIONS:
        raise Refused(f"unknown position '{position}'", f"pick one of {', '.join(POSITIONS)}")
    if horizon not in HORIZONS:
        raise Refused(f"unknown horizon '{horizon}'", f"pick one of {', '.join(HORIZONS)}")

    ev = _evidence()
    mix, bpg, tbl, rot = ev["mix"], ev["bp"], ev["tb"], ev["rot"]
    ctl_window = horizon
    book = "mix_100" if position == "income" else "brake_75"
    out = {"as_of": _archive_end().isoformat(), "capital": capital,
           "want": want, "position": position, "horizon": horizon, "positions": {},
           "must_beat": {}, "asked": None}

    for name in ("mix_00", "mix_50", "mix_100", "brake_75"):
        r = row(mix["rows"], "name", name)
        out["positions"][name] = {
            "qqq": r["qqq"], "brake": r["brake"],
            "capacity": {w: r["windows"][w]["safe"] * capital / 100_000.0 for w in ("deep", "recent")},
            "meets_budget": {w: r["windows"][w]["capacity_meets_budget"] for w in ("deep", "recent")},
            "floor_fail": {w: r["windows"][w]["floor_fail"] for w in ("deep", "recent")},
            "dd": {w: r["windows"][w]["dd"] for w in ("deep", "recent")}}
    out["deep_start"] = mix["deep"].isoformat()
    out["record_recent"] = mix["recent"].isoformat()

    for name, label in (("blend_sq", "control"), ("spy_only", "plain SPY"), ("qqq_only", "plain QQQ")):
        r = row(rot["rules"], "rule", name)
        out["must_beat"][label] = {w: r["cells"][("start", w)]["safe"] * capital / 100_000.0 for w in ("long", "recent")}
    out["control_delta_recent"] = row(rot["rules"], "rule", "blend_sq")["cells"][("start", "recent")]["vs_spy"] * \
        capital / 100_000.0
    br = row(tbl["rows"], "rule", "brake_either")["cells"]
    out["brake_vs_control"] = {"long": br[("start", "long")]["vs_control"] * capital / 100_000.0,
                               "recent": br[("start", "recent")]["vs_control"] * capital / 100_000.0}

    best_rule = max((r for r in rot["rules"] if r["rule"] not in ("spy_only", "qqq_only", "blend_sq")),
                    key=lambda r: r["cells"][("start", "recent")]["vs_spy"])
    # `vs_spy` is a difference of `safe` figures, and every other line built from `safe` on this sheet is scaled to the
    # capital the reader named. Round 86 found this one line was not: the sheet printed the same 88.29 a month for a 25,000-dollar
    # account and a 400,000-dollar one: a figure per hundred thousand wearing a dollar sign.
    scale = capital / 100_000.0
    out["best_rule"] = {"name": best_rule["rule"], "vs_spy_recent": best_rule["cells"][("start", "recent")]["vs_spy"] * scale,
                        "vs_control_recent": min(best_rule["vs_blend"] or (0.0, 0.0)) * scale,
                        "verdict": best_rule["verdict"]}

    # Section 4's data. The dominance scan is the only part of this sheet that is not scale-free, and it is the part that
    # answers the question a small account actually has: the whole rest of the sheet prices proportions, and a ticket is not
    # a proportion. Round 86: at a thousand of capital with a 9.95-dollar ticket the two-sleeve book ends BELOW plain VOO over
    # two years, which no
    # proportional figure in seventy rounds of this repository could have shown.
    out["execution"] = {"band_points": paper.TILT_BAND_POINTS, "commission": commission,
                        "free": rc.scan(capital, 0.0),
                        "priced": rc.scan(capital, float(commission)) if commission is not None else None,
                        "tiers": _tiers(capital), "friction": _friction()}

    picked = out["positions"][book]
    out["book"] = book
    out["asked"] = None
    if want is not None:
        if want <= 0:
            raise Refused("--want must be a positive withdrawal", "it is the thing being asked of the book")
        bmr = row(bpg["rows"], "name", "dm12_sq")["windows"]
        out["asked"] = {"want": want, "as_multiple_of_control_recent": want / (out["must_beat"]["control"]["recent"]),
                        "capacity_of_book": picked["capacity"][ctl_window],
                        "meets_budget_on_book": picked["meets_budget"][ctl_window],
                        "p_fail": None, "n": None, "dm12_sq_recent_p_fail": bmr["recent"]["p_fails"].get(1.00)}
        if not picked["meets_budget"][ctl_window]:
            raise Refused(
                f"no withdrawal at all meets a 5% failure budget on the {ctl_window} record for this book",
                f"switch to --position insurance: the braked book funds "
                f"{money(out['positions']['brake_75']['capacity']['deep'])}/mo on that record at this size, "
                f"and nothing else does")
        if want > picked["capacity"][ctl_window]:
            raise Refused(
                f"${want:,.2f}/mo exceeds what the {book} book can fund on the {ctl_window} record "
                f"(${picked['capacity'][ctl_window]:,.2f}/mo at this size)",
                "reduce the withdrawal, add capital, or accept a failure budget you have named instead of 5%")
        out["asked"]["p_fail"], out["asked"]["n"] = _p_fail_at(capital, round(want, 2), book, ctl_window)
    return out


@functools.lru_cache(maxsize=32)
def _p_fail_at(capital: float, want: float, book: str, window: str) -> tuple:
    """The failure probability at exactly the withdrawal asked for — measured on a fresh path, not interpolated between the
    multiples some other table happened to use."""

    import monthly_income_race as mir
    import shelter_long_record as sl
    import tilt_brake as tbm
    from boring_alpha.data.csv_loader import load_csv_market_data
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    series = {s: sl.legs(data, s) for s in ("SPY", "QQQ")}
    sig = {s: sl.month_signal(sorted(series[s]), series[s], "start") for s in ("SPY", "QQQ")}
    dates = [d for d in sorted(set(series["SPY"]) & set(series["QQQ"])) if d >= ms.deep_start(series)]
    months = sorted({(d.year, d.month) for d in dates})
    mix = _evidence()["mix"]
    since = mix["deep"] if window == "deep" else mix["recent"]
    use = [d for d in dates if d >= since]
    weight, brake = next((r["qqq"], r["brake"]) for r in mix["rows"] if r["name"] == book)
    weights = tbm.weights_from_marks(series, use, ms.mark_for(weight, brake, sig, months))
    c = rse.score(series, use, weights, capital, 10, targets=(round(want, 2),))
    return c["p_fails"][round(want, 2)], c["n"]


def money(v: float) -> str:
    """One format for every figure on the sheet, so a negative premium reads as minus rather than as `$-166.55`."""

    return ("-$" if v < 0 else "$") + f"{abs(v):,.2f}"


def render(o: dict) -> str:
    c = money  # noqa: E731
    p = lambda v: f"{100 * abs(v):.1f}%"  # noqa: E731
    lines = []
    a = lines.append
    a("  DECISION SHEET · generated, not written · every figure below was read from the tool named beside it")
    a(f"  scale ${o['capital']:,.0f} · position {o['position']} · horizon {o['horizon']} · archive through "
      f"{o['as_of'] or 'the sealed snapshot'}")
    a("")
    a("  1. THE TWO POSITIONS, PRICED SIDE BY SIDE  [mix_sweep.py]")
    a(f"     record A: {o['record_recent']} on (the last fifteen years)      record B: {o['deep_start']} on "
      f"(the earliest this family can be scored)")
    for name, v in o["positions"].items():
        a(f"     {name:9} {v['qqq']:>4.0%} QQQ{' +cash brake' if v['brake'] else '          '}   "
          f"A funds {c(v['capacity']['recent']):>10}  "
          + (f"B funds {c(v['capacity']['deep']):>10}" if v["meets_budget"]["deep"] else "B funds      none")
          + f"   worst drawdown A {p(abs(v['dd']['recent']))} B {p(abs(v['dd']['deep']))}")
    a(f"     the growth tilt's whole recent-window advantage over the plain fund: {c(o['control_delta_recent'])}/mo")
    a(f"     a brake against the static blend: {c(o['brake_vs_control']['long'])}/mo long, "
      f"{c(o['brake_vs_control']['recent'])}/mo recent  [tilt_brake.py]")
    a("")
    a("  2. WHAT A BOT HAS TO BEAT  [rotation_search.py]")
    a(f"     the static 50/50 control, which makes no decisions: {c(o['must_beat']['control']['recent'])}/mo recent, "
      f"{c(o['must_beat']['control']['long'])}/mo long")
    a(f"     plain SPY, the benchmark named in the objective:   {c(o['must_beat']['plain SPY']['recent'])}/mo recent")
    a(f"     plain QQQ, the free version of the tilt:           {c(o['must_beat']['plain QQQ']['recent'])}/mo recent")
    a(f"     the best rule the archive contains ({o['best_rule']['name']}): {c(o['best_rule']['vs_spy_recent'])}/mo "
      f"against plain SPY, and it is beaten by the control by {c(abs(o['best_rule']['vs_control_recent']))}/mo on the same")
    a(f"     window. Its own verdict line, from the tool: {o['best_rule']['verdict']}")
    a("")
    a("  3. WHAT THIS ARCHIVE REFUSES  [docs/reviews/README.md, rules 61-78]")
    for what, (_, why) in REFUSED_ASKS.items():
        a(f"     {what:11} — {why}")
    a("")
    a("  4. HOW TO EXECUTE IT, AT YOUR SIZE  [rebalance_cost.py, paper.py]")
    ex = o["execution"]
    fr = ex["friction"]
    a(f"     rebalance only past {ex['band_points']:g} points of drift, and know which cost is which. Over the record the bill for"
      f" the tickets is {fr['bill_record_pct']:.3f}% of paid in ({fr['bill_recent_pct']:.3f}% over the last five years); what the"
      f" *policy* of rebalancing cost — the same two funds with the band honoured instead of never traded again — is "
      f"{fr['drift_record_pct']:.2f}% of paid in, or {fr['times_the_bill']:.0f} times the bill. Both recomputed from"
      f" rebalance_cost.py when the sheet was built, and neither contains a transaction")
    two = next(h for h in ex["free"] if h["horizon"] == "two years")
    rec = next(h for h in ex["free"] if h["horizon"] == "the record")
    a(f"     with no commission the comparison does not depend on size at all: the tilt is ahead by "
      f"{100 * two['gap'] / two['paid_in']:+.1f}% of paid in over two years and "
      f"{100 * rec['gap'] / rec['paid_in']:+.1f}% over the record, at every size the tool prices "
      f"(the ladder runs {rc.CAPITAL_LADDER[0]:,.0f} to {rc.CAPITAL_LADDER[-1]:,.0f})")
    if ex["priced"] is None:
        a(f"     a flat ticket breaks that invariance, and the sheet was not told yours: pass --commission (0, 4.95 and 9.95"
          f" are priced by the tool) to see what ${o['capital']:,.0f} of capital keeps")
    for h in (ex["priced"] or []):
        verdict = "dominates" if h["dominates"] else "FAILS against"
        a(f"     at ${ex['commission']:.2f} a ticket, {o['capital']:,.0f} of capital over {h['horizon']}: the tilt {verdict}"
          f" plain VOO by {100 * abs(h['gap']) / h['paid_in']:.1f}% of everything paid in"
          f" ({h['tilt_tickets']:.0f} tickets against the witness's {h['witness_tickets']:.0f})")
    if ex["priced"] is not None:
        for t in ex["tiers"]:
            share = t["share_of_free_edge"] or 0.0
            kept = (f"keeps {100 * share:.0f}% of" if share >= 0 else f"gives up {100 * (1 - share):.0f}% of")
            a(f"     tier ${t['commission']:.2f}: the two-sleeve book {kept} its commission-free two-year edge at this size"
              f"{' and still dominates' if t['dominates'] else ' and ENDS BEHIND the witness'}")
    if ex["priced"] is not None and any(not h["dominates"] for h in ex["priced"]):
        worst = min((h for h in ex["priced"] if not h["dominates"]), key=lambda h: h["gap"] / h["paid_in"])
        a(f"     REFUSED at this size on this broker: {worst['horizon']} is enough — the two-sleeve form ends behind the"
          f" witness. Hold one fund, or use a broker that charges nothing per ticket; the ticket count is set by the fund"
          f" count, not by the rebalancing policy")
    a("")
    if o["asked"] is None:
        a("  5. NO WITHDRAWAL ASKED · pass --want to be told whether a specific withdrawal survives")
        return "\n".join(lines)
    q = o["asked"]
    a("  5. THE ASK, PRICED  [binding_payout.py, mix_sweep.py]")
    a(f"     asked {c(q['want'])}/mo = {q['as_multiple_of_control_recent']:.2f}x the static blend's recent-window capacity")
    a(f"     the {o['book']} book funds {c(q['capacity_of_book'])}/mo on the {o['horizon']} record at a 5% failure budget")
    if q["p_fail"] is not None:
        a(f"     measured failure probability at exactly that withdrawal: {p(q['p_fail'])} of {q['n']} ten-year windows")
    a(f"     for reference, the best rule in the archive fails {p(q['dm12_sq_recent_p_fail'])} at the blend's capacity")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--want", type=float, default=None)
    ap.add_argument("--position", choices=POSITIONS, default="income")
    ap.add_argument("--horizon", choices=HORIZONS, default=None)
    ap.add_argument("--commission", type=float, default=None,
                    help="what the broker charges per ticket; omit it and the sheet prices the two-sleeve book commission-free")
    ap.add_argument("--ask", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    horizon = args.horizon or HORIZON_FOR_POSITION[args.position]
    try:
        o = sheet(args.capital, args.want, args.position, horizon, args.ask, args.commission)
    except Refused as e:
        print(f"  REFUSED · {e}\n  what would change it: {e.fix}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(o, indent=2, sort_keys=True, default=str))
    else:
        print(render(o))
        print("\n  regenerate with: .venv/bin/python tools/decision_sheet.py"
              f" --capital {args.capital:g} --position {args.position}"
              + (f" --commission {args.commission:g}" if args.commission is not None else "")
              + (f" --want {args.want:g}" if args.want else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
