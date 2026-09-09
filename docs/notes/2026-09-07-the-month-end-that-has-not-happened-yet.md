# The month-end that has not happened yet

Round 87. Tools changed: [`rehearse_forward.py`](../../tools/rehearse_forward.py) (new),
[`paper.py`](../../tools/paper.py) (one clamp and one new violation). Tests added:
[`test_forward_rehearsal.py`](../../tests/test_forward_rehearsal.py), 12 of them.

## Why rehearse a date the calendar has not reached

Five books are anchored. Every one of them holds exactly one entry — the opening — and the first real seal is 2026-09-30, three
weeks away. That means the code path which will decide whether this whole programme ever produces evidence has never once been
run against a month-end that had not already been sealed into history: `tests/test_paper*.py` exercises the engine on the
archive, where a month-end is a fact, while the forward books need it to be a *procedure*. Round 84 made that worse rather
than better, by changing two conventions on the seal path (`_deposits_due` now accrues a transfer per calendar month,
`days_to_invest` records how long the oldest tranche waited) under the cover of unit tests that could call the helper but
never the command, because the sealed archive refuses to step at a date it does not contain.

So the month-end was manufactured. The rehearsal copies the corpus into a scratch directory, appends synthetic bars for dates
after the tail — and the bill-curve row that has to travel with them — then drives the same four commands a person will type
after month-end: `init`, `step`, `report`, `compare`. Four scenarios, 85 checks: a flat tape, a 12-point divergence, a missed
seal, and a 25% crash. Nothing in it writes to `data/`, and the tool now proves that by hashing the real files before and
after.

## Four things the rehearsal found, in the order it found them

**1. The engine cannot seal a date the bill curve does not cover.** The first run died with `ValueError: missing cash factor
for 2026-09-30`: `MarketData` requires a cash factor for every price date it holds, and appending prices without appending
cash produces a corpus that `fetch_market_data.py` could never emit, because it renames prices and cash in one atomic
operation precisely so a half-finished run cannot pair new prices with an old curve. That is correct behaviour, and it is now
the first line of the month-end runbook: **fetch before you seal.** The rehearsal appends a held-flat cash factor, which is
an assumption, and an harmless one to make, because a rehearsal scores a procedure and not a return.

**2. A plan that says it never borrows was allowed to borrow a cent.** On the divergence scenario — SPY +12%, QQQ −12%, the
5-point band breached, SPY sold and the proceeds redeployed — the sealed entry's own note read

```
deposit 500.00, bought 549.98, sold 49.98, borrow 0.00 at 5.91% on 0.01 borrowed
```

and its `violations` field was empty. One cent had been borrowed, at an annual rate, on a book whose sealed `plan` string says
in words *"do nothing: deposit, buy on arrival, never rebalance, never borrow."* The mechanism is rounding, not fraud: a buy
is sized from the target weight, cash is debited gross of the spread, and the arithmetic lands a fraction of a cent past the
cash that exists. The ledger's answer to that was to invent a loan and charge two tenths of a cent of interest on it, silently
contradicting a field in its own entry.

The fix trims the buy to the cash that is actually there — the dust stays in cash, where the plan says it is — but only when
**the plan's own weights sum to at most one**. That guard is deliberately structural rather than a list of model names: the
shelter ladder borrows on purpose and its weights exceed one, so it must keep the behaviour, and a future unlevered model
inherits the protection without anyone remembering to add it. If cash still ends negative after the clamp, the entry now
carries a violation saying so, at which point the ledger is complaining rather than concealing.

**3. The rehearsal destroyed something of mine, and a snapshot is the only reason it is recoverable.** The first version of
the harness bound `self.cash = paper.CASH_FILE` a few lines *before* repathing that module global, so it appended a synthetic
row to the live bill curve and only announced itself because finding 1 then refused to load the file. One row, removed by
hand, verified against an untouched snapshot copy: `data/current/cash_daily.csv` and
`data/snapshots/20260906T203953Z/cash_daily.csv` both hash `db41cf49ed50d520…`, and the manifest's row count is back to 8,458.
The guard now refuses to append to any path outside the scratch directory, and the tool hashes the real corpus before and
after and exits non-zero if either byte moved. It is worth naming the pattern, because this is the second time in four rounds:
`tools/paper.py` was unrecoverable in round 84 because it was untracked and uncopied; this file survived because the archive
happens to be snapshotted. **A thing survives an accident only if a copy of it exists somewhere, and the tooling tree is still
the one part of this repository where no copy does.**

**4. The cadence is what round 84 decided it was, confirmed through the command rather than the helper.** A seal on 2026-09-30
arrives with **no deposit**, because the anchor already funded September's money; the first transfer lands on 2026-10-30.
Skip a month and the next seal arrives with two transfers and a `days_to_invest` of 30 — the first time the ledger's own
idle-cash finding has had anything to find. On a flat tape, three months of deposits arriving produced **no sell at all** in
the banded book: round 84's phantom-drift defect is dead in integration, not just in the unit test that asserts the helper's
arithmetic.

## What the rehearsal says the first month will cost

On the flat scenario — every price unchanged, so nothing is earned and everything is charged — the live book's shape seals at
**$4,997.89 from a $5,000 opening, a fee line of $2.11**: 4.2 basis points in one month, about **0.50% a year** of pure
friction on a $5,000 account, most of it the 20 bp carried by the QQQ sleeve. That is the honest floor under any return the
forward books will ever report, and it is why `report` will say *underpowered* for two more entries: over a handful of months
the fee line, not the market, is the largest number on the page.

## Checks

**2150 passed, 239 subtests** (`/tmp/suite_r87.txt`), 87 standing rules. `journalctl.py verify` reports `chain intact`; all
five books still `intact` with one entry each; the rehearsal's own report says `all checks passed` and `the real corpus is
byte-identical to what it was before the rehearsal: yes`.

*Round 87. 87 standing rules. The seal path is no longer untested, the ledger can no longer borrow while denying it, and the
archive is byte-identical to the round it started — which is a sentence this repository is only allowed to write when a
snapshot exists to check it against.*
