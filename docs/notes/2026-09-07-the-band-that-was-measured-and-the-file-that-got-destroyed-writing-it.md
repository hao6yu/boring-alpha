# The band that was measured, and the file that got destroyed writing it

Measured 2026-09-07, round 84. New: a fifth anchored book, `tilt_band`;
[`test_paper_band.py`](../../tests/test_paper_band.py) (13). Changed: [`paper.py`](../../tools/paper.py) (a banded model, and the
drift convention), [`power_horizon.py`](../../tools/power_horizon.py) (the same drift convention, so the two copies agree).

Round 83 ended with an uncomfortable asymmetry: the *fees* the archive's backtests ignore are worth 0.054% of contributions,
while the *policy* those backtests assume — rebalance to target every month — is worth 10.4% of contributions on the record,
and **negative** on the last five years. A backtest cannot settle that, because the sign belongs to whichever window you ask.
So it went where every unsettled claim in this repository goes: anchored, with the answer arriving in month-ends nobody has
seen.

## The fifth book

`tilt_band` is the live income book — 50% SPY / 50% QQQ, $5,000 opened and $500 a month, plain VOO as its witnessed comparator,
anchored the same day as the others at 2026-09-04 — with exactly one difference: **it trades only when a sleeve has drifted
five points of weight from its target.** Between breaches it buys the deposit and sells nothing.

| book | model | anchored | comparator | difference |
|---|---|---|---|---|
| `tilt` | static 50/50, rebalanced monthly | 2026-09-04 | 100% VOO | — |
| `tilt_band` | static 50/50, rebalanced past 5 points | 2026-09-04 | 100% VOO | the band |
| `constant` | 125% SPY | 2026-09-04 | 100% SPY | leverage |
| `tilt_qqq` | static 50/50 | 2026-09-04 | 100% QQQ | the witness |

The band is `TILT_BAND_POINTS = 5.0`, pinned by a test to the regime table in `rebalance_cost.REGIMES` that produced it, on
the same footing as `TILT_WEIGHT` being pinned to `mix_sweep`'s control row. `--band` is accepted by the CLI and refused, as
`--tilt` is: a caller may not choose a number whose entire value is that it was measured. Round 70's rule that a book has one
construction is honoured in the narrow way — the two books differ in the policy and in nothing else, and a test asserts the
sleeves, the fees and the witness are identical while `tilt`'s own config contains no band key at all, so the policy was never
retrofitted onto a sealed book.

## The defect the tests caught, in the second draft of a brand-new function

`orders_within_band` first measured drift the obvious way — each sleeve against the target, over **total equity including the
cash that had just arrived**. For a book that receives a deposit every month, that measure says every sleeve is underweight by
about the deposit share, every month, forever. At this book's 10% deposit ratio the phantom drift is 5 points: exactly the
band. The band would have breached on schedule and the book would have rebalanced monthly while reporting that it was being
patient.

Drift is now measured across the **invested** book — the arriving cash is excluded, because incoming money is not a
misallocation, it is next month's rebalance, and it gets spent in the buy-only branch. The same convention was applied to
`power_horizon.simulate`, which computes its own drift and cannot import this one; two copies of an accounting rule that
disagree is round 82's lesson, and the fixture for the 3-point case now reads 3.0 points in both.

The three properties the tests hold, all of them paid for in round 83: inside the band there is never a sell; the deposit is
invested anyway (a band that strands the deposit is a cash-drag policy wearing a low-turnover name); and at inception, when
every sleeve is 50 points adrift, the band does not stop the opening from being invested.

## The part that is not a success story

Between the last verified state of this repository and this note, `tools/paper.py` was destroyed by my own scripted patch: a
one-off Python heredoc that patched two files in sequence reused a single variable for both sources, and after re-reading the
second file it wrote that content back to the **first** path. `paper.py` — the journal engine, every r70–r84 rule that lives
in it, fourteen rounds of work — became a byte copy of `power_horizon.py`, 320 lines instead of a thousand.

There was no copy. The file was **untracked**: never committed, so no git blob; `__pycache__` had been overwritten by the
import of the broken module a minute later; no local APFS snapshot, no editor history (nothing had been opened in an editor —
every write came through me), no dangling git object. `tools/` in this repository is one large pile of uncommitted work held
in place by nothing but the filesystem.

What survived is what this repository spends its whole design protecting: `data/paper/` — every ledger, every shadow chain,
the pinned comparator, all five books' anchors — because the ledger is append-only content-addressed JSON and does not care
what reads it. `journalctl.py verify` reported `chain intact` at every point during the loss, and `src/boring_alpha/journal.py`
(which owns the hashing, so the rebuilt file cannot quietly change what an entry means) was untouched. The rebuild is driven by
the ~100 tests in `tests/test_paper*.py` plus the sealed configs, which is precisely the situation those tests were written
for: they were the specification, and they did not move.

Eleven behaviours could not be recovered from any evidence — the shape of the note fields on each entry, the trend model's
weights, the borrow-rate convention, and so on. They are listed in this note rather than guessed over, and most of them are
cosmetic: no sealed entry depends on them, because every book still holds exactly one anchor row. One of them decides money, so
it was not left as an accident.

**A missed seal used to forgive the deposit it missed.** The rebuilt `_deposits_due` paid one transfer per *seal*, so a book
that skipped a month-end arrived with $500 instead of the $1,000 that would really have been wired — and since paid-in is the
denominator of every dollar-weighted return in `journal.py`, under-arriving money raises the reported return. The convention is
now one transfer per calendar *month*, with `days_to_invest` recording how long the oldest tranche waited (which is also what
makes the ledger's own idle-cash finding reachable for the first time), and four tests in
[`test_paper_books.py`](../../tests/test_paper_books.py) pin it: the anchor's month is already funded, one month pays one
deposit, two months pay two, and a late tranche is sealed as late. This is a choice made during a recovery, stated here, not a
restoration of something known: the honest alternative was to let a lost file's ambiguity decide the book's own denominator.

Two operational changes follow, and they are not stylistic:

- **A patch script writes one file and re-reads it to verify, or it does not run.** The failure mode here is invisible from
  the outside — the script printed "drift measured across the invested book", which was true of the *string*, and then wrote
  the wrong content to the wrong path.
- **The tool tree gets committed**, or every future round is one careless variable name away from starting over. The ledger
  cannot be silently amended; the code that reads it currently can be silently deleted.

## Checks

The rebuild is trusted because it reproduces measurements taken before the file was lost, not because it looks reasonable:
`rebalance_cost.py` prints round 83's 50/50 row **to the dollar** ($9,783,165 / $9,988,324 / $9,778,203, with $1,697 of spread
paid and 100 of 193 months sold); the witness arithmetic lands independently on round 74's published $5,497.92 for the first
2024 interval; the live report prints round 81's skill and dominance lines verbatim; `paper.py compare` lists all five books
`intact`; `journalctl.py verify` reports `chain intact` and the comparator spec unedited; and all 14 tools that import `paper`
exit 0 on their default arguments, none of them edited.

The one column that moves is the banded one, for a reason written above: under the corrected drift convention the 75% QQQ
book's 5-point band ends at $11,008,766 where round 83 printed $11,001,368. The phantom drift that the old convention invented
from each arriving deposit used to make it believe it had to trade; without it, it traded less and did better. That $7,398 on
an eleven-million-dollar account is the size of the defect on that book, and it is the same defect that would have made the
live `tilt_band` book rebalance monthly while reporting that it was being patient.

Suite: **2115 passed, 239 subtests** in 767 s — round 83's 2096 plus 15 band tests and the 4 cadence tests. 84 standing rules.

## Footer

Suite after the rebuild and the cadence tests: the totals are in `/tmp/suite_r84.txt`; the paper suites are 96 tests, the five
dependent suites 81, `paper.py compare` lists five books all `intact`, `journalctl.py verify` reports `chain intact`, and
`rebalance_cost.py` still prints round 83's 50/50 row to the dollar.

*Round 84. 84 standing rules. Five anchored books, all `intact`, none of them holding more than the $5,000 they opened with:
the answers are calendar-bound, and the engine that writes them had to be rebuilt from its own tests before any of this could
be believed.*
