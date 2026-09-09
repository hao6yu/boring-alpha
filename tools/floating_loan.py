"""The loan, priced the way a broker actually prices it: a spread over a rate that moves.

    .venv/bin/python tools/floating_loan.py
    .venv/bin/python tools/floating_loan.py --spread-bps 300 --levels 1.0 1.25 1.5
    .venv/bin/python -m pytest tests/test_floating_loan.py -q

Round 29 left one plan standing: a constant 1.25× book, +1.63%/yr over the index under sweep cash and a posted
4.90% desk rate, the only positive row in `action_ledger.py` that is not a rate the broker is simply not paying.
Everything about it came from round 11, which priced the loan at a **fixed posted rate** — and margin interest is
not billed that way. A desk quote is a spread over an index, and this archive contains the index: the same
DGS3MO curve that every backtest here credits the cash leg with. So the surviving plan has one input nobody has
ever varied, and it is the input the plan is most exposed to, because a leveraged long-equity book is short a
rate and long a spread.

This file varies it. The desk spread is **calibrated, not assumed**: today's posted menu rate minus today's bill
curve (4.90% − 2.88% = 202bp), so the floating and fixed models agree on the month the account is being priced in
and differ only on the history. Then the same constant-1.25× book is run under both, over every window, and the
window where the two models disagree the most is the one that tells you what you are actually underwriting.

## The thing the full record hides

The archive spans the whole modern rate cycle: 6%+ before 2007, essentially zero from 2012 to 2021, 5%+ again
from 2023. A floating loan is cheap for most of it and expensive for the part that matters to anyone starting
today. Averaged over the whole record the floating model therefore looks *better* than the fixed one, and that
average is a regime gift rather than a finding — the same trap as a backtest that spends thirty years in a
bull market, except the variable is the cost of the money. So the numbers below are printed per window first and
the full record last, and the verdict line reads the **worst** window, because for a loan that is the only one
that has to be survivable.

## What this file cannot do

  * **The curve is 3-month Treasuries, not the desk's actual reference.** A real margin rate references a broker's
    own funding benchmark, which is wider than DGS3MO and does not fall as fast. `SPREAD` absorbs that error in
    the level; it cannot absorb it in the *timing*.
  * **A margin rate is floored in practice and this one is not.** When the curve went to zero a desk still
    charged something. The floating model here would have charged 2.02% in 2020 against a posted 4.90%, which is
    the single most optimistic thing in this file, and it is why the zero-rate window is reported separately.
  * **Nothing here models a reprice.** A desk can widen its spread without the index moving, at any time, and
    round that into the plan retroactively. The `--spread-bps` flag is the closest thing to that risk: run it at
    +100bp over the calibrated number and look at the worst window.
  * **Still no tax, still survivorship-biased, still the same 12 sleeves.** See `cross_section.py` and
    `action_ledger.py` for those standing caveats.

"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import book_power as bp                            # noqa: E402
import income_frontier as ifr                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
import cash_yield_gap as cyg                       # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

SYMBOL = "SPY"
EXPENSE = float(wc.EXPENSE[SYMBOL])
CAPITAL = 20_000.0

# Windows chosen for what they did to rates, not for what they did to equities.
WINDOWS = (
    ("full record", 1993, 2026),
    ("rate fall 2007-09", 2007, 2009),
    ("zero-rate 2012-19", 2012, 2019),
    ("covid 2020-21", 2020, 2021),
    ("rate shock 2022-26", 2022, 2026),
)


def spread_bps_calibrated(data) -> float:
    """The desk's spread implied by today's posted menu rate over today's bill curve, in basis points."""

    bill = cyg.bill(data)["current3m"]
    return (ifr.MENU_PUBLIC - bill) * 10_000.0


def excess(data, spread_bps: float, borrow: str, leverage: float,
           first: int, last: int) -> dict:
    """Excess over the pinned comparator for a constant-leverage book, in one window, in annualised percent."""

    strat, bench, keys, _w = bp.net_strategy_returns(data, SYMBOL, spread_bps, EXPENSE,
                                                     sweep=bp.SWEEP, borrow=borrow, static=leverage)
    idx = [i for i, k in enumerate(keys) if first <= int(str(k)[:4]) <= last]
    if len(idx) < 12:
        return {"months": len(idx), "excess": float("nan"), "mo": float("nan"), "dd": float("nan")}
    diff = [strat[i] - bench[i] for i in idx]
    equity, peak, dd = 1.0, 1.0, 0.0
    for i in idx:
        equity *= 1.0 + strat[i]
        peak = max(peak, equity)
        dd = min(dd, equity / peak - 1.0)
    mean = statistics.fmean(diff)
    return {"months": len(idx), "excess": mean * 1200.0, "mo": mean * CAPITAL, "dd": dd}


def main() -> int:
    ap = argparse.ArgumentParser(description="price a constant-leverage book under a floating desk rate")
    ap.add_argument("--spread-bps", type=float, default=None,
                    help="override the calibrated desk spread (bp over the bill curve)")
    ap.add_argument("--levels", type=float, nargs="+", default=[1.00, 1.25, 1.50, 1.75, 2.00])
    ap.add_argument("--capital", type=float, default=CAPITAL)
    args = ap.parse_args()

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    calib = spread_bps_calibrated(data)
    spread = calib if args.spread_bps is None else args.spread_bps
    fixed = ifr.MENU_PUBLIC * 10_000.0

    print(f"the floating loan · {SYMBOL} · sweep cash at {bp.SWEEP:.2%} · capital ${args.capital:,.0f}\n")
    print(f"  posted menu rate      {ifr.MENU_PUBLIC:.2%} a year")
    print(f"  today's bill curve    {cyg.bill(data)['current3m']:.2%} a year (archive, DGS3MO, 3-month)")
    print(f"  calibrated spread     {calib:.0f}bp   (what is being varied: {spread:.0f}bp)")
    print(f"  the two models agree today and differ only in history\n")

    for leverage in args.levels:
        print(f"  constant {leverage:.2f}x  ({(leverage-1):.2f} borrowed per $1 of equity)")
        print(f"    {'window':22} {'months':>7} {'FIXED 4.90%':>12} {'FLOATING':>10} "
              f"{'f − f':>8} {'$ /mo':>8} {'max DD':>8}")
        worst = None
        for name, first, last in WINDOWS:
            fx = excess(data, fixed, "posted", leverage, first, last)
            fl = excess(data, spread, "book", leverage, first, last)
            if fx["months"] < 12:
                continue
            scale = args.capital / CAPITAL
            if name != "full record" and (worst is None or fl["excess"] < worst[1]["excess"]):
                worst = (name, fl)
            print(f"    {name:22} {fx['months']:>7} {fx['excess']:>+11.2f}% {fl['excess']:>+9.2f}% "
                  f"{fl['excess']-fx['excess']:>+7.2f}% {fl['mo']*scale:>+8.2f} {fl['dd']:>7.1%}")
        if worst and leverage > 1.0:
            print(f"    the binding window is {worst[0]}: {worst[1]['excess']:+.2f}%/yr, "
                  f"drawdown {worst[1]['dd']:.1%} — the full record is not the underwriting")
        print()

    print("  Read the rate-shock row before the full-record row. A book that is long equity and short a rate")
    print("  earned its money twice over 2012-2019 and paid for it once in 2022-2026; the average of those two")
    print("  facts is not a plan. Sources: `withdrawal_capacity.EXPENSE`, `income_frontier.MENU_PUBLIC`")
    print("  (April 2026 posted tier), the DGS3MO curve inside the sealed snapshot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
