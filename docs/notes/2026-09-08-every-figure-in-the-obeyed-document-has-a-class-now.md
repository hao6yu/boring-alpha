# The runbook's figures now have a class each, and the first thing it caught was this round's own footer

Round 101. Changed: [`RUNBOOK.md`](../RUNBOOK.md) (two stale figures, one copied figure removed, footer made truthful),
[`test_runbook.py`](../../tests/test_runbook.py) 16→21.

## The sweep round 100 implied

Round 100's rule was narrow — *the friction paragraph's percentages must be the tools' own*. This round applied the rule to the rest of
the document's load-bearing numbers, by recomputing them rather than by grepping a second copy of each:

| the runbook said | the tool says | verdict |
|---|---|---|
| paid in $2,020,000; VOO $7,853,675; bills $2,447,542 (+21.2%); tilts 9,778,202 / 9,812,538 / 9,988,324; 71%; −4.1% | `power_horizon.secondary_bars` | all reprinted exactly |
| the banded book sits **$2,404,018** behind plain QQQ | `$2,404,017` (12,216,556 − 9,812,538) | **off by a dollar** — corrected |
| the tilt loses to QQQ "**12,316,793 against 9,841,466** in round 82's replay" | today's replay: 12,216,556 / 9,778,202 | attributed honestly to round 82, and still wrong to print: the archive was re-pulled after that replay, and the archive's revision is exactly what round 96 measured (all rows 0.4–0.8% low). **Removed the copy**, pointing at the command instead |
| `beat` **18.8%**, luckiest 5% clearing **+152 bps**, "~50 at 36", no-skill median **58 bps** behind, "by anything at all at 60" | `skill_null.py --paths 600`: 0.1883 / +151.85 / +49.78 / −58.12 / p95 = **−0.18 bps** | every figure reprints; and the *qualitative* claim "no margin at 60" is now a tested claim, since p95 must stay ≤ 0 for the sentence to be true |

The one-dollar figure matters less than its shape: it was a hand-rounded difference of two numbers that a command prints to the dollar,
in a sentence whose whole job was to quote that command. The stale pair mattered more: a figure with provenance is still a copy, and
round 96 had already measured how far such a copy drifts. Round 94's rule again — *a fact in four files exists four times, and the copies
disagree* — now applied to prose inside a single file. The sentence no longer carries dollars; it says the command's own line is the figure.

## Pinning to the dollar is a decision, and it is disclosed

These figures are corpus-coupled on purpose. A re-pull that moves the replay will fail `TheDecisionFiguresAreReprinted`, and that failure
is correct: the runbook would then be quoting a number the corpus no longer produces. `corpus_diff.py` is where the programme decides
whether a revision is tolerable; this class is where it refuses to quote a moved figure as if it had not moved. The docstring says so, so
the next person does not "fix" the test by widening a tolerance.

## The test caught a lie about itself, within the hour

The footer used to read: *"the friction columns are recomputed by `tests/test_runbook.py` on every run."* It now names the three classes
that do the recomputing — and its own test reads those names back out of the source and requires each class to exist. The first version of
that footer named a class called `TheNumbers`, which has never existed in any file in this repository. It was caught by the test written
four minutes earlier. That is the argument for the whole round in one line: **a claim that a check exists is itself a claim, and it needs
the check.**

## Checks

**2309 passed, 239 subtests** — five new tests, four asserting published figures against their tools and one asserting the document's
claim about its own coverage. Runtime cost: one `skill_null.py --paths 600 --json` call (1.4 s) and two `secondary_bars` blocks, in
`setUpClass`, so it is paid once. Two formatting traps found on the way, both the runbook's fault and both the same one as round 100's:
a markdown line break landing inside a quoted phrase ("8.70% of / paid in", "so the / command's own line") makes a prose test fail for the
wrong reason, so quoted phrases now get their own line. Live state unchanged: five books, one anchor each, all chains verify, sealed fees
$0.00, first seal 2026-09-30.

*Round 101. 101 standing rules. Every figure the operator is asked to act on is now printed by a command and checked by a test, and the
runbook says which class owes it — because the sentence "this is checked" is the most expensive kind of claim a document can make.*
