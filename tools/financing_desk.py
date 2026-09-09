#!/usr/bin/env python3
"""Where the levered book stops beating the index, and what the desk charges to get there.

Round 46. Every leveraged number in this repository has been priced at one of two financing assumptions: the
archive's bill curve plus 150bp, or `income_frontier.MENU_PUBLIC`, the April 2026 posted rate of the cheapest
retail desk (4.90% all-in, Public.com's flat tier). Both are real. Neither is what most retail accounts pay: the
same April 2026 survey has Fidelity's base tier at 10.575%, Schwab's at 10.00%, E*TRADE's at 10.45% and
Firstrade's at ~12.00%, and base tiers are what accounts under $100k actually pay — tiered discounts start above
the balance a starter account has.

So this file answers the question the recommendation cannot avoid: for each sleeve, each leverage and each
window, **what is the all-in financing rate at which the levered book stops beating the same money invested
without leverage** — and how does that compare with the rate card of the desk the account is actually sitting on.
The break-even is the number that makes a broker choice checkable without asking anyone what they hold.

Usage:  python tools/financing_desk.py [--lev 1.25] [--sleeve SPY] [--window both]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import book_power as bp                    # noqa: E402
import income_frontier as ifr              # noqa: E402
import withdrawal_capacity as wc           # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data   # noqa: E402

# Posted base-tier rates, all-in, as disclosed in April 2026 and tabulated by
# https://sidebysidebrokers.com/blog/margin-rates-2026-comparison.html — the same survey round that sourced
# `MENU_PUBLIC`. A secondary source, dated, verified against the desk's own page where that page renders; the
# ordering has been stable for years and the absolute numbers move with the Fed, so they are inputs to re-read,
# not constants to believe. `MENU_PUBLIC` is kept as the cheap anchor so this file and `income_frontier` cannot
# silently drift apart.
DESKS = (
    ("Public.com (flat)", 0.0490),
    ("Robinhood Gold", 0.0575),
    ("IBKR Pro (base tier)", 0.0583),
    ("Moomoo (flat)", 0.0680),
    ("Schwab (base tier)", 0.1000),
    ("E*TRADE (base tier)", 0.1045),
    ("Fidelity (base tier)", 0.10575),
    ("Merrill Edge (base tier)", 0.1113),
    ("Firstrade (base tier)", 0.1200),
)

SLEEVES = ("SPY", "QQQ")
WINDOWS = (("full", None), ("the VOO era", 192))
CHEAP, EXPENSIVE = DESKS[0], DESKS[-1]


def compounded(monthly: list, months: int | None = None):
    """Terminal wealth of a compounded path, and its worst point. None if the account is destroyed."""

    series = monthly if months is None else monthly[-months:]
    path, worst = 1.0, 1.0
    for r in series:
        path *= (1.0 + r)
        worst = min(worst, path)
    if path <= 0:
        return None, worst
    return (path ** (12.0 / len(series)) - 1.0) * 100.0, worst


def excess(data, symbol: str, lever: float, rate: float, months: int | None = None) -> tuple:
    """Annualised excess of a constant-leverage book over the same money unlevered, at a given all-in rate.

    `borrow="posted"` matters here: it charges the whole loan at one flat posted rate and lets the cash leg cancel,
    so the number is exactly comparable to a desk's published schedule. Under `borrow="book"` the same call would
    charge the archive's own bill curve plus a spread, which is a different account in a different decade.
    """

    original = ifr.MENU_PUBLIC
    ifr.MENU_PUBLIC = rate
    try:
        strat, bench, _keys, _w = bp.net_strategy_returns(
            data, symbol, wc.TURNOVER_COST * 1e4, wc.EXPENSE[symbol], borrow="posted", static=lever)
    finally:
        ifr.MENU_PUBLIC = original
    a, worst = compounded(strat, months)
    b, _bw = compounded(bench, months)
    if a is None:
        return None, worst
    return a - b, worst


def breakeven(data, symbol: str, lever: float, months: int | None = None,
              lo: float = 0.0, hi: float = 0.60) -> float | None:
    """The all-in rate at which the tilt's excess crosses zero. None if it is negative even at a free loan."""

    if excess(data, symbol, lever, lo, months)[0] is None or excess(data, symbol, lever, lo, months)[0] <= 0:
        return None
    for _ in range(48):
        mid = (lo + hi) / 2.0
        e = excess(data, symbol, lever, mid, months)[0]
        if e is not None and e > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def table(data, lever: float, sleeves=SLEEVES, windows=WINDOWS) -> list:
    rows = []
    for symbol in sleeves:
        for label, months in windows:
            cheap, _ = excess(data, symbol, lever, CHEAP[1], months)
            rich, _ = excess(data, symbol, lever, EXPENSIVE[1], months)
            be = breakeven(data, symbol, lever, months)
            rows.append({"symbol": symbol, "window": label, "lever": lever, "cheap": cheap,
                         "expensive": rich, "breakeven": be,
                         "spread_share": ((cheap - rich) / cheap) if (cheap is not None and rich is not None
                                                                       and cheap > 0) else None})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lev", type=float, default=1.25)
    ap.add_argument("--sleeve", default=None)
    ap.add_argument("--window", default="both", choices=("both", "full", "era"))
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    sleeves = (args.sleeve,) if args.sleeve else SLEEVES
    windows = WINDOWS if args.window == "both" else \
        tuple(w for w in WINDOWS if (w[1] is None) == (args.window == "full"))

    print(f"\n  FINANCING BREAK-EVEN — a constant {args.lev:.2f}x book against the same money unlevered, "
          f"charged a flat posted rate")
    print(f"  {'sleeve':7} {'window':13} {'@4.90%':>9} {'@12.00%':>9}  {'break-even':>11}   verdict at the "
          f"expensive desk")
    for r in table(data, args.lev, sleeves, windows):
        be = "never" if r["breakeven"] is None else f"{r['breakeven']:.2%}"
        if r["cheap"] is None:
            verdict = "the account does not survive the window at all"
        elif r["expensive"] is None:
            verdict = "destroyed at the expensive desk"
        elif r["expensive"] <= 0:
            verdict = "FAILS: the index wins outright"
        else:
            verdict = f"survives, keeps {r['expensive'] / r['cheap']:.0%} of the cheap desk's edge"
        print(f"  {r['symbol']:7} {r['window']:13} "
              f"{('n/a' if r['cheap'] is None else format(r['cheap'], '+.2f') + 'pp'):>9} "
              f"{('n/a' if r['expensive'] is None else format(r['expensive'], '+.2f') + 'pp'):>9}  {be:>11}   "
              f"{verdict}")

    print(f"\n  the rate card as a cost, on a $10,000 loan held a year:")
    for name, rate in DESKS:
        print(f"    {name:24} {rate:>7.3%}   ${rate * 10_000:,.0f}/yr")
    print(f"  spread between {CHEAP[0]} and {EXPENSIVE[0]}: {(EXPENSIVE[1] - CHEAP[1]) * 10_000:.0f}bp, which at "
          f"{args.lev:.2f}x costs {(EXPENSIVE[1] - CHEAP[1]) * (args.lev - 1) * 100:.2f}pp a year")

    rows = table(data, args.lev, sleeves, WINDOWS)
    # A ratio whose denominator is small is a statement about the denominator. SPY over the full archive earns
    # +1.12pp at the cheap desk, so the same 1.77pp rate-card gap is 158% of it and the sentence means something;
    # QQQ over the full archive earns +0.45pp, and "405%" would only report that 0.45 is small. Rows are screened
    # on the denominator, not on the answer.
    live = [r for r in rows if r["spread_share"] is not None and r["cheap"] > 1.0]
    gap_pp = (EXPENSIVE[1] - CHEAP[1]) * (args.lev - 1) * 100.0
    if live:
        worst = max(live, key=lambda r: r["spread_share"])
        print(f"\n  at {args.lev:.2f}x the rate-card gap between {CHEAP[0]} and {EXPENSIVE[0]} costs "
              f"{gap_pp:.2f}pp a year, which is {worst['spread_share']:.0%} of the entire leveraged edge "
              f"({worst['symbol']}, {worst['window']}: {worst['cheap']:+.2f}pp at the cheap desk).")
        print("  Every signal this repository has ever measured was worth under ~2.5pp a year net of costs. The\n"
              f"  desk is offering or withholding {gap_pp:.2f}pp of that, before any model is chosen: where the\n"
              f"  account is held is the decision, and the model is the small print.")


if __name__ == "__main__":
    main()
