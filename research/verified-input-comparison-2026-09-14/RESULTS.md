# Verified-input comparison: better data did not improve returns

The already-authorized before/after comparison is complete. Applying all 189 verified repairs lowers net profit in both periods. Recent stock selection falls further behind the matched reference. The improved source coverage is useful research infrastructure, but this is not an improved income strategy.

## Why the earlier work stopped

The assistant incorrectly treated a 28/28 extraction-completeness gate as a prerequisite for any return comparison. The original fixed score already assigns missing financial features a neutral contribution. We can therefore test all verified repairs while leaving unqualified values missing, with exactly the same cohort and strategy rules. No further user information or account access was needed.

The earlier failed gate is preserved in the [accounting follow-up](../financial-fix-comparison-2026-09-14/RESULTS.md). It still prevents a claim that extraction is complete. Whirlpool January 2026 earnings remain missing in both variants. No tolerance was widened and no company/month was removed. The limited comparison scope was frozen before evaluating revised returns.

## Central cases: $10,000 starting account

These are net of the frozen trading fees and slippage, before taxes, without cash interest or new data charges. The old window is January 3, 2022–December 29, 2023; the recent window is January 2, 2024–September 11, 2026. Recent central results use the previously declared cash1/delay5 conditional settlement assumptions.

| Window / costs | Profit before | Profit after | Change | Annualized before → after | Max drawdown before → after |
|---|---:|---:|---:|---:|---:|
| 2022–2023 / base | $599.63 | $492.68 | −$106.96 | 2.97% → 2.45% | 14.91% → 14.91% |
| 2022–2023 / stress | $390.74 | $381.75 | −$9.00 | 1.95% → 1.90% | 15.07% → 15.07% |
| 2024–2026 / base | $1,675.22 | $1,286.56 | −$388.66 | 5.91% → 4.59% | 7.46% → 7.12% |
| 2024–2026 / stress | $1,453.15 | $1,061.39 | −$391.76 | 5.16% → 3.81% | 8.00% → 7.69% |

No complete account hit the frozen $2,000 trailing-dollar halt. Recent drawdown falls slightly, but the revised stressed return is below the 4% cash hurdle and the revised base return is below 6%. Ending NAV includes unpaid dividend/merger entitlements and final sale proceeds; it is not all immediately withdrawable cash. These are separate accounts starting at $10,000, not one continuous 2022–2026 investment.

## Stock selection, trading and uncertainty

The reference uses the unchanged eligible universe at each account’s own prior-day stock exposure and subtracts its actual dated fee/slippage rate. Positive selection dollars mean the strategy finishes ahead of this diagnostic; negative dollars mean it trails. This reference is not executable and does not adjust for sectors, beta or other factor exposures.

| Window / costs | Selection dollars before → after | Fills before → after | Mean stock exposure before → after | Fees + slippage before → after |
|---|---:|---:|---:|---:|
| old / base | $518.48 → $471.55 | 39 → 43 | 64.41% → 63.17% | $67.58 → $74.07 |
| old / stress | $479.58 → $508.53 | 39 → 43 | 63.78% → 63.26% | $177.88 → $194.73 |
| recent / base | −$247.11 → −$623.69 | 77 → 79 | 61.76% → 61.85% | $134.43 → $137.24 |
| recent / stress | −$245.60 → −$619.19 | 77 → 79 | 62.37% → 62.48% | $356.50 → $362.41 |

In the recent base case, extra fees/slippage account for only $2.81 of the $388.66 decline in profit. The weaker portfolio path, rather than an added data bill, explains most of the difference. Higher trading costs can change later whole-share sizing; base/stress are complete separate simulations. Turnover and every dated trade are retained in the JSON results and account files.

The paired bootstrap resamples the same months in both versions: 2,000 stationary resamples, expected block length 12 months, seed 20260914. It uses 24 old months and 32 complete recent months, excluding unfinished September 2026. The following are mean monthly changes in **basis points**, with 95% intervals; they are not annual-return intervals.

| Window / costs | Strategy return change, after − before | Selection return change, after − before |
|---|---:|---:|
| old / base | -4.070 [-15.774, +5.562] | -1.338 [-13.176, +9.439] |
| old / stress | -0.220 [-11.309, +10.157] | +1.488 [-8.478, +11.454] |
| recent / base | -10.668 [-24.665, +1.346] | -10.539 [-21.837, +0.008] |
| recent / stress | -10.914 [-25.181, +1.304] | -10.663 [-22.102, +0.006] |

All central paired intervals include zero. The recent selection interval’s positive endpoint is very close to zero; this does not justify a strong statistical conclusion in either direction. Individual before/after selection intervals and all monthly observations are saved as well. All these years have been seen, there are few independent market regimes, and intervals do not correct for earlier strategy searches. This test establishes the historical effect of this specific input repair, not future profitability.

## Every declared scenario

All seven old ZIMV cash/receipt scenarios are unchanged from the old strict result because neither version held ZBH at that event. They do not add independent performance evidence. Recent strict accounts remain unresolved from the held PXD conversion on May 3, 2024, in both variants. Their full-period profit and selection values remain null. Conditional completion is explicitly hypothetical about fractional cash and stock availability; it is not verification of actual broker receipts.

| Window / scenario | Before profit | After profit | After annualized | After selection dollars |
|---|---:|---:|---:|---:|
| old / strict-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / strict-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / zero_withheld-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / zero_withheld-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / cash_25.53_2022-03-01-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / cash_25.53_2022-03-01-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / cash_25.53_2022-04-01-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / cash_25.53_2022-04-01-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / cash_25.53_withheld-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / cash_25.53_withheld-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / cash_100_2022-03-01-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / cash_100_2022-03-01-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / cash_100_2022-04-01-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / cash_100_2022-04-01-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| old / cash_100_withheld-base | $599.63 | $492.68 | 2.45% | $471.55 |
| old / cash_100_withheld-stress | $390.74 | $381.75 | 1.90% | $508.53 |
| recent / strict-base | unresolved | unresolved | unresolved | unresolved |
| recent / strict-stress | unresolved | unresolved | unresolved | unresolved |
| recent / cash0-delay0-base | $1,562.12 | $1,173.46 | 4.20% | −$753.19 |
| recent / cash0-delay0-stress | $1,340.05 | $948.29 | 3.42% | −$746.72 |
| recent / cash0-delay5-base | $1,562.12 | $1,173.46 | 4.20% | −$753.19 |
| recent / cash0-delay5-stress | $1,340.05 | $948.29 | 3.42% | −$746.72 |
| recent / cash1-delay0-base | $1,675.22 | $1,286.56 | 4.59% | −$623.69 |
| recent / cash1-delay0-stress | $1,453.15 | $1,061.39 | 3.81% | −$619.19 |
| recent / cash1-delay5-base | $1,675.22 | $1,286.56 | 4.59% | −$623.69 |
| recent / cash1-delay5-stress | $1,453.15 | $1,061.39 | 3.81% | −$619.19 |
| recent / cash1.25-delay0-base | $1,703.50 | $1,314.84 | 4.69% | −$591.37 |
| recent / cash1.25-delay0-stress | $1,481.43 | $1,089.67 | 3.91% | −$587.35 |
| recent / cash1.25-delay5-base | $1,703.50 | $1,314.84 | 4.69% | −$591.37 |
| recent / cash1.25-delay5-stress | $1,481.43 | $1,089.67 | 3.91% | −$587.35 |

All 12 recent conditional cases earn less after repairs and trail the matched reference. Results are not selected for the best settlement assumption. No incomplete account was dropped or converted to a cash-only result.

## Data and verification

All 5,700 original company-month slots remain. Every one of the 189 recovered fields enters its eligible feature slot: 86 old and 103 recent. There are 142 affected company-months across 13 issuers. Market-cap denominators, the other four features, eligibility, score weights, ranking rules, prices and portfolio policies are unchanged. Cross-sectional ranks can change for issuers whose own inputs were not repaired. Entry lists change in 8 of 24 old months and 13 of 33 recent months; retention lists change in 16 and 17 months respectively.

Book-equity coverage rises from 39.5% to 41.0%, and trailing-earnings coverage from 43.7% to 45.5%. Coverage remains limited. The preceding numeric source audit verified all 189 repairs; this comparison does not claim to have repaired every missing input.

30 baseline account cases exactly reproduce their saved objects. Across all 60 configured before/after replays, 56 are complete and four retain explicit unresolved prefixes. Independent Decimal ledger checks reconcile 32,596 priced daily observations and recompute 3,284 fills across those cases. There are 32 distinct serialized account payloads; repeated scenarios are not independent tests. Frozen top-decile entry membership, position caps, cash, whole-share units, costs and complete-period summary metrics are checked.

The input panels and schedules were frozen before revised account evaluation. All 151 protected prior artifacts and frozen source hashes remain unchanged. A documented adapter restored the original completion benchmark’s floating-point summation order after a 1.11e-16 weight mismatch; account objects, signals and economic assumptions were unchanged. The original frozen code and failure stage are preserved in `adapter-freeze.json`.

**New network data requests: 0. New paid data: $0. Model fits: 0. Parameter searches: 0.**

## Decision

Keep the verified repairs as a separately versioned research input and preserve the original baseline for comparison. Do not discard accurate inputs just because the older missing-data version backtests better. This round did not improve the strategy’s return case and does not justify a funded bot or capital scaling.

The input-repair question is now answered. A future, locked strategy-versus-control paper test could assess signal availability and execution, but it has not been started or scheduled and a short paper run would not prove annual outperformance. No further parser loop or vendor search is needed to finish this comparison.
