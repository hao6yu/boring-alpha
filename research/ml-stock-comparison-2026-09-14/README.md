# Fixed monthly stock model comparison

This implements the frozen [100-stock experiment](../ml-free-data-preparation-2026-09-13/NEXT_EXPERIMENT.md).
The question is whether one fixed tree model improves on a regularized linear
model and a fixed financial/momentum score, using the same historical cohort,
information dates, eligible observations and account rules.

Read [RESULTS.md](RESULTS.md) and `decision.json` for measured outcomes, plus
[account details and paths](ACCOUNT_NOTES.md) for the cash and spinoff limitations. This is an exploratory 2022–2023
diagnostic; 2024–2025 strategy prices are reserved.

## Evidence and implementation

- `experiment-start.json`: scope, initial timestamp and bounded request/effort limits.
- `collect.py`, acquisition manifests and `finish_download.py`: dated SEC facts,
  registrant metadata and scoped Tiingo prices, with payload hashes and quota accounting.
- `identity-map.json`, `reviewed_sources.py`: historical issuer continuity,
  source-supported corporate actions and explicitly rejected series.
- `fundamentals.py`, `panel.py`: 5,500 original company-month slots, dated
  financial features, price/action qualification and coverage.
- `models.py`: the fixed annual-refit Ridge/tree/score comparison.
- `portfolio.py`, `account-policy.json`: $10,000 whole-share base/stress accounts.
- `verify.py`: source integrity, information cutoffs, reference-return cases and
  account timing checks before fitting.
- `evaluation-start.json`: code and data hashes frozen before fitting.
- `verify_accounts.py`: independent Decimal replay of fills, costs, cash,
  receivables, holdings, NAV and the permanent loss halt.
- `report.py`: renders measured outcomes after account verification.

Provider payloads, the monthly panel, predictions and full account ledgers are
stored locally under `data/snapshots/ml-stock-comparison-2026-09-14/` and excluded
from Git. Manifests retain their paths and SHA-256 hashes. A repository clone
alone does not include these inputs. The implementation also reuses the preserved
SEC extraction helpers and archived fee scenario from earlier experiments.

## Running and reproducibility

Use the repository `.venv/bin/python`. Acquisition reads the existing Tiingo key
privately from `.env`; no key is included in these research artifacts. Respect
the request ledger and hourly quota. The finite collector stops at its deadline,
on provider denial, on its request cap or when its request list is complete.

The construction order is `fundamentals.py`, `panel.py`, `verify.py`, `models.py`,
`verify_accounts.py`, then `report.py`. Each script is invoked by its full
repository-relative path. The model runner refuses to overwrite a completed
evaluation. Reproduction should use a separately labeled copy of the frozen
inputs, without changing the original outcome or silently searching new parameters.

Successful requests do not imply complete source coverage. The coverage artifact
separates request completion, missing history, entry eligibility and known labels.
Unknown held corporate outcomes leave the affected account incomplete. Unpaid
claims can contribute to NAV but cannot finance purchases without payment evidence.
