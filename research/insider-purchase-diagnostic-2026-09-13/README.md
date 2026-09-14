# Insider purchase economic diagnostic

User-authorized exploratory continuation at $10,000 simulated capital. The original sample-gate stop remains unchanged. Fixed three-hour effort cap, no paid data or live trading. See experiment-policy.json for the pre-outcome registration.

Completed: negative after-cost evidence on the identifiable subset; full signal
price and matched-control coverage remain unresolved. See [RESULTS.md](RESULTS.md).

The simulation and source freeze refuse to overwrite completed results.
Recheck the retained accounting and focused synthetic tests from the repo root:

```sh
.venv/bin/python research/insider-purchase-diagnostic-2026-09-13/verify_accounts.py
.venv/bin/python -m pytest research/insider-purchase-diagnostic-2026-09-13/test_diagnostic.py -q
```

Original archives, full signal/exclusion ledgers, price-derived matching features
and detailed accounts remain under the ignored data/snapshots directory.
No commit or push was requested for this diagnostic.
