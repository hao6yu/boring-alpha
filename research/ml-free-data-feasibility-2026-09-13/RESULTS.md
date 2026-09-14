# Databento + SEC feasibility result

**The free/existing-credit route works for obtaining and joining the core data.
Continue with this route for a shorter study; keep the Sharadar purchase parked.**
The sample is complete as a feasibility check. It is not a finished financial
feature panel, a profitability test, or authorization for the full download.

## What was actually checked

Ten predetermined companies: Apple, Microsoft, JPMorgan, Exxon Mobil, Johnson
& Johnson, Amazon, GE, Meta/Facebook, Activision Blizzard, and Bed Bath & Beyond.
Four decision dates: December 31, 2019; December 31, 2021; June 30, 2023; and
November 30, 2023. The sample deliberately includes ticker reuse, splits,
spinoffs, an acquisition and a bankruptcy; it is not representative of an
investable universe or selected by returns.

| Check | Result |
|---|---:|
| SEC Company Facts requests | 10/10 successful |
| Raw daily Databento records received in retained download | 14,197 |
| Unrelated older META fund records identified and excluded | 148 |
| Correct-issuer price records retained | 14,049 |
| Missing expected sessions while these stocks traded on the feed | 0 |
| Valid price joins at active company/date checks | 37/37 |
| Other company/date checks after removal from the feed | 3, correctly without prices |
| Core accounting fields available, across all 40 checks | 37/40 |
| Core accounting plus price joins among 37 active checks | 34/37 |
| Above joins also having an entity-wide reported share count | 30/37 |

Core accounting means assets, parent equity, net or common income, and operating
cash flow. Annual/YTD components were combined into trailing-year flows, with
their filing dates retained. This is less than qualification of the original
six proposed model features. Net income is not automatically common income;
reported share counts are not automatically current market-cap denominators.

## Concrete data issues found

1. **Ticker reuse matters.** Before Meta Platforms adopted META on June 9,
   2022, a Roundhill fund used the symbol. A full-history META request returned
   148 fund records. Dated aliases now join Facebook's FB history to its META
   history and exclude that fund. A raw ticker-only merge would silently attach
   unrelated prices to Facebook's financials.
   [Nasdaq notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125),
   [fund ticker-change notice](https://www.miaxglobal.com/alert/2022/01/28/miax-exchange-group-options-markets-corporate-action-alert-roundhill-ball-0).
2. **Company Facts is useful but incomplete for the exact fields.** Three J&J
   dates lack the exact parent-equity extraction; Meta's four dates lack an
   entity-wide common-share count. Original filings, including class-specific
   facts omitted from this API, need to be checked. These are identified
   extraction gaps, not evidence that the original filings lack the information.
   [SEC API scope](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
3. **Removal is not a zero return or an indefinite last price.** ATVI prices end
   October 12, 2023, immediately before the completed cash acquisition; BBBY
   ends May 2, immediately before Nasdaq suspended trading. We kept their
   earlier histories and did not fill prices after these dates. A held position
   still needs its actual cash/stock consideration or OTC/cancellation treatment.
   [ATVI completion filing](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b),
   [BBBY suspension notice](https://www.sec.gov/Archives/edgar/data/886158/000119312523115523/d89202dex991.htm).
4. **Raw daily bars need corporate-action work.** Nasdaq venue bars are
   unadjusted UTC-day aggregates, not consolidated regular-session fills or
   total-return data. GE's 2021 reverse split and 2023 healthcare spinoff are
   concrete examples of events that must be handled before using price changes
   as momentum or investment returns. Dividends also require treatment.
   [Databento bar conventions](https://databento.com/docs/schemas-and-data-formats/ohlcv),
   [GE split](https://www.ge.com/news/press-releases/ge-completes-one-for-eight-reverse-stock-split),
   [GE HealthCare spinoff](https://www.gehealthcare.com/en-us/about/newsroom/press-releases/ge-healthcare-completes-spin-off-and-begins-trading-on-nasdaq).

## Cost and access

The signed-in Chrome billing page showed $117.95 remaining credits and $0.00
cash balance before acquisition. After acquisition it showed $117.91 credits
and $0.00 cash balance, with no plans or licenses subscribed. These displays
are rounded to cents, not an exact transaction ledger.

- Fresh sample quote: **$0.022212937474** for the fixed 11 raw ticker aliases,
  May 1, 2018 through December 31, 2023, XNAS.ITCH daily bars.
- Two streamed responses were incurred: estimated total **$0.044425874948 in
  credits**, with no new cash payment or subscription.
- The first client version wrongly treated HTTP 206 as failure and discarded
  its response body. Databento documents 206 as successful data with partially
  resolved symbols. The client was corrected and one explicit recovery request
  completed. Both requests count toward cost; first-response metadata is
  retained, but its discarded content cannot be verified against the recovery.
  [HTTP conventions](https://databento.com/docs/api-reference-historical/basics/schemas-and-conventions).
- Broader price-only quote, same dates/schema/venue but **ALL_SYMBOLS**:
  **$19.37593370676**. This includes symbols outside any eventual stock universe
  and is not an order, a full research cost estimate, or an estimate of separate
  corporate-action/reference products. It fits the observed remaining credits.
- SEC access: **$0**, without account creation. Cleaning effort, existing Codex
  usage and local resources are not claimed to be economically free.

## Verification and limitations

Fourteen retained response hashes, 346 historical financial fact components,
bar validity, dated instrument mappings, listing-session coverage, and ticker
exclusions checked successfully. Tests verify NYSE holiday handling for the
two-session filing lag, exclusion of synthetic later restatements, rejection
of conflicting facts, and independently stated Apple TTM arithmetic. No price
was carried forward past a documented listing removal.

The Company Facts API transports complete filing histories; the collector
discarded records filed in 2024 or later before saving or analyzing values.
The vendor's entire-response hash is retained, along with hashes of filtered
pre-2024 data. No 2024–2025 strategy prices or feature values were evaluated.
Later as-filed comparative revisions are usable only after their filing lag;
quarterly fields are not selected by their report date alone.

The sample demonstrates access and narrowly measured coverage. It does not
establish historical S&P 500 membership, universe-wide delisting coverage,
corporate-action completeness, executable prices, or the final feature panel.
Hand-verifying ten names does not demonstrate that all issuer identities can
be joined correctly at scale. No model was fitted and no strategy returns were
computed.

## Next step

Use a bounded preparation phase on the same sample to resolve accounting/share
classes and build split/dividend/spinoff and security-lifecycle handling. Then
choose a dated historical universe and freeze a revised, shorter chronology
before any broader acquisition or model comparison. Preserve removed names;
do not substitute today's surviving members for historical membership.

The 2018 start cannot supply the earlier proposal's 2000–2010 training period.
With 2024–2025 reserved, substantially fewer independent market months remain
for training and diagnostics. That limitation must be visible in the revised
experiment. The present evidence supports this cheaper data route, not a claim
that it produces a profitable model or reproduces the original long-history test.

Reproduce the offline checks from this directory using the project virtualenv:
`python analyze.py`, `python prices.py`, `python verify.py`. Use `probe.py sec`
for cached SEC acquisition or `probe.py quotes` for the fixed quote requests;
authenticated modes accept a hidden key prompt. Raw data remain gitignored.
