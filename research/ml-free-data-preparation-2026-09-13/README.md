# Free data preparation, September 13, 2026

Start with [RESULTS.md](RESULTS.md), then [NEXT_EXPERIMENT.md](NEXT_EXPERIMENT.md).
The user authorized repairing the fixed ten-company feasibility sample and
defining the larger dataset/shorter chronology. No model fit occurred here.

From the repository root, reproduce offline outputs using:

```sh
.venv/bin/python research/ml-free-data-preparation-2026-09-13/prepare.py
.venv/bin/python research/ml-free-data-preparation-2026-09-13/freeze_cohort.py
.venv/bin/python research/ml-free-data-preparation-2026-09-13/verify.py
```

`acquire.py tiingo` reuses cached hashes and the existing local Tiingo key;
`acquire.py filings` uses cached SEC outcomes. No key is logged or put into
command arguments. Neither mode creates an account or purchases a plan.
These are fixed-sample collectors, not a broad acquisition command.

`accounting-repairs.json` contains source-specific original-filing corrections.
`corporate-actions.json` and `terminal-outcomes.json` distinguish actual units,
receivables and final shareholder outcomes from vendor price adjustments.
Raw payloads and derived reference-price rows remain under the gitignored
`data/snapshots/ml-free-data-preparation-2026-09-13/` directory. The corporate
reference is for return features; never substitute it for an executable ledger.

`next-cohort.json` is a deterministic 100-security acquisition list, not a list
of stock recommendations or completed issuer mappings. Original feasibility
outputs remain unchanged. `artifact-hashes.json` records this phase's files.
