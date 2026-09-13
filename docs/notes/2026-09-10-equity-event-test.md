# Earnings-language experiment: stopped at the training-sample gate

The data collection and validation produced **175 usable 2020 training events**,
below the **200 required before model fitting**. No model was fitted, no
2022–2023 evaluation targets were opened, and no portfolio profitability result
was calculated. This result identifies an inadequate sample for this design;
it does not establish whether the earnings-language hypothesis makes money.

## What was completed

The earlier availability repair now passes **97/100**, above its unchanged
95-slot threshold. Databento supplied the four missing qualified PTN windows.
The dedicated acquisition quote totals **$0.012873232367**, about 1.3 cents,
against existing credits. This is a quote total, not an invoice reconciliation.
Public SEC data and the existing free Tiingo account added no subscription
cost. User time, computing, and agent usage are not included in that figure.

A separate performance cohort was fixed from original 2019 filings: 100
issuers and all 1,600 quarterly slots for 2020–2023. Collection found 1,257
current releases, 1,199 original prior releases, and 1,198 source-qualified
joins. Failed and inactive-company slots remain on the denominator.

One hundred price requests, including two successful transport retries,
produced responses for 98 symbols: 90 nonempty histories, including the market
benchmark, and eight empty histories. Nonempty does not mean qualified;
recycled tickers, stale post-acquisition rows, and action conflicts remain
excluded where required. The last nine planned queries were not acquired.

## Admission result

| Check | Observed | Required | Result |
|---|---:|---:|---|
| 2020 training events with matured labels | 175 | 200 | Fail |
| 2021 validation events with matured labels | 200 | 100 | Pass |
| 2022–2023 events qualified before entry | 378 | 200 | Pass |
| Issuers in that evaluation pool | 57 | 40 | Pass |

The evaluation counts describe source and pre-entry eligibility. They do not
certify future prices, completed trades, account NAV, or positive returns.

The nine remaining price queries could add **at most 24** training events,
even assuming perfect historical coverage, identity, liquidity, and narrative
quality: **175 + 24 = 199**. Four already measured MGTA liquidity failures
cannot be changed by downloading its later successor ticker.

PEGI's March 2020 event cannot supply the registered ordinary-stock label
through March 31: its last trading day was March 13 and its cash merger closed
before the March 16 open. Continuing stock prices cannot be inferred from the
cash consideration. [Nasdaq's merger notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-47),
[issuer completion announcement](https://patternenergy.com/pattern-energy-and-canada-pension-plan-investment-board-complete-transaction/).

An additional check rejected simply clearing CADE's identity warning. Its
downloaded history matches BancorpSouth, the acquirer, rather than the selected
old Cadence Bancorporation. The original merger proxy reports different
April 8, 2021 closing prices for the two securities; the downloaded anchor and
2020 dividend pattern match the acquirer.
[Original merger proxy](https://www.sec.gov/Archives/edgar/data/1614184/000114036121023608/nt10025002x2_defm14a.htm).

The 199 ceiling applies to these remaining queries and the existing qualified
data. It is not a ceiling for a larger cohort or genuinely new replacement
historical sources. Waiting for the next free API quota window would not make
this run eligible for fitting, so acquisition stopped here.

## What the checks establish

The final source audit reviewed 45 distinct metric pairs, or 90 financial
cells, without finding an incorrect non-null amount in that sample. This is
not a population accuracy guarantee. Numerical missingness remains material:
only 508 revenue comparisons and 460 USD-resolved EPS comparisons were
available across 1,199 loaded pairs before price and share-basis checks.
Literal currency evidence and regulatory USD inference remain separate.

Original-source identity, table extraction, price qualification, model timing,
portfolio accounting, and metric calculations have focused tests. The final
34 checks affected by source-cache and runner integration passed. The source
cache rechecks original document and source-ledger hashes and reproduces the
same 1,600 rows as fresh extraction. Account tests use synthetic data; they are
not a historical trading result.

Other limitations remain explicit: incomplete predecessor searches, selection
conditional on retrievable original sources, daily-close execution proxies,
unverified dividend payment timing, and unresolved complex merger claims.
No live orders, account changes, or recurring monitoring were started.

## Decision and retained work

The fixed 100-issuer sample was too small after source and trading-eligibility
checks. The minimum was not lowered and the cohort was not replaced to force
admission. Any continuation needs a separately specified larger cohort or
materially better historical coverage, with a finite effort and data budget.
The existing collectors, original filings, source audit, and execution tests
can be reused. Equity prices for 2024–2025 remain reserved for this experiment.

The machine-readable result and reproduction pointers are in
[`research/equity-event-test-2026-09-10/`](../../research/equity-event-test-2026-09-10/README.md).
