# BoringAlpha

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

Broker connectivity, live orders, sentiment, pullback timing, leverage, and ML
are intentionally outside this milestone.

## Quick start

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/boring-alpha backtest configs/ba_001_multi_asset_trend.toml
```

The command writes a content-addressed run under `experiments/BA-001/` and
prints the strategy/benchmark summary. Repeating the same run verifies the
existing artifacts instead of silently overwriting them. Relative paths inside
a configuration, such as `output_dir` and the CSV paths, resolve against the
directory that contains the configuration file, so a run writes to the same
place regardless of the working directory.

## Evaluating a strategy

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
backtest window outside its period is refused. Gating and truncation live in
`load_market_data`, the only supported way to obtain data for a configuration,
so the seal is not a step a caller can forget.

A period may end at `"dataset"` rather than a date, which is how BA-001's
sealed period expresses the charter's "latest complete dataset": no truncation
and no upper bound beyond the data you have prepared.

`exploratory` is unbounded and always permitted, and stamps every run with a
warning that it is not evidence about the strategy. The checked-in demo uses it.

Two gates implement the charter's sealing policy. A `validation` run requires a
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
the artifacts instead of rewriting them. `artifact_schema` is 5; a manifest
without that field predates the schema.

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
src/boring_alpha/data/  Canonical data and adapters
src/boring_alpha/signals/ Strategy implementations
src/boring_alpha/portfolio/ Cash, positions, and target-weight planning
src/boring_alpha/execution/ Cost model and order-to-fill simulation
src/boring_alpha/backtest/ The daily mark-to-market engine that drives them
src/boring_alpha/metrics/ Performance statistics
tests/                  Correctness tests
experiments/            Generated immutable artifacts (ignored)
```
