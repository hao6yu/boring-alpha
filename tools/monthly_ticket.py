"""SUPERSEDED for the plan you should run — see `tools/shelter_ticket.py`. Kept because the desk arithmetic is evidence.

This file's first sentence used to be "the only mechanism in this repository that beats plain DCA", written at round 12
about a 1.25x book. Rounds 29 and 30 withdrew it by doing the obvious thing to a levered plan and charging it: at the
202 bps a desk actually posts, the financing term costs more than the leverage earns, and the book loses to holding the
same fund. Round 61 found no configuration that beats the index on return, and round 68 fixed what the surviving
construction is actually worth — a trend rule sheltered in intermediate Treasuries, +$130 to +$145 a month per $100,000
of **withdrawal capacity** over plain VOO, nothing on return. Round 70 watched both books on one May 2025 session: the
financed ticket paid 6.47 in costs against the sheltered one's 3.26, and finished further behind doing-nothing.

So this desk-break-even work still matters — it is why the levered plan is refused rather than ignored, and it is the only
posted-rate table in the repository — but the sheet it issues is not the recommendation. Run
`.venv/bin/python tools/shelter_ticket.py`.

----

This month's ticket for the levered sleeve — priced at your size.

Run: .venv/bin/python tools/monthly_ticket.py [--sleeve SPY] [--lever 1.25] [--desk Public]
         [--value 20000] [--window full]

Fifteen rounds of this repo have measured every signal it could build against plain DCA into the same fund,
and exactly one thing has survived: holding more of a broad equity sleeve than the account has money for,
at a rate that exists. Rounds 11 and 12 measured it — clears at 1.25x and above on four of eight posted
desks, median +$95 a month at a cheap one, and negative at the dearest — and it contains no forecast at all.
Everything else the goal asked for (news, trend calls, a short-horizon decision) has been priced and failed.

So this file is not another test. It is the artifact the surviving result should have had from the start: an
instruction sheet with numbers in it, and a refusal path. **The plan is worth nothing if the tool cannot say
no**, and the rate at which it must say no is measurable, so it is computed here rather than asserted: the
borrow break-even of the same book, on the same deposit schedule, in every window the archive holds. This
ticket is issued only if the chosen desk clears the *least generous* of them.

## The claim, written before the arithmetic

  * At the cheapest base tier on the April 2026 menu (4.90%), 1.25x on a broad US equity sleeve beats plain
    DCA into that sleeve on this account's own deposit schedule, in every window in the archive.
  * The excess is arithmetic, not alpha: it is 0.25 x (sleeve return − borrow rate) per year, which is the
    equity premium of a quarter of the account arriving early. It is therefore **not profit for being
    clever**, and it reverses whenever the sleeve's return falls toward the borrow rate.
  * At the size this account actually starts at, that excess is worth tens of dollars a month, not hundreds.
    The +$142/month figure on the archive's full record belongs to a path that compounds $500 a month for
    thirty-three years, and it is printed here labelled as exactly that, beside the number that applies to
    the account in front of it.
  * The plan fails at a posted rate above the break-even, at any sleeve whose expected return is near the
    borrow rate, and at a broker that reprices the base tier. It is not a lever that can be pulled once.

Nothing in this file is a recommendation to borrow. It is the bill of costs for a decision already measured,
in the units the decision has to be made in — and the printed refusal when those units say no.

## Conventions, all inherited so nothing here is re-derived

Exposure, band, maintenance and forced delevering, the 2 bps per unit of one-way turnover, the sleeve's real
expense ratio, and the $5,000 + $500/month schedule all come from `financing_break_even` (round 11), which
inherits them from `leverage_sizing` (round 4). The desk menu is the same eight posted base tiers. A desk's
*posted* rate is passed to the engine as `rate − window cash rate`, because the engine accrues cash plus a
spread — passing the posted rate as the spread would charge the T-bill twice and overstate every desk by
150-400 bps, which is most of the margin this comparison exists to measure.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import financing_break_even as fbe                # noqa: E402  the engine, the menu, the break-even
from boring_alpha.data.csv_loader import (        # noqa: E402
    load_csv_market_data,
)

SNAPSHOT, CASH_FILE = ROOT / "data" / "current" / "market_daily.csv", ROOT / "data" / "current" / "cash_daily.csv"
TURNOVER_BPS = 2.0        # one-way, per unit: the same toll every funded tool in this repo charges
CASH_LEG_WARNING = (                                                      # round 29: the ticket's own caveat
    "and is worth nothing at a real brokerage sweep. For THIS policy that gap is small and does not\n"
    "      reverse the verdict: a constant 1.25x book pays interest on the loan and never sits in idle cash\n"
    "      to be under-credited, so under sweep cash and posted borrow it measures +1.63%/yr = +$27/mo at\n"
    "      $20,000, against +2.20% above (round 29). What the action ledger scores at -$4/mo is a DIFFERENT\n"
    "      book — the vol-target signal, averaging 1.02x, which spends a quarter of its life in cash that is\n"
    "      not credited. Do not read one as the other: notes/2026-09-06-ticket-repricing.md."
)
MAINTENANCE = 0.30        # Reg T maintenance equity, the level at which the engine force-sells to 1.0x

#: Cost term of the forward identity, taken from what the engine actually charged rather than from
#: the flat turnover allowance. Bps of ending NAV, a year.
def ticket_cost(book, years: float) -> float:
    return (book.carry_paid + book.cost_paid) / max(book.ending, 1.0) / years * 1e4



@dataclass
class Ticket:
    sleeve: str
    lever: float
    desk: str
    rate: float
    value: float
    price: float
    asof: str
    target: float
    units: float
    borrow: float
    carry_month: float
    carry_year_bps: float
    measured_cost_bps: float
    margin_calls: int
    archive_per_month: float
    trigger_price: float
    trigger_fall: float
    break_even_allin: dict
    worst_break_even: float
    sleeve_irr: float
    excess_bps: float
    excess_measured: float
    per_month_at_size: float
    clears: tuple
    issued: bool


def allin_break_even(symbol: str, window: str, lever: float) -> float:
    """The posted all-in borrow rate at which this sleeve and window stop beating unlevered DCA.

    `break_even_spread` solves in the window's own cash world; adding the window's realised cash rate back
    converts it to the number a broker's pricing page is comparable to. The break-even is solved at the
    leverage being asked about, never at a fixed one: at 2x the loan is twice as big and the break-even is
    nearer, and a ticket that quoted one number for every size would be quoting the wrong one. Note that
    `financing_break_even` declares `comparator(window, symbol)` and `break_even_spread(symbol, window)`
    with their arguments the other way round, which is why every call here is by keyword.
    """

    spread, _gap = fbe.break_even_spread(symbol=symbol, window=window, lever=lever)
    return spread + fbe.annualised_cash(fbe.cell(window, symbol)[3])


def issue(sleeve: str, lever: float, desk: str, value: float, window: str,
          windows: tuple = ("full", "since 2010", "recent")) -> Ticket:
    rate = dict(fbe.MENU)[desk]
    data = load_csv_market_data(SNAPSHOT, CASH_FILE)
    asof = max(d for d in data.by_date if sleeve in data.by_date[d])
    price = data.by_date[asof][sleeve].close

    be = {w: allin_break_even(sleeve, w, lever) for w in windows}
    worst = min(be.values())
    comp = fbe.comparator(window, sleeve)
    # The forward arithmetic, in bps of NAV: leverage only pays to the extent the sleeve outruns the loan.
    excess_bps = (lever - 1.0) * (comp.irr - rate) * 1e4 - TURNOVER_BPS * 2.0
    # Reg T, in one line: the loan is fixed in dollars, so a price fall of f leaves equity V(1 - L f)
    # on a position of L V (1 - f). Requiring that ratio to clear m gives the exact trigger below. The
    # first version of this line printed 1 - L m. Below 1/m x that approximation is conservative and
    # above it the approximation tells the operator to watch a price the broker has already breached:
    # same formula, opposite risk, decided by a number nobody was looking at.
    trigger_fall = min((1.0 - MAINTENANCE * lever) / (lever * (1.0 - MAINTENANCE)), 1.0 / lever)
    clears = tuple(name for name, posted in fbe.MENU if posted <= worst)
    # The archive's own evidence about this exact book, so the identity above can be distrusted against
    # something measured rather than against nothing.
    book = fbe.at_rate(sleeve, window, lever, rate)
    years = max((book.path[-1][0] - book.path[0][0]).days / 365.2425, 1.0)
    ticket = Ticket(
        sleeve=sleeve, lever=lever, desk=desk, rate=rate, value=value, price=price, asof=asof.isoformat(),
        target=value * lever, units=value * lever / price, borrow=value * (lever - 1.0),
        carry_month=value * (lever - 1.0) * rate / 12.0,
        carry_year_bps=(lever - 1.0) * rate * 1e4,
        measured_cost_bps=(book.carry_paid + book.cost_paid) / max(book.ending, 1.0) / years * 1e4,
        margin_calls=book.margin_calls,
        archive_per_month=fbe.per_month(book, comp),
        trigger_price=price * (1.0 - trigger_fall) if trigger_fall > 0 else price,
        trigger_fall=trigger_fall,
        break_even_allin=be, worst_break_even=worst, sleeve_irr=comp.irr, excess_bps=excess_bps,
        excess_measured=(lever - 1.0) * (comp.irr - rate) * 1e4 - ticket_cost(book, years),
        per_month_at_size=value * ((lever - 1.0) * (comp.irr - rate) * 1e4 - ticket_cost(book, years)) / 1e4 / 12.0,
        clears=clears, issued=rate <= worst and lever > 1.0,
    )
    return ticket


def render(t: Ticket, window: str) -> str:
    bar = "=" * 78
    out = [bar,
           f"  {t.lever:.2f}x {t.sleeve}  ·  financed at {t.desk} {t.rate:.3%}  ·  "
           f"account ${t.value:,.0f}  ·  priced at {t.sleeve} {t.price:,.2f} on {t.asof}",
           bar]
    if not t.issued:
        out += [f"  REFUSED. {t.desk} posts {t.rate:.3%} and the break-even on the least generous window "
                f"is",
                f"  {t.worst_break_even:.2%} ({', '.join(f'{w}: {r:.2%}' for w, r in t.break_even_allin.items())}).",
                f"  Borrowing at this rate to buy {t.sleeve} is expected to lose against just buying "
                f"{t.sleeve}.\n",
                f"  Desks that clear {t.worst_break_even:.2%} on today's menu: "
                f"{', '.join(t.clears) if t.clears else 'none — run it unlevered'}.", ""]
        return "\n".join(out)

    out += [
        "",
        "  ORDER THIS MONTH",
        f"    target exposure   ${t.target:>12,.0f}   = {t.lever:.2f}x of NAV, in {t.sleeve}",
        f"    units at close    {t.units:>12,.2f}   shares (or ETF units) at ${t.price:,.2f}",
        f"    financed portion  ${t.borrow:>12,.0f}   the loan, at {t.desk}",
        f"    carry this month  ${t.carry_month:>12,.2f}   interest, billed monthly ({t.carry_year_bps:,.0f} bps of NAV a year)",
        f"    delever trigger   ${t.trigger_price:>12,.2f}   {t.sleeve} close; a {t.trigger_fall:.0%} fall from here",
        f"                      forces the position back to 1.00x, because Reg T maintenance is "
        f"{MAINTENANCE:.0%} equity.",
        f"                      That price assumes the loan just sits there. A book that rebalances to",
        f"                      target on the schedule delevers as it falls and never reaches it: this",
        f"                      same book, run over the archive, took {t.margin_calls} margin call(s).",
        "",
        "  WHAT IT HAS TO EARN TO BE WORTH IT",
        f"    {t.sleeve} money-weighted return, {window}: {t.sleeve_irr:.2%}",
        f"    break-even borrow, all-in: " + "  ".join(f"{w} {r:.2%}" for w, r in t.break_even_allin.items()),
        f"    headroom at {t.desk}: {t.worst_break_even - t.rate:+.2%} (the binding window decides, not the average)",
        f"    expected excess over unlevered DCA: {t.excess_bps:+,.0f} bps of NAV a year",
        f"      = {t.lever - 1:.2f} x ({t.sleeve_irr:.2%} sleeve - {t.rate:.2%} borrow) - {TURNOVER_BPS * 2:.0f} bps of turnover",
        f"    on the book's own measured costs ({t.measured_cost_bps:,.0f} bps, not {TURNOVER_BPS * 2:.0f}): {t.excess_measured:+,.0f} bps, and that is the line below",
        f"    at ${t.value:,.0f} of NAV that is {t.per_month_at_size:+,.0f} dollars a month, "
        f"or {t.per_month_at_size * 12 / max(t.value, 1):+.2%} a year",
        f"      BUT THE LINE ABOVE ASSUMES THE CASH LEG EARNS THE BILL CURVE, which this account does not",
        f"      {CASH_LEG_WARNING}",
        "",
        f"  Archive note: the same policy on this repo's $5,000 + $500/month schedule over the {window} "
        f"window",
        f"  ends {t.archive_per_month:+,.0f} dollars a month ahead of DCA. That figure is a compounding path "
        f"whose",
        f"  deposits run for the whole window, not a forecast for an account starting today — the line",
        f"  above is the one for this size.\n",
        f"  Clears the break-even at {len(t.clears)} of {len(fbe.MENU)} posted desks: {', '.join(t.clears)}.\n",
        "  Plan string for the journal (`journalctl.py close`, first field):",
        f"    {t.lever:.2f}x {t.sleeve} at {t.desk} {t.rate:.3%}, band 10%, delever to 1.00x under "
        f"{MAINTENANCE:.0%} maintenance",
        bar, ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sleeve", default="SPY", choices=list(fbe.SLEEVES))
    ap.add_argument("--lever", type=float, default=1.25)
    ap.add_argument("--desk", default="Public", choices=[n for n, _ in fbe.MENU])
    ap.add_argument("--value", type=float, default=20_000.0, help="account NAV to write the ticket against")
    ap.add_argument("--window", default="full", choices=list(fbe.WINDOWS))
    ap.add_argument("--json", action="store_true", help="machine-readable, for the forward record")
    args = ap.parse_args()

    if not args.json:
        print("  SUPERSEDED as a recommendation (marked round 71, withdrawn by rounds 29-30): a levered book loses to the same fund held"
              " unlevered once the loan is charged what a desk posts (rounds 29, 30, 61, 70).\n"
              "  For the construction this repository does stand behind, run `tools/shelter_ticket.py`."
              "  This sheet is the desk arithmetic, kept on purpose.\n")

    if args.lever <= 1.0:
        print(f"{args.lever:.2f}x borrows nothing, so there is no ticket and nothing to bill. "
              f"Buy the sleeve; the comparator in every note in this repo is exactly that.")
        return 2
    if args.value < 2_000:
        print(f"${args.value:,.0f} of NAV at {args.lever:.2f}x carries ${args.value * (args.lever - 1):,.0f} "
              f"of debt; the carry is billed monthly and the minimum deliverable at most desks is one "
              f"share. Nothing here is worth refusing over, but the ticket below is a rounding error "
              f"with a margin agreement attached.")

    t = issue(args.sleeve, args.lever, args.desk, args.value, args.window)
    if args.json:
        print(json.dumps(t.__dict__, sort_keys=True, indent=2, default=str))
        return 0 if t.issued else 1
    print("the monthly ticket · issued only if the desk clears the break-even on the least generous window\n")
    print(render(t, args.window))
    print("What this ticket is not: it is not a signal, it has no view, and it does not respond to news. "
          "It is a\nfixed exposure chosen once and financed every month, which is the shape of the only "
          "thing in\nthis repository that beat DCA net of a real broker's real rate. If the goal is a bot "
          "that reads\nthe news and trades it, that mechanism has been tested six ways here and is not "
          "this.")
    return 0 if t.issued else 1


if __name__ == "__main__":
    raise SystemExit(main())
