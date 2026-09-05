# BA-002 — workflow simplification and calendar follow-up

Date: 2026-09-04
Baseline: `3a3a74c`, including the uncommitted synthetic-first implementation.
This follows the holder's instruction to proceed after reviewing the initial
[implementation record](2026-09-04-ba-002-implementation.md).

## Outcome and unchanged scope

The research interface is simpler: generated draft freeze, explicit
confirmation, then an explicit run context and one family journal. Seen runs
reuse that freeze; first holdout access still needs a separate reveal reason.
No historical BA-002 run, market-price inspection/download, real confirmation
or reveal occurred. All execution tests use fictional inputs in temporary
directories. BA-001's charter, period registry, correction record, after-tax
note and archived results are unchanged. Unrelated PNGs are untouched.

The first candidate remains 9/12/15 equal votes without rebalance bands.
Bands can be a later recorded variant; they are not silently included here.
The five paired rows, annual 60%-target benchmark, eight tax scenarios,
50-bps primary margin and 20%/no-worse-than-benchmark drawdown gates are
unchanged. Implementation completion is not evidence of a trading advantage.

## The smaller operating model

- Profiles own admission policy through one gate interface. BA-001 retains
  its existing review requirements and schema-5/6 archive compatibility.
- `research prepare`, `show` and `confirm` replace hand-authored approval
  files. Preparation hashes source bytes without parsing market observations.
  The record contains the complete human charter, machine behavior, periods,
  tax policy and calendar identity, and exact code/input identities.
- Confirmation requires the full displayed identity hash and a human reason.
  It recomputes the configured proposal, so changed policy, calendar, windows,
  code or inputs cannot silently confirm a stale draft. It does not reveal data.
- Three config paths remain: calendar, freeze and journal. Related candidates
  must point at the same BA-TREND journal. No separate authorization list,
  approval-file/state pair or per-seen-run confirmation remains.
- `open_run` carries a `RunContext` and handles access, completion and failure.
  `MarketData` contains observations, not private lifecycle attributes.
- The journal records attempted/accessed/completed/failed/refused events.
  An identical frozen retry after a crash needs no manual journal editing.
  A reviewed code/evaluator repair must retain candidate, contract, window,
  policy, calendar and inputs. Its diagnostic label and repair origin survive
  exact retries; classification refuses it as new eligibility evidence.
- BA-001's existing `--unseal` reason doubles as its first reveal reason when
  a new protected invocation uses this workflow. It still needs the confirmed
  freeze and shared journal, but not a redundant second reason flag.

The retained mechanisms improve evidence or ordinary failure recovery:
independent session checks, account replay, read-once input capture, per-file
checksums, code consistency checks, manifest-last publication and a small POSIX
lock preventing simultaneous family execution. This is not security against
the computer's owner. Using a fresh journal to pretend history is unseen would
violate the procedure; the software cannot prevent its owner from doing that.

## Calendar and provenance

The checked-in [NYSE calendar and source record](../data/nyse-calendar.md)
cover 2006-01-01 through 2026-08-31: 5,197 sessions and 44 early closes.
The standard-library generator includes historical holiday conventions and
the five exceptional full-closure dates. Its full session and early-close
sets match `exchange_calendars==4.13` XNYS, checked in a temporary environment
without adding a runtime dependency. Primary-source records support the
exceptional closures; the archive contains short attributed excerpts and
transcribed facts, not complete original publications or an exhaustive audit
of every year's circulars.

An actual SPY date-only comparison remains explicitly deferred. The tool
supports a bounded comparison without interpreting or printing price values.
Do not fix a missing feed row by intersecting the expected calendar with it.
Global-equity diagnostics remain unavailable, not replaced with a new proxy.

## Review corrections in this follow-up

Review found that legacy strategy identity excluded tax/calendar settings;
the BA-001 freeze now binds those digests and checks them before journal access.
It also found that a repaired run's retry could retain the journal warning but
lose its artifact label. Both label and repair origin now persist.

Synthetic confirmation exposed the same content/provenance distinction as
the earlier manifest bug: adding confirmation metadata must not change an
otherwise identical artifact. Archives therefore store an identity-only draft
envelope in `freeze.json`; confirmation status/reason/time are appended to
invocation provenance. That archived draft is never execution permission.
Historical classification requires a matching external confirmed freeze.
The demo and review commands now share the same synthetic-generator identity,
so its unchanged draft can be confirmed from either seen-period config.

## Verification and handoff

Stable-code verification: `.venv/bin/python -m pytest -q` reported
**806 passed, 140 subtests passed in 125.95 seconds**. These are pytest
executions, not distinct declared methods. `git diff --check` is clean.
The calendar generator's `--check` reproduces the recorded canonical digest.
Targeted tests cover stale confirmations, first-reveal refusal, one-freeze
reuse across seen windows, source replacement/deletion, execution drift,
crash retries, repair restrictions/labels, immutable reruns after synthetic
confirmation, archived replay and recomputed classification. Controlled
journal mutations bypassing family overlap or permitting changed repair
inputs fail their discriminating regressions.

See the repository README for complete preparation, confirmation, run and
repair examples. No historical config is registered by this change. Before
running one, review the implementation and charter, select and retain the
exact original source snapshot, perform the permitted date-only cross-check,
then deliberately confirm the freeze. Raw-source identity is stricter than
the truncated numeric archive: command reruns need that frozen original
snapshot; archive readers independently replay the preserved bounded inputs.
Fresh CLI processes are required when changing code, and POSIX locking is
still the supported platform. This follow-up does not change tax-model or
small-account execution limitations. Changes remain uncommitted for review.

## Postscript — 2026-09-04

This work was subsequently committed as `fd729f4`. The branch review at
`6cce761` records a later seen-only SPY date check with 3,990 matching sessions
over 2006-02-28..2021-12-31. No holdout market data was compared. The v1
calendar provenance remains unchanged as an authoring-time record.

The [review-fix record](2026-09-04-ba-002-review-fixes.md) supersedes this
checkpoint's freely configured journal path and describes the optional
capital-loss sensitivity. The economic BA-002 gates remain unchanged.
