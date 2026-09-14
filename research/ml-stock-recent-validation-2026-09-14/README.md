# Recent-window fixed-score validation

The user prefers 2022 through current 2026 as the primary research window.
The already-seen 2022–2023 comparison remains separate from the new evaluation
of January 2, 2024 through September 11, 2026. September 14 was still in
progress when the scope was frozen, so its unfinished daily bar is excluded.

## Current status: scope and endpoint check complete

The [protocol](protocol.json) was saved before requesting recent strategy
prices. It retains the existing 100-security historical cohort, fixed scoring
formula and $10,000 account constraints. It does not select today's AI/tech
winners, change weights or retrain the failed models. Older history remains
useful for later stress checks; this decision does not establish that older
market regimes are obsolete.

The [date probe](date-probe.json) passed. The first three predetermined cohort
symbols, PNR, VFC and CSCO, each returned 1,177 daily rows from January 3,
2022 through September 11, 2026. Three Tiingo requests used existing access;
new paid data cost was $0. These observations establish availability for the
three sampled securities, not full-cohort coverage or profitability.

Acquisition code and scope hashes were recorded before the requests in
`acquisition-freeze.json`; response paths and hashes are in
`price-manifest.json`. Provider payloads remain in the gitignored
`data/snapshots/ml-stock-recent-validation-2026-09-14/` directory. Credentials
are read privately from the existing environment file and are not recorded
in these artifacts.

Full acquisition, updated dated financial inputs, later corporate-action
qualification, account simulation and reference comparisons have not run.
No collector is running in the background. No profitability result is claimed.
The current cohort is fixed from 2018 and does not represent all stocks
available in 2026; recent dates alone do not remove that limitation.

The [Tiingo documentation](https://www.tiingo.com/documentation/end-of-day)
describes historical and latest daily prices, including evening corrections.
Its [Starter limits](https://www.tiingo.com/about/pricing) currently list 50
requests/hour. The subsequent full download should obey those limits and
check actual provider responses; a newer date range does not require a
subscription upgrade by itself.
