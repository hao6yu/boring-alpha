# Two books, one quote

Measured 2026-09-07, round 70. Live artifact changed: [`paper.py`](../../tools/paper.py) (`--book`, `compare`). Tests:
10 new in [`test_paper_books.py`](../../tests/test_paper_books.py).

Round 69 superseded the paper book's last non-shelter chain, which left the repository in a position it should not be in:
exactly one plan in this archive has measured positive against a buy-and-hold comparator on a *return* basis — a constant
1.25× SPY book, +1.63%/yr over the full record, with a −59.7% drawdown in 2007-09 (rounds 29 to 32) — and it now had no
forward record of any kind. Meanwhile the one construction the last fifteen rounds converged on is running forward. A
book that tracks only what its author currently believes is measuring its beliefs, not the market, so the book gained a
name and the levered plan got its chain back.

## What running two books means concretely

```
  book       model      entries        asof      value  fees paid    witness       gap  chain
  ------------------------------------------------------------------------------------------
  (root)     shelter          1  2026-09-04   5,000.00       0.00   5,000.00     +0.00  intact
  constant   constant         1  2026-09-04   5,000.00       0.00   5,000.00     +0.00  intact
```

A named book lives in `data/paper/books/<name>/`, with its own ledger, its own shadow witness and its own anchor config.
Opening cash, monthly deposit, spread and borrow rate are *shared by construction* — the same numbers for every book —
because the point of two books is that they are comparable as accounts, and that only holds if the only differences
between them are the model and the sleeve it trades. `compare` prints one row per book against its own sealed witness.

Rehearsed on archive data rather than awaited, at a session where the two models genuinely disagree (May 2025: the trend
rule was sheltered, a levered book does not care):

| book | holdings | value | fees paid | witness | gap |
|---|---|---:|---:|---:|---:|
| shelter | IEF, 100%, unlevered | 5,496.74 | 3.26 | 5,497.92 | −1.18 |
| constant | SPY, 125%, financed | 5,493.53 | **6.47** | 5,497.92 | **−4.39** |

Two things in that rehearsal are worth keeping in view when the real chains accumulate. The levered book paid **twice**
the costs of the sheltered one — expense on 125% of fund value, plus interest on the loan — and it finished four dollars further behind doing
nothing on the same $5,500 of committed cash. That is rounds 29 and 30's finding (the financing term worth more than
half the trade's benefit) showing up in a single month's fee line, and it is exactly what the forward record exists to
observe rather than infer. And the *witness* column is identical for both books, because identical deposits against
identical quotes must produce an identical doing-nothing account: that is now an asserted invariant rather than an
assumption, and if the two ever differ the books are not comparable and the table is decoration.

## Isolation, and the two things I got wrong while writing it

`--book` takes a name matched against `^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$` and refuses anything else, so a book name cannot
walk out of `data/paper/` — `../outside`, `a/b`, a leading `.` or `-`, and a 40-character name all raise. A step on one
book leaves the other's sealed chain **byte-identical**, which is asserted by comparing the file bytes before and after
rather than by trusting the path plumbing. A tampered anchor makes `compare` print `BROKEN` for that book: the command
that exists to summarise health may not skip the patient.

Second, `command_report` rebuilt its comparator from literals — `Comparator("100% SPY", {"SPY": 1.0}, EXPENSE_RATIO)` —
while `command_step` had long read it from the anchor config, on the file's own stated policy that a benchmark may not be
editable at a call site. The report path now reads the same config. One rule, one source.

Third, a test I wrote with the wrong premise, kept here because the schema is not obvious: I asserted that a 1.25× book
must show `invested > opening + deposit`. It does not — `invested` is capped at the account's own cash *deliberately*, so
leverage is recorded as gross exposure exceeding net value plus a borrow charge in the sealed note. The correct assertion
reads the entry's own quotes and note; the field that looks like it is measuring leverage is measuring something else, and
this file has now been told the difference in both directions.

## What this settles, and what it still cannot

The `constant` chain is the one that can falsify the only positive-measuring claim in the archive, on the axis it was
made on. The `shelter` chain tests whether the trend rule's switches cost what this book charges, whether the sealed book
keeps agreeing with the research rule as data arrives, and whether the plan tracks its witness within costs. Neither
chain can settle a 5% failure budget — that is a distribution over 169 windows and one forward path draws once. And the
`constant` book should be read as what round 32 called it: a loan, not a signal. It is running forward because it is the
one claim the archive could not close, not because anyone recommends 125% of a portfolio in a taxable account.

## Checks

10 tests plus 6 subtests, 2.9 s, offline; whole suite **1878 passed** (collected first: 1868 + 10). Both books verify
(`journalctl verify` for the research ledger, each book's own two chains intact), and the anchor configs record the model,
the sleeves, the fees and the trend reading each book is being measured on.
