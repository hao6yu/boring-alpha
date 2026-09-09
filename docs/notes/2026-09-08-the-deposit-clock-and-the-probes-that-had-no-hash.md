# The deposit clock, and the probes that had no hash

Goal round 7 (of 96), `goal-91eb485f…`. Two things this round were sentences in documents and are now properties a test enforces, plus a small
incident about how evidence gets polluted.

## The money clock, checked at the runner rather than assumed

Last round's note claimed `--asof 2026-10-30` rehearses the first deposit month. It was plausible, it was unrun, and the objective names that
date as *first deposit 2026-10-30* — so it should have been a checked property, not a claim. Running it showed the right behaviour and said
nothing about it, so the published scenario now computes the arithmetic itself, independently of `paper._months_apart`, and fails if the sealed
entry disagrees:

| seal date | transfers the calendar owes | what the sealed entry says |
| --- | --- | --- |
| 2026-09-30 (first seal) | $0 — 0 calendar months from the 2026-09-04 anchor | `cash_arrived 0.00`, `days_to_invest 0` |
| 2026-10-30 (first deposit) | $500 — 1 calendar month | `cash_arrived 500.00`, `days_to_invest 0` |

That is the whole first-deposit claim, verified: nothing arrives before the date the objective names, exactly one $500 transfer arrives on it,
and the book does not pretend the money waited around before it landed. Both dates now pass the full published scenario — 17 checks, real tree
byte-identical after each.

## The reachable half of the cost stack finally has an artifact

Step 1 wants the cost stack as a *dated, sourced* input with a hash beside the numbers. The fee schedule is unreachable to a script and stays
ingested-only. But since round 5 the reachable half — both coin books, the retail quote, the conversion quote, the product list — had existed
only as prose in a note describing what a live probe printed once. Prose about a megabyte of order book is not evidence: the venue's answers
will move and nothing would show it.

`tools/venue_fees.py snapshot` now appends one JSON line per run to `data/venues/measures.jsonl` — UTC time, and per URL the byte count and the
sha256 of the payload **as fetched** — through one `_fetch` choke point, because hashing a re-serialised guess is hashing the wrong bytes. It
changes no verdict: `taker` still refuses without an ingested fee record, and there is a test named after exactly that temptation
(`test_an_archived_measurement_still_does_not_license_a_price`). One line per run, never edited, so staleness is visible instead of remembered.

## How an evidence file gets polluted, by the test written to protect it

The first version of the archive's test class did not inherit the fixture that redirects `VENUE_DIR`, `RECORD` and `MEASURES` into a temp
directory. So it called `snapshot()` against the real archive and appended **six genuine probe lines** to `data/venues/measures.jsonl` before
failing on an unrelated missing import. It also exposed a second defect: the command printed paths with `relative_to(ROOT)`, which raises the
moment the artifact is relocated — which is precisely what a test does.

Three answers, in order of how much they matter:

- the polluted archive was **deleted and restarted at one honest entry**, not trimmed and not kept, because a file whose provenance is a test
  run is not evidence; the doc says so where the file is described;
- a test now asserts the artifact under test lives under a temp dir
  (`test_the_fixture_moves_the_archive_off_the_real_tree`), which is the general guard against this class of mistake rather than a fix for one;
- and the append-only property is pinned by `after.startswith(first)`, because a file that claims to append and quietly rewrites is worse than
  one that never existed.

## A limitation found while naming a check

The scenario had a check called *"the copy's ledger names a rehearsal snapshot."* It did not check that. A sealed entry carries `asof`,
`quotes`, `holdings`, values and hashes — and **no snapshot id**; the corpus identity in `paper.py report` comes from reading the `current`
pointer at report time, which is a fact about now, not about the seal. Rather than delete the check or leave the name lying, it now reads
*"the synthetic corpus is identifiable by name (entries seal quotes, not a snapshot id)"* and asserts what is actually true. The mitigation is
real, not rhetorical: a seal pins the prices it used, the rehearsal writes only into a copy that is deleted, and its corpus directory says
`REHEARSAL-` in the name. The gap itself — a sealed entry should arguably carry the snapshot it was sealed against — is recorded here so a later
round meets it as a known limitation rather than as a surprise, and it is not free: that is a schema change touching chains that already verify.

## Where the objective stands

Step 1 is complete on the reachable half and human-gated on the rest. Steps 2 and 3 stay published failures. Step 4's BA-006 waits on one
number and carries its disclosures. Step 5 is now verified end to end for both dates the objective names — seal and deposit — at the runner
level as well as the engine level. Nothing is complete while the evidence is historical, and it still is: first seal 2026-09-30, 24 entries to
any claim of skill.

## Checks

**2447 passed, 239 subtests** (2441 + 6 new; collected count printed before the run). Rules: **117**. Files: `tools/venue_fees.py`
(`snapshot`, the `_fetch` choke point, the path-display fix), `tools/rehearse_forward.py` (independent transfer arithmetic, honest check names),
`tests/test_venue_fees.py` (14→20), `docs/data/coinbase-spot.md`, `docs/RUNBOOK.md`, `data/venues/measures.jsonl` (one entry, restarted).

*Goal round 7. The month now proves its own money clock, the probes have hashes, and the round's most useful output is a test that catches its
own fixture writing into the archive.*
