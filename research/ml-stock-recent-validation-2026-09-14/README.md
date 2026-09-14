# Recent-window fixed-score validation

Completed September 14, 2026. Read the [completed conditional results](COMPLETION_RESULTS.md).

The frozen $10,000 strategy earned **5.91% annualized under base costs and
5.16% under stressed costs** from January 2, 2024 through September 11, 2026
in the preselected central settlement scenario. Maximum drawdowns were
7.46% and 8.00%; neither account halted. It trailed the reference with matched
stock exposure and costs by $247.11/$245.60, so a stock-selection advantage
has not been demonstrated.

All 12 declared settlement scenarios reconcile and remain profitable, with
base annualized returns of 5.53–6.01% and stressed returns of 4.78–5.26%.
These are conditional historical simulations, including non-spendable cash
claims, not verified brokerage receipts or immediately withdrawable balances.
The initial [strict result](RESULTS.md) remains preserved: the old account
engine could not represent the held PXD-to-XOM stock conversion. The separate
[completion protocol](completion-protocol.json) and [implementation freeze](completion-freeze.json)
made the settlement assumptions explicit before the follow-up outcomes.

The prior pending work was committed as `95dd022` before this continuation.
All acquisition is now complete: 96 Tiingo price requests and 94 SEC
company-fact responses, at $0 new paid data cost. No collector remains running.
There are 3,300 original company-month slots, 2,859 eligible scores and
676 evaluation sessions. Independent account replays cover 8,112 daily
observations and 924 fills across the 12 scenarios.

The user prefers 2022 through current 2026 as the primary research window.
The already-seen 2022–2023 comparison remains separate, earning 2.97%/1.95%
annualized under base/stress costs. The new account starts from $10,000 in
2024; no continuous 2022–2026 result is claimed. September 14 was still in
progress at scope freeze, so September 11 is the final evaluated session.

The [original recent-window protocol](protocol.json) preserves the same
100-security historical cohort and six-signal score. There was no fitting,
ranking-parameter search or replacement with current AI/tech winners.
All original comparison/follow-up files remain byte-for-byte unchanged.
Recent cohort prices and results are now seen research data; tuning on them
would be exploratory.

## Research decision

Keep this fixed score as a baseline. The result is insufficient to justify
scaling capital or claiming dependable extra income. A prospective locked
score-versus-control paper comparison could provide execution evidence;
several months of observation would not establish reliable annual returns.
This completed test does not start a new experiment or automation.

## Reproduction and audit

Use `.venv/bin/python` from the repository root. Detailed source payloads,
fixed predictions and compressed account ledgers remain in the gitignored
`data/snapshots/ml-stock-recent-validation-2026-09-14/` directory. Manifests
record local paths and hashes; credentials are read privately from the
existing environment file and are excluded from artifacts.

- `completion_verify.py after` replays all completed conditional accounts.
- `completion_report.py` regenerates the conditional report and chart.
- `verify_recent.py after` verifies the preserved strict result and its
  original 85-day priced prefixes.
- `evaluate.py` and `completion.py` refuse to overwrite their completed
  results. Preserve both freezes; no further price download is required.

The [final report](COMPLETION_RESULTS.md), [decision](completion-decision.json),
[verification](completion-verification-after.json) and
[artifact manifest](artifact-manifest.json) record the outcome and limits.
