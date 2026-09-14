# Financial-input research closeout

Completed September 14, 2026. The input audit, qualified extraction work and
controlled before/after comparison are finished for this research round.
This does not mean the financial dataset is complete or that the strategy is
ready for a funded account.

## Finding

The original account calculations reproduce exactly using their original
inputs. Missing financial features received neutral scores. Recovering 189
verified financial fields changed the cross-sectional rankings and trades,
reducing profit in both tested periods. The original numbers were results for
the older input version, not reliable forecasts of future earnings.

Each period starts with a separate $10,000 account. Results include the frozen
fees and slippage, exclude taxes and cash interest, and include receivables in
ending account value.

| Period / costs | Original profit | Repaired profit | Original annualized | Repaired annualized |
|---|---:|---:|---:|---:|
| 2022–2023 / base | $599.63 | $492.68 | 2.97% | 2.45% |
| 2022–2023 / stressed | $390.74 | $381.75 | 1.95% | 1.90% |
| 2024–September 11, 2026 / base | $1,675.22 | $1,286.56 | 5.91% | 4.59% |
| 2024–September 11, 2026 / stressed | $1,453.15 | $1,061.39 | 5.16% | 3.81% |

Recent figures use the previously frozen central conditional corporate-action
settlement case. Recent drawdowns improve slightly to 7.12%/7.69%, but stock
selection trails the matched reference by $623.69/$619.19 after repairs.
Every one of the 12 declared recent settlement/cost scenarios earns less after
repairs and trails that reference. The reference is an attribution diagnostic,
not an executable portfolio or a full factor-risk adjustment.

The paired monthly bootstrap intervals include zero in all central cases.
Already-seen years, a limited historical cohort and prior strategy searches
prevent a claim of a dependable trading advantage.

## Preserved evidence and corrections

The full chronology is committed so the later conclusion does not erase the
earlier claims:

1. [Initial financial-input audit](../../research/financial-input-audit-2026-09-14/RESULTS.md).
2. [Extraction v2](../../research/financial-extraction-v2-2026-09-14/RESULTS.md)
   and its [correction to the initial recovery claim](../../research/financial-extraction-v2-2026-09-14/ERRATA.md).
3. [Accounting follow-up](../../research/financial-fix-comparison-2026-09-14/RESULTS.md),
   including the 27/28 fixture result and verified source provenance.
4. [Completed input comparison](../../research/verified-input-comparison-2026-09-14/RESULTS.md),
   with every declared scenario, uncertainty estimates and frozen rules.

The assistant's earlier requirement to resolve all 28 fixtures before any
comparison was too broad. The fixed model already supports missing financial
features. A separately frozen comparison could use every verified repair while
retaining every unqualified field as missing. The failed completeness gate is
preserved; it was not silently changed into a passing extraction result.

All 5,700 company-month slots remain. Book/earnings coverage is still only
41.0%/45.5%. Whirlpool January 2026 earnings remain unqualified. Strict recent
accounts remain unresolved at the PXD conversion; hypothetical settlement
completion is not verification of actual broker receipts.

## Verification and repository scope

Thirty original account cases reproduced exactly. All 60 configured before/after
replays were evaluated: 56 complete cases and four explicit unresolved prefixes.
Independent ledger checks reconciled 32,596 priced daily observations and
recomputed 3,284 fills across those cases. Repeated scenarios are not independent
performance evidence. All 151 protected prior artifacts remain unchanged.

The repository contains source code, reports, corrections, protocols, input
change records, results, verification and artifact hashes. Downloaded filings,
market-data snapshots and full account/reference ledgers remain in the existing
ignored `data/snapshots/` directories. A fresh clone requires those local
snapshots to reproduce the entire experiment; hashes identify the exact inputs.
Credentials are excluded from the commit.

Pre-commit review checked 264 artifact-manifest entries, all comparison freezes,
Python/JSON syntax, local document links and credential patterns. The sole
whitespace finding is an extra final blank line in the already-frozen
`financial-fix-comparison-2026-09-14/extract_v3.py`; it is preserved to keep the
historical source hashes valid.

The comparison used zero new network data requests, paid data, model fits or
parameter searches. No new simulations are needed to close this round.

## Decision

Retain the verified repairs as a versioned research input. Preserve the
original baseline as its comparator; do not prefer missing data because its
seen backtest is higher. The current evidence does not justify funding or
scaling this strategy. No live orders, paper monitor, data acquisition or
follow-on experiment have been started by this closeout.
