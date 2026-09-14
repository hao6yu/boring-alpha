# Next experiment specification — financial extraction only

Status: proposed, not executed or queued. This is the next step justified by
the completed ten-company audit; no improved-return claim has been made.

## Hypothesis

The fixed score's accounting signals are weakened by missing common-equity and
common-earnings inputs. Better historically available extraction may improve
signal fidelity. It can also reduce returns; source correctness takes priority.

## Bounded implementation gate

Use the existing original 100-security cohort and its cached SEC facts and
submission metadata. Develop reusable rules for complete common-equity
reconciliation and explicit basic common-EPS numerators. The twenty reviewed
snapshots provide accounting fixtures, including losses, NCI, discontinued
operations, a combined common-stock/paid-in-capital line and deferred
compensation. A ticker-specific list of filled values is not the implementation.

Start with one implementation pass, no new vendor or account, no paid data,
and at most 90 original filing-document retrievals. If broad coverage requires
more retrievals or extensive manual certification, stop at this gate with
measured coverage and the concrete remaining work. Do not silently extend the
effort or relax the source standard to reach a chosen recovery percentage.
This retrieval budget is a proposal for the next pass, not work started now.

Freeze the rules and source manifests before inspecting revised returns.
For every historical company-month in 2022 through the existing September
2026 cutoff, either produce an accession/period/scope-qualified value or retain
the existing missing-value treatment. No copying an interpretation across
filings without support; no later restatements at earlier dates; no unsupported
assumptions about preferred claims or participating securities. Apply rules to
the entire cohort, retaining every failure and documenting coverage by date
and company. Do not choose symbols or periods by return improvement.

Proceed to evaluation only if the same general rules pass the fixtures,
reconcile every changed value and operate on the full cohort without extending
the manually hardcoded sample. A low-coverage result is still useful evidence
and may end this candidate.

## One fixed comparison after the data gate

Preserve the existing score and all six signal definitions, portfolio size,
weights, whole-share sizing, $10,000 starting capital, $2,000 reserve, cash lock,
loss halt, corporate-action scenarios and base/stress costs. Change only the
qualified financial numerator extraction; do not add signals or train a model.
Preserve the original snapshots and store the revised inputs separately.

Run the same declared 2022–2023 and 2024–September 2026 account windows and
references once. Report all windows and corporate-action sensitivities;
do not select the favorable one. Show net profit, annualized returns,
drawdown, halts, turnover, changed inputs, and the advantage relative to the
matched reference. Use the previously fixed uncertainty method.

An attractive candidate must survive stressed costs and the declared account
risk rules and show improved evidence for selection advantage. Merely exceeding
cash interest in the already-seen market period is insufficient. If the change
only improves data quality, retain that engineering improvement but make no
performance claim. If it worsens results, record the result without reverting
correct accounting to preserve an attractive backtest.

All these years are already observed. This is a controlled exploratory
comparison, not a fresh out-of-sample result. Freeze any candidate before a
prospective paper test; this proposal authorizes no live trading or automation.
