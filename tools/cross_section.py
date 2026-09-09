"""The rotation bar: what a cross-sectional rule must clear, priced against doing nothing twice.

Run: .venv/bin/python tools/cross_section.py [--cost-bps 2.0] [--months-skip 1] [--lookback 252]

Rounds 3, 13 and 14 closed directional timing on a single sleeve from both directions: at a weekly
clock the filter needs 63–98% of its calls right and shows 41–83%, and at a daily clock the bar falls
a couple of points and the money falls further, because a faster clock supplies *events* rather than
*independent evidence*. Both rounds named the same escape: a rule needs many roughly independent bets,
and one autocorrelated price series cannot supply them. This archive contains twelve sleeves, which is
the only place in the repository where that claim can be tested rather than asserted — a rotation is a
sequence of comparisons between sleeves, so it can make a decision every month without re-asking the
same asset the same question.

It is also the rule family that finally matches the goal as stated. "Beat VOO and QQQ" is not a
directional claim about the market; it is a claim about *which* sleeve to hold this month, which is
exactly what a cross-sectional rule answers, and a monthly rotation is short-term trading in the only
sense a retail account can actually execute.

Two comparators are printed because two questions are being asked, and neither can grade the other
(P0's dominance rule and the goal's own stated bar):

  * **`equal-weight all` is the dominance test (P0).** A rotation that cannot beat buying every sleeve
    it is allowed to name, on the same deposits and the same calendar, is paying for the privilege of
    ranking them. This is the naive version of itself, and the P0 rule says it loses to that or it is
    `Redundant`, whatever it beats afterwards.
  * **DCA into VOO is the goal's own bar.** The alternative to a rotation in this account is not an
    equal-weight basket of twelve funds, it is the boring thing that would have been bought instead.
    A rule can clear the first and still fail the second, and it has to clear both.

The required accuracy is then solved on the rotation's own calendar rather than counted. `bar` is the
fraction of rebalances at which the shadow rotation must hold the ranking's own top-K rather than fall
back to the equal-weight basket, for its account to reach what plain DCA into VOO reaches. Money is
linear in that fraction by construction — a month is either the pick or the basket, so the account is a
blend of two fixed books — which makes the solve exact, not simulated. `hits` beside it is the realised
fraction of rebalances where the chosen basket did beat the basket it replaced; it is printed as a
*wedge*, not as evidence, because round 13 established that a count which reverses sign under reversal
cannot rank two books that the money ranks. The reversed control is therefore printed with the same
bar and the same wedge on purpose: if the ranking's count is worth something, the reversal's count must
look better and its money must look worse, and if both come out symmetric the ranking is carrying
nothing.

Four things this file cannot do, stated where they can be misread:

  * **The universe is survivorship-biased and so is every number in it.** All nine sleeves are here
    because someone in 2026 could name them and buy them. The panel runs on the SPY calendar and each
    sleeve is unavailable before its own listing — the alternative, keeping only month-ends where every
    sleeve trades, would start the sample in September 2010 because VOO listed then and silently drop
    2007 to 2009 out of a momentum test. What is scored begins 2007-03-30, thirteen months of warm-up
    after the youngest sleeve listed, and it is twenty years of the most-selected cross-section in the
    world. A rotation result here is an upper bound, not an estimate.
  * **Nine names are not nine bets.** The header of every report prints the average pairwise monthly
    correlation and the effective sleeve count it implies, which over this record is +0.32 and **2.5 of
    9** — and 2.0 in the one window where the rotation looks good. A top-3 holding SPY, IWM and QQQ has
    made one bet three times. Read `n_eff` before believing any decision count in this file.
  * **Rebalancing at the month's last shared session on a close-to-close total return is the cheapest
    execution in the world.** `tr_close` is dividend-adjusted close, the cost is a flat per-leg toll,
    and nothing here models the spread of an odd-hour fill, the tax bill of selling a winner in a
    taxable account, or the fact that DBC and IEF do not trade at the SPY's spread.
  * **A monthly cadence is a choice, and a cheap one.** The lookback and the skip are round-3-style
    defaults (twelve months, skip the last one, the only momentum window with a literature behind it);
    the flags change them, and changing them is a new scan, not a new finding.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import funded_frame  # noqa: E402  (the per-month convention, in one place)
from boring_alpha.data.csv_loader import load_csv_market_data  # noqa: E402

SNAPSHOT = ROOT / "data" / "current" / "market_daily.csv"
CASH_FILE = ROOT / "data" / "current" / "cash_daily.csv"
OPENING, MONTHLY = 5_000.0, 500.0

# Expense ratios, per sleeve, fetched rather than typed: nine of these twelve sleeves had no ratio
# pinned anywhere in this repository, and a cross-sectional test that charges the same fee to every
# sleeve is not testing a rotation, it is testing an assumption. As of 2026-09-06: five pinned by
# `withdrawal_capacity` (SPY/VOO/VTI/ITOT/QQQ), seven from the issuers' published ratios —
# IWM 0.19% (iShares), EFA 0.32% (iShares), EEM 0.72% (iShares), TLT 0.15% (iShares), IEF 0.15%
# (iShares), GLD 0.40% (SPDR), DBC 0.84% (Invesco). The spread between the cheapest and the
# dearest sleeve here is 72 bps a year, which is more than most timing edges this repo has measured,
# and it is the reason an equal-weight basket is not a free comparator either.
#: Imported at the point of use rather than at the top: this file sets up its module path above, and a fee table is a
#: tool-local module, so the import belongs where the path is already real.
import fund_fees                                # noqa: E402

#: Round 94: this file had the most accurate copy of the four in the repository, and was still three basis points off on
#: DBC (0.87 against a published 0.84) after six years of being right about everything else. The ratios now come from
#: `fund_fees.py`, which carries the source and the date for each one.
EXPENSE = dict(fund_fees.FEES)

# The ranked set, after three exclusions that each cost something. VTI and ITOT are the same bet as
# SPY at the same fee, and a top-3 that can hold all three has made one bet three times, so they are
# out. VOO is out of the *ranking* because it is the bar, and a bar does not compete with what it
# grades. Nine sleeves across four asset classes are left, and their shared history begins with the
# youngest of them, DBC in February 2006.
UNIVERSE = ("SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC")
BENCH = "VOO"                    # the goal's own bar, as the user stated it
BENCH_FROM = date(2010, 9, 1)    # ...which did not exist until September 2010
BENCH_EARLY = "SPY"              # ...and this is the same index, 6.45 bps a year dearer, that did
LOOKBACK, SKIP = 12, 1
TOP_K = (1, 2, 3)
COSTS = (0.3, 2.0, 5.0)          # one-way bps: a rotation's turnover is its own worst enemy
COIN_BOOKS = 25
SEED = 20_260_907
WINDOWS = (
    # The shared panel opens when the youngest sleeve lists (DBC, 2006-02-06) and the first thirteen
    # months are warm-up, so the scoreable window starts in March 2007, not February 2006. Naming the
    # window by the date the archive begins would have been a label claiming twenty years of scored
    # history on nineteen.
    ("shared 2007-03..2026-08", date(2007, 3, 1), date(2026, 9, 30)),
    ("seen A 2007-06..2017-12", date(2007, 6, 1), date(2017, 12, 31)),
    ("seen B 2018..2021", date(2018, 1, 1), date(2021, 12, 31)),
    ("recent 2022..2026", date(2022, 1, 1), date(2026, 9, 30)),
)


@dataclass
class Panel:
    """Month-end total returns for every sleeve, on one reference calendar, with availability kept.

    `avail` is not decoration. The alternative — keeping only month-ends where *every* sleeve trades —
    makes the shared sample begin on the youngest sleeve's listing date, which in this archive means
    throwing away 2007, 2008 and 2009 because VOO listed in September 2010. A cross-sectional test that
    quietly drops the worst crash in its sample is not a test of anything.
    """

    months: list                       # month-end dates, on the reference calendar
    first: int = 1                     # index the scored account starts at, after the warm-up
    ret: dict = field(default_factory=dict)      # symbol -> [return per month]
    avail: dict = field(default_factory=dict)    # symbol -> [bool: listed and trading that month]
    age: dict = field(default_factory=dict)      # symbol -> [months since this sleeve's first month-end]
    cash: list = field(default_factory=list)
    expense: dict = field(default_factory=dict)

    def eligible(self, month: int, need: int) -> list:
        return [s for s in UNIVERSE if self.avail[s][month] and self.age[s][month] >= need + 1]


def build_panel(symbols=UNIVERSE, lookback_months: int = LOOKBACK,
                start: date | None = None, end: date | None = None, warmup: int = 0,
                reference: str = "SPY") -> Panel:
    """Monthly total returns at each month's last session, on the reference sleeve's calendar.

    A sleeve is available from its own first month-end on; before that it does not exist and cannot be
    held, and the account's universe simply had fewer names in it. Deposits and returns follow the
    convention every funded tool in this repo uses: the month's deposit arrives at the start of the
    month and gets that month's return.
    """

    data = load_csv_market_data(SNAPSHOT, CASH_FILE)
    floor = start if start is None else back_months(start, warmup)
    ends = {}
    for d in data.dates:
        if reference not in data.by_date[d]:
            continue
        if d < floor or (end and d > end):
            continue
        ends[(d.year, d.month)] = d                       # last reference session of each month
    months = [ends[k] for k in sorted(ends)]
    if len(months) < lookback_months + 14:
        raise ValueError(f"{len(months)} month-ends on the {reference} calendar in {start}..{end}; a "
                         f"rotation needs {lookback_months + 13} before it can rank anything, and an "
                         f"empty panel printed as a zero is how a null result passes as a result")
    first = 0 if start is None else next((i for i, d in enumerate(months) if d >= start), len(months))
    if first < lookback_months + 1:
        raise ValueError(f"the window opens at {start} with only {first} months of archive behind it; "
                         f"ranking needs {lookback_months + 1}, so this window would be solved on a "
                         f"warm-up it does not have")

    panel = Panel(months=months, first=first, cash=[],
                  expense={s: EXPENSE[s] for s in set(symbols) | {BENCH, BENCH_EARLY}})
    panel.cash.append(0.0)
    for i in range(1, len(months)):
        prior, now = months[i - 1], months[i]
        panel.cash.append(math.prod(data.cash_factors[x] for x in data.dates
                                    if prior < x <= now) - 1.0)
    want = list(set(symbols) | {BENCH, BENCH_EARLY})
    for s in want:
        last, seen = None, None
        rets, avail, ages = [], [], []
        for i, d in enumerate(months):
            if s in data.by_date[d]:
                close = data.by_date[d][s].close
                rets.append(0.0 if last is None else close / last - 1.0)
                last = close
                seen = i if seen is None else seen
                avail.append(True)
                ages.append(i - seen + 1)
            else:
                rets.append(0.0 if last is None else 1.0 - 1.0)
                avail.append(False)
                ages.append(0 if seen is None else i - seen)
        panel.ret[s], panel.avail[s], panel.age[s] = rets, avail, ages
    return panel


def back_months(d: date, n: int) -> date:
    """`d` moved back `n` calendar months, clamped to the first of that month."""

    total = d.year * 12 + (d.month - 1) - n
    return date(total // 12, total % 12 + 1, 1)


def score_momentum(panel: Panel, month: int, lookback: int, skip: int, reverse: bool = False) -> list:
    """Rank the eligible sleeves on trailing total return, oldest month first. Nothing future reaches it."""

    need = lookback + skip
    out = []
    for s in UNIVERSE:
        if month < need or not panel.avail[s][month] or panel.age[s][month] < need + 1:
            continue
        # Compounded over `lookback` months whose last `skip` are dropped, using returns earned up to
        # and including month `month - skip - 1`: the decision at the close of month `month - 1` may
        # not see month `month`, which is the month the resulting weights are in force for.
        window = panel.ret[s][month - need + 1: month - skip]
        out.append((math.prod(1.0 + r for r in window) - 1.0, s))
    out.sort(key=lambda t: (t[0], t[1]))
    ranked = [s for _g, s in out]
    return list(reversed(ranked)) if not reverse else ranked


def weights_for(panel: Panel, month: int, k: int, lookback: int, skip: int,
                reverse: bool = False) -> dict:
    ranked = score_momentum(panel, month, lookback, skip, reverse)
    if not ranked:
        return {}
    take = ranked[:max(1, min(k, len(ranked)))]
    return {s: 1.0 / len(take) for s in take}


def bench_weights(panel: Panel, month: int) -> dict:
    """The goal's own bar, switched to the month it became buyable.

    A test that "beats VOO" over twenty years has to say what the money held before VOO existed. It
    would have held SPY: the same index, 6.45 bps a year dearer. That is a real cost of the choice, so
    it is printed as a row of its own rather than folded into a splice nobody can see.
    """

    return {(BENCH if (panel.months[month] >= BENCH_FROM and panel.avail[BENCH][month])
             else BENCH_EARLY): 1.0}


def equal_weights(panel: Panel, month: int) -> dict:
    eligible = panel.eligible(month, LOOKBACK + SKIP)
    return {s: 1.0 / len(eligible) for s in eligible} if eligible else {}


def run_book(panel: Panel, weights: list[dict], cost_bps: float, opening: float = OPENING,
             monthly: float = MONTHLY, first: int | None = None) -> dict:
    """The funded simulator for a sleeve-weight schedule. Deposits monthly, one-way toll on turnover.

    A month's return is the weighted return of the sleeves held through it, net of each sleeve's own
    expense ratio, with whatever weight is not in a sleeve earning the archive's cash factor. A switch
    is charged per leg, per unit, on the weights as they move.
    """

    if len(weights) != len(panel.months):
        raise ValueError(f"{len(weights)} weight rows against {len(panel.months)} month-ends: a "
                         f"schedule is indexed by month, and a short list silently shifts every "
                         f"decision into the month after the one that made it")
    value, paid, fees, prev = opening, opening, 0.0, {}
    path, worst, churn_total = [opening], 0.0, 0.0
    for i in range(first if first is not None else panel.first, len(panel.months)):
        w = weights[i] or prev          # a month with no ranking holds what it already held
        held = [s for s in w if not panel.avail[s][i]]
        if held:
            raise ValueError(f"{','.join(held)} is held at {panel.months[i]} before it listed; a panel "
                             f"that lets a rotation hold a fund that does not exist yet is the worst "
                             f"look-ahead in this repository because it is invisible")
        churn = sum(abs(w.get(s, 0.0) - prev.get(s, 0.0)) for s in set(w) | set(prev))
        churn_total += churn
        cost = churn * cost_bps / 1e4 * value
        fees += cost
        gross = sum(weight * (panel.ret[s][i] - (1.0 + panel.ret[s][i]) * panel.expense[s] / 12.0)
                    for s, weight in w.items())
        gross += (1.0 - sum(w.values())) * panel.cash[i]
        value = value * (1.0 + gross) - cost + monthly
        paid += monthly
        path.append(value)
        worst = min(worst, value / max(max(path[:-1]), 1e-9) - 1.0)
        prev = w
    months = len(panel.months) - (first if first is not None else panel.first)
    return {"ending": value, "paid": paid, "fees": fees, "path": path, "worst": worst,
            "months": months, "turnover": churn_total / max(months / 12.0, 1.0),
            "started": panel.months[first if first is not None else panel.first]}


def shadow_book(panel: Panel, weights: list[dict], p: float, cost_bps: float,
                fallback: list[dict], seed: int = SEED, draws: int = 1) -> float:
    """Hold the ranking's pick with probability p and the fallback basket otherwise, at this calendar.

    Returns the ending balance. With `draws` the draws are averaged, which is only ever needed for a
    control book; a *required* accuracy is solved at its expectation, which is exact because the
    account is affine in p: each month contributes p·pick + (1−p)·basket and nothing else moves.
    """

    if draws <= 1:
        return blend_ending(panel, weights, fallback, p, cost_bps)
    rng = random.Random(seed)
    total = 0.0
    for _ in range(draws):
        mixed = []
        for i in range(len(weights)):
            if weights[i] and rng.random() >= p:
                mixed.append(fallback[i])
            else:
                mixed.append(weights[i])
        total += run_book(panel, mixed, cost_bps)["ending"]
    return total / draws


def blend_ending(panel: Panel, weights: list[dict], fallback: list[dict], p: float,
                 cost_bps: float) -> float:
    """The p-blend of two fixed schedules, at the expectation. Linear in p by construction."""

    lo = run_book(panel, fallback, cost_bps)["ending"]
    if abs(p) < 1e-15:
        return lo
    if p >= 1.0 - 1e-15:
        return run_book(panel, weights, cost_bps)["ending"]
    hi = run_book(panel, weights, cost_bps)["ending"]
    return lo + p * (hi - lo)


def solve_blend(panel: Panel, weights: list[dict], fallback: list[dict], target: float,
                cost_bps: float) -> float | None:
    """The blend fraction at which the shadow rotation reaches `target`. Exact, because it is linear."""

    lo = run_book(panel, fallback, cost_bps)["ending"]
    hi = run_book(panel, weights, cost_bps)["ending"]
    if abs(hi - lo) < 1e-9:
        return None if abs(target - lo) > 1e-9 else 1.0
    p = (target - lo) / (hi - lo)
    if p > 1.0:
        return None                      # even holding the pick every month falls short
    if p < 0.0:
        # The pick book sits on the wrong side of its own fallback, so blending *more* of the ranking
        # moves the account away from the target and no accuracy on this calendar reaches it. Printed
        # as a bare 0.0% this row would read as a cleared bar, which is the bug this repo has four
        # entries in the standing rules about.
        return None
    return p


def hit_rate(panel: Panel, weights: list[dict], fallback: list[dict], bench: str) -> tuple:
    """Share of rebalances where the pick beat the fallback, and the same against the goal's bar.

    Counted on the *month the weights were in force*, net of nothing — this is the statistic round 13
    discredited, kept only so the wedge between it and the money can be read directly.
    """

    right = replaced = 0
    for i in range(panel.first, len(panel.months)):
        if not weights[i] or not fallback[i]:
            continue
        pick = sum(wt * panel.ret[s][i] for s, wt in weights[i].items())
        base = sum(wt * panel.ret[s][i] for s, wt in fallback[i].items())
        if pick > base:
            right += 1
        replaced += 1
    return (right / replaced if replaced else None, replaced)


def effective_n(panel: Panel, start: int = 0) -> tuple:
    """Average pairwise monthly correlation, and the independent-sleeve count it implies."""

    months = slice(start, None)
    series = {s: panel.ret[s][months] for s in UNIVERSE}
    means = {s: sum(v) / len(v) for s, v in series.items()}
    cov, pairs, total = {}, [], 0.0
    for s, v in series.items():
        cov[s] = math.sqrt(sum((x - means[s]) ** 2 for x in v)) or 1e-12
    names = list(UNIVERSE)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            x, y = names[a], names[b]
            both = [i for i in range(len(series[x])) if panel.avail[x][i + start] and panel.avail[y][i + start]]
            if len(both) < 24:
                continue
            mx = sum(series[x][i] for i in both) / len(both)
            my = sum(series[y][i] for i in both) / len(both)
            sx = math.sqrt(sum((series[x][i] - mx) ** 2 for i in both)) or 1e-12
            sy = math.sqrt(sum((series[y][i] - my) ** 2 for i in both)) or 1e-12
            r = sum((series[x][i] - mx) * (series[y][i] - my) for i in both) / (sx * sy)
            total += r
            pairs.append((r, x, y))
    if not pairs:
        return 0.0, 1.0, [(0.0, "n/a", "n/a")], [(0.0, "n/a", "n/a")]
    rho = total / len(pairs)
    n_eff = len(names) / (1.0 + (len(names) - 1) * rho) if rho > -1 else 1.0
    pairs.sort(reverse=True)
    return rho, n_eff, pairs[:3], pairs[-2:]


def scan(panel: Panel, cost_bps: float, lookback: int, skip: int) -> list[dict]:
    months = len(panel.months)
    bench_w = [bench_weights(panel, i) for i in range(months)]
    spy_w = [{BENCH_EARLY: 1.0} for _ in range(months)]
    spy_book = run_book(panel, spy_w, cost_bps)
    ew = [equal_weights(panel, i) for i in range(months)]
    bench = run_book(panel, bench_w, cost_bps)
    ew_book = run_book(panel, ew, cost_bps)
    rows = []
    for name, weights in (
            ("always SPY", spy_w),
            ("index DCA SPY>VOO", bench_w),
            ("equal-weight all", ew),
            ("top-1 momentum", [weights_for(panel, i, 1, lookback, skip) for i in range(months)]),
            ("top-2 momentum", [weights_for(panel, i, 2, lookback, skip) for i in range(months)]),
            ("top-3 momentum", [weights_for(panel, i, 3, lookback, skip) for i in range(months)]),
            ("top-2 reversed", [weights_for(panel, i, 2, lookback, skip, True) for i in range(months)]),
    ):
        book = run_book(panel, weights, cost_bps)
        hits, called = hit_rate(panel, weights, ew, BENCH)
        bar = None if name in ("always SPY", "index DCA SPY>VOO") else solve_blend(
            panel, weights, ew, bench["ending"], cost_bps)
        rows.append({"rule": name, "ending": book["ending"], "fees": book["fees"],
                     "worst": book["worst"], "turnover": book["turnover"],
                     "vs_ew": book["ending"] - ew_book["ending"],
                     "vs_bench": book["ending"] - bench["ending"],
                     "vs_spy": book["ending"] - spy_book["ending"],
                     "hits": hits, "called": called, "bar": bar,
                     "months": book["months"]})
    for row in rows:
        row["$/mo vs index"] = funded_frame.per_month_equivalent(
            row["vs_bench"], 0.07, row["months"])
        row["$/mo vs EW"] = funded_frame.per_month_equivalent(
            row["vs_ew"], 0.07, row["months"])
        row["wedge"] = None if (row["hits"] is None or row["bar"] is None) else row["hits"] - row["bar"]
    return rows


def render(rows: list[dict]) -> str:
    head = (f"{'rule':18s} {'ending':>11} {'$/mo vs EW':>11} {'$/mo vs index':>13} "
            f"{'turnover':>9} {'fees':>8} {'worst':>7} {'hits':>6} {'bar':>6} {'wedge':>6}")
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['rule']:18s} {r['ending']:>11,.0f} {r['$/mo vs EW']:>+11,.0f} "
            f"{r['$/mo vs index']:>+13,.0f} "
            f"{'' if r['turnover'] is None else format(r['turnover'], '.1f') + 'x':>9} "
            f"{r['fees']:>8,.0f} {r['worst'] * 100:>6.1f}% "
            f"{'—' if r['hits'] is None or r['rule'] == 'equal-weight all' else format(r['hits'] * 100, '.1f') + '%':>6} "
            f"{'no bar' if r['bar'] is None else format(r['bar'] * 100, '.1f') + '%':>6} "
            f"{'—' if r['wedge'] is None else format(r['wedge'] * 100, '+.0f') + 'pp':>6}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cost-bps", type=float, default=2.0)
    ap.add_argument("--lookback", type=int, default=LOOKBACK, help="trailing months, default 12")
    ap.add_argument("--months-skip", type=int, default=SKIP, help="months skipped at the end, default 1")
    ap.add_argument("--window", default=None, choices=[w[0] for w in WINDOWS])
    args = ap.parse_args()

    windows = WINDOWS if not args.window else [w for w in WINDOWS if w[0] == args.window]
    print(f"cross-sectional rotation · universe {len(UNIVERSE)} sleeves · one-way cost "
          f"{args.cost_bps:g} bps · {args.lookback}-month lookback skipping "
          f"{args.months_skip} · bar solved against DCA:{BENCH}, dominance against equal-weight\n")
    tally = []
    for label, lo, hi in windows:
        panel = build_panel(start=lo, end=hi, warmup=LOOKBACK + SKIP + 2)
        if len(panel.months) - panel.first < 14:
            print(f"=== {label}: skipped, only {len(panel.months)} month-ends\n")
            continue
        rows = scan(panel, args.cost_bps, args.lookback, args.months_skip)
        rho, n_eff, hi_pairs, lo_pairs = effective_n(panel, panel.first)
        print(f"=== {label} · {len(panel.months) - panel.first} scored months from "
              f"{panel.months[panel.first]} · average pairwise monthly "
              f"correlation {rho:+.2f} · n_eff {n_eff:.1f} of {len(UNIVERSE)}")
        print(f"    most correlated pair: {hi_pairs[0][1]}/{hi_pairs[0][2]} at {hi_pairs[0][0]:+.2f}"
              f"; least: {lo_pairs[-1][1]}/{lo_pairs[-1][2]} at {lo_pairs[-1][0]:+.2f}")
        print(render(rows))
        print()
        tally += [dict(r, window=label) for r in rows]

    rotation = [r for r in tally if "momentum" in r["rule"]]
    win = [r for r in rotation if r["vs_ew"] > 0 and r["vs_bench"] > 0]
    print(f"{len(win)} of {len(rotation)} rotation windows beat both the equal-weight basket and "
          f"the index-fund DCA at {args.cost_bps:g} bps one-way.")
    for r in win:
        print(f"  clears both: {r['window']} — {r['rule']}, {r['$/mo vs index']:+,.0f}/mo against the "
              f"goal's bar and {r['$/mo vs EW']:+,.0f}/mo against its own naive version")
    print("\n  Read these numbers as an upper bound and not an estimate. Every sleeve here is one a")
    print("  person in 2026 could name and buy, which is a selection made after the fact and the whole")
    print("  table is conditioned on it. The $/mo columns discount at 7%, the comparator's own standing")
    print("  stand-in, and a gap worth less than about $25 a month is inside the noise of which nearly-")
    print("  identical fund this file happened to call the bar. Close-to-close at a flat toll is the")
    print("  cheapest execution in the world: no odd-hour spread, no realised-gain tax bill, no DBC bid.")
    reversals = [r for r in tally if r["rule"] == "top-2 reversed"]
    forward = [r for r in tally if r["rule"] == "top-2 momentum"]
    worse = sum(1 for a, b in zip(forward, reversals) if a["vs_bench"] < b["vs_bench"])
    print(f"the reversed ranking out-earned the forward one in {worse} of {len(reversals)} windows"
          f"{' — the ranking is not carrying the money' if worse else ''}.")


if __name__ == "__main__":
    main()
