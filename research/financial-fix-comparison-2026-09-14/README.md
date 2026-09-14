# Financial accounting follow-up

Read [RESULTS.md](RESULTS.md). Status: **STOP_DATA_GATE_FAILED**, with 27/28
fixture checks passing. No profitability test ran.

This is a new experiment; it does not overwrite the earlier audit or v2 run.
`protocol.json` was frozen before accounting resolution. `extract_v3.py`
inherits the v2 statement and numeric rules and adds source-linked EPS-policy
qualification. `replay.py` applies those rules to all 5,700 original slots;
the only manual expected-value correction is isolated in the fixture checker.
The production parser does not read fixture answers or returns.

`extraction-freeze.json` records code and payload hashes before any revised
return inspection. `accounting-resolution.json` records source facts and
independent rounding intervals for the remaining failure.

Run saved-evidence verification from the repository root:

```sh
.venv/bin/python research/financial-fix-comparison-2026-09-14/verify.py
.venv/bin/python research/financial-fix-comparison-2026-09-14/verify_sources.py
```

The second command reuses the independent v2 numeric auditor against the new
payload, redirecting only output paths and immutable source-manifest reads.
It does not mutate the prior run. Neither command fetches data or tests returns.

Large derived JSON files are gitignored under
`data/snapshots/financial-fix-comparison-2026-09-14/`. Original SEC DOM files
remain under the v2 snapshot folder. Both are required for local verification.
`replay.py` documents the generating procedure; preserve the recorded freeze
before regenerating its outputs because it writes a fresh freeze timestamp.

The revised monthly payload remains diagnostic. It retains old annotations
and all unrelated input fields, including existing `missing_reasons`; use the
separate change-provenance and coverage outputs to interpret repairs.
