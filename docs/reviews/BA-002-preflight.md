# BA-002 seen-history preflight — price verification incomplete

Date: 2026-09-04; Tiingo follow-up added 2026-09-05.
**No BA-002 performance sweep or classification was run during this preflight.**
This is a data-admission finding, not a failed strategy or an Inconclusive
economic verdict. No source file, trading rule, tax policy or threshold was
changed in response to the checks.

Subsequent update: the holder authorized a versioned issuer-supported correction
and a separate [two-feed performance diagnostic](BA-002-source-sensitivity.md),
now complete with a practical no-go recommendation. Statements below about
pending results and unchanged input files describe the preflight state, before
that authorized follow-up. The original snapshot and formal freeze remain
unchanged; the new diagnostic does not confer formal eligibility.

## Ready

The holder authorized the proposed seen-history cycle. Revision 1 fixes the
existing 9/12/15 rule, five-row grid, $100,000 standalone account, annual
60%-invested benchmark and eight stylized tax scenarios. Deduction sensitivity
is off. Primary after-tax margin remains 50 bps/year; all drawdowns must be at
most 20% and no worse than the paired benchmark.

- [Seen A config](../../configs/ba_002_development.toml): 2007-06-01–2017-12-31.
- [Seen B config](../../configs/ba_002_validation.toml): 2018-01-01–2021-12-31.
- [Separate registry](../../configs/ba_002_evaluation_periods.toml): BA-001 is
  untouched; sealed dates are metadata only, with no runnable sealed config.
- Both configs pass profile validation and have identical strategy and tax
  identities. All eight symbols, cash and distributions meet the independent
  calendar requirements in both periods, including the 2006-02-28 warmup
  anchor. Existing plausibility checks return no findings in either window.
- The running implementation passed **879 tests and 192 subtests in 122.09s**.
  The subsequently added source-diagnostic tests passed separately: **14 tests**.
  These counts are separate runs, not a claim that one full run executed 893.

The selected inputs remain snapshot `20260904T192633Z`, methodology
`yahoo-adjusted-v2+dgs3mo-v1`, not the mutable `data/current` pointer.
Numeric input loading was date-bounded before conversion. Latest retained
dates are 2017-12-29 and 2021-12-31 respectively.

## Fresh primary-source corroboration

Twelve selected 2020 cash distributions across EEM, EFA, IWM, IEF and TLT match
the issuer's amounts within the snapshot's three-decimal rounding. The maximum
absolute difference is $0.000495/share. These compare the cash-distribution
column, not foreign-tax-grossed ordinary income. They do not establish actual
historical qualified fractions. [iShares 2020 supplement, pages 3, 29 and 41](https://www.ishares.com/us/literature/tax-information/2020-ishares-distribution-summary.pdf).

EEM's June and December 2008 issuer distributions were also freshly confirmed
against the issuer download: the prior [split-restated-unit finding](../decisions/2026-09-04-distributions-v2.md)
stands. The retrieved issuer workbook's SHA-256 is
`b17ebcd6358619f76faf02f885250185acd3a840f478cad8be98aa814c9c2287`.
Its historical sheet has NAV, not exchange market prices, so it cannot settle
the open/close discrepancies below.

The 3-for-1 EEM split effective July 24, 2008 is corroborated by
[CME advisory 08-158](https://www.cmegroup.com/tools-information/lookups/advisories/clearing/Chadv08-158.html)
and [Nasdaq PHLX memo 1410-08](https://www.nasdaqtrader.com/content/phlxmemos/2008/Jul/1410-08.pdf).

## What stopped admission

A preliminary comparison used three SHA-pinned QuantConnect/Lean sample
archives from commit `23b735d99a357807dc0df9f4c51d30f05fe0d277`. This is an
independently published reference, **not an authenticated independent vendor
audit**. The fixed diagnostic tolerance was the greater of $0.02 or 5 bps of
the aligned reference price, selected before local comparison and not relaxed.
It is a discrepancy flag, not a newly added strategy-advancement criterion.

The reference covers only SPY, IWM and EEM, through 2021-03-31. Five universe
symbols and the final 191 seen sessions remain unverified against that feed.

| Symbol | Daily closes outside tolerance / 3,799 | Monthly next-opens outside tolerance / 166 | Changed horizon votes / 501 |
|---|---:|---:|---:|
| SPY | 690 | 18 | 0 |
| IWM | 746 | 26 | 0 |
| EEM | 653 | 21 | 0 |

The largest monthly execution-open discrepancy is SPY on **2009-10-01**:
the snapshot's recovered cash-price open is **$103.00**, against **$105.29**
in the reference, a **2.1749%** difference relative to the reference. IWM on
2017-12-01 differs by $0.65, or 42.30 bps. These are price differences, not
portfolio-return or annualized-alpha estimates; their performance impact was
not computed. Neither source has been selected as correct.

No votes changed in 1,503 covered comparisons. However, that diagnostic
substitutes only the price component and retains Yahoo's corporate-action
adjustments and cash. It does not validate independent total returns or prove
that execution discrepancies have negligible economic consequences. The final
covered March 2021 decision has no covered April execution open.

The reference has its own material provenance warning: EEM's sample includes
722 records before the fund's launch, while its map starts in April 2003.
It is unresolved whether this is ticker reuse, synthetic history or another
sample convention. [The repository's issue 5254](https://github.com/QuantConnect/Lean/issues/5254)
also discusses historical sample open/close prices lacking official-price
alignment; [PR 5576](https://github.com/QuantConnect/Lean/pull/5576) records
corrections, not a complete sample-specific vendor lineage. Therefore the
reference is retained as a warning/sanity check, not used to repair Yahoo.

## Reproduction and preserved state

Run the bounded, read-only [diagnostic](../../tools/check_ba002_seen_prices.py):

```sh
.venv/bin/python tools/check_ba002_seen_prices.py \
  --snapshot data/snapshots/20260904T192633Z
```

Its full [local JSON output](../../experiments/BA-002/preflight/20260904/price-check.json)
preserves source hashes, examples, discrepancy rows and coverage. It is ignored
by Git; source price extracts must not be publicly redistributed without
appropriate rights. The three reference ZIP hashes are pinned in the script.
No portfolio-performance metrics are calculated by it.

| Identity | SHA-256 |
|---|---|
| Prices | `750f4344d2138b8d1a2b191c05a595fff8566f434d242d3cb85a6e30ea579279` |
| Cash | `963bf17ca515014328370d1ecf58f972a22d17472254c322352e6f7f6537c13c` |
| Distributions | `cf5f53e96d1b28aa849a578dcef512aae75fd48b2f35a52dabbf31e8ef0fa141` |
| Snapshot manifest | `0c3d0a4ee554a5641eb1d4e1a5318f42028839efb53792a5887eb9b9ff4aefe5` |
| Running code | `a63a77df3adb569a6048336fdba40c775013fcd80fac3ad6a55002b09ea7dbb8` |
| Strategy spec | `5ddccb92050949d42745faaeed3cf3697a8f5ccc1cfca507f040e377cf27c2a1` |
| Tax policy | `9abb91e20b43a0d18a9e8404439145f13e5cf338d4eed4fd7363293146f54542` |

The [draft freeze](../../research/ba002-seen-20260904-freeze.json), identity
`6f3a2a046b0b40bb36da4b930534a8836697596b5e1d25b577e14b39c39acc4c`,
was prepared but **not confirmed**. It preserves the exact charter text before
the completed source audit. No family journal was initialized and no research
attempt/reveal was claimed. An exact local source archive is retained at
`research/ba002-seen-code-a63a77df3adb.tar.gz` because the tested corrections
remain uncommitted on top of `6cce761`; the commit alone is not the running code.
The archive's SHA-256 is
`b11169ebc882b6221387fbc90efcbb5c2e73645dfff53c703b2cfd3149e2b746`;
rehashing its 48 Python source members reproduces the running code hash above.

## Boundary disclosure

No protected-window CSV observations were loaded into an evaluation, and no
holdout or BA-002 performance run occurred. Targeted historical web searches
nevertheless returned unsolicited current issuer/secondary-site snippets,
including later EEM distribution/quote fields and comparison summaries.
These were not used economically, copied into the diagnostic, or used to
change the strategy. A public Tiingo page interpreted `/free/prices` as the
unrelated ticker FREE and displayed later dates despite edited date fields;
it was closed without selecting a universe ETF. These incidental exposures
must not be described as an absolutely observation-free external search.

## Dependency identified September 4

The holder reports no existing historical-data account or export. The first
practical candidate is Tiingo's Starter account: its [published pricing](https://www.tiingo.com/about/pricing)
currently lists $0/month and 30+ years of price history, with request limits
apparently sufficient for eight ETFs. Its [EOD API](https://www.tiingo.com/documentation/end-of-day)
provides raw/adjusted prices and corporate actions with explicit start/end
parameters. Actual ticker/date entitlement and source conventions still need
checking. Account creation, token access, and any purchase were not performed.
Raw licensed inputs should remain local, not in this public repository.

Obtain date-bounded data or a trusted export, reconcile the flagged prices and
adjustment conventions, and then finish admission. Do not silently substitute
sources, overwrite this draft, weaken thresholds, or turn an unresolved data
issue into a strategy verdict. Any changed input bytes require a new reviewed
freeze. The return/drawdown report remains pending.

## September 5 — authenticated Tiingo follow-up

The holder supplied a Tiingo credential in the ignored local `.env`. Eight
requests to the documented historical EOD endpoint succeeded, each explicitly
bounded to **2006-02-28–2021-12-31**. Authentication used an HTTPS header, never
a query parameter or logged value. CSV dates were checked before numerical
conversion. Each ETF has all **3,990 expected sessions**, without extra dates,
fills or substitutions. No protected price observations were requested or
numerically parsed by this capture/audit.

Tiingo documents raw and adjusted OHLC, ex-date cash distributions, and split
factors. The adjusted-return check uses **Tiingo's own adjusted prices**, not
Yahoo's adjustment factors; ratios remove harmless differences in absolute
adjusted price levels. Raw prices were aligned to end-of-seen-window share
units using observed split factors. EEM's recorded factor is a slightly rounded
3-for-1; it was retained as delivered, not silently changed. Dividend comparisons
retain both contemporary-share and already-restated hypotheses. [API fields
and adjustment methodology](https://www.tiingo.com/documentation/end-of-day).

### Findings

The prior SPY 2009-10-01 execution-open discrepancy is **corroborated in Yahoo's
favor** by Tiingo, not a reason to patch Yahoo using the old QuantConnect
sample. All 175 checked SPY execution opens are within the unchanged tolerance.
This is corroboration from another feed, not a claim of exchange-certified
ground truth or fully independent upstream lineage.

| ETF | Daily close flags / 3,990 | Next-open flags / 175 | Changed horizon votes / 525 |
|---|---:|---:|---:|
| SPY | 6 | 0 | 0 |
| IWM | 83 | 5 | 0 |
| EFA | 16 | 3 | 0 |
| EEM | 26 | 10 | 1 |
| IEF | 9 | 3 | 0 |
| TLT | 16 | 6 | 2 |
| GLD | 7 | 6 | 0 |
| DBC | 68 | 5 | 1 |

All four changed votes and all 38 flagged monthly execution opens belong to
**development**. Aggregating the actual calendar requirement maps, rather than
assigning periods from a decision's calendar year:

- Development: 3,048 horizon votes, four changes; 1,016 next-open comparisons,
  38 flags. First/last decisions: 2007-05-31 and 2017-11-30.
- Validation/seen B: 1,152 horizon votes, no changes; 384 next-open comparisons,
  no flags. First/last decisions: 2017-12-29 and 2021-11-30.

The four changed decisions are DBC's 15-month vote on 2008-10-31, EEM's
12-month vote on 2015-03-31, and TLT's 15-month votes on 2011-01-31 and
2013-03-28. DBC involves a substantial month-end closing-price disagreement;
the others involve votes close to cash. They are not four strategy trades or
measured portfolio-return differences. No performance sensitivity was run.

Of 580 symbol/ex-date cases where either feed reports a distribution, **579
agree within Yahoo's three-decimal rounding** after EEM share-unit alignment.
The remaining case is **TLT on 2012-11-01**: Tiingo has a distribution and
Yahoo has zero. The **issuer independently confirms the missing Yahoo event**:
cash income of **$0.269553/share**, record date November 5, paid November 7.
BlackRock's fund download returned the exact filename
`iShares-20-Year-Treasury-Bond-ETF_fund.xls`; `Distributions!A168:H168` contains
the event. The total-distribution and income fields agree, with zero capital
gains and return of capital. [Issuer download](https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=239454&component=fundDownload&userType=individual).

The [bounded issuer extract](../../experiments/BA-002/preflight/20260905/tlt-2012-11-issuer-distribution.json)
preserves source identity, fields, retrieval metadata and the full response's
UTF-8 SHA-256:
`d1d3f37beb296153ab64ed8853b09e19320767fd93e0d60016f7157b3f3e50a1`.
Only the November 2012 distribution row was extracted numerically; other
worksheets and later distribution amounts were not inspected. The full current
workbook was not retained. The initial 2012 tax-summary URL returned 404, but
the fund download resolved the event. The issuer record does not establish
whether Hurricane Sandy explains the omission or affected scheduling.

The vendors' adjusted-price factors also differ across that date; Yahoo lacks
the corresponding dividend adjustment step. Therefore a correction must address
**both total-return prices and the distribution input**, not just populate one
tax-event cell. No correction has been made, and its economic impact has not
been calculated. Any earlier result using the affected Yahoo history needs
this data-quality caveat; existing BA-001 artifacts have not been rewritten.

Across all 31,920 sessions the Tiingo open/close adjustment factor is uniform
within floating-point precision (maximum relative mismatch below 5e-16).
That corroborates the within-session factor convention; it **does not**
validate every historical opening print. There are 1,067 daily-open and 231
daily-close flags in total. The fixed tolerance remains the greater of $0.02
or 5 bps of the aligned reference price. No tolerance or strategy threshold
was relaxed after these observations.

### Local evidence and reproduction

Raw Tiingo responses and bounded normalized CSVs are in ignored local
`data/snapshots/tiingo-seen-20260905-v1/`, with checksums and token-free request
URLs. Its manifest SHA-256 is
`e58f1be2bc3757a4a5a161f227a60e50af97533ef1278a9c3d45329306a0d795`.
The completion manifest was written last. The selected Yahoo snapshot and
`data/current` were not changed. Raw and row-level reference evidence remains
local under Tiingo's internal-use terms, not in this public repo. [Product
licensing](https://www.tiingo.com/products/end-of-day-stock-price-data),
[terms](https://api.tiingo.com/tos/).

The [local final diagnostic](../../experiments/BA-002/preflight/20260905/tiingo-check-v2.json)
contains per-file checksums, diagnostic source hashes, distribution comparisons,
vote differences and flagged execution opens. The original `tiingo-check.json`
is retained; v2 adds explicit period summaries and diagnostic code hashes.
An offline replay of v2 exactly matched its saved JSON object.

Replay with no credential or network access, using a **new** output path:

```sh
.venv/bin/python -m tools.check_ba002_tiingo \
  --snapshot data/snapshots/20260904T192633Z \
  --reference data/snapshots/tiingo-seen-20260905-v1 \
  --output experiments/BA-002/preflight/20260905/tiingo-replay.json
```

The capture option `--capture` requires a new reference directory and reads
only `TIINGO_API_KEY` from `.env`. It is unnecessary for replay. Requests cannot
override the eight-symbol universe or seen-date bounds. Redirects are refused;
upstream error text and response contents are suppressed on failure.

**112 focused tests passed** in a single run of the three source-diagnostic
test modules (14 existing, 75 capture, 23 comparison tests). These are offline
fictional tests, not 112 historical evaluations or a rerun of the full engine
suite. Discriminating fixtures catch cross-zero votes, equality voting, split
ex-date errors, threshold inflation, omitted horizons and a removed next-open
date cap. Capture tests cover secret-safe failures, exact coverage, invalid
numbers, date-first filtering, checksums and incomplete captures.

The runtime code and evaluator hashes remain those recorded above. The freeze
is still **draft**; there is no canonical family journal and no BA-002 sweep
directory. The data blocker remains open, not converted into a strategy fail.
The next useful step is an explicit, issuer-supported correction of the Yahoo
distribution **and adjusted-return history**, then a fixed-rule comparison
across the two vendor datasets to quantify residual source sensitivity. That
changes the proposed input evidence and requires a new reviewed freeze before
formal evaluation. Do not silently replace the primary source or select a feed
by which one produces more alpha. No new account or paid subscription is needed
for the two local captures already obtained.

Boundary disclosure for this follow-up: the bounded authenticated requests and
local audit respected the cap. Separate searches for the 2012 issuer document
returned unsolicited later TLT return-table and GOVT quote snippets. Those
pages were not opened, and the values were not used or recorded in the audit.
This does not constitute a holdout evaluation, but must not be described as an
absolutely observation-free external search.
