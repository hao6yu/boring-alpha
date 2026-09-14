# Fixed 100-stock monthly model comparison

**The registered linear/tree/fixed-score comparison has been run on the identified eligible subset. These are exploratory 2022–2023 results, not a validation pass or live-trading approval.**

The original 100 security slots remain in all 5,500 company-month records. Diagnostic entry eligibility ranges from 88 to 89 names per month. The predefined aggregate-coverage gate passes.

## Account outcomes

Each account starts with $10,000, holds whole shares, keeps a $2,000 settled-cash reserve and has a permanent $2,000 trailing dollar-loss halt. Base/stress slippage is 10/50 bps per side plus the preserved IBKR Pro Fixed fee scenario. These are historical close-based execution proxies; actual account fees and fills are not established.

| Ranking | Costs | Ending value | Net profit | Annualized return | Max drawdown | Halt date |
|---|---|---:|---:|---:|---:|---|
| ridge | base | unresolved | unresolved | unresolved | unresolved | none |
| ridge | stress | unresolved | unresolved | unresolved | unresolved | none |
| tree | base | $9,680.16 | $-319.84 | -1.62% | 18.73% | none |
| tree | stress | $9,349.36 | $-650.64 | -3.33% | 18.79% | none |
| fixed | base | $10,599.63 | $599.63 | 2.97% | 14.91% | none |
| fixed | stress | $10,390.74 | $390.74 | 1.95% | 15.07% | none |

Missing held marks or unqualified stock-distribution delivery/fractional cash make an account incomplete. No complete return is fabricated for such an account. Known unpaid dividends/merger claims remain in NAV but are not spendable; their payment dates were not guessed. Sale proceeds stay locked for seven calendar days. No tax estimate is included.

## Does the trained tree improve stock ranking?

The metric below is within-month Spearman correlation between predicted rank and realized excess return. Higher is better; this is not an account return. Excess returns subtract the mean of known eligible labels in that month.

| Ranking | 2022 mean correlation | 2023 mean correlation | Both years |
|---|---:|---:|---:|
| ridge | -0.1394 | 0.0315 | -0.0539 |
| tree | -0.0959 | 0.0520 | -0.0219 |
| fixed | 0.0530 | 0.0367 | 0.0448 |
| tree_minus_ridge | 0.0436 | 0.0205 | 0.0320 |

The 95% stationary month-block interval for the tree-minus-linear difference is [-0.0149, 0.0775]. It uses 2,000 resamples and expected block length 12 months. With only 24 already familiar market months, this interval has limited power and cannot establish a durable edge.

## Data and test scope

- Fixed cohort: one deterministic 100-security selection from the archived April 2018 roster; no survivor replacements or later IPO additions.
- Initial training: 31 monthly labels, June 2019–December 2021; expanding annual refits for 2022 and 2023, using only completed earlier labels.
- Models: Ridge alpha 100; one fixed histogram gradient boosting configuration; one fixed six-signal score. No hyperparameter search or outcome-driven feature changes.
- SEC filing availability is lagged two NYSE sessions. Market cap uses a split-corrected reported-share proxy, not exact contemporaneous capitalization. Unidentified common-book or common-income fields stay missing with neutral ranks and missing indicators.
- Reference return features reinvest distributions fractionally at the reference close. The whole-share account is separate. Current backfilled vendor data are not archived real-time data vintages.
- Previous company failures and ticker changes are retained. Modern FOXA is excluded from the old Twenty-First Century Fox issuer. Sealed Air’s initial incorrect identifier was rejected before any features or models used it.
- LyondellBasell’s January 2019 $15 vendor distribution is removed: it belongs to a subsidiary’s convertible special stock. Its June 2022 $6.39 common distribution is supported by the issuer.
- The 2024–2025 strategy windows remain unopened. No broker order, new subscription or new cash data purchase occurred.

This attempt made 112 additional Tiingo requests and reused available sample data. Acquisition obeyed the hourly quota; waiting time is not evidence of additional analysis. Source snapshots, input hashes, model refit boundaries and account replays are retained locally.

## Interpretation

The tree account did not beat the lower end of the user’s 4–6% cash hurdle. This version does not justify funding or promotion.
The tree’s measured ranking advantage is not clearly separated from zero by the planned interval. Do not claim that the more complex model has demonstrated a reliable improvement.

These findings concern this fixed implementation and dataset. They do not establish that quantitative trading generally works or fails. No parameter changes or reserved-year test are queued automatically.

Evidence: `panel-coverage.json`, `fit-audit.json`, `evaluation-start.json`, `evaluation-result.json`, `verification.json`, and `account-verification.json`.

Primary action sources: [LyondellBasell subsidiary distribution](https://www.lyondellbasell.com/en/news-events/corporate--financial-news/a.-schulman-inc2.-a-lyondellbasell-subsidiary-announces-convertible-special-stock-dividend), [Cerner exchange notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-127), [Kansas City Southern completion](https://www.sec.gov/Archives/edgar/data/54480/000119312521356252/d25745d8k.htm). Further reviewed facts and URLs are in `reviewed_sources.py`.

[Account paths and the specific Ridge spinoff gap](ACCOUNT_NOTES.md) provide additional detail derived from the frozen outputs.
