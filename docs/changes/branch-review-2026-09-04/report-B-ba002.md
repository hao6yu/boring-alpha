# Review B — BA-002 candidate, evidence/archive layer, NYSE calendar

Verdict: Ready to merge (Yes) for this layer. Critical 0 · Important 1 · Minor 7.

Branch `after-tax-overlay`, range `7cbe449..fd729f4`, read-only review of the head.

## Coverage

Read in full (head): signals/trend.py, profiles.py, criteria_ba002.py, period_evidence.py, ba002_artifacts.py, archived_config.py, research_contract.py, data/calendar.py, research_access.py, backtest/engine.py (untouched; read for anchoring/execution semantics), data/market.py, tools/build_nyse_calendar.py, data/calendars/*.json, docs/strategies/BA-002.md, docs/superpowers/plans/2026-09-04-ba-002.md, both BA-002 change records, docs/data/nyse-calendar.md. Targeted: domain.py, signals/__init__.py, data/loader.py, data/csv_loader.py, config.py, report.py, sweep.py 93–365 and 484–545, cli.py (run_classify, banners), tax/reconstruct.py helpers, research_freeze.py, research_state.py (protection predicate), data/quality.py, portfolio/account.py::plan_rebalance.

Tests read in full: test_signal_ba002.py, test_criteria_ba002.py, test_calendar.py, test_nyse_calendar.py, test_archived_config.py, test_ba002_pairing.py, test_ba002_integration.py, test_ba002_safety_integration.py, test_freeze_binding.py, test_execution_identity.py, test_repair_artifacts.py, test_research_access.py, test_research_contract.py.

Not reviewed: research_commands.py, research_state.py body, tax package, cli.py beyond classify/banners, and the remaining test files.

Commands run: build_nyse_calendar.py --check (digest 6bc0cf5a… reproduced); per-year dump of regular_closures/early_closes; five in-scope test files against a scratch copy (118 passed, 33 subtests); fourteen deliberate mutations applied to the scratch copy and reverted. Nothing in the checkout was modified; no market data was read; no run touched dates ≥ 2022-01-01.

## Strengths

1. The signal is the charter, line for line. MultiHorizonTrend.snapshot (trend.py:95–131): per horizon, its own anchor, its own cash hurdle, strict > vote, sleeve_weight/len(horizons) per true vote. Targets are absolute weights — inactive votes leave capital in cash. Readiness is the separate warmup_months anchor; validate_horizon_inputs forbids warmup < max(horizons). Every row and the 12-month reference pass warmup_months=15.
2. No look-ahead. Engine calls snapshot(data, day) only at month-ends after that day's close (engine.py:185–188), executes at next open, never treats the dataset's last date as a month-end. Signal reads only bar(as_of).close, bar(anchor).close, and the cash-index ratio.
3. The benchmark is the charter's benchmark. gating_benchmark(cfg, 15) → TargetExposureAllocation(symbols, 15, 0.125, 0.6, "annual"): 7.5% per ETF, same readiness, hold=True except December. The double-cost benchmark runs at 20 bps.
4. Criteria exact, Decimal from serialized values. number() (period_evidence.py:39–49) refuses bools/NaN/inf and builds Decimal(str(value)); margin = worst_cagr − best_cagr; primary >= 0.005, stress > 0, drawdown <= 0.20 and <= benchmark. Result type is ResearchEligibility, never Verdict.ADVANCE.
5. No pooling, no account reuse. classify requires one development and one validation evidence, both passing. Each row's benchmark account is benchmark:<row>; run_sweep runs run_scenarios separately for all ten gating accounts plus four diagnostics. test_ba002_pairing.py calibrates a 20-bps strategy between the two real benchmark maxima so substitution flips the verdict.
6. Evidence hygiene holds. CSV rows are date-filtered before any float(); _load_market_data bounds end then through() truncates again; distributions are date-filtered and truncated to data.dates[-1]; archived inputs and fingerprints come from the truncated dataset. verification flags are earned: validate_ba002_inputs runs first; validate_replay + validate_output_sessions run on every tax account before account_reconciliation is set.
7. Archive consumption trusts nothing it can recompute. load_ba002_evidence verifies every checksum, re-parses the embedded config against the contract without touching original paths, reloads market data and checks its fingerprint, reloads distributions and calendar and checks digests, requires an externally confirmed freeze for historical contracts, refuses repaired/revealed runs, replays every account and recomputes drawdown. Saved passed flags are never read.
8. Calendar generator rules check out for 2006–2026. Year counts (251/251/253/252/252/252/250/252/252/252/252/251/251/252/253/252/251/250/252/250) match for every year the reviewer could recall independently.
9. Tests discriminate. All fourteen mutations were caught.

## Issues

### Critical
None found.

### Important

I-1. Contract validator and preflight do not bind "seen" periods to the family's protected boundary. research_contract.py:217–237 accepts any ordered, disjoint development/validation/sealed triple given the right status strings; research_access.py:154–191 (research_context) never consults PROTECTED_START. The journal (research_state.py:232) protects on identity.end >= 2022-01-01 regardless of labels, so data protection holds. But a typo such as validation 2018-01-01..2022-12-31 would be accepted by prepare/confirm, the run would consume the family's one reveal, and the archive would carry evidence_status "seen" and print SEEN RESEARCH HISTORY — a mislabel of revealed data guarded only by human reading of the draft.
Fix: in research_context, refuse any status == "seen" period with end >= PROTECTED_START and require periods["sealed"]["start"] == PROTECTED_START for historical contracts. Add a test that such a contract is refused at research prepare.

### Minor

M-1. Classification bound to the whole-package code hash — cost, not safety. period_evidence.py:199–200, :285–286 require code_sha256 == code_fingerprint(). Any later commit touching any module makes classify refuse every earlier BA-002 archive unless run from the frozen checkout. Fail-closed and documented. Alternative: bind classify to evaluator_sha256 plus archive-to-archive code_sha256 equality.
M-2. Per-horizon anchors computed but never compared with archived decisions. SessionCalendar.requirements builds anchors (calendar.py:186–189); validate_inputs uses only required_sessions; load_ba002_evidence never reads *_decisions.json. Compare archived HorizonEvidence.anchor_date with req.anchors, or drop the surface.
M-3. After-tax CAGRs not recomputed at classify; identity_checks are saved flags (period_evidence.py:129–145). aftertax is the independent re-score but is not part of classify. Clarify the docstring at ba002_artifacts.py:126; optionally add --rescore.
M-4. Calendar and charter prose still say the SPY check is deferred. docs/data/nyse-calendar.md, data/calendars/nyse-provenance-v1.json ("deferred; not performed"), BA-002.md §7. data/ is write-once and test_nyse_calendar.py:118 pins the literal status sentence, so updating requires nyse-provenance-v2.json plus a test edit. Pin checksums and the calendar digest, not the narrative.
M-5. Weak assertion. test_criteria_ba002.py:98 asserts "50" in detail; the detail always contains "at least 50 bps/year", so it cannot fail.
M-6. Cosmetic. BA002Profile.grid hard-codes "20/10 bps" in descriptions while cost_bps is derived (profiles.py:204–206); MultiHorizonTrend.lookback_months = warmup_months (trend.py:91) could be mistaken for a horizon.
M-7. Ford citation points at the aggregate rulebook PDF — already flagged.

## Calendar verification detail

Method: ran regular_closures/early_closes for 2006–2026 and compared every date with the reviewer's own knowledge (training knowledge, not a live source). Verified (all match): New Year's observed Monday when Jan 1 is Sunday (2006, 2012, 2017, 2023) and not observed Friday when Saturday (2011, 2022). MLK, Presidents', Memorial, Labor, Thanksgiving correct every year. All 21 Good Fridays correct. Independence Day / Christmas nearest-weekday correct. Juneteenth from 2022 only. Exceptional closures 2007-01-02, 2012-10-29/30, 2018-12-05, 2025-01-09 correct and believed complete (2015-07-08 halt and March-2020 circuit breakers were not full-day closures; tests pin both as sessions). 5,197 sessions. The 44 half-days match recollection for 2008–2025; not certain about the 1 p.m. closes on 2006-07-03 and 2007-07-03.
Could not verify: the exchange_calendars==4.13 comparison, most cited URLs, and whether any unscheduled closure the reviewer is unaware of occurred.
Is SessionCalendar.requirements duplicate of the quality layer? No. quality.py flags gaps only above max_calendar_gap_days = 5; neither it nor require_complete_calendar detects a single session missing from every series, an extra non-session row, or an inadequate warmup start.

## Mutation table (scratch copy, all caught, all reverted)

| # | Mutation | Caught by |
|---|---|---|
| M1 | tie votes asset (>=) | test_an_exact_tie_votes_cash |
| M2 | denominator fixed at 3 | test_pair_uses_two_votes_not_three |
| M3 | readiness uses max(horizons) | test_pair_without_fifteen_vote_still_requires_fifteen_month_history |
| M4 | cash hurdle uses last dataset date | test_future_prices_and_cash_cannot_change_earlier_votes |
| M5 | primary > not >= | test_exact_50_bps_passes… + 4 others |
| M6 | stress >= 0 | test_one_zero_margin_stress_fails[×4] |
| M7 | relative drawdown strict < | 7 tests incl. boundary fixture |
| M8 | absolute cap 0.25 | test_drawdown_absolute_and_relative_gates_are_separate[-0.21--0.3] |
| M9 | New Year Sat→Fri | 5 calendar tests |
| M10 | Juneteenth from 2021 | 5 calendar tests |
| M11 | drop Carter closure | 6 calendar tests |
| M12 | calendar warmup uses max(horizons) | test_common_readiness_and_each_anchor_use_expected_sessions |
| M13 | evidence accepts missing scenario | test_incomplete_or_incompatible_evidence_refuses[missing_scenario] |
| M14 | margin = min paired difference | test_independent_extrema_fail_although_every_matched_pair_beats_50_bps |

## Design judgment (for the holder to decide consciously; no redesign recommended)

1. Turnover is not only signal changes. plan_rebalance trades any deviation above 1e-10, so every non-hold month-end rebalances drift in every held sleeve, realizing gains monthly; the ensemble adds three flip opportunities per sleeve per month. Given BA-001 failed C2–C5 on 2018–2021 for turnover/whipsaw and the gate is worst-strategy vs best-benchmark, "no bands" is a structural headwind. A later bands variant is a second draw on the same seen data.
2. The relative-drawdown gate against a 60% static book, pre-tax, is the likeliest failure mode in the 2018–2021 window (Q4 2018, Feb–Mar 2020). A rule that can be 100% invested entering a fast decline will usually draw down more than a 60% holder. A failure there says little about the trend logic.
3. Independent worst/best across eight scenarios penalizes the higher-turnover account asymmetrically. Deliberate; read a near miss as "lost on dispersion" vs "lost on level".
4. Leave-one-out pairs are different step functions (6.25% per flip), not "the primary minus one vote".

## Recommendations
1. Add the protected-boundary check (I-1) with a test before the first historical research prepare.
2. Decide consciously on whole-package code-hash binding (M-1); if kept, document that seen sweeps and classify must run from one code revision.
3. Cross-check archived anchor_date against req.anchors, or remove the unused surface (M-2).
4. Clarify the loader docstring on recomputed vs. read quantities; consider --rescore (M-3).
5. Publish nyse-provenance-v2.json rather than editing v1 when recording the SPY match (M-4).
6. Tighten test_exact_50_bps… (M-5).

## Assessment
Ready to merge: Yes, for this layer. The code implements the charter exactly; no look-ahead, pooling, account reuse, or post-2021 parsing during a seen run; the evidence chain binds behaviour, windows, policy, calendar, contract and code; the calendar's rules and special closures check out for all 21 years; fourteen deliberate regressions were each caught. I-1 is a labelling gap in a path the journal still protects, fixable in a few lines, and should land before real BA-002 dates are registered.
