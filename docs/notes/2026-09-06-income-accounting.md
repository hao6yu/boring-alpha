# The same stance priced twice: +$136 a month on average, and $43 a month *less* than what not borrowing guarantees

Measured 2026-09-06, round 41. Tool: [`income_accounting.py`](../../tools/income_accounting.py); tests
[`test_income_accounting.py`](../../tests/test_income_accounting.py) (10).

## Two files have been answering the goal's sentence with opposite signs

The goal is phrased in monthly dollars, and this repository has answered that phrasing twice, in two places, and
nobody had put the answers in one table:

- **`leverage_sizing.py`** (round 3, full record, DCA account): 1.25× is worth **+$143/mo**.
- **`withdrawal_capacity.py`** (round 4, 20-year windows, worst start): the largest withdrawal surviving **every**
  start falls from **$379/mo at 1.0× to $335/mo at 1.25×**.

Both are correct and they are not the same quantity. The first is `funded_frame.per_month_equivalent` of a **terminal**
gap — a balance at the end of 33 years restated as the annuity it would have supported, discounted at the
comparator's own rate. The second is the **minimum** over 55 start dates of a cheque that never triggered a forced
sale. One is a mid-table statistic, the other is a lower bound, and a stance can raise the first while lowering the
second. This one does.

## The reconciliation, at one capital ($100,000, 20-year plans, every start date)

| sleeve | lev | mean $/mo | guarantee | vs 1.0× | binding start |
|---|---:|---:|---:|---:|---|
| SPY | 1.00 | +0.00 | **378.52** | +0.00 | 2000-05 |
| SPY | 1.25 | +136.18 | 335.16 | **−43.36** | 2000-05 |
| SPY | 1.50 | +272.36 | 300.00 | −78.52 | 2000-05 |
| SPY | 1.75 | +408.54 | 266.02 | −112.50 | 2000-05 |
| SPY | 2.00 | **+544.71** | **233.20** | −145.31 | 2000-05 |
| QQQ | 1.00 | +0.00 | 171.09 | +0.00 | 2000-04 |
| QQQ | 1.25–2.00 | +165 → +661 | **0.00** | −171.09 | none |
| VTI | 1.00 → 2.00 | +0.00 → +472.72 | 508.59 → 424.22 | −84.37 | 2001-07 |
| ITOT | 1.00 → 2.00 | +0.00 → +545.93 | 607.03 → 574.22 | −32.81 | 2006-05 |

**On SPY the mean is maximised at 2.0× and the guarantee at 1.0×.** Every step up the grid moves money *out of* the
guarantee column and *into* the mean column: at 1.25× you buy $136 of average month for $43 of guaranteed month, and
at 2.0× you buy $545 for $145.

> **Amended in round 42: every guarantee above is sampled on `withdrawal_capacity.py`'s default stride of 3, which
> this project already knows flatters the loan.** `income_frontier.py` has a test named
> `test_the_start_grid_is_part_of_the_claim_because_it_changes_the_verdict`, whose docstring records that the coarse
> grid lets the levered promise through. Re-measured on every grid from 1 to 12, the guarantee at 1.0× runs
> **$364.45 (165 starts) → $378.52 (55) → $390.23 (14)** — a level that moves **$25.78/mo** on a cosmetic input —
> because the start date that ends the promise is **April 2000** and a stride of 3 steps from January lands on
> **May**. The honest figures are therefore **$364.45 at 1.0×, $317.58 at 1.25×, a delta of −$46.88** (not
> −$43.36), and the correction moves *against* the loan, which is the direction the coarse grid was biased in.
> What does not move is the finding: the delta is negative at **every** grid from stride 1 to 12, in a band of
> **−$41 to −$47**, and the guarantee is maximised at 1.0× on all of them. The tool now defaults to stride 1 and
> prints the whole band, because a statistic whose value depends on an input nobody was asked to choose should be
> reported with that dependence attached rather than as one number.

QQQ is the sharpest sleeve, and its guarantee declines rather than vanishing: **$171.25 at 1.0×, $113.75 at 1.25×,
$68.75, $40.00, $20.00 at 2.0×**, against a mean column reading +$165 to +$661/mo.

> **Corrected in round 43: this note originally said QQQ's guarantee was "exactly $0.00 — not small, zero". It is
> not, and the reason it looked that way is the more important finding.** `withdrawal_capacity.capacity` probes 40
> points up to a 6%/yr ceiling, so its smallest rung is **$150/mo** on a $100k lump, and `if not passing: return
> 0.0, 0, "none"` reports anything below that first rung as **zero**. QQQ's true frontier at 1.25× is **$113.75** —
> below the rung, so the tool printed $0.00, and the binding start printed `none`, which I read as "nothing
> survives at any size" when it means "the grid found no failure because it never probed that low". Probed at a
> $5/mo rung the answer is graded and monotone, and the delta against 1.0× is **−$57.34**, larger than the −$43.36
> originally reported. The finding stood; the drama did not. `income_accounting.py` now re-probes at a $0.2%/yr
> ceiling whenever a frontier comes back zero, reports a frontier sitting on the ceiling as truncated rather than as
> a number, and prints the refinement in the row so the provenance travels with the figure.

The one exception in the table is ITOT, where 1.25× guarantees **$9.38 more** than 1.0×. It is not a counterexample
so much as a measurement-resolution statement: ITOT has **11 start dates**, and at 1.5× the same sleeve already
reports binding start `none`. The guarantee is a minimum over a small set, so a minimum over 11 draws can move
either way; the trend from 1.25× onward is still down.

## The mechanism, and why it is sequence rather than cost

Financing here is the archive's own cash index plus 150bp, and round 40 already established the loan's incremental
month is negative **39.1%** of the time with a nine-year hole in its excess. Leverage does not merely lower the
average — it multiplies the *path*, and a 20-year plan's survivability is decided by where its worst 240 months sit
relative to its withdrawal schedule, not by what the whole record averaged. That is why every binding start in the
table is **2000-04 / 2000-05 / 2001-07**: the same dot-com window r39 identified as the reason the era moves the edge
by half its size, and r30 found binding on the drawdown side. Three engines, never shared a line of code, all
landing on the same window.

## What this settles about the goal

Round 40 concluded from the shape that the plan is not a paycheck. This round prices the same conclusion in the goal's
own unit and finds the sign is not merely weak but **reversed**: the action that beats the index on average
**guarantees a smaller monthly amount than the action that does not beat it**, at every leverage above 1.0× on three
of four sleeves, and on the fourth the guarantee is zero.

So the answer to *"can a bot earn me extra each month and beat VOO/QQQ"* now has all three parts measured, not
argued:

1. **Beating the index requires exposure** (r38: every cash-holding stance loses, monotonically).
2. **Exposure makes the guaranteed monthly amount smaller, not larger** (this round, dense grid: −$46.88/mo at
   1.25× on SPY, −$151 at 2.0×; on QQQ −$57.34 falling to −$151 as the guarantee walks 171 → 114 → 69 → 40 → 20).
3. **The only bounded monthly amount in the repository is the deposit spread** — $39.85/mo averaged across the
   archive, positive in 80.9% of months, never worse than −$1.65 — and it costs the index to hold.

Parts 1 and 2 together are the finding of the whole exercise: **there is no leverage level at which this account both
beats the index and increases the money it can promise every month.** The trade is real and it is available, and it
is a bet, and the honest price of it is −$43/mo of guarantee for +$136/mo of expectation. Anyone who wants that bet
should take it knowingly; anyone who wants a monthly number should stop looking for one in the market.

## Checks

12 tests, 1.8 s, offline: the two columns must **rank the grid differently** (mean maximised at 2.0×, guarantee at
1.0× — asserted as an ordering, so it cannot be satisfied by two constants that happen to differ); the guarantee must
fall monotonically on SPY while the mean rises monotonically; the 1.0× mean cell must be **exactly** zero to nine
decimal places, or the two columns are not sharing a comparator and the comparison is void; SPY's 1.0×
guarantee must reproduce the $378.52 published by `withdrawal_capacity.py` to 5 cents **when run on that file's own
stride** (the cross-artifact pin moved to the other file's grid deliberately, so this file's default change could
not silently break it), while the dense grid must land on $364.45, find binding start 2000-04, and prove the coarse
grid finds 2000-05 instead; **VOO must refuse** rather than price a
16-year window as if it were a 20-year plan (while a 12-year plan must produce a number, proving the refusal is about
window length); QQQ's guarantee must be *exactly* 0.00 above 1.0× while its mean exceeds $100; and an unknown sleeve
must raise rather than return zero, because zero is a result in this file and an absent sleeve may not wear one. Two
bugs caught before green: a dict membership test written against the wrong level of the archive structure, and
`isoformat()` called on a binding start that was already a string. Round 42 re-measured this note's guarantees on five start grids and amended them in place; see the blockquote above
the QQQ paragraph. Full suite at that point: **1554 passed, 233 subtests**.
`journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
