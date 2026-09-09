# The last mile is a document, so it got tests too

Round 89. New: [`docs/RUNBOOK.md`](../RUNBOOK.md) and
[`test_runbook.py`](../tests/test_runbook.py), 13 tests that re-derive everything the document claims.

## Why a document is the right object for round 89

The objective is money arriving monthly, and the archive's answer to it has been settled for a dozen rounds: a static growth
tilt, bought and never touched, recorded monthly against the index it claims to beat. Rounds 87 and 88 made that *executable* —
the seal rehearsed against a manufactured month-end, then the whole fetch-anchor-fetch-seal loop rehearsed offline. But the
procedure still existed in only two places: a CLI's help text and my own memory across a dozen rounds of notes. That is not a
programme an operator can run in October without me. The gap between "the tools work" and "this can be run every month by a
person" is a document, and a document in this repository that nobody checks becomes a rumour — commands rot, numbers get typed
instead of read, and the authority of prose outlives the truth of the tools underneath it.

So: a runbook, plus a test file whose whole job is to refuse the runbook. Every command in it is checked against the named
tool's own `--help` output (each tool is asked about the subcommand given, since `paper.py --help` never mentions `--book`);
every dollar in the friction table is recomputed from `paper`'s constants and the tilt's posted weights; the first-seal claim is
checked by calling `paper._deposits_due` rather than by trusting the sentence; the status strings it quotes must be strings
something in `tools/` actually prints; the stopping rule may only name fields the ledger really seals. One test asserts the
ugliest number in the file stays ugly — the ratio of ticket cost to everything else at a small account is asserted to exceed 20,
because a future edit that quietly softened "26×" into "meaningful" would be exactly the kind of edit a document makes to itself
when its author stops looking.

## The one number worth more than any signal in this archive

| capital | expense, monthly | spread on the transfer | total | two $9.95 tickets |
|---|---|---|---|---|
| $5,000 | $0.61 | $0.15 | $0.76 | $19.90 — **26×** |
| $20,000 | $2.45 | $0.60 | $3.05 | $19.90 — 6.5× |
| $100,000 | $12.27 | $3.00 | $15.27 | $19.90 — 1.3× |
| $250,000 | $30.68 | $7.50 | $38.18 | $19.90 — 0.5× |

At a $5,000 book on a per-ticket broker, **the brokerage charges twenty-six times what the funds charge** — $19.90 a month to
move two sleeves against $0.76 a month for the whole proportional cost of owning them. This is round 86's crossover said in
operating language instead of dominance-table language, and it is the single most actionable thing this project has produced:
not a signal, not a tilt, not a band — a venue. It is also why `report`'s fee line will look large against its first few
intervals, and why the first honest number is not a return but a cost.

## Four conditions under which the programme stops

Written before the evidence, because a stopping rule invented afterwards is a rationalisation with a schedule.

1. **P0.** If after 24 sealed entries the tilt has not beaten plain VOO on identical charges — same transfers, same spread, its
   own posted fee — the tilt is retired. The books exist to be able to say this.
2. **The band against its own twin.** One declared field separates them. The bill for rebalancing is measured, not imagined:
   $1,091, or 0.054% of paid in, over the 16-year record, and $18 / 0.003% over the last five years. If the banded book falls
   behind the unbanded one by more than that, the band goes.
3. **No claim while `report` says `underpowered`.** The books currently say 23 more monthly entries and $5,000 more paid in are
   required before skill can be distinguished from the witness.
4. **Any integrity failure stops everything immediately** — a book that is not `intact`, an entry carrying a violation, a plan
   line that contradicts its own numbers. Round 87 found one of those (a cent borrowed on a plan that forbids borrowing) and it
   was worth stopping for.

## What this round did *not* do

It manufactured no evidence. A runbook cannot shorten the wait — the first transfer lands 2026-10-30, and the first number that
means anything is years out. What it can do is make the wait legible and the procedure repeatable by someone other than the
person who wrote the engine, which is the difference between a research notebook and a programme. And one honesty note about the
table above: the expense ratios are today's posted ratios applied across a 16-year backtest, which flatters the older years of
funds that have cut fees since issue. The forward books do not have that problem, because a ratio charged on the date it was
charged is a measurement.

## Checks

**2173 passed, 239 subtests** (`/tmp/suite_r89.txt`), 89 standing rules. The new file's 13 tests run in under a second.
`paper.py compare` still reports five books `intact`, one entry deep; `journalctl.py verify` reports `chain intact`. The corpus
was not touched: this round wrote no data, only documentation and its guard.

*Round 89. 89 standing rules. The programme now has a document it cannot quietly outgrow, and the document has a test file whose
entire purpose is to be embarrassed on its behalf.*
