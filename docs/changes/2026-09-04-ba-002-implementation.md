# BA-002 — synthetic-first implementation record

Date: 2026-09-04
Baseline: `3a3a74c` on `after-tax-overlay`
Scope: [implementation plan](../superpowers/plans/2026-09-04-ba-002.md)

This records the initial 709-test implementation review. The subsequent
[workflow simplification](2026-09-04-ba-002-workflow-simplification.md)
supersedes its separate authorization/state workflow and unresolved calendar
dependency. Historical facts and the test count below refer to that earlier
checkpoint, not the final follow-up suite.

BA-002 is implemented for review with synthetic inputs. Its charter is not
locked and it has no historical result. No market data was fetched or run,
no holdout was inspected, and no real freeze, authorization or reveal record
was created. BA-001's charter, reviews and archived results are unchanged.

## What is implemented

- Equal cash-relative votes at 9, 12 and 15 months. Each horizon retains its
  own anchor and cash hurdle in decision evidence. Pair variants divide by
  two, while every row and reference retains 15-month readiness.
- Five fixed rows: primary, double cost and each leave-one-horizon-out rule.
  Each carries its own annual 60%-target benchmark. Both sides use 20 bps in
  the double-cost row; neither reuses the primary account's tax result.
- All eight existing tax scenarios for every account, including paired stress
  benchmarks and non-gating diagnostics. Independent account replay and exact
  expected-session coverage run before scoring and when reading archives.
- The approved numerical criteria: primary worst-strategy / best-benchmark
  after-tax CAGR margin at least 50 bps/year; every stress margin strictly
  positive; every row's pre-tax, cost-net drawdown magnitude at most 20% and
  no worse than its paired benchmark. Decimal comparisons retain serialized
  precision at the boundaries. Both seen periods must pass separately.
- A validated research contract and immutable period-evidence representation.
  Classification recomputes gates and reports research eligibility, not
  BA-001's Advance label. Invalid evidence raises an error, not a verdict.
- Schema-7 archives with explicit account maps, all decisions/ledgers/curves,
  deterministic compressed inputs, calendar, contract and result checksums.
  Publication serializes writers and writes the completion manifest last.
  Identical reruns verify existing bytes and append separate provenance.
- Family-scoped access controls for BA-TREND. Historical BA-002 execution
  requires independent authorization; new protected BA-001 invocations cannot
  use an exploratory alias or `--unseal` as a substitute. Missing/unwritable
  state refuses access; authorized access is recorded durably before parsing
  observations. A failed or crashed run cannot restore a consumed reveal.
- A self-contained synthetic demo and both CLI paths. Single `backtest` is
  explicitly a pre-tax primary-rule diagnostic, not a full eligibility sweep.
  Archived `aftertax` output is a separate diagnostic, never an overwrite of
  the eligibility evidence.

## Integration findings that changed the implementation

**Authorization was not enough while files could be reopened.** An independent
review replaced price/cash/distribution files between fingerprinting and
parsing. The original access identity and computed observations could differ.
Authorized source and manifest bytes are now captured once and parsed from
that immutable capture after durable access starts. Tests replace and delete
the original files and require computation to retain the approved bytes.

**An embedded config is evidence too.** The first archive consumer checked
shared hashes and reconstructed accounts, but did not independently parse the
manifest's config. Changing its benchmark exposure could evade that layer.
`archived_config.py` now cross-checks full behavior, windows, source, policy
and recomputed strategy identity against the contract without opening any of
the original live paths. Tests prohibit path reads/resolution while consuming
valid archived configuration.

**Schema compatibility must be profile-specific.** BA-001 still reads schema
5/6. Schema 7 is not an additive permission to classify arbitrary legacy
criteria: BA-002 requires the complete archive. Noninteger schema tags,
missing diagnostic tax accounts and inconsistent distribution metadata are
also refused.

**Execution must retain the authorized code identity.** A late fingerprint
alone could label a run with code changed during its earlier calculations.
Invocation-start code/evaluator identities are now pinned without creating
synthetic approvals, compared with any historical attempt's frozen identity,
and checked before tax scoring and schema-7 publication. A completed manifest
must not be written first and only then discover that authorization differed.

**Some old fixtures were deliberately outside the new access boundary.**
Gate and quality tests used fictitious unregistered candidate IDs; they now
use BA-001. Quality/methodology fixtures use bounded, fictional seen windows.
Existing C5 and dataset-ended regression fixtures retain their discriminating
prices and dates, with only the new access boundary isolated by a test patch.
Separate access tests exercise actual refusal, authorization, concurrent
claims and crash persistence. No production bypass was added for tests.

## Verification

Final stable-code verification: `.venv/bin/python -m pytest -q` reported
**709 passed, 116 subtests passed in 111.49 seconds**. `git diff --check` was
clean. These are pytest executions, not distinct declared methods;
parametrization, inheritance and unittest subtests are not interchangeable
counts. The separate saved-verdict mutation probe failed its intended
assertion, confirming that the regression is detected.

The synthetic acceptance tests cover config → backtest/sweep → complete
archive → account replay → tax replay → two-period classification. Direct
and archived tax dictionaries match account-for-account. Altering future
distribution values to nonnumeric traps leaves a bounded rerun's immutable
manifest unchanged and appends only invocation provenance.

Discriminating regression checks include:

- Explicit vote outcomes and pair denominators, independent cash anchors,
  exact ties and common warmup; controlled denominator/readiness/tie mutations
  were caught during signal implementation.
- Primary and stress boundary cases, failed absolute/relative drawdown gates,
  and favorable matched tax differences with unfavorable independent extrema.
  Controlled extrema and primary-threshold mutations are retained as tests.
- A real synthetic benchmark calculation whose 10/20-bps accounts differ,
  then a deliberately calibrated criterion probe between their returns.
  Replacing the stress benchmark with the base benchmark fails its assertion.
  Those altered probe returns are test inputs, never published evidence.
- Removal of boundary/interior/anchor sessions from every series at once,
  declared closures, insufficient calendar coverage, and shortened curves.
- Changed embedded behavior, missing accounts/scenarios/checksums, incomplete
  publication, stale code/evaluator identity, and altered saved pass flags.
  CLI classification remains identical even when both saved period verdicts
  are changed with internally consistent file checksums. A separate in-memory
  mutation that makes the CLI trust those saved verdicts fails that exact
  end-to-end assertion; it changes no source file or published evidence.
- Authorized-input replacement/deletion, future numeric-parse traps,
  family overlap, concurrent first-reveal claims and process interruption.

The demo uses generated prices, a fictional weekday calendar and zero
distributions. It is not a financial result or a realistic tax-data acceptance
sample; separate existing tax fixtures test distributions and lot accounting.

## Remaining decisions and limitations

Before any historical BA-002 command, independently review the implementation,
confirm the remaining charter/policy/date choices, source and archive a usable
exchange-session calendar, and bind the exact input/code identities to an
explicit freeze and scoped run authorization. The human charter should be
archived at that freeze; mutable Markdown is not used as machine behavior.
The real calendar provider, source rights and exceptional closures are not
resolved by generating the synthetic demo. The global-equity diagnostic stays
unavailable rather than substituting an unapproved proxy.

Both proposed research windows are already seen. Favorable results would
only screen a candidate for a separate holdout decision, not establish an
independent edge. No live orders, broker interface, share rounding, capital
deployment or promise of a return/loss cap is implemented.

The existing federal-only tax rates, DBC scenarios, qualified fractions and
NAV-rescaling convention remain stylized. This work does not repair omitted
tax-funding transactions, actual K-1 allocations, GLD expense sales, foreign
credits, state/NIIT taxes or changing tax law. All risk gates remain pre-tax.

Hashes and local approval files are procedural integrity safeguards, not
security against the computer's owner. A missing or unreadable ledger refuses
execution; it cannot record its own refusal in a ledger it cannot write.
Code/evaluator identity is deliberately strict: using changed BA-002 code on
old evidence requires the frozen checkout or a reviewed compatibility path.
Fingerprints identify on-disk source: execute from a fresh CLI process in that
checkout, not a long-running Python session retaining modules from older code.
The current implementation uses POSIX file locking and is tested on macOS;
Windows locking support is not included.

Changes are left uncommitted for review. Unrelated PNG assets are untouched.

## Postscript — 2026-09-04

The implementation and workflow follow-up above were committed as `fd729f4`.
The branch review was committed separately as `6cce761`. Its later SPY date-only
check reported 3,990 matching sessions over 2006-02-28..2021-12-31, without a
holdout market-data check. The original statements above describe their earlier
checkpoints. Current correction status is in the
[review-fix record](2026-09-04-ba-002-review-fixes.md).
