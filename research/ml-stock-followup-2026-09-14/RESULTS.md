# Fixed-score benchmark and linear-account follow-up

**The fixed score shows an exploratory selection advantage in this sample, but still misses the 4–6% account-return target. Both trained models remain unattractive under the tested conditions.**

This is the separately authorized, cached-data follow-up to the [original comparison](../ml-stock-comparison-2026-09-14/RESULTS.md). Predictions, source data and original results are unchanged. No model was retrained, no new market data was requested, and no reserved-year strategy prices were opened.

## Fixed score versus ordinary stock exposure

Each reference starts with $10,000. On every day it receives the prior-cut eligible cohort’s equal-mean stock return at the fixed strategy’s actual prior-close stock exposure fraction. It deducts the same dated fee/slippage rate, expressed as a fraction of the strategy’s prior NAV. Uninvested capital and receivables earn zero. This is a fractional attribution reference, not a whole-share executable strategy or a sector/volatility-adjusted alpha estimate.

| Cost case | Fixed-score profit | Matched-exposure reference profit | Fixed minus reference |
|---|---:|---:|---:|
| base | $599.63 | $81.15 | $518.48 |
| stress | $390.74 | -$88.83 | $479.58 |

Both years have a positive average monthly fixed-minus-reference difference. The planned stationary month-block intervals remain wide:

| Cost case | Mean monthly difference | 95% month-block interval | 2022 mean | 2023 mean |
|---|---:|---:|---:|---:|
| base | 0.191 pp | [-0.212, 0.639] pp | 0.248 pp | 0.133 pp |
| stress | 0.180 pp | [-0.198, 0.611] pp | 0.256 pp | 0.105 pp |

The interval uses 2,000 stationary resamples of 24 months with expected block length 12 months. It includes zero in both cost cases. The result is encouraging enough to retain the fixed score as a research lead, but it does not establish a reliable advantage. These market months were already familiar, and this follow-up was chosen after the original outcomes. Sector and other risk tilts can contribute to the difference.

## Twenty unranked account controls

Seeds 0–19 were fixed before these control outcomes. Each ranks the same eligible companies by a persistent hash of seed and issuer ID, independently of scores and realized returns. All use the same $10,000 capital, whole-share sizing, 10% entry/20% retention bands, cash reserve, proceeds lock, costs and permanent loss halt.

**The strict full ensemble remains incomplete:** controls 09 and 13 in each cost case encounter the same ZBH fractional-share cash gap as Ridge. No failed or incomplete control is deleted. The complete-ensemble figures below are conditional on all seven disclosed receipt scenarios.

| Cost case | Mean control profit across receipt scenarios | Controls beaten by fixed score |
|---|---:|---:|
| base | -$416.63 to -$410.63 | 20 of 20 |
| stress | -$537.27 to -$531.27 | 19 of 20 |

These controls share the account rules but are not exact turnover or risk matches:

| Base-cost diagnostic | Fixed score | Mean unranked control |
|---|---:|---:|
| Average stock exposure | 64.41% | 56.21% |
| Purchases | 20 | 9.45 |
| Traded notional | $27,619.14 | $12,962.80 |

Persistent random ranks trade less than the changing fixed score. Three base and four stress controls hit the loss halt. Their lower average exposure also reflects those halts. The separate exposure/cost reference above addresses part of this mismatch. Beating 20 controls is a descriptive result, not a formal p-value or 20 independent economic histories.

## Ridge and the missing spinoff payment

The strict original Ridge account remains unresolved. Six ZBH shares create 0.6 ZIMV share; cached ZIMV data give a March 1, 2022 close of $25.53 and a maximum daily high of $33.44 over the retained 2022–2023 history. Neither establishes the broker’s cash-in-lieu sale or payment.

The protocol tested zero cash, $25.53 per ZIMV share (the ex-date reference), and a deliberately high $100 per ZIMV share. Positive amounts were paid hypothetically on the event date, April 1, or left unspendable through the end. These are seven sensitivity cases, not sourced receipts. Under this account’s six-share holding they correspond to $0, $15.318 or $60.

| Assumed total ZIMV receipt | Ridge base profit | Ridge stress profit | Stress halt |
|---|---:|---:|---|
| $0.00 | -$280.38 | -$1,865.28 | 2022-09-30 |
| $15.32 | -$265.06 | -$574.52 | none |
| $60.00 | -$296.65 | -$434.70 | none |

Changing payment timing among the declared cases did not change their final returns. Changing the amount did change whole-share sizing, and the zero-receipt stress case triggered the September 30, 2022 loss halt. Outcomes are therefore not monotonic in the payment amount: the observed range is not an exhaustive mathematical bound on every possible account path. **Every tested Ridge case loses money.** There is no reason from this sensitivity check to spend more effort pursuing the exact payment to promote Ridge.

## Decision and verification

- Keep the fixed score as the only research lead from this comparison. It shows favorable selection evidence in this limited sample; a longer-history, correctly dated cohort would be the next kind of evidence to consider. No acquisition or follow-on test is queued here.
- Keep the tree and Ridge versions shelved. Neither supports funding under the measured tree result or the disclosed Ridge scenarios.
- The fixed score itself remains below the user’s target: 2.97%/1.95% annualized with 14.91%/15.07% drawdowns under base/stress costs. The benchmark comparison does not turn this into dependable extra income.
- Independent replay passed for 86 distinct account files: 80 complete cases and six valid strict prefixes, 40,314 NAV days and 2,516 fills. Control rank orders, source hashes, cash availability, account sizing, halts and exposure-reference arithmetic were checked.
- New paid data cost: $0. New network market-data requests: 0. New fitted models: 0. Original artifacts and predictions remain byte-for-byte unchanged.

Evidence: `protocol.json`, `run-freeze.json`, `results.json`, `orders.json`, `verification-before.json`, and `verification-after.json`. Full compressed ledgers and reference paths are in the local snapshot directory.

[Benchmark account paths](benchmark-paths.png).
