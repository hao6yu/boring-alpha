# One screen for four ways this programme can be wrong

Round 92. Changed: [`forward_p0.py`](../../tools/forward_p0.py) gains `--against` and `--status`;
[`test_forward_p0.py`](../../tests/test_forward_p0.py) grows from 13 tests to 25; [`RUNBOOK.md`](../RUNBOOK.md) puts one command
first in the monthly block.

## What was still manual

Round 91 gave stopping rule 1 a command. Rule 2 — the banded book must not fall behind its unbanded twin by more than the
measured rebalancing bill — did not: `paper.py compare` prints each book against its **own witness**, which is the wrong pair for
this question, because the witness is the zero-commission twin of the same sleeves and the twin that matters is the *same book
without the band*. And the operator had six commands a month and no single place that answered "what do the four conditions say
today", which is the only question a monthly procedure really asks.

## Two additions

**`--against <book>`, for the band against its twin.** Net value in dollars at identical paid-in, each side reduced by the orders
*it actually made*, counted from changes in sealed holdings. Two chains that have not sealed the same intervals are refused
outright — comparing a policy over different periods is not comparing policies. The allowed shortfall is the measured bill as a
**share of paid in** (default 0.054%, `--bill-cap` to override), so the test is scale-parametric like everything else here, and
three outcomes are possible rather than two: `BAND FAILS its own twin` past the cap, `no verdict either way` inside it, and a
statement that the band is ahead but the twin is the cheaper construction by default. The middle one is the point: a check that
can only print pass or fail will always be read as a pass, so the arithmetic is allowed to say *inconclusive*.

**`--status`, for the monthly screen.** Four conditions, each with the command that owns it:

```
P0 — beat plain VOO net of everything      nothing to compare yet: … no interval over which to price VOO
The band, against its own twin             nothing to compare yet: neither book has sealed an interval with holdings in it
Skill, past the protocol's floor           underpowered — 23 more monthly entries and $5,000 more paid in
Integrity, immediately                     all chains verify
```

Three of the four read `not decidable` today, and the screen exits 0 anyway, because nothing is wrong: the record is three weeks
old and the first interval seals on 2026-09-30. A status line that manufactured a verdict from one anchor entry would be the most
expensive line in this repository, and a status command that exited non-zero while honestly reporting ignorance would train the
operator to ignore its exit code — which is the only property that makes the integrity line worth anything.

## Two test premises that were wrong, and why they were worth writing

The fixtures are built so the expected answer is arithmetic, and twice the arithmetic disagreed with my expectation rather than
with the tool. First, I asserted the banded book would be *ahead* of its twin on a pair of fixtures whose sealed closing values
are identical — with commission zero, two identical books tie, full stop; the venue had to be introduced for anything to
separate them. Second, I computed the bill cap against the $5,000 opening and the tool used $6,000 paid in, because the fixture
has two deposits in it and paid-in is the thing the bill is a share *of*. Both were corrected in the tests, not in the tool, and
both are recorded here because the failure they represent — a fixture whose two sides are secretly the same, a denominator that
quietly excludes money that arrived — is the class of mistake that makes a passing test worth nothing.

What would have been worse is the version of the pair check that assumes the band trades less: a banded book is *claimed* to
trade less, and the whole reason the comparison counts orders off sealed holdings is that the claim is testable and the claim is
sometimes false. If the sealed chain shows the band trading more than its twin, that number goes into the report, not a theory
about drift.

## Checks

**2210 passed, 239 subtests** (`/tmp/suite_r92.txt`), 92 standing rules. Live books unchanged: five `intact`, one entry each,
sealed fees to date $0.00. The monthly block's first line is now the screen, and the screen's first line tells the truth about
how little is knowable this month.

*Round 92. 92 standing rules. Every stopping condition in the runbook now has a command behind it, and every one of those commands
is permitted to say it does not know yet.*
