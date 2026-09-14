# Financial-input audit — completed September 14, 2026

**The missing-input problem is recoverable in this sample.** Reviewing the
original filings recovered all 28 missing common-equity and trailing common-
earnings fields across 10 predetermined companies at two historical dates.
This supports improving the extraction layer. It does **not** establish an
improvement in returns or a deployable trading strategy.

| Target input | Available before | Available after manual review | Recovered |
|---|---:|---:|---:|
| Common shareholders' book equity | 6 / 20 | 20 / 20 | 14 |
| Trailing annual earnings attributable to common shareholders | 6 / 20 | 20 / 20 | 14 |
| Combined | 12 / 40 | 40 / 40 | 28 |

The 12 previously available values are unchanged. All 99 frozen baseline files
and both original panel/fundamentals payloads match their starting hashes.
There were no price requests, rankings, model fits or profitability runs.
New paid data cost: **$0**.

## What was wrong with the inputs

The existing extractor correctly refused to invent zero preferred capital or
zero earnings adjustments when a tag was absent. However, it recognized only
a limited set of tagged representations. The audited filings contained other
explicit representations of the same common-shareholder quantities.

The revised rules demonstrated here are:

1. **Equity:** reconstruct the complete, explicitly identified common-equity
   components and reconcile them to the filed shareholder total. Exclude
   noncontrolling interests. Alternatively, use parent equity less preferred
   capital when the filing explicitly establishes the preferred balance.
2. **Earnings:** qualify the basic common-EPS numerator from the original
   disclosure, then reconstruct trailing earnings from the original full year
   plus current year-to-date earnings minus prior year-to-date earnings.
3. **Timing:** each numeric fact and accounting interpretation must be supported
   by a filing available before the historical cutoff, with the existing
   two-exchange-session delay. No later filing may repair an earlier snapshot.

These are filing-specific review certificates, **not global aliases** saying
that net income always equals common earnings or that absent preferred stock
always equals zero. The SEC explains that its aggregated APIs omit custom
taxonomy facts and facts that do not apply to the entire filing entity; source
filings can therefore contain information missing from a particular API view.
[SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

## Accounting cases that matter

- **Whirlpool:** its original 2022 EPS disclosure explicitly identifies a
  $1,519 million loss available to Whirlpool. With the 2023 YTD and comparative
  amounts, trailing common earnings are negative $1,614 million. A subsequent
  annual report was not used to establish the earlier value.
  [2022 annual filing](https://www.sec.gov/Archives/edgar/data/106640/000010664023000015/whr-20221231.htm).
- **Mondelez:** 2022 consolidated earnings of $2,726 million include $9 million
  attributable to noncontrolling interests. The basic common-EPS numerator is
  $2,717 million. Using consolidated earnings would be the wrong ownership scope.
  [2022 annual filing, Note 17](https://www.sec.gov/Archives/edgar/data/1103982/000110398223000006/mdlz-20221231.htm).
- **VF:** the accounting policy defines basic EPS from total net income or loss.
  Its 2025 quarterly statement separately shows continuing and discontinued
  operations. The prior YTD total is negative $206.708 million; substituting the
  positive $50.482 million continuing-operations amount would corrupt trailing
  earnings. [Annual policy](https://www.sec.gov/Archives/edgar/data/103379/000010337925000023/vfc-20250329.htm),
  [quarterly statement](https://www.sec.gov/Archives/edgar/data/103379/000010337925000060/vfc-20250927.htm).
- **Cummins:** the common-stock line already includes paid-in capital. Adding
  another paid-in-capital amount would double count it. Its reconstructed
  September 2025 common book equity is $12,064 million, excluding NCI.
  [Quarterly filing](https://www.sec.gov/Archives/edgar/data/26172/000002617225000039/cmi-20250930.htm).
- **Flowserve:** September 2023 parent equity includes $7.878 million of deferred
  compensation equity absent from the same-date companyfacts view. Omitting it
  fails reconciliation. September 2025 explicitly reports no preferred shares
  issued. The complete 2023 reconstruction and the explicit 2025 preferred
  disclosure are different supported paths, not an absent-tag fallback.
  [2023 statement](https://www.sec.gov/Archives/edgar/data/30625/000003062523000136/fls-20230930.htm),
  [2025 statement](https://www.sec.gov/Archives/edgar/data/30625/000003062525000072/fls-20250930.htm).
- **Negative equity:** Aon in the earlier snapshot and Hilton in both snapshots
  retain negative common book equity. It is not clamped to zero or treated as
  missing. [Aon filing](https://www.sec.gov/Archives/edgar/data/315293/000162828023035412/aon-20230930.htm),
  [Hilton filing](https://www.sec.gov/Archives/edgar/data/1585689/000158568925000160/hlt-20250930.htm).

All exact accession numbers, fiscal periods, source URLs, values, signs and
review notes are in [reviewed-evidence.json](reviewed-evidence.json). Detailed
before/after values are in [audit-results.json](audit-results.json).

## Limits and decision

The companies were selected for missing inputs, in original cohort order:
PNR, VFC, CSCO, WHR, AON, RHI, HLT, MDLZ, CMI and FLS. The two anchors are
January 2024 and January 2026, with cutoffs December 29, 2023 and December 31,
2025. This is 20 company-date observations, not a random sample or 20 independent
companies. **100% recovery here is not an estimate of full-cohort coverage.**

The replay automatically verifies values, filing dates, fiscal alignment and
reconciliation. Accounting classifications were manually reviewed. It cannot
automatically extend those interpretations to another filing. One equity
component required manual numeric transcription; an additional preferred-share
disclosure required reading the original statement. Scaling this work remains
an engineering and data-quality question.

The three annual filings that exceeded the web reader's size limit were read
in the normal browser. Web excerpts are cached; browser-only observations are
summarized in [browser-review.json](browser-review.json). Full original HTML was
not archived, so an independent accounting review should revisit the linked
filings. No login or paid source was needed.

**Continue with a bounded extraction implementation.** Then evaluate one
version that changes only financial-data extraction across the original
cohort. Do not patch just these ten winners in a coverage audit and call that a
strategy improvement. The score, weights, costs, account rules and reference
must remain fixed. The existing 2022–2026 returns are already seen; a revised
historical result would be exploratory and would still need prospective
validation. See [the next experiment specification](NEXT_EXPERIMENT.md).

Verification: **18 checks passed**, including rejection of premature filings,
incomplete trailing years, incorrect NCI scope, substituted continuing earnings,
omitted deferred compensation and unsupported preferred-stock assumptions.
See [verification.json](verification.json). The baseline's 5.91%/5.16%
base/stress annualized returns and lack of demonstrated selection advantage
remain the last performance evidence; this audit produces no new return estimate.
