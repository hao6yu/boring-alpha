# Fixed stock momentum diagnostic: negative observed result

The $10,000 momentum account lost **$1,938.22 under base costs** and **$1,976.70 under stressed costs**. Both hit the $2,000 trailing-loss halt on May 9, 2022 and liquidated on May 10. **Shelve this implementation.** These results do not support funding or tuning it on the same history.

The momentum accounts have complete conditional accounting. The full comparison with unranked stocks remains **unresolved** because two of the 20 predeclared control baskets need an unimplemented WWE-to-TKO share transition and absent TKO prices. No controls were dropped to produce a more favorable comparison.

## Measured account economics

Evaluation: January 3, 2022–December 29, 2023, 501 trading sessions. After the halt, the accounts remain in cash and verified receivables for the rest of the window.

| Metric | Base costs | Stressed costs |
|---|---:|---:|
| Ending account value | $8,061.78 | $8,023.30 |
| Net profit / loss | $-1,938.22 | $-1,976.70 |
| Total return | -19.38% | -19.77% |
| Annualized return over full window | -10.27% | -10.48% |
| Maximum peak-to-trough drawdown | 20.28% | 20.34% |
| Maximum dollar drawdown | $2,028.48 | $2,034.10 |
| Closed positions | 13 | 12 |
| Commissions and regulatory fees | $26.65 | $24.60 |
| Assumed slippage | $16.56 | $76.45 |
| Profit / loss adding back costs on identical fills | $-1,895.01 | $-1,875.65 |
| Ending settled cash | $8,037.16 | $7,998.68 |
| Ending dividend receivables | $24.62 | $24.62 |

Costs are not the principal explanation: even adding back every modeled fee and slippage charge leaves a base loss of $1,895.01. This is an accounting decomposition of the same fills, not a new zero-cost simulation. Stress costs also change affordable entries, so the accounts have different trades.

The trailing-loss threshold is observed at closing marks, with liquidation at the next executable session. The $28.48/$34.10 overshoot demonstrates why it is not a guaranteed loss ceiling. The subsequent liquidation close recovered part of that drawdown. Only one completed position was profitable in each cost case; all stock positions were closed by May 10, 2022.

Constant 4% and 6% annual cash reference scenarios end at **$10,811.35** and **$11,228.83** over the same 726 inclusive calendar days. These are comparison assumptions, not historical yields or an account-specific available rate. Strategy cash earns zero in this registered test; tax and operating expenses are excluded. Annualized returns include the long inactive period after the halt.

![Simulated account values](/Users/haoyu/development/boring-alpha/research/equity-momentum-diagnostic-2026-09-13/account-value.png)

## What was fixed before calculation

Rank the same 200 historical incumbent issuers by 11 months of adjusted-close return, skipping the latest month. For January 2022, the score is November 30, 2021 adjusted close divided by December 31, 2020 adjusted close, minus one. Enter the top 10% of eligible names and retain holdings while they remain in the top 20%, with monthly review, ceiling-rounded rank bands, and predetermined tie-breaking.

Use at most ten stock positions. Each new position receives at most $800, 8% of prior account value, and available settled cash above a $2,000 reserve. Whole-share quantities are committed before the entry session; a budget-based closing-limit proxy can cancel an entry. Retained positions drift without monthly resizing. Exiting positions occupy a slot through that day's fill; replacement waits until a later monthly review. Sale proceeds are locked for seven calendar days in the model. The permanent $2,000 trailing dollar-loss halt and final-window liquidation apply to every account.

Base/stress slippage is 10/50 basis points per side, plus the archived IBKR Pro Fixed commission/regulatory schedule. It is a current-rate counterfactual, not a reconstruction of historical fees or confirmation of the user's tariff. Verified corporate-action entitlements enter account value; spendability requires separate evidence. Unknown dividend payment dates leave receivables unavailable for reinvestment. No leverage or cash interest is used.

The lagged-return definition comes from [Open Source Asset Pricing's Mom12m implementation](https://github.com/OpenSourceAP/CrossSection/blob/master/Signals/pyCode/Predictors/Mom12m.py); this version requires complete formation history instead of imputing missing returns as zero. Separate entry and retention thresholds follow the trading-cost principle studied by [Novy-Marx and Velikov](https://doi.org/10.1093/rfs/hhv063). The long-only account, fixed cohort, and sizing are our adaptation, not a replication or a claim to reproduce published returns. Momentum is related to previously explored ETF, crypto, and futures families in this repository.

## Coverage and all controls

All **4,800 issuer-month slots** are preserved: 2,516 ready, 491 known listing-ineligible, 1,131 liquidity-ineligible, and **662 unresolved** (645 liquidity-price gaps, 17 formation-price gaps). Monthly qualified breadth ranges from 97 to 116 issuers. Missing slots are not classified as economically ineligible. The measured account is conditional on this qualified subset; missing opportunities could change rankings and trades. A fixed 2019 incumbent cohort is not a comprehensive, survivorship-free US market universe.

Each control is a separate simulated $10,000 account with the same eligibility, account rules, entry/retention fractions, costs and halt. Momentum order is replaced by a stable hash order using predeclared seeds 0–19. These 20 hypothetical accounts are comparison references, not a proposed pooled $200,000 portfolio.

| Control seed | Base ending value | Base status | Stress ending value | Stress status |
|---|---:|---|---:|---|
| 00 | Unresolved | Incomplete | Unresolved | Incomplete |
| 01 | $8,043.07 | Halted | $7,990.69 | Halted |
| 02 | $10,423.42 | Completed | $10,352.92 | Completed |
| 03 | $8,285.72 | Halted | $8,238.85 | Halted |
| 04 | $9,638.94 | Completed | $9,542.42 | Completed |
| 05 | $8,073.82 | Halted | $8,021.28 | Halted |
| 06 | $11,133.99 | Completed | $11,072.36 | Completed |
| 07 | $8,093.89 | Halted | $7,896.53 | Halted |
| 08 | $8,126.16 | Halted | $8,066.07 | Halted |
| 09 | $7,944.55 | Halted | $7,867.90 | Halted |
| 10 | Unresolved | Incomplete | Unresolved | Incomplete |
| 11 | $7,938.07 | Halted | $7,887.91 | Halted |
| 12 | $10,585.92 | Completed | $10,574.33 | Completed |
| 13 | $7,904.34 | Halted | $7,858.44 | Halted |
| 14 | $7,826.18 | Halted | $7,776.92 | Halted |
| 15 | $8,038.77 | Halted | $7,870.42 | Halted |
| 16 | $10,593.31 | Completed | $10,590.39 | Completed |
| 17 | $7,943.43 | Halted | $7,771.32 | Halted |
| 18 | $8,168.93 | Halted | $8,123.91 | Halted |
| 19 | $9,764.95 | Completed | $9,683.53 | Completed |

Controls 00 and 10, in each cost case, hold 15 old WWE shares at the September 12, 2023 transition. The archived [NYSE removal notice](https://corporate.wwe.com/f/docs/sec-filings/16925127.PDF) records their exchange for TKO shares. The frozen manifest has no TKO history, and the engine cannot silently treat a different issuer as the old security. Their NAVs remain missing from that date. See `control-coverage-gap.json` for the exact source record and hashes.

As registered, no full-ensemble average, paired confidence interval, or ranking-edge conclusion is computed from only the 18 complete controls. The negative momentum account is enough to decline this implementation for the user's objective; it does not resolve momentum's incremental return against the full control set.

## Verification, scope, and decision

Eight synthetic tests passed covering timing, missing history, rank bands, retention, cash settlement, fixed entry quantities, position/cash limits, halt execution, and fractional splits. A separate verifier recalculated 2,516 admitted scores and all 504 monthly model rankings from the frozen inputs and underlying prices. It also reconciled **38 complete accounts** (two momentum plus 36 controls), and the valid prefixes of four incomplete control runs: 20,734 daily NAV observations and 952 fills. It rechecked 124 raw price-file hashes, fees, cash claims, held units, verified splits, cash mergers, and first halt dates.

For cash-merger controls, the verifier includes merger-terminated lots when reconciling total P&L; the inherited `completed_positions` convenience field counts sell-filled closures only. This does not alter account NAV. Verification uses the same cached evidence and is not external data replication. Strategy code, source adapter code, policy, inputs and result hashes are unchanged. Details: `account-verification.json` and `verify_accounts.py`.

This is one exploratory diagnostic on already-examined 2022–2023 history. The early permanent halt means it does not measure an uninterrupted strategy through 2023. It neither validates a live execution model nor establishes that stock momentum generally fails. Increasing capital, relaxing the halt, changing ranks, or adding an overlay would be new hypotheses, not repairs to this result.

**Decision: shelve this exact implementation; no deployment or further variants are justified by this run.** Preserve the partial comparison and existing failures. A broader claim about the family remains unsupported. Reserved 2024–2025 strategy prices remain unopened.

New paid data: **$0**. Reporting checkpoint: **19.0 minutes** from the recorded start, within the two-hour cap. No new market-data request or purchase was made. The policy was registered at 2026-09-14T00:27:00.270878+00:00; calculation began at 00:32:01 UTC on September 14, 2026. The folder uses the local September 13 date.

Policy SHA-256: `bb794d736f507c5a3ee7838eb73cd993b10dd4a12655f6dd72f69fa7dc3bfaa9`.
