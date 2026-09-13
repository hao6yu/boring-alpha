# Earnings-release model: proposal and initial data audit

Date: September 10, 2026. The user explicitly accepts systematic trading of
individual stocks around events. Ordinary stock/ETF allocation remains outside
the requested work.

Update: the subsequently authorized [100-slot pilot is complete](2026-09-10-equity-event-pilot.md).
It did not clear the data gate: 89/100 slots passed combined checks, with
inactive-security treatment also unresolved. The proposal and initial audit
below are preserved as the pre-pilot record; profitability remains untested.

**Decision: one exploratory earnings-release model is sufficiently concrete
for a bounded data pilot. It is not ready for a profitability test or funding.**
The initial document audit succeeded, and the existing price provider returns
useful metadata. Modern evidence also gives strong reasons to reject a simple
announcement-day trading bot. No returns or model scores were calculated here.

## One candidate, one comparison

**Hypothesis:** changes in earnings-release language contain information about
subsequent returns beyond the contemporaneously reported numerical results.
Investors may take time to distinguish durable improvement from temporary
accounting gains or complex explanations. This is a proposed mechanism, not an
advantage established for us. Public AI access supplies no exclusive edge.

The proposed first model is an **elastic-net linear regression** combining a
small set of accounting features with training-only word/phrase features. It
would predict market-relative returns over **20 trading sessions**, then be
evaluated as a cash-funded, long-only strategy. This horizon is a design choice,
not a claim to replicate a paper or a parameter selected from returns.

- **Inputs:** original earnings-release text; reported revenue/EPS and their
  comparable historical changes; explicitly distinguished non-GAAP measures;
  prior returns and liquidity known before entry. Acquisitions, fiscal periods
  and share-basis changes require explicit treatment or missing-value labels.
- **Baseline:** the same regularized model using accounting and past-price
  inputs without text. Add a matched event portfolio to distinguish stock
  exposure from signal value. A seasonal earnings change is not analyst
  consensus surprise; do not rename it SUE without a valid expectations model.
- **Timing:** use the first regular session strictly after both the official
  filing date and Eastern acceptance date. Proposed execution is that session's
  close, with a declared closing-price/slippage proxy for an initial daily-data
  test. This avoids designing a 10:00 fill from daily OHLC. Native closing
  execution and order cutoffs would still need later validation.
- **Trading scope:** historically eligible, liquid U.S. common stocks; whole
  shares, long-only, no leverage. A possible $5,000 implementation caps each
  position at $1,000 and retains at least $1,000 cash. This is a feasibility
  sketch, not a complete risk/order protocol or a guaranteed loss limit.
- **Evaluation:** chronological training only; training vocabulary, scaling,
  feature selection and penalty choice use past data. Training labels must have
  finished their 20-session horizon before the next fit. Preserve 2024–2025
  equity strategy returns as reserved evaluation history. No present-day list
  of surviving companies may define the historical universe.

Modern pretrained language models can contain information learned after a
historical event. They will not supply historical trading scores for this first
test. The agent can assist extraction and audit; the statistical predictor must
learn from information available before each decision.

The model must show incremental after-cost value over the numerical baseline,
not just predict earnings correctly or make money in a rising stock market.
No horizon contest, collection of alternative models, or tuning of failed
BA-012 rules is proposed.

## Evidence: relevant, mixed and narrower than a profit claim

Demers and Vega study earnings press releases from 1998–2006. Changes in
managerial optimism contain incremental information beyond numerical surprise
and predict returns over days +2 through +62. However, their portfolio evidence
is gross long–short, concentrated in smaller/medium firms; it does not establish
our liquid-stock, long-only, 20-session implementation after costs.
[Federal Reserve paper](https://www.federalreserve.gov/pubs/ifdp/2008/951/ifdp951.htm).

Wu and coauthors' 2025 paper is especially relevant: it uses SEC 8-K release
attachments through 2023. Text helps explain announcement returns, but their
9:45-to-close long–short strategies have negative alpha when using executable
bid/ask prices. That directly weakens a simple same-day release-reading bot.
It does not directly test our longer holding period; changing the horizon also
does not establish that our alternative works.
[Original paper](https://arxiv.org/html/2509.24254v2).

PEAD.txt uses earnings-call transcripts, including Q&A, from Capital IQ and
other academic datasets. Its 63-session long–short result cannot be transferred
to SEC releases, which omit that information. This proposal is not a replication
of PEAD.txt. [Journal paper](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/peadtxt-postearningsannouncement-drift-using-text/5EB217BB68B5FB054FE38541BAAC4679).

## What was actually checked

Before collecting documents, fixed three issuers and selected each one's
earliest Item 2.02 Form 8-K filed in July–September 2023. They are convenience
examples for data inspection, not the eventual universe or a performance sample.
The audit acquired submissions metadata, the filing index, Form 8-K and the
identified Exhibit 99.1. JPM required older submissions metadata as well.

| Issuer | SEC acceptance, New York time | API UTC time | Following session | Accounting checks |
| --- | --- | --- | --- | --- |
| MSFT | July 25, 2023, 16:02:47 | 20:02:47Z | July 26 | Quarterly revenue $56.2bn; reported EPS $2.69. Annual results and constant-currency growth also appear. |
| WMT | August 17, 2023, 06:59:53 | 10:59:53Z | August 18 | GAAP EPS $2.92; adjusted EPS $1.84. This is fiscal Q2 FY2024, ending July 2023. |
| JPM | July 14, 2023, 06:46:08 | 10:46:08Z | July 17 | Reported/managed revenue $41.3bn/$42.4bn; EPS $4.75/$4.37 excluding significant items. First Republic affects comparison. |

All three timezone conversions agree exactly. The proposed daily-price test
would use the following session's close, not the acceptance-time price.

Original releases: [Microsoft](https://www.sec.gov/Archives/edgar/data/789019/000095017023034400/msft-ex99_1.htm),
[Walmart](https://www.sec.gov/Archives/edgar/data/104169/000010416923000088/earningsreleasefy24q2.htm),
[JPMorgan](https://www.sec.gov/Archives/edgar/data/19617/000001961723000425/a2q23erfexhibit991narrative.htm).

Acceptance is not first public dissemination. SEC does not provide a timestamp
for first availability on its website, and the issuer can announce before
filing. Walmart's 8-K even says it will issue the release that day. The proposed
delay is a conservative historical proxy, not proof of precise availability;
future collection should record first successful retrieval. Ambiguous cases
must remain unresolved. [SEC timing FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions).

Preserve original accessions and treat amendments as new information at their
own availability times. Companyfacts aggregates disclosures across filings; it
requires source-accession filtering. The frames endpoint's last-filed selection
must not be used directly for historical signals.
[SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

### Price metadata probe

Used the existing Tiingo connection for metadata only. No price rows were
downloaded or returns inspected; credentials were not logged.

| Requested ticker | Observed result | What it establishes |
| --- | --- | --- |
| MSFT, WMT, JPM | HTTP 200; historical start dates reported | Provider recognizes the current identifiers; historical row quality remains untested |
| ATVI | HTTP 200; end date October 13, 2023 | Some acquired-company history remains represented |
| SIVB | HTTP 404 | Old ticker alone fails; excluding it would be an invalid shortcut |
| SIVBQ, one targeted follow-up | HTTP 200 under later identifier | Alias resolution is necessary; full price continuity and terminal shareholder outcome are still unverified |

The SIVB/SIVBQ change is corroborated by the
[OCC symbol-change memo](https://infomemo.theocc.com/infomemos?number=52179).
ATVI/SIVB were deliberately chosen as coverage challenges, not as examples of
strategy returns. Metadata date ranges are not proof that every intervening
date traded. Current exchange codes also must not be applied backward: the WMT
metadata says NASDAQ while its sampled 2023 filing says NYSE.

Tiingo documents raw and split/dividend-adjusted daily prices. Metadata success
does not verify corporate actions, delisting returns, historical CIK/security
mapping, daily continuity or the desired observation time. Those are the next
data questions. [Provider documentation](https://www.tiingo.com/documentation/end-of-day).

## Small-account cost screen

IBKR Pro currently lists tiered $0.0035/share with a $0.35 order minimum, or fixed
$0.005/share with a $1 minimum. Personal Pro approval and pricing remain
unverified. Tiered has additional exchange/clearing/regulatory charges; fixed
also lists regulatory charges. [Commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).

| Position size | Tiered round-trip commission floor | Fixed round-trip commission floor |
| ---: | ---: | ---: |
| $500 | $0.70 / 14 bps | $2 / 40 bps |
| $1,000 | $0.70 / 7 bps | $2 / 20 bps |

These floors apply only while per-share charges stay below the minimum.
Additional assumed total round-trip spread/slippage of 10/25/50 bps costs
$1/$2.50/$5 per $1,000 position, plus other charges and any data costs. These
are sensitivities, not observed fills. Stocks are mechanically more divisible
than BA-012's futures basket; that helps sizing without creating an edge.
The 4%/6% cash comparisons must include all dedicated capital. Idle account
interest must reflect actual eligibility, not an assumed cash yield.

## Next bounded deliverable

Recommend a **100-event data pilot, capped at two hours and $0 in new paid
data**, before model training. Freeze a historical sampling rule independent
of returns and retain every selected event, including failures. The pilot must
join original releases to prior comparable releases, historical security IDs,
corporate actions and the proposed daily price windows. Include inactive-name
coverage challenges separately. Verify API quotas before bulk requests.

This is a data pilot, not a training set large enough to establish ML profits.
Report every missing join, revision ambiguity, timing problem and accounting
mismatch. Proceed toward a separately frozen, multi-year experiment only if
at least 95 of 100 selected events join without unresolved identity/timing
errors and the inactive-name checks have defensible treatment. No passing
percentage permits silent deletion or zero-return treatment of failures.

If that target cannot be met within the budget, stop and report the exact
failure and required remedy. A later profitability experiment must separately
beat the numerical baseline and cash after base/stress costs, with uncertainty,
turnover, market exposure and drawdowns reported. It may still reject the model.

## Audit artifacts and status

[Sample selection](../../research/equity-event-feasibility-2026-09-10/sample-policy.json),
[source manifest](../../research/equity-event-feasibility-2026-09-10/source-manifest.json),
[timing audit](../../research/equity-event-feasibility-2026-09-10/timing-audit.json),
[accounting audit](../../research/equity-event-feasibility-2026-09-10/accounting-audit.json),
[price metadata results](../../research/equity-event-feasibility-2026-09-10/price-metadata-results.json).

An independent review reconciled all 14 SEC payload hashes/sizes, selected
accessions, exhibits and timezone conversions. A local inspection-library
error occurred after three successful index downloads; their original payloads
remain intact, and the manifest explicitly labels filesystem write times
instead of fabricating lost HTTP transport timestamps. It is not a failed SEC
access request.

No strategy registration, training, backtest, order, subscription change or
data purchase occurred. The completed work establishes initial data feasibility
and a testable proposal. Profitability remains unknown.
