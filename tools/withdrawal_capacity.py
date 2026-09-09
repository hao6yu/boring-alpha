"""What this account can actually pay out, in dollars per month, and how sure you are.

Run: .venv/bin/python tools/withdrawal_capacity.py [--window-years 20] [--instrument wrapper]

Every number this repository has produced so far is an accumulation number: what a balance
grows to if nobody touches it. Round 4 reported "leveraged SPY earns $346 a month more
than doing nothing", which is an accrual on an equity line that spends part of every
decade 70% underwater. That is not income. Money nobody can take out is not a monthly
income, and a plan whose stated purpose is a monthly amount has to be tested by taking a
monthly amount out of it.

So this tool asks the decumulation question instead:

    start with a lump, withdraw W every month for N years, pay real costs, and find the
    largest W that every possible start date in the record survives.

The answer must be quoted as a guarantee across *every* start date, not an average. A
sequence-of-returns figure averaged over start dates is the most conveniently misleading
number in personal finance: it blends the person who started in 1999 with the one who
started in January 2000, and only one of them ran out of money.

The comparator is the same plan held without leverage on the same withdrawal policy — the
Dominance Rule translated into this frame. If a levered, trading book cannot pay a LARGER
reliable monthly amount than simply owning the index, it is Redundant here too, and no
amount of interesting machinery changes that.

Two instruments, because round 4 established that the instrument dominates the sizing
decision, and there is no reason to expect that finding to survive a change of question
by accident:

  margin   a loan against the account, at the account's own financing spread, with a
           maintenance test. Below the cushion the book is cut to 1x at the cost of the
           forced sale, and the run records a call. A call disqualifies a withdrawal from
           counting as reliable whoever survives it: a plan that works only because the
           broker was not allowed to force the sale at the bottom is not a plan.
  wrapper  a leveraged ETF. It holds no loan, so nothing is callable. It is priced as a
           transformation of the account's return — lever x index, less the financing on
           its swap line, less its own expense ratio on its own NAV — and not as a loan
           on top of a balance. Charging that fund's 90 bps against the account's gross
           exposure instead of its NAV is the error that inverted round 4's conclusion,
           and it is not repeated here. Moving money in or out costs the fund's spread.

Conventions, so this can be argued with. Withdrawals are funded by selling, never by
adding to the loan — an account that borrows to pay a chequebook is compounding a mistake,
and letting the comparator do it would inflate the benchmark rather than the candidate.
The withdrawal is indexed at 2.5% a year by default, because a fixed nominal amount
flatters the answer by asking the account to pay the same cheque in 2046 as in 2026;
--inflate 0 shows what that assumption is worth. Order within a month: market, ruin check,
withdrawal, maintenance, rebalance. Stating it matters — a forced sale that lands before
the withdrawal is a different simulation from one that lands after it.
"""

from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boring_alpha.data.csv_loader import load_csv_market_data

SNAPSHOT = ROOT / "data" / "current" / "market_daily.csv"
CASH_FILE = ROOT / "data" / "current" / "cash_daily.csv"

START = 100_000.0          # normalised lump; every withdrawal below is a fraction of it
TURNOVER_COST = 0.0002     # 2.0 bps per unit, one way, for plain sleeves
# The loan price, taken from the forward engine rather than re-typed here. This constant was 0.015 until round 104, which is
# the value round 30 *raised* `paper.BORROW_SPREAD` from — the research family had been pricing margin at a quote the chain had
# already rejected, flattering every levered study in this repository by 52 bps (r103's lesson, one layer down: the fee
# *literals* were sourced in round 94 and the *carry* literal was not). See `cost_conventions.py`, which reprints this fact.
import paper                                   # noqa: E402  the posted desk quote, not a local opinion

BORROW_SPREAD = paper.BORROW_SPREAD
MAINTENANCE_EQUITY = 0.30  # a lender cuts the book at this cushion
BAND = 0.10
WRAPPER_EXPENSE = 0.0090   # a leveraged fund's real expense ratio, on its own NAV
WRAPPER_SPREAD = 0.0025    # what it costs to move money into one

# Expense ratios, real and per-sleeve, listed separately because the whole reason to
# prefer VOO to SPY is six bps, and six bps is exactly the sort of number a withdrawal
# table should display rather than fold into a rounding convention.
#: The five funds this file grades, at the ratios `fund_fees.py` sources them at. It remains a deliberate short list, and the
#: reason is publication and window length, not a fee lookup: `sleeve_table.py` swept IWM, EFA and EEM in round 102 and printed
#: what they did to a published law, and this file's 20-year withdrawal tables would be re-published end to end by the same three
#: legs. VOO is refused by the arithmetic here rather than by scope — 192 months cannot make a 20-year window.
import fund_fees                                # noqa: E402  after the module path is real

EXPENSE = {symbol: fund_fees.fee_for(symbol) for symbol in ("SPY", "VOO", "VTI", "ITOT", "QQQ")}

SLEEVES = ("SPY", "QQQ", "VTI", "ITOT", "VOO")
LEVERS = (1.0, 1.25, 1.5, 1.75, 2.0)

WINDOW_YEARS = 20
START_STRIDE = 3           # every third month is a start date; ~55 starts per sleeve


@dataclass(frozen=True, slots=True)
class Run:
    survived: bool
    calls: int
    paid: float
    ending: float
    cuts: int = 0        # how many times a guardrail reduced the cheque
    smallest: float = 0.0  # the least that was ever actually handed over
    traded: float = 0.0  # cumulative units of the book moved, in dollars


def run(
    returns: list[float],
    cash_rate: list[float],
    lever: float,
    first_withdrawal: float,
    expense: float,
    inflate: float = 0.025,
    band: float = BAND,
    instrument: str = "margin",
    maintenance: float = MAINTENANCE_EQUITY,
    spread: float = BORROW_SPREAD,
    guard: tuple[float, float] | None = None,
    targets: list[float] | None = None,
    fraction: float | None = None,
) -> Run:
    """One start date. A lump, a monthly withdrawal, a target path or a constant leverage.

    `targets`, when given, overrides `lever` month by month and is how a *policy* rather
    than a constant weight is scored. It must be the window's own slice rather than a global
    series: a window is a start date, and reaching backwards through a shared array to find
    the alignment is exactly the off-by-one that turns a trend gate into a crystal ball.
    Every caller therefore carries targets inside the window tuple it passes.

    `fraction`, when set, makes the cheque a proportion of the account's current value each month instead
    of a dollar amount decided in advance. It is the only withdrawal rule here that cannot die, and the only
    one whose promise is made in percentage points rather than dollars, which is why it is scored against
    the others at an equal *floor* in `income_frontier.py` and never side by side with them at an equal first
    cheque. It refuses to be combined with `guard` or `inflate`: a cheque that is simultaneously a fraction,
    an index and a guardrail is three products, and silently dropping two of the three flags is how a
    simulator starts telling stories.

    Margin mode carries position and cash separately, because two of the questions here —
    how much is borrowed, and is the cushion still above maintenance — have no answer in a
    single balance figure. Wrapper mode carries one line, because a fund holds no loan and
    a single balance is the complete truth about it.
    """

    if fraction is not None and (guard is not None or inflate != 0.0):
        raise ValueError("a fractional cheque cannot also be indexed or guarded; pick one product")
    if fraction is not None and not 0.0 < fraction < 1.0:
        raise ValueError(f"fraction {fraction} is not a monthly withdrawal rate")

    if instrument == "wrapper":
        if targets is not None:
            # A wrapper's leverage is set by its issuer, so a varying weight inside one is
            # not the same instrument: it is a fund plus a cash line, with the fund's 90 bps
            # on the fund and nothing on the cash. Refusing beats approximating it as a
            # margin book and calling the result a wrapper comparison.
            raise NotImplementedError("a target path inside a wrapper is a fund-plus-cash "
                                      "portfolio, which is a different instrument")
        return _run_wrapper(returns, cash_rate, lever, first_withdrawal, inflate, spread,
                            guard)

    def weight(month: int) -> float:
        if targets is None:
            return lever
        # Clamped rather than raised at the end of the window: the closing rebalance is
        # asked for after the last month's return, and a path has nothing to say about a
        # month that is not in it. Holding the last known weight keeps this identical to a
        # constant leverage on the final step, which is the only defensible reading.
        return targets[month] if month < len(targets) else targets[-1]

    position = weight(0) * START
    cash = START - position
    paid = 0.0
    calls = 0
    cuts = 0
    smallest = first_withdrawal
    high = START
    traded = 0.0

    for month in range(len(returns)):
        position *= 1.0 + (returns[month] - expense / 12.0)
        # Carry on the cash line in whichever direction it sits. A levered book's cash
        # line is a loan, and accruing it at the cash rate instead of the margin rate is
        # the flattery the paper book was caught doing at 128% exposure.
        cash *= 1.0 + (cash_rate[month] if cash >= 0.0
                       else cash_rate[month] + spread / 12.0)
        value = position + cash
        # Ruin is the account, not the sleeve. The test used to read `value <= 0 or position <= 0`, which is
        # the same event for a book that is all sleeve and a wrong one for a plan that never held a sleeve: a
        # cash account was scored ruined in its first month, so every "just hold T-bills" row this tool could
        # have produced came back dead. It was also wrong for a 50/50 account, whose sleeve can be sold down
        # to nothing by a cheque and bought back at the next rebalance — a plan with 90% of itself in cash is
        # off target, not dead. A levered book cannot reach this state with money left: its cash line is a
        # loan, so position <= 0 with value > 0 is arithmetically impossible, and the maintenance test below
        # is what governs a loan.
        if value <= 0.0:
            return Run(False, calls, paid, max(0.0, value), cuts, smallest, traded)

        withdrawal = (fraction * value if fraction is not None
                      else first_withdrawal * (1.0 + inflate) ** (month / 12.0))
        if fraction is None and guard and value < high * (1.0 - guard[0]):
            withdrawal *= guard[1]
            cuts += 1
        smallest = withdrawal if month == 0 else min(smallest, withdrawal)
        high = max(high, value)
        # The cheque is funded by selling the sleeve first and drawing the cash line only for what the
        # sleeve cannot cover, which is what the module docstring promised and the old one-line version
        # did not do. Selling more sleeve than the account holds is the same category of error as the
        # ruin test above, and it is impossible to reach at a full equity weight — which is why it took a
        # cash plan to matter.
        sold = min(position, withdrawal)
        position -= sold * (1.0 + TURNOVER_COST)
        cash -= withdrawal - sold
        paid += withdrawal
        traded += withdrawal
        value = position + cash
        if value <= 0.0:
            return Run(False, calls, paid, max(0.0, value), cuts, smallest, traded)

        if value < maintenance * position:
            # Force the sale a lender would force. The fee comes off the position, not
            # the cash line: a fee taken from cash would manufacture a loan no lender
            # agreed to, which is the same defect in a different costume.
            trim = position - value
            position = value - trim * TURNOVER_COST
            cash = 0.0
            calls += 1
            traded += trim

        value = position + cash
        delta = weight(month + 1) * value - position
        if abs(delta) > band * value:
            cost = abs(delta) * TURNOVER_COST
            cash -= delta + cost
            position += delta
            traded += abs(delta)

    return Run(True, calls, paid, position + cash, cuts, smallest, traded)


def _run_wrapper(
    returns: list[float],
    cash_rate: list[float],
    lever: float,
    first_withdrawal: float,
    inflate: float,
    spread: float,
    guard: tuple[float, float] | None = None,
) -> Run:
    """The same plan inside a leveraged fund: fully invested, levered internally, not callable.

    The account owns one thing, so there is no rebalance to perform and no band to
    respect — the fund's leverage is the issuer's problem, not this account's. What the
    account pays is the fund's return, the fund's expense on its own NAV, and its spread
    on every withdrawal. There is no maintenance test because there is no loan secured by
    anything: a leveraged ETF can go to zero and cannot be force-sold at the bottom, which
    is the entire reason it exists and the reason it is priced as an instrument rather
    than as a convenience.
    """

    balance = START
    paid = 0.0
    cuts = 0
    smallest = first_withdrawal
    high = START
    for month in range(len(returns)):
        balance *= 1.0 + (
            lever * returns[month]
            - (lever - 1.0) * (cash_rate[month] + spread / 12.0)
            - WRAPPER_EXPENSE / 12.0
        )
        if balance <= 0.0:
            return Run(False, 0, paid, 0.0, cuts, smallest)
        withdrawal = first_withdrawal * (1.0 + inflate) ** (month / 12.0)
        if guard and balance < high * (1.0 - guard[0]):
            withdrawal *= guard[1]
            cuts += 1
        smallest = withdrawal if month == 0 else min(smallest, withdrawal)
        high = max(high, balance)
        balance -= withdrawal * (1.0 + WRAPPER_SPREAD)
        paid += withdrawal
        if balance <= 0.0:
            return Run(False, 0, paid, 0.0, cuts, smallest)
    return Run(True, 0, paid, balance, cuts, smallest)


def smallest_cheque(
    windows: list[tuple], lever: float, expense: float, inflate: float, instrument: str,
    maintenance: float, spread: float, guard: tuple[float, float] | None, fraction: float,
) -> float:
    """The least ever handed over, across every start date, at this withdrawal.

    A guardrail's headline is the first cheque and its truth is the smallest one. Quoting
    only the first would let a policy that halves the spending in a bear market be compared
    against a fixed policy as though the larger number were the same promise, which is how
    a "safe" 8% figure ends up on a retirement pamphlet.
    """

    if not windows:
        raise ValueError("no windows means nothing survived and nothing failed; refuse")
    worst = fraction * START
    if lever <= 0.0 and any(len(window) < 4 or window[3] is None for window in windows):
        raise ValueError("a zero leverage with no target path scores an empty account, "
                         "not a policy")
    for window in windows:
        returns, cash_rate, _start = window[:3]
        path = window[3] if len(window) > 3 else None
        outcome = run(returns, cash_rate, lever, fraction * START, expense, inflate,
                      instrument=instrument, maintenance=maintenance, spread=spread,
                      guard=guard, targets=path)
        if outcome.survived:
            worst = min(worst, outcome.smallest)
    return worst


def reliable(
    windows: list[tuple],
    lever: float,
    expense: float,
    inflate: float,
    fraction: float,
    instrument: str,
    maintenance: float,
    spread: float = BORROW_SPREAD,
    guard: tuple[float, float] | None = None,
) -> bool:
    """Does every start date pay this withdrawal, with no forced sale anywhere?"""

    withdrawal = fraction * START
    for window in windows:
        returns, cash_rate, _start = window[:3]
        path = window[3] if len(window) > 3 else None
        outcome = run(returns, cash_rate, lever, withdrawal, expense, inflate,
                      instrument=instrument, maintenance=maintenance, spread=spread,
                      guard=guard, targets=path)
        if not outcome.survived or outcome.calls:
            return False
    return True


def capacity(
    windows: list[tuple],
    lever: float,
    expense: float,
    inflate: float = 0.025,
    instrument: str = "margin",
    maintenance: float = MAINTENANCE_EQUITY,
    spread: float = BORROW_SPREAD,
    guard: tuple[float, float] | None = None,
    ceiling: float = 0.06,
    tolerance: float = 0.00002,
    steps: int = 40,
) -> tuple[float, int, str]:
    """The largest monthly withdrawal every start date survives, plus two warnings.

    Returns (frontier, gaps, binding start). `gaps` is the answer to a question a bisection
    cannot ask for itself: is "survives" actually monotone in the withdrawal? It looks
    obviously true and it is not. A larger withdrawal sells more of the position, and a
    smaller position is a *higher* equity ratio, so under a maintenance rule withdrawing
    more can talk a run out of the forced sale that a smaller withdrawal suffers. If that
    happens the passing set is not an interval, and a bisection would return some boundary
    and call it the maximum. So the predicate is probed on a grid first, anything that
    passes above the frontier is counted, and the frontier reported is the first failure —
    the largest withdrawal that is reliable *all the way down to zero*, which is the
    property anyone spending the money actually needs.

    `binding start` names the window that sets the number, because a headline figure with
    no date attached invites the reader to imagine their own start date, and the answer to
    this question is mostly about which one they picked.
    """

    if not windows:
        raise ValueError("no windows means nothing survived and nothing failed; refuse")

    # Callers scoring a target path pass `lever` as a dead 0.0, because the path is the
    # exposure. That sentinel is only safe if it is checked: a window list that quietly lost
    # its paths would otherwise be scored as a zero-position account, die by month two, and
    # report a frontier of $0 as though that were a finding about the policy.
    if lever <= 0.0 and any(len(window) < 4 or window[3] is None for window in windows):
        raise ValueError("a zero leverage with no target path scores an empty account, "
                         "not a policy")

    probe = [ceiling * (i + 1) / steps for i in range(steps)]
    passing = [f for f in probe
               if reliable(windows, lever, expense, inflate, f, instrument, maintenance, spread,
                guard)]
    if not passing:
        return 0.0, 0, "none"
    lowest_failure = next((f for f in probe if f not in passing), ceiling)
    gaps = sum(1 for f in passing if lowest_failure is not None and f > lowest_failure)

    lo, hi = (passing[-1] if passing else 0.0), lowest_failure
    while hi - lo > tolerance:
        mid = (lo + hi) / 2.0
        if reliable(windows, lever, expense, inflate, mid, instrument, maintenance,
                    spread, guard):
            lo = mid
        else:
            hi = mid

    # Probed just *above* the frontier, not at the midpoint: at or below the frontier
    # nothing fails, and a binding window reported as "none" would be a bug pretending to
    # be a result.
    binding = "none"
    for window in windows:
        returns, cash_rate, start = window[:3]
        path = window[3] if len(window) > 3 else None
        outcome = run(returns, cash_rate, lever, hi * START * 1.001, expense, inflate,
                      instrument=instrument, maintenance=maintenance, spread=spread,
                      guard=guard, targets=path)
        if not outcome.survived or outcome.calls:
            binding = f"{start:%Y-%m}"
            break
    return lo, gaps, binding


def per_window(
    windows: list[tuple],
    lever: float,
    expense: float,
    inflate: float,
    instrument: str,
    maintenance: float,
    spread: float,
    guard: tuple[float, float] | None = None,
    ceiling: float = 0.06,
    tolerance: float = 0.00005,
    steps: int = 200,
) -> list[float]:
    """What each individual start date could have paid. The distribution, not its floor.

    Reported next to the guarantee because the two move in opposite directions, and a table
    that shows only the minimum talks the reader out of leverage while a table that shows
    only the mean talks them into ruin. The whole decision is the shape between them.
    """

    if not windows:
        raise ValueError("no windows means nothing survived and nothing failed; refuse")
    out: list[float] = []
    for window in windows:
        # The window travels whole. Unpacking it and reassembling a 3-tuple silently scored
        # every policy window at the constant leverage argument instead — which the caller
        # passes as a dead 0.0 sentinel for path rows, so the median column came back 0 and
        # read like a finding. A target path is not an annotation on a window, it is part of
        # the window.
        single = [window]
        # A coarse grid is fine for a floor — one number, and it is the grid's *lowest*
        # passing cell that matters — but a median read off $150 cells makes three
        # different leverages look identical to the dollar, which is an artefact of the
        # search pretending to be a result.
        out.append(capacity(single, lever, expense, inflate, instrument, maintenance,
                            spread, guard, ceiling, tolerance, steps)[0])
    return out


def monthly(
    series: dict[date, float], factors: dict[date, float]
) -> tuple[list[float], list[float], list[date]]:
    """Daily closes to (monthly returns, monthly net cash rate, month keys), aligned."""

    closes: list[float] = []
    factor_month: list[float] = []
    keys: list[date] = []
    for day in sorted(series):
        if keys and (keys[-1].year, keys[-1].month) == (day.year, day.month):
            closes[-1] = series[day]
            factor_month[-1] *= factors.get(day, 1.0)
            continue
        keys.append(day)
        closes.append(series[day])
        factor_month.append(factors.get(day, 1.0))
    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    rates = [factor_month[i] - 1.0 for i in range(1, len(closes))]
    return returns, rates, keys[1:]


def last_business_day(year: int, month: int) -> date:
    """The last weekday of a calendar month. Round 47's defect in one line: the archive seals after a session, so
    its final month is usually a stub, and any statistic that annualises the tail is pricing days that were never
    traded. Defined here rather than in `cash_yield_gap`, which found the bug, because every consumer of `monthly`
    inherits it and this is the module they all import.
    """

    d = date(year, month, calendar.monthrange(year, month)[1])
    while d.weekday() > 4:
        d -= timedelta(days=1)
    return d


def monthly_complete(
    series: dict[date, float], factors: dict[date, float], last_date: date
) -> tuple[list[float], list[float], list[date]]:
    """`monthly()`, minus a trailing month whose calendar month has not finished.

    Returns the same triple. A bucket is dropped only when `last_date` has not reached its month's last weekday,
    so a seal that happens to land on a month end keeps the month, and a four-day September keeps nothing.
    Spot-anchored statistics must read this function; window minima and full-history statistics provably do not
    care, which is the invariant the blast-radius tests pin.
    """

    rets, rates, keys = monthly(series, factors)
    if keys and last_date < last_business_day(keys[-1].year, keys[-1].month):
        return rets[:-1], rates[:-1], keys[:-1]
    return rets, rates, keys


def windows_for(
    returns: list[float], cash_rate: list[float], keys: list[date], years: int, stride: int,
    weights: list[float] | None = None,
) -> list[tuple]:
    """Start dates, each carrying its own aligned slice of a target-weight path.

    The path travels inside the window rather than as a second list indexed by position, so
    that no caller can line a weight up against the wrong month. A policy window and a
    constant-weight window are then the same shape and go through the same code.
    """

    months = years * 12
    if len(returns) < months:
        return []
    if weights is not None and len(weights) != len(returns):
        raise ValueError("the weight path must be the same length as the return series")
    return [
        (returns[i:i + months], cash_rate[i:i + months], keys[i],
         weights[i:i + months] if weights is not None else None)
        if weights is not None else
        (returns[i:i + months], cash_rate[i:i + months], keys[i])
        for i in range(0, len(returns) - months + 1, stride)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window-years", type=int, default=WINDOW_YEARS)
    parser.add_argument("--stride", type=int, default=START_STRIDE)
    parser.add_argument("--sleeve", default=None, help="restrict to one symbol")
    parser.add_argument("--lever", type=float, default=None, help="restrict to one leverage")
    parser.add_argument("--inflate", type=float, default=0.025,
                        help="annual indexation of the withdrawal (default 2.5%)")
    parser.add_argument("--instrument", choices=("margin", "wrapper"), default="margin",
                        help="retail margin (callable) or a leveraged-ETF wrapper (not)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--guardrail", type=float, default=None,
                        help="cut the withdrawal by --cut when the account falls this "
                             "far below its high water mark (e.g. 0.25)")
    parser.add_argument("--cut", type=float, default=0.5,
                        help="fraction of the withdrawal to keep after a guardrail cut")
    parser.add_argument("--spread", type=float, default=BORROW_SPREAD,
                        help="financing spread over cash; 0 isolates sequence risk "
                             "from cost of carry")
    parser.add_argument("--maintenance", type=float, default=MAINTENANCE_EQUITY,
                        help="equity cushion at which a lender cuts the book to 1x")
    args = parser.parse_args()

    data = load_csv_market_data(SNAPSHOT, CASH_FILE)
    sleeves = (args.sleeve,) if args.sleeve else SLEEVES
    levers = tuple(l for l in LEVERS if args.lever is None or l == args.lever)
    maintenance = 0.0 if args.instrument == "wrapper" else args.maintenance
    guard = None if args.guardrail is None else (args.guardrail, args.cut)

    print(f"reliable withdrawal capacity · {args.window_years}-year plans on a "
          f"${START:,.0f} lump · {args.instrument}")
    print(f"financing archive cash + {BORROW_SPREAD:.2%} · lender's cushion "
          f"{maintenance:.0%} · withdrawal indexed {args.inflate:.1%}/yr"
          f" · spread {args.spread:.2%}")
    print("every number below is the WORST start date in the record, not the average"
          + (f" · guardrail: withdraw {args.cut:.0%} below {args.guardrail:.0%} of high"
             if guard else "") + "\n")
    if guard:
        print("with a guardrail the quoted figure is the FIRST cheque, not a promised "
              "one: the contract is that it gets cut, so it is a different product from "
              "the fixed row and must not be read as the same promise made bigger\n")
    print(f"{'sleeve':6} {'lev':>5} {'starts':>7} {'first cheque':>13} "
          f"{'smallest':>11} {'median':>9} {'%/yr':>6} {'vs median':>10}   reading")

    for symbol in sleeves:
        series = {d: data.by_date[d][symbol].close for d in data.by_date
                  if symbol in data.by_date[d]}
        if not series:
            print(f"{symbol:6} not in this archive")
            continue
        returns, cash_rate, keys = monthly(series, data.cash_factors)
        windows = windows_for(returns, cash_rate, keys, args.window_years, args.stride)
        if not windows:
            print(f"{symbol:6} only {len(returns)} months of history — no "
                  f"{args.window_years}-year window exists. No number is printed rather "
                  f"than a short one.")
            continue
        expense = EXPENSE.get(symbol, 0.0)
        # The Dominance bar is always plain ownership, never "the same instrument at 1x".
        # A one-times leveraged fund is not a product anyone can buy, so judging a wrapper
        # against a 1x wrapper would judge it against a benchmark that exists only inside
        # this file — round 6's lesson about a comparator priced to please, in a new
        # costume. Recomputed per sleeve rather than read off a neighbouring row.
        base, base_gaps, base_binding = capacity(
            windows, 1.0, expense, args.inflate, "margin", MAINTENANCE_EQUITY,
            args.spread, guard)
        base *= START
        base_each = sorted(per_window(windows, 1.0, expense, args.inflate, "margin",
                                      MAINTENANCE_EQUITY, args.spread, guard=guard))
        base_median = base_each[len(base_each) // 2] * START
        if args.verbose:
            print(f"  {symbol}: {len(windows)} windows from {len(returns)} months of "
                  f"history · gaps at 1x {base_gaps} · floor set by {base_binding}")
        for lever in levers:
            if args.instrument == "wrapper" and lever == 1.0:
                continue   # no such product; the bar for a wrapper is plain ownership
            fraction, gaps, binding = capacity(windows, lever, expense, args.inflate,
                                               args.instrument, maintenance, args.spread,
                                               guard)
            each = sorted(per_window(windows, lever, expense, args.inflate,
                                     args.instrument, maintenance, args.spread,
                                     guard=guard))
            median, best = each[len(each) // 2] * START, each[-1] * START
            dollars = fraction * START
            if lever == 1.0:
                delta, reading = "—", "the bar every other row must clear"
            else:
                delta = f"{median - base_median:+,.0f}"
                # A difference smaller than the search's own step is not a result. The grid
                # resolves to about $30 a month here, and a table that prints "+$4" as
                # "pays more" manufactures a conclusion out of a rounding convention —
                # round 3's SE discipline, applied to the bisection that produces this
                # number rather than to the returns that feed it.
                if abs(median - base_median) < 40.0:
                    reading = "typical start indistinguishable from owning it"
                else:
                    reading = ("typical start pays LESS than owning it"
                               if median < base_median else "typical start pays more")
                if dollars == 0.0:
                    reading = "NO withdrawal survives every start"
            if len(windows) < 25:
                reading += " (thin: few starts)"
            if gaps:
                reading += f" ({gaps} non-monotone)"
            if args.verbose and binding not in ("none", "ceiling", "never"):
                reading += f"   [{binding} sets the floor]"
            floor_cheque = smallest_cheque(windows, lever, expense, args.inflate,
                                           args.instrument, maintenance, args.spread,
                                           guard, fraction)
            print(f"{symbol:6} {lever:5.2f} {len(windows):7d} {dollars:12,.0f} "
                  f"{floor_cheque:11,.0f} {median:9,.0f} {fraction * 12 * 100:8.2f}% "
                  f"{delta:>10}   {reading}")


if __name__ == "__main__":
    raise SystemExit(main())
