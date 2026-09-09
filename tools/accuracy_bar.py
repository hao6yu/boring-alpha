"""Every rule's own bar: what accuracy a signal needs, given how *that* rule trades.

Run: .venv/bin/python tools/accuracy_bar.py [--sleeve SPY] [--window full..] [--cost-bps 2.0]
         [--cadence 1|2|5] [--reps 400] [--r3-expense]

Round 3 is the reason this repository stopped looking for a timing signal. It measured the accuracy a
weekly market/flat timer needs to beat plain DCA — 56% full window, 58% in every sub-window — then scored
the rules that actually exist here against that number and found fifteen of sixteen rule×window cells
short by 0.5 to 5.1 points. That table has been quoted ever since as the reason the search is pointless,
so this tool exists to audit the bar, which is the one input to a search nobody checks: if the bar is
wrong, "nothing here can work" is an artefact and not a finding.

Two features of round 3's model are properties of the model rather than of a timer, and both make a
slow rule's task look harder than it is.

1. **The bar's turnover is not the rule's turnover.** Round 3 holds skill constant by redrawing the
   held state *every week* (`chosen = better if rng.random() < accuracy else not better`) — clean as a
   way to fix accuracy, and also a timer that changes its mind about half of all weeks at any accuracy,
   paying two legs each time: 844 turns over 1,691 bars, which at the headline 2.0 bps per leg is a toll
   of roughly 1% a year charged to the bar and to no rule. The 200-session trend filter it was compared
   against turns 107 times on the same window, one bar in sixteen. Round 3 computes a switch count,
   stores it in the same tuple, and never prints it, so nothing in the output says the comparison is
   between a filter that trades a hundred times and a coin that trades eight hundred and forty-four.

2. **The expense ratio is charged to the wrong leg.** `weekly_bars` compounds the cash state *net of
   the fund's expense ratio* and the equity state with no expense at all, while the module's own
   docstring says "expense ratio on the fund while long". There is no fund in cash to charge, and a
   real one in the fund. Going to cash is therefore billed ~9.5 bps/yr it would not pay and staying
   in is given ~9.5 bps/yr it would owe: over 33 years, a few points of terminal value moved from the
   timer to buy-and-hold, on a table read at the dearest cost for exactly this reason.

So each rule is scored against a bar solved on *its own* switch calendar. The construction is narrow
on purpose, so the comparison cannot drift:

  * A rule's answers are cut into **runs** — maximal stretches of bars holding the same state. Run
    boundaries are the rule's switches, so a shadow book that keeps the rule's calendar pays exactly
    what the rule pays, at any accuracy.
  * Accuracy is scored **per run**: over the stretch just held, was the leg held the leg that won?
    Weekly decisions that rarely change states are a slow rule and are scored as one.
  * The bar `p*` is the accuracy at which the shadow book's mean ending equals plain DCA's, solved by
    bisection on the same bars, deposits and switch dates. Skill against skill, cost against cost.
  * The fund leg pays the sleeve's real expense ratio; the cash leg pays nothing but earns the
    archive's own cash factors. `--r3-expense` runs the old placement, as an attribution column and
    not as a silent default.

Four controls are printed inside the table, because a bar that has never refused anything is
decoration. **Always long** is DCA in this frame, holds one run, and so must sit exactly on its own
bar: at `p = 1` the shadow book holds the leg that won, which is the leg it already held. Any gap on
that row is this file's accounting failing, not a result. **Always flat** must miss by a mile.
**Reversed trend** must score exactly `1 − trend` on the count, or the scoring is reading something other
than the rule — and it must *not* come out complementary on the skill, which is the finding rather than a
failure: 27.4% of runs right becomes 72.6% and the dollars move the wrong way relative to that, so the
count and the money are not the same measurement.
**Coin flip** is the attribution control — at a coin's turnover, this tool's bar should come
back near round 3's ~58%, which is how a reader can see how much of the old number was turnover and
how much was the toll.

`--cadence` moves the review frequency and nothing else: one decision every N sessions, with every
lookback still measured in **sessions**, so a 200-session filter is asked the same question on the same
Tuesday whether the clock between decisions is five sessions or one. Round 13's note ended by arguing
that this door must be wide — the bar falls as a rule makes more, smaller bets, to ~58% at a coin's
turnover — and round 14 measured it instead of admiring it: at one session per decision every bar did
fall, by 0.2 to 3.7 points, and 22 of 33 rows lost *more* money, median −$23 a month, because the extra
decisions are whipsaws and a two-year opinion graded weekly is not the same object as a two-week opinion
graded daily. The coin's own bar goes the other way from the intuition, too: 58.1% at 844 decisions,
56.6% at 4,228, while its losses rise from −$823 to −$1,065 a month, because the toll is charged per
switch and information is not. See [the cadence
grid](../docs/notes/2026-09-06-cadence-bar.md); `TheCadenceIsAFreedomNotAnEdge` pins the invariants that
make that reading trustworthy (5.0x the bars, the same deposits, the same signal on the same sessions).

Money is printed beside the gap, because a bar that does not predict the sign of the dollars is not a
bar. `$/mo vs DCA` prices the rule as itself — its states, its switches, no randomness — discounted
at the comparator's rate by the convention every other tool here uses. A positive gap with negative
dollars is a bug in this file, never a discovery, and the verdict column says `bar only, loses money`
rather than letting it read as a win.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import funded_frame  # noqa: E402  (the per-month convention, in one place)
import withdrawal_capacity as wc  # noqa: E402  (real expense ratios per sleeve)
from boring_alpha.data.csv_loader import load_csv_market_data  # noqa: E402
from boring_alpha.signals.voltarget import VolTargetPolicy  # noqa: E402

# The same archive every forward tool in this repository reads, via `withdrawal_capacity`: the
# 2026-09-04 snapshot happens to hold SPY alone, and a tool that pointed at it and asked for QQQ got
# an empty slice back and printed nothing, which is how a null result looks from the outside.
SNAPSHOT, CASH_FILE = wc.SNAPSHOT, wc.CASH_FILE
MIN_SESSIONS = 252                     # round 11's floor, inherited: less is not a window

OPENING = 5_000.0
MONTHLY = 500.0
WEEK = 5                       # sessions per bar, round 3's convention
MOM_UNIT = 5                   # a momentum lookback is stated in weeks of sessions, at any cadence
CADENCES = (1, 2, 5)           # sessions between decisions: what `--cadence` may be set to
REPS = 400
ENUMERATE_MAX = 14
SEED = 20_260_906              # fixed, so a bar is reproducible to the point
COIN_BOOKS = 25
IRR_STANDIN = 0.07             # only the discount rate for $/mo; every tool here uses one
CONTROLS = ("always long", "always flat", "coin flip", "reversed 126-trend")

SLEEVES = ("SPY", "QQQ", "VTI")
COSTS = (0.3, 1.0, 2.0)        # one-way bps: round 3's grid, so the two tables read together

WINDOWS = {
    "full 1993..2026": (date(1993, 1, 1), date(2026, 9, 30)),
    "seen A 2007-06..2017-12": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B 2018..2021": (date(2018, 1, 1), date(2021, 12, 31)),
    "recent 2022..2026": (date(2022, 1, 1), date(2026, 9, 30)),
}

GATE = VolTargetPolicy(target_vol=0.15, vol_window=21, trend_window=200, min_weight=0.30,
                       max_weight=1.30, review_every=5, rebalance_band=0.01)

# The two-state reading of every rule round 3 scored, the two slow classics it did not, the repo's
# own gate, and the four controls. A rule sees the closes up to and including the session its position
# is entered at, and answers True (hold the fund), False (hold cash) or None (no answer yet).
RULES = {
    "always long":        ("const", True),
    "always flat":        ("const", False),
    "coin flip":          ("coin", None),
    "200-session trend":  ("trend", 200),
    "126-session trend":  ("trend", 126),
    "50-session trend":   ("trend", 50),
    "dual MA 50/200":     ("dual", (50, 200)),
    "4-week momentum":    ("mom", 4),
    "13-week momentum":   ("mom", 13),
    "52-week momentum":   ("mom", 52),
    "candidate's gate":   ("gate", None),
    "reversed 126-trend": ("rev", 126),
}


def decide(kind: str, arg, closes: list[float]) -> bool | None:
    """One rule, one answer, from the closes it is allowed to see — nothing else reaches it.

    Lookbacks are in **sessions**, never in bars: a 200-session trend filter asked what to do on
    Tuesday answers the same question whether the calendar between decisions is one session or five.
    Only `--cadence` moves, and it moves the review frequency and the toll, not the signal.
    """

    if kind == "const":
        return arg
    if kind == "trend":
        if len(closes) < arg + 1:
            return None
        return closes[-1] > sum(closes[-arg:]) / arg
    if kind == "rev":
        answer = decide("trend", arg, closes)
        return None if answer is None else (not answer)
    if kind == "dual":
        fast, slow = arg
        if len(closes) < slow + 1:
            return None
        return sum(closes[-fast:]) / fast > sum(closes[-slow:]) / slow
    if kind == "mom":
        need = arg * MOM_UNIT
        if len(closes) < need + 1:
            return None
        return closes[-1] / closes[-1 - need] - 1.0 > 0.0
    if kind == "gate":
        window = closes[-300:]
        # The engine's own convention: same length as the closes, first element 0.0, never a None.
        returns = [0.0] + [window[i] / window[i - 1] - 1.0 for i in range(1, len(window))]
        weight = GATE.raw_weights(window, returns)[-1]
        return None if weight is None else weight > 0.0
    raise ValueError(f"unknown rule kind {kind!r}")


@dataclass
class Slice:
    """One sleeve, one window, cut into weekly bars, with the expense ratio put where it is owed."""

    symbol: str
    expense: float
    dates: list
    closes: list
    bars: list = field(default_factory=list)      # (fund, cash, deposit, entry) per bar
    cadence: int = WEEK                           # sessions between decisions

    def months(self, start: int) -> int:
        span = (self.dates[-1] - self.dates[self.bars[start][3]]).days
        return max(int(round(span / 365.2425 * 12)), 1)

    @property
    def drag(self) -> float:
        """The sleeve's expense ratio over one holding period, as a multiplier."""

        return (1.0 - self.expense) ** (self.cadence / 252.0)


def slice_of(symbol: str, bounds, r3_expense: bool = False, cadence: int = WEEK) -> Slice:
    """Weekly bars over the archive. Expense on the fund leg; `r3_expense` runs round 3's placement.

    Bars are `cadence` sessions wide, so the same slice can be solved at a weekly or a daily review.
    The default applies the sleeve's real expense ratio to the sessions the fund is held and charges
    nothing in cash. Round 3 did the opposite, and the flag exists so the attribution column is the
    same code path rather than a hand-restated number that can drift.
    """

    data = load_csv_market_data(SNAPSHOT, CASH_FILE)
    expense = wc.EXPENSE.get(symbol, 0.0)
    dates = [d for d in sorted(data.by_date)
             if symbol in data.by_date[d] and bounds[0] <= d <= bounds[1]]
    if len(dates) < MIN_SESSIONS:
        raise ValueError(f"{symbol} has {len(dates)} sessions in {bounds[0]}..{bounds[1]} of this "
                         f"archive; {MIN_SESSIONS} is the floor anything can be solved on, and "
                         f"silently returning an empty slice is how a sleeve that is not in the "
                         f"snapshot at all prints as a zero instead of an error")
    closes = [data.by_date[d][symbol].close for d in dates]
    slice_ = Slice(symbol, expense, dates, closes, cadence=cadence)
    drag = slice_.drag
    bars, month = [], None
    index = 1
    while index + cadence - 1 < len(dates):
        window = dates[index - 1:index + cadence]
        first, last = data.by_date[window[0]][symbol], data.by_date[window[-1]][symbol]
        gross = last.close / first.close - 1.0
        cash = math.prod(data.cash_factors[d] for d in window[1:]) - 1.0
        if r3_expense:
            fund, cash = gross, (1.0 + cash) * drag - 1.0
        else:
            fund, cash = (1.0 + gross) * drag - 1.0, cash
        deposit = 0.0
        stamp = window[-1]
        if month != (stamp.year, stamp.month):
            month = (stamp.year, stamp.month)
            deposit = MONTHLY
        bars.append((fund, cash, deposit, index - 1))
        index += cadence
    slice_.bars = bars
    return slice_


def answers(slice_: Slice, kind: str, arg, coin: random.Random | None) -> list:
    """One answer per bar, from the closes available at that bar's entry session. No look-ahead."""

    out = []
    for _fund, _cash, _deposit, entry in slice_.bars:
        if kind == "coin":
            out.append(None if entry < 1 else coin.random() < 0.5)
        else:
            out.append(decide(kind, arg, slice_.closes[:entry + 1]))
    return out


def runs_of(flags: list) -> list[tuple[int, int, bool]]:
    """Maximal same-state stretches: `(first bar, last bar, held)`. Boundaries are the switches."""

    runs: list[list] = []
    for bar, state in enumerate(flags):
        if state is None:
            continue
        if runs and runs[-1][2] == state and runs[-1][1] == bar - 1:
            runs[-1][1] = bar
        else:
            runs.append([bar, bar, state])
    return [tuple(r) for r in runs]


def span(slice_: Slice, first: int, last: int) -> tuple[float, float]:
    """Compounded (fund, cash) return over bars `first..last`, expense already inside each bar."""

    fund = cash = 1.0
    for bar in range(first, last + 1):
        fund *= 1.0 + slice_.bars[bar][0]
        cash *= 1.0 + slice_.bars[bar][1]
    return fund - 1.0, cash - 1.0


def price_rule(slice_: Slice, flags: list, cost: float, start: int) -> tuple[float, int]:
    """The rule as itself — its states, its switches, its costs. No randomness anywhere in it."""

    value, held, switches = OPENING, None, 0
    for bar in range(start, len(slice_.bars)):
        fund, cash, deposit, _entry = slice_.bars[bar]
        value += deposit
        state = flags[bar]
        if state is None:
            continue
        if state != held:                                      # opening the book costs a leg too,
            value -= value * 2.0 * cost                        # as it does in round 3's comparator
            switches += 1
        held = state
        value *= (1.0 + fund) if held else (1.0 + cash)
    return value, switches


def price_dca(slice_: Slice, cost: float, start: int) -> float:
    """Plain DCA on the same weekly grid from the same start session: the P0 comparator."""

    value, first = OPENING, True
    for bar in range(start, len(slice_.bars)):
        fund, _cash, deposit, _entry = slice_.bars[bar]
        value += deposit
        if first:
            value -= value * 2.0 * cost
            first = False
        value *= 1.0 + fund
    return value


def draws_for(runs, reps: int) -> list[list[float]]:
    """One fixed uniform per run per repetition, drawn once and reused at every accuracy.

    Fixed draws are what make the solve monotone: raising the accuracy can only turn a lost run into a
    won one, never the reverse, so the mean ending rises with accuracy and a bisection is legal.
    """

    return [[rng.random() for _ in runs] for rng in (random.Random(SEED + rep) for rep in range(reps))]


def affine(slice_: Slice, first: int, last: int, state: bool) -> tuple[float, float]:
    """One run as an affine map on the account: (multiplier, deposit annuity). Exact, not fitted.

    Inside a run the held state does not change, so the value at the run's end is the value at its
    start times a fixed multiplier, plus each week's deposit grown by the weeks that follow it. That
    is the same arithmetic the bar-by-bar loop does — the test that the two agree to the cent is the
    point — and it turns a shadow book from `O(bars)` work into `O(runs)` work, which is the only
    reason exact enumeration over 2^runs is affordable at all.
    """

    mult, add, first_deposit = 1.0, 0.0, 0.0
    for bar in range(first, last + 1):
        fund, cash, deposit, _entry = slice_.bars[bar]
        rate = (1.0 + fund) if state else (1.0 + cash)
        add = (add + deposit) * rate                 # the deposit arrives at the week's start, so it
        mult *= rate                                 # earns this week and every week after it
        if bar == first:
            first_deposit = deposit
    return mult, add, first_deposit


def run_affines(slice_: Slice, runs, cost: float) -> list:
    """Per run: (fund multiplier, fund annuity, cash multiplier, cash annuity) with the exit charge."""

    charge = 1.0 - 2.0 * cost                        # a switch costs two legs off the whole book
    out = []
    for first, last, _state in runs:
        fund_mult, fund_add, deposit = affine(slice_, first, last, True)
        cash_mult, cash_add, _ = affine(slice_, first, last, False)
        # The charge is levied when the book changes hands, which is before the run's own compounding
        # and before the weeks after the first deposit — so it falls on the opening balance and that
        # week's deposit only, and the annuity term must give back the part it was never charged on.
        out.append((fund_mult * charge, fund_add - fund_mult * deposit * (1.0 - charge),
                    cash_mult * charge, cash_add - cash_mult * deposit * (1.0 - charge)))
    return out


def shadow_book(slice_: Slice, runs, cost: float, start: int, draws: list,
                accuracy: float, spans: list, affines: list | None = None) -> float:
    """The rule's calendar with its correctness redrawn: same bars, deposits and switch dates.

    `draws[i] < accuracy` is the one test that decides run *i*, which is why fixed draws make the
    whole surface monotone: raising the accuracy can only convert a lost run into a won one.
    `exact_mean` abuses the same entry point with a synthetic draw vector to price one named subset.
    """

    table = affines if affines is not None else run_affines(slice_, runs, cost)
    value = OPENING
    for index, (first, last, _state) in enumerate(runs):
        fund_mult, fund_add, cash_mult, cash_add = table[index]
        won = spans[index][0] > spans[index][1]
        hold_fund = won if draws[index] < accuracy else (not won)
        mult, add = (fund_mult, fund_add) if hold_fund else (cash_mult, cash_add)
        value = value * mult + add
    return value


def realized(slice_: Slice, runs) -> tuple[float, float, float]:
    """(hit rate, share of runs long, standard error) — one trial per run, not per week."""

    if not runs:
        return 0.0, 0.0, 0.0
    hits = longs = 0
    for first, last, state in runs:
        fund, cash = span(slice_, first, last)
        hits += int(state == (fund > cash))
        longs += int(state)
    n = len(runs)
    p = hits / n
    # Add-two, add-four: a run-level proportion at 0% or 100% has no honest error otherwise, and the
    # degenerate one is the number that makes a one-run control look like a fifteen-sigma discovery.
    tilde = (hits + 2.0) / (n + 4.0)
    return p, longs / n, math.sqrt(tilde * (1.0 - tilde) / (n + 4.0))


def exact_mean(slice_: Slice, runs, cost: float, start: int, accuracy: float, spans: list,
               table: list) -> float:
    """E[ending] by enumerating every subset of won runs, weighted by its own probability.

    A rule with a handful of runs has a bar that Monte Carlo cannot resolve: with one run and 150
    draws the estimate moves in steps of 0.67%, and the first control row of the table is *exactly*
    the one-run case, whose gap must read as zero rather than as a rounding artefact. Sixteen runs
    or fewer are enumerated outright, and above that the law of large numbers does the job instead.
    """

    n = len(runs)
    total = 0.0
    for mask in range(1 << n):
        probability = 1.0
        for index in range(n):
            probability *= accuracy if (mask >> index) & 1 else (1.0 - accuracy)
        # Run i's sentinel: under 1.0 the book holds the leg that won, over it the leg that lost —
        # so one named subset is priced through the same entry point the Monte Carlo uses, and the
        # two cannot disagree about what a book costs.
        drawn = [0.5 if (mask >> i) & 1 else 1.5 for i in range(n)]
        total += probability * shadow_book(slice_, runs, cost, start, drawn, 1.0, spans, table)
    return total


def curve_for(slice_: Slice, runs, cost: float, start: int, draws: list, spans: list):
    """This rule's skill surface: expected ending as a function of accuracy, on its own calendar.

    One curve serves both readings the table needs, and they are different readings — see `implied`.
    The **bar** is where it crosses the comparator; the **skill** is where it crosses the rule's own
    realised ending.
    """

    table = run_affines(slice_, runs, cost)
    exact = len(runs) <= ENUMERATE_MAX

    def mean_at(accuracy: float) -> float:
        if exact:
            return exact_mean(slice_, runs, cost, start, accuracy, spans, table)
        return sum(shadow_book(slice_, runs, cost, start, d, accuracy, spans, table)
                   for d in draws) / len(draws)

    return mean_at


def invert(mean_at, target: float):
    """The smallest accuracy whose mean ending reaches `target`; None if the curve never gets there.

    The surface is monotone by construction — fixed draws, so raising the accuracy can only convert a
    lost run into a won one, never the reverse — which is what makes bisection legal rather than mere
    search. The slack is one float wide on purpose: the always-long row's shadow at p=1 is DCA to the
    last digit, and without the tolerance it lands one ulp under and prints "no bar" where the
    invariant demands "exact". A genuinely unreachable target is a per-cent shortfall, not a rounding.
    """

    ceiling = mean_at(1.0)
    if target > ceiling:
        return 1.0 if target <= ceiling * (1.0 + 1e-9) else None
    if mean_at(0.0) >= target:
        return 0.0
    low, high = 0.0, 1.0
    for _ in range(30):
        mid = (low + high) / 2.0
        if mean_at(mid) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def bar_of(mean_at, dca: float):
    """The accuracy this calendar needs to match plain DCA. None means no accuracy can."""

    return invert(mean_at, dca)


def implied(mean_at, ending: float):
    """The accuracy an i.i.d. timer would need, on this calendar, to end where this rule ended.

    Counting decisions is the wrong statistic, and the reversal control proves it. On SPY 1993-2026 the
    126-session trend filter is right on 27.4% of its runs and costs $502 a month, because the runs it
    loses are two-week whipsaws and the runs it wins are two-year trends; its exact mirror image, same
    bars and same switch dates with every position reversed, is right on 72.6% of runs and costs $929 a
    month. Same calendar, opposite counts, dollars moved by −$427 and neither near breakeven — so what
    settles a book is not how often a decision was right but *which* decisions it was right on, and a
    percentage of decisions cannot express that. The model is therefore inverted
    instead of the outcomes counted: the rule's own ending is solved back through the monotone surface
    that produced the bar, and the answer is the skill it actually showed, in the units the bar is
    quoted in.

    Sign agreement with the money column is then structural rather than hopeful: `skill > bar`
    exactly when `ending > dca`, because both are the same monotone curve read at two heights. A row
    where they disagree is a broken solve, and `TheIdentity` asserts the identity rather than
    trusting it. The distance between `skill` and the raw count of hits is the new number: it says
    whether a rule's wins sat in the runs that mattered or in the ones that cost a switch and nothing
    else.
    """

    return invert(mean_at, ending)


def audit(symbol: str, label: str, bounds, cost_bps: float, reps: int,
          r3_expense: bool = False, cadence: int = WEEK) -> list[dict]:
    """Every rule on one sleeve and one window, against its own bar and its own money."""

    slice_ = slice_of(symbol, bounds, r3_expense, cadence)
    if len(slice_.bars) < 120:
        return []
    rows = []
    for position, (name, (kind, arg)) in enumerate(RULES.items()):
        # A randomised control gets more than one book: one coin draw is 4.6 points wide, and a
        # control row that swings on its seed is not a control. Everything else is deterministic and
        # is priced once.
        books = ([answers(slice_, kind, arg, random.Random(SEED + 1000 + trial))
                  for trial in range(COIN_BOOKS)] if kind == "coin"
                 else [answers(slice_, kind, arg, None)])
        scored = [row for row in (score_book(slice_, flags, cost_bps / 10_000.0, reps) for flags in books)
                  if row]
        # `gap` is derived at the end from the averaged skill and bar, so the two can never be
        # averaged apart from it: an averaged gap would be a mean of differences over a difference of
        # means, which is a different number and the one the table reads.
        if not scored:
            continue
        row = {"sleeve": symbol, "window": label, "rule": name, "trials": len(scored)}
        for key in ("bars", "runs", "share", "hits", "ending", "dca", "switches"):
            row[key] = sum(r[key] for r in scored) / len(scored)
        solved = [r["bar"] for r in scored if r["bar"] is not None]
        row["bar"] = sum(solved) / len(solved) if len(solved) == len(scored) else None
        row["gap"] = None if row["bar"] is None else row["hits"] - row["bar"]
        row["skill"] = (sum(r["skill"] for r in scored) / len(scored)
                        if all(r["skill"] is not None for r in scored) else None)
        row["wedge"] = None if row["skill"] is None else row["skill"] - row["hits"]
        row["gap"] = None if row["bar"] is None else row["skill"] - row["bar"]
        row["se"], row["months"] = scored[0]["se"], scored[0]["months"]
        rows.append(row)
    return rows


def score_book(slice_: Slice, flags: list, cost: float, reps: int):
    """One rule, one book: its runs, its accuracy, its own bar and its own money, or None."""

    start = next((i for i, value in enumerate(flags) if value is not None), None)
    if start is None or len(slice_.bars) - start < 60:
        return None
    dca = price_dca(slice_, cost, start)
    # Re-index to absolute bars. `runs_of` restarts its counting at the slice it was handed, and a run
    # that says "bars 0..233" while being priced on bars 5..238 is a wrong number that still looks
    # exactly like a right one: the candidate's gate row was $2,160 short until this line existed.
    runs = [(a + start, b + start, state) for a, b, state in runs_of(flags[start:])]
    if not runs:
        return None
    spans = [span(slice_, a, b) for a, b, _state in runs]
    hits, share, se = realized(slice_, runs)
    ending, switches = price_rule(slice_, flags, cost, start)
    curve = curve_for(slice_, runs, cost, start, draws_for(runs, reps), spans)
    bar, skill = bar_of(curve, dca), implied(curve, ending)
    return {"bars": len(slice_.bars) - start, "runs": len(runs), "share": share, "hits": hits,
            "se": se, "switches": switches, "ending": ending, "dca": dca, "bar": bar, "skill": skill,
            # The wedge is the honest part of the headline: how far the skill the money shows sits
            # from the percentage of decisions that were right. Positive means the wins were the runs
            # that mattered; negative means they were the ones that cost a switch and nothing else.
            "wedge": None if skill is None else skill - hits,
            "gap": None if bar is None else skill - bar,
            "months": slice_.months(start)}


def per_month(row) -> float:
    return funded_frame.per_month_equivalent(row["ending"] - row["dca"], IRR_STANDIN, row["months"])


def render(rows) -> str:
    head = (f"{'rule':<18} {'runs':>5} {'long':>5} {'hits':>6} {'skill':>6} {'own bar':>8} {'gap':>9} "
            f"{'wedge':>7} {'switches':>9} {'$/mo vs DCA':>12}  verdict")
    out = [head, "-" * len(head)]
    for row in rows:
        bar = "no bar" if row["bar"] is None else f"{row['bar'] * 100:.1f}%"
        skill = "n/a" if row["skill"] is None else f"{row['skill'] * 100:.1f}%"
        wedge = "n/a" if row["wedge"] is None else f"{row['wedge'] * 100:+.0f}pp"
        gap = "n/a" if row["gap"] is None else f"{row['gap'] * 100:+.1f} pp"
        se = f"{row['gap'] / row['se']:+.1f}" if row["gap"] is not None and row["se"] else ""
        money = per_month(row)
        trials = f" \u00d7{row['trials']}" if row.get("trials", 1) > 1 else ""
        verdict = ("exact" if row["gap"] is not None and abs(row["gap"]) < 1e-9 else
                   "BEATS ITS OWN BAR" if row["gap"] is not None and row["gap"] > 0 else
                   "no bar on earth" if row["gap"] is None else "short")
        out.append(f"{row['rule'] + trials:<18} {row['runs']:>5.0f} {row['share'] * 100:>4.0f}% "
                   f"{row['hits'] * 100:>5.1f}% {skill:>6} {bar:>8} {gap:>9} {wedge:>7} "
                   f"{row['switches']:>9,.0f} {money:>+12,.0f}  {verdict}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sleeve", action="append", choices=SLEEVES)
    parser.add_argument("--window", action="append", choices=list(WINDOWS))
    parser.add_argument("--cost-bps", type=float, default=COSTS[-1])
    parser.add_argument("--reps", type=int, default=REPS)
    parser.add_argument("--r3-expense", action="store_true",
                        help="charge the expense ratio to the cash leg, as round 3 did")
    parser.add_argument("--cadence", type=int, default=WEEK, choices=CADENCES,
                        help="sessions between decisions (5 = round 3's weekly convention)")
    args = parser.parse_args()

    windows = {k: v for k, v in WINDOWS.items() if not args.window or k in args.window}
    print(f"every rule's own bar · one-way cost {args.cost_bps:g} bps · expense on the "
          f"{'CASH leg (round 3)' if args.r3_expense else 'FUND leg'} · one decision every "
          f"{args.cadence} session(s) · {args.reps} shadow draws per solve\n")
    tally = []
    for symbol in (args.sleeve or SLEEVES):
        for label, bounds in windows.items():
            rows = audit(symbol, label, bounds, args.cost_bps, args.reps, args.r3_expense,
                           args.cadence)
            if not rows:
                continue
            print(f"=== {symbol} · {label} · fund expense "
                  f"{wc.EXPENSE.get(symbol, 0.0) * 10_000:.2f} bps ===")
            print(render(rows))
            print()
            tally += rows

    real = [r for r in tally if r["rule"] not in CONTROLS]
    clear = [r for r in real if r["gap"] and r["gap"] > 0]
    # The gap is an inequality on the same curve the money is read from, so it can only disagree with
    # the dollars if the solve is broken. Rows with no bar make no claim and are not counted.
    scored_rows = [r for r in real if r["gap"] is not None]
    disagree = [r for r in scored_rows if (r["gap"] > 0) != (per_month(r) > 0)]
    print(f"{len(clear)} of {len(real)} real-rule windows clear their own bar; the gap and the money "
          f"agree in {len(scored_rows) - len(disagree)} of the {len(scored_rows)} rows that have a "
          f"bar at all.")
    for row in clear:
        print(f"  clears its own bar: {row['sleeve']} {row['window']} — {row['rule']}, "
              f"{row['hits'] * 100:.1f}% of decisions right, {row['skill'] * 100:.1f}% of skill, "
              f"against a bar of {row['bar'] * 100:.1f}% ({per_month(row):+,.0f}/mo)")
    if disagree:
        print(f"  {len(disagree)} rows where the bar and the dollars disagree — the solve is wrong, "
              f"not the market:")
        for row in disagree:
            print(f"    {row['sleeve']} {row['window']} {row['rule']}: gap "
                  f"{row['gap'] * 100:+.1f} pp, {per_month(row):+,.0f}/mo")


if __name__ == "__main__":
    main()
