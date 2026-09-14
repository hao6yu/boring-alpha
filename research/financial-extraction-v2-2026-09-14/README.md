# Financial extraction v2 — bounded diagnostic

Start with [RESULTS.md](RESULTS.md) and [ERRATA.md](ERRATA.md).
Decision: **STOP_DATA_GATE_FAILED**. No revised profitability comparison ran.

The protocol and filing plan were frozen before implementation. The parser
and replay code were frozen after fixture development and before broader
validation. Do not overwrite those frozen files to make the old run pass.

From the repository root, replay the saved local evidence:

```sh
.venv/bin/python research/financial-extraction-v2-2026-09-14/process.py
.venv/bin/python research/financial-extraction-v2-2026-09-14/verify.py
.venv/bin/python research/financial-extraction-v2-2026-09-14/audit_provenance.py
```

These commands use existing local data, perform no network requests, and run
no trading simulation. `prepare.py` is the historical setup script and refuses
to overwrite the frozen protocol. `capture_server.py` and `capture_browser.js`
document the completed browser acquisition; do not restart it for this run.

Tracked outputs contain counts, source metadata, hashes, gate results, and
verification. Large original DOM captures and replay payloads live under
`data/snapshots/financial-extraction-v2-2026-09-14/`, which is gitignored.
The retrieval manifest records both complete and rejected partial captures.
Those local snapshots are required for replay from another checkout.

The revised monthly JSON is a diagnostic payload, not a production replacement
for the existing panel. It preserves original fields, including old
`missing_reasons` annotations; use `change-provenance.json` and `coverage.json`
to interpret repairs. No strategy feature panel consumes these changes.
Counts measure rule-qualified candidates, subject to the failed overall data
gate; they are not a claim that every accounting structure is now supported.
