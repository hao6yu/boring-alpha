# Earnings-language experiment v1

**Stopped at the training-sample gate. Profitability is untested.**

The final panel contains 175 usable 2020 training observations, 200 validation
observations, and 378 events across 57 issuers qualified before evaluation
entry. The frozen training minimum is 200. Perfect success from the nine
remaining planned queries could raise 175 only to 199, so they were not
acquired. No model was fitted. Evaluation targets remain masked, and no account
returns were calculated. Only development labels allowed by policy were calculated.

- [Human-readable result](../../docs/notes/2026-09-10-equity-event-test.md)
- [Machine-readable result](test-result.json)
- [Admission decision](source-readiness.json)
- [Frozen experiment policy](experiment-policy.json)
- [Final panel inventory](panel-inventory.json)
- [Final SEC source freeze](sec-freeze.json)
- [Source feature audit](feature-source-audit.json)
- [Remaining-query upper bound](sec-training-feasibility-refined.json)
- [CADE identity rejection](cade-provider-identity-rejection.json)
- [Corporate-action evidence](corporate-action-evidence.json)
- [Price-source conflicts](price-source-exceptions.json)
- [Quoted data expense](data-expense.json)

Original documents, licensed price files, detailed source features, and the
development panel remain in ignored local storage under
`data/snapshots/equity-event-test-2026-09-10/`. The earlier availability pilot
and repair artifacts were preserved. Their PTN follow-up passes 97/100; that
availability result does not override this separate training-sample failure.

Rebuild the panel locally without network requests:

```sh
.venv/bin/python research/equity-event-test-2026-09-10/panel.py
```

The panel reuses only an exactly matching, hash-verified audited extraction.
Rebuilding may update artifact hashes; do not treat old admission records as
valid for a changed panel. `run_experiment.py freeze` refuses fitting while
`source-readiness.json` is false. There is no scheduled download or future run.
