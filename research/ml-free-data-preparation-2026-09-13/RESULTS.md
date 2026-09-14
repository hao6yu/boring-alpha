# Ten-company preparation result

**The seven identified accounting gaps are repaired, and the sample's price
history now has explicit corporate-action treatment. Continue to the bounded
[100-stock comparison](NEXT_EXPERIMENT.md). No profitability result exists yet.**

| Check | Before | Now |
|---|---:|---:|
| Required raw accounting fields at 40 company/date checks | 37/40 | 40/40 |
| Reported common share counts | 36/40 | 40/40 |
| Accounting, shares and valid Nasdaq price joins at active checks | 30/37 | 37/37 |
| Existing-entitlement daily price records checked | — | 15,624 |
| Missing expected sessions in the retained Tiingo histories | — | 0 |
| Internal adjustment transitions checked | — | 15,612; zero discrepancies |

The price count includes the ten original companies and GE's two distributed
securities, Wabtec and GE HealthCare. A separate ATVI merger outcome produces
15,625 economic reference observations. None is a simulated strategy trade.

## What was repaired

**Accounting.** Meta's four original filings report Class A and Class B shares
separately. Their sums are 2,851,746,531; 2,781,759,516; 2,562,732,034; and
2,569,862,732 on the four respective cover measurement dates. Company-wide
financial ratios must not use Class A alone. Equal dividend/liquidation rights
support an explicitly labeled A-price-times-A+B economic-value proxy, not an
observed quotation for unlisted Class B.
[2019 filing](https://www.sec.gov/Archives/edgar/data/1326801/000132680119000069/fb-09302019x10q.htm),
[2021 filing](https://www.sec.gov/Archives/edgar/data/1326801/000132680121000065/fb-20210930.htm),
[March 2023 filing, including Note 4](https://www.sec.gov/Archives/edgar/data/1326801/000132680123000067/meta-20230331.htm),
[September 2023 filing](https://www.sec.gov/Archives/edgar/data/1326801/000132680123000103/meta-20230930.htm).

J&J's three missing equity observations reconcile to $58.210B, $70.272B and
$70.869B using common capital + retained earnings + accumulated other
comprehensive income − treasury stock, all from the same historical filing.
The 2023 treasury tag is `TreasuryStockCommonValue`; earlier dates use
`TreasuryStockValue`. This is an issuer-specific reconciliation, not a generic
assumption that missing minority interest equals zero. The 2021/2023 displayed
balance sheets independently agree; the oversized 2019 original could not be
read through the web tool, so retained Company Facts components establish it.
[2021 balance sheet](https://www.sec.gov/Archives/edgar/data/200406/000020040621000070/jnj-20211003.htm),
[2023 balance sheet](https://www.sec.gov/Archives/edgar/data/200406/000020040623000056/jnj-20230402.htm).

**Corporate outcomes.** These corrections prevent material backtest errors:

- GE's February 2019 vendor cash-dividend entry of $0.420281 is treated as a
  Wabtec stock distribution: 0.005371 WAB shares per GE share. It is not
  immediately spendable cash. GE's January 2023 factor of 1.281 is a price
  adjustment for a spinoff, not 1.281 GE shares. The entitlement is one GEHC
  share per three GE shares. Both children have retained price histories.
  [Wabtec terms](https://www.ge.com/investor-relations/shareholder-services),
  [GEHC filing](https://investor.gehealthcare.com/static-files/94bb183f-27f5-425a-adce-bb71fc9c0216).
- Apple's 4-for-1, Amazon's 20-for-1 and GE's 1-for-8 splits are actual share
  multipliers. [Apple](https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/),
  [Amazon ex-date notice](https://www.miaxglobal.com/sites/default/files/alert-files/AMZN_split__50496.pdf),
  [GE](https://www.ge.com/news/press-releases/ge-completes-one-for-eight-reverse-stock-split).
- Tiingo repeats ATVI's $94.42 quote on October 13, 2023 after its final trading
  session. That row is excluded and replaced by the documented **$95 cash
  merger claim**, with payment availability left unknown.
  [Completion filing](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b).
- The original Bed Bath & Beyond's Tiingo history is under **BBBYQ**, including
  its OTC period. Its September 29, 2023 last quote of $0.0789 is retained as
  a quote, but held equity ends at **zero** after cancellation without
  consideration. The confirming filing was accepted at 16:23:06 ET; this is
  an after-close outcome, not an assumed earlier sell signal.
  [Cancellation filing](https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010d8k.htm),
  [Acceptance timestamp](https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/0001193125-23-247428-index.htm).
- J&J's Kenvue transaction was a voluntary exchange. Default no election means
  no automatic KVUE grant to a continuing J&J holder.
  [Final exchange results](https://www.jnj.com/media-center/press-releases/johnson-johnson-announces-final-results-of-exchange-offer-and-finalizes-separation-of-kenvue-inc).

There are 172 routine dividend records across the twelve security histories.
They follow the project's existing vendor-evidence convention: check identity
and internal adjustments, record an ex-date receivable, and do not make it
spendable before a supported payment date. These are not 172 independent
issuer confirmations. The forward return reference assumes frictionless
fractional reinvestment for feature construction; it is not the whole-share
account ledger, and future data revisions are not archived vendor vintages.

## Cost, verification and remaining scope

Thirteen Tiingo requests succeeded using the already configured key, including
one empty BBBY response. No new subscription, cash data purchase or Databento
request occurred during this preparation phase. Existing Codex usage and
research time are not claimed to be free. Source and derived prices stay local
and gitignored. No 2024–2025 strategy prices were opened.

The offline checks pass: 18 retained source payload hashes, seven accounting
repairs with availability dates, documented unit ratios and terminal outcomes,
all expected sample sessions, and the archived-roster cohort selection.
The SEC refused eight direct original-filing downloads with HTTP 403; public
web-readable filing pages supplied the reviewed facts. Six manifest entries
were reconstructed from preserved files and tool outcomes after an initial
concurrent-write error. That provenance repair is explicit in
`manifest-recovery.json`; missing timestamps were not invented.

This resolves the identified sample problems. It does **not** establish
universe-wide data quality, precise current share counts, all six complete
financial features, executable fills, or a profitable model. Missing common
income remains explicitly missing instead of being silently replaced with
consolidated net income. The next scope defines the free-source ratios and
keeps the original missing-indicator convention.

The [next experiment](NEXT_EXPERIMENT.md) fixes 100 historical security rows,
June 2019–December 2021 training and January 2022–December 2023 diagnostics,
with one linear-versus-tree comparison and a fixed-score reference. Its short,
already familiar period is a diagnostic; promising results would still require
separate validation. The paid long-history proposal remains preserved and parked.
