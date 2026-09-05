# BoringAlpha: Codex's response to the project review and model ratings

Date: 2026-09-05. Reviewed repository: `754dd5265de0625338d1084e009a4a75608b88d3`.
Author: Codex, a participant in this project, writing at the owner's request.
**This is a participant's assessment, not an independent audit or model benchmark.**

Responds to the [local GLM review](2026-09-04-project-review-and-model-attribution.md)
and [Fable's response](2026-09-04-fable-response-to-project-review.md).
Those notes assess an earlier September 4 checkpoint. This response separates
that comparison from the September 5 evidence now available.

## My verdict

**Good research software, useful negative evidence, no demonstrated trading edge.**

I agree with the best part of GLM's diagnosis: the lab's strongest achievement
is making a flattering but unsupported answer harder to produce. I disagree
with treating that as sufficient success indefinitely. The owner wanted a fun
project with a possible economic use, not an expanding bureaucracy for eight
ETFs. The next improvement should answer a better question, not add another
approval mechanism.

The current result is more specific than “we don't know.” We have enough
evidence to decline further investment in **BA-002 as currently defined**.
That is an economic decision about one candidate under explicit assumptions,
not proof that momentum cannot work, nor proof that AI cannot help investors.

## What I checked, and what I did not

I read both rating notes, the BA-001 validation and after-tax records, the
BA-002 source-sensitivity results, the correction/simplification records and
the BA-003 draft. Targeted code checks covered the two trend signals, account
reconciliation and the existing execution/planning interface. A separate
read-only attribution pass checked the rewritten commit map and relevant
commits. These are sampled checks, not a fresh line-by-line audit of the repo.

The immediately preceding repository verification ran the full suite:
**1,044 tests passed in 122.11 seconds**. It printed no separate subtest tally.
The subsequent Git identity rewrite preserved every commit tree; the final
commit added only the rewrite record/map. I did not rerun the suite or compute
new historical returns for this response. Earlier reports' different subtest
counts remain observations of those runs, not numbers to silently combine.

No new market data, protected-period observations, live orders or credentials
were accessed for this review. Recorded performance below comes from existing
reports, not a fresh independent backtest.

## The engineering credit is deserved—but has limits

Three mechanisms earn their complexity:

- **Bound the information before computing.** Calendar checks and period
  truncation address real ways a historical simulation can answer the wrong
  question while looking internally consistent.
- **Preserve enough evidence to replay an answer.** Stored inputs, decisions,
  orders, fills, curves and content identities are more useful than a screenshot
  of a return number. A hash alone detects change; retained bytes enable replay.
- **Check accounting through a separate reconstruction.** The replay validator
  rebuilds cash and holdings from fills and compares them with the archived
  curve. Two tax formulas agreeing with each other cannot detect every missing
  trade; this additional comparison can catch a different class of mistake.

None of those mechanisms establishes that the market feed is true, that the
tax assumptions match an actual taxpayer, or that the signal will work next
year. The second-vendor comparison improves the evidence without removing
those limitations.

The documented test failures also matter more than the test count. Reviewers
reintroduced plausible bugs and found tests that stayed green. Later fixtures
were constructed to fail under those mutations. That is stronger evidence
than the number of test methods, but it is still not proof that all remaining
tests can detect the mistakes they claim to guard against.

## Where I would be harder on the project

**Scope proportionality.** The first BA-002 workflow attempted to solve more
authorization and failure-state problems than this one-person lab needed.
Simplifying it after criticism was good. Not needing that correction would
have been better. I would not turn the ability to construct a large governance
layer into a claim that constructing it was the right decision.

**Research breadth.** A 12-month trend rule and a 9/12/15 ensemble are related
ideas, not a diversified research program. BA-003 asks a more distinct question,
but it still belongs to the same broad momentum family and uses already-seen
windows. An identifier is not a statistical reset button.

**Implementation realism.** The $100,000 fractional-share simulation does not
establish practicality for the intended $2,000–$5,000 account. The tax overlay
is stylized, and its NAV-rescaling convention is not a broker simulation of
selling positions to fund tax payments. Drawdown gates use pre-tax, cost-net
daily equity, not an enforceable maximum loss on a live account.

**Negative results are useful, but not infinitely useful.** Rejecting a weak
candidate can prevent a bad allocation of attention or capital. That does not
demonstrate positive investment returns from the project, or quantify money
saved. We have not measured a net financial return on model subscriptions,
data, or the owner's time.

## Three corrections to the earlier reviews

1. **GLM's status snapshot has aged.** At its checkpoint, BA-002 was
   synthetic-only and the independent vendor check was absent. Since then,
   the [two-source screen](../reviews/BA-002-source-sensitivity.md) completed
   and supported a practical no-go. Calling the current output “zero economic
   conclusions” now misses a real, if disappointing, conclusion.
2. **Fable's “turnover and whipsaw criteria” wording is imprecise.** BA-001's
   [validation report](../reviews/BA-001-validation.md) records failures of the
   Sharpe guard and related robustness criteria, and says costs were not the
   binding constraint. Whipsaw is part of the explanation, not the name of
   the mechanical verdict.
3. **The approximately 60-bps deduction estimate is not verified evidence.**
   The [after-tax note's scope postscript](2026-09-04-BA-001-after-tax.md)
   explicitly declines to adopt it as a bound. An optional sensitivity now
   exists, off by default; it did not rescore the archived BA-001 tables or
   alter BA-002's comparison.

BA-001's after-tax tables also retain their original code/data identities.
Later holding-period corrections and the TLT source repair did not rewrite
those historical calculations. They must not be marketed as newly rescored
results incorporating every later correction.

## The model ratings: useful opinions, not a leaderboard

GLM correctly disclosed the small sample and shared workflow. Its further
suggestion that the relative rankings are more trustworthy than the absolute
scores does not follow: the rankings are also confounded by assignments,
review opportunities, human instructions and delegation.

Fable's strongest correction is about attribution. A commit trailer identifies
who took responsibility for a change, not everyone who improved it. Fable
reports that much implementation was delegated to Sonnet/Haiku and reviewed
by other models. GPT-5.6's design criticisms landed in Fable-tagged commits.
Those are not isolated contestants doing the same task under equal conditions.

Here are my **whole-point scores for the delivered project contributions at
the September 4 comparison checkpoint**. I prioritize correctness and
verifiable evidence, then research judgment, then useful implementation and
proportionate scope. Code volume and commit prose are secondary. These are
subjective judgments, not a calculated weighted average: **9/10 means a
standout contribution with meaningful caveats; 8/10 means strong work
materially reduced by avoidable defects or complexity.** Neither means
first-attempt correctness or predicts general model ability. Later September 5
work is discussed separately above; it is not added to these scores.

Same-day revision, 2026-09-05: following the owner's feedback that identical
broad bands obscured the assessment, I replaced them with explicit scores and
the rationale below. This is a sharper evaluative judgment of the same
evidence, not a new audit or new performance evidence.

| Contributor label | GLM overall | Fable's response | My project-contribution score |
|---|---:|---:|---:|
| GPT-5.6 / Sol, per the owner's identification | 8.4 | 9.0–9.2 | 9/10 |
| Opus 5 | 9.4 | No revised numerical score | 9/10 |
| Fable 5.1-directed work | 9.3 | 8.8–9.0 | 8/10 |
| GPT-6 Astra-directed work | 8.3 | 8.8–9.0 | 8/10 |

| Contributor | Strongest demonstrated contribution | Main deduction |
|---|---|---|
| GPT-5.6 | Skeptical design reviews, five substantive tax-accounting corrections, independent account replay and discriminating regressions. | The initial skeleton still needed extensive hardening; its later verification strengths do not make that first version reliable. |
| Opus | Foundational engine and evidence work: calendar timing, sealing, artifact/provenance separation, the harness and execution split. | Several mechanisms and tests needed later correction; polished commit messages cannot establish correctness. |
| Fable-directed work | Research framing, orchestration and candid development/validation reviews, including explicit pre-commitments and the decision to leave the holdout unrevealed. | Five consequential accounting errors survived its design and planned review process, alongside repeated evidence-record corrections. |
| Astra-directed work | The substantial BA-002 integration: signal, paired screening, replayable evidence and calendar, incorporating external review. | Overbuilt initial governance, remaining important review findings and a difficult-to-review mega-commit. |

The ties are deliberate, not a refusal to judge. I give GPT-5.6 and Opus the
higher scores for two different standout contributions: skeptical verification
and foundational engineering. Fable's research leadership and Astra's
integration work were strong, but their avoidable correctness and scope costs,
respectively, weigh more heavily in this lab. The record does not support
finer distinctions within those pairs, and **these project-specific scores do
not establish an ordering of general model capability**.

Acknowledging externally found errors is valuable, but is not discovery credit.
Session structure partly explains Astra's commit granularity; it does not make
a 13,000-line change easy to inspect. Neither the amount of code nor the number
of passing tests is a substitute for evidence that the relevant behavior is
correct.

I will not reclaim GPT-5.6's correction work for Astra. The
[attribution record](2026-09-04-fable-response-to-project-review.md) explicitly
assigns the tax corrections to GPT-5.6 and the BA-002 build to GPT-6. The
no-trailer mapping comes from the owner's confirmed account, not Git proving
which backend model generated particular lines. “Sol” likewise comes from the
owner's identification, not the original Git metadata.

GLM deserves credit as a reviewer too: its broad critique redirected attention
from construction toward data quality and economic usefulness. I would not
give it a coding score from a task that did not ask it to build the system.

## What I would do next

Review the [BA-003 proposal](../strategies/BA-003.md), then—only after agreement—
implement its narrow change and run its fixed seen-history screen. Keep the
passive comparator and no-signal control, both feeds, existing economic bars,
and the stopping rule. Do not expand the hypothesis search merely because
writing another variant is cheap.

Passing that screen would justify discussing a separately authorized forward
paper test, not funding or opening the shared holdout automatically. Failing
would justify shelving the candidate, not inventing another gate.

**My one-line review: the useful product so far is a better-supported “no,”
not a better-disguised “yes.”**
