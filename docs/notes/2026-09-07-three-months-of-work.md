# The hedge is perfect, and on this record it has three months of work to do

Measured 2026-09-07, round 67. Tool: [`shelter_long_record.py`](../../tools/shelter_long_record.py) (`--grid`). Tests:
9 in [`test_insurance_grid.py`](../../tests/test_insurance_grid.py).

Round 62's central claim is that the trend rule is not an alpha and should not be scored as one: it is sequence
insurance, and the proof was a 2×2 — of the entries where a plain index payout plan breaks, the rule fails at **none** of
them, and it pays for itself in vain at none either: **56 insurance / 0 redundant / 0 cost**, over 283 starts from 1993.
Round 66 established that the record this claim rests on should be the one the *question* allows, not the one a
ten-sleeve panel happens to leave. So the 2×2 was re-scored on the 2002-on record with the surviving shelters.

## First, the frame has to be the one where anything fails

Scored in round 62's own frame — $1,000 a month **in**, the promise that the account ends whole — the index plan fails in
**0 of 169** starts. Nothing anywhere fails, so the table is empty and the claim cannot be tested. Round 62's 56
failures came from a record that starts in 1993 and runs a contributing plan into the lost decade. On post-2002 data,
insurance can only be discussed in the withdrawal frame.

## At the published payout: perfect, and tiny

| leg | starts | insurance | redundant | cost | fine | own P(fail) | concordance | entries covered |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| index | 169 | — | — | — | — | 4.1% | — | (7 failures) |
| cash | 169 | **7** | **0** | **0** | 162 | 0.0% | 0% | 2003-04-04 → 2003-04-23 |
| **IEF** | 169 | **7** | **0** | **0** | 162 | 0.0% | 0% | 2003-04-04 → 2003-04-23 |
| TLT | 169 | 7 | 0 | 0 | 162 | 0.0% | 0% | 2003-04-04 → 2003-04-23 |
| GLD | 142 | — | — | — | — | — | — | dropped: shorter record |

The claim survives intact — every index failure covered, none missed, none paid for in vain — and shrinks to what this
record actually contains: **three adjacent entry months in April 2003**, the start of the one decade in which the index
plan fails at $435.47. Round 62's 56 entries were spread across 1998-02 to 2007-07 because its record reaches back into
the dot-com bust; on a record starting 2002-08 there is one episode, and the hedge covers it. That is not a refutation.
It is the honest size of the thing: a plan at the published payout is protected against one three-month window in twenty-four years, and pays nothing for that protection in the other 162 starts.

## Where the shelter earns its keep is the risk frame, not the income frame

Raise the withdrawal to **$700/mo**, past where the bill-sheltered plan's capacity stops:

| leg at $700/mo | insurance | redundant | cost | own P(fail) | concordance |
|---|---:|---:|---:|---:|---:|
| cash | 11 | 61 | 23 | 49.7% | 85% |
| **IEF** | **42** | **30** | **12** | **24.9%** | 42% |
| TLT | 21 | 51 | 26 | 45.6% | 71% |

The shelter converts 50 of the index's failures into covered entries and cuts the entries where the hedge was a pure
debt by half. This is the same IEF that was worth +$73.12/mo of income in round 66, doing something else with the same
money — and it is worth more for it: the index fails in 42.6% of starts at this withdrawal, and the sheltered plan in
24.9% of them.

## And above the ceiling the hedge has nothing left to sell

At **$900/mo**, every leg's insurance cell is **empty** and each fails in more than four starts out of five: 0
insurance / 76 redundant / 60-71 cost. Rounds 63 and 65 said the trend leg is the risk-buyer's choice below its capacity
and the thing that breaks above it; this is that sentence in round 62's table.

One shape worth keeping, because the first draft of this note got it backwards: **the insurance cell is a hump in the
withdrawal, not a slope.** At $435 the index fails 7 times, so a hedge can cover at most 7. At $700 the index fails 72
times and the hedge covers 42 of them. At $900 the plan is failing everywhere and the hedge covers nothing. A claim of
insurance has a payout band, and the published plan sits at the bottom edge of it.

## Checks

9 tests, 8.4 s, offline. The contribution frame is pinned at zero failures so nobody re-discusses insurance in a frame
that cannot show any; the 7/0/0 cells and the *span* of covered entries (April 2003, spread under 40 days) are pinned;
so is the hump `[7, 42, 0]`, with the assertion written after the measurement rather than before it — the two first
drafts of these tests asserted a monotone narrowing and a cost-majority at $900, and both were wrong. GLD is dropped for
length rather than paired by row number against a longer index record. The benchmark row is verified to be the index held
with no shelter at all, to 12 places, so the 2×2 cannot be scoring the hedge against itself. Full suite **1840 passed**
(collected first: 1831 + 9). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
