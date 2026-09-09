"""Score a trading policy in the only unit the objective is written in: monthly income.

Run: .venv/bin/python tools/policy_withdrawal.py [--sleeve SPY] [--window-years 20]

Round 7 settled something uncomfortable. On a *withdrawal* basis, leverage on an index sleeve
lowers the reliable monthly amount at every leverage — with financing free, and worse inside
a wrapper — while leaving the average untouched. Leverage buys dispersion, not income.
Accumulation numbers said the opposite and both are correct: nobody was taking money out in
accumulation numbers.

That leaves exactly one unasked question, and it is the best one available. The candidate is
not constant leverage. It is a volatility target with a 200-day trend gate and a 30% floor,
and the single regime that sets round 7's floor — the 2000 to 2002 collapse — is precisely
the regime a trend gate claims to read. If any mechanism here is going to raise a floor, this
is the one that claims it can, and the floor is the thing the goal actually needs.

The engine, the costs, and the bisection are imported from `withdrawal_capacity` rather than
re-implemented: two simulators that drift apart is the failure mode round 6 named, and a
policy scored by a second engine is a policy scored twice.

## The controls, and what each one refutes

A volatility target with a 1.3x cap spends most of its time pinned near the cap, so "the
policy beat the index" is confounded with "the policy holds more leverage" unless something
holds leverage fixed. Five rows, each answering a different accusation:

  flat 1.00x        the index. The Dominance Rule. Losing here is Redundant.
  flat at the       the policy's average weight, decided zero times. Losing here means the
   policy's own     machinery bought nothing and a spreadsheet cell would have done it.
   average
  gateless          vol target, no trend gate. Losing here means the 200-day average is
                    decoration and only the volatility estimate is working.
  candidate         the thing under test.
  candidate,      the candidate's own weights, read backwards. Same numbers, same average
  wrong months    over the whole record, same time spent at each weight — only the order
                  differs, so anything this row cannot match is timing and not exposure. It
                  is the row that decides whether the result is a trading rule or a smaller
                  position, and it is the one that has to lose. Individual windows do carry
                  a different mean weight under a reversal; that redistribution *is* the
                  timing, which is why this control is not the same thing as the flat row.

And one control that is not a row but a check: `test_alignment_shift_matters` in
`tests/test_policy_withdrawal.py`, which shows that sliding the weight path forward or back
by a single month changes the answer materially. If it did not, the careful alignment in
`monthly_weights` would be a stylistic preference rather than the difference between a
trading rule and a look-ahead.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boring_alpha.data.csv_loader import load_csv_market_data
from boring_alpha.signals.voltarget import VolTargetPolicy

import withdrawal_capacity as wc

# The pre-registered candidate, verbatim from tools/paper.py: an 18% vol target on a 30-day
# window, a 200-day trend gate, a 30% floor, a 1.30x cap, a ten-percent band, five-session
# review. Nothing here is retuned — changing any of those five numbers is a new candidate,
# and finding the best of a grid on the same data used to judge it is what killed BA-004.
CANDIDATE = VolTargetPolicy(target_vol=0.18, vol_window=30, trend_window=200,
                            max_weight=1.3, min_weight=0.3, rebalance_band=0.10,
                            review_every=5)
GATELESS = VolTargetPolicy(target_vol=0.18, vol_window=30, trend_window=None,
                           max_weight=1.3, min_weight=0.3, rebalance_band=0.10,
                           review_every=5)

SLEEVES = ("SPY", "QQQ", "VTI", "ITOT")
EXPENSE = wc.EXPENSE


def monthly_weights(policy: VolTargetPolicy, days: list[date], closes: list[float],
                    keys: list[date], lag: int = 0) -> list[float]:
    """One weight per month: what the policy wants on that month's first session.

    `raw_weights` emits, for session *t*, the weight decided from data through *t-1* — the
    volatility window and the trend average are both `values[t-window:t]`, strictly prior.
    Taking that value at each month's first session is therefore exactly the exposure the
    policy holds through that month, with no look-ahead and no averaging to argue about.

    The monthly approximation is stated rather than hidden: the live book reviews every five
    sessions and this reviews at the month boundary, which *understates* the policy's
    responsiveness. If the gate fails here it may be the cadence, not the rule, and that is a
    claim the forward book can settle and this table cannot.

    `lag` exists only for the test that proves the alignment matters. Zero in production.
    """

    returns = [0.0] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    desired = policy.raw_weights(closes, returns)
    first_of_month: dict[tuple[int, int], int] = {}
    for index, day in enumerate(days):
        first_of_month.setdefault((day.year, day.month), index)
    out: list[float] = []
    for month in keys:
        index = first_of_month.get((month.year, month.month))
        if index is not None and lag:
            index = min(max(index + lag, 0), len(days) - 1)
        weight = None if index is None else desired[index]
        # Before the windows fill the policy declines to answer. Holding the floor rather
        # than skipping the month is the conservative reading: it keeps the risk on. The
        # live paper book sits in cash for exactly those thirty sessions, so this is the
        # harder of the two readings, not the flattering one — and it is two months of 1993,
        # nowhere near the window that sets any number below.
        out.append(CANDIDATE.min_weight if weight is None else weight)
    return out


def report(symbol: str, book: str, windows: list[tuple], lever: float, args,
           average: float | None = None) -> tuple[float, float, float, str, list[float]]:
    """Print one row of the table and hand back what the verdict line needs.

    The per-window list comes back in window order, unsorted, on purpose: the verdict pairs
    it against another row's list start-for-start, and a sorted list would have paired
    1998-05's candidate with 2015-02's control and called the correlation a result.
    """

    fraction, gaps, binding = wc.capacity(
        windows, lever, EXPENSE.get(symbol, 0.0), args.inflate, "margin",
        wc.MAINTENANCE_EQUITY, args.spread,
        None if args.guardrail is None else (args.guardrail, args.cut))
    first = fraction * wc.START
    smallest = wc.smallest_cheque(
        windows, lever, EXPENSE.get(symbol, 0.0), args.inflate, "margin",
        wc.MAINTENANCE_EQUITY, args.spread,
        None if args.guardrail is None else (args.guardrail, args.cut), fraction)
    each = wc.per_window(
        windows, lever, EXPENSE.get(symbol, 0.0), args.inflate, "margin",
        wc.MAINTENANCE_EQUITY, args.spread,
        None if args.guardrail is None else (args.guardrail, args.cut))
    median = sorted(each)[len(each) // 2] * wc.START
    shown = f"{average:.2f}" if average is not None else "  —"
    note = ""
    if gaps:
        note += f" {gaps} non-monotone"
    if binding not in ("none", "ceiling", "never"):
        note += f" {binding} sets the floor"
    print(f"{symbol:6} {book:16} {shown:>5} {len(windows):7d} {first:11,.0f} "
          f"{smallest:9,.0f} {median:8,.0f}{note}")
    return first, smallest, median, binding, [f * wc.START for f in each]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window-years", type=int, default=20)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--sleeve", default=None)
    parser.add_argument("--inflate", type=float, default=0.025)
    parser.add_argument("--spread", type=float, default=wc.BORROW_SPREAD)
    parser.add_argument("--guardrail", type=float, default=None)
    parser.add_argument("--cut", type=float, default=0.5)
    parser.add_argument("--lag", type=int, default=0,
                        help="shift the weight path by N months (diagnostic only)")
    args = parser.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    sleeves = (args.sleeve,) if args.sleeve else SLEEVES

    print(f"a trading policy scored as a spending plan · {args.window_years}-year "
          f"retirements · ${wc.START:,.0f} lump")
    print(f"candidate: {CANDIDATE.name}")
    print(f"costs: {wc.TURNOVER_COST * 1e4:.1f} bps turnover · cash + "
          f"{args.spread:.2%} financing · lender's cushion "
          f"{wc.MAINTENANCE_EQUITY:.0%} · indexed {args.inflate:.1%}")
    print("every figure is the WORST start month in the record\n")
    print(f"{'sleeve':6} {'book':16} {'avg lev':>7} {'starts':>7} {'first':>11} "
          f"{'smallest':>9} {'median':>8}   notes")

    for symbol in sleeves:
        bars = [(d, data.by_date[d][symbol]) for d in sorted(data.by_date)
                if symbol in data.by_date[d]]
        if not bars:
            print(f"{symbol:6} not in this archive")
            continue
        days = [d for d, _b in bars]
        closes = [b.close for _d, b in bars]
        returns, cash_rate, keys = wc.monthly({d: b.close for d, b in bars},
                                             data.cash_factors)
        plain = wc.windows_for(returns, cash_rate, keys, args.window_years, args.stride)
        if not plain:
            print(f"{symbol:6} only {len(returns)} months — no "
                  f"{args.window_years}-year window exists.")
            continue

        weights = monthly_weights(CANDIDATE, days, closes, keys, args.lag)
        gateless = monthly_weights(GATELESS, days, closes, keys, args.lag)
        scrambled = list(reversed(weights))
        gated = wc.windows_for(returns, cash_rate, keys, args.window_years, args.stride,
                              weights)
        ungated = wc.windows_for(returns, cash_rate, keys, args.window_years, args.stride,
                                gateless)
        reversed_windows = wc.windows_for(returns, cash_rate, keys, args.window_years,
                                         args.stride, scrambled)
        average = sum(weights) / len(weights)

        index_first = report(symbol, "flat 1.00x", plain, 1.0, args, 1.0)[0]
        flat_row = report(symbol, "flat at avg weight", plain, round(average, 2), args,
                          average)
        pol_row = report(symbol, "candidate", gated, 0.0, args, average)
        scram_row = report(symbol, "wrong months", reversed_windows, 0.0, args, average)
        gate_first = report(symbol, "no trend gate", ungated, 0.0, args,
                           sum(gateless) / len(gateless))[0]
        pol_first, pol_small, pol_med = pol_row[0], pol_row[1], pol_row[2]
        flat_first, flat_calls = flat_row[0], flat_row[4]
        scram_first = scram_row[0]

        def call(value: float, against: float, label: str) -> str:
            if abs(value - against) < 40.0:
                return f"indistinguishable from {label}"
            return f"beats {label}" if value > against else f"LOSES to {label}"

        verdict = ("REDUNDANT — the machinery buys no income" if pol_first <= flat_first
                   else "the policy earns its leverage")
        verdict += (" · DOMINATED by the index" if pol_first < index_first
                    else " · clears the index")
        verdict += f"; {call(pol_first, gate_first, 'the gateless version')}"
        # The row that has to lose. Same weights, same average, same time spent at each
        # weight, order reversed — so anything this row cannot match is timing.
        verdict += (f"; {call(pol_first, scram_first, 'the same weights in reverse')}"
                    if pol_first > scram_first else
                    f"; SCRAMBLED TIMING MATCHES IT (${scram_first - pol_first:,.0f} better "
                    f"backwards) — the win is exposure, not a trading rule")
        wins = sum(1 for ours, theirs in zip(pol_row[4], flat_calls) if ours > theirs + 1.0)
        worst_gap = min(ours - theirs for ours, theirs in zip(pol_row[4], flat_calls))
        print(f"{symbol:6} {'VERDICT':16} {'':7} {'':7} {pol_first:11,.0f} "
              f"{pol_small:9,.0f} {pol_med:8,.0f}   {verdict}; {wins}/{len(flat_calls)} "
              f"starts pay more, worst start {worst_gap:+,.0f}")


if __name__ == "__main__":
    raise SystemExit(main())
