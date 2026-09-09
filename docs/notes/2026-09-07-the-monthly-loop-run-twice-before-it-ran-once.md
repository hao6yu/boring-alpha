# The monthly loop, run twice before it has ever run once

Round 88. Tests added: [`test_forward_pipeline.py`](../../tests/test_forward_pipeline.py), 10 of them. Tool changed and then
put back: [`fetch_market_data.py`](../../tools/fetch_market_data.py) — the only difference from its committed form is a
comment, which is the point of the note.

## What was still untested after round 87

Round 87 rehearsed the *seal* against manufactured bars, and the rehearsal's first lesson was that the engine refuses a date
the bill curve does not cover — so the fetch is the step that must succeed first, on 2026-09-30, before any book can move. The
fetcher had 26 honest tests, all of them on pure functions: adjustment, the incomplete-session rule, dividend alignment, the
cash-rate lag. None of them had ever run `main()`. So the corpus had never been written by the fetcher and read back by the
engine, and the claim *"fetch, then seal"* — which is what the operator will type every month from now on — had never been
executed start to finish.

The new file stubs the fetcher's one transport seam (`_get`, one function, so the stub cannot drift from the real path),
hand-builds Yahoo chart payloads and a FRED CSV, stands the clock forward where the exchange calendar requires it, and runs
the month twice: **fetch, anchor, fetch again, seal.**

## What it proved, and what it caught

**The atomicity claim is true, and is now measured rather than read.** `write_snapshot` writes a timestamped snapshot, puts the
manifest in last as the completion marker, then repoints `current` by making a symlink at `current.tmp` and renaming it over
the old one. The test asserts `current`'s four files are byte-identical to the named snapshot's, and that a run which fails —
a refused endpoint, or an empty payload for one sleeve — exits 2 and leaves the previous corpus byte-identical. Not "should
leave": a hash tree before and after, compared. A silently-shrunken corpus (a sleeve quietly missing) is worse than a fetch
that fails loudly, and the test says so.

**No fetch can produce a month-end that has not traded.** The fetcher drops any session dated today or later, so standing the
clock at 2026-09-07 yields a corpus ending 2026-09-04 no matter how many times the fetch is repeated. The first seal cannot be
pulled forward, and the forward record is calendar-bound in the tooling, not just in the intention. That is worth stating to
anyone hoping the four-week wait could be compressed by fetching harder.

**The loop works.** Second fetch lands a 2026-10-30 bar; the anchored banded book seals against it; one deposit arrives; the
ledger and its shadow chain both verify; the closing value reconciles to the sealed quotes; the recovered cash line is not
negative; no violations are recorded. That is the whole monthly routine, offline, in a second and a half.

**And the test caught my own regression within its first run.** Reading round 87's `missing cash factor` refusal, I decided two
fetches inside one second would collide — which is true — and "fixed" it by having `write_snapshot` invent a `-2` suffix when
the timestamped directory already exists. Two things went wrong. The existing suite's
`test_an_existing_snapshot_directory_is_never_overwritten` refused: the refusal is deliberate, because a snapshot's name is its
identity and the manifest inside it is the completion marker, so a tool that quietly renames its own snapshots has
snapshots that are no longer addressable. And my own version had a subtler fault — the symlink that repoints `current` was
built from the unsuffixed timestamp, so the second fetch left `current` pointing at the **previous** corpus. The failure that
would have produced is the worst kind available: not a crash, but `paper.py` reporting `book is already closed at 2026-09-30`
forever, an operator concluding that a month had been sealed when in fact the corpus had silently stopped advancing. The
change is reverted; the comment now records why `exist_ok=False` is a decision. A pointer that lies is worse than a tool that
stops.

## The state of the runbook, then

Three weeks to the first seal, and the chain is rehearsed at both ends: fetch (this round) and seal (last round), against the
same interface the operator will use, with the real corpus provably untouched by either. What remains genuinely unexercised is
small and worth naming: a real network response with real quirks (a suspended symbol, a payload with a split), and the
`report` output once a book has more than one entry — the latter being the thing that finally answers whether the tilt earns
its fees, which is calendar-bound and not fixable by tooling.

## Checks

**2160 passed, 239 subtests** (`/tmp/suite_r88.txt`), 88 standing rules. `tests/test_fetcher.py` is 26 green as it was before
the round started, which is the evidence that the fetcher's behaviour is unchanged: this round touched only a comment. The
real corpus is byte-identical (hash tree of `data/` taken before and after every class in the new file).

*Round 88. 88 standing rules. The month-end is still three weeks out, and now the fetch is as rehearsed as the seal — and the
suite is what stopped me from breaking it while I was "fixing" it.*
