# BoringAlpha

English | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**No free lunch. No magic backtests.**

BoringAlpha is a small, dependency-light laboratory for systematic trading
research. Its first job is not to make money. Its first job is to make it hard
to fool ourselves.

The initial strategy, **BA-001 Multi-Asset Trend**, is deliberately simple:
eight fixed ETF sleeves are invested when their trailing 12-month total return
exceeds the trailing cash return, and otherwise remain in cash. Signals are
observed at month-end and executed at the next session's open.

> BoringAlpha is research software, not investment advice. Backtests and paper
> trading do not guarantee live results. The checked-in demo configuration uses
> deterministic synthetic data and has no economic meaning.

## Current milestone

The repository currently provides:

- the locked BA-001 strategy charter;
- deterministic synthetic data for exercising the system;
- strict long-form CSV ingestion for future real datasets;
- month-end trend signals with fixed sleeves on a shared trading calendar;
- next-session execution and explicit transaction costs;
- cash accrual, a trade ledger, equity curves, and risk metrics;
- cash and static equal-weight benchmarks using the same accounting engine;
- declared evaluation periods that seal data after their boundary;
- plausibility checks that halt on implausible data and record the rest;
- a pre-registered evaluation sweep and a mechanical advancement verdict;
- content-addressed, immutable experiment artifacts recording code provenance;
- tests for timing, lookahead, costs, fixed-sleeve behavior, and determinism.

The after-tax extension adds annual target-exposure benchmarks and eight
declared tax scenarios, with partial-lot wash accounting and independent
verification when replaying archived accounts. Its NAV convention and tax
policy are stylized. The [implementation correction record](docs/changes/2026-09-04-after-tax-corrections.md)
describes the tested mechanics and remaining limitations; BA-001's pre-tax
classification remains Inconclusive.
The completed [BA-001 after-tax diagnostic](docs/notes/2026-09-04-BA-001-after-tax.md)
records both archived periods: its advantage over the exposure-matched
allocation held in development and reversed in validation under every tested
tax scenario.

The successor, [BA-002 Multi-Horizon Trend](docs/strategies/BA-002.md), has a
completed [two-feed seen-history diagnostic](docs/reviews/BA-002-source-sensitivity.md):
**practical no-go under both corrected Yahoo and Tiingo inputs**.
It blends 9-, 12- and 15-month signals against an annual 60%-target benchmark.
Its five-row screen requires at least 50 bps/year of primary after-tax advantage,
positive stress margins, and cost-net drawdown at most 20% and no worse than
each paired benchmark. These are research criteria, not return/loss guarantees.
The reused historical windows are explicitly already seen; passing them would
only make the candidate eligible to request a separately authorized holdout.
The [data preflight](docs/reviews/BA-002-preflight.md) found a missing TLT
dividend, now corrected in a new Yahoo snapshot. The separately authorized
source comparison ran all five paired rows and eight tax scenarios in both
seen windows. In 2018–2021, base after-tax CAGR is about 2.00–2.03% versus
4.16–4.21% for the benchmark, with worse drawdown, under both feeds. These are
non-gating diagnostic results, not formal classification or deployment evidence.
The original freeze remains draft; no holdout evaluation is authorized or run.

Broker connectivity, live orders, sentiment, pullback timing, leverage, and ML
are intentionally outside this milestone.

## Quick start

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/boring-alpha backtest configs/ba_001_multi_asset_trend.toml
```

The command writes a content-addressed run under `experiments/BA-001/` and
prints the strategy/benchmark summary. Repeating the same run verifies the
existing artifacts instead of silently overwriting them. Relative paths inside
a configuration, such as `output_dir` and the CSV paths, resolve against the
directory that contains the configuration file, so a run writes to the same
place regardless of the working directory.

### BA-002 synthetic walkthrough

Create a self-contained demo outside the repository, then run the printed
commands with your installed `boring-alpha` executable:

```bash
ba002_demo_dir=$(mktemp -d)
.venv/bin/python -m boring_alpha.demo "$ba002_demo_dir"
.venv/bin/boring-alpha backtest "$ba002_demo_dir/configs/development.toml"
.venv/bin/boring-alpha sweep "$ba002_demo_dir/configs/development.toml"
.venv/bin/boring-alpha sweep "$ba002_demo_dir/configs/validation.toml"
```

Use the two sweep paths printed by these commands with `boring-alpha classify`.
The demo has a fictional calendar and zero distributions; it exercises the
pipeline, not market performance. Dedicated tax tests cover distributions and
lot mechanics. It creates a synthetic draft freeze, but no confirmation or
real run journal.

BA-002 archives both accounts for every grid row, all eight tax scenarios,
the independent expected calendar, frozen-behavior contract, complete human
charter in the freeze record, and truncated
inputs. Publication writes the checksum manifest last. Classification verifies
the archive and account replay, then recomputes the gates rather than trusting
saved pass flags. Post-hoc `aftertax` is a separately identified diagnostic,
not a replacement for the sweep's eligibility evidence.

Precisely: classification replays pre-tax accounting and recomputes drawdown
and gates. After-tax CAGRs and tax identity-check results are validated inputs
from checksummed `tax.json`, not freshly recomputed tax returns. Archived
decisions are traces, not an independent regeneration of the trading signals.
`aftertax` provides a separately identified tax replay when one is requested.

The archived freeze is an identity-only draft envelope, never execution
permission. Confirmation metadata lives in append-only invocation provenance;
historical classification additionally requires the matching external
confirmed freeze. Confirming a synthetic draft does not change its existing
economic artifacts or initialize a real journal.

### Formal historical research workflow (not yet executed)

The independent [NYSE session calendar](docs/data/nyse-calendar.md) is now
checked in. The [branch review](docs/changes/2026-09-04-branch-review-after-tax-overlay.md)
subsequently reported an exact SPY date-only match over seen history:
2006-02-28 through 2021-12-31, 3,990 sessions. No holdout market file was checked.
The later seen-history preflight added two historical configs and a draft
freeze. It did not confirm the freeze or run a formal sweep. The subsequent
[source-sensitivity experiment](docs/reviews/BA-002-source-sensitivity.md) used
distinct, non-classifiable artifacts and supports stopping this candidate.
The following formal workflow is documentation, not the recommended next step
for BA-002 after that result.

After reviewing the charter and selecting fixed input snapshots, configure
two locations, resolved relative to the config file:

```toml
[research]
calendar_path = "../data/calendars/nyse-2006-2026-v1.json"
freeze_path = "../research/ba002-freeze.json"
```

All related BA-001/BA-002 configurations use the **same canonical family journal**:
`<Git common directory>/boring-alpha/journals/BA-TREND.json`. The installed
package's source checkout selects the Git common directory, so changing config
location, working directory or linked worktree cannot create another history.
`research.journal_path` is no longer accepted in executable configs. Historical
execution outside a Git-backed source checkout is refused. Synthetic runs do
not locate or initialize this journal.
The following are instructions for a later deliberate review, not commands
already run or a request to open the holdout:

```bash
boring-alpha research prepare CONFIG --charter docs/strategies/BA-002.md
boring-alpha research show research/ba002-freeze.json
boring-alpha research confirm CONFIG --hash FULL_DISPLAYED_HASH --reason "Reviewed the complete freeze"
```

`prepare` writes a draft containing the charter text, behavior, policy, calendar,
periods and code/input identities. It hashes source bytes without parsing
market observations. `confirm` checks that the configured identities still
match, confirms that exact draft, and initializes the family journal. Neither
command runs a strategy or reveals a holdout. Existing drafts are write-once;
select a new freeze path for a reviewed revision.

Reconfirming an already confirmed freeze cannot recreate a missing journal.
Do not erase it: recover the existing history from backup. The journal is
durable local operating state inside Git metadata, **not committed by `git add`**
and not transferred by clone/push. Back it up separately; never treat a clone
with no history as a fresh scientific holdout. Reviewed non-sensitive freeze
records in `research/` can be committed; personal tax inputs should remain
local. Invocation provenance and frozen archive identities remain separate.

Ordinary `sweep DEVELOPMENT_CONFIG` and `sweep VALIDATION_CONFIG` reuse the same
confirmed freeze, with no per-run approval file. Classify their printed archive
paths using `boring-alpha classify DEVELOPMENT_SWEEP VALIDATION_SWEEP --freeze
research/ba002-freeze.json`. Passing is only eligibility to request a holdout.
First holdout execution additionally requires `sweep SEALED_CONFIG --reveal
"Explicit reason for this reveal"`.

The journal logs attempts, access, failure and completion. After a crash, retry
the identical frozen command; no ledger editing is needed. Changed code on
already-revealed coverage requires a separately reviewed new freeze and
`--repair-of PRIOR_ATTEMPT_ID --repair-reason "Describe the correction"`.
Only code/evaluator changes are permitted for that repair: candidate, rule,
window, policy, calendar and input bytes must match. Repair results and their
retries remain **revealed-data diagnostics**, never a fresh holdout or new
eligibility evidence. Do not delete or reset the journal to retry a candidate.
Managed runs print the journal path and attempt ID **before** access; overlap
refusals name the earlier attempts for `--repair-of`.

One independent reveal is shared by the BA-TREND family: revealing BA-001's
sealed period consumes BA-002's opportunity to call that history unseen, and
vice versa. Later analysis can only be explicitly revealed-data research.
The current repair command permits same-candidate code/evaluator corrections,
not a cross-candidate diagnostic workflow. Historical seen windows must end
before 2022-01-01, and the registered historical sealed window starts there.

## Evaluating BA-001

A single backtest is not evidence for or against a strategy. The charter fixes
what must be run alongside it, and `sweep` runs the whole grid at once so the
stability checks cannot become a menu of results chosen after the fact:

```bash
boring-alpha sweep configs/my_development_run.toml
```

The grid is the pre-registered 12-month rule, the same rule at twice the base
cost, the 9- and 15-month neighbours, and the rule with its largest-contributing
sleeve held permanently in cash. Each runs against the charter's full static
benchmark. A sweep writes `summary.md`, which leads with the pre-registered
result and labels everything after it as a stability check, plus `criteria.json`
holding the arithmetic behind C1 to C5.

Alongside them it reports the cash and exposure-matched benchmarks, one-way
turnover, cost drag, worst month, time in market, per-sleeve and per-cluster
attribution, and a stationary block bootstrap interval for the Sharpe difference
against static. That interval is the honest counterweight to a point estimate:
on about a decade of monthly decisions it will often contain zero, and the
summary says so in plain words either way.

Two conventions worth stating, because both are easy to read wrongly:

- **Turnover is one-way.** Trade notional sums both sides of every rebalance,
  so the reported figure is half of it. A full round trip of the portfolio is
  one unit, not two.
- **Attribution ranks on excess over cash.** A sleeve's contribution is its
  share of the strategy's return *above* what the same capital would have
  earned sitting in cash, which is the charter's definition and what C5 uses to
  pick the sleeve to remove. Raw profit is reported beside it, because in a
  high-cash-rate period the two can disagree about which sleeve mattered most.

The verdict needs both periods, so it is a separate step:

```bash
boring-alpha classify experiments/BA-001/sweeps/<development> \
                      experiments/BA-001/sweeps/<validation>
```

`classify` applies the charter's advance / reject / inconclusive rule to the two
sweeps and prints the criterion-by-criterion arithmetic. The verdict is
computed, never typed in. Inconclusive is a real outcome; the tooling says so
rather than inviting another variant.

## Evaluation periods

Every run declares the period it targets, and the boundaries live in
`configs/evaluation_periods.toml` rather than in the run configuration, so a
config cannot quietly widen its own window:

```toml
[evaluation]
period = "development"   # or validation, sealed, exploratory
```

The dataset is truncated at the period's end before the engine sees it, so data
after the boundary never reaches the engine, the metrics, or the data
fingerprint. A development run therefore keeps its identity after later data is
appended, which is the property `tests/test_seal_identity.py` pins down. A
backtest window outside its period is refused. Profiles own admission rules;
the CLI uses `open_run` for the explicit run lifecycle, while the loader owns
truncation. Direct managed historical loads are refused without that context.

A period may end at `"dataset"` rather than a date, which is how BA-001's
sealed period expresses the charter's "latest complete dataset". Its requested
end must reach the latest complete shared session; a shorter selected result
is refused. BA-002 instead requires fixed, exact contract dates.

BA-001's `exploratory` mode stamps a warning that it is not strategy evidence.
The checked-in synthetic demo uses it. It does not bypass protected historical
access; BA-002 does not accept an exploratory alias for its fixed windows.

BA-001 retains its charter's review gates. A `validation` run requires a
written development review at `docs/reviews/<ID>-development*.md`. A `sealed`
run requires both that review and a validation review, plus an explicit reason:

```bash
boring-alpha backtest configs/my_sealed_run.toml --unseal "dev and validation reviewed"
```

The reason is recorded in the run's provenance record, and the run must be
listed in the strategy's charter change log. Neither gate is cryptographic: you
can always edit a file, and `evaluation.periods_path` can point at a different
registry. They exist so that looking at sealed data is a deliberate, reviewable
act rather than an accident. What the artifacts do guarantee is that a run
states which boundaries it obeyed: the resolved period and its bounds are part
of the run identity, so the same configuration under different boundaries is a
different run.

New historical invocations that can expose BA-TREND data from 2022 onward
(including BA-001 exploratory runs) also require a confirmed freeze and the
same family journal **before observation parsing**. BA-001's existing
`--unseal` reason also serves as its first reveal reason; a second flag is not
needed. Failures preserve the reveal but permit identical frozen retries or
explicit diagnostic code repairs as described above. Captured input bytes are
used throughout a managed run. This is a procedural research safeguard, not
security against the machine's owner. Read-only legacy BA-001 archive
classification needs no retroactive freeze.

For BA-001, the optional research table in
`configs/ba_001_real_csv.example.toml` shows the two locations. After selecting
the exact registered window and matching immutable data methodology, prepare
with `boring-alpha research prepare CONFIG --charter docs/strategies/BA-001.md`,
review and confirm its displayed hash as above, then retain BA-001's existing
review-file and `--unseal` requirements. These instructions do not authorize
running BA-001's holdout. An old v1 config must not silently follow `data/current`
to a v2 snapshot: choose the matching frozen snapshot explicitly.

## Run artifacts

Each run writes `manifest.json`, `metrics.json`, `decisions.json`, the equity
and trade CSVs for the strategy and both benchmarks, and `provenance.jsonl`.

`manifest.json` describes the experiment's identity: the full configuration
text, the SHA-256 of the configuration, the data, and the code, the declared
period and its bounds, the first and last session actually loaded, and every
warning, including month-ends that produced no signal and any data-quality
finding. It is written once. The run identifier is derived from the
configuration, data, and code hashes plus the resolved evaluation period, so
identical inputs always land in the same directory and a second run verifies
the artifacts instead of rewriting them. A manifest without `artifact_schema`
predates the schema-aware readers.

The trade ledgers record `intended_notional` beside the filled notional, so an
order that was scaled down by available cash is visible as a partial fill, and
`reference_price` — the month-end close the decision was made on — beside the
fill price. The difference between those two prices is slippage; in the
backtest it is the overnight gap, and it is the figure a paper fill will be
compared against.

`provenance.jsonl` describes the environment each invocation ran in — timestamp,
Git commit, whether the working tree was dirty, Python version, and any unseal
reason — and gains one line per run. These belong outside the manifest on
purpose: a docs-only commit or a Python patch upgrade changes the environment
without changing the experiment, and folding them into a write-once file would
make the integrity check fire on ordinary work until you learned to ignore it.

New BA-001 artifacts use schema 6, with specific schema-5/6 compatibility
readers. Complete BA-002 sweeps use schema 7 and explicit strategy/benchmark
account maps. Their frozen implementation/evaluator hashes must match the
code consuming them; future behavior changes require reviewed compatibility
or the original code checkout, not automatic acceptance of an old hash.

Three configuration rules are enforced rather than assumed: `report.output_dir`
and `evaluation.period` are required, and `backtest.start` must select the first
session of a month, so use the first calendar day of the month.

## After tax

A configuration may carry a `[tax]` table (see `configs/tax_policy.toml` for
the stylized BA-001 policy). When it does, every run in a sweep is also scored
after tax by a pure overlay over the pre-tax artifacts: fills are converted to
real shares, distributions open their own lots, sales close lots by method,
wash sales are adjusted, and each calendar year is taxed with
character-retaining carryovers under an after-tax NAV convention (the pre-tax
path is rescaled at each year end by the tax paid). Three inputs are declared
rather than known — lot selection, a commodity pool's tax character, and the
qualified fraction of equity distributions — so the overlay runs a fixed grid
of eight scenarios and any after-tax conclusion must hold under all of them.
Results land in `tax.json` beside `criteria.json`, with a summary block in
`summary.md`. Drawdown is never recomputed after tax.

Any archived sweep can be re-scored without re-running it:

```bash
boring-alpha aftertax experiments/BA-001/sweeps/<id> --policy configs/tax_policy.toml \
    --distributions data/current/distributions_daily.csv
```

The output is named by the policy, the distributions and the overlay's code
fingerprint, so a corrected overlay produces a separately identified file and
identical inputs are idempotent. Rates in the checked-in policy are a
federal-only stylized scenario, not anyone's bracket; real rates belong in an
untracked local copy.

### Optional capital-loss deduction sensitivity

The eight gating scenarios exclude the ordinary-income capital-loss deduction.
An explicit sensitivity is available without changing those gates:

```bash
boring-alpha aftertax PATH_TO_ARCHIVED_SWEEP --policy configs/tax_policy.toml \
    --loss-sensitivity configs/loss_sensitivity.example.toml
```

The example declares **zero available capacity**; edit a local copy only after
choosing the household assumptions. It requires annual unused deduction
capacity, available outside ordinary taxable income, and whether the resulting
tax savings stay outside the account or are explicitly contributed. The rate
defaults to the selected tax policy, not an inferred personal tax bracket.
The capacity applies to a tax return, not separately to simultaneous accounts;
each strategy/scenario here is an alternative account, not an additive benefit.

The diagnostic consumes short-term then long-term carryovers after capital
netting and recalculates later years and terminal liquidation. It does not add
a tax benefit while preserving the losses that funded it. Outside savings earn
no assumed return; contribution mode is a stylized NAV-rescaling experiment,
not exact tax-lot funding, and suppresses self-financing CAGR/tax-drag claims.
The full policy, account size, baseline and sensitivity results are archived in
a separate `tax-loss-sensitivity-*.json`; `tax.json` and eligibility are unchanged.
The existing $100,000 research result cannot be scaled to $2,000–$5,000 once
a fixed-dollar deduction is included. See the
[sensitivity design](docs/decisions/2026-09-04-capital-loss-sensitivity.md).

## Real CSV contract

The real-data adapter accepts two CSV files. Prices use total-return-adjusted
open and close values so that dividends and splits are represented in the
return series without mixing raw and adjusted units:

```csv
date,symbol,tr_open,tr_close
2024-01-02,SPY,100.12,100.80
```

Cash data contains the one-session growth factor applied to cash carried from
the prior session:

```csv
date,cash_factor
2024-01-02,1.00021
```

Dates must be unique per symbol and values must be positive. Sleeves may begin
on different dates: the portfolio's calendar is the sessions on which every
configured symbol has a bar, and it starts at the first such session. After that
common start a missing bar is a data error that halts the run, never an implicit
move to cash. Downloaded market data and secrets are ignored by Git.

## Data plausibility

Loaded data is inspected before it is used. Findings that usually mean a broken
series halt the run: a one-session move beyond ±40%, an open gapping beyond
±25% from the prior close, or a cash factor implying an annual rate outside
−10% to +30%, which is what a rate entered where a one-session growth factor
belongs looks like. Findings that are merely suspicious are recorded in the
manifest and printed: gaps over five business days in the shared calendar, and
ten or more identical consecutive closes.

The thresholds are deliberately loose enough that real crisis sessions pass.
Any of them can be relaxed for a run:

```toml
[quality]
max_session_return = 0.6
```

Inspection happens after the evaluation period truncates the data, so findings
describe the data the run actually used.

## Negative control

Synthetic data comes in two regimes, selected with `[data] regime`. The default
`trending` builds slow cycles that any trend rule trades well — useful for
exercising the machinery, and flattering by construction. `random_walk` is the
negative control: driftless and memoryless, it is the series on which a trend
rule should earn nothing and still pay costs. A result that looks similar in
both regimes is a result about the plumbing, not about trend.

## Repository map

```text
configs/                Versioned experiment configuration
configs/evaluation_periods.toml  Period boundaries taken from the charters
docs/principles.md      Research rules
docs/strategies/        Locked strategy charters
docs/reviews/           Written reviews that gate the next period
docs/changes/           Implementation and correction records
docs/notes/             Research diagnostics and result notes
docs/decisions/         Decision records: benchmarks, data, tax policy
src/boring_alpha/data/  Canonical data and adapters
src/boring_alpha/signals/ Strategy implementations
src/boring_alpha/portfolio/ Cash, positions, and target-weight planning
src/boring_alpha/execution/ Cost model and order-to-fill simulation
src/boring_alpha/backtest/ The daily mark-to-market engine that drives them
src/boring_alpha/metrics/ Performance statistics
src/boring_alpha/tax/   After-tax overlay: lots, wash sales, year-end netting
tests/                  Correctness tests
tools/                  Market-data fetchers and calendar builders
experiments/            Generated immutable artifacts (ignored)
```
