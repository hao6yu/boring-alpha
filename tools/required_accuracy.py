"""What accuracy a market-timer needs to beat doing nothing — measured, not opined.

Run: .venv/bin/python tools/required_accuracy.py

Two rounds of candidates have lost on dollars while often winning on risk, which
raises the only question worth asking before writing a fourth: how good does a
signal have to be to clear the toll at all? If the answer is "far better than
anything measurable from public daily data", then continuing to search is a
hobby, not a plan, and it is worth saying so plainly. If the answer is "modestly
better", the search is worth funding.

Method. A timer holds either the fund or cash, decides once a week, and pays two
legs whenever it switches states. Skill is parameterised directly: on each week it
picks the better of the two states with probability p, and the worse one otherwise.
That is an abstract model of a signal, not a backtest of one — no look-ahead is
being smuggled in, because the ex-post better state is used only to *assign* an
accuracy, never to form a position. Buy-and-hold appears as the special case where
the timer is always long, so its accuracy equals the base rate of weeks the fund
beat cash and it pays no switching cost at all. That is the bar, and it is higher
than a coin flip for exactly that reason.

Same costs as the rest of the research: expense ratio on the fund while long,
borrowing irrelevant here since the flat state holds cash rather than no exposure,
and per-leg costs applied to the whole book at every state change.

    .venv/bin/python tools/required_accuracy.py --cost-bps 0.3 --reps 400
"""

from __future__ import annotations

import argparse
from datetime import date
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boring_alpha.data.csv_loader import load_csv_market_data

SNAPSHOT = ROOT / "data" / "snapshots" / "20260904T192633Z" / "market_daily.csv"
CASH_FILE = ROOT / "data" / "snapshots" / "20260904T192633Z" / "cash_daily.csv"
SYMBOL = "SPY"

EXPENSE = 0.000945
OPENING = 5_000.0
MONTHLY = 500.0
SESSIONS_PER_WEEK = 5
ACCURACIES = (0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.64, 0.66, 0.68, 0.70, 0.75)

WINDOWS = {
    "full 1993..2026": (date(1993, 1, 1), date(2026, 9, 30)),
    "seen A 2007-06..2017-12": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B 2018..2021": (date(2018, 1, 1), date(2021, 12, 31)),
    "recent 2022..2026": (date(2022, 1, 1), date(2026, 9, 30)),
}


def weekly_bars(data, bounds):
    """Compound sessions into five-session bars, with cash accrued over the same span."""

    dates = [d for d in data.dates if d >= bounds[0] and SYMBOL in data.by_date[d]]
    bars, starts, deposits = [], [], []
    index = 1
    month = None
    while index + SESSIONS_PER_WEEK - 1 < len(dates):
        window = dates[index - 1:index + SESSIONS_PER_WEEK]
        first, last = data.by_date[window[0]][SYMBOL], data.by_date[window[-1]][SYMBOL]
        equity = last.close / first.close - 1.0
        cash = math.prod(data.cash_factors[d] for d in window[1:]) * (
            (1.0 - EXPENSE) ** (SESSIONS_PER_WEEK / 252.0)
        ) - 1.0
        deposit = 0.0
        stamp = window[-1]
        if month != (stamp.year, stamp.month):
            month = (stamp.year, stamp.month)
            deposit = MONTHLY
        bars.append((equity, cash, deposit))
        starts.append(window[0])
        index += SESSIONS_PER_WEEK
    return bars, starts


def run(bars, accuracy, cost_per_leg, seed):
    """One simulated timer. Returns ending value and number of state changes."""

    rng = random.Random(seed)
    value = OPENING
    held = True
    switches = 0
    for equity, cash, deposit in bars:
        value += deposit
        better = equity > cash
        chosen = better if rng.random() < accuracy else not better
        want = chosen          # the call picks the leg outright; it does not nudge the last position
        if want != held:
            value -= value * 2.0 * cost_per_leg
            switches += 1
            held = want
        value *= (1.0 + equity) if held else (1.0 + cash)
    return value, switches


def buy_and_hold(bars, cost_per_leg):
    value, switches = OPENING, 0
    first = True
    for _equity, _cash, deposit in bars:
        value += deposit
        if first:
            value -= value * 2.0 * cost_per_leg
            switches += 1
            first = False
        value *= 1.0 + _equity
    return value, switches


def achieved_accuracy(data, bounds, rule):
    """How accurate an actual rule was, on the same weekly grid and definition."""

    bars, starts = weekly_bars(data, bounds)
    dates = [d for d in data.dates if d >= bounds[0] and SYMBOL in data.by_date[d]]
    hits = weeks = 0
    for position, (equity, cash, _deposit) in enumerate(bars):
        signal = rule(data, dates, starts[position])
        if signal is None:
            continue
        weeks += 1
        hits += int(signal == (equity > cash))
    return (hits / weeks if weeks else 0.0), weeks


def trend_rule(window):
    def rule(data, dates, asof):
        prior = [d for d in dates if d <= asof]
        if len(prior) < window + 1:
            return None
        reference = data.by_date[prior[-1]][SYMBOL].close
        average = sum(
            data.by_date[d][SYMBOL].close for d in prior[-window:]
        ) / window
        return reference > average
    return rule


def momentum_rule(weeks):
    def rule(data, dates, asof):
        prior = [d for d in dates if d <= asof]
        need = weeks * SESSIONS_PER_WEEK
        if len(prior) < need + 1:
            return None
        return (data.by_date[prior[-1]][SYMBOL].close
                / data.by_date[prior[-1 - need]][SYMBOL].close - 1.0) > 0.0
    return rule


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cost-bps", type=float, action="append")
    parser.add_argument("--reps", type=int, default=300)
    args = parser.parse_args()
    costs = args.cost_bps or [0.3, 1.0, 2.0]
    data = load_csv_market_data(SNAPSHOT, CASH_FILE, end=date(2026, 9, 30))

    print("required accuracy for a weekly market/flat timer to beat plain DCA\n")
    for label, bounds in WINDOWS.items():
        bars, _starts = weekly_bars(data, bounds)
        if len(bars) < 100:
            continue
        base = sum(1 for e, c, _ in bars if e > c) / len(bars)
        print(f"=== {label}: {len(bars)} weeks, {base * 100:.1f}% of weeks the fund beat cash "
              f"(that free accuracy IS buy-and-hold) ===")
        growth = sorted((math.log(1.0 + e) for e, _c, _d in bars), reverse=True)
        total = sum(growth)
        if total > 0:
            for share in (0.01, 0.05):
                k = max(1, int(round(share * len(growth))))
                print(f"    concentration: the best {k:>3} weeks ({share:.0%} of them) "
                      f"carry {sum(growth[:k]) / total * 100:,.0f}% of the fund's log growth, "
                      f"so a timer that is right on the average week but blind to "
                      f"those weeks is not slightly worse, it is structurally worse.")
        paid_in = OPENING + sum(d for _, _, d in bars)
        crossings = {}
        for one_way in costs:
            hold, _ = buy_and_hold(bars, one_way / 10_000.0)
            line = []
            crossing = None
            for accuracy in ACCURACIES:
                values, switches = [], []
                for rep in range(args.reps):
                    value, count = run(bars, accuracy, one_way / 10_000.0, 1_000 + rep)
                    values.append(value)
                    switches.append(count)
                mean = sum(values) / len(values)
                gap = mean - hold
                line.append((accuracy, gap, sum(switches) / len(switches)))
                if gap > 0 and crossing is None:
                    crossing = accuracy
            crossings[one_way] = crossing
            text = "  ".join(f"{a:.0%}:{g / hold * 100:+5.1f}%" for a, g, _ in line)
            print(f"  {one_way:>4.1f} bps/leg  break-even accuracy "
                  f"{'none of the grid' if crossing is None else f'{crossing:.0%}'}   "
                  f"({text})")
        # The bar that matters is the one at the dearest cost: a rule that only
        # works at frictionless prices is not a rule.
        need = max(v for v in crossings.values() if v is not None) if any(
            v is not None for v in crossings.values()) else None
        print(f"  achieved by rules that actually exist here, against the "
              f"{max(costs):.1f} bps/leg bar of "
              f"{('%.0f%%' % (need * 100)) if need else 'beyond the grid'}:")
        for name, rule in (("200-session trend", trend_rule(200)),
                           ("50-session trend", trend_rule(50)),
                           ("4-week momentum", momentum_rule(4)),
                           ("13-week momentum", momentum_rule(13))):
            accuracy, weeks = achieved_accuracy(data, bounds, rule)
            se = math.sqrt(max(accuracy, 1e-9) * (1 - accuracy) / max(weeks, 1))
            edge = (accuracy - need) / se if (need and se) else float("nan")
            verdict = ("clears" if edge > 1.96 else
                       "short" if edge < 0 else "inside noise")
            print(f"    {name:<18} {accuracy * 100:>5.1f}% over {weeks:>4} weeks"
                  f"   {(accuracy - need) * 100 if need else 0:+5.1f} pp"
                  f" = {edge:+.2f} SE   {verdict}")
        print()

    print("Read it as a toll, not a forecast. A timer must clear the base rate AND")
    print("the switching cost from the same accuracy, and every point of accuracy in")
    print("this table is a weekly coin flip won more often than chance, quarter after")
    print("quarter, for as long as the account is held.")


if __name__ == "__main__":
    main()
