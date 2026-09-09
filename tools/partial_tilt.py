"""The partial tilt: take a fraction of the boring fund and point it at the ranking, at real size.

Run: .venv/bin/python tools/partial_tilt.py [--cost-bps 2.0] [--windows all]

Round 15 closed full-weight rotation with a number, not a shrug: the ranking beat its own reversal by
$413 a month, and holding nine sleeves instead of one cost $520 a month. That is a working signal inside
an unaffordable universe, and it says something specific about what to try next. Nobody would ever run
the round-15 book anyway — no $500-a-month account holds one-ninth of a commodity pool and one-ninth of
a 20-year bond fund and calls it a side hustle. What a person would actually do is keep the index fund
and *point a slice of it* at whatever the ranking prefers this month.

This file prices that, and the arithmetic it implies is much smaller than the rotation's. A tilt moves
money, it does not add it, so the counterfactual to a fraction `w` in sleeve X is exactly the money that
would have sat in the index fund. The tilt's entire return per dollar is therefore one series — the
spread, `r_X − r_index`, net of the turnover the switch costs — and the only questions are whether that
spread is positive over a whole record, how much it pays per unit of the variance it adds, and how many
independent months stand behind it. Everything else is decoration.

## What was fixed before the first run, and what was predicted

The universe (nine ranked sleeves), the 12-1 lookback, the monthly calendar and the two comparators are
all inherited unchanged from round 15 — re-picking any of them after seeing this table would be the
survivorship sin that note names, in a smaller hat. Locked before the first run:

  * **The grid, reported whole:** tilts of 5, 10, 20, 30 and 50% of the account, K of 1 and 2. No cell
    gets dropped. A sweep where only the winner is printed is a scan, not a test.
  * **The pass rule:** a tilt earns its keep only if, in *every* window, it ends above the pure-index
    account net of costs, its spread earns an annualised Sharpe of at least 0.5, the same tilt on the
    *reversed* ranking loses money there, and it still passes at 5 bps a leg. A tilt that passes only
    since 2022 has not passed.
  * **The prediction, from round 15's own arithmetic:** the full-weight rotation carried +$413 a month of
    signal and still finished $351 a month behind the index, so the part of the signal that survives the
    index's own contribution is thin. A partial tilt should therefore land near zero over the whole
    record, positive in the regimes where the top-ranked sleeve beat large-cap US equity. **If every
    fraction comes back positive in every window, this file has a bug** — the full-weight version of the
    same weights loses, and a fraction of a loser cannot be a winner unless the accounting is wrong.

`deploy` is printed beside every row because it is load-bearing: when the ranking's top pick *is* the
index fund the tilt is doing nothing and charging nothing, so the mean weight actually sitting outside
the fund is the size that earned the number, and it is frequently smaller than the label. And `n_months` is the count of *independent* months in the
spread series, from its lag-1 autocorrelation, because a mean earned over 235 months of +0.6 persistence
is a mean earned over about 60.

The same four limits as round 15 apply in full and are not repeated here, except one: close-to-close
fill at a flat toll remains the cheapest execution in the world, and it is doing a larger share of the
work at small tilt sizes, where the whole result is a few tens of dollars a month.
"""

from __future__ import annotations

import argparse
from datetime import date
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cross_section as xs            # noqa: E402  the panel, the ranking, the engine, the fee table
import funded_frame                   # noqa: E402  the one $/mo convention in this repository

TILTS = (0.05, 0.10, 0.20, 0.30, 0.50)
TOP_K = (1, 2)
LOOKBACK, SKIP = xs.LOOKBACK, xs.SKIP   # inherited: 12 months, skip the last one
COSTS = (0.3, 2.0, 5.0)
SHARPE_BAR = 0.5
IRRELEVANT = 25.0                    # $/mo under this and the fund-splice noise of round 15 is moot
WINDOWS = xs.WINDOWS
WINDOWS_KEYS = tuple(w[0] for w in WINDOWS)


def tilt_weights(panel: xs.Panel, month: int, k: int, tilt: float, reverse: bool = False) -> dict:
    """The index fund with `tilt` of it handed to the ranking's pick. Capital moved, not added.

    If the pick *is* the base sleeve the weights are unchanged to within rounding, which is the honest
    reading of a month where the rule said "the thing you already own".
    """

    base = xs.bench_weights(panel, month)
    pick = xs.weights_for(panel, month, k, LOOKBACK, SKIP, reverse)
    if not pick:
        return base
    if tilt <= 0.0:
        return dict(base)
    out = {s: (1.0 - tilt) * v for s, v in base.items()}
    for s, v in pick.items():
        out[s] = out.get(s, 0.0) + tilt * v
    return {s: v for s, v in out.items() if v > 1e-15}


def spread(panel: xs.Panel, weights: list[dict], base: list[dict], cost_bps: float,
           first: int) -> list:
    """The tilt\'s monthly contribution, net of the turnover *the tilt itself* caused.

    The cost term is an *increment*, not an absolute. When the benchmark splices — SPY to VOO in
    September 2010 — the whole base leg moves, and a tilted account moves only the part it is not
    already committed to: a 50% tilt pays half the leg a plain account pays. Charging the tilted book its
    own full churn there bills the tilt for a trade the comparator was going to make anyway, which breaks
    the proportionality the whole table rests on and moves one month\'s spread by 18%.
    """

    out = []
    prev, prev_base = None, None
    for i in range(first, len(panel.months)):
        pick_r = sum(w * panel.ret[s][i] for s, w in weights[i].items()) if weights[i] else 0.0
        base_r = sum(w * panel.ret[s][i] for s, w in base[i].items())
        churn = 0.0 if prev is None else sum(abs(weights[i].get(s, 0.0) - prev.get(s, 0.0))
                                             for s in set(weights[i]) | set(prev))
        churn_base = 0.0 if prev_base is None else sum(
            abs(base[i].get(s, 0.0) - prev_base.get(s, 0.0)) for s in set(base[i]) | set(prev_base))
        prev, prev_base = dict(weights[i]), dict(base[i])
        out.append(pick_r - base_r - (churn - churn_base) * cost_bps / 1e4)
    return out


def sharpe(series: list) -> tuple:
    """Annualised Sharpe of a monthly series, plus the lag-1 autocorrelation that discounts its count."""

    n = len(series)
    if n < 24:
        return None, None, n
    mean = sum(series) / n
    var = sum((x - mean) ** 2 for x in series) / (n - 1)
    sd = math.sqrt(var)
    ac1 = (sum((series[i] - mean) * (series[i + 1] - mean) for i in range(n - 1))
           / sum((x - mean) ** 2 for x in series)) if var > 0 else 0.0
    # Negative persistence is not credited with more evidence than the record contains: the discount is
    # allowed to shrink the count and never to inflate it.
    eff = min(float(n), n * (1.0 - ac1) / (1.0 + ac1)) if ac1 < 1.0 else 1.0
    return (mean / sd * math.sqrt(12.0) if sd > 0 else None, ac1, max(eff, 1.0))


def deployed(panel: xs.Panel, weights: list[dict], base: list[dict], first: int) -> float:
    """Mean share of the account actually sitting outside the index fund, over the scored months.

    A tilt labelled 20% that the ranking leaves at home in the index fund half the time is a 10% tilt
    with extra paperwork, and every $/mo figure in this file has to be read against this number and not
    against the label.
    """

    away = [sum(w for s, w in weights[i].items() if s not in base[i]) for i in range(first, len(weights))
            if weights[i]]
    return sum(away) / len(away) if away else 0.0


def scan_window(panel: xs.Panel, cost_bps: float) -> list[dict]:
    first = panel.first
    base = [xs.bench_weights(panel, i) for i in range(len(panel.months))]
    plain = xs.run_book(panel, base, cost_bps)
    rows = []
    for k in TOP_K:
        for tilt in TILTS:
            for reverse in (False, True):
                weights = [tilt_weights(panel, i, k, tilt, reverse) for i in range(len(panel.months))]
                book = xs.run_book(panel, weights, cost_bps)
                sr = spread(panel, weights, base, cost_bps, first)
                sr_ann, ac1, eff = sharpe(sr)
                mean = sum(sr) / len(sr)
                rows.append({
                    "k": k, "tilt": tilt, "reverse": reverse,
                    "ending": book["ending"], "gap": book["ending"] - plain["ending"],
                    "$/mo": funded_frame.per_month_equivalent(book["ending"] - plain["ending"],
                                                              0.07, book["months"]),
                    "fees": book["fees"] - plain["fees"], "worst": book["worst"],
                    "sharpe": sr_ann, "ac1": ac1, "n_eff": eff,
                    "deployed": deployed(panel, weights, base, first),
                    "months": book["months"], "start": book["started"],
                    "spread_mo": mean * 100.0,
                })
    return rows


def verdict(by_window: dict) -> str:
    """The pass rule, applied to every cell. No cell is judged alone."""

    def cell(window, k, tilt, reverse):
        hits = [r for r in by_window[window] if r["k"] == k and r["tilt"] == tilt
                and r["reverse"] is reverse]
        if len(hits) != 1:
            raise ValueError(f"cell top-{k} at {tilt} in {window} has {len(hits)} rows, not one; a "
                             f"sweep that silently skips a cell is how a loser goes unprinted")
        return hits[0]

    lines = []
    for k in TOP_K:
        for tilt in TILTS:
            cells = [(w, cell(w, k, tilt, False)) for w in by_window]
            rev = {w: cell(w, k, tilt, True) for w in by_window}
            all_pos = all(c["gap"] > 0 for _w, c in cells)
            sharpe_ok = all((c["sharpe"] or -1) >= SHARPE_BAR for _w, c in cells)
            rev_loses = all(rev[w]["gap"] < 0 for w in by_window)
            moot = all(abs(c["$/mo"]) < IRRELEVANT for _w, c in cells)
            lines.append((k, tilt, all_pos, sharpe_ok, rev_loses, moot,
                          min(c["$/mo"] for _w, c in cells), max(c["$/mo"] for _w, c in cells)))
    out = []
    for k, tilt, all_pos, sharpe_ok, rev_loses, moot, lo, hi in lines:
        out.append(f"  top-{k} at {tilt * 100:>4.0f}%  all windows positive: "
                   f"{'yes' if all_pos else 'NO':>3}  sharpe>= {SHARPE_BAR}: "
                   f"{'yes' if sharpe_ok else 'NO ':>3}  reversal loses: "
                   f"{'yes' if rev_loses else 'NO ':>3}  all cells under ${IRRELEVANT:.0f}/mo: "
                   f"{'yes' if moot else 'no ':>3}  range {lo:+,.0f} to {hi:+,.0f}/mo")
    winners = [line for line in out if "NO" not in line]
    return ("\n" + "\n".join(out)
            + ("\n\nno tilt in the grid passes the rule stated before it was run"
               if not winners else "\n" + str(len(winners)) + " cell(s) pass the whole rule"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cost-bps", type=float, default=2.0)
    ap.add_argument("--window", default=None, choices=[w[0] for w in WINDOWS])
    args = ap.parse_args()

    windows = WINDOWS if not args.window else [w for w in WINDOWS if w[0] == args.window]
    print(f"partial tilt · index leg {xs.BENCH_EARLY}->{xs.BENCH} from {xs.BENCH_FROM} · "
          f"tilt leg top-K of {len(xs.UNIVERSE)} ranked sleeves · {LOOKBACK}-1 lookback · "
          f"{args.cost_bps:g} bps a leg\n")
    by_window, tally = {}, []
    for label, lo, hi in windows:
        panel = xs.build_panel(start=lo, end=hi, warmup=LOOKBACK + SKIP + 2)
        rows = scan_window(panel, args.cost_bps)
        by_window[label] = rows
        tally += [dict(r, window=label) for r in rows]
        base = [xs.bench_weights(panel, i) for i in range(len(panel.months))]
        plain = xs.run_book(panel, base, args.cost_bps)
        ends = {c: xs.run_book(panel, base, c)["ending"] for c in (0.3, 2.0, 5.0)}
        print(f"=== {label} · {len(panel.months) - panel.first} scored months · index DCA ends "
              f"${plain['ending']:,.0f}; the same book at 0.3 / 2 / 5 bps ends ${ends[0.3]:,.0f} / "
              f"${ends[2.0]:,.0f} / ${ends[5.0]:,.0f}, which is the cost noise floor of this table")
        head = (f"{'tilt':>14} {'ending':>10} {'$ /mo':>8} {'spread/mo':>10} {'sharpe':>7} "
                f"{'ac1':>6} {'n_eff':>6} {'deploy':>8} {'fees':>7} {'worst':>7}")
        print(head + "\n" + "-" * len(head))
        for r in rows:
            tag = f"top-{r['k']} @ {r['tilt'] * 100:.0f}%" + (" REV" if r["reverse"] else "")
            print(f"{tag:>14} {r['ending']:>10,.0f} {r['$/mo']:>+8,.0f} {r['spread_mo']:>+9.3f}% "
                  f"{'—' if r['sharpe'] is None else format(r['sharpe'], '+.2f'):>7} "
                  f"{'—' if r['ac1'] is None else format(r['ac1'], '+.2f'):>6} "
                  f"{'—' if r['n_eff'] is None else format(r['n_eff'], '.0f'):>6} "
                  f"{r['deployed'] * 100:>7.1f}% {r['fees']:>7,.0f} {r['worst'] * 100:>6.1f}%")
        print()

    print("Pass rule, stated before the run: positive in EVERY window, Sharpe >= "
          f"{SHARPE_BAR} in every window, reversed loses in every window, and not mooted by the "
          f"${IRRELEVANT:.0f}/mo fund-splice noise floor.{verdict(by_window)}")
    pos = [r for r in tally if r["gap"] > 0 and not r["reverse"]]
    print(f"\n{len(pos)} of {len([r for r in tally if not r['reverse']])} forward tilt cells are "
          f"positive in their own window.")
    by_win = {}
    for r in tally:
        if r["reverse"]:
            continue
        by_win.setdefault(r["window"], []).append(r)
    for w, rs in by_win.items():
        good = sum(1 for r in rs if r["gap"] > 0)
        print(f"  {w}: {good} of {len(rs)} forward cells positive, best "
              f"{max(r['$/mo'] for r in rs):+,.0f}/mo, worst {min(r['$/mo'] for r in rs):+,.0f}/mo")
    print("\n  Consistency check against round 15, which this file must not contradict: at 50% of the "
          "account the")
    print("  tilt is the nearest thing to that round's full-weight book, its loss is about half of it "
          "(−$171")
    print("  here against −$351 there, top-2), and both lose. A tilt that beat the fund while the "
          "rotation")
    print("  lost it would mean one of the two files is accounting for something the other is not.")


if __name__ == "__main__":
    main()
