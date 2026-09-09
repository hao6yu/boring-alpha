# A benchmark that could not compound

Measured 2026-09-07, round 82. Changed: [`paper.py`](../../tools/paper.py) (`recover_cash`, both chains),
[`test_paper_shadow.py`](../../tests/test_paper_shadow.py) (one assertion's sign, in the open). New:
[`power_horizon.py`](../../tools/power_horizon.py), [`test_power_horizon.py`](../../tests/test_power_horizon.py) (18),
[`test_paper_compounding.py`](../../tests/test_paper_compounding.py) (8).

I set out to answer a question the book poses about itself: its report says it needs 23 more monthly seals before a skill
claim, and the obvious reply is *then put more money in*. So the claim went down in the tool before the numbers were seen —
**the number of seals needed to detect the tilt's difference against plain VOO is invariant to account size while every cost
is proportional, and rises as flat per-order costs replace proportional ones.** The claim survived. It is not what the round
turned up first.

## The differential test found a defect in the sealed witness

To answer a question about the wait honestly, the study's benchmark had to be the journal's own. So the study grew a
simulator and the test file grew a comparison: same fund, same deposits, same month-ends, `simulate` against
`paper.shadow_step`, month by month. They agreed to a quarter. And both were wrong, because the copy had faithfully
reproduced the original's arithmetic:

```
fund:            100.0  ->  110.0  ->  121.0  ->  133.1      (+33% in three months)
witness:      $5,498.21 -> $5,998.06 -> $6,497.89            (= deposits, less fees)
```

Both chains recovered their cash line by taking the previous entry's `closing_value` and subtracting the holdings priced at
*today's* prices. Those are two different prices, and the difference between them — the month's mark-to-market — landed in the
cash line, where the month's orders then invested it or swept it. The interval therefore closed worth whatever had been
deposited into it, whatever the market did. A third of a rally, and the benchmark reported the deposit schedule.

The consequence is directional, not cosmetic. Under that arithmetic a witness in a rising market is a straight line, so every
strategy beats it; in a falling market the witness is still a straight line, so every strategy loses to it. **The P0
dominance rule — the one claim in this repository that must not rest on the graded party's arithmetic — was about to be
computed against a benchmark that cannot move.** Nothing had been decided yet, because the first seal is due at the next
month-end; the defect was found before it could be sealed into a chain, not after.

The fix is one function, [`recover_cash`](../../tools/paper.py), which prices the prior holdings at the quotes *that entry
sealed* (`Entry.quotes`), used by both `shadow_step` and `command_step` so the two chains cannot grow two versions of a
subtle rule again. Cash is a state variable in the study's simulator for the same reason.

## The test that was pinning the defect

One assertion broke, and it deserves naming rather than deletion. `test_a_strategy_that_only_trades_loses_to_one_that_does_not`
asserted the trading book sat *behind* the witness, and its own docstring allowed the exception: *"unless it was paid to trade
by the market."* The sign it checked had been guaranteed by a structural defect, not by markets — after the fix the same four
archive months have the vol-target book **ahead** by $24.92. The test is now
`test_the_witness_never_pays_more_than_the_book_it_judges`: it asserts the half that cannot legitimately reverse (the witness
pays strictly fewer costs than the book it judges) and leaves the direction of the gap to a property test that asks whether
the ledger moves when prices do. A sign assertion on a market outcome will eventually be satisfied by a bug.

What the new file tests instead: a rising path leaves the witness strictly ahead of its deposits, a falling one strictly
behind; a flat market still computes the number the old code computed (the repair changes a mark, not a convention); the
witness's *units* never fall in a rising market, which is the tell-tale of the old arithmetic selling the gain back; the
sealed balance matches dollar-cost averaging worked out longhand to within half a percent; and the two chains demonstrably
share the one implementation.

## The study, once its accounts could earn

Withdrawn result first: the study's first run said the tilt never beats plain VOO — every cell reported *"the measured
difference does not favour the book."* That was the defect talking, in both accounts at once, and it is withdrawn here rather
than quietly rerun. With cash carried properly, over every month VOO has existed:

| | paid in | closed at | |
|---|---|---|---|
| plain VOO, the witness | $2,020,000 | $7,888,445 | — |
| **tilt, 50/50 SPY/QQQ, rebalanced monthly** | **$2,020,000** | **$9,841,466** | **+$1,953,020** |
| QQQ alone | $2,020,000 | $12,316,793 | +$4,428,348 |
| SPY alone | $2,020,000 | $7,794,662 | −$93,783 |

**Re-run 2026-09-08 (round 96), and it is now a command.** `power_horizon.py` prints these four bars itself, and the reprint on a
re-fetched corpus reads VOO $7,853,675, SPY $7,760,092, tilt $9,778,202, QQQ $12,216,556 — every row 0.4–0.8% below the figures
above, in the same direction for all four, which is what revised closes look like and not what a changed fee looks like (paid in is
identical at $2,020,000, and the month count is still 193). The finding is untouched: the free version of the bet is ahead of the
rebalanced tilt by $2,438,354, where this table said $2,475,327. What did change is that the table can no longer rot quietly —
`tests/test_power_horizon.py` pins each row to within 1.5% of the numbers above and tells the reader to amend this note when a row
moves more than that. A headline with no command under it decays; this one now has a command and a tolerance.

Two things inside that table. SPY finishing $93,783 behind VOO is the 6.45 bp fee difference compounding over sixteen years —
an internal check that the simulator charges fees rather than mentioning them. And QQQ alone beats the rebalanced tilt by
$2.5M: rebalancing a divergent pair to a fixed weight **sells the winner every month**, and the archive's backtests charge
nothing for it, because a constant weight vector has no turnover to price (round 74's warning that trading less is not costing
less, arriving on the other side). This does not overturn round 78 — that measured withdrawal capacity from a lump sum under a
failure budget, a different question — but it says the *monthly-rebalanced* tilt is the construction this book runs, and it is
worth less than holding the growth sleeve it keeps selling.

## The claim, scored

| window | costs proportional | $4.95 a ticket | $9.95 a ticket |
|---|---|---|---|
| every month VOO has existed (192) | **224 seals at every size from $5,000 to $250,000** | 235 vs 224 | 248 vs 225 |
| last five years (60) | **595 seals at every size** | 873 vs 599 | **1,451 vs 603** |

The unrounded wait differs across account sizes by 0.000000000% when costs are proportional — confirmed, in both windows.
**Capital buys dollars, not knowledge**: everything the account pays is a proportion, so the gap and its noise scale together
and the two-sigma test is scale-free. Break proportionality with a $9.95 ticket and the invariance breaks *against the small
account* — 1,451 seals at $5,000 against 603 at $250,000, because eleven years of two tickets a month is a fifth of a $500
deposit. The lever is the broker's ticket charge, not the deposit: a model fact is not on the table, a broker fact is.

And the honest reading of the magnitudes: 224 seals is eighteen years of month-ends, and on the last five years the wait is
fifty. The live book's report asks for 23 more entries; that is an observation-count rule in
[`journal.py`](../../src/boring_alpha/journal.py) (`min_entries`, `min_paid_in`), not a variance calculation, and this study's
arithmetic says a *significant* difference is not what a $5,000 book with $500 arriving monthly is equipped to produce.
[`book_power.py`](../../tools/book_power.py) reached the same place by an independent route — block bootstrap, month-60
resolution of 5.7%/yr against an edge worth 0.49%/yr — and its own words stand: **the skill line will stay underpowered at any
deposit size**, and the ledger's answerable claim is the episode one. Two tools, two constructions, one conclusion; note the
phrase collision, since `book_power.py`'s heading "because it does not compound" describes the *claim* the ledger makes, and
today the phrase was also literally true of its arithmetic.

## What I got wrong, and what remains open

I read the `Quote` field as `price` (it is `close`); I hand-wrote two probes that mis-divided dollars by units, which is the
same failure the tests exist to prevent; one patch silently failed to apply because of an em-dash in the target text, and I
nearly concluded the fix had done nothing until I grepped for the line I had asked for; two tests asserted premises I had not
computed (a round trip that buys high and ends low *loses*, and a two-fund book pays *two* tickets, not one); and
`horizon()` reported "no dispersion" ahead of checking the sign, so a series with no difference at all reported a horizon of
one seal. Fixed, in that order.

Open: the study assumes monthly i.i.d. increments at the study layer (the bootstrap handles clustering elsewhere); commissions
are flat per ticket with no volume tier or per-share component; the archive is month-end, so the study cannot see intra-month
rebalancing, which is exactly where the tilt's QQQ selling happens; `accuracy_bar.py`'s skill surface and BA-003 remain
unevaluated; and the fixed cost of *knowing* is still unpriced — the answer the objective wants may have to come from the
episode ledger rather than from a return comparison.

## Checks

18 tests in [`test_power_horizon.py`](../../tests/test_power_horizon.py) and 8 in
[`test_paper_compounding.py`](../../tests/test_paper_compounding.py); the sealed witness and the study agree month for month
to under a quarter; all six paper suites green; suite **2077 passed** (was 2051); `journalctl.py verify` reports the chain
intact, and the four books' anchor and witness cash are unchanged — the fix touches arithmetic at the *next* seal, and no book
has a second entry yet.
