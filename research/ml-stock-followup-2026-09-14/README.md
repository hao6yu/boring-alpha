# Cached-data follow-up

Read [RESULTS.md](RESULTS.md) for the fixed-score benchmark comparison and
Ridge spinoff-payment sensitivity. This follow-up does not change the original
model results or establish the actual fractional-share cash payment.

`protocol.json` fixes 20 control seeds, two cost cases, the exposure/cost
reference and seven receipt cases before their outcomes. `run-freeze.json`
records implementation hashes. The fixed predictions are reused; no model is
refitted and no network market-data request is made.

The run order is `verify.py --before`, `followup.py`, `verify.py`, then `report.py`,
using the repository `.venv/bin/python`. The runner refuses to overwrite its
completed result. The report is a presentation of existing outputs, not another
strategy evaluation. Original source files are checked before and after use.

Full ledgers are compressed JSON under
`data/snapshots/ml-stock-followup-2026-09-14/` and are excluded from Git. They
depend on the preserved original snapshot. Every control is retained; ensemble
averages are unavailable for the strict incomplete ensemble and explicitly
conditional for the receipt scenarios. Receipt sensitivities are not exhaustive
mathematical bounds or observed broker cash flows.

[Benchmark chart](benchmark-paths.png) shows the base fixed account, exposure/cost reference, and scenario-qualified unranked mean.
