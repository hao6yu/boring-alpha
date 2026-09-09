# A rehearsal already existed, and the runner did not

Goal round 6 (of 96), `goal-91eb485f…`. The step that is live right now is step 5: the first real seal is 2026-09-30, three weeks out. I went
at it with a premise I'd picked up from the runbook's own framing — *the seal path has never run for real, and a monthly procedure whose first
test is its first run will fail in public on the day it matters* — built a rehearsal for it, watched it go green, and then read the paragraph
in the runbook that the tool was written to protect:

The paragraph I had not read said that before the first seal of a new book set, `rehearse_forward.py` walks the engine through a month-end
that has not happened — flat, band-breeding, a skipped month, a crash — against a scratch copy, and reports whether the real files were left
byte-identical, with a class under it since round 107. This round rewrote that paragraph; the rewritten version keeps the claim and adds the
half that was missing, so the archive's own history is still readable in the file.

So rounds 87 and 88 had already done this, and the tool's own docstring opens with the sentence I had just re-derived. The duplicate tool is
deleted, and the honest order of this round is: **read the authority first.** What survives is the part that genuinely did not exist.

## What was missing was a way to point the loop somewhere disposable

`rehearse_forward.py`'s four scenarios drive `paper.py` **in-process**, on one scratch book that `init` creates. That is the right rehearsal
for the engine and the wrong shape for a month: a month is eleven commands, each its own process, each resolving the state root at its own
import, over the five books that actually exist — `forward_p0`, five seals, `journalctl verify`, `audit_entries`, the cost sheet, a report, a
compare. There was no way to point *that* chain at a copy, so nothing in the repository had ever run it against a fabricated month-end.

Two pieces make it possible, both small:

- **`tools/labdata.py`** — one resolver for the lab's state root, read from `BORINGALPHA_DATA`. It refuses a path that does not exist, and
  it refuses an override that names the real tree — including the repository root, which is the typo that matters, because it reads like a
  rehearsal and then writes into the append-only ledgers the whole objective rests on. `journalctl.py` takes the redirected *journal* but
  keeps its pinned comparator snapshot hardcoded on purpose: an anchor that a rehearsal could move would turn the verification tool into a
  way of passing.
- **`rehearse_forward.py --scenario published`** — the block itself, as an operator runs it, against a copy of `data/paper` and
  `data/journal` with the corpus carried forward flat to the seal date. The fetch and the corpus diff are dropped, because a rehearsal must
  not be able to write a real snapshot and there is only one corpus here anyway, and it is fake.

## What the month actually does

Fifteen checks, all ok, in 10 seconds:

| check | result |
| --- | --- |
| all eleven published commands | exit 0, root sealed at $4,998.11, four books sealed, `journalctl` chain and pinned comparator intact |
| `audit_entries.py` on the fresh chains | `clean — 2 entries account for themselves` |
| every live book sealed exactly one new entry | 5 of 5 ledgers gained exactly one |
| **running the month twice** | **refused**: `book is already closed at 2026-09-30; nothing new to seal` |
| the copy's snapshot id | `REHEARSAL-2026-09-30T000000Z`, with a sidecar naming what is invented |
| files changed under the real `data/` tree | **0**, checked by hashing every file in it before and after |

The double-seal check is the one I'd have skipped, and the only one that changes what I expect on 30 September. The likeliest way a monthly
book gets broken is not a crash, it is somebody running the ritual twice — and "all commands exited 0" on the happy path is exactly the
report that would have hidden a second seal for a date already sealed, corrupting the deposit accounting and every hash downstream of it. A
rehearsal that never asks for the refusal is a rehearsal of the good weather.

`--asof 2026-10-30` rehearses the first deposit month too, so the loop is now known-running for both dates the objective names.

## Where that leaves the objective after six rounds

Step 5 was never the question mark this round thought it was — but it is now verified at the runner level as well as the engine level, which
is what "keep the loop running" has to mean before it can run. Steps 2 and 3 stay published as failures (BA-005 fails on grounds no fee can
move). Step 4's BA-006 is still open on exactly one input — the fee tier — and still carries the disclosure that its clearing row exists only
from 2016-05-18, with a cash leg worth $16/month of the difference. Nothing here is complete: the evidence is still entirely historical, the
first seal is 2026-09-30, and 24 entries stand between now and any claim of skill.

## Checks

**2441 passed, 239 subtests** (2428 + 13 new; collected count printed before the run). Rules: **116**. Files: `tools/labdata.py` (new),
`tools/rehearse_forward.py` (the published scenario, +15 checks), `tools/paper.py` and `tools/journalctl.py` (state root through one resolver;
the anchor stays), `docs/RUNBOOK.md` (one rehearsal tool, two documented halves), `tests/test_rehearse_forward.py` (12→19),
`tests/test_labdata.py` (new, 6). Deleted: `tools/rehearse_month.py`, `tests/test_rehearse_month.py` — the duplicate, and its tests.

*Goal round 6. The rehearsal existed; the runner didn't. Six rounds in, the loop is known to run, the answer keeps being the boring one, and
the only number still missing is one only the account holder can read.*
