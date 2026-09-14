# Verified financial-input comparison

Read [RESULTS.md](RESULTS.md) for the complete before/after assessment and [decision.json](decision.json) for the research decision.

`protocol.json` preserves the scope clarification and prior file hashes. `prepare.py` produced the frozen panels/schedules and 189-field change list. `worker.py` replays the original account engines. `resume_recent.py` reuses the original floating-point reference implementation; its bounded arithmetic correction is recorded in `adapter-freeze.json`. `finalize.py` verifies saved results and renders the report.

The old and recent workers must run in separate Python processes because the original recent adapter changes module globals. The existing freezes and result files intentionally prevent silent overwrites. `finalize.py` can regenerate summaries from the saved accounts without trading simulation or network access.

Raw panels, schedules, predictions, account ledgers and reference paths are in `data/snapshots/verified-input-comparison-2026-09-14/`, under the existing ignored snapshot policy. Their hashes are recorded in the freezes and result files. No credentials are required by the offline comparison.
