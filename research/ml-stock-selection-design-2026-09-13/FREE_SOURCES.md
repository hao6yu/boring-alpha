# Free and existing-credit alternatives

Reviewed September 13, 2026 after the user asked about Databento. The Sharadar
purchase proposal is parked. This is a source comparison, not a new model run
or a claim that the complete required panel is obtainable for free.

Subsequent user-authorized work: [the ten-company feasibility sample is complete](../ml-free-data-feasibility-2026-09-13/RESULTS.md).
It supports continuing the existing-credit/free route, with explicit remaining
accounting, corporate-action and universe work. The unknown balance and access
statements below describe this earlier review; the sample contains fresh checks.

| Source | What we can use | What remains missing for the proposed experiment |
|---|---|---|
| Existing Databento account | Historical equity prices, trades, quotes and instrument definitions; eligible requests can consume remaining signup credits before new cash. | Equity history starts in 2018, not the proposed 1998 warmup / 2000 training start. Current credit balance and exact request cost are unverified. Historical index membership, issuer links and corporate-action entitlement still need resolution. |
| SEC EDGAR | Public financial statements and filing histories, without an API key. Financial Statement Data Sets begin in 2009 and preserve as-filed information. | No stock-price history or ready-made historical S&P 500 membership. Comparable trailing fundamentals require filing-date selection, amendments, units, fiscal-period and tag handling. This does not supply the original 2000–2010 training history. |
| Open Source Asset Pricing | Public stock characteristics and published portfolio returns; useful for studying signal definitions and historical evidence. | The listed downloads do not establish a complete stock-level return/price/corporate-action panel for our account simulation. Price, Size and STreversal are omitted from the public wide characteristics file and directed to CRSP. The outputs are not a current live fundamental feed. |

Databento advertises $125 signup credits, expiring six months after signup,
one allocation per team. It is metered historical data, not an unlimited free
service. The September 9 access note recorded $125 before the first requests;
subsequent work used some credits. That old balance is not a current quote.
Do not create another account for another signup allocation or assume credit
access includes separate reference subscriptions.
[Pricing](https://databento.com/pricing),
[stock history and available schemas](https://databento.com/stocks).

Our existing authenticated dataset metadata independently establishes
XASE.PILLAR from May 1, 2018 and EQUS.SUMMARY from July 1, 2024. This is dataset
coverage, not proof of every security's completeness. Generic daily bars from
one exchange are not consolidated regular-session total-return prices.
See [the earlier metadata](../equity-event-test-2026-09-10/databento-metadata-probe.json)
and [source review](../equity-event-test-2026-09-10/databento-source-review.json).
The documented Databento market/reference products reviewed do not establish
an as-reported financial-statement dataset; SEC is the proposed source for
that part, rather than assuming Databento prices include company financials.

SEC Company Facts covers standard taxonomy, entity-wide facts. Its Frames
endpoint selects last-filed facts, so a current frame cannot be assumed to
represent information known on a historical decision date. Historical filing
selection is necessary. XBRL reporting was first required in 2009; company
coverage and field availability vary.
[API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[as-filed quarterly datasets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets).

Open Source Asset Pricing's current listed release mostly ends in December
2024, with some inputs ending earlier. No data were downloaded here and no
reserved strategy values were examined. Its existing portfolio returns cannot
substitute for labels on individual stocks when fitting our stock-ranking model.
[Downloads](https://www.openassetpricing.com/data/),
[timing conventions](https://www.openassetpricing.com/faq/).

## Decision

Free sources and existing credits can support a narrower feasibility check.
They have not been shown to replace the full proposed long-history experiment.
Recommend checking a small, predetermined issuer sample with Databento prices
and SEC fundamentals before paying for another subscription. The deliverable
would be feature/price join coverage, exact remaining-credit economics and a
credible usable date range, not profitability or a large download.

Do not silently shorten the proposed research ambition to fit the vendor.
A 2018–2023 combined panel has much less chronological evidence after warmup
and training. Any shortened experiment needs an explicit revised specification;
2024–2025 strategy windows remain reserved. Sharadar remains a convenience and
longer-history option, not a prerequisite for doing any useful further research.
No new data charges, account creation, training or strategy returns in this review.
