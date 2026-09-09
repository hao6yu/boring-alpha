"""What financing rate does the surviving mechanism need — and can anyone actually get it?

Run: .venv/bin/python tools/financing_break_even.py [--sleeve SPY] [--window full]

Ten rounds of this repo have killed every signal it built. One mechanism survives: holding more
of the equity than you have money for. `leverage_sizing` (round 4) measured it on SPY at an
assumed borrow of archive cash plus 150 bps, and that assumption is the load-bearing member of
the whole result — a number about the world, not about a model, and until now unchecked.

It should not have been. US retail margin is posted, tiered and wildly dispersed: as of April 2026
the base tier — the tier a $5,000 opening and $500 a month actually pays, because the discounts
start at $25k-$100k — runs from 4.90% at the cheapest broker to about 12.00% at the most expensive,
against the same collateral under the same rules. That is 710 basis points of certainty, which is
two orders of magnitude more than the largest timing edge this repo has ever measured. If the
mechanism needs money at 9% and the account pays 10.575%, it has negative expected value and the
drawdown was a present bought at a loss.

So this tool asks the round-3 question inverted: not "what does leverage earn at an assumed rate"
but **what does it pay at rates that exist, and how much room is left before the gap closes**.
For each sleeve, window and leverage it reports:

  $/mo        the monthly equivalent of the terminal gap versus plain DCA, priced at the cheapest
              desk on the menu and at a large custodian's — the bill, not the promise;
  room        the break-even spread, by bisection: how much *more* spread the cell could absorb
              before the gap reaches zero. A diagnostic, and a window-relative one — it is solved
              in the cash world of the window it is measured over while the bill is paid in
              today's, which is why the two can disagree and why the verdict column reads off the
              bill rather than the room;
  clears      how many of the eight desks the gap survives, priced at the posted rate.

Two conventions, both inherited from round 4 so the tables read together:

  cadence     the gate from round 10 is *not* applied. A constant-leverage mandate specifies
              exposure at every moment, so drift back toward the target is the mandate rather
              than a violation of a review interval, and the band is the only thing standing
              between the book and churn. Rules that specify an interval get gated; this one
              specifies a level.
  low-L band  the band is suppressed below 1.25x, for the reason round 4 wrote down at length: a
              10% dead band is bigger than a $500 deposit once an account clears $5,000, so the
              deposit silently stays in cash and the row ends $163k light over 33 years. Rows at
              or below 1.0x borrow nothing, have no break-even to solve, and are refused rather
              than answered with a zero.

Costs: 2.0 bps per unit of one-way turnover, borrow at the archive's cash index plus a spread
charged daily on the borrowed leg only, the sleeve's real expense ratio, 30% maintenance equity
with forced sale when breached, $5,000 opening and $500 a month deposited on arrival. Comparator is
plain DCA into the same sleeve, same schedule, unlevered, from the sleeve's first session — not from
a policy's first live session, since this book has no warm-up. That makes it a different
comparator from `funded_policy`'s by design, and the two tables are not interchangeable.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import funded_policy as fp  # noqa: E402  (series + the archive every forward tool reads)
import withdrawal_capacity as wc  # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data  # noqa: E402
from funded_frame import per_month_equivalent  # noqa: E402
from run_voltarget_scan import funded  # noqa: E402

BAND = 0.10
TIGHT = 0.01                  # the band's own control; see `band_wedge`
SUPPRESS_BELOW = 1.25         # see "low-L band" in the module docstring
LEVERS = (1.25, 1.5, 2.0)     # round 4's grid, so the two tables read together
SLEEVES = ("SPY", "QQQ", "VTI", "ITOT", "VOO")
WINDOWS = {"full": fp.WINDOWS["full"], "since 2010": fp.WINDOWS["since 2010"],
           "recent": fp.WINDOWS["recent"]}
# Base (lowest) tier margin rates, as published in April 2026. The base tier is the point: this
# repo's account convention is $5,000 opened plus $500 a month, so the first tier is the tier.
# Source and caveats are in docs/notes/2026-09-06-financing-break-even.md.
MENU: tuple[tuple[str, float], ...] = (
    ("Public", 0.0490),
    ("Robinhood Gold", 0.0575),
    ("IBKR Pro", 0.0583),
    ("Moomoo", 0.0680),
    ("Schwab", 0.1000),
    ("E*TRADE", 0.1045),
    ("Fidelity", 0.10575),
    ("Firstrade", 0.1200),
)

HEAD = (f"{'lev':>4} {'ending':>13} {'$/mo cheap':>11} {'$/mo @10.6%':>12} {'room':>19} "
        f"{'maxDD':>7} {'calls':>5} {'carry':>8} {'band$':>9}  clears at")


def annualised_cash(factors: list[float]) -> float:
    """The cash index as one annual number, geometric. The arithmetic mean over a compounding
    daily series is not the rate anybody actually earned."""

    if not factors or not all(f > 0.0 for f in factors):
        raise ValueError("no usable cash index; nothing here can be discounted at it")
    growth = 1.0
    for factor in factors:
        growth *= factor
    return growth ** (252.0 / len(factors)) - 1.0


def trailing_cash(factors: list[float], years: int = 1) -> float:
    """The cash index over the most recent `years` — the only cash rate a forward book meets. The
    full archive averages 2.54% and the last year 3.81%, so any comparison between a rate solved
    across the archive and a rate posted today has to say which world it is in."""

    return annualised_cash(factors[-years * 252:] if len(factors) >= years * 252 else factors)


_CACHE: dict[tuple, object] = {}


def cell(window: str, symbol: str):
    """(dates, closes, returns, cash factors) for one slice, loaded once and shared — the CSV is
    the expensive part, and a bisection asks the same question fourteen times."""

    key = (window, symbol)
    if key not in _CACHE:
        slice_ = fp.series(symbol, WINDOWS[window])
        if len(slice_[0]) < 252:
            raise ValueError(f"{symbol} has {len(slice_[0])} sessions in {window}; a year is the "
                             f"minimum anything can be solved on, and a near-empty window would "
                             f"print $0 as though it were a result")
        _CACHE[key] = slice_
    return _CACHE[key]


def _run(dates, closes, returns, factors, symbol, lever, spread, band):
    """The shared engine, repriced for this sleeve, restored on exit.

    `EXPENSE` matters and is easy to forget: the engine's module constant is SPY's 9.45 bps, and
    running QQQ (20 bps) or a total-market fund (3 bps) without overriding it prices four
    different funds as the same one.
    """

    import run_voltarget_scan as engine

    saved = (engine.BORROW_SPREAD, engine.EXPENSE)
    engine.BORROW_SPREAD, engine.EXPENSE = spread, wc.EXPENSE.get(symbol, 0.0)
    try:
        return funded(closes, returns, factors, dates,
                      targets=[lever] * len(dates), band=band, start=1)
    finally:
        engine.BORROW_SPREAD, engine.EXPENSE = saved


def comparator(window: str, symbol: str):
    """Plain DCA: unlevered, never rebalanced, deposit spent on arrival, band 0."""

    key = ("comparator", window, symbol)
    if key not in _CACHE:
        _CACHE[key] = priced(symbol, window, 1.0, 0.015, 0.0)
    return _CACHE[key]


def priced(symbol: str, window: str, lever: float, spread: float, band: float | None = None):
    return _run(*cell(window, symbol), symbol, lever, spread,
                band if band is not None else (0.0 if lever < SUPPRESS_BELOW else BAND))


def at_rate(symbol: str, window: str, lever: float, rate: float):
    """The book as a desk would actually bill it.

    The engine accrues `cash_daily + spread`, so a desk charging `rate` all-in is passed a spread
    of `rate` minus the window's own cash rate, holding the *total* charge at the posted rate on
    average over the window. Passing the posted rate as the spread instead would charge the cash
    rate twice and overstate every desk by 150-400 bps, which is most of the margin this tool
    exists to measure.
    """

    return priced(symbol, window, lever,
                  max(rate - annualised_cash(cell(window, symbol)[3]), -0.05), TIGHT)


def band_wedge(symbol: str, window: str, lever: float) -> float:
    """What the no-trade band is worth in dollars: tight-band ending minus wide-band ending.

    The sign is not fixed and does not go one way, which is why this is a column and not an
    assumption. At 1.25x the band is wider than the monthly deposit, deposits sit in cash, and
    dropping the band is worth six figures. At 2.0x on QQQ the band also suppresses the
    sell-back-to-target that a crash forces, and skipping that deleveraging through a V-shaped
    collapse is worth more than the deposits were, so the wedge goes negative. The first draft of
    this tool asserted the first direction only, in writing, before measuring the second.
    """

    return (priced(symbol, window, lever, 0.015, TIGHT).ending
            - priced(symbol, window, lever, 0.015).ending)


def break_even_spread(symbol: str, window: str, lever: float, tolerance: float = 2.0,
                      high: float = 0.30) -> tuple[float | None, float]:
    """The borrow spread at which the levered book's terminal equals DCA's, and what the gap
    actually was at the spread returned.

    Priced at the tight band, the same band the bill and the verdict columns use: the wide band
    parks deposits in cash, which is a second, unrelated concession to leverage, and solving
    under it while billing under the tight band produced a break-even 40-65 bps too generous —
    a discrepancy the residual test caught, not this comment.

    The second half of the return value is the honest one. The terminal is *step-discontinuous*
    in the spread, because the spread moves the account along a path and the band flips whole
    trade decisions when the path crosses its boundary. So the crossing is not always a point:
    at 1.25x on the wide band the function jumps from +$1,590 to −$12,000 across a tenth of a
    basis point. Reporting the residual next to the spread says how much of the answer is a
    price and how much is a cliff; reporting only the spread would invent precision the
    simulator does not have.

    `(None, gap)` when the question has no answer, rather than a number pretending to be one: at
    or below 1.0x the book never borrows, so every spread is a break-even and none is informative;
    and a book that loses to DCA with money at zero interest has no spread that rescues it.
    """

    if lever <= 1.0 + 1e-9:
        raise ValueError(f"{lever:.2f}x borrows nothing, so it has no break-even spread to solve")
    base = comparator(window, symbol)
    cheap, dear = priced(symbol, window, lever, 0.0, TIGHT), priced(symbol, window, lever, high, TIGHT)
    if cheap.ending - base.ending <= 0.0:
        return None, cheap.ending - base.ending
    if dear.ending - base.ending >= 0.0:
        return high, dear.ending - base.ending
    low, top, gap = 0.0, high, 0.0
    for _ in range(20):
        mid = (low + top) / 2.0
        gap = priced(symbol, window, lever, mid, TIGHT).ending - base.ending
        if abs(gap) < tolerance:
            return mid, gap
        low, top = (mid, top) if gap > 0 else (low, mid)
    # The fall-through return must re-price at the spread it is about to hand back. The function is step-discontinuous in
    # the spread (see the docstring: the band flips whole trade decisions), and `gap` above belongs to the *previous* probe,
    # which is a different spread from the narrowed midpoint. Reporting the old probe's residual alongside a new spread is
    # the same fault as a check that reports its own input: it looks like a measurement of the answer and measures the
    # search. Round 98's suite caught this as a $5.97 disagreement between the reported residual and a fresh run — the
    # test that re-prices rather than trusting the solver's word (r93).
    answer = (low + top) / 2.0
    return answer, priced(symbol, window, lever, answer, TIGHT).ending - base.ending


def per_month(book, base) -> float:
    """The terminal gap as the level monthly amount it is worth, at the *comparator's* rate."""

    first, last = base.path[0][0], base.path[-1][0]
    months = max(int(round(max((last - first).days, 30) / 365.2425 * 12)), 1)
    return per_month_equivalent(book.ending - base.ending, base.irr, months)


def report(symbol: str, window: str, tally: list) -> None:
    dates, _closes, _returns, factors = cell(window, symbol)
    base = comparator(window, symbol)

    print(f"\n{symbol} · {window} · {dates[0]}..{dates[-1]} · {len(dates)} sessions · "
          f"cash over window {annualised_cash(factors):.2%} · comparator ${base.ending:,.0f} at "
          f"{base.irr:+.2%}, DD {base.max_drawdown:.1%}")
    print(HEAD)
    for lever in LEVERS:
        desk = {name: at_rate(symbol, window, lever, rate) for name, rate in MENU}
        monthly = {name: per_month(book, base) for name, book in desk.items()}
        cleared = [name for name, _ in MENU if desk[name].ending > base.ending]
        be, residual = break_even_spread(symbol, window, lever)
        book = priced(symbol, window, lever, 0.015, TIGHT)
        room = "no answer" if be is None else f"{be * 1e4:,.0f} bps ±${abs(residual):,.0f}"
        room = room if len(room) <= 19 else ("no answer" if be is None
                                             else f"{be * 1e4:,.0f} bps ±{abs(residual) * 0.001:,.1f}k")
        print(f"{lever:4.2f} {book.ending:13,.0f} {monthly[MENU[0][0]]:+11,.0f} "
              f"{monthly['Fidelity']:+12,.0f} "
              f"{room:>19} "
              f"{book.max_drawdown * 100:6.1f}% {book.margin_calls:5d} {book.carry_paid:8,.0f} "
              f"{band_wedge(symbol, window, lever):+9,.0f}  "
              + (f"{len(cleared)}/{len(MENU)} desks, up to {cleared[-1]}" if cleared
                 else "no desk on the menu"))
        tally.append({"sleeve": symbol, "window": window, "lever": lever, "be": be,
                      "monthly": monthly, "cleared": len(cleared), "dd": book.max_drawdown})


def summary(tally: list, today: float) -> None:
    print(f"\n{'—' * 78}")
    print(f"the same {len(tally)} cells billed at each desk's posted rate, worst cell included:")
    for name, rate in MENU:
        vals = [t["monthly"][name] for t in tally]
        print(f"  {name:15} posted {rate:7.2%}   median {statistics.median(vals):+6,.0f}/mo   "
              f"worst cell {min(vals):+6,.0f}/mo   positive in "
              f"{sum(1 for v in vals if v > 0):2d} of {len(vals)}")
    needed = [t["be"] for t in tally if t["be"] is not None]
    print(f"room before the gap closes, in each window's own cash world: median "
          f"{statistics.median(needed) * 1e4:,.0f} bps, narrowest "
          f"{min(needed) * 1e4:,.0f} bps, widest {max(needed) * 1e4:,.0f} bps")
    worst = min(tally, key=lambda t: t["dd"])
    print(f"deepest drawdown on the grid: {worst['dd'] * 100:.1f}% "
          f"({worst['sleeve']} {worst['window']} at {worst['lever']:.2f}x), against today's cash "
          f"of {today:.2%}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sleeve", default=None, choices=list(SLEEVES))
    parser.add_argument("--window", default="all", choices=["all", *WINDOWS])
    args = parser.parse_args()

    print("the financing break-even for the one mechanism still standing")
    print("$/mo is the terminal gap as a level monthly amount at the comparator's own rate,")
    print("priced at that desk's POSTED rate — the bill, not the promise")
    today = trailing_cash(cell("full", "SPY")[3])
    print("menu (April 2026 base tiers), over today's cash of "
          f"{today:.2%}: " + ", ".join(f"{n} {r:.2%}" for n, r in MENU))

    chosen = [args.sleeve] if args.sleeve else list(SLEEVES)
    windows = [args.window] if args.window != "all" else list(WINDOWS)
    tally: list = []
    for window in windows:
        for symbol in chosen:
            try:
                cell(window, symbol)
            except ValueError as error:
                print(f"\n{symbol} · {window}: {error}")
                continue
            report(symbol, window, tally)
    if tally:
        summary(tally, today)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
