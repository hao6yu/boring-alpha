# BA-012 final bounded feasibility attempt

**Decision: park BA-012.** The revised settlement acquisition did not obtain a
complete panel within the final effort allowance. All 72 monthly sizing cases
remain unresolved. There is no evidence from this attempt that a $5,000 portfolio
is feasible, infeasible, profitable, or able to beat the cash hurdle.

## Scope and stopping decision

The user authorized one final attempt: at most 30 minutes, from
2026-09-10 16:12:18 to 16:42:18 UTC, with cumulative Databento estimates capped
at $1. The scope was a documented data amendment and sizing only. The original
protocol, input panel and result were preserved. No strategy P&L, 2024–2025
holdout prices, account changes, subscriptions or trades were undertaken.

The revised rules were frozen before settlement prices were read. Version 2
replaces October gold maturities with December of the same year and uses actual,
nonintraday settlement updates available by 16:30 Chicago time. It preserves
message timing, update and delete handling, and separately labels legacy
event-time proxies. An eventual final settlement is never substituted using
hindsight. The original sizing, risk and calendar rules remain unchanged.

The initial collector incorrectly rejected HTTP 206. Databento documents that
status as successful partial symbol resolution. This was our transport-handling
error; the failed request's full estimate remains charged to the research
budget. The helper was corrected, and the preplanned fallback requested only
each contract's required date interval.
[Databento error/status documentation](https://databento.com/docs/api-reference-historical/basics/errors).

The fallback comprises 181 queries. All were quoted, and three completed:
6EH0, 6EH1 and 6EH2. Their data transfers took about 21, 11 and 30 seconds,
respectively, before allowing for the per-query metadata quote. At that observed
throughput, the remaining 178 queries could not fit the remaining six minutes.
Acquisition was stopped at 16:35:51 UTC, retaining the fourth request's
reservation. Adding further transport infrastructure or extending the attempt
would defeat its effort limit. This is a stopping decision based on time and
incomplete acquisition, not a claim that settlement history is unavailable.

## Evidence retained

- Three complete, checksummed raw partitions contain 81,972 statistics records.
- The offline adapter selected 187 settlement references across those three
  contracts; it rejected 414 required-contract settlement messages published
  after the fixed cutoff.
- All 187 required references inside the completed query ranges were selected.
  They use modern capture timestamps. No required key in those ranges was lost
  to settlement-selection rules; the sample supports the data path only.
- The panel has 10,024 unfilled required references and no complete joint date.
  This count includes unacquired partitions; it is not a provider coverage-failure
  count: 57 belong to the interrupted query and 9,967 to the unacquired queries.
  Overall coverage is 187 of 10,211 references (1.83%). None of the 72 monthly
  windows is READY.
- The $5,000 sizing report records 72 unresolved cases, zero verified cash
  decisions and zero verified nonzero decisions. It does not run optimization
  on incomplete inputs or classify them as cash.
- Seven focused collector checks and 14 settlement adapter checks passed.
  A separate review found no blocker in HTTP 206 handling or reservation
  accounting. Five original/frozen artifact hashes were reverified unchanged.

## Budget

| Item | Reserved provider estimate, USD |
| --- | ---: |
| Original version 1 acquisition, including failed attempts | 0.162474512840 |
| Rejected grouped statistics request | 0.194647833705 |
| Four narrow requests, including the interrupted fourth | 0.008147433399 |
| **Cumulative total** | **0.365269779944** |

The full narrow plan was quoted at $0.244202017778 and projected cumulative
usage of $0.601324364323. It was affordable under the estimate ceiling; time
was the binding constraint. These figures are provider estimates with
conservative reservations, not an independently verified bill. No acquisition
process or download lock remains active.

## Reproducible records

- Authorization and limit: `research/ba012-stage-a/final-feasibility-attempt.json`
- Frozen amendment: `research/ba012-stage-a/settlement-amendment-v2.json`
- Frozen revised rolls: `research/ba012-stage-a/rolls-v2.json`
- Narrow archive: `data/futures/ba012-settlements/20260910T163244052927Z/manifest.json`
- Adapter output: `research/ba012-stage-a/settlement-inputs-v2.json`
  (`096c328bd3f1cfe701031c9c2f567b722c8bf011c7e9969a93c463e9f98c19da`)
- Final machine-readable outcome: `research/ba012-stage-a/final-feasibility-outcome.json`

Further work is parked. This attempt does not justify a funded pilot or bot.
