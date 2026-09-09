"""How much does the short term cost? The same signal, re-decided from once a year to every day.

Round 57. Rounds 55 and 56 tested two families at one frequency each and both lost. The objective's own words are
about *short-term* trading, so this round varies the one thing the objective actually specifies: how often the model
acts. Two families, six frequencies, one accounting engine.

Families, both pre-declared, both carried forward from earlier rounds rather than invented here:

  * `ma200`     — SPY above its 200-day average, else bills (round 55's best drawdown result).
  * `mom_top1`  — the strongest of six risk sleeves if it also beats the bill yield, else bills (round 56's only
                  real result).

Frequencies: annual, quarterly, monthly, biweekly, weekly, daily. Every one of them is the same information — a
200-day average or a 12-month ranking — merely read more or less often. Nothing gets cleverer; the question is what
reading it more often is worth.

The split that makes this readable is **gross versus net**. Gross charges the funds' expense ratios but no trading
cost, so it answers "is fresher information better information?" Net adds the repository's posted 0.0002 one-way on
every unit traded, and again at 4x for slippage honesty, which answers "do you keep it?" If gross is flat and net
falls, the short term is a bill, not a belief.

Run:  python tools/frequency_cost.py [--panel-start 2006-02-07]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import rotation_edge as re_                                              # noqa: E402
import trend_cost_test as tc                                             # noqa: E402
import withdrawal_capacity as wc                                         # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data            # noqa: E402

FAMILIES = ("ma200", "mom_top1")
FREQS = ("annual", "quarterly", "monthly", "biweekly", "weekly", "daily")
WARMUP = 252                                     # the longest lookback used below, so every family warms up alike
COST_PASS = (0, 1, 4)


def signal_days(ordered: list, freq: str) -> list:
    """Indices on which a decision is allowed to be taken, at or after warm-up. Deterministic and data-independent
    for the sub-monthly settings, because a rule that only rebalances when a calendar tick falls right is a rule
    with an untested accident in it."""

    n = len(ordered)
    ends = re_.month_end_indices(ordered)
    # WARMUP gates every frequency alike. Applying it only to the calendar frequencies let `daily` reach back through
    # a 252-day slice of a list that has only ten days in it yet: Python clamps a negative start to zero, so the
    # first "12-month" rankings of the daily rule were computed from one to a handful of days and treated as if they
    # were a year of evidence. A short window is not a missing value, it is a different signal.
    if freq == "daily":
        out = [i for i in range(WARMUP, n)]
    elif freq == "weekly":
        out = [i for i in range(n) if (i - WARMUP) % 5 == 0 and i >= WARMUP]
    elif freq == "biweekly":
        out = [i for i in range(n) if (i - WARMUP) % 10 == 0 and i >= WARMUP]
    elif freq == "monthly":
        out = [i for i in sorted(ends) if i >= WARMUP]
    elif freq == "quarterly":
        out = [i for i in sorted(ends) if i >= WARMUP and ordered[i].month in (3, 6, 9, 12)]
    elif freq == "annual":
        out = [i for i in sorted(ends) if i >= WARMUP and ordered[i].month == 12]
    else:
        raise ValueError(f"undeclared frequency: {freq}")
    return [i for i in out if i < n - 1]


def weights_for_family(family: str, ordered, rets, bills, expense, closes_by_date, freq, unknown_er) -> list:
    """Hold a decision taken on the last signal day until the next one. All-cash until the first signal, as in the
    two earlier rounds — an unknown signal is not a reason to be invested."""

    days = signal_days(ordered, freq)
    allow = set(days)
    hold = {}
    out = []
    for i in range(len(ordered)):
        if i in allow:
            if family == "ma200":
                s = sma(closes_by_date["SPY"], 200, i)
                hold = {"SPY": 1.0} if s is not None and closes_by_date["SPY"][i] > s else {}
            elif family == "mom_top1":
                ranked = sorted(((re_.compound(rets[s][i - 251:i + 1]) - 1.0, s) for s in re_.CANDIDATES),
                                key=lambda x: (-x[0], x[1]))
                bill_12m = re_.compound(bills[max(0, i - 251):i + 1]) - 1.0
                hold = {ranked[0][1]: 1.0} if ranked[0][0] > bill_12m else {}
            else:
                raise ValueError(f"undeclared family: {family}")
        out.append(tuple(float(hold.get(s, 0.0)) for s in re_.UNIVERSE))
    return out


def sma(closes, n, i):
    """`n`-day average of a date-indexed close series. Returns None while the window would reach before the data."""

    if i - n + 1 < 0:
        return None
    window = closes[i - n + 1:i + 1]
    if any(x is None for x in window):
        return None
    return sum(window) / n


def trades_per_year(res, years):
    return res["switches"] / years if years else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unknown-er", type=float, default=re_.UNKNOWN_ER)
    args = ap.parse_args()
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    ordered, rets, bills, expense = re_.panel(data, args.unknown_er)
    closes_by_date = {"SPY": [None] * len(ordered)}
    pos = {d: i for i, d in enumerate(tc.days_of(data, "SPY"))}
    cl = tc.closes_of(data, "SPY")
    for i, d in enumerate(ordered):
        closes_by_date["SPY"][i] = cl[pos[d]]

    n = len(ordered)
    years = (n - 1) / tc.DAYS
    print(f"frequency sweep · {ordered[0]} to {ordered[-1]} · {n} days · {years:.1f} years"
          f" · the same information, read {len(FREQS)} different ways")
    print(f"  families {FAMILIES} · turnover {wc.TURNOVER_COST:.2%} one-way · unposted expenses {args.unknown_er:.2%}"
          " · gross pays no trading cost at all\n")

    hold_spy = re_.run_weights(ordered, rets, bills, expense, re_.constant_weights("SPY", n))
    for family in FAMILIES:
        print(f"  {family}")
        print(f"    {'freq':10} {'updates':>8} {'expo':>6} {'GROSS':>8} "
              f"{'net@1x':>8} {'net@4x':>8} {'max DD':>8} {'trades/yr':>10} {'cost/yr':>9}   gross - net@1x")
        print("    " + "-" * 96)
        gross_values, net_values = [], []
        for freq in FREQS:
            w = weights_for_family(family, ordered, rets, bills, expense, closes_by_date, freq, args.unknown_er)
            g = re_.run_weights(ordered, rets, bills, expense, w, 0)
            one = re_.run_weights(ordered, rets, bills, expense, w, 1)
            four = re_.run_weights(ordered, rets, bills, expense, w, 4)
            gross_values.append(g["cagr"])
            net_values.append(one["cagr"])
            print(f"    {freq:10} {len(signal_days(ordered, freq)):>8} {one['mean_expo']:>6.0%} {g['cagr']:>8.2%}"
                  f" {one['cagr']:>8.2%} {four['cagr']:>8.2%} {one['max_dd']:>8.1%}"
                  f" {trades_per_year(one, years):>10.1f} {one['cost_drag']:>9.4%}"
                  f"   {(g['cagr'] - one['cagr']) * 100:>+8.2f}pp")
        print(f"    SPY buy-and-hold on the same engine: {hold_spy['cagr']:.2%}, max DD {hold_spy['max_dd']:.1%}."
              "  Gross and net are the")
        print("    same number there, because it never trades — which is the baseline every row below is billed"
              " against.")
        gspan = (max(gross_values) - min(gross_values)) * 100
        nspan = (max(net_values) - min(net_values)) * 100
        print(f"    across the six frequencies the GROSS answer spans {gspan:.2f}pp and the NET answer spans"
              f" {nspan:.2f}pp. Reading the")
        print("    same information more often is worth the first number and costs the second.\n")

    print("  the price of the short term, measured from each family's OWN BEST frequency, not from the slowest")
    print(f"    {'family':10} {'best freq':>10} {'net@1x':>8} {'daily net':>10} {'faster costs':>13}"
          f"   {'gross moved':>12}   {'DD best':>8} {'DD daily':>9}")
    print("    " + "-" * 80)
    for family in FAMILIES:
        rows = {}
        for freq in FREQS:
            w = weights_for_family(family, ordered, rets, bills, expense, closes_by_date, freq, args.unknown_er)
            rows[freq] = (re_.run_weights(ordered, rets, bills, expense, w, 0),
                          re_.run_weights(ordered, rets, bills, expense, w, 1))
        best = max(FREQS, key=lambda f: rows[f][1]["cagr"])
        gb, nb = rows[best]
        gd, nd = rows["daily"]
        print(f"    {family:10} {best:>10} {nb['cagr']:>8.2%} {nd['cagr']:>10.2%}"
              f" {(nb['cagr'] - nd['cagr']) * 100:>12.2f}pp   {(gb['cagr'] - gd['cagr']) * 100:>+11.2f}pp"
              f"   {nb['max_dd']:>8.1%} {nd['max_dd']:>9.1%}")

    print("    Read the last two columns together: if gross barely moves and net falls, the short term is an"
          " invoice.\n    If gross rises by less than net falls, the extra information is real and unsellable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
