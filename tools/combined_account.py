"""The four positive ledger rows composed into ONE account, and the answer to whether it beats VOO.

    .venv/bin/python tools/combined_account.py
    .venv/bin/python tools/combined_account.py --capital 20000 --sweep-default
    .venv/bin/python -m pytest tests/test_combined_account.py -q

The goal has always been one sentence: does the whole thing beat just buying VOO. Thirty-eight rounds have priced
individual actions, and `action_ledger.py` sorts them into one table — but a table is not an account, and this
repository has never summed them into a portfolio. When round 38 tried, the sum collapsed, for two reasons that
are the finding.

**Each positive row is priced against a different counterfactual.** The cash row is worth $46.12/mo only for an
account that holds all its money idle; the loan row is worth $27.24/mo only for an account that owns 125% equity
and has no idle cash to switch; the share-class row is worth $1.07/mo only against the *specific* mistake of
holding SPY, and is worth exactly nothing once the benchmark is already the cheap fund. These are not four actions
available simultaneously — they are four answers to four different questions. `book_power.py` line 99 makes the
arithmetic unavoidable: the cash leg is `(1 - w) * cash`, so at a full 1.0 weight the idle-cash decision is worth
**precisely zero**, and at the loan's 1.25 weight that term is *negative* — the loan does not forgo the cash
switch, it reverses it.

**So the composed account is a one-dimensional choice: how much cash to hold.** This tool sweeps that one dial
and prices every stance on the same monthly path, against the benchmark the goal actually named — VOO buy-and-hold
at the cheap share class, default brokerage sweep, no view. Whatever beats that is the answer. Nothing else is.

## What the sweep shows

Every stance that holds cash **loses to plain VOO**, monotonically: 10% cash costs −1.19%/yr, 25% costs −2.97%,
half cash −5.95%, and all cash −11.89%/yr, which is −$198 a month on $20,000. The switch adds $47.00/mo at
all-cash and the sweep says take it all — and it is nowhere near the $198 of forgone market return it is being
weighed against. The switch is worth what it is worth, and that is less than holding cash costs, at every weight.

The maximum achievable excess over the index, net of every cost this project knows about, is the loan:
**+2.48%/yr, $41.40/mo** at 1.25× on VOO's 192 months, or **+1.63%/yr, $27.24/mo** on SPY's 404. Those two numbers
do not differ because of the funds — on the common 192 months SPY and VOO agree to **0.024%/yr**, tighter than the
0.065% fee gap between them, as two funds tracking one index must. They differ because **the samples are different
decades**: SPY starts 1993 and carries dot-com and 2008, VOO starts 2010-09 inside the strongest sustained bull in
the archive. One fund, one policy, two windows, **0.83%/yr** apart — half the edge. The loan's plan is worth
1.63%/yr over 33 years and 2.46%/yr over the last 16, and the difference is a statement about the calendar, not
about the borrowing.

So the goal's question has one answer, and it is not a trading model: **the account beats the index by borrowing,
or holds cash and does not.** No stance in between is both positive and free of leverage.

## What this file does not do

  * **It does not add the ledger's numbers together.** That is the error this file exists to prevent, and the
    numbers each carry a different implicit baseline; the table's own `--verify` re-derives them separately.
  * **The comparator is VOO at 100% with no cash**, which is the goal's own framing. A benchmark that also holds
    cash would make the switch look better and would not be the question asked.
  * **Still no tax, still survivorship-biased.** See `action_ledger.py`.

"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import action_ledger as al                         # noqa: E402
import book_power as bp                            # noqa: E402
import cash_yield_gap as cy                        # noqa: E402
import income_frontier as ifr                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

SYMBOL = "VOO"
SPREAD_BPS = 3.0
DEFAULT_SWEEP = float(wc.TURNOVER_COST)            # the brokerage's own sweep credit, not a Treasury bill
CAPITAL = 20_000.0


def monthly_edge(data, weight: float, cash: float, symbol: str = SYMBOL) -> tuple:
    """The account's incremental month — levered minus just holding — as a series, not an average.

    Everything in this project reports an annualised mean, and a mean is exactly the wrong statistic for the
    question the goal actually asks, which is whether money arrives *each month*. A plan that averages +2.45%/yr
    and is negative in six of ten months is not an income stream to a person who has to keep holding it through
    month five. This returns (keys, monthly excess decimals) so the shape can be examined rather than averaged.
    """

    strat, bench, keys, _w = bp.net_strategy_returns(
        data, symbol, SPREAD_BPS, float(wc.EXPENSE[symbol]), sweep=cash, borrow="posted", static=weight)
    return keys, [a - b for a, b in zip(strat, bench)]


def rolling_edge(months: list, years: int) -> list:
    """Annualised excess over every overlapping window of `years`, so a single headline cannot be an era."""

    n = years * 12
    if len(months) < n:
        return []
    return [sum(months[i:i + n]) / n * 1200.0 / 100.0 for i in range(len(months) - n + 1)]


def streaks(months: list, keys: list | None = None) -> dict:
    """How long the account can go backwards while doing exactly what it promised.

    The mean is a promise. The longest run of negative incremental months is the sentence the holder actually has
    to live with, and at 1.25x on a broad index it is measured below rather than assumed short.
    """

    worst_run, run, worst_month, trough, trough_run = 0, 0, 0.0, 0.0, 0
    peak, cum, deep, deep_from, deep_to = 0.0, 0.0, 0.0, None, None
    for i, m in enumerate(months):
        run = run + 1 if m < 0 else 0
        worst_run = max(worst_run, run)
        worst_month = min(worst_month, m)
        trough = min(trough + m, 0.0)
        trough_run = min(trough_run, trough)
        cum += m
        if cum > peak:
            peak, cur_from = cum, (keys[i + 1] if keys and i + 1 < len(keys) else None)
        if cum - peak < deep:
            deep, deep_to, deep_from = cum - peak, (keys[i] if keys else None), cur_from
    neg = sum(1 for m in months if m < 0)
    out = {"months": len(months), "share_negative": neg / len(months), "worst_streak": worst_run,
           "worst_month": worst_month, "cum_trough": trough_run,
           "mean_month": sum(months) / len(months)}
    if keys:
        out["trough_from"], out["trough_to"] = deep_from, deep_to
        out["trough_years"] = (deep_to.year - deep_from.year) if (deep_from and deep_to) else 0
    return out


def common_months(data, symbols=(SYMBOL, "SPY")) -> int:
    """The number of months every symbol in the comparison actually has.

    Round 38's closing claim — that ~0.79%/yr of the loan's edge is "which near-identical fund the tool happened to
    name" — was measured by running SPY over 404 months and VOO over 192 and differencing. That is not a fund test,
    it is a decade test: VOO's series starts 2010-09-09, inside the strongest sustained bull in the archive, and SPY's
    starts 1993-01-29 and so carries dot-com and 2008. Re-run on the common 192 months the two funds agree to
    **0.024%/yr**, three times *tighter* than the fee gap between them, which is what two funds tracking one index
    must do. The 0.85%/yr gap was the sample. Restricted to the common window the same policy earns +2.46% on SPY
    against +1.63% over its full record, so the era is worth ~0.83%/yr — half the edge. **Any comparison that changes
    the symbol and silently changes the sample is measuring the calendar.**
    """

    return min(len(wc.monthly(ifr.series_for(data, s), data.cash_factors)[1]) for s in symbols)


def legs(data, weight: float, cash: float, symbol: str = SYMBOL, last: int | None = None) -> dict:
    """One stance, priced by the engine that prices everything else in this project.

    `cash` is what idle money earns — the brokerage sweep or a bill fund — and `weight` is how much equity is
    held, so `(1 - weight)` is negative whenever the account borrows and the same line prices the loan.
    """

    strat, bench, _keys, _w = bp.net_strategy_returns(
        data, symbol, SPREAD_BPS, float(wc.EXPENSE[symbol]), sweep=cash, borrow="posted", static=weight)
    if last is not None and last < len(strat):
        strat, bench = strat[-last:], bench[-last:]
    n = len(strat)
    ann = sum(strat) / n * 1200.0        # percent per year, already scaled
    bann = sum(bench) / n * 1200.0
    eq, run, dd = 1.0, 1.0, 0.0
    for r, b in zip(strat, bench):
        eq *= 1.0 + r
        run *= 1.0 + b
        # Drawdown is quoted against the benchmark's own path, so a stance that merely lost
        # less than VOO is not described as having recovered.
        dd = min(dd, eq / max(run, 1e-12) - 1.0)
    # `ann` is in percent units, as every other tool in this project reports it; `excess` is the same quantity as
    # a decimal so a `%` format string does not scale it a second time. The first draft of this file printed the
    # loan at "+248.42%/yr" for exactly that reason.
    return {"weight": weight, "excess": (ann - bann) / 100.0, "ann": ann / 100.0, "bench": bann / 100.0,
            "months": n, "dd_vs_bench": dd, "mo": (ann - bann) / 1200.0 * CAPITAL, "symbol": symbol}


def sweep_capital(data, bill: float) -> list:
    """Every cash stance from all-cash to 25% borrowed, each priced against the same VOO buy-and-hold."""

    out = []
    for w in (0.0, 0.25, 0.50, 0.75, 0.90, 1.0, 1.10, 1.25):
        switched = legs(data, w, bill)
        default = legs(data, w, DEFAULT_SWEEP)
        out.append({"weight": w, "idle": 1.0 - w, "switched": switched, "default": default,
                    "switch_value": (switched["excess"] - default["excess"]) * 100.0})
    return out


def main() -> int:
    global CAPITAL
    ap = argparse.ArgumentParser(description="compose the positive actions into one account against VOO")
    ap.add_argument("--capital", type=float, default=20_000.0)
    ap.add_argument("--rate", type=str, default="current",
                    help="which short rate to price idle cash at: current, median, q1")
    args = ap.parse_args()
    CAPITAL = args.capital

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    bill_year = cy.path(data)["spot"] if args.rate == "current" else \
        (cy.path(data)["median"] if args.rate == "median" else cy.path(data)["q1"])

    print(f"one account, {cy.path(data)['months']} months, every cost this project knows about")
    print(f"  benchmark: 100% {SYMBOL}, expense {float(wc.EXPENSE[SYMBOL]):.4%}, default sweep "
          f"{DEFAULT_SWEEP:.2%}, no view\n  idle cash priced at {bill_year:.2%} ({args.rate})"
          f"   capital ${args.capital:,.0f}\n")

    print(f"  {'equity':>7} {'idle':>6} {'ann. excess':>12} {'$/mo':>9} {'switch worth':>13} "
          f"{'DD vs bench':>12}   stance")
    rows = sweep_capital(data, bill_year)
    for r in rows:
        st = ("all cash" if r["weight"] == 0.0 else
              "the benchmark" if r["weight"] == 1.0 else
              "THE LOAN" if r["weight"] == 1.25 else
              "holds cash" if r["weight"] < 1.0 else "levered")
        print(f"  {r['weight']:>6.2f}x {r['idle']:>5.0%} {r['switched']['excess']:>+11.2%} "
              f"{r['switched']['mo']:>+8.2f} {r['switch_value']/1200*args.capital:>+12.2f} "
              f"{r['switched']['dd_vs_bench']:>11.1%}   {st}")

    best = max(rows, key=lambda r: r["switched"]["excess"])
    print(f"\n  best stance over plain VOO: {best['weight']:.2f}x at {best['switched']['excess']:+.2%}/yr "
          f"(${best['switched']['mo']:+.2f}/mo)")
    loan = next(r for r in rows if r["weight"] == 1.25)
    at_full = next(r for r in rows if r["weight"] == 1.0)
    if abs(loan["switch_value"]) < 0.005:
        print("\n  and notice the loan row's switch value is exactly zero, not small. Under `borrow=\"posted\"` the")
        print("  engine charges one all-in desk rate on the borrowed leg, so the cash term appears twice and")
        print("  cancels: `(1-w)*c - (w-1)*(menu-c)` = `-(w-1)*menu`. A borrowed account cannot also collect a")
        print("  cash yield, which is the same thing round 31 found from the other side — the switch and the")
        print("  loan are one exposure to the rate curve, not two independent wins.")
    print(f"  at 1.25x the switch is worth ${loan['switch_value']/1200*args.capital:+.2f}/mo by that algebra.")
    print(f"  the cash switch at a FULLY invested account is worth "
          f"${at_full['switch_value']/1200*args.capital:+.2f}/mo, because `(1 - w) * cash` "
          f"is zero when w is 1 — the ledger's")
    print(f"  top row and its loan row are opposite stances on the same dollars, not two actions to add.")

    print(f"\n  why the ledger's positive rows do not sum")
    row = {a[0]: a[2] for a in al.ACTIONS}
    print(f"    idle cash switch   ${row['move idle cash out of the default sweep']:>7.2f}/mo priced on 100% of "
          f"the account sitting in cash — a 0.00x account, which forfeits the market")
    print(f"    constant 1.25x     ${row['a constant 1.25x book, financed at a posted desk rate']:>7.2f}/mo "
          f"priced on no idle cash at all — the switch is worth nothing "
          f"here and the loan pays the spread the switch would have earned")
    gap = (wc.EXPENSE["SPY"] - wc.EXPENSE[SYMBOL]) * args.capital / 12.0
    print(f"    cheap share class  ${gap:>7.2f}/mo worth exactly this only if the alternative is SPY; against a "
          f"{SYMBOL} benchmark it is zero")
    print(f"    distributions      ${row['reinvest distributions promptly']:>7.2f}/mo a non-action, listed so "
          f"it stops being a worry")
    print(f"\n    four rows, four different baselines. The one composition the goal asked for has one answer:")
    print(f"    the account beats the index by borrowing, or holds cash and does not.")

    keys, edge = monthly_edge(data, 1.25, DEFAULT_SWEEP, symbol="SPY")
    st = streaks(edge, keys)
    print(f"\n  the shape of that +27.24/mo, month by month, since {keys[0]}")
    print(f"    negative in {st['share_negative']:.1%} of months, longest losing run {st['worst_streak']} months, "
          f"worst single month {st['worst_month']:+.2%} (${st['worst_month']*args.capital:,.0f})")
    print(f"    deepest drawdown IN the excess itself: {st['cum_trough']:+.1%} "
          f"(${st['cum_trough']*args.capital:,.0f}) — the loan lagging plain holding, not the market lagging cash")
    print(f"    ...and that hole took {st['trough_years']} years to dig, {st['trough_from']} to {st['trough_to']}")
    for y in (1, 3, 5, 10):
        w = rolling_edge(edge, y)
        if not w:
            continue
        pos = sum(1 for x in w if x > 0) / len(w)
        print(f"    rolling {y:>2}-year: positive in {pos:>5.1%} of {len(w):>3} windows, "
              f"worst {min(w):+.2%}/yr, best {max(w):+.2%}/yr")
    print("\n    So the plan is not a paycheck. It pays about $27 a month on $20,000 on average and it is the wrong")
    yrs = abs(st["worst_month"]) * args.capital / (st["mean_month"] * args.capital * 12.0)
    print(f"    word to use beside 'each month': {st['share_negative']:.0%} of its months go backwards, and its worst")
    print(f"    single month (${st['worst_month']*args.capital:,.0f}) costs {yrs:.1f} times a FULL YEAR of that average pay.")
    print("    From 2000 to 2009 the levered book trailed plain holding for nine straight years. Anyone who needs")
    print("    the money to arrive monthly cannot hold through that, and the plan's own mean is no argument that")
    print("    they should try.")

    print(f"\n  the same policy on every sleeve in the archive, versus just holding that sleeve")
    print(f"  {'sleeve':>7} {'months':>7} {'own window':>11} {'common':>9} {'expense':>8}   {'$/mo':>8}")
    for sym in ("SPY", "VOO", "QQQ", "VTI", "ITOT"):
        f = legs(data, 1.25, DEFAULT_SWEEP, symbol=sym)
        c = legs(data, 1.25, DEFAULT_SWEEP, symbol=sym, last=common_months(data))
        print(f"  {sym:>7} {f['months']:>7} {f['excess']:>+10.2%} {c['excess']:>+8.2%} "
              f"{float(wc.EXPENSE[sym]):>7.2%}   {f['mo']:>+7.2f}")
    print("\n  Read the last two columns as one sentence. On the shared window the four broad-market funds agree")
    print("  within five basis points — as four funds on broad indexes must — and every one of them looks better")
    print("  on its own window than on the common one. The loan is worth ~2.45%/yr on any broad index over the")
    print("  last sixteen years and ~1.6%/yr across each fund's full history. QQQ's larger number is QQQ, not the")
    print("  loan, and its 0.20% expense is the most expensive line in the menu for the privilege of that view.")

    n_common = common_months(data)
    cov = {sym: len(wc.monthly(ifr.series_for(data, sym), data.cash_factors)[1])
           for sym in ("SPY", SYMBOL, "QQQ", "VTI", "ITOT")}
    print(f"\n  before trusting that number: the archive's series do not start together")
    print(f"    " + "  ".join(f"{k} {v}mo" for k, v in cov.items())
          + f"   -> common window {n_common} months")
    spy_full = legs(data, 1.25, DEFAULT_SWEEP, symbol="SPY")
    spy_com = legs(data, 1.25, DEFAULT_SWEEP, symbol="SPY", last=n_common)
    voo_com = legs(data, 1.25, DEFAULT_SWEEP, symbol=SYMBOL, last=n_common)
    fee_only = wc.EXPENSE["SPY"] - wc.EXPENSE[SYMBOL]
    print(f"    same policy, same window:   SPY {spy_com['excess']:+.3%}/yr   {SYMBOL} {voo_com['excess']:+.3%}/yr"
          f"   differ {abs(voo_com['excess'] - spy_com['excess']):.3%}")
    print(f"    the fee gap alone is {fee_only:.3%}, so the two funds track one index as they must.")
    print(f"\n    what actually moved round 38's 0.85%/yr was the sample, not the fund:")
    print(f"    SPY over its own 404 months {spy_full['excess']:+.2%}/yr; SPY over the common {n_common} months "
          f"{spy_com['excess']:+.2%}/yr.")
    print(f"    One fund, one policy, two windows, {abs(spy_com['excess'] - spy_full['excess']):.2%}/yr apart — "
          f"half the edge.")
    print(f"    The archive's first half contains dot-com and 2008; the second half does not. Any figure quoted")
    print(f"    here is a statement about a window as much as about a policy, and the windows differ by series.")
    print(f"\n    the SPY column reproduces the ledger's loan row exactly, and must: same stance, same financing.")
    print(f"    If that ever stops matching, the two files are no longer describing one account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
