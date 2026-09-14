# Stock momentum economic diagnostic

One authorized fixed rule, $10,000 simulated capital, two-hour effort cap, $0 new paid data.

**Complete: negative observed economics; shelve this implementation.** Base/stress
ending account values are $8,061.78/$8,023.30. Both momentum accounts triggered
the loss halt on May 9, 2022 and liquidated the next session. The complete
unranked comparison remains unresolved because two control seeds require
WWE-to-TKO successor history absent from the frozen cache.

- [Results and decision](RESULTS.md), [machine-readable decision](decision.json).
- [Frozen policy](experiment-policy.json), [input registration](input-freeze.json),
  [immutable results](evaluation-result.json).
- [Independent accounting reconciliation](account-verification.json),
  [control coverage gap](control-coverage-gap.json).

The run used only the cached 2019–2023 price window. Raw inputs and all 42
account ledgers reside in the gitignored
`data/snapshots/equity-momentum-diagnostic-2026-09-13/` directory; their hashes
and relative paths are recorded in the tracked registration/result files.
Prior experiments and the reserved 2024–2025 strategy window remain preserved.

From the repository root, offline checks and report reproduction are:

```sh
.venv/bin/python -m pytest research/equity-momentum-diagnostic-2026-09-13/test_momentum.py -q
.venv/bin/python research/equity-momentum-diagnostic-2026-09-13/verify_accounts.py
.venv/bin/python research/equity-momentum-diagnostic-2026-09-13/write_report.py
```

Verification/report regeneration updates their timestamps. The original
simulation refuses to overwrite its completed results and enforces the expired
research deadline; rerunning or amending the experiment requires a separately
recorded scope. No further variants, paid data, or live pilot follow from this result.
