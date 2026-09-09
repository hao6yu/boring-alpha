"""Does attention forecast the index, and is what it forecasts worth more than the trade it causes?

Run: .venv/bin/python tools/attention_bar.py [--cost-bps 2]

The feed is captured by `attention_feed.py` and sealed before this file runs: 14 daily series, 2015-07-01 to
2026-09-04, 4,084 days, every response blob content-addressed and re-hashed by `verify`. Page views are chosen
because they satisfy the two properties this repository has failed to get from any other non-price input — the
value for a day was knowable on that day, and the series is never revised afterwards. What it measures is
reader attention rather than news content: the cheapest honest approximation to the input the goal asked for
that a retail account can actually obtain point-in-time.

## The rule, written before the join

Fixed while no return had been read against it, in the capture tool's docstring and restated here.

  *signal*        log of the financial basket's daily view sum, z-scored against a trailing 252 days of its
                  own past, using data through that day only. No whole-sample statistic appears anywhere in
                  this file: a global mean is the future leaking backwards.
  *decision*      a month's signal is the mean of its daily z. Exposure for the *following* month is set by
                  that number and nothing else, and the one-month shift is tested rather than assumed.
  *sitting out*   an explicit zero weight, which earns the archive's cash factor. Not an empty row:
                  `run_book` reads an empty row as "hold what you held", which would turn a market-timing
                  test into buy-and-hold and print the most convincing wrong number in the file.
  *directions*    both are priced and both printed. Panic at a high is plausibly a contrarian buy (the crowd
                  exhausts) and plausibly a warning (attention follows the fall). Choosing which one after
                  seeing the result is the oldest way to make a dead feed look alive.
  *thresholds*    the whole grid, z of 0.5, 1.0 and 1.5, both directions. Twelve cells, none dropped.
  *book*          the funded frame the repository has used since round 4: $5,000 opened, $500 a month, the
                  sleeve's real expense ratio, 2 bps per unit of one-way turnover, four windows.
  *bar*           plain DCA into the same sleeve, and plain DCA into VOO — the two comparators every round
                  since 15 has carried. A feed that predicts and still loses to DCA net of costs is a
                  redundant feed, and it is reported as one instead of restated as a finding.
  *control*       the six non-financial articles through the identical pipeline with its own rolling z. If
                  `Water` and `Moon` clear the bar, the bar is broken and not the market.
  *pass rule*     positive versus DCA in every window, better than the same rule run backwards, above the
                  $25/month floor inside which the choice between two near-identical index funds already
                  moves the answer, and not reproducible by the control basket.

## What a pass would and would not mean

The sample is eleven years: 134 months, one inflation panic, one pandemic drawdown, one 2022 bear — and no
2008, because the endpoint's own depth limit is 2015-07-01 and no analysis extends that. A pass here is
evidence about a decade, not about a mechanism. Attention is persistent, so the effective count is printed next
to the raw one; a signal that is "on" four months in five has far fewer bets than it has months.

The likeliest outcome, on fifteen rounds of precedent, is that the feed carries something real and that what it
carries is worth less than the trades it would cause. That is what "priced" means in this repository, and this
file exists to say it in dollars rather than adjectives.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cross_section as xs                       # noqa: E402  the funded book, the panel, the comparators
from funded_frame import per_month_equivalent    # noqa: E402

PANEL_FILE = ROOT / "data" / "attention" / "attention_daily.csv"
SLEEVE, BENCH = "SPY", "VOO"
Sleeves = (SLEEVE, BENCH)
THRESHOLDS = (0.5, 1.0, 1.5)
ROLL, MIN_HISTORY = 252, 189
NOISE_FLOOR = 25.0            # $/mo: what the SPY-vs-VOO choice alone is worth, measured in round 15
# Windows inside the feed's own reach. 2008 is unavailable to this feed at any price.
WINDOWS = (("full 2015-07..2026-08", date(2015, 7, 1), date(2026, 9, 4)),
           ("A 2015-07..2019", date(2015, 7, 1), date(2020, 1, 1)),
           ("B 2020..2022", date(2020, 1, 1), date(2023, 1, 1)),
           ("C 2023..2026-08", date(2023, 1, 1), date(2026, 9, 4)))


def rolling_z(values: list[float]) -> list:
    """z against the trailing year, from data through each day only; None until a usable window exists."""

    out = []
    for i in range(len(values)):
        window = values[max(0, i - ROLL):i + 1]
        if len(window) < MIN_HISTORY:
            out.append(None)
            continue
        mean = sum(window) / len(window)
        sd = math.sqrt(sum((v - mean) ** 2 for v in window) / len(window))
        out.append((values[i] - mean) / sd if sd > 1e-9 else 0.0)
    return out


def load_panel() -> tuple[list, list, list]:
    if not PANEL_FILE.exists():
        raise SystemExit(f"{PANEL_FILE.name} missing. run `attention_feed.py fetch`, then `panel`.")
    days, fin, ctl = [], [], []
    with PANEL_FILE.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            days.append(date.fromisoformat(row["day"]))
            fin.append(math.log(max(float(row["fin_sum"]), 1.0)))
            ctl.append(math.log(max(float(row["ctl_sum"]), 1.0)))
    return days, fin, ctl


def monthly(days: list, values: list) -> dict:
    """Month -> mean of that month's daily z. A month with fewer than 15 scored days does not exist."""

    zs = rolling_z(values)
    buckets: dict = {}
    for d, z in zip(days, zs):
        if z is not None:
            buckets.setdefault((d.year, d.month), []).append(z)
    return {date(k[0], k[1], 1): sum(v) / len(v) for k, v in sorted(buckets.items()) if len(v) >= 15}


def schedule(panel: xs.Panel, by_month: dict, threshold: float, panic_buys: bool) -> list:
    """Weights for every month of the panel, from the previous month's signal only.

    The shift lives here: the row that drives month i is built from the signal of month i-1, so no decision
    in this file can see the month it is trading. A sit-out is an explicit zero, and a month before the
    first usable signal is a zero too — the book starts in cash rather than starting in the market by
    default, which is the assumption a timing test must not be allowed to make for free.
    """

    out = []
    for i in range(len(panel.months)):
        key = panel.months[i].replace(day=1)
        z = by_month.get(key) if i >= 1 else None
        previous = by_month.get(panel.months[i - 1].replace(day=1)) if i >= 1 else None
        if previous is None:
            out.append({s: 0.0 for s in Sleeves})
            continue
        hot = previous >= threshold
        del z
        # One sleeve gets the whole weight. The first version of this line put 1.0 in *every* sleeve,
        # which read as fully invested and was 2.0x — a leveraged timing rule priced as an unlevered one,
        # and the exposure column did not notice because 2.0 is also greater than 0.5. The benchmark leg
        # is a comparator and is never held.
        on = hot if panic_buys else not hot
        out.append({s: (1.0 if (on and s == SLEEVE) else 0.0) for s in Sleeves})
    return out


def price(panel: xs.Panel, weights: list, cost_bps: float) -> dict:
    """One window: the rule against DCA into the same sleeve and into the goal's own benchmark."""

    n = len(panel.months)
    book = xs.run_book(panel, weights, cost_bps, first=panel.first)
    dca = xs.run_book(panel, [{s: (1.0 if s == SLEEVE else 0.0) for s in Sleeves}] * n, cost_bps,
                      first=panel.first)
    bench = xs.run_book(panel, [xs.bench_weights(panel, i) for i in range(n)], cost_bps, first=panel.first)
    months = book["months"]
    live = [sum(weights[i].values()) for i in range(panel.first, n)]
    if max(live) > 1.0 + 1e-9:
        raise ValueError(f"the schedule asks for {max(live):.2f}x exposure; this tool prices an unlevered "
                         f"timing rule and will not silently price leverage instead")
    on = sum(1 for v in live if v > 0.5) / months
    return {"gap": book["ending"] - dca["ending"], "gap_vs_bench": book["ending"] - bench["ending"],
            "$/mo": per_month_equivalent(book["ending"] - dca["ending"], 0.07, months),
            "$/mo_vs_bench": per_month_equivalent(book["ending"] - bench["ending"], 0.07, months),
            "ending": book["ending"], "dca": dca["ending"], "bench": bench["ending"],
            "fees": book["fees"], "worst": book["worst"], "on": on, "months": months,
            "turnover": book["turnover"]}


def persistence(series: list) -> tuple:
    live = [v for v in series if v is not None]
    if len(live) < 24:
        return None, None
    pairs = list(zip(live, live[1:]))
    mx = sum(a for a, _ in pairs) / len(pairs)
    my = sum(b for _, b in pairs) / len(pairs)
    cov = sum((a - mx) * (b - my) for a, b in pairs) / len(pairs)
    vx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs) / len(pairs))
    vy = math.sqrt(sum((b - my) ** 2 for _, b in pairs) / len(pairs))
    ac1 = cov / (vx * vy) if vx * vy > 1e-12 else 0.0
    n_eff = len(live) * (1 - ac1) / (1 + ac1) if ac1 < 0.95 else 1.0
    return ac1, max(min(n_eff, len(live)), 1.0)


def scan(cost_bps: float) -> tuple[list, dict]:
    days, fin, ctl = load_panel()
    fm, cm = monthly(days, fin), monthly(days, ctl)
    if list(fm) != list(cm):
        raise SystemExit("the two baskets disagree about which months exist; that is a capture bug")
    rows, meta = [], {}
    for name, lo, hi in WINDOWS:
        panel = xs.build_panel(Sleeves, lookback_months=1, start=lo, end=hi, warmup=15, reference=SLEEVE)
        for basket, series in (("financial", fm), ("control", cm)):
            live = [series[m.replace(day=1)] for m in panel.months if m.replace(day=1) in series]
            ac1, n_eff = persistence(live)
            if name == WINDOWS[0][0]:
                meta[basket] = (ac1, n_eff, len(live))
            for threshold in THRESHOLDS:
                for panic_buys in (True, False):
                    r = price(panel, schedule(panel, series, threshold, panic_buys), cost_bps)
                    r.update({"basket": basket, "z": threshold, "panic_buys": panic_buys, "window": name})
                    rows.append(r)
    return rows, meta


def report(rows: list, meta: dict, cost_bps: float) -> None:
    print(f"attention bar · {SLEEVE} against DCA into {SLEEVE}, and against DCA into {BENCH} · "
          f"{cost_bps} bps a leg")
    for basket, (ac1, n_eff, live) in meta.items():
        print(f"  {basket:9} basket z: lag-1 autocorrelation {ac1:+.2f} -> about {n_eff:.0f} independent "
              f"bets in {live} scored months")
    print(f"  a rule is only interesting above ${NOISE_FLOOR:.0f}/mo, the gap round 15 measured between two "
          f"funds on one index\n")
    graded = grade(rows)
    print(f"  {'cell':34} {'$/mo vs DCA':>11} {'vs VOO':>9} {'exposure':>9} {'turnover':>9} "
          f"{'worst dip':>9} {'fees':>8}")
    print("  " + "-" * 88)
    for basket in ("financial", "control"):
        for threshold in THRESHOLDS:
            for panic_buys in (True, False):
                cells = {r["window"]: r for r in rows if r["basket"] == basket and r["z"] == threshold
                         and r["panic_buys"] is panic_buys}
                if len(cells) != len(WINDOWS):
                    raise ValueError(f"{len(cells)} windows for one cell; a grid with a hole is not a grid")
                full = cells[WINDOWS[0][0]]
                positive = sum(1 for c in cells.values() if c["gap"] > 0)
                verdict_cell = graded.get((basket, threshold, panic_buys), "fail")
                tag = (f"{basket:9} z>={threshold:<4} {'panic buys' if panic_buys else 'panic exits'}"
                       f"  ({positive}/{len(cells)} windows up)")
                print(f"  {tag:34} {full['$/mo']:>+11,.0f} {full['$/mo_vs_bench']:>+9,.0f} "
                      f"{full['on']:>8.0%} {full['turnover']:>8.2f}x {full['worst']:>8.1%} "
                      f"${full['fees']:>7,.0f}  {verdict_cell}")
                for window in [w[0] for w in WINDOWS][1:]:
                    c = cells[window]
                    print(f"      {window:30} {c['$/mo']:>+11,.0f} {c['$/mo_vs_bench']:>+9,.0f} "
                          f"{c['on']:>8.0%} {c['turnover']:>8.2f}x {c['worst']:>8.1%} ${c['fees']:>7,.0f}")


def grade(rows: list) -> dict:
    """One cell of the grid, graded once, by the rule the docstring promises.

    The first version of this logic lived in two places — a per-cell label and a bottom-line verdict — and
    disagreed with itself, which is how a table ends up printing "clear" above a sentence that says no cell
    cleared. There is now one grader and both read it. Its first clause is the one that can lose the
    argument: the same rule, the same threshold, the same windows, run on six articles about rocks and
    water. Anything that general attention reproduces, this file reports as general attention.
    """

    index = {(r["basket"], r["z"], r["panic_buys"], r["window"]): r for r in rows}
    windows = [w[0] for w in WINDOWS]
    out = {}
    for basket in ("financial", "control"):
        for threshold in THRESHOLDS:
            for panic_buys in (True, False):
                mine = [index[(basket, threshold, panic_buys, w)] for w in windows]
                reasons = []
                if basket == "financial":
                    ctl = [index[("control", threshold, panic_buys, w)] for w in windows]
                    rev = [index[("financial", threshold, not panic_buys, w)] for w in windows]
                    if any(c["gap"] >= f["gap"] for f, c in zip(mine, ctl)):
                        return_into = "REFUTED by its own control"
                    elif not all(c["gap"] > 0 for c in mine):
                        return_into = "fail: not positive in every window"
                    elif not all(m["gap"] > r["gap"] for m, r in zip(mine, rev)):
                        return_into = "fail: the reversal is better"
                    elif min(abs(c["$/mo"]) for c in mine) <= NOISE_FLOOR:
                        return_into = "fail: inside the noise floor"
                    else:
                        return_into = "CLEARS the pre-registered rule"
                    out[(basket, threshold, panic_buys)] = return_into
                else:
                    out[(basket, threshold, panic_buys)] = "(control, cannot pass by construction)"
    return out


def verdict(rows: list) -> str:
    """The rule as pre-registered, which means including the clause that can lose the argument.

    The first version of this function graded the financial basket against its own reversal and its own
    materiality and printed PASS, while the control basket in the same row of the grid was making more money
    than it was. A pass rule that omits its own refutation is not a pass rule; the clause "not reproducible
    by six articles about rocks and water" is now the first thing checked, not a footnote under the table.
    """

    graded = grade(rows)
    winners = [k for k, v in graded.items() if v.startswith("CLEARS")]
    refuted = [k for k, v in graded.items() if v.startswith("REFUTED")]
    index = {(r["basket"], r["z"], r["panic_buys"], r["window"]): r for r in rows}
    lines = [f"  z>={t} {'panic buys' if b else 'panic exits'} CLEARS the rule" for _b, t, b in winners] \
        or ["  no cell on the financial basket clears the bar stated before the join"]
    if refuted:
        gaps = []
        for _basket, threshold, panic_buys in refuted:
            gaps += [index[("control", threshold, panic_buys, w)]["$/mo"]
                     - index[("financial", threshold, panic_buys, w)]["$/mo"] for w in [x[0] for x in WINDOWS]]
        lines.append(f"  {len(refuted)} of {len(THRESHOLDS) * 2} directions were refuted by the control "
                     f"basket at the same threshold on the same windows; its largest lead was "
                     f"${max(gaps):,.0f}/mo.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cost-bps", type=float, default=2.0)
    args = ap.parse_args()
    rows, meta = scan(args.cost_bps)
    report(rows, meta, args.cost_bps)
    print("\nPass rule, fixed before the join: positive versus DCA in every window, better than the same rule\n"
          "run backwards, above $25/mo, and — the clause that decides this file — not reproducible by six\n"
          "articles about rocks and water at the same threshold on the same windows.\n")
    print(verdict(rows))
    fin_best = max((r["$/mo"] for r in rows if r["basket"] == "financial"))
    ctl_best = max((r["$/mo"] for r in rows if r["basket"] == "control"))
    fin_worst = min((r["$/mo"] for r in rows if r["basket"] == "financial"))
    print(f"\nfinancial basket spans {fin_worst:+,.0f} to {fin_best:+,.0f} /mo across the grid; the control "
          f"basket's best is {ctl_best:+,.0f}/mo.")
    print("If the control basket's best is a large positive, this file has measured Wikipedia's traffic "
          "growth\nand not the market, whatever the financial basket says.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
