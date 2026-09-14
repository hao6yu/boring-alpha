# Next experiment: one bounded 100-stock model comparison

**Use the existing SEC/Tiingo route. Keep the paid Sharadar purchase and the
Databento all-symbols download parked.** The completed sample establishes a
workable preparation path. The next deliverable is a prepared monthly panel
and one fixed model comparison, subject to the explicit limits below.

## Frozen acquisition scope

The 100 security rows in `next-cohort.json` are selected once from the 505-row
[April 2, 2018 repository snapshot](https://github.com/datasets/s-and-p-500-companies/commit/5dfdfbc3b9f52802f89e72da6e050b5cafdec4a6).
Sort SHA256(`ba-ml-free-cohort-v1|` + original symbol) ascending and take 100.
There was no search over seeds or candidate returns. This is a dated community
roster, not an independently certified S&P membership database. The study is
of this fixed historical cohort, not a reconstruction of a changing index.

Resolve each historical company to its CIK and dated security aliases. The
2018 FOXA, for example, must not silently become today's different issuer.
Retain every original cohort slot and its outcomes when a company merges,
renames, moves OTC or fails. Do not replace unavailable names with survivors.
New IPOs/index entrants are outside this fixed-cohort experiment. Received
successor securities are tracked as holdings and outcomes, not automatically
added as new ranked candidates. Multiple selected classes of an issuer share
one position cap; resolve any duplicate issuer before fitting.

- Prices/actions: May 1, 2018–December 31, 2023, reusing cached Tiingo payloads.
- Fundamentals: SEC as-filed observations necessary for those decision dates;
  retain filing dates and discard filings made in 2024 or later before analysis.
- Initial training: **31 return months, June 2019–December 2021**. The first
  signal is May 31, 2019, after the full momentum lookback and 252 sessions.
- Diagnostic: **24 return months, January 2022–December 2023**, with annual
  refits using only labels completed before that refit. Never train on the
  upcoming January return when making its decision.
- **2024–2025 remain reserved.** This replaces the paid proposal's chronology
  only for this smaller experiment; it does not manufacture 2000–2010 training.

Twenty-four market months provide weak evidence about reliability, even with
100 stocks each month. The period is already economically familiar from prior
research. Any result is exploratory and cannot justify a funded pilot alone.

## Feature definitions and comparison

Keep the [original comparison](../ml-stock-selection-design-2026-09-13/PROPOSAL.md):
Ridge alpha 100; histogram gradient boosting with learning rate .05, 150
iterations, 15 leaves, minimum 100 samples/leaf, L2 10, no early stopping,
seed 20260914; and the fixed six-signal rank average as a reference. No
hyperparameter sweep, extra signals, LLM price forecasts or new model families.

Use the same valuation, common earnings, profitability, operating cash flow,
momentum and volatility concepts, with these explicit free-source adaptations:

1. Parent/common book equity excludes identifiable preferred equity when
   paired with ordinary common shares. Market value is raw close times the
   latest available reported ordinary shares, adjusted only for subsequent
   evidenced actual share splits. This is a stale-share proxy, not exact
   contemporaneous market cap. Require a share measurement no older than
   180 days; sum economically equivalent classes when supported by filings.
2. Common earnings use reported common-income TTM, or a documented
   reconciliation of parent income less preferred claims. Do not silently
   equate consolidated net income with earnings available to common holders.
   An unavailable financial feature remains missing with the original model's
   neutral rank and missing indicator; it need not trigger another vendor hunt.
3. For return on assets and operating cash flow/assets, use the arithmetic
   mean of reported assets at the current and prior-year matching fiscal ends,
   both known at the decision. This explicit two-endpoint denominator is a
   free-source approximation, not an assertion that it reproduces Sharadar's
   average-assets field. Use matching entity scope/currency and positive assets.
4. Build momentum and 63-session volatility from forward action-aware return
   references. Do not use a price-adjustment factor as a delivered share ratio.
   Spinoff reinvestment is a reference-index convention; whole-share account
   cashflows and received securities are handled separately.

Retain the original two-NYSE-session filing lag, filing/report-age limits,
$5/252-session/$10 million turnover entry rules, within-month ranks and missing
indicators, second-session-close to month-end labels, equal month weights,
and identical eligible sets for paired comparisons. Returns with unidentified
terminal consideration are unknown, never zero or a stale endpoint sale.

Report feature/label coverage by issuer and month before scores. Keep all 100
original slots in that accounting. Require at least 80 entry-eligible issuers
per diagnostic month and known labels for at least 95% of eligible observations
in every diagnostic year to present an aggregate model comparison. Otherwise
report only the identified subset and its coverage limitation, without declaring
an unconditional pass or an economic failure of the idea. These thresholds are
fixed before observing this cohort's model results.

Use the original $10,000 whole-share account constraints and base/stress cost
cases for all rankings. Report paired monthly rank correlation, yearly
consistency and actual account outcomes. A missing mandatory held mark or
corporate outcome leaves that account incomplete. Dividend/corporate receivables
enter NAV but cannot finance purchases until payment is supported. No live
trading is part of this experiment. Freeze adapter code and input hashes before
fitting; record mechanical corrections explicitly.

## Effort and data limits for continuation

Proposed continuation cap: **eight active research hours**, with a four-hour
checkpoint that must produce an actual monthly panel and a coverage table.
If data preparation consumes that checkpoint, report the exact remaining gaps
and stop this attempt rather than spending the remainder writing a general
market-data platform. Once the panel is adequate, use the remaining time for
the fixed comparison. Failed data coverage is distinct from failed profitability.

New subscriptions/cash data purchases: **$0**. Reuse existing data first. Limit
additional Tiingo work to these 100 securities and necessary dated aliases or
distributed/successor securities, with at most 150 additional requests in this
attempt. The public Starter limits are 50 requests/hour, 1,000/day, 500 unique
symbols/month and 1 GB/month; the account's remaining quota is not established.
Respect actual quota responses; do not upgrade, rotate keys or circumvent limits.
[Tiingo published limits](https://www.tiingo.com/about/pricing).
SEC requests remain within its published access limits. The $19.38 Databento
quote remains unused; no full-market order is required for this scope.

This document freezes the acquisition cohort and proposed scope; it does not
claim that issuer resolution, the full feature panel, account conversion code
or the model comparison has already been completed.
