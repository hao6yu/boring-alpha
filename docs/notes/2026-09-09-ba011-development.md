# BA-011 development result: fail and close this round

Completed September 9, 2026 America/Chicago (September 10 UTC).
**The single authorized late-day MES test failed.** The $5,000 pilot halted
below its capital floor in July 2021. The unrestricted diagnostic also lost
money after costs over 2021–2023. No 2024–2025 price files or strategy results
were opened for this experiment.

The [protocol](../strategies/BA-011.md) was registered in commit `4ca2c83` before
this candidate's return calculation. The tested code was frozen in `77789ba`
before the run. There was one rule set, with no parameter search or revision
after seeing returns. The prior paper-only screen was inconclusive about
single-instrument economics; this test measures that missing quantity directly.

## Fixed strategy and results

Use the sign of the move from the preceding full session's 15:59 close to
today's 15:29 close. Long if positive, short otherwise. Enter one MES contract
at 15:31 open and exit at 16:00 open, subject to the account drawdown exit.
Abstain on contract changes or unavailable/non-full predecessors. There is no
additional technical stop or magnitude filter.

All figures span January 2021 through December 2023, with no annual account reset.

| Model | Trades | Gross P&L | Trading friction | Data fees | Net P&L | Ending equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Base pilot | 139 | −$232.50 | $517.08 | $55.80 | **−$805.38** | $4,194.62 |
| Pilot, double slippage | 110 | −$68.75 | $684.20 | $55.80 | **−$808.75** | $4,191.25 |
| Base, account limits ignored | 732 | $2,301.25 | $2,723.04 | $55.80 | **−$477.59** | $4,522.41 |
| Double slippage, account limits ignored | 732 | $2,301.25 | $4,553.04 | $55.80 | **−$2,307.59** | $2,692.41 |

The base pilot halted **July 27, 2021**, at **$4,239.57**, below the registered
$4,240 capital floor. The halt was a capital-floor event, not a $1,000 drawdown
trigger. Continuing monthly data fees then reduced equity by another $44.95.
The stress pilot reached the capital floor on June 15, 2021; its post-halt
data fees were $46.50. Neither pilot resumed trading.

The 732-trade unrestricted base diagnostic averages **$3.14 gross per trade**,
below **$3.72 round-trip trading friction**, even before monthly data fees.
It lost 9.55% of initial account equity over the full three years. Its annual
net P&L was −$962.50 in 2021, +$742.50 in 2022, and −$257.59 in 2023.
Doubling slippage adds exactly $2.50 × 732 = $1,830 of costs to the same trades.
Positive gross movement therefore supplies no net edge under the fixed assumptions.

For context, the separate hypothetical 4% and 6% cash accounts gain $624.32 and
$955.08 over three years. These are benchmark scenarios, not historical deposit
products or a claim about available guaranteed returns.

## Risk and evidence limits

The base pilot's largest observed minute-close/flat liquidation drawdown was
$900.89, including later data fees. The unrestricted base diagnostic reached
$1,354.86; stress unrestricted reached $2,403.84. These account-path measurements
are model estimates, not execution guarantees. The conservative intrabar OHLC
envelope is reported separately and does not reconstruct tick ordering.

The worst base-pilot trade lost $117.47. The unrestricted base diagnostic's worst
trade lost $318.72. Its five largest winners totaled $1,170.15, or 8.11% of all
positive trade P&L. The [chart](../../experiments/BA-011/20260910-first-run/development/overview.png)
shows daily closing paths; the account halt uses minute-close/flat liquidation
equity instead.

Base costs are $0.61 per side plus one adverse $1.25 tick per fill; stress doubles
slippage. Data costs are $1.55/month, including after halt. Idle cash earns zero;
taxes and additional hosting/electricity are excluded. Historical/account-specific
margin, executable quotes and actual fills remain unverified. The one-minute
entry delay and account limits make this an implementation of the published
hypothesis, not an exact replication of its portfolio results.

## Data and verification

Only 2021–2023 source partitions were read: 1,060,530 raw bars, retaining
292,859 bars across 749 full sessions. Every session contains 391 bars, including
the 16:00 opening execution bar; there are no missing minutes. Hashes, prices,
volume, chronology, contract mappings and calendar references reconcile.

Seventeen sessions were excluded by fixed pre-entry reference rules: one
unavailable initial close, 12 contract changes and four preceding early closes.
The unrestricted models therefore have exactly 732 trades. References carry
correctly across December–January and never subtract different contracts.

Validation: **141 tests and 34 subtests passed**, including the existing raw
audit/accounting checks and 44 new engine/adapter tests. Independent review
reconciled report and daily/trade ledger arithmetic. The plot was rendered and
visually checked. No additional data spending or account changes occurred.

Preserved local artifacts:

- [Input manifest](../../data/futures/ba011-inputs/20260910T043738915285Z/manifest.json)
- [Development report](../../experiments/BA-011/20260910-first-run/development/report.json)
- [Daily ledger](../../experiments/BA-011/20260910-first-run/development/day-ledger.jsonl)
- [Trade ledger](../../experiments/BA-011/20260910-first-run/development/trade-ledger.jsonl)

| Artifact | SHA-256 |
| --- | --- |
| Protocol | `08323b44f643b0fb4a18994810b0428aebfd1806b8c1144137bbec143313ffae` |
| Engine | `07eff64257e1746582367f44c1761f450e364f129356fd9a82c588ce9708b2f4` |
| Adapter | `ede8bdd7c7325647457ffa0029a3a8cc097428b2306fbf54efcbc2245f49d366` |
| Input manifest | `540593dffd3fde22c607cf74026c7248e3fc4c3f08919b972c8e0c50101d29c1` |
| Report | `2ff7f3e231435c311f903826c3261917722d8aea5f00fe3c5145dc66b73b34d9` |

The report contains calendar, dependency and ledger hashes. Raw data and generated
experiment artifacts remain outside Git. The runner refuses to overwrite a run.

```sh
# Intentional reproduction only: a new output directory is required.
.venv/bin/python tools/ba011.py \
  --input data/futures/ba011-inputs/20260910T043738915285Z/manifest.json \
  --stage development --output-root experiments/BA-011/reproduction
```

## Decision

Retire BA-011 version 1 and end this reopened research round. Do not relax the
capital floor, lower costs, reverse the signal, add filters, or open 2024–2025
to seek a rescue. This outcome applies to this fixed candidate and account model;
it does not establish that all quantitative trading is unprofitable.

No follow-up strategy, data purchase, paper adapter or live deployment is queued.
