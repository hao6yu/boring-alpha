# Ten-company financial-input audit

Read [RESULTS.md](RESULTS.md) for the decision and limitations. This folder is a
separate data-quality audit. It does not change the model or any baseline file.

The sample and scope were frozen in `protocol.json` before additional filing
inspection. `reviewed-evidence.json` records manually reviewed source mappings;
`extraction-freeze.json` locks those mappings before the coverage replay.
`source-manifest.json` identifies the cached source payloads and web excerpts.

From the repository root, reproduce the offline audit with the existing venv:

```sh
.venv/bin/python research/financial-input-audit-2026-09-14/audit.py
.venv/bin/python research/financial-input-audit-2026-09-14/verify.py
```

The original SEC companyfacts, submission metadata and fundamental snapshots
must be present at the hash-checked paths. They and the web excerpts remain in
gitignored `data/snapshots`. Public source URLs accompany every new value.
Browser-only reads are summarized rather than archived as original HTML.

`build_evidence.py` records how the certificates were assembled from manually
reviewed values. It is not an automatic filing parser. Do not regenerate the
freeze to silently accept changed evidence; use a separately versioned audit.

The scripts only verify financial inputs and write results in this folder.
They make no network calls, read no market-price features, fit no model, and
place no orders. Original panel bytes are hashed only to check preservation.
The accounting interpretation itself remains a manual review assertion.
