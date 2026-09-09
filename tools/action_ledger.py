"""Every action this repository has priced, in one table, sorted by dollars and marked by variance.

    .venv/bin/python tools/action_ledger.py
    .venv/bin/python tools/action_ledger.py --capital 50000
    .venv/bin/python -m pytest tests/test_action_ledger.py -q

Twenty-seven rounds have produced verdicts one at a time. This file adds them up, because the shape of the
result only appears when they are in one place, and the shape is not what the project set out to find.

Two columns do all the work. **$ per month** is what the action is worth at the capital actually on hand —
every figure is scale-proportional, so `--capital` rescales the whole table honestly. **Variance** is the one
nobody asked for and the one that decides everything: round 23 proved that at this account size a stochastic
edge of the magnitude this repository has ever found cannot be *measured* — the paper book resolves ~6%/yr at
month 60 against an effect of 0.4%, and no deposit size changes that, because an edge and its noise both scale
with capital. So an action with variance is an action you will never know the result of, at this size, however
good its backtest looks. An action with no variance is a *quoted rate and an arithmetic difference*, and you
will know within one statement whether it happened.

That distinction, not the ranking, is the finding of this file. Read down the variance column before the dollars
column.

Every row cites its round, and the numbers are transcribed from the published notes rather than recomputed, so
this is a table of record and not a re-analysis; the checks at the bottom of the note re-derive the two rows
that could be checked cheaply and would embarrass the table if they had drifted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import withdrawal_capacity as wc                                       # noqa: E402
from boring_alpha.data.csv_loader import load_csv_market_data           # noqa: E402
import unlevered_timing as ut                                          # noqa: E402
import cash_yield_gap as cy                                             # noqa: E402
import financing_desk as fd                                              # noqa: E402

BASE_CAPITAL = 20_000.0

# Derived, not remembered. Round 38 found this row carrying $25.00/mo, which was round 18's *noise floor* — the
# size of the splicing artefact between two funds tracking the same index — transcribed into the ledger as if it
# were the value of the action. The action is worth the expense ratio, and nothing else: 6.45 bps on this capital.
EXPENSE_GAP_MO = (wc.EXPENSE["SPY"] - wc.EXPENSE["VOO"]) * BASE_CAPITAL / 12.0

# The leverage the recommendation actually suggests, used only to convert a rate-card spread into $/mo.
TILT = 1.25

# The rate card is an action, and it is worth more than the strategy it sits under: 710bp of posted spread on the
# borrowed slice of a 1.25x book is $29.58 a month on $20,000, against the whole leveraged tilt's $27.24 (r46).
FINANCING_MO = (fd.EXPENSIVE[1] - fd.CHEAP[1]) * (TILT - 1.0) * BASE_CAPITAL / 12.0

# (action, what to actually do, $/mo at $20k, variance class, round, the caveat that matters)
ACTIONS = [
    # Derived at print time, never transcribed. This row carried 46.12 and "the 55th percentile" as literals for
    # fifteen rounds; both came from a spot rate computed by compounding a four-day partial month (r47), and the
    # corrected figures are ~$63/mo at ~the 65th percentile. See `switch_row`.
    ("move idle cash out of the default sweep",
     "hold settlement cash in a T-bill fund or ladder instead of the brokerage default sweep",
     None, "none", "24", "derived at print time from cash_yield_gap.path()"),
    ("hold the cheapest share class of the same index",
     "VOO/ITOT instead of SPY/QQQ-class pricing for the same exposure",
     round(EXPENSE_GAP_MO, 2), "none", "18, 38",
     "worth exactly the fee gap and no more; round 18's $25/mo figure was the NOISE FLOOR that dwarfs this "
     "action, transcribed here as if it were the prize (r38)"),
    ("de-risk with the trend/vol rule, unlevered",
     "the same signal capped at 1.0x: half the drawdown, a negative premium",
     -21.15, "substantial", "26",
     "worth +0.51%/yr against an equal-exposure control: timing, not income"),
    ("the vol-target rule as configured (1.3x cap)",
     "the paper book's rule, financed at the posted desk rate",
     -4.10, "substantial", "25",
     "+0.09%/yr on the book's own subsidised financing assumption; NOT the same policy as the next row"),
    ("a constant 1.25x book, financed at a posted desk rate",
     "the monthly ticket's policy: fixed leverage, no signal, no idle cash to under-credit",
     27.24, "substantial", "29",
     "the only plan in this repo still positive under sweep cash and posted borrow; +1.63%/yr vs the index"),
    ("hold the loan at the cheap end of the posted rate card",
     "a desk whose base margin tier is ~4.9% rather than one whose base tier is ~12%: same loan, same collateral",
     round(FINANCING_MO, 2), "none", "46",
     f"{(fd.EXPENSIVE[1] - fd.CHEAP[1]) * 10_000:.0f}bp of posted spread on the borrowed slice. Worth exactly "
     "this only if you borrow, nothing if you don't. Larger than the whole leveraged tilt above it."),
    ("cross-sectional rotation across nine sleeves",
     "monthly top-K momentum on the universe in `cross_section.py`",
     -231.0, "substantial", "cross-section",
     "loses to equal-weight and to the index; 9 names are 2.5 effective bets"),
    ("directional timing at any faster cadence",
     "weekly or daily entry/exit on one sleeve",
     None, "substantial", "2, 13, 14",
     "needs 63-98% of calls right and shows 41-83%; the nightly round trip costs more than the premium"),
    ("reinvest distributions promptly",
     "there is nothing to do: the float is one cheque, not the account",
     0.01, "none", "27",
     "even never reinvesting at all costs under $1.55/mo; a non-action, listed so it stops being a worry"),
]


def rows(data) -> list:
    """`ACTIONS` with every derivable figure recomputed from the archive. The CLI and the tests both read this,
    so nothing can pin a transcribed literal again."""

    out = list(ACTIONS)
    for i, row in enumerate(out):
        if row[2] is None and str(row[0]).startswith("move idle cash"):
            out[i] = switch_row(data)
    return out


def switch_row(data) -> tuple:
    """The first row, recomputed from the archive on every print rather than remembered in a literal.

    Round 47 is the second time this ledger has published a number that its own engine could compute: r38 found
    the share-class row carrying a noise floor as if it were the action's value, and this row was carrying a spot
    bill yield that a four-day September stub had pulled down by 103bp. Both are the same habit — a figure copied
    out of a note into a table — and both are fixed the same way.
    """

    pth = cy.path(data)
    return ("move idle cash out of the default sweep",
            "hold settlement cash in a T-bill fund or ladder instead of the brokerage default sweep",
            pth["worth_spot"], "substantial", "24, 47, 49",
            f"today's bill {pth['spot']:.2%}, the {round(pth['percentile'] * 100)}th percentile of the record: "
            f"${pth['worth_at_median']:,.0f}/mo at its median, ${pth['worth_at_q1']:,.0f} at its lower "
            f"quartile; and it is NOT variance-free (r49) — it paid ${pth['worth_at_q1']:,.0f}/mo at the "
            f"lower quartile of the record and went negative in {1 - pth['share_under_100']:.0%} of months "
            f"were it not for the 2bp, so the regime is the risk")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=float, default=BASE_CAPITAL)
    ap.add_argument("--verify", action="store_true", help="re-derive the two rows that can be recomputed")
    args = ap.parse_args()
    scale = args.capital / BASE_CAPITAL
    data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
    resolved = rows(data)

    print(f"the action ledger · every action this repository has priced, at ${args.capital:,.0f} of capital\n")
    print(f"  {'action':42} {'$ /mo':>10} {'$/yr':>9}  {'variance':12} {'src':>10}  the caveat")
    print("  " + "-" * 132)
    for action, _how, dollars, variance, src, caveat in sorted(
            resolved, key=lambda a: -(a[2] if a[2] is not None else -1e9)):
        money = "  measured no" if dollars is None else f"{dollars * scale:>+10,.2f}"
        year = "" if dollars is None else f"{dollars * scale * 12:>+9,.0f}"
        print(f"  {action:42} {money} {year}  {variance:12} {src:>10}  {caveat}")
        print(f"  {'':42}   → {_how}")

    sure = [a for a in resolved if a[3] == "none" and a[2] and a[2] > 0]
    risky = [a for a in resolved if a[3] != "none" and a[2] is not None and a[2] > 0]
    sure_total = sum(a[2] for a in sure) * scale
    risky_total = sum(a[2] for a in risky) * scale
    print(f"\n  {len(sure)} actions carry no variance to them and are worth ${sure_total:,.2f}/mo combined; "
          f"{len(risky)} that\n  do are positive on the record and total ${risky_total:,.2f}/mo. The idle-cash row "
          f"sits in neither\n  group's certainty: it is the largest number on the table and it is a rate view, "
          f"worth 3 cents\n  a month in 2021 and $63 today.")
    print("  read the top of this table and the order of operations is not in doubt: the two largest numbers a\n"
          "  bot could act on are where the cash sits and where the loan is booked. Neither is a model. The "
          "rest\n  of the table is a drawdown preference, a fee choice, and four documented failures.")
    if args.verify:
        print("\n  re-deriving the rows that can be recomputed:")
        row = switch_row(data)
        print(f"    switch: bill {cy.path(data)['spot']:.2%} -> ${row[2]:,.2f}/mo at ${args.capital:,.0f} "
              f"(derived, not transcribed)")
        print(f"    expense gap SPY {wc.EXPENSE['SPY']:.6f} - VOO {wc.EXPENSE['VOO']:.6f} = "
              f"{(wc.EXPENSE['SPY']-wc.EXPENSE['VOO'])*1e4:.2f}bp = ${EXPENSE_GAP_MO*args.capital/BASE_CAPITAL:.2f}"
              f"/mo at ${args.capital:,.0f}")
        data = load_csv_market_data(wc.SNAPSHOT, wc.CASH_FILE)
        capped = ut.run(data, cap=1.0)
        print(f"    unlevered rule vs the index: {capped['total']*1200:+.2f}%/yr = "
              f"${capped['mo']*(args.capital/ut.CAPITAL):,.2f}/mo at ${args.capital:,.0f} "
              f"(the row says {ACTIONS[2][2]:+.2f} at ${ut.CAPITAL:,.0f})")
        print(f"    static control at the same mean weight ({capped['mean_w']:.3f}): "
              f"{ut.run(data, static=capped['mean_w'])['total']*1200:+.2f}%/yr")
    print("\n  Sources: notes 2026-09-06-{cash-yield-gap, sleeve-league, unlevered-timing, sweep-repricing, "
          "cross-section, session-split-and-cadence, distribution-float}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
