"""One sourced expense-ratio table for every sleeve in this repository's universe.

Before round 94 the same fact — what a fund charges its holders each year — was written down in four places and agreed in none of
them. `paper.FEES` carried five posted ratios and charged the other seven legs a flat 0.35% guess. `run_comparator_battery.py`
carried its own nine-line table, four of whose values were wrong (IEF and TLT at 0.38%/0.48% when both charge 0.15%, EEM at 0.32%
and DBC at 0.65% when they charge 0.72% and 0.84%). `cross_section.py` had a near-correct twelve-line table, three basis points off
on DBC. `withdrawal_capacity.py` posted five and refused the rest, which is the only honest stance available when a file has to
decide. Round 83 measured the whole 50/50 book's rebalancing bill at 0.054% of paid in over sixteen years; the battery's TLT line
alone was 33 bps a year wrong, six times the cost the entire strategy was being graded on. Hand-copied constants rot (r91), and
this is a fee table, which is the one input the whole programme has already learned dominates every signal in the archive (r86).

So the ratios live here, once, with the source and the date they were read. A tool that wants a fee imports this file. A tool that
wants to score a sleeve this file does not price must say so and refuse, which is what `withdrawal_capacity.py` still does — its
refusal is a decision about which universe it grades, not a gap in this table.

Two things this table does not pretend about. First, a ratio is not a constant over a sixteen-year record: iShares cut EFA and EEM
more than once inside the window this repository scores, and every number here is the one published today, which flatters any
strategy that held those legs early. Second, the sealed books are not retroactively corrected: a paper book's fees are frozen in
its config at the anchor, and a book whose cost assumption changes mid-chain stops being one chain. What changes is what the
research says, and what the next anchor will charge.

    .venv/bin/python tools/fund_fees.py            # the table, the guess, and the correction it implies
    .venv/bin/python tools/fund_fees.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Read on this date, from each fund's own published ratio as carried by https://stockanalysis.com/etf/<ticker>/ (a secondary
#: source, chosen because it renders the number in text; the issuers' own product pages carry the same figures behind script).
#: `tests/test_fund_fees.py` re-checks the table against the strings below, not against a copy of itself.
RETRIEVED = "2026-09-08"
SOURCE = "https://stockanalysis.com/etf/{ticker}/"

#: A ratio for a fund this file does not price. Deliberately not zero, and — unlike the guess it replaces — used only where the
#: symbol is genuinely absent from the table, never as a stand-in for a ratio that could have been looked up.
GUESS = 0.0035

#: ticker -> (ratio, issuer, note). The five that were always posted keep their exact values: sealed chains priced with them are
#: immutable, and `SPY` at 0.0945% is the gross prospectus ratio rather than the 0.09% rounded figure a screener prints.
RATIOS: dict[str, tuple[float, str, str]] = {
    "SPY": (0.000945, "State Street", "posted in this repository since round 1; a witness for the journal's own chain"),
    "VOO": (0.0003, "Vanguard", "the bar every other claim in this repository is measured against"),
    "VTI": (0.0003, "Vanguard", "the same bet as SPY at a third of the fee"),
    "ITOT": (0.0003, "iShares", "total-market, priced with the fund, not the index"),
    "QQQ": (0.0020, "Invesco", "the growth sleeve, six times VOO's ratio"),
    "IWM": (0.0019, "iShares", "was charged the 0.35% guess: the guess was 16 bps too harsh"),
    "EFA": (0.0032, "iShares", "was charged the guess: 3 bps too kind; iShares has cut this ratio inside the scored record"),
    "EEM": (0.0072, "iShares", "was charged the guess: 37 bps too kind, and the battery had it at 0.32%"),
    "IEF": (0.0015, "iShares", "was charged the guess: 20 bps too harsh; the battery had it at 0.38%"),
    "TLT": (0.0015, "iShares", "was charged the guess: 20 bps too harsh; the battery had it at 0.48%"),
    "GLD": (0.0040, "SPDR", "was charged the guess: 5 bps too kind, in the one direction the old comment did not admit"),
    "DBC": (0.0084, "Invesco", "was charged the guess: 49 bps too kind, and the dearest leg in the universe by a factor of 28"),
}

#: Funds a paper book never trades but the research has to price anyway: the bill legs a cash sleeve would use. They are kept
#: out of `RATIOS` on purpose — `paper.py` raises if a *sleeve* is unpriced, and `withdrawal_capacity.py` scores the traded
#: universe only, so a symbol added here cannot quietly become a scorable sleeve. Their ratios were already written in
#: `cash_yield_gap.py`, which is the same duplication this file exists to end; that file now imports them from here.
CASH_FUNDS: dict[str, tuple[float, str, str]] = {
    "SGOV": (0.0009, "iShares", "0-3 month Treasuries; the cheapest bill leg with any history in this repository's sources"),
    "BIL": (0.0014, "SPDR", "1-3 month Treasuries; 5 bps dearer than SGOV for a duration the objective does not need"),
}

#: The seven legs `paper.py` has always quoted on every sealed entry, and whose ratios this file now posts.
FORMERLY_GUESSED = ("IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC")

#: The five ratios the repository has posted since before there were paper books. Sealed chains are priced with these.
POSTED_FIVE = ("SPY", "VOO", "VTI", "ITOT", "QQQ")

FEES = {symbol: ratio for symbol, (ratio, _, _) in RATIOS.items()}


def fee_for(symbol: str) -> float:
    """The ratio a fund charges, or the pessimistic guess for a fund this table does not price.

    Bill funds count: until round 99 `fee_for("SGOV")` returned the 0.35% guess for a fund that charges 0.09%, i.e. the table
    lied by 26 bps a year about the one instrument a cautious reader of this repository would actually buy.
    """

    entry = RATIOS.get(symbol) or CASH_FUNDS.get(symbol)
    return entry[0] if entry else GUESS


def priced(symbol: str) -> bool:
    """Whether this file prices the symbol at all. Traded legs and cash legs are both priced; only the traded legs are
    scoreable sleeves, which is what `sleeve_table.py` and `withdrawal_capacity.py` go on."""

    return symbol in RATIOS or symbol in CASH_FUNDS


def correction(symbol: str) -> float:
    """What the old flat guess got wrong for this leg, in annual ratio: positive means the guess overcharged the holding.

    Scale-parametric by design, so the sentence can be read at any size: multiply by capital for dollars a year.
    """

    return GUESS - fee_for(symbol)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.json:
        print(json.dumps({"retrieved": RETRIEVED, "guess": GUESS,
                          "fees": {s: RATIOS[s][0] for s in FEES},
                          "correction": {s: correction(s) for s in FORMERLY_GUESSED}}, indent=2))
        return 0

    print(f"# expense ratios, read {RETRIEVED} from each issuer's published figure\n")
    print(f"  {'fund':<6}{'ratio':>8}{'was charged':>13}{'error':>9}   issuer")
    for symbol, (ratio, issuer, _) in RATIOS.items():
        was = FEES.get(symbol, GUESS) if symbol not in FORMERLY_GUESSED else GUESS
        error = "" if symbol not in FORMERLY_GUESSED else f"{(GUESS - ratio) * 10000:+.0f} bps"
        print(f"  {symbol:<6}{ratio:>7.2%}{was:>13.2%}{error:>9}   {issuer}")
    harsher = [s for s in FORMERLY_GUESSED if correction(s) > 0]
    kinder = [s for s in FORMERLY_GUESSED if correction(s) < 0]
    print(f"\n  the flat {GUESS:.2%} guess overcharged {', '.join(harsher)} and undercharged {', '.join(kinder)}.")
    print(f"\n  cash legs, priced but never scored as sleeves: "
          + ", ".join(f"{t} {r:.2%}" for t, (r, _, _) in CASH_FUNDS.items())
          + f" — the guess would have mispriced them by {', '.join(f'{GUESS - r:+.2%}' for r in (fee_for('SGOV'), fee_for('BIL')))}")
    print("  Its own comment in `paper.py` claimed it was 'deliberately the pessimistic direction', which was true of four legs")
    print("  and false of three, and a comment that is mostly true about a cost is how a cost stops being watched.")
    print(f"\n  on $100,000: the guess over-billed {sum(max(0.0, correction(s)) for s in FORMERLY_GUESSED) * 100_000.0:,.0f} dollars")
    print(f"  and under-billed {sum(max(0.0, -correction(s)) for s in FORMERLY_GUESSED) * 100_000.0:,.0f} dollars a year, across")
    print(f"  those {len(FORMERLY_GUESSED)} legs held equally — and {max(FORMERLY_GUESSED, key=lambda s: abs(GUESS - fee_for(s)))}"
          f" alone is {abs(GUESS - fee_for(max(FORMERLY_GUESSED, key=lambda s: abs(GUESS - fee_for(s))))) * 10_000:.0f} bps of"
          " drift the archive never charged itself for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
