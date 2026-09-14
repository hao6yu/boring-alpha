# Monthly stock-selection data and experiment proposal

[Read the proposal](PROPOSAL.md).

The paid option is parked following the user's request to consider Databento
and free alternatives. [Read the free-source comparison](FREE_SOURCES.md).
The earlier $69 Sharadar proposal remains documented, with no purchase approved.
Data cost incurred for this proposal so far: $0.

The public Apple demo confirms six query paths. `source-and-sample-evidence.json`
records endpoints, parameters, response status, hashes and counts. Raw market
samples and documentation snapshots remain in the gitignored
`data/snapshots/ml-stock-selection-design-2026-09-13/` directory. Read the
provider's retention/termination rules before any paid acquisition.

`probe_public_sample.py` uses only the vendor's published demo credential,
system curl with TLS verification, and small date-bounded queries. It does not
read user credentials, create an account, purchase data, fit models, compute
strategy returns, or open reserved 2024–2025 strategy prices.

The proposal fixes a historical-membership universe and one linear/tree model
comparison. It still needs a paid-data manifest and pre-run code freeze; it is
not a completed profitability experiment or a validation pass.
