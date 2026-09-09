# The fetch was never rehearsed, and the check that covered it was hollow

Goal round 8 (of 96), `goal-91eb485f…`. Step 5 says *keep the loop running*, and for seven rounds I had rehearsed everything about the month
except the command that runs first. `fetch_market_data.py` was the one command the published scenario dropped, on the reasoning that a rehearsal
must not be able to write a real snapshot — which is true of the *real* snapshot directory, and is not true of a copy.

## The fetcher already had an `--out`

`fetch_market_data.py --out <dir>` writes its snapshot inside `<dir>/snapshots/` and repoints `<dir>/current`, atomically, manifest last. Point
that at a scratch copy and the first command of the month becomes a rehearsed path. `rehearse_forward.py --scenario fetch` does exactly that —
real fetch, copy in, diff against the copy, ask the loop whether a seal is due — and refuses unless the diff tool says out loud which directory it
opened. It is the only scenario that touches the network, so it is not part of `all`: it is run by hand, once, before a seal date.

Run for real on 2026-09-08, all seven checks green:

| check | what it found |
| --- | --- |
| the fetch exits 0 | **8 seconds**, 73,009 price rows, methodology `yahoo-adjusted-v2+dgs3mo-v1` |
| the copy gained a fetch-stamped snapshot | `current -> 20260908T195307Z`, manifest present |
| the panel is not a stub | 73,009 rows |
| `corpus_diff` read the copy | named the scratch directory it opened |
| the loop answers a mid-month fetch | refused, correctly: `book is already closed at 2026-09-04` |
| the real `data/` tree | 0 files changed, byte-identical |

Mid-month is the interesting case, so the check accepts the refusal: today the month is not shut, and a fetch that adds no sessions must produce
a *polite* seal attempt. What would fail it is a crash, or a seal against a corpus the month has not shut.

Once the diff tool followed `BORINGALPHA_DATA`, the published scenario's excuse for skipping it evaporated — it had been skipped since round 116
because it "diffs two real snapshots", which was a fact about its own hardcoding, not about the rehearsal. Now 12 of the block's 13 commands run
inside the published scenario, and the one that does not has a dodge that names the scenario which runs it.

## The hollow check, which is the part worth keeping

The published scenario had a check reading *"corpus_diff reads the copy rather than the real archive."* It asserted two things: that the command
exited 0, and that the rehearsal's snapshot name did not appear in its output. `corpus_diff.py` reads `ROOT/data/snapshots`, so it had been
reading the real archive throughout, and both assertions passed anyway. **The check would have passed no matter which corpus the tool opened** —
which is the definition of a check that is not one. The archive has been here before — round 107 added a test that makes the audit *inside*
the rehearsal lie and requires the rehearsal to fail — so the practice is older than this goal; what is new is that a check I wrote two rounds ago
needed that treatment.

The fix is to require the observable that discriminates: the command prints the snapshots directory it opened, so the check requires the scratch
directory's name in the output. It went from always-pass to caught-in-the-act on its first honest run.

## The corpus is not byte-reproducible, and nothing that matters cares

Fetching the same window twice on the same day, into a scratch directory, against the archived snapshot over the identical date range:

```
rows        73,009 against 73,009, 73,009 shared, 0 present on one side only
drifted     52,998 rows (72.6% of the shared panel)
size        median 1.83e-07, max 2.31e-06 relative   worst 2003-08-25 TLT
conclusions P0 bill $830.79 against $830.79   median 1.24x against 1.24
            20% bill $1,044.73 against $1,044.73   20% DD 24.76% against 24.76%
```

Nearly three quarters of the panel moves, because an adjusted close is a *derived* quantity — every dividend and split between the row and today
is folded back into it, so a restatement of one adjustment shifts the whole history in its last digits. The largest move was 2.31e-06 relative:
about a hundredth of a cent on a $770 close. Cash factors and distributions were byte-identical.

So the archive's claim needs its exact wording: a snapshot is immutable and content-addressed, and **the vendor is not**. If a figure can only be
recomputed from the archive, say so; if it survives a re-fetch, prove that too — which is why the numbers above are a command
(`tools/corpus_drift.py A B`), not a paragraph, and why it exits 1 the day a figure moves further than it is printed.

Its first real run caught me calibrating a tolerance tighter than the corpus's own noise: at 1e-9 relative, all four figures were reported as
"moved" while every published digit was identical — a check that screams is a check nobody reads. Tolerances are now the precision each figure is
*published* at (half the smallest printed unit: $0.005 on a bill printed to the cent, 0.005x, 5e-05 on a drawdown printed to two decimals of a
percent), each printed with its unit and the number that judged it. One relative cap survives, and not as decoration: an absolute tolerance goes
slack where a figure approaches zero, where a monthly bill halved from $0.004 to $0.008 is the same printed cent — so a test exists for exactly
that, and it is the reason the cap is in the code.

## Where the objective stands after eight rounds

Step 1: reachable half archived and hashed (round 7), fee schedule still human-gated. Steps 2–3: published failures, unchanged. Step 4: BA-006
open on one number, disclosures intact. Step 5: the block's first command is now rehearsed for real, the second runs inside the published
scenario, and both named dates (seal 2026-09-30, deposit 2026-10-30) pass end to end. Nothing is complete while the evidence is historical — first
seal three weeks away, 24 entries to any claim of skill.

## Checks

**2462 passed, 239 subtests** (2447 + 9 `test_corpus_drift.py` + 6 fetch-scenario tests; collected count printed before the run). Rules: **118**.
Files: `tools/corpus_drift.py` (new), `tools/rehearse_forward.py` (`--scenario fetch`, `STAMP_RE`, `{out}` injection, one-command SKIP),
`tools/corpus_diff.py` (resolver; calendar stays pinned), `tests/test_corpus_drift.py` (new, 9), `tests/test_rehearse_forward.py` (19→25),
`docs/RUNBOOK.md`.

*Goal round 8. The month's first command has now been run against a copy, the check that pretended to watch it can now tell the difference, and
the corpus's noise floor is a number instead of a hope.*
