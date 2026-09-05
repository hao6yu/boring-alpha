# BA-002 — accepted branch-review corrections

Date: 2026-09-04. Baseline: `6cce761` on `after-tax-overlay`.
The holder accepted the focused recommendations after the
[branch review](2026-09-04-branch-review-after-tax-overlay.md).

## Scope

This fixes concrete evidence/workflow errors and adds an explicitly optional
household-tax sensitivity. It does not merge, commit or push the branch, lock
the charter, change its 9/12/15/no-bands rule or thresholds, run a historical
evaluation, or reveal a holdout. No repository files under `data/` or
`experiments/` were read for market evaluation or changed. The five unrelated
PNG files remain untouched. Original review reports are retained, not rewritten
as if their subsequent corrections had already existed.

## Implemented

- Historical contract validation now binds seen periods to dates before
  2022-01-01 and sealed periods to that starting boundary. Preparation,
  confirmation and archive readers use the invariant. Synthetic dates remain
  unconstrained. Equivalent legacy freeze checks prevent relabeling via BA-001.
- The configurable journal path is removed. A single BA-TREND journal lives
  under the package checkout's Git common directory, shared across linked
  worktrees/configurations. Synthetic work does not resolve/create it;
  non-Git historical execution refuses. Reconfirming a previously confirmed
  freeze cannot resurrect a deleted journal. This prevents mistakes, not
  deliberate history resets through cloning or manual edits.
- Journal path and attempt ID are printed before access starts; overlap
  refusals identify earlier attempts. Existing identical retries and explicit
  diagnostic repair labels remain. One candidate's reveal consumes the
  family's independent holdout opportunity, not all possible future research.
- Price, cash and distribution parse errors no longer echo raw rows, header
  contents or chained numeric exceptions. Date-first filtering still excludes
  future numeric observations; malformed-date tracebacks cannot expose them.
- Long-term holding periods use a calendar-year anniversary instead of a
  fixed 365-day count, including leap-year boundaries and tacked lot origins.
- The [capital-loss sensitivity](../decisions/2026-09-04-capital-loss-sensitivity.md)
  requires declared capacity, outside taxable income and savings destination.
  Annual deduction consumption reduces short then long carryovers; subsequent
  netting and terminal liquidation are recomputed. Outside savings remain
  separate; contribution mode is explicitly a stylized NAV/deposit experiment,
  not exact real-lot funding or self-financing performance. Baseline and
  sensitivity outputs are separately identified, and sensitivity records
  cannot become BA-002 gating accounts.
- Archive documentation now states the actual guarantee: pre-tax accounts and
  drawdowns are recomputed; checksummed after-tax metrics/check flags are
  validated saved inputs. The separate aftertax command replays taxes.
- The weak threshold-detail assertion now checks the computed margin, not the
  threshold's always-present wording. The existing discriminating boundary and
  mutation tests remain.
- Current docs record the branch reviewer's later 3,990-session seen-only SPY
  check. They do not imply a new inspection or a holdout check; the reported
  check lacks an attached exact snapshot byte identity. Old v1 provenance and
  original checkpoint text are preserved, with dated postscripts. BA-001 gets
  a research config example and a scope note about the omitted deduction.

## What this does not establish

The review's roughly 60-bps estimate is not published as a verified improvement
or bound. No historical account was rescored with this feature. Fixed-dollar
deductions make account size relevant, and the existing $100,000 result cannot
be proportionally mapped to a $2,000–$5,000 account. The baseline eight scenarios
and approved 50-bps/20%-drawdown screening criteria remain unchanged.

No speculative same-lot wash-sale or DBC sale-character change was made from
unverified legal recollection. Other explicitly deferred tax approximations,
real-funding transactions and reporting refinements are not claimed resolved.
The Ford closure source was not invented: its indexed NYSE memo text supports
the date, with the aggregate PDF retrieval limitation already disclosed.

The canonical journal is local operating state under Git metadata, not a
tracked file transferred by clone/push. Back it up separately and migrate
existing history deliberately. Selected non-sensitive freeze records may be
versioned; personal tax assumptions should remain in local config.

## Verification

- Final stable-code run: `.venv/bin/python -m pytest -q` — **879 passed,
  192 subtests passed in 121.28 seconds**. Execution fixtures are fictional
  and temporary; this is not a historical-results verification.
- Five targeted mutation probes were caught: retaining consumed loss
  carryovers, crediting the terminal deduction twice, restoring the fixed
  365-day holding-period rule, and exposing chained conversion errors in each
  of the price/cash and distribution loaders. The mutations were reverted
  before the final suite.
- Independent integration review also led to regressions for a zero-capacity
  policy under negative cash yields and fractional carryover roundoff.
  Contribution-mode effective tax rate is omitted along with CAGR/tax drag,
  because its account deposits invalidate the baseline ratio interpretation.
- Both relevant CLI help surfaces were checked; `aftertax --loss-sensitivity`
  is documented and remains off by default. `git diff --check` is clean.
