"""Which entry states does the rule protect, and which does it cost you in? The 2x2 table, not the average.

Round 62. Two claims survived the last seven rounds and both are about shape rather than average return: round 58's
trend leg supported 36% more monthly withdrawal than the index, and round 60's long record found 4.2% of 10-year
windows left a plain-equity contributor with less than they deposited while the trend rule had no such window. An
average over hundreds of windows is the wrong statistic for a person who will live through exactly one of them. What
decides whether either claim is worth having is *concordance*:

  * index fails, rule survives — **insurance**. This is the only cell that makes a risk-reduction claim worth paying
    for, and it is the cell round 60's "0% vs 4.2%" is really describing.
  * both fail — **redundant**. The rule failed in the same place the sleeve failed, so it added a cost and no shelter.
  * rule fails, index survives — **cost**. Paying for protection you did not need, which is fine in small doses and
    fatal in large ones.
  * neither fails — the boring majority, printed so the other three can be read as fractions of a real denominator.

Two frames, the two that match how money actually moves: a withdrawal at round 58's fixed $435.47 a month from
$100,000, and round 60's contribution of $1,000 a month from nothing. Same record (SPY monthly, 1993 to 2026), same
engines as those rounds, every window scored at the same payout so the cells are comparable.

Run:  python tools/entry_state.py [--years 10] [--payout 435.47] [--contribution 1000] [--worst 3]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import plan_survival as ps                               # noqa: E402
import rates_gate as rg                                  # noqa: E402
import withdrawal_capacity as wc                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

BENCH = "SPY hold"
ALL_LEGS = ("SPY hold", "MA200 monthly", "static 60/40", "yield_gate", "carry_flip", "tightening_exit",
            "ma200_and_gate")
LEGS_DEFAULT = ("SPY hold", "MA200 monthly", "static 60/40")
CELLS = ("insurance", "redundant", "cost", "fine")


def legs_from_long_record(data, years: int) -> dict:
    """The monthly series and their dates, straight from round 59's engine."""

    out, keys, eq, cash, _y, _sg = rg.series(data, years, 100_000.0, 0.05)
    series = {leg: (out[leg]["dates"], out[leg]["m"]) for leg in ALL_LEGS if leg != "static 60/40"}
    series["static 60/40"] = (keys[1:], [0.6 * a + 0.4 * b for a, b in zip(eq[1:], cash[1:])])
    return series


def starts(series: dict, years: int) -> list:
    """Every month from which every leg has a full plan ahead of it, on contiguous dates."""

    months = years * 12
    idx = {leg: {d: i for i, d in enumerate(dates)} for leg, (dates, _m) in series.items()}
    keep = []
    first_dates = series[BENCH][0]
    for s in range(0, len(first_dates) - months + 1):
        d0 = first_dates[s]
        ok = True
        for leg, (dates, m) in series.items():
            i = idx[leg].get(d0)
            if i is None or i + months > len(m):
                ok = False
                break
            if dates[i:i + months] != first_dates[s:s + months]:
                ok = False                              # a leg missing a month inside the window: skip it
                break
        if ok:
            keep.append((d0, s))
    return keep


def score(series: dict, start_list: list, years: int, payout: float, contribution: float, capital: float) -> dict:
    """Per leg, per start month: the outcome and the terminal balance."""

    months = years * 12
    out = {}
    for leg, (dates, m) in series.items():
        idx = {d: i for i, d in enumerate(dates)}
        rows = []
        for d0, _s in start_list:
            i = idx[d0]
            window = m[i:i + months]
            if contribution > 0:
                r = ps.simulate(window, capital, 0.0, contribution, 0.0)
                total = capital + contribution * months
                rows.append({"date": d0, "terminal": r["terminal"], "failed": r["terminal"] < total - 1e-9,
                             "multiple": r["terminal"] / total})
            else:
                r = ps.simulate(window, capital, payout, 0.0, 0.0)
                rows.append({"date": d0, "terminal": r["terminal"], "failed": not r["survived"],
                             "multiple": r["terminal"] / capital})
        out[leg] = rows
    return out


def contingency(scored: dict) -> dict:
    """The 2x2 against the benchmark, plus the conditional that answers 'does it help when you need it'."""

    base = {r["date"]: r["failed"] for r in scored[BENCH]}
    cells = {leg: dict(zip(CELLS, (0, 0, 0, 0))) for leg in scored}
    for leg, rows in scored.items():
        for r in rows:
            b, me = base[r["date"]], r["failed"]
            if b and me:
                cells[leg]["redundant"] += 1
            elif b:
                cells[leg]["insurance"] += 1
            elif me:
                cells[leg]["cost"] += 1
            else:
                cells[leg]["fine"] += 1
    for leg, c in cells.items():
        n_base_fail = c["insurance"] + c["redundant"]
        c["n"] = sum(c[k] for k in CELLS)
        c["p_fail_self"] = (c["redundant"] + c["cost"]) / c["n"]
        c["concordance"] = (c["redundant"] / n_base_fail) if n_base_fail else None
    return cells


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--payout", type=float, default=435.47)
    ap.add_argument("--contribution", type=float, default=1_000.0)
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--worst", type=int, default=3)
    ap.add_argument("--legs", default=",".join(LEGS_DEFAULT),
                    help="comma-separated subset of the legs to score; a short leg shrinks the common start set")
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    wanted = tuple(x.strip() for x in args.legs.split(",") if x.strip())
    for w in wanted:
        if w not in ALL_LEGS:
            raise SystemExit(f"no such leg: {w}. Try one of {list(ALL_LEGS)}")
    if BENCH not in wanted:
        raise SystemExit(f"{BENCH} must be scored: it is the reference for every cell")
    all_series = legs_from_long_record(data, args.years)
    # Only the legs being scored may constrain the start set. Scoring three legs against a fourth one's warm-up
    # silently shortened the sample by three years on the first run of this file.
    series = {k: v for k, v in all_series.items() if k in wanted}
    start_list = starts(series, args.years)
    d0 = start_list[0][0]
    d1 = series[BENCH][0][start_list[-1][1] + args.years * 12 - 1]
    print(f"entry states · SPY monthly, starts {d0} to {start_list[-1][0]}, last plan ends {d1}"
          f" · {len(start_list)} window starts"
          f" · {args.years}-year plans · legs {list(wanted)}")
    print("  every leg scored at the same payout at every start, so the cells below are one denominator apiece\n")

    frames = (("withdrawal", args.payout, 0.0, args.capital),
              ("contribution", 0.0, args.contribution, 0.0))
    for label, payout_, contrib_, cap_ in frames:
        scored = score(series, start_list, args.years, payout_, contrib_, cap_)
        cells = contingency(scored)
        n = cells[BENCH]["n"]
        base_fail = sum(1 for r in scored[BENCH] if r["failed"])
        print(f"  FRAME: {label} — " + (f"${payout_:,.2f}/mo from ${cap_:,.0f}, failure = ever liquidated or"
                                       " ends below the start" if payout_ else
                                       f"${contrib_:,.0f}/mo into ${cap_:,.0f} start, failure = ends below what was"
                                       " deposited"))
        print(f"    the benchmark failed in {base_fail} of {n} entry states ({base_fail / n:.1%})\n")
        order = [l for l in wanted if l in scored]
        print(f"    {'leg':16} {'insurance':>22} {'redundant':>20} {'cost':>18} {'fine':>10}"
              f" {'P(fail)':>8} {'P(fail|index fails)':>20}")
        print("    " + "-" * 100)
        for leg in order:
            c = cells[leg]
            ins = f"{c['insurance']:>4} ({c['insurance'] / n:>5.1%})"
            red = f"{c['redundant']:>4} ({c['redundant'] / n:>5.1%})"
            cost = f"{c['cost']:>4} ({c['cost'] / n:>5.1%})"
            conc = "  n/a (0 bench fails)" if c["concordance"] is None else f"{c['concordance']:>20.0%}"
            print(f"    {leg:16} {ins:>22} {red:>20} {cost:>18} {c['fine']:>10}"
                  f" {c['p_fail_self']:>8.1%} {conc}")
        print("\n    concordance = P(this leg also fails | the index fails). 100% means the protection is absent"
              " exactly\n    when it is wanted. Insurance is the first column; cost is the third; the two are not"
              " the same trade.")

        worst = sorted(scored[BENCH], key=lambda r: r["multiple"])[:args.worst]
        print(f"\n    the {args.worst} worst entry months for the index, and what each leg did from the same month:")
        hdr = " ".join(f"{leg[:14]:>16}" for leg in order)
        print(f"      entered        index x      {hdr}")
        for w in worst:
            row = f"      {w['date']}      {w['multiple']:>7.2f}x"
            for leg in order:
                r = next(x for x in scored[leg] if x["date"] == w["date"])
                row += f" {r['multiple']:>10.2f}x{'F' if r['failed'] else '.'}"
            print(row)
        med = {leg: statistics.median(r["multiple"] for r in rows) for leg, rows in scored.items()}
        print("      " + "-" * 78)
        print("      median        " + " ".join(f"{med[leg]:>10.2f}x" for leg in order)
              + "   (F = failed, . = survived)")
        print("")
    print("  the cell counts answer a different question from the medians above, and the two can disagree: a rule can")
    print("  cost a little on every window to save a great deal on a few. Which of those is happening is visible in")
    print("  the ratio of the first column to the third, not in either average.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
