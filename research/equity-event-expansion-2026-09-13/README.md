# Earnings-language experiment: fixed 200-company expansion

**Completed 2026-09-13: do not advance to a pilot.** The text model returned
5.42% annually under base costs and 2.05% under stressed costs. Both fail the
required 6% hurdle. The full-suite status remains UNRESOLVED because of one
matched-control input gap; the scored-model accounts are complete and their
known failures are decisive. See [the results and limitations](RESULTS.md).

The following records the protocol registered before fitting and evaluation.

The user authorized this continuation after the original 100-company study
stopped at 175 usable training events, below its 200-event minimum. The original
study is preserved in commit `b579208`; its profitability remains untested.

This study extends the same original 2019-Q3 hash ranking to its first **200
eligible companies**, retaining the original 100 and all failed quarterly slots.
The 3,200 slots cover 2020–2023. Company selection uses original 2019 documents,
not subsequent returns, liquidity, survival, or convenient data availability.
The existing model, features, years, trading rules, costs, and pass thresholds
are unchanged. The larger cohort addresses source attrition; the 200-event
minimum is an operational floor, not proof of adequate statistical power.

The sole statistical design change is cohort breadth. This is a new exploratory
experiment prompted by observed coverage, not an independent confirmation of
the first experiment. At registration no evaluation returns had been examined. All 2024–2025
equity strategy prices remain reserved.

Collection is capped at 9,000 additional SEC attempts and three hours from
registration, using the existing limit below four starts per second. Successful
original-source caches are reused with checksum verification. The SEC's
[developer guidance](https://www.sec.gov/about/developer-resources) permits at
most ten requests per second across a user; access denial stops collection.
No complete-submission TXT fallback is enabled.

The price budget is at most 110 new requests through the existing free Tiingo
account, respecting 50/hour, 1,000/day and 500 unique symbols/month. Newly
selected seed symbols are requested in fixed rank order, followed by missing
original seed symbols and contemporaneous identifiers. Every failed response
remains visible. No paid data or subscription is authorized in this expansion.

Before model fitting, freeze the full roster, finish the bounded source pass,
audit identity and action conflicts, and verify the unchanged minimums. Do not
stop acquiring the registered cohort merely because 200 training observations
have appeared. Training/validation labels may be calculated under the existing
cutoffs; evaluation labels remain masked until model and forecasts are frozen.
If a gate fails or source/accounting uncertainty prevents a valid result, retain
the failure and stop. Do not alter thresholds or nominate another variation.

Raw documents, provider data, detailed features, and live collection caches
remain in ignored local storage. No live trading or account changes follow from
a backtest pass.
