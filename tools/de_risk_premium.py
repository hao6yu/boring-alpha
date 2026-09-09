"""What de-risking costs in the half of the record that never crashed — the premium, priced.

    .venv/bin/python tools/de_risk_premium.py
    .venv/bin/python tools/de_risk_premium.py --horizons 5,10,15,20 --cheque 400
    .venv/bin/python -m pytest tests/test_de_risk_premium.py -q

Round 20 proved the trend-gated vol target clears the Dominance Rule on SPY at an equal floor, and round 21
found the edge is on one sleeve's record and roughly nothing on VOO's. Between those two facts sits the
question nobody has priced: a rule that steps aside in a crash is insurance, and insurance has a **premium**.
Every note so far has quoted the payout.

## The premium, defined so it cannot hide

The equal-floor frame fixes each rule's median cheque by construction, so a fixed cheque cannot register the
rule's benefit or its cost in the income column at all — it shows up only in what the account is worth at the
end. So the premium is defined in the one unit that is left, and stated as a distribution rather than a
minimum:

    difference(start) = ending capital under the rule − ending capital holding the fund
                        at the same cheque, same horizon, same expense, same turnover charge,
                        same posted borrow rate; reported as a fraction of the opening lump.

Reported per start date: the **share of starts where the rule cost money**, the median, the tenth percentile
(what a mildly-annoying decade costs) and the single worst start. The minimum over starts was round 20's
statistic and it is the least useful one for a purchase decision: it answers "can this destroy me", not
"what does this cost me".

## Two things fixed before any number was computed

1. **Overlapping windows are not independent bets.** Fifteen start dates a year, twenty years apart, re-use
   the same 2008 nine hundred times. The headline win rate is therefore computed on a **non-overlapping**
   chain — consecutive disjoint windows from the earliest possible start — with the overlapping grid reported
   underneath as detail. Counting the bets and not the names is standing rule r15, and a win rate over
   overlapping windows is the exact mistake that rule was written from.
2. **The buy test is a comparison against the cheapest alternative decision, not against zero.** The rule is
   worth buying at a given account size only if the median start is positive *and* the tenth-percentile cost
   is smaller than what choosing a cheaper fund is worth at that size — round 18's noise floor, $25/mo at
   $20k. If the premium at $20k is larger than the fund-swap decision, the rule is a worse use of five minutes
   and a spreadsheet cell.

The 7% comparator used to restate a terminal gap as dollars a month is round 18's convention, kept so the
figures in this file series stay comparable; it is not an expected return and `--irr` moves it.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import income_frontier as ifr                    # noqa: E402  the equaliser, and the plan menu
import withdrawal_capacity as wc                 # noqa: E402  the engine
from funded_frame import per_month_equivalent    # noqa: E402  terminal gap -> level $/mo
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

HORIZONS = (10, 20)
CHEQUE = 400.0
SLEEVES = ("SPY", "VTI", "QQQ")
P = 10                           # the percentile that answers "what does a mild decade cost"


def chain(returns, cash, keys, path, years: int, disjoint: bool) -> list:
    """Windows to price: the whole strided grid, or one non-overlapping chain from the earliest start."""

    stride = years * 12 if disjoint else ifr.STRIDE
    return wc.windows_for(returns, cash, keys, years, stride, path)


def differences(windows_rule: list, windows_index: list, plan_rule, plan_index, cheque: float) -> list:
    """Ending-capital difference per start date, as a fraction of the opening lump.

    Both plans are priced on windows produced from the same calendar and stride, so their start dates line up
    by construction; the assert below is there because a misalignment would show up as a large, plausible
    number rather than as an error.
    """

    out = []
    for w_rule, w_index in zip(windows_rule, windows_index):
        assert w_rule[2] == w_index[2], f"{w_rule[2]} vs {w_index[2]}: the two plans start on different dates"
        rule = ifr.score(w_rule, plan_rule, "fixed", cheque)
        held = ifr.score(w_index, plan_index, "fixed", cheque)
        # A start that died leaves nothing. The engine's `ending` for a dead plan is whatever the last month
        # happened to leave, which for a levered book can be negative; comparing a rule that survived against
        # a fund that killed the account is the whole point of the exercise, so a death is floored at zero
        # rather than allowed to become a credit to the dead plan.
        out.append((w_rule[2], (max(rule.ending, 0.0) - max(held.ending, 0.0)) / wc.START,
                    not rule.survived, not held.survived))
    return out


def describe(rows: list, irr: float, size: float, months: int) -> dict:
    """One row of the table: how often it cost, how much it cost, and what that is per month."""

    diffs = [r[1] for r in rows]
    ordered = sorted(diffs)
    n = len(ordered)

    def pct(q: float) -> float:
        return ordered[min(n - 1, max(0, int(round(q * (n - 1)))))]

    cost = [d for d in diffs if d < 0.0]
    median = statistics.median(diffs)
    tenth = pct(P / 100.0)
    return {"n": n, "win": 1.0 - len(cost) / n, "median": median, "p10": tenth, "worst": ordered[0],
            "best": ordered[-1], "mean": statistics.fmean(diffs),
            "median_mo": per_month_equivalent(median * size, irr, months),
            "p10_mo": per_month_equivalent(tenth * size, irr, months),
            "worst_mo": per_month_equivalent(ordered[0] * size, irr, months),
            "dead_rule": sum(1 for r in rows if r[2]), "dead_index": sum(1 for r in rows if r[3]),
            "avg_cost": statistics.fmean(cost) if cost else 0.0}


def report(sleeve: str, years: int, both: dict, irr: float, sizes: tuple) -> list:
    lines = []
    for kind in ("disjoint", "grid"):
        rows = both[kind]
        if not rows:
            lines.append(f"  {sleeve:5} {years:>3}y  {kind:8} no windows: the record is too short")
            continue
        d = describe(rows, irr, sizes[0], years * 12)
        span = f"{rows[0][0]:%Y-%m}..{rows[-1][0]:%Y-%m}"
        lines.append(f"  {sleeve:5} {years:>3}y  {kind:8} bets {d['n']:>3}  rule lost {100*(1-d['win']):>3.0f}% "
                     f"of them  median {d['median']*100:+6.1f}%  p{P} {d['p10']*100:+6.1f}%  "
                     f"worst {d['worst']*100:+6.1f}%  {span}")
        for size in sizes:
            d = describe(rows, irr, size, years * 12)
            lines.append(f"              at ${size:,.0f}: median {d['median_mo']:+7.0f} /mo   "
                         f"p{P} {d['p10_mo']:+7.0f} /mo   worst start {d['worst_mo']:+7.0f} /mo"
                         + (f"   rule died {d['dead_rule']}x" if d["dead_rule"] else "")
                         + (f"   fund died {d['dead_index']}x" if d["dead_index"] else ""))
    return lines


def build(data, spread: float, sleeve: str, years: int, cheque: float) -> dict:
    """Both plans' windows for one sleeve and horizon, on one calendar, at one stride."""

    calendar = wc.monthly(ifr.series_for(data, sleeve), data.cash_factors)
    returns, cash, keys = calendar
    plans = {p.label: p for p in ifr.plans(cash_yield(data), spread)}
    rule_plan = plans["candidate" if sleeve == "SPY" else f"cand {sleeve}"]
    path = ifr.weight_path(rule_plan.path, data, sleeve, keys)
    grid = wc.windows_for(returns, cash, keys, years, ifr.STRIDE, path)
    disjoint = wc.windows_for(returns, cash, keys, years, years * 12, path)
    index_windows = wc.windows_for(returns, cash, keys, years, ifr.STRIDE)
    index_disjoint = wc.windows_for(returns, cash, keys, years, years * 12)
    return {"rule": rule_plan, "index": plans[sleeve],
            "grid": differences(grid, index_windows, rule_plan, plans[sleeve], cheque),
            "disjoint": differences(disjoint, index_disjoint, rule_plan, plans[sleeve], cheque)}


def cash_yield(data) -> float:
    return ifr.cash_yield_now(data.cash_factors)


def mean_cash(data) -> float:
    monthly = wc.monthly(ifr.series_for(data, "SPY"), data.cash_factors)[1]
    return (1.0 + sum(monthly) / len(monthly)) ** 12 - 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--horizons", default=",".join(str(h) for h in HORIZONS))
    ap.add_argument("--cheque", type=float, default=CHEQUE, help="$ a month per $100k, same for both plans")
    ap.add_argument("--irr", type=float, default=0.07, help="comparator rate for the $/mo restatement")
    ap.add_argument("--sleeves", default=",".join(SLEEVES))
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    spread = ifr.MENU_PUBLIC - mean_cash(data)
    sizes = (20_000.0, 50_000.0, 100_000.0)
    print("the premium of stepping aside · ending capital under the rule minus holding the fund, at the same "
          f"${args.cheque:,.0f}/mo")
    print(f"engine withdrawal_capacity.run · fixed cheque, so the median is identical by construction and "
          f"only capital can speak")
    print(f"headline = non-overlapping chains (each bet a separate decade); grid = every "
          f"{ifr.STRIDE} months and re-uses the same crises\n")
    for sleeve in args.sleeves.split(","):
        for years in (int(h) for h in args.horizons.split(",")):
            both = build(data, spread, sleeve, years, args.cheque)
            print("\n".join(report(sleeve, years, both, args.irr, sizes)))
            print()
    print(f"priced against the decision it competes with: choosing SPY over VOO is worth about "
          f"${ifr.NOISE_FLOOR:,.0f}/mo per $100k\n(= ${ifr.NOISE_FLOOR/5:,.0f}/mo at $20k, round 18). A "
          f"premium larger than that is a worse use of the account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
