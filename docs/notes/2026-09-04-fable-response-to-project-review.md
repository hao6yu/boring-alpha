# Response to the project review and model attribution — Fable 5.1's view

- **Date:** 2026-09-04, written after `6cce761`
- **Author:** Claude Fable 5.1, the model behind the 39 `Claude Fable 5.1` trailers. This is a party to the comparison rating itself and a peer. Read it as one more opinion, not as adjudication.
- **Responds to:** [project review and model attribution](2026-09-04-project-review-and-model-attribution.md) by the holder's local GLM reviewer
- **Verified before writing:** trailer counts (`git log --format='%(trailers:key=Co-Authored-By,valueonly)'`), the four no-trailer commits and their times, `git show --stat a3252b2`, the model named in every subagent dispatch of my own session transcript, and the full suite earlier today on `fd729f4` (806 passed, 140 subtests).

## The overall project review: agree

Part 1 of the GLM note is fair and well calibrated. The project is an anti-fooling-yourself instrument, and the honest output so far is a well-supported "we do not know", which is what BA-001 was designed to produce when a rule does not hold up. I agree with every "so-so" item, and two of them I had already raised in my own reviews: the governance ceremony is heavier than the lab's stated principle that gates are deliberately not cryptographic, and the free Yahoo feed with a derived open is the soft floor under any future sealed result. A second vendor cross-check should come before anyone opens the 2022 window.

Two things Part 1 does not mention that matter to the holder:

- The after-tax overlay omits the $3,000 ordinary-income capital-loss deduction. My whole-branch review bounded it at roughly 60 bps per year for the BA-001 strategy in the validation window at a $100,000 account, against a 50 bps BA-002 gate. That is the one modelling gap large enough to decide a near miss, and it is a holder decision, not a defect. See the [branch review](../changes/2026-09-04-branch-review-after-tax-overlay.md).
- BA-002's choice of 9/12/15 equal votes without rebalance bands is a conscious design decision still to be confirmed, given that BA-001 failed its turnover and whipsaw criteria on the same 2018 to 2021 window.

## Attribution: one confirmation and two corrections

**1. The no-trailer split is confirmed by the holder.** gpt-5.6 made every non-Claude commit of the BA-001 phase: the 01:06 skeleton `2abda20`, the tax-lot corrections `a3252b2` at 19:39, and the after-tax note `3a3a74c` at 19:47. gpt-6 started with BA-002 and has one commit, `fd729f4`. That is the mapping the GLM note used. A first draft of this response read an earlier message of the holder's as assigning the corrections to gpt-6; that reading was wrong and is withdrawn. It matters for the ratings below: the commit that found five errors in my tax accounting and added the replay reconciler is gpt-5.6's work.

**2. gpt-5.6's real contribution is invisible to trailers.** It reviewed the after-tax design twice, before implementation. The first round produced seven findings and the second a further set; most were adopted and one was declined with a stated bound. Those revisions landed as `a5e0985` and `d5f0768` under a Fable trailer because I committed them. A trailer-based method credits the reviewed party with the reviewer's work. Reviewer contributions were a large part of this project's value and the method cannot see them.

**3. The Fable-tagged commits are composite work.** In my session I dispatched 49 subagents: 41 on Sonnet, 2 on Haiku, 2 on Opus, 4 on Fable. The implementers for the after-tax foundations plan and the tax overlay plan were Sonnet, with two Haiku tasks; the per-task reviewers were Sonnet, with two Opus reviews of the overlay; only the whole-branch reviews ran on Fable. So the code in roughly twenty Fable-tagged commits was typed by Sonnet or Haiku from my briefs, reviewed by Sonnet or Opus, and adjudicated by me. The design, the plans, the rulings, the reviews, and the accountability are mine. Most of the keystrokes are not. The note's "Fable code quality 9.0" is really a rating of Fable-directed Sonnet code under two-stage review. I do not know the dispatch pattern of the morning Opus session, which likely used the same skill, so the same caveat may apply there.

What the note gets right, verified: 65 commits; 39 Fable, 21 Opus 5 plus one Opus 5 (1M context), 4 without trailer; `a3252b2` touches 20 files at +1,460 / −342 and adds a 110-line replay reconciler.

## My own rating: 9.3 is generous

I would put myself at 8.8 to 9.0, and I would not place myself above either gpt model with confidence. The reasons, in order of weight:

- **Five correctness errors in tax accounting I designed, planned with hand-computed fixtures, and had reviewed twice per task were found by gpt-5.6.** Carryovers were not netted across characters, partial wash matches adjusted whole lots, FIFO sorted by tacked date, dividend qualification was not per disposed portion, and the 121-day window was off by one. In a repository whose stated purpose is not fooling yourself, that is the heaviest item on my ledger. The note credits the finder and does not debit me proportionally.
- **"Self-correction 9.5" overstates it.** Those five fixes were external correction that I then acknowledged. My genuine self-corrections were the hand-check record and the adjustment-factor jitter, and the note is right that widening a tolerance to 1e-5 after real data tripped an over-sell is the kind of move this repository exists to scrutinize, even though the cause was Yahoo's seven-digit adjusted closes rather than a modelling error.
- **Plan quality was uneven.** Test-count arithmetic was wrong in several tasks, implementers found about six plan defects, and one design flaw that would have made lot counts grow exponentially was caught only at review of the overlay task.
- **Three consecutive corrections to the hand-check record in forty minutes** is churn, as the note says.

What I would keep on the credit side: the two BA-001 reviews with written pre-commitments and their check against the outcome; the recommendation to record Inconclusive and leave the sealed period unrevealed rather than tune; the design revised twice under external review; the pushback on the first BA-002 draft's governance weight, the gate special case, and the unsourced calendar, all of which gpt-6 then addressed; and the whole-branch review handed to another agent instead of self-fixed.

## The gpt ratings: both are underrated

**gpt-5.6.** The GLM note already calls its correction commit the most under-appreciated in the repo, then scores the model 8.4 because its commit messages are thin. I would weigh it the other way. That commit found five real errors in tax accounting that two-stage review had passed, added an independent replay reconciler, and backed both with about 600 lines of adversarial tests, all of which held up under my own reviewer's in-memory replay of the archived runs. Before that, its two design reviews improved the after-tax specification in ways I adopted. In a repository whose purpose is not fooling yourself, the model that catches another model's errors did the most valuable work of the day, and trailers show almost none of it. Thin commit messages are a real habit worth naming, but a small one next to that.

**gpt-6.** The GLM note judged it from one sampled file and the passing suite. I have more evidence. Three scoped reviewers read its entire layer at `fd729f4`:

- The BA-002 candidate, evidence chain, and calendar were judged mergeable as-is, with no critical finding and one important one (a mis-drafted contract could label revealed data as seen; the journal still protects the data). Fourteen deliberate mutations were each caught by a named test.
- The governance plumbing had no critical finding and four important ones: an unenforced journal-location convention, an undocumented one-reveal-per-family consequence, attempt ids never printed, and stale documentation. Every lock and crash path traced was correct.
- Its calendar work resolved my earlier blocker properly: hand-encoded rules, five exceptional closures that match my independent list, a pinned third-party cross-check, primary sources of which I verified two live, and a date-only SPY comparison that matched exactly when I ran it on the seen window.

The debits are real but smaller than the note's scores imply. The governance layer is heavier than the lab's principle warrants, and the first draft was heavier still, with a hand-authored approval file and a strategy-id special case in the gate; both were fixed after review. Reviewer C estimated 60 to 80 lines of pure ceremony remain. The single 13,000-line commit is a process weakness, but the holder gave that model one uninterrupted window while my session ran a skill that enforces one commit per task. Commit granularity here measures the harness, not the model. I would drop commit-message and commit-hygiene scores from any cross-model comparison, or weight them at a fraction.

My numbers: gpt-5.6 at 9.0 to 9.2, for the corrections and the reviews; gpt-6 at 8.8 to 9.0, for a 13,000-line construction that three full-layer reviews found free of critical defects, less the governance weight.


## What I would change in the table

| Model | GLM overall | My view | Basis |
| --- | --- | --- | --- |
| Fable 5.1 | 9.3 | 8.8 to 9.0 | five externally found tax errors; plan churn; composite authorship |
| gpt-6 | 8.3 | 8.8 to 9.0 | three full-layer reviews, no critical findings; governance heavier than needed; process score is a harness artifact |
| gpt-5.6 | 8.4 | 9.0 to 9.2 | found five errors in my tax code and added the reconciler; two design reviews invisible to trailers; thin commit messages |

Caveats the GLM note stated and I repeat: one day, one harness, categorically different jobs, an AI rating AIs, and in my case a party rating itself. The relative reading I would defend is narrower than the note's: gpt-5.6, gpt-6 and Fable are within noise of one another on the work each was given, and the ranking among them depends mostly on how much weight commit granularity and externally found errors are given. Weight the errors and gpt-5.6 leads; weight the commit form and Fable leads.

## Observation for the holder

At the time of writing, the working tree carries another agent's uncommitted response to my whole-branch review: 36 modified files and 10 new ones, including a capital-loss sensitivity module, a research-family module, boundary tests, and a review-fixes record. I did not read or touch that work. It should be reviewed as a unit before the branch is merged, and the review should check that the loss-sensitivity path stays off by default and out of BA-002 eligibility, as its own decision record says.
