"""Size the one mechanism that actually beat DCA: leverage. Not a recommendation.

Run: .venv/bin/python tools/leverage_sizing.py [--windows full,recent]

Findings through round 3, all reproducible from tools in this repo:

  * no unlevered timing signal clears the dominance rule (required_accuracy.py:
    the bar is 56-58% weekly accuracy, the rules that exist get 53-58%, and
    fifteen of sixteen cells fall short);
  * the mean-reversion mirror image is dead on raw moments;
  * the overnight/intraday split says the nightly toll exceeds what nights pay;
  * constant leverage with no signal at all beat DCA in all four windows.

That last line is the only mechanism left standing, and it is worth being exact
about what it is: leverage is not an edge. It multiplies the equity risk premium
and charges a spread for the privilege. It is included here because the goal is
dollars per month, the user's own capital is finite, and a levered index sleeve
is a real choice with a real cost — not because a backtest that only wins with
borrowed money is a strategy. This tool exists to find where that stops paying,
not to sell it.

Every row is net of real costs, on the funded simulator from run_voltarget_scan
(2.0 bps per unit of one-way turnover, borrow at the archive's own cash index
plus 150 bps charged daily on the borrowed portion, 30% maintenance equity with
forced deleveraging when breached, 9.45 bps fund expense). Comparator is plain
DCA into the same fund, same schedule, unlevered.

What "optimal" means here has to be chosen before looking, because leverage
raises both the good number and the bad one and any single ratio can be gamed by
picking the ratio. Three are reported, each answering a different question:

  CAGR                      what it earns
  max DD                    what it does to the account on the worst ride
  $/ unit DD                dollars bought per unit of drawdown accepted
  worst month               the single month that would feel like losing it all

and one hard constraint that no ratio justifies crossing: the leverage at which
the margin engine ever fires. A forced sale at the bottom is a different kind of
loss from a drawdown, because it is permanent and it happens by construction in
the exact week that hurts. Rows above that line are disqualified regardless of
how good their CAGR looks.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boring_alpha.data.csv_loader import load_csv_market_data  # noqa: E402
from run_voltarget_scan import (  # noqa: E402
    BORROW_SPREAD,
    MONTHLY,
    OPENING,
    TURNOVER_COST,
    funded,
)
from funded_frame import per_month_equivalent  # noqa: E402

SNAPSHOT = ROOT / "data" / "snapshots" / "20260904T192633Z" / "market_daily.csv"
CASH_FILE = ROOT / "data" / "snapshots" / "20260904T192633Z" / "cash_daily.csv"
SYMBOL = "SPY"

WINDOWS = {
    "full": (date(1993, 1, 1), date(2026, 9, 30)),
    "seen A": (date(2007, 6, 1), date(2017, 12, 31)),
    "seen B": (date(2018, 1, 1), date(2021, 12, 31)),
    "recent": (date(2022, 1, 1), date(2026, 9, 30)),
}

# Fixed before running. 1.0 is the control (unlevered, no signal: pure DCA in a
# band, so any gap to the comparator here is timing noise and not leverage).
LEVERS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)

BAND = 0.10
REVIEW_EVERY = 5

# The alternative wrapper: a daily-reset 2x index fund. Expense ratio ~0.90% is
# what the large ones actually charge; financing at the fund's swap rate is
# roughly cash plus 25 bps, an order of magnitude cheaper than a retail margin
# desk. Both are stated so the comparison can be argued with.
import withdrawal_capacity as wc                             # noqa: E402  one assumption per fact

ETF_EXPENSE = wc.WRAPPER_EXPENSE   # the same leveraged-fund assumption, owned by the file that states it first
ETF_SPREAD = 0.0025


@contextmanager
def engine_costs(borrow_spread: float, expense: float):
    """Temporarily reprice the shared engine.

    A wrapper's costs are already inside its own return series, so running it
    through an engine that also charges borrow and expense would bill them twice.
    Restored on exit even on exception, because a mutated module constant leaks
    into every later row and the leak looks exactly like a result.
    """

    import run_voltarget_scan as engine

    saved = (engine.BORROW_SPREAD, engine.EXPENSE)
    engine.BORROW_SPREAD, engine.EXPENSE = borrow_spread, expense
    try:
        yield
    finally:
        engine.BORROW_SPREAD, engine.EXPENSE = saved


def series(data, bounds):
    dates = [d for d in data.dates
             if bounds[0] <= d <= bounds[1] and SYMBOL in data.by_date[d]]
    closes = [data.by_date[d][SYMBOL].close for d in dates]
    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    returns.insert(0, 0.0)
    return dates, closes, returns


def constant_target(length, lever):
    return [lever] * length


def worst_month(path):
    """Largest month-over-month drop in account value, deposits excluded.

    Deposits are removed from the ratio because a $500 contribution is not a
    gain; leaving them in would flatter every row by the same amount and the
    flattering would grow as the account's returns shrank, which is backwards.
    """

    worst = 0.0
    month_end: dict[tuple[int, int], float] = {}
    for stamp, value in path:
        month_end[(stamp.year, stamp.month)] = value
    ordered = sorted(month_end.items())
    for (_prev_key, prev), (_key, value) in zip(ordered, ordered[1:]):
        if prev > 0:
            worst = min(worst, value / prev - 1.0)
    return worst


def comparator(dates, closes, returns, cash_factors, start):
    """Plain DCA: unlevered, never rebalanced, deposit spent on arrival.

    Target 1.0 with band 0 means the engine buys whatever cash exists on every
    session, which after the monthly deposit is exactly "spend it when it
    arrives" and otherwise nothing. The only cost it pays is the one a buy-and-
    holder genuinely pays: the spread on the deposit.
    """


    return funded(
        closes, returns, cash_factors, dates,
        targets=[1.0] * len(dates), band=0.0, start=start,
    )


def wrapper_returns(returns, cash_factors, lever, expense, spread):
    """A daily-reset leveraged ETF expressed as one instrument, not as a trade.

    This matters and it is easy to get backwards. A 2x fund's expense ratio is
    quoted against its own NAV — the money in — not against the gross exposure it
    runs, so charging it on the exposure would double-count the leverage the fund
    has already applied. Financing is charged on everything the fund borrows,
    which at L times is (L-1) of NAV. Both inputs are annual and both are divided
    by 252 here; the first draft of this function charged the annual spread every
    day and priced the wrapper at a 99% loss, which is the kind of number that
    only looks like a finding.

    `cash_factors[d] - 1.0` is already a one-day rate, so it is not divided.
    """

    return [
        lever * r - (lever - 1.0) * ((cf - 1.0) + spread / 252.0) - expense / 252.0
        for r, cf in zip(returns, cash_factors)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", default=",".join(WINDOWS))
    parser.add_argument(
        "--spread", type=float, default=None,
        help="borrow spread over the archive cash index, as a decimal. The "
             "default is the engine's 0.015, which is retail margin. Pass 0.0 "
             "to price an exchange-traded 2x fund, whose swap financing is the "
             "institutional rate and which cannot be margin called at all.")
    args = parser.parse_args()
    chosen = [w.strip() for w in args.windows.split(",") if w.strip() in WINDOWS]

    if args.spread is not None:
        import run_voltarget_scan as engine
        engine.BORROW_SPREAD = args.spread
        spread_note = (f"borrow at archive cash + {args.spread:.2%}"
                       if args.spread else "borrow at archive cash, spread-free")
    else:
        spread_note = "borrow at archive cash + 1.50% (retail margin)"

    data = load_csv_market_data(SNAPSHOT, CASH_FILE, end=date(2026, 9, 30))

    print(f"constant-leverage SPY, funded $5k + $500/mo, net of real costs")
    print(f"  {spread_note}")
    print("The 1.00x row is a check, not a candidate: same engine, target 1.0,")
    print("no band, so it must equal the comparator exactly. If it does not, the")
    print("rows below it are not worth reading.\n")

    for name in chosen:
        bounds = WINDOWS[name]
        dates, closes, returns = series(data, bounds)
        if len(dates) < 260:
            continue
        cash_factors = [data.cash_factors[d] for d in dates]
        comp = comparator(dates, closes, returns, cash_factors, 1)

        print(f"=== {name}  {dates[0]}..{dates[-1]}  ({len(dates)} sessions)")
        print(f"    comparator: plain DCA, ${comp.ending:,.0f} on "
              f"${comp.paid_in:,.0f} paid in, CAGR {comp.irr:+.2%}, "
              f"max DD {comp.max_drawdown:.1%}, total cost paid "
              f"${comp.cost_paid:,.0f} (2 bps on every dollar deposited), "
              f"never rebalanced, no borrow")
        header = (f"    {'lev':>4} {'ending':>12} {'$ vs DCA':>12} {'extra/mo':>9} "
                  f"{'CAGR':>7} "
                  f"{'maxDD':>7} {'worstmo':>8} {'$/uDD':>9} {'trades':>7} "
                  f"{'calls':>5} {'borrow$':>9}")
        print(header)

        rows = []
        for lever in LEVERS:
            # The 1.0 control is run at band 0.0 on purpose, and it is the single
            # most valuable row here: at target 1.0 with no band the engine must
            # reproduce plain DCA to the dollar. Run at the same 10% band as the
            # levered rows it does NOT, and the reason is instructious — a 10%
            # dead band is larger than a $500 deposit the moment the account
            # clears $5,000, so the deposit silently stays in cash and the row
            # ends $163k light over 33 years. At target 1.5 that never happens,
            # because the gap between 150% and the current weight is always far
            # wider than the band, so deposits do get invested. Same engine, same
            # band, opposite failure — a reminder that a dead band is not free
            # at low leverage, it is just paid in a currency that is harder to
            # see on a screen.
            band = 0.0 if abs(lever - 1.0) < 1e-9 else BAND
            res = funded(
                closes, returns, cash_factors, dates,
                targets=constant_target(len(dates), lever),
                band=band, start=1,
            )
            if abs(lever - 1.0) < 1e-9:
                drift = res.ending - comp.ending
                flag = ("engine matches comparator"
                        if abs(drift) < 1.0 else f"ENGINE DRIFT {drift:+,.2f}")
            gap = res.ending - comp.ending
            wm = worst_month(res.path)
            # The objective is phrased in monthly dollars, so translate. Terminal
            # gap is the wrong unit for that question and an annuity is the right
            # one: if the extra wealth had been withdrawn evenly as it was
            # created, what monthly amount does it correspond to, given the same
            # fund was compounding underneath it the whole time.
            years = max((dates[-1] - dates[0]).days / 365.2425, 1.0)
            months = int(round(years * 12))
            # Terminal gap is the wrong unit for a goal stated in monthly dollars,
            # so convert it to the level monthly amount whose accumulated value at
            # the comparator's own rate equals that gap. Discounting at the
            # comparator's rate rather than the levered row's keeps the conversion
            # honest: it prices the extra dollars as what they are, a claim on the
            # same asset, and does not let leverage rate its own winnings.
            per_month = per_month_equivalent(gap, comp.irr, months)
            # Dollars of terminal wealth bought per point of drawdown accepted.
            eff = gap / (abs(res.max_drawdown) * 100.0) if res.max_drawdown else 0.0
            rows.append((lever, res, gap, wm, eff, per_month))

            print(f"    {lever:>4.2f} {res.ending:>12,.0f} {gap:>+12,.0f} "
                  f"{per_month:>+8,.0f} "
                  f"{res.irr:>6.2%} {res.max_drawdown:>7.1%} {wm:>7.1%} "
                  f"{eff:>9,.0f} {res.turns:>7} {res.margin_calls:>5} "
                  f"{res.carry_paid:>9,.0f}"
                  + ("   RUINED" if res.ruined else "")
                  + (f"   {flag}" if abs(lever - 1.0) < 1e-9 else ""))
            if res.ruined:
                break

        # Marginal, not average: a lever is chosen at the margin, and an average
        # ratio always flatters the middle of a curve that turns over at the end.
        print("    marginal step          extra/mo  added DD pt  $ per added DD pt")
        for (la, ra, ga, wa, ea, ma), (lb, rb, gb, wb, eb, mb) in zip(rows, rows[1:]):
            add_dd = abs(rb.max_drawdown) - abs(ra.max_drawdown)
            add_mo = mb - ma
            price = add_mo / add_dd if add_dd > 1e-9 else float("inf")
            print(f"    {la:>4.2f}x -> {lb:<4.2f}x       {add_mo:>+8,.0f} "
                  f"{add_dd * 100:>+11.1f}   {price:>+14,.0f}")

        disqualified = [r[0] for r in rows if r[1].margin_calls > 0 or r[1].ruined]
        print(f"    disqualified at: {disqualified or 'none'}"
              f"  (a forced deleveraging is not a drawdown: it converts a paper")
        print(f"    number into a permanent one, on the schedule worst-of-timing.")

        # Instrument, not signal. Rounds 1-3 searched for a rule to trade and found
        # none that cleared the bar; this compares two ways of owning the same
        # exposure, neither of which requires an opinion. It is here because the
        # round-3 finding was that the sleeve chosen swamped the rule chosen by an
        # order of magnitude, and the same question had not yet been asked of the
        # one mechanism still standing.
        print("    instrument: same exposure, two wrappers, no view required")
        print(f"    {'lev':>4} {'retail margin':>15} {'ETF wrapper':>13} "
              f"{'wrapper -':>11}  {'margin calls':>20}")
        for lever in (1.5, 2.0):
            diy = next((r for lv, r, *_ in rows if abs(lv - lever) < 1e-9), None)
            if diy is None:
                continue
            with engine_costs(0.0, 0.0):
                wrap = funded(
                    closes,
                    wrapper_returns(returns, cash_factors, lever, ETF_EXPENSE,
                                    ETF_SPREAD),
                    cash_factors, dates,
                    targets=[1.0] * len(dates), band=0.0, start=1,
                )
            gap = wrap.ending - diy.ending
            print(f"    {lever:>4.2f} {diy.ending:>15,.0f} {wrap.ending:>13,.0f} "
                  f"{gap:>+11,.0f}  {f'{diy.margin_calls} DIY / 0 wrapper':>20}"
                  f"   {'wrapper' if gap > 0 else 'DIY'} wins")
        print()

    print("Read this as a price list, not a green light. Every column that looks")
    print("good rises with the same dial that raises the ones that hurt, and the")
    print("margin column is a cliff rather than a slope: below it a bad year is a")
    print("number on a screen, above it a bad year is a forced sale that locks in.")


if __name__ == "__main__":
    main()
