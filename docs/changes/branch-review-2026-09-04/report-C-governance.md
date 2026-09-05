# Report C — Research governance plumbing and integration (layer 3)

Verdict: With fixes. Critical 0 / Important 4 / Minor 10.

Branch `after-tax-overlay`, range `7cbe449..fd729f4` (HEAD verified = fd729f4, working tree clean apart from untracked PNGs). Read-only review; no data dated 2022-01-01 or later was evaluated. Probes ran only on fictional temp files (`scratchpad/branch-review/probe_governance.py`).

## Coverage

Read in full at head: research_access.py, research_state.py, research_freeze.py, research_commands.py, research_contract.py, demo.py, evaluation.py, profiles.py, data/loader.py, data/csv_loader.py, data/market.py, data/calendar.py, cli.py, config.py, report.py, sweep.py, ba002_artifacts.py, tax/policy.py, data/distributions.py (loader section), README, pyproject.toml, both BA-002 change records, docs/strategies/README.md, and the tests test_research_*.py, test_freeze_binding.py, test_execution_identity.py, test_ba002_safety_integration.py, test_repair_artifacts.py, plus the diffs of test_cli.py, test_csv_loader.py, test_gates.py, test_hardening.py, test_seal_identity.py, test_report.py, test_config.py, test_classify.py, test_quality_wiring.py, test_sweep.py. Not reviewed: tools/build_nyse_calendar.py, criteria_ba002.py, period_evidence.py, archived_config.py, tax package internals (other reviewers' layers).

Targeted tests run: 136 passed, 49 subtests, 5.3 s.

## Q1. Silent failures and crash paths

Nothing is swallowed; POSIX locks are released on every path; a crash cannot resurrect a consumed reveal within one journal file; interrupted runs are recoverable by an identical retry with clear messages.

- RunJournal._locked (research_state.py:175-191): `<journal>.lock`, blocking LOCK_EX, LOCK_UN in finally, closed by `with`. Writes are temp + fsync + os.replace + dir fsync (_durable_write, 138-155).
- AccessAttempt.start_access (255-281): family lock LOCK_EX|LOCK_NB; contention becomes a journaled `refused` event and ResearchAccessError; every exception path calls _release().
- open_run (research_access.py:282-299): `except BaseException` → finish(error) → re-raise; else → finish(). prepare_run has no statement after begin(), so no orphaned attempt.
- Crash states: `attempted` only → ignored; `access_started` without completion → reveal preserved, identical retry accepted as rerun (real spawn + os._exit test); partial archive without manifest.json → identical rerun re-verifies bytes and writes the manifest; changed-code rerun lands in a new dir and leaves the orphan (write-once).
- Reveal is recorded at access_started (line 290) before load_market_data (292). The only reuse path is a second journal file (Important #1).
- Minor: a body exception inside _locked is re-wrapped as "run journal cannot be read or durably written: 'not-in-journal'" (probe P1) — wrong diagnosis, not silent.

## Q2. BA-001 compatibility

- prepare_run for ba_001_development.toml / ba_001_validation.toml (csv, end < 2022, no [research]): check_admission → legacy review gates; research_context → requires_managed_run False → None; RunContext(None, baseline); not managed → inputs=None, attempt=None. open_run skips start_access; _load_market_data → load_csv_market_data(end=evaluation.end) → .through(evaluation.end) → quality. No freeze/calendar/journal path is read.
- Identity: code_fingerprint scope unchanged (rglob("*.py") at base and head). Config hashing and run/sweep id formulas unchanged. data.fingerprint() unchanged: filtering at parse then .through(end) yields the same bars. Re-running BA-001 dev/val gives content-identical manifests except code_sha256 (and schema 6). Archived sweeps 4b9d1479…/f0a36ea7… (schema 5) remain classifiable.
- Local data note (not the branch): both checked-in BA-001 configs declare yahoo-adjusted-v1+dgs3mo-v1; data/current now points at the 20260904T192633Z snapshot recording yahoo-adjusted-v2+dgs3mo-v1, so they fail the pre-existing methodology check unless pointed at data/snapshots/20260904T153009Z.
- A future BA-001 sealed run requires: [research] (NYSE calendar, freeze path, journal path); `research prepare CONFIG --charter docs/strategies/BA-001.md`; `research confirm`; both review files; `--unseal REASON` (doubles as reveal); backtest.end = latest shared session; any code change before the run means a new freeze at a new path. README:251-259 says this in prose; no BA-001 example; configs/ba_001_real_csv.example.toml has no [research].

## Q3. Read-once input capture

- load_csv_market_data is literally load_csv_market_data_bytes(prices.read_bytes(), cash.read_bytes(), end=end): plain and captured paths cannot diverge. Date filter precedes float() in both and in load_distributions_bytes.
- _latest_shared_csv_date reads date/symbol of all rows; only reached for "dataset"-ended evidence periods; only a date can reach a message.
- Leak edge (Minor): csv_loader.py:40-54 puts date.fromisoformat inside the same try as the float parse, so a protected row with a malformed date is echoed in full including tr_open/tr_close (probe P2). Same shape in distributions.py:216-224.

## Q4. Freeze / confirm semantics

- confirm_research_freeze rebuilds the draft from current config, calendar, policy, periods, code and input bytes and compares the full identity hash before confirm_freeze, which checks the user-supplied hash again. Replay against a different config, calendar, code or inputs is refused (tests named in Q7).
- Identity-only draft in freeze.json + confirmation in provenance is implemented exactly (archival_freeze research_freeze.py:166-174; append_provenance report.py:195-201; external confirmed freeze required by load_ba002_evidence ba002_artifacts.py:155-161; test_demo_confirmation_does_not_change_existing_run_artifacts pins byte-stability).
- `research show` prints path, status, identity hash and json_text(identity): no observations, no input paths.

## Q5. Weight versus purpose

Added governance code: research_access.py 306, research_state.py 300, research_freeze.py 214, research_commands.py 106, demo.py 159, ~120 lines in loaders/cli/report/config, ~1,300 lines of tests.

Earn their keep: journal event stream + sequence validation + durable writes; draft/confirm with recomputation; date-before-float filtering; read-once capture; manifest-last publication with checksums; execution-identity verify() at two boundaries.

Ceremony (advisory):
- evaluator_sha256 as a separate identity: evaluator files are inside the package hash, so it can never produce a refusal code_sha256 does not. ~35-45 lines.
- Duplicate verify() calls (research_access.py:288/291/293, loader.py:83/85, cli.py:98). ~5 lines.
- Dead loader branch loader.py:121-132 (unreachable for csv after parse-time filtering). ~12 lines.
- Format strictness: _unique_object, Z-suffix timestamp check, _legacy_contract overlap check for a one-period contract. ~20 lines.
- Optional, loses one test-backed property: non-blocking family lock + refused event. ~25 lines.

Total removable without losing evidence: ~60-80 lines; ~100 with the family lock.

## Q6. Docs

README CLI examples all match build_parser. Stale/incomplete: README:109-113 SPY comparison "remains deferred"; docs/data/nyse-calendar.md:99-101 "not performed"; docs/strategies/BA-002.md:286; workflow record :68; both records "uncommitted" (:4,111; implementation record :162). README:126 states the same-journal rule with no enforcement/location convention; README:153 references PRIOR_ATTEMPT_ID with no source; README silent on committing research/ (not gitignored). docs/strategies/README.md:10 BA-002 row is honest.

## Q7. Can the tests fail?

- Lock contention: test_research_state.py::test_concurrent_family_access_is_refused_and_journaled (real flock); cross-process release via test_hard_crash_leaves_reveal_and_releases_lock_for_exact_retry (real spawn + os._exit).
- Crash retry: the hard-crash test; test_failure_before_access_does_not_reveal_but_failure_after_access_does; test_corrupt_lifecycle_refuses_instead_of_replenishing_holdout.
- Stale confirmation: test_research_commands.py::test_confirmation_refuses_configuration_changed_since_preparation, …refuses_other_reviewed_identity_changes[calendar|window|code], …requires_the_exact_full_displayed_hash.
- First-reveal refusal: test_first_holdout_requires_reason_and_refusal_is_an_event, test_changed_candidate_cannot_reset_family_even_with_reveal_reason, test_changed_overlapping_window_cannot_claim_a_fresh_reveal, test_synthetic_access_does_not_reveal_historical_coverage; LoaderAccessTests::test_protected_exploratory_alias_requires_a_freeze_before_parsing and test_legacy_unseal_reason_does_not_replace_a_family_freeze.
- Input replacement: test_ba002_safety_integration.py; LoaderAccessTests::test_raw_access_identity_changes_with_future_bytes_but_observations_stay_truncated.
- Mocking notes: LoaderAccessTests._mock_run uses a Mock attempt; test_execution_identity patches fingerprints (necessary); test_hardening.py now patches prepare_run for three ≥2022 fixtures. Gaps: no test drives cli.run_sweep_command on a managed csv BA-002 config with real journal through classify --freeze; nothing tests the two-journal-paths scenario.

## Strengths

- Lock and journal discipline correct on every traced path; reveal recorded before parsing; refused events rather than silent skips.
- Read-once capture has no parallel code path; date filter precedes numeric parsing everywhere.
- Confirm recomputes the whole draft; archived freeze is identity-only with confirmation in provenance, pinned by a byte-stability test.
- BA-001 dev/val untouched in behaviour and identity; archived schema-5 sweeps classifiable.
- Recovery is procedural and documented; refusals name the remedy.
- Tests are real where it matters (real flock, real subprocess crash, real file mutations).

## Issues

### Critical
None found.

### Important
1. Family history keyed by a free path; `confirm` initializes a second empty journal. config.py:118-128, research_freeze.py:190-192, research_state.py:162-173; README:126 states the rule without enforcement. Fix: derive the journal location from the hard-coded family and drop journal_path, or refuse to create a journal when one already exists for the family; print the journal path in run output.
2. Undocumented mutual exclusion of BA-001 sealed and BA-002 holdout. research_state.py:244-245 refuses any non-identical protected overlap in the family; repair (240-242) keeps candidate_id, so no cross-candidate path. Fix: state it in README:251-259 and BA-002.md "Unopened retrospective holdout".
3. Attempt ids never surfaced. research_state.py:205; cli.py:129-194; README:153. Fix: print `Journal attempt: <id>`, name overlapping ids in refusals, and/or add `research journal JOURNAL`.
4. Stale docs. README:109-113; docs/data/nyse-calendar.md:99-101; docs/strategies/BA-002.md:286; workflow record :4, :68, :111; implementation record :162; README silent on tracking research/. Fix: record the SPY check (window, session count, result), update status lines, add one sentence on research/.

### Minor
5. csv_loader.py:40-54, distributions.py:216-224: malformed protected-row date echoes price/dividend columns (probe P2). Parse the date before the try or report only row number and date.
6. loader.py:119-132: post-truncation check unreachable for csv. Remove or annotate.
7. research_state.py:188-191: _locked re-wraps body exceptions with a misleading message (probe P1). Narrow the except.
8. research_commands.py:33-34: end = "dataset" for BA-002 gives a bare "Invalid isoformat string". Say BA-002 periods need fixed dates.
9. research_commands.py:88: existing freeze reports "refusing to overwrite changed experiment artifact". Use a freeze-specific message pointing to a new freeze_path.
10. research_access.py:288-293, loader.py:83/85, cli.py:98: 6-8 full-package hashes per run; two suffice.
11. ba002_artifacts.py:109: .{sweep_id}.lock files accumulate under experiments/BA-002/sweeps/; relocate.
12. evaluator_sha256 implied by code_sha256; retire later. Advisory.
13. README:251-259 and configs/ba_001_real_csv.example.toml: no BA-001 [research]/prepare example.
14. Local state: BA-001 configs declare methodology v1 while data/current is v2.

## Recommendations
1. Decide the journal-location question (Important #1) before the first historical run.
2. Write the mutual-exclusion paragraph (Important #2) while no reveal has happened.
3. Surface attempt ids (Important #3).
4. Apply the doc corrections (Important #4) with the SPY check record.
5. Optional Q5 cleanup (~60-80 lines).
6. Add an end-to-end test: cli.run_sweep_command on a managed fictional csv BA-002 config with confirmed freeze and real journal, then run_classify(..., freeze_path=…).

## Assessment
Ready to merge: With fixes. Mechanisms are correct on every crash and lock path traced; BA-001 preserved except the inevitable code hash; read-once and date-first filtering hold; confirm/freeze semantics match the record. No correctness bug can reuse a consumed reveal within a journal or lose evidence. The Important items are a convention to enforce or state (journal path), an unstated research consequence (one reveal per family), an ergonomics gap on the only recovery path (attempt ids), and stale docs.
