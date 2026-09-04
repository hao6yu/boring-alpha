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
- month-end trend signals with fixed sleeves;
- next-session execution and explicit transaction costs;
- cash accrual, a trade ledger, equity curves, and risk metrics;
- cash and static equal-weight benchmarks using the same accounting engine;
- content-addressed, immutable experiment artifacts;
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

## Run artifacts

Each run writes `manifest.json`, `metrics.json`, `decisions.json`, and the
equity and trade CSVs for the strategy and both benchmarks. The manifest embeds
the full configuration text, the SHA-256 of the configuration, the data, and
the code, the data source label, and every warning, including month-ends that
produced no signal. The run identifier is derived only from those three hashes,
so identical inputs always land in the same directory and a second run verifies
the artifacts instead of rewriting them. `artifact_schema` is 2; a manifest
without that field predates the schema and recorded the absolute configuration
path instead of its text.

Two configuration rules are enforced rather than assumed: `report.output_dir`
is required, and `backtest.start` must select the first session of a month, so
use the first calendar day of the month.

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

Dates must be unique per symbol, values must be positive, and all configured
symbols must share a complete calendar across the supplied warm-up and
evaluation data.
Downloaded market data and secrets are intentionally ignored by Git.

## Repository map

```text
configs/                Versioned experiment configuration
docs/principles.md      Research rules
docs/strategies/        Locked strategy charters
src/boring_alpha/data/  Canonical data and adapters
src/boring_alpha/signals/ Strategy implementations
src/boring_alpha/backtest/ Accounting and execution
src/boring_alpha/metrics/ Performance statistics
tests/                  Correctness tests
experiments/            Generated immutable artifacts (ignored)
```
