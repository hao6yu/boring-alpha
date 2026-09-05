# Whole-branch review — `after-tax-overlay` against `main`

Date: 2026-09-04
Range: `7cbe449` (merge-base with `main`) .. `fd729f4` (branch head). 15 commits, 81 files, about 18,000 insertions.
Status: **review only. Nothing was fixed, and the branch was not merged.** The holder asked for the findings to be documented for a separate agent to act on.

## Verdict

No critical defect was found in any layer. Every reviewer judged the branch mergeable once the items below are addressed or consciously deferred.

| Layer | Reviewer verdict | Critical | Important | Minor |
| --- | --- | --- | --- | --- |
| A. After-tax overlay | With fixes (documentation) | 0 | 1 | 10 |
| B. BA-002 candidate, evidence, calendar | Yes | 0 | 1 | 7 |
| C. Research governance plumbing | With fixes | 0 | 4 | 10 |

Full reports: [report-A-tax.md](branch-review-2026-09-04/report-A-tax.md), [report-B-ba002.md](branch-review-2026-09-04/report-B-ba002.md), [report-C-governance.md](branch-review-2026-09-04/report-C-governance.md). Each names the files read in full, the files not covered, the tests run, and the mutation probes performed.

## How the review was done

Three scoped reviewers ran in parallel on the most capable available model, read-only, with these rules: no writes under `experiments/` or `data/`, no evaluation of any data dated 2022-01-01 or later, no `--unseal` or `--reveal`, no fetcher, no subagents. Layer A replayed the overlay in memory on the archived BA-001 runs and reproduced the archived after-tax CAGRs to below 1e-12. Layer B applied fourteen deliberate mutations to a scratch copy of the source and confirmed a named test caught each one. Layer C traced every lock, journal, and crash path and ran the research and loader test files.

Controller verification on `fd729f4` before dispatch:

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 806 passed, 140 subtests, 115 s |
| `git diff --check 7cbe449..fd729f4` | clean |
| `tools/build_nyse_calendar.py --check` | reproduces digest `6bc0cf5a…` |
| SPY date-only cross-check, 2006-02-28..2021-12-31 | 3,990 expected, 3,990 observed, none missing, extra, or duplicated |
| ICE press release for the 2018-12-05 closure | fetched; names the date |
| SEC Release 34-70099 (Superstorm Sandy), page 5 | fetched; states all U.S. equities markets closed 2012-10-29 and 2012-10-30 |

The SPY check reads only the date and symbol columns and was restricted to the seen window. It wrote nothing. The holdout portion of the calendar was not compared against any market file.

## Decisions for the holder

These are research-policy choices, not defects. They should be settled before any historical BA-002 command.

1. **Model the $3,000 ordinary-income capital-loss deduction, or state its exclusion.** U.S. individuals deduct up to $3,000 of net capital loss against ordinary income each year. The overlay never does, and the omission is listed only in the corrections record's "Remaining scope". Reviewer A bounded it from the archived BA-001 `by_year` records under `hifo-deferral-base` (upper bound: min($3,000, net loss) × 35% per loss year, added to terminal wealth). Development window: strategy about +7 bps/yr, exposure-matched about +10, benchmark about +12. Validation window: strategy about +60 bps/yr, comparators 0. The lower bound is roughly 43% of those. These are reviewer estimates and must be recomputed before publication. The term is fixed in dollars, so it scales inversely with account size and breaks the overlay's scale-free convention. BA-002's primary gate is 50 bps/yr, so a 60 bps unmodelled term can decide a near miss in either direction. Recommendation from the controller and reviewer A: model it, declaring `initial_cash` as the account size in the BA-002 charter. The alternative is to state the exclusion and its direction in the charter and in `KNOWN_OMISSIONS`.
2. **One reveal per family.** The journal refuses any second protected run in the BA-TREND family that is not an identical rerun (`research_state.py:232-245`). Revealing BA-001's sealed period would permanently foreclose BA-002's holdout, and the reverse. This matches the earlier decision to keep BA-001's sealed period for a successor, but it is undocumented. Confirm the policy and record it in the README and in BA-002.md's holdout section.
3. **Journal location.** The family journal lives at whatever `journal_path` the config names, and `research confirm` initializes a new empty journal at a new path (`config.py:118-128`, `research_freeze.py:190-192`, `research_state.py:162-173`). A mistyped path yields a fresh family with a reusable first reveal. Options: derive the path from the hard-coded family and drop the config field, or refuse to create a journal when one already exists for the family, or keep the field and document the convention plainly while printing the path at run start. The controller would take the first option; the third is acceptable under the lab's non-cryptographic principle if the README says it plainly.

## Important findings

### A-1. $3,000 capital-loss offset omitted and unstated where readers look
`src/boring_alpha/tax/overlay.py:47-55` (`KNOWN_OMISSIONS`), `src/boring_alpha/tax/yearend.py:179-182`, `docs/notes/2026-09-04-BA-001-after-tax.md`. Add the omission, its bound, and its account-size dependence to `KNOWN_OMISSIONS` and to the BA-001 note. Then take decision 1 above for BA-002. The BA-001 direction (validation about −168 bps/yr) does not change.

### B-1. Seen periods are not bound to the protected boundary
`src/boring_alpha/research_contract.py:217-237` accepts any ordered, disjoint development/validation/sealed triple with the right status strings; `research_context` in `src/boring_alpha/research_access.py:154-191` never consults `PROTECTED_START`. The journal still protects on the actual end date, so no data leaks. But a mis-drafted contract such as validation 2018-01-01..2022-12-31 would pass `prepare` and `confirm`, consume the family's one reveal, and produce an archive stamped `seen` with the "SEEN RESEARCH HISTORY" banner. Fix: refuse any `seen` period whose end is on or after `PROTECTED_START`, and require the sealed period to start at `PROTECTED_START` for historical contracts. Add a test that such a contract is refused at `research prepare`.

### C-1. Journal keyed by a free path
See decision 3. Whatever is chosen, print the journal path in run output.

### C-2. Mutual exclusion of BA-001 sealed and BA-002 holdout is undocumented
See decision 2. `research_state.py:244-245` refuses overlapping protected coverage; repair at 240-242 keeps the candidate id, so there is no cross-candidate path. Document in README (around lines 251-259) and in BA-002.md.

### C-3. Attempt ids are never surfaced
`research_state.py:205` generates them; `cli.py:129-194` never prints them; README line 153 tells the user to pass one to `--repair-of`. Print the attempt id after each managed run, name the overlapping ids in refusals, or add a `research journal` listing command.

### C-4. Stale documentation
- README lines 109-113, `docs/data/nyse-calendar.md` lines 99-101, `docs/strategies/BA-002.md` line 286, and the workflow-simplification record line 68 say the SPY date check is deferred or not performed. It was performed on 2026-09-04 over 2006-02-28..2021-12-31 with an exact match of 3,990 sessions. Record it in the editable docs. `data/calendars/nyse-provenance-v1.json` also says "deferred; not performed" and `tests/test_nyse_calendar.py:118` pins that sentence; `data/` is write-once, so either leave v1 as a statement true at authoring time and point to the docs, or publish a `nyse-provenance-v2.json` with a test update. Do not edit v1 in place.
- Both BA-002 change records say changes remain uncommitted (workflow record lines 4 and 111; implementation record line 162). They were committed as `fd729f4`. Append a dated postscript rather than rewriting the records.
- README does not say whether the `research/` directory (journal and freeze) is committed. It should be; they are small text evidence.
- README has no BA-001 `[research]` and `research prepare` example, and `configs/ba_001_real_csv.example.toml` has no `[research]` table, although a future BA-001 sealed run now requires a confirmed freeze and the shared journal in addition to `--unseal`.
- The Ford closure (2007-01-02) cites the aggregate NYSE rulebook PDF, which the author's own record says could not be opened. The date is corroborated by the pinned third-party calendar library and by the controller's knowledge, but the citation does not support itself. Mark it as such or replace it. `data/calendars/nyse-source-facts-v1.json` is write-once; make the note in `docs/data/nyse-calendar.md`.

## Minor findings

### Layer A (tax overlay)
1. A partially sold lot's own remainder is treated as its wash-sale replacement (`lots.py:389-392`; pinned by `tests/test_tax_lots.py:357`). Reviewer A believes IRS guidance excludes shares retained from the same purchase, citing Revenue Ruling 56-602 from memory; that citation is unverified. Measured effect on after-tax CAGR is at most +0.003 bps/yr. Confirm the rule with the holder before changing anything.
2. DBC sales are characterised 60/40 under the `mtm_60_40` scenario rather than by holding period (`overlay.py:230-240`, `yearend.py:76-79`). Section 1256 applies to the pool's futures; a unit-holder's sale is capital gain by holding period. The whole mtm axis moves results by 1.2 to 1.3 bps/yr. Either set `mark_to_market=False` for sale records or document the choice in spec §4.5 and `KNOWN_OMISSIONS`.
3. `by_year.wash_disallowed` is NAV-scaled while `totals.wash_sale_disallowed_total` is unscaled (`overlay.py:258` vs `332-335`). Exclude reporting fields from `Amounts.scaled` or label units in both places.
4. The code fingerprint covers the whole package (`report.py:101-107`), so any unrelated source change yields a new tax identity and a new output file. Optional: an overlay-scoped hash, or a sentence in spec §7.
5. The over-sell guard is an absolute 1e-9 shares (`lots.py:21`, `229`). Harmless at lab scale; make it relative or document it.
6. `run_aftertax` appends a provenance line on idempotent reruns (`cli.py:399-400`).
7. Untested: negative `tax_liquidation` when liquidation nets to a loss; return of capital after an mtm step-up; DBC sale character under mtm.
8. `test_the_command_prints_one_line_per_run` asserts substrings only.
9. The qualified-dividend holding period ignores the wash-sale tack (`overlay.py:222`). Conservative and deliberate; record it as a stated approximation in spec §4.5.
10. `is_long_term` uses more than 365 days, one day lenient in leap years (`yearend.py:22-25`).

### Layer B (BA-002, evidence, calendar)
1. Classification requires the archive's `code_sha256` to equal the current whole-package fingerprint (`period_evidence.py:199-200`, `285-286`). Any later commit makes `classify` refuse earlier BA-002 archives unless run from the frozen checkout. Fail-closed and documented, so a cost rather than a risk. Alternative: bind classify to the evaluator hash plus archive-to-archive code equality.
2. `SessionCalendar.requirements` computes per-horizon anchors (`calendar.py:186-189`) that nothing compares against archived decisions. Compare archived `HorizonEvidence.anchor_date` with them in the loader, or drop the surface.
3. After-tax CAGRs are not recomputed at classify; `identity_checks` are saved flags (`period_evidence.py:129-145`). Drawdown is recomputed. Clarify the docstring at `ba002_artifacts.py:126`; optionally add a `--rescore` path that runs `aftertax`.
4. Calendar and charter prose still say the SPY check is deferred (covered under C-4).
5. `tests/test_criteria_ba002.py:98` asserts that "50" appears in a detail string that always contains "at least 50 bps/year"; it cannot fail. Assert the computed margin text.
6. Cosmetic: `BA002Profile.grid` hard-codes "20/10 bps" in descriptions while `cost_bps` is derived (`profiles.py:204-206`); `MultiHorizonTrend.lookback_months = warmup_months` (`trend.py:91`) could be mistaken for a horizon.
7. Ford citation (covered under C-4).

Reviewer B also verified the calendar generator's rules independently for all 21 years: New Year's observed on Monday when January 1 is a Sunday and never on the preceding Friday, all Good Fridays, nearest-weekday Independence Day and Christmas, Juneteenth from 2022 only, and the five exceptional closures. Not verified from memory: the 1 p.m. closes on 2006-07-03 and 2007-07-03, and the `exchange_calendars` comparison itself.

### Layer C (governance plumbing)
1. `csv_loader.py:40-54` and `distributions.py:216-224` parse the date inside the same `try` as the numeric fields, so a protected row with a malformed date is echoed in full, including prices, in the error message. Parse the date first, or report only the row number and date. This is the one evidence-hygiene item among the minors.
2. `loader.py:119-132`: the post-truncation check is unreachable for CSV sources after parse-time filtering. Remove or annotate.
3. `research_state.py:188-191`: a body exception inside the journal lock is re-wrapped as "run journal cannot be read or durably written", which misdiagnoses it. Narrow the `except`.
4. `research_commands.py:33-34`: `end = "dataset"` for BA-002 produces a bare "Invalid isoformat string". Say that BA-002 periods need fixed dates.
5. `research_commands.py:88`: an existing freeze reports "refusing to overwrite changed experiment artifact". Use a freeze-specific message pointing to a new `freeze_path`.
6. `research_access.py:288-293`, `loader.py:83`, `85`, `cli.py:98`: six to eight full-package hashes per run; two carry all the evidence.
7. `ba002_artifacts.py:109`: `.{sweep_id}.lock` files accumulate under `experiments/BA-002/sweeps/`. Relocate.
8. `evaluator_sha256` is implied by `code_sha256` (the evaluator files are inside the package hash), so it can never refuse anything the code hash does not. Advisory; retire later.
9. No BA-001 `[research]` example (covered under C-4).
10. Local state, not a branch defect: both checked-in BA-001 configs declare methodology `yahoo-adjusted-v1+dgs3mo-v1`, while `data/current` now points at the `20260904T192633Z` snapshot recording `yahoo-adjusted-v2+dgs3mo-v1`. They fail the methodology check until pointed at `data/snapshots/20260904T153009Z` or updated.

Reviewer C's weight assessment: the journal event stream with durable writes, draft-and-confirm with recomputation, date-before-float filtering, read-once capture, manifest-last publication, and the two execution-identity checks all earn their keep. Roughly 60 to 80 lines are ceremony that could go without losing any test-backed property (items 6 and 8 above, the dead loader branch, and some format strictness). Trimming is advisory.

## Design notes for the holder (no change recommended now)

From reviewer B, on the 9/12/15 equal-vote candidate without rebalance bands:

- Turnover is not only signal changes. The account rebalances any drift above 1e-10 at every non-hold month-end, realizing gains monthly, and the ensemble adds three flip opportunities per sleeve per month. BA-001 failed C2 to C5 on 2018-2021 for turnover and whipsaw, and the gate is worst-strategy against best-benchmark, so no bands is a structural headwind. A later bands variant is a second draw on the same seen data.
- The relative-drawdown gate against a 60% static book, pre-tax, is the likeliest failure in the 2018-2021 window (Q4 2018, February to March 2020). A rule that can be fully invested entering a fast decline will usually draw down more than a 60% holder. A failure there says little about the trend logic.
- Independent worst-over-best across eight scenarios penalizes the higher-turnover account asymmetrically. Read a near miss as "lost on dispersion" versus "lost on level".
- The leave-one-out rows are different step functions (6.25% per flip), not the primary minus one vote.

## Suggested order for the fixing agent

1. Settle the three holder decisions.
2. B-1 boundary check with its test.
3. A-1 (a) and (b): `KNOWN_OMISSIONS` and the BA-001 note paragraph, with the offset bounds recomputed from the archived `by_year` records.
4. C-3 attempt-id printing; C-1 per the decision.
5. C-4 documentation updates and postscripts; C minor 1 (malformed-row echo).
6. Remaining minors as a separate, optional pass.
7. Full suite, then merge `after-tax-overlay` into `main`.

Constraints that bind the fixing agent: do not edit or delete anything under `experiments/` or `data/`; do not run any evaluation dated 2022-01-01 or later; append to change records rather than rewriting them; keep the untracked PNGs under `docs/` out of commits; do not invent sources or URLs.
