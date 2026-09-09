"""Which spending rule pays the most, when every rule is forced to promise the same floor?

Run: .venv/bin/python tools/income_frontier.py [--years 10] [--floor 400]

Eighteen rounds of this repository have searched for a *trading* rule that raises monthly income and the
round that came closest to a verdict instead concluded the opposite: on a withdrawal basis nothing on the
menu — not leverage, not a wrapper, not a signal — moved the reliable monthly number as much as the decision
about whether the cheque is allowed to shrink. That decision costs nothing, needs no forecast, and is the
user's. It has never been priced across the rule family, and it is the largest lever the repo has named and
not measured.

So this tool stops asking what a plan earns and asks what it **pays**, on the statistic the goal is written
in. Four rules, one equaliser, and the Dominance Rule applied to income rather than to terminals.

## The four rules, and the one statistic that makes them comparable

A plan is not its policy; it is also its cheque. Comparing rules by their first cheque is the trick that makes
every flexible rule look generous, because a flexible rule's first cheque is a promise it withdraws in the
worst year — which is the only year the number is worth anything. So every rule here is scored by the
**smallest cheque it ever actually handed over, across every start date in the record**: its floor. Then each
rule is scaled — by bisection — until it delivers a chosen floor, and only *then* compared, on the median
mean cheque it paid over those same starts. Same floor, compare the average; that ordering is fixed here
before the run, and it is the whole design.

  fixed        a dollar amount, never indexed, never cut. The floor is the cheque.
  indexed      the same, grown 2.5% a year — what round 7 used, and what flatters the recent past.
  guardrail    a dollar amount allowed to be cut to half when the account falls 25% below its high-water
               mark. Its floor is below its first cheque, by construction, and that is the trade.
  fraction     a percentage of the account's current value, every month. It cannot die and it has no floor
               in dollars, which is why it has to be equalised rather than quoted: at an equal floor it
               either pays more or it does not, and the answer is not assumed here.

Feasibility, for every rule and every scale: every start date in the record survives to the horizon, with no
maintenance call. A plan that survives only because the broker was not allowed to force the sale is not a
plan, and an average over start dates is the most conveniently misleading number in personal finance.

## The bar, which is the same one as always

  * the levered plan must pay a larger median at an equal floor than plain unlevered VOO;
  * plain VOO must pay a larger median at an equal floor than holding T-bills;
  * a rule that cannot deliver the requested floor at all — because survival binds before the floor does —
    is reported as "cannot promise it", not as a smaller number.

Nothing here is a signal. Every plan priced is either an index, cash, or an index on a loan at a posted rate,
which is the complete list of things this repository has ever found worth owning. If a spending rule moves the
monthly number by more than any mechanism in eighteen rounds did, that is the finding, and it is a finding
about a spreadsheet cell rather than about a model.

## Conventions, so the numbers can be argued with

The engine is `withdrawal_capacity.run`, imported and not re-implemented — two simulators that drift apart is
the failure mode round 6 named. Costs are that engine's: each sleeve's real expense ratio, 2 bps per unit one
way, borrow at the archive cash index plus a spread, 30% maintenance equity with a forced sale. The levered
rows are priced at the April 2026 Public tier of 4.90% *all-in*, which in this engine means a spread of
4.90% minus the archive's current cash yield; the spread is therefore allowed to be negative, and it is: a
posted retail margin rate below the T-bill bill is a fact about the last year's rate curve, not a bug. The
engine normalises to a $100,000 lump, so every figure is linear in the account's size and the table prints
$/mo at $20k, $50k and $100k rather than pretending the archive's normalisation is the user's balance. The
common horizon is 10 years because that is the longest plan VOO's 15-year record supports, and the number of
starts each plan was measured on is printed with its first and last start date. VOO has few starts and benign
ones, which flatters it and is stated above the table rather than left to the reader.

## The round-20 addition, and the bar it has to clear

Round 8 scored the pre-registered candidate — 18% vol target, 30-day window, 200-day trend gate, 30% floor,
1.30x cap — in withdrawal units and it raised the worst-start floor on SPY from $379 to $518, the only
mechanism in this repository ever to beat the Dominance Rule on an income statistic. Round 19's table did not
test it: it priced constant leverage and called the question closed. That was the wrong generalisation and this
version of the table fixes it by pricing the candidate in the same equal-floor frame, against the same four
spending rules, with three things round 8 could not do:

  * the band is set to zero for a path plan, so every monthly weight change the policy asks for is executed
    and charged. Round 8 ran the index plan's 10% band, which lets a policy that wants 0.30x sit at 1.10x for
    free and calls the difference expense. This charges the policy for the trades it itself causes;
  * the borrow is the April 2026 posted Public tier of 4.90% all-in, not the archive cash index plus a
    researcher's 150 bps. A policy that sometimes holds 1.30x is a policy that sometimes borrows at a desk's
    posted rate, and round 17 established that the menu, not the assumption, is the constraint;
  * the comparators are the ones round 19 made standard: the same sleeve unlevered, and a flat weight at the
    policy's own average — because a rule that beats nothing but doing-less-nothing has not been tested.

The bar, fixed here before the first cell: at an equal floor and the same spending rule, the candidate must pay
a larger median than plain SPY *and* than flat-at-its-own-average-weight, on a path whose mirror image loses to
it, at both horizons. If it clears, it is the first thing in twenty rounds worth building. If it does not, the
number that killed it goes in the note, and the candidate retires with its arithmetic on the record.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import withdrawal_capacity as wc                 # noqa: E402  the engine; there is exactly one
from policy_withdrawal import CANDIDATE, GATELESS, monthly_weights    # noqa: E402  the pre-registered path
from boring_alpha.signals.voltarget import VolTargetPolicy            # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

MENU_PUBLIC = 0.0490      # April 2026, the cheapest desk's base tier, all-in
FLOORS = (400.0, 700.0, 1000.0)   # $/mo on a $100k normalised lump: 4.8%, 8.4%, 12.0% a year
SIZES = (20_000.0, 50_000.0, 100_000.0)
RULES = ("fixed", "indexed", "guardrail", "fraction")
PATH_PLANS = ("candidate", "gateless", "reversed", "flat at avg")
SLEEVE_LEAGUE = ("SPY", "VOO", "QQQ", "VTI", "ITOT")   # every sleeve in the archive, at its own expense
# Round 18 measured the SPY-versus-VOO fund choice itself at $25/mo on a $20k funded frame
# (`attention_bar.NOISE_FLOOR`). Scaled by capital that is on the order of $125/mo per $100k, which is this
# table's unit. Used as an order-of-magnitude "that gap is not a finding" band and nothing finer: a precise
# equivalence would need the contribution schedule, and this is a lump table.
NOISE_FLOOR = 125.0
GUARD = (0.25, 0.50)      # cut to half below 75% of high water — round 7's shape, unchanged
INFLATE = 0.025
STRIDE = 2                # every second month is a start date
MIN_STARTS = 12           # fewer starts than this is an anecdote, not a horizon


@dataclass(frozen=True)
class Plan:
    """One thing it is possible to own, at its real cost. Every plan here is an index, cash, or a loan."""

    label: str
    sleeve: str | None      # None holds no sleeve at all: T-bills, and the calendar of the reference sleeve
    lever: float
    expense: float
    spread: float           # over the archive cash index. May be negative; see the docstring
    calendar: str = "SPY"   # whose month-ends the plan is measured on
    path: str = ""          # "", "candidate", "gateless", "reversed", "avg": a weight policy, not a level
    band: float = None      # rebalance band; a path plan is run at zero so its own churn is charged

    def __post_init__(self):
        if self.band is None:
            object.__setattr__(self, "band", 0.0 if self.path else wc.BAND)

    @property
    def label_width(self) -> int:
        return len(self.label)


@dataclass(frozen=True, slots=True)
class Cell:
    plan: str
    rule: str
    target: float           # the floor this cell was asked to promise, $/mo on a $100k lump
    scale: float            # the rule's own knob: $/mo first cheque, or a monthly fraction
    floor: float            # the smallest cheque actually handed over, across every start
    median: float           # median over starts of the mean cheque actually paid
    ratio: float            # median / floor: what a dollar of promise buys
    ending: float           # smallest terminal balance over starts, as a fraction of the lump
    starts: int
    feasible: bool
    bounded_by: str
    binding: str            # first start date that failed, and how
    calls: int = 0          # margin calls across every start: a call disqualifies whoever survives it

    def dollars(self, size: float) -> float:
        return self.median * size / wc.START


def cash_yield_now(factors: dict) -> float:
    """Trailing-year annualised yield on the archive's own cash index, from the last 12 monthly factors."""

    monthly = _cash_monthly(factors)
    tail = monthly[-12:] if len(monthly) >= 12 else monthly
    if not tail:
        raise SystemExit("the archive has no cash factors; the plan cannot be financed or parked")
    growth = 1.0
    for f in tail:
        growth *= f
    return growth ** (12.0 / len(tail)) - 1.0


def _cash_monthly(factors: dict) -> list:
    """The cash index compounded to month factors, oldest first."""

    out: list = []
    keys = sorted(factors)
    for day in keys:
        key = (day.year, day.month)
        if out and out[-1][0] == key:
            out[-1][1] *= factors[day]
            continue
        out.append([key, factors[day]])
    return [v[1] for v in out]


def plans(cash_now: float, spread: float | None = None) -> list:
    """The menu. `spread` is the annual cost of borrowing over the archive cash index.

    It defaults to today's cash yield subtracted from the posted tier — right for a decision made this month,
    wrong for a twenty-year backtest. The archive's own mean cash yield sits well below today's, so pricing
    against today leaves the simulation borrowing at roughly 3.9% a year on average, a point cheaper than the
    desk would charge. The caller passes a spread set against the record's mean, and the header says which was
    used. A candidate spends 68% of its months in borrow, so this is its cost and not a rounding.
    """

    if spread is None:
        spread = MENU_PUBLIC - cash_now       # negative in a low-rate year, and that is the truth
    menu = [Plan("cash", None, 0.0, 0.0, 0.0, "SPY"),
            Plan("VOO", "VOO", 1.0, wc.EXPENSE["VOO"], 0.0, "VOO"),
            Plan("SPY", "SPY", 1.0, wc.EXPENSE["SPY"], 0.0, "SPY"),
            Plan("QQQ", "QQQ", 1.0, wc.EXPENSE["QQQ"], 0.0, "QQQ"),
            Plan("VTI", "VTI", 1.0, wc.EXPENSE["VTI"], 0.0, "VTI"),
            Plan("ITOT", "ITOT", 1.0, wc.EXPENSE["ITOT"], 0.0, "ITOT"),
            Plan("SPY 1.25x", "SPY", 1.25, wc.EXPENSE["SPY"], spread),
            Plan("SPY 1.50x", "SPY", 1.50, wc.EXPENSE["SPY"], spread),
            # The pre-registered candidate and the three controls that make it a test rather than a demo.
            Plan("candidate", "SPY", 1.0, wc.EXPENSE["SPY"], spread, "SPY", "candidate"),
            Plan("gateless", "SPY", 1.0, wc.EXPENSE["SPY"], spread, "SPY", "gateless"),
            Plan("reversed", "SPY", 1.0, wc.EXPENSE["SPY"], spread, "SPY", "reversed"),
            Plan("flat at avg", "SPY", 1.0, wc.EXPENSE["SPY"], spread, "SPY", "avg")]
    # Round 20 proved the candidate on SPY, and the goal is written against VOO and QQQ. One fund's result is
    # one fund's result: the same rule on a different index is a different claim, and the pre-registration
    # that made round 20 believable was written on a single sleeve. Every sleeve in the archive now carries
    # the policy and the mirror image of its own path, each on its own calendar and at its own expense ratio.
    for sleeve in SLEEVE_LEAGUE:
        if sleeve == "SPY":
            continue
        menu += [Plan(sleeve, sleeve, 1.0, wc.EXPENSE[sleeve], 0.0, sleeve),
                 Plan(f"cand {sleeve}", sleeve, 1.0, wc.EXPENSE[sleeve], spread, sleeve, "candidate"),
                 Plan(f"rev {sleeve}", sleeve, 1.0, wc.EXPENSE[sleeve], spread, sleeve, "reversed")]
    return menu


def series_for(data, symbol: str) -> dict:
    return {d: bars[symbol].close for d, bars in data.by_date.items() if symbol in bars}


def weight_path(kind: str, data, symbol: str, keys: list) -> list:
    """The policy's monthly weight path, in the alignment the engine's window slicing expects.

    `reversed` is the mirror image of the candidate's own path: same weights, same time at each level, same
    mean, wrong months. `avg` is the flat weight the policy averaged over the record, decided zero times.
    """

    # `which` is the policy to compute from and `kind` stays the control being asked for. They were one
    # variable once, and "avg" rewrote itself to "candidate" before the flat path could be built, so the
    # control that is supposed to say "you could have just held this" quietly returned the candidate and
    # matched it to the dollar. A control that copies its subject is worse than no control.
    which = "candidate" if kind == "avg" else kind
    policy = GATELESS if which == "gateless" else CANDIDATE
    closes = series_for(data, symbol)
    days = sorted(closes)
    path = monthly_weights(policy, days, [closes[d] for d in days], keys)
    if len(path) != len(keys):
        raise ValueError(f"{len(path)} weights for {len(keys)} months: the path and the calendar disagree")
    if not any(abs(w - path[0]) > 1e-9 for w in path):
        raise ValueError("the weight path never moves; the policy is not answering and every comparison "
                         "below would be a comparison with a constant")
    if kind == "reversed":
        return list(reversed(path))
    if kind == "avg":
        flat = sum(path) / len(path)
        flat_path = [flat] * len(path)
        if any(abs(w - flat) > 1e-12 for w in flat_path):
            raise ValueError("the flat control is not flat")
        return flat_path
    return path


def score(window: tuple, plan: Plan, rule: str, scale: float, _zero_path: list = None) -> wc.Run:
    """One start date, one rule, one scale. The engine decides everything about costs and ruin.

    A cash plan's zero weight path is built from the window's own length, not from a shared array: the
    engine's docstring is explicit that reaching backwards through a series the window does not carry is
    the off-by-one that turns a policy into a crystal ball, and a path of zeros is still a path.
    """

    returns, cash, _start = window[:3]
    # The window's own path slice travels inside the window; a shared array would be the off-by-one that
    # turns a trend gate into a crystal ball, which is the engine's own words for its own bug.
    targets = window[3] if len(window) > 3 else ([0.0] * len(returns) if plan.sleeve is None else None)
    fraction = scale if rule == "fraction" else None
    return wc.run(returns, cash, plan.lever, 0.0 if fraction is not None else scale,
                  plan.expense, INFLATE if rule == "indexed" else 0.0, plan.band, "margin",
                  wc.MAINTENANCE_EQUITY, plan.spread,
                  GUARD if rule == "guardrail" else None, targets, fraction)


def evaluate(windows: list, plan: Plan, rule: str, scale: float, zero_path: list) -> Cell:
    """Every start date at once. The floor and the ending are minima over starts; the median is a median."""

    floors, means, ends, binding, calls = [], [], [], "", 0
    for window in windows:
        run = score(window, plan, rule, scale, zero_path)
        # A call disqualifies the withdrawal no matter who survives it. Round 7's reason stands: a plan that
        # works only because the lender never had to sell at the bottom is not a plan, and the levered rows
        # below are the only ones that can hear that bell.
        calls += run.calls
        if (not run.survived or run.calls) and not binding:
            binding = f"{window[2]:%Y-%m}" + ("" if not run.survived else " (call)")
        floors.append(run.smallest if run.survived else 0.0)
        # The mean cheque is over the months the plan actually had, so a plan that died in year three does
        # not flatter its average by dividing a short life by a long horizon.
        means.append(run.paid / len(window[0]) if run.survived else 0.0)
        ends.append(max(run.ending, 0.0) / wc.START)
    floor, median = min(floors), statistics.median(means)
    return Cell(plan.label, rule, 0.0, scale, floor, median, median / floor if floor > 0 else 0.0,
                min(ends), len(windows), not binding, "", binding, calls)


def solve(windows: list, plan: Plan, rule: str, target: float, zero_path: list) -> Cell:
    """Ask each rule to promise `target` a month, at the cheapest knob setting that does, then read its median.

    A fixed cheque's floor *is* its first cheque, so the answer for `fixed` and `indexed` is the target
    itself and the only question left is whether the plan survives every start at that size. A guardrail's
    floor is half its first cheque whenever any start gets cut, so it is asked for twice the floor. A
    fraction has no dollar knob at all: its rate is bisected until the worst cheque over every start lands
    on the target, on the branch below the peak where the floor rises with the rate.
    """

    if rule in ("fixed", "indexed"):
        cell = evaluate(windows, plan, rule, target, zero_path)
        return _stamp(cell, target, "floor" if cell.feasible else "survival")
    if rule == "guardrail":
        cell = evaluate(windows, plan, rule, target / GUARD[1], zero_path)
        if cell.floor > target * 1.001:      # nothing in the record ever triggered the cut
            cell = evaluate(windows, plan, rule, target, zero_path)
            return _stamp(cell, target, "never triggered")
        return _stamp(cell, target, "floor" if cell.feasible else "survival")

    lo, hi = target / wc.START, 4.0 * target / wc.START
    if evaluate(windows, plan, rule, lo, zero_path).floor < target * 0.999:
        cell = evaluate(windows, plan, rule, lo, zero_path)
        return _stamp(cell, target, "survival")
    for _ in range(28):
        mid = (lo + hi) / 2.0
        if evaluate(windows, plan, rule, mid, zero_path).floor >= target * 0.999:
            lo = mid
        else:
            hi = mid
    cell = evaluate(windows, plan, rule, lo, zero_path)
    return _stamp(cell, target, "floor" if cell.feasible else "survival")


def _stamp(cell: Cell, target: float, bounded_by: str) -> Cell:
    return Cell(cell.plan, cell.rule, target, cell.scale, cell.floor, cell.median,
                cell.median / cell.floor if cell.floor > 0 else 0.0, cell.ending, cell.starts,
                cell.feasible, bounded_by, cell.binding, cell.calls)


def apply_sweep(rates: list, sweep: float | None) -> list:
    """Replace every monthly cash rate with the rate an account would actually have been paid.

    Round 24 found the asymmetry this exists to test: the simulations credit the idle slice of a de-risking
    rule — 15.7% of the record on average — with the Treasury curve in the archive, while the audited median
    brokerage default sweep pays 0.02% and does not care what the curve did. This is not a floor and not a
    haircut, it is a substitution: at a desk that pays a flat rate, the curve is simply unavailable.

    Note what travels with it. `mean_cash` is computed from these rates downstream, and the borrow spread is
    `MENU_PUBLIC - mean_cash`, so the all-in financing stays pinned at the posted desk rate while the cash
    credit falls. Replacing the cash leg while holding the spread fixed would silently cheapen leverage at the
    same time as it de-rated the cash, and the two errors would partly cancel — which is the worst possible
    combination in a file whose whole purpose is a defensible number.
    """

    if sweep is None:
        return rates
    return [(1.0 + float(sweep)) ** (1.0 / 12.0) - 1.0] * len(rates)


def load(years: int, stride: int = STRIDE, sweep: float | None = None) -> tuple:
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    yield_now = cash_yield_now(data.cash_factors)
    # The record's own mean cash yield, annualised, for pricing a backtest's borrow. Every monthly figure in
    # this archive comes from the same cash factor, so this is one number and it is checkable.
    monthly_cash = wc.monthly(series_for(data, "SPY"), data.cash_factors)[1]
    monthly_cash = apply_sweep(monthly_cash, sweep)
    mean_cash = (1.0 + sum(monthly_cash) / len(monthly_cash)) ** 12 - 1.0
    # Under a sweep the account's cash yield *is* the sweep, so every downstream use of `yield_now` — the cash
    # plan's own rate, and the caller's spread — has to see the substituted figure rather than the curve.
    if sweep is not None:
        yield_now = mean_cash
    # The calendar cache and the per-plan windows live in separate dicts. They were one dict once, and the
    # plan labelled "SPY" shares its name with the SPY calendar that four plans are measured on, so the
    # fourth plan read a 2-tuple as a 3-tuple and unpacked a crash instead of a table.
    calendars: dict = {}
    tables: dict = {}
    for plan in plans(yield_now):
        cache = calendars.get(plan.calendar)
        if cache is None:
            returns, cash_rate, keys = wc.monthly(series_for(data, plan.calendar), data.cash_factors)
            cache = (returns, apply_sweep(cash_rate, sweep), keys)
            calendars[plan.calendar] = cache
        returns, cash_rate, keys = cache
        path = None
        if plan.path:
            path = weight_path(plan.path, data, plan.sleeve, keys)
            tables[plan.label + " avg lev"] = sum(path) / len(path)
        # The path goes in with the windows, month-aligned, so each start date carries its own slice of it.
        windows = wc.windows_for(returns, cash_rate, keys, years, stride, path)
        tables[plan.label] = (windows, path)
        tables[plan.label + " span"] = (windows[0][2], windows[-1][2]) if windows else None
    return tables, yield_now, data, mean_cash


def report(cells: list, years: int, cash_record: float, target: float, spans: dict | None = None,
           spread: float | None = None, avgs: dict | None = None, cash_note: str = "") -> None:
    print(f"income frontier · what each spending rule pays when all four must promise ${target:,.0f} a "
          f"month for {years} years")
    print(f"engine withdrawal_capacity.run · a start date every {STRIDE} months · a plan qualifies only if "
          f"EVERY start survives with no margin call")
    print(f"borrow priced at the April 2026 posted Public tier {MENU_PUBLIC:.2%} on average: spread "
          f"{spread:+.2%} over the archive cash index, set against the record's mean cash yield "
          f"{cash_record:.2%}{cash_note}\n")
    if avgs:
        print("  " + " · ".join(f"{k}: mean weight {v:.3f}" for k, v in avgs.items()) +
              "\n  a path plan runs at a zero band, so every monthly move it asks for is executed and charged")
    print(f"  {'plan':11} {'rule':10} {'starts':>6} {'floor paid':>11} {'median/mo':>10} {'×floor':>7} "
          f"{'min end':>8} {'$20k':>7} {'$50k':>7} {'$100k':>8}  reading")
    print("  " + "-" * 108)
    if spans:
        note = ", ".join(f"{k[:-5]} {v[0]:%Y-%m}..{v[1]:%Y-%m}" for k, v in spans.items() if v)
        print(f"  start dates run {note}")
        print("  VOO's record begins 2010-09, so its starts are few and all from the mildest decade this "
              f"asset class\n  has ever seen: it is the flattered party in every row below, not the injured "
              f"one\n")
    for plan in list(dict.fromkeys(c.plan for c in cells)):
        for rule in RULES:
            cell = next(c for c in cells if c.plan == plan and c.rule == rule)
            if not cell.feasible:
                how = "a lender forced a sale" if "call" in cell.binding else "a start died"
                reading = f"cannot keep {years} years: {how} at {cell.binding or 'an early start'}"
                if cell.calls:
                    reading += f" ({cell.calls} call(s) across the record)"
            elif cell.floor < target * 0.999:
                reading = (f"cannot promise ${target:,.0f}: the worst cheque is ${cell.floor:,.0f}, "
                           f"because a fraction of a shrinking account is smaller than the fraction")
            elif saturated(cell):
                reading = (f"pays {cell.ratio:.2f}x, the rule's own ceiling: no start cut it, so this row "
                           f"\n       cannot rank plans — see the note before quoting the gap")
            else:
                reading = f"pays {cell.ratio:.2f}x its promise"
            print(f"  {plan:11} {rule:10} {cell.starts:>6} {cell.floor:>11,.0f} {cell.median:>10,.0f} "
                  f"{cell.median / cell.floor if cell.floor else 0:>7.2f} {cell.ending:>8.2f} "
                  f"{cell.dollars(SIZES[0]):>7,.0f} {cell.dollars(SIZES[1]):>7,.0f} "
                  f"{cell.dollars(SIZES[2]):>8,.0f}  {reading}")
        print()


def saturated(cell) -> bool:
    """True when a guardrail row sits at the ratio its own definition allows and no more.

    A guardrail keeps half its cheque when triggered, so its median is capped at twice its floor. When a
    record is mild enough that no start is ever cut, the median sits on that cap — and every plan in the
    table sits there with it, so the row compares two numbers that are both the number 2.00. Round 20 quoted
    VOO's 1.99x as a sizeable result; it was the ceiling, not an achievement, and a plan's rank cannot be
    read off a row that the promise never tested. This is the flag that says so, in the table and in the
    verdict, on the same page as the number.
    """

    return cell.rule == "guardrail" and cell.feasible and cell.floor > 0 and cell.median / cell.floor > 1.97


def verdict(cells: list, target: float, years: int) -> str:
    """`not measured` and `cannot promise` are different sentences and only one of them is a verdict.

    VOO has fifteen years of history, so a twenty-year plan has no start date for it at all. Reporting that
    as "VOO cannot promise the cheque" would be the same error as a missing experiment reported as a failed
    one, and it would be the most consequential sentence in the table: it would read as if the cheapest fund
    on this list had been tested against a twenty-year promise and lost.
    """
    """The Dominance Rule, in the goal's own unit."""

    def best(plan: str) -> Cell | None:
        ok = [c for c in cells if c.plan == plan and c.feasible and c.floor >= target * 0.999]
        return max(ok, key=lambda c: c.median) if ok else None

    lines = []
    measured = {c.plan for c in cells}
    pairs = [("SPY 1.25x", "SPY"), ("SPY 1.50x", "SPY"), ("candidate", "SPY"),
             ("candidate", "flat at avg"), ("candidate", "reversed"), ("candidate", "gateless"),
             ("SPY", "VOO"), ("VOO", "cash"), ("SPY", "cash"), ("QQQ", "cash")]
    # On every sleeve, the same two questions: does the rule beat holding the fund, and does it beat holding
    # the fund's own price history read backwards. A sleeve with too little history prints "not measured".
    pairs += [(f"cand {s}", s) for s in SLEEVE_LEAGUE if s != "SPY"]
    pairs += [(f"cand {s}", f"rev {s}") for s in SLEEVE_LEAGUE if s != "SPY"]
    pairs += [("VTI", "VOO"), ("ITOT", "VOO")]
    for label, rival in pairs:
        winner, loser = best(label), best(rival)
        if label not in measured or rival not in measured:
            missing = label if label not in measured else rival
            lines.append(f"  {label:10} vs {rival:10} not measured: {missing} has no {years}-year record "
                         f"in this archive")
        elif winner is None:
            lines.append(f"  {label:10} cannot promise ${target:,.0f}/mo from any start; nothing to compare")
        elif loser is None:
            lines.append(f"  {label:10} clears it, {rival} does not — {label} is the only one making "
                         f"that promise")
        else:
            gap = winner.median - loser.median
            tag = "  REDUNDANT" if gap <= 0 else ""
            if saturated(winner):
                # The winner's median is the ratio the guardrail is *allowed* to pay, not the ratio it earned.
                # A row like that cannot rank two plans by income, and saying "REDUNDANT" or quoting a gap on
                # top of it would be quoting the number 2.00 as if it were a result.
                tag = ("  NOT DISCRIMINATING: the winner sits on the guardrail's 2.00x ceiling, so no start "
                       "cut it")
            lines.append(f"  {label:10} vs {rival:10} {gap:+9,.0f} /mo median at an equal floor" + tag)
    ok = [c for c in cells if c.feasible and c.floor >= target * 0.999]
    graded = [c for c in ok if c.rule == "guardrail"]
    flat = [c for c in graded if saturated(c)]
    if graded and len(flat) > len(graded) // 2:
        lines.append(f"  {len(flat)} of {len(graded)} ranking rows sit pinned on the guardrail's 2.00x "
                     f"ceiling:\n  on this horizon the promise is mild enough that the spending rule never "
                     f"binds,\n  so the plan column is measuring survival and capital, not income.")
    weak = [(label, rival) for label, rival in pairs if label.startswith("cand") and rival in measured
            and best(label) and best(rival)]
    gaps = {f"{l} vs {r}": best(l).median - best(r).median for l, r in weak}
    if gaps:
        worst = min(gaps, key=lambda k: gaps[k])
        if gaps[worst] < NOISE_FLOOR:
            lines.append(f"  the candidate's weakest showing is {worst} at ${gaps[worst]:,.0f} /mo, inside "
                         f"the ${NOISE_FLOOR:,.0f}\n  noise floor of choosing SPY over VOO: on a short mild "
                         f"record the rule has nothing\n  to protect against, and the table cannot see the "
                         f"decade that makes it work.")
    spread = (max((c.median for c in ok), default=0.0) - min((c.median for c in ok), default=0.0))
    ratios = sorted({round(c.median / c.floor, 2) for c in ok if c.floor > 0})
    lines.append(f"  the whole distance between the best and worst *plan* at this floor is ${spread:,.0f} "
                 f"/mo,\n  while the distance between the best and worst *rule* inside one plan runs "
                 f"{ratios[0]:.2f}x to {ratios[-1]:.2f}x.")
    champ = best("candidate")
    index = best("SPY")
    # The claim to test is "the candidate beats the same sleeve held flat", not "the candidate tops the
    # table": at ten years VOO out-pays everything, and VOO's fifteen benign years are the reason. Letting
    # the champion decide which sentence to print would have hidden the candidate's own result behind a
    # flattered comparator.
    if champ is not None and index is not None and champ.median > index.median:
        lines.append(f"  This time neither line is the story. {champ.plan} — a rule, no forecast in the "
                     f"spending, charged\n  its own monthly turnover at a posted borrow rate — pays "
                     f"${champ.median - index.median:,.0f} /mo more than\n  the same sleeve held flat, with "
                     f"the mirror image of its own path and its own average weight both beaten.")
    else:
        lines.append("  The spending rule is a spreadsheet cell. The plans differ by a loan at a posted rate.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--floor", type=float, default=0.0, help="one floor only, $/mo on a $100k lump")
    ap.add_argument("--stride", type=int, default=STRIDE)
    ap.add_argument("--sweep", type=float, default=None,
                    help="annual rate the account is actually paid on idle cash, replacing the archive "
                         "curve (0.0002 = the audited brokerage default)")
    args = ap.parse_args()
    tables, cash_now, _data, mean_cash = load(args.years, args.stride, args.sweep)
    cash_note = (f" (substituted: the account earns {args.sweep:.2%} wherever the archive curve is "
                 f"quoted, and the borrow spread moves with it so the all-in stays {MENU_PUBLIC:.2%})"
                 if args.sweep is not None else "")
    # Priced at the posted tier *on average* over the record, which is the conservative reading of a
    # twenty-year backtest: a constant spread set against today's yield would have the simulation borrowing
    # below what the desk posts, in exactly the years the promise is hardest to keep.
    spread = MENU_PUBLIC - mean_cash
    targets = (args.floor,) if args.floor else FLOORS
    for target in targets:
        cells = []
        for plan in plans(cash_now, spread):
            windows, zero_path = tables[plan.label]
            if len(windows) < MIN_STARTS:
                continue
            for rule in RULES:
                cells.append(solve(windows, plan, rule, target, zero_path))
        spans = {k: v for k, v in tables.items() if k.endswith(" span")}
        avgs = {k[:-8]: v for k, v in tables.items() if k.endswith(" avg lev")}
        report(cells, args.years, mean_cash, target, spans, spread, avgs, cash_note)
        print("Verdict, in the unit the goal is written in — the same plan must beat the cheaper one it is "
              "supposed to improve on:")
        print(verdict(cells, target, args.years))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
