"""Two ways to hold more of the same index, priced against each other: a broker loan and a fund's own leverage.

    .venv/bin/python tools/leverage_routes.py
    .venv/bin/python tools/leverage_routes.py --weight 2.0 --fund-er 0.0095 --swap 0.0100
    .venv/bin/python -m pytest tests/test_leverage_routes.py -q

Rounds 29 and 30 left one plan in the repository that beats the index under honest costs, and it is a loan at a
broker that has to approve the account, maintain it, and can raise its rate on a Tuesday. But there is a second
route to exactly the same exposure that needs none of that: a leveraged ETF, whose leverage is embedded in the
product and whose cost is charged to the fund rather than to the account. For anyone who cannot or does not want
to run a margin account — and at $20,000, in a tax-advantaged account, that is most people — it is the only
route. So the surviving conclusion of five rounds of work has a substitute worth pricing, and nobody had priced it.

## The arithmetic, which is not the arithmetic people expect

The intuitive version says the leveraged fund is obviously cheaper because 0.95% is not a big number. The
accounting version says something else, and it comes down to *what the rate is charged on*:

  * **A loan** charges its rate on the borrowed part only. To hold `L` you borrow `L − 1` per dollar of equity, so
    the all-in extra cost per dollar of *exposure* is `(L − 1) / L × rate`.
  * **A fund's own leverage** charges its costs on the whole position, and it pays a dealer to hold the swap for
    it — so the fund pays the same rate the desk would have charged, *plus* its management fee, on the borrowed
    part, and then charges the management fee again on everything.

At 1.25× that difference is decisive on today's numbers: **a loan costs 0.98%/yr of exposure and the fund costs
1.53%** — the fund is 55% more expensive, because it pays the funding spread the borrower would have paid *and* the
manager's fee. The fund only wins when the funding benchmark collapses toward zero, at which point the fund's
fixed fee is the only cost left. That crossover is below **0.15%** on the sticker fee and never happens at all once
a realistic dealer spread is included. In the sealed archive, the fund wins in **23% of months** at zero assumed
swap and in **no months at all** at a 50bp spread — and those 23% are the 2012-2021 decade, not the present.

## The cost the arithmetic above cannot see

Volatility drag, and it is not a fee. A fund that resets daily compounds `L` returns on the *prior day's* balance,
so in a market that goes nowhere it loses money: at 1.25× with 20% annualised vol and a flat index, roughly
`−(L−1)·L/2·σ² ≈ −1.25%·L·σ²` a year of pure path cost, growing with the square of the leverage and completely
absent from any expense ratio. A margin account rebalanced monthly has no such term, because its leverage is
re-stated rather than re-compounded. This file therefore prices the *cost* route and prints the drag term beside it
as an explicit warning, but it does not simulate the drag — doing that honestly needs daily paths over the whole
archive, and the correct answer is that at 1.25× the term is small and at 3× it is a strategy decision in itself.

## What this file deliberately does not claim

  * **No specific fund is endorsed.** `--fund-er` is a parameter and the sticker fee is not the fund's real cost.
    The numbers printed at 0.95% are illustrative of a 3× product's published fee; a fund's true cost is its
    tracking difference, which requires its price history, which this archive does not contain.
  * **The dealer's swap spread is assumed, not observed.** It is the single most load-bearing unknown here and it
    moves the answer from "sometimes cheaper" to "never". The flag exists so the sensitivity is visible.
  * **Margin rates are posted tiers, not yours.** Round 30 established the real rate floats, and this file uses
    the posted tier for the same reason the ledger does: it is the conservative direction for a borrower.

"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cash_yield_gap as cyg                       # noqa: E402
import income_frontier as ifr                      # noqa: E402
import withdrawal_capacity as wc                   # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data    # noqa: E402

SYMBOL = "SPY"
FUND_ER = 0.0095          # a 3x product's published fee; a parameter, not a recommendation
DEALER_SWAP = 0.0050      # what a swap counterparty charges to hold the fund's leverage
CAPITAL = 20_000.0


def curve(data) -> list:
    """The archive's bill curve, annualised, one entry per month."""

    return [r * 12.0 for r in wc.monthly(ifr.series_for(data, SYMBOL), data.cash_factors)[1]]


def cost_of_loan(weight: float, rate: float) -> float:
    """Annual cost per dollar of *exposure* when the account borrows the gap itself."""

    return (weight - 1.0) / weight * rate


def cost_of_fund(weight: float, er: float, swap: float, bill: float) -> float:
    """Annual cost per dollar of exposure when a fund borrows it for you.

    Careful with the denominators, because this is where the intuition goes wrong. The fund's fee is charged on
    the whole position, which is `L` units per unit of equity, and the dealer's funding is charged on the borrowed
    `L − 1`. Per unit of EXPOSURE the fee is then simply `er` and the funding `(L−1)/L × (bill + swap)` — so the
    fee does NOT shrink with leverage while the funding does, which is the whole reason a loan wins at low leverage
    and a fund starts to look reasonable only at high leverage, where the same fee is spread over more exposure.
    """

    return er + (weight - 1.0) / weight * (bill + swap)


def crossover_bill(weight: float, er: float, swap: float, posted: float) -> float:
    """The bill-curve level at which the two routes cost the same: below it the fund wins, above it the loan does.

    Setting `(L−1)·b + L·er = (L−1)·(posted)` and solving gives `b* = posted − swap − L·er/(L−1)`. A negative
    answer is the interesting one and the common one at low leverage: the fund can never win at this spread,
    because its fee on the unlevered slice is larger than the entire funding advantage.
    """

    return posted - swap - weight * er / (weight - 1.0)


def drag(weight: float, sigma: float) -> float:
    """Approximate annual path cost of a daily-reset fund: `-(L-1)*L/2 * sigma^2`. An approximation is the right
    tool for a warning; the honest version is a simulation this file does not run."""

    return -(weight - 1.0) * weight / 2.0 * sigma ** 2


def main() -> int:
    ap = argparse.ArgumentParser(description="compare a margin loan with a fund's own leverage")
    ap.add_argument("--weight", type=float, default=1.25)
    ap.add_argument("--fund-er", type=float, default=FUND_ER)
    ap.add_argument("--swap", type=float, default=DEALER_SWAP)
    ap.add_argument("--sigma", type=float, default=0.16, help="annual vol, for the daily-reset drag term")
    ap.add_argument("--capital", type=float, default=CAPITAL)
    args = ap.parse_args()
    if args.weight <= 1.0:
        raise SystemExit("an unlevered book is round 24's cash decision, not a leverage route")

    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    rates = curve(data)
    bill_now = cyg.bill(data)["current3m"]
    posted = ifr.MENU_PUBLIC
    scale = args.capital / CAPITAL

    print(f"routes to {args.weight:.2f}x {SYMBOL} · capital ${args.capital:,.0f} · costs per dollar of EXPOSURE\n")
    print(f"  posted margin rate      {posted:.2%}      bill curve today  {bill_now:.2%}      "
          f"fund sticker {args.fund_er:.2%}   dealer swap {args.swap:.2%}")
    loan = cost_of_loan(args.weight, posted)
    fund = cost_of_fund(args.weight, args.fund_er, args.swap, bill_now)
    print(f"\n  TODAY, today")
    print(f"    margin at the broker  {loan:.2%} of exposure   ${loan * args.capital * args.weight:,.0f}/yr on the book")
    print(f"    a fund's own leverage {fund:.2%} of exposure   ${fund * args.capital * args.weight:,.0f}/yr on the book")
    verdict = "the loan is cheaper" if loan < fund else "the FUND is cheaper"
    print(f"    -> {verdict}, by {abs(fund - loan):.2%} of exposure "
          f"(${abs(fund - loan) * args.capital * args.weight:,.0f}/yr on the book, "
          f"{abs(fund - loan) / max(loan, 1e-9):.0%} relative)")

    x = crossover_bill(args.weight, args.fund_er, args.swap, posted)
    print(f"\n  WHERE THAT FLIPS")
    if x > 0:
        share = sum(1 for b in rates if b < x) / len(rates)
        print(f"    the fund wins only when the bill curve is below {x:.2%}.")
        print(f"    the record has been below that in {share:.0%} of its {len(rates)} months, and is not today.")
        if share > 0.9:
            print(f"    (that is nearly the whole record, which means the loan is worse almost everywhere the")
            print(f"     archive looked — at {args.weight:.2f}x and this spread, convenience is the cheap route.)")
    else:
        print(f"    never. At a {args.swap:.2%} dealer spread the fund cannot beat the loan at any interest rate:")
        print(f"    its fee on the unlevered slice alone ({args.fund_er:.2%}) already costs more than the funding")
        print(f"    advantage the loan enjoys. The crossover solves to {x:.2%}, which is not a rate.")

    print(f"\n  WHAT THE COST COMPARISON CANNOT SEE")
    print(f"    a daily-reset fund pays a path cost the loan does not: at {args.sigma:.0%} annual vol that is "
          f"{drag(args.weight, args.sigma):.2%} a year,\n    not in any expense ratio, "
          f"and ${abs(drag(args.weight, args.sigma)) * args.capital * args.weight:,.0f}/yr on the book."
          f" It grows with the SQUARE of leverage.")
    print(f"\n  So the fund is the route that needs no approval, no margin agreement and no taxable-account")
    print(f"  position, and it pays for that convenience. The loan is cheaper almost always; the fund is available")
    print(f"  almost always. Which one is right is a question about the account, and this file only prices them.")
    print(f"\n  Sources: `income_frontier.MENU_PUBLIC` (April 2026 posted tier), the DGS3MO curve in the sealed")
    print(f"  snapshot, published fund expense ratios as PARAMETERS. No fund price history is in this archive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
