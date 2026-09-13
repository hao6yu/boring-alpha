# Minimal chronological earnings-text test dataset

Prepared September 10, 2026 (America/Chicago), from local scripts and artifacts
only. This is a proposed acquisition/data plan for the authorized test, not a
registered trading protocol or a result. No network, model fitting or investment
returns were used to prepare it. Root owns source qualification and the final
execution/model protocol.

Use **100 incumbent CIKs selected using information available in 2019 Q3**, then
collect their 2020–2023 events. Use 2020 for the first fit, 2021 for chronological
development, and 2022–2023 for one frozen evaluation. This is a substantially
smaller first screen than a full-market study. It can test incremental language
information in this declared incumbent sample; it cannot establish broad-market
profitability or justify funding on its own.

## Point-in-time cohort before collecting outcomes

1. Archive `https://www.sec.gov/Archives/edgar/full-index/2019/QTR3/master.idx`.
   Rank its unique original Form 8-K CIKs by ascending
   `SHA256("BA-equity-event-test-2019Q3-v1|" + zero_padded_10_digit_CIK)`.
   Freeze this seed and rule before listing the selected names or inspecting
   their price histories.
2. In rank order, inspect original filings accepted no later than September 30,
   2019. Select the first 100 issuers with a verified original full quarterly or
   year-end earnings Item 2.02 release and a U.S.-listed ordinary/common stock
   class established by a contemporaneous cover. Preserve every screened CIK,
   exclusion, source and uncertainty. Use the new explicit full-release rule;
   retain preliminary disclosures separately.
3. Restrict the first screen to an unambiguous single listed common class.
   Funds, preferred shares, warrants, units, OTC-only securities and unresolved
   multi-class/ADR mappings do not silently become common-stock observations.
   Resolve a higher-ranked candidate's uncertain eligibility before finalizing
   the first 100; a provider's missing prices do not make a CIK ineligible.
4. Freeze all 100 CIKs. Do not replace a name because it later delists, changes
   ticker, stops reporting, has poor returns, lacks a prior document, or lacks
   provider coverage. Reconcile ticker/class/venue changes at their actual
   effective dates. Current submissions tickers and current provider exchange
   labels are discovery aids, not historical identity evidence.

Membership is known before the first 2020 decision. This deliberately excludes
post-September-2019 IPOs and the rest of the market. It is an **incumbent-only
point-in-time cohort**, not a reconstructed historical index. It does not
require future survival. A name already ineligible for listed-stock trading at
a particular event cannot receive a new entry, but stays in the cohort ledger.

The former 25-issuer/100-slot cohort was selected in 2023 Q3 and cannot supply
this historical universe. Its sources are reusable only if the newly frozen
CIKs/accessions independently require those exact documents; no one is added
to improve cache reuse or coverage.

## Events, timing and chronological separation

| Data period | Purpose | Proposed use |
| --- | --- | --- |
| Calendar 2019 original releases | Prior-year narrative/period joins and cohort evidence | Inputs only; no 2019 strategy result needed |
| Calendar 2020 | Initial fit | Only labels whose complete 20-session horizons are available by each fit cutoff |
| Calendar 2021 | Chronological validation | Choose the small regularization/feature specification; no 2022–2023 outcome inspection |
| Calendar 2022 through final eligible November 2023 entry | Frozen evaluation | Same two models and matched event baseline; no model/horizon contest |
| Through December 29, 2023 | Mature final evaluation holdings/outcomes | Last scheduled entry November 30 gives 20 following NYSE sessions within 2023 |
| Calendar 2024–2025 | Reserved | No prices, labels, model selection or repair by peeking |

Retain 16 fixed calendar event-window slots per issuer: **1,600 slots**. Select
the first full original release within each window and deduplicate by disclosed
fiscal period, not an assumed calendar quarter. A slot can be missing; 1,600
slots is not a claim of 1,600 actual earnings events. Keep right-censored late
2023 events in the inventory even though they cannot supply a completed
20-session outcome without opening 2024. Do not shorten their horizon.

Use the existing following-session-close timing proxy: the entry session is
strictly after both official filing date and Eastern acceptance date. Preserve
exact-clock conflicts and require the independently verified daily entry to be
invariant. Select/transform each input only from documents available by that
decision. Inspect original preliminary/guidance candidates over the contract's
90-day lookback and explicitly referenced earlier disclosures, recording
coverage; this does not establish absence of all prior public information.

Before the January 2022 evaluation begins, freeze the chosen specification and
refit only on 2020–2021 labels already matured by the fit cutoff. If root chooses
monthly expanding refits, their schedule and label-maturity embargo must be
frozen now and used identically by both models. No full-period vocabulary or
standardization. A calendar-year split without the 20-session maturity rule is
insufficient.

## Small model, realistic sample size

There are at most **800 development slots and 800 evaluation slots**, before
missing documents, no-event windows, delistings, liquidity exclusions and the
late-2023 boundary. An illustrative planning range is 350–650 eligible
development observations and a similar evaluation count; it is a scenario,
not measured coverage. The initial 2020 fit alone may have only 175–325 usable
events. Report actual counts by year, issuer, fiscal scope and exclusion reason
before fitting.

That scale supports only a deliberately small elastic-net screen: roughly
25–50 training-selected text terms/features in total, a short numerical/price
feature set, and a tiny predeclared regularization choice. The precise feature
cap and penalty protocol belong in root's registration. It does **not** support
an unrestricted thousands-of-terms search, modern pretrained historical scores,
or searching many holding periods. Both numerical-only and text-added models
receive identical metadata, missingness, predecessor and past-price controls.
The three accounting examples are extraction tests, not a trained feature panel.

Even hundreds of events are not hundreds of independent investment outcomes:
issuers repeat and 20-session holdings overlap. Only 24 evaluation months are
available. A positive result must remain exploratory and carry calendar-block
and issuer-dependence uncertainty; weak precision is not repaired by treating
each daily row as an independent sample. A much smaller realized panel may
still exercise the system, but cannot be advertised as persuasive text-alpha
evidence.

## Required data and approximate request count

The least-effort path is **one history per security plus immutable document
deduplication**, not one price request per event.

| Item | Concrete scope | Planning estimate, not a quote |
| --- | --- | --- |
| SEC master indexes | 2019–2023 quarterly indexes for selection and independent filing-frame checks | 20 indexes; one 2023 Q3 index already cached |
| SEC submissions | Selected CIKs plus rank-screen candidates; only historical pages intersecting 2019–2023 | Approximately 150–250 screened CIKs; 150–750 metadata payloads at 1–3 relevant pages each; actual upper limit must be declared before collection |
| Original current/prior release records | About 1,600 current slots plus up to 400 unique 2019 prior releases | Roughly 5,000–7,500 index/primary/exhibit requests including typical nonqualifying candidates; unusually many supplemental filings increase this |
| Price/identity series | 100 fixed issuers, historical aliases/classes, one reference market series | Roughly 100–130 whole-window price requests, plus up to the same number of metadata requests; multiple aliases/venues may require more |
| Accounting/text extraction | Required original current/prior pairs only | Local processing; source/table evidence and unresolved values retained |

Request the equity price window **2019-10-01 through 2023-12-31** (actual last
regular session December 29), with raw and adjusted OHLC, raw-volume semantics,
split/dividend events and inactive-name coverage. October 7, 2019 is the 60th
preceding NYSE session for January 2, 2020, so October 1 provides a small margin.
Do not fetch 2024 as an API convenience. Root must choose and qualify the market
reference separately; using its prices for a benchmark does not propose a
passive allocation to the user.

The original pilot assumed 50 Tiingo requests/hour and 500 unique securities
per month. If still applicable, 200–260 metadata/price calls require roughly
4–6 quota hours before retries; this is not permission to exceed verified
quotas. A bulk or already-authorized source may reduce wall time. SEC work at
the established four-request/second ceiling has an ideal 20–35-minute floor
for this document volume, with actual elapsed time likely longer. Manual
fiscal/identity repairs, not arithmetic, may dominate. Do not promise an
immediate backtest from the 100-slot cache.

## Reuse and the shortest collection order

The original SEC archive contains 705 successful sources for 26 distinct
archived CIKs, 44 submissions payloads and only the 2023 Q3 master index. Its
99 selected current events run from October 2022 through September 2023.
These observed cache counts are not the number of sources reusable by a fresh
2019 cohort; overlap is unknown until selection is frozen.

1. Qualify the missing fixed-pilot source as root is doing, then freeze the
   chronological protocol and the above seed. Do not rerank the old survivors.
2. Build the 2019 ranking and 100-name historical identity manifest first.
   Deduplicate requests by exact URL/accession and validate all reused hashes.
3. Obtain one bounded 2019–2023 price history per frozen security, qualify raw
   units/actions/inactive mappings, and derive liquidity only from information
   available before each decision. A missing provider history is unresolved,
   not an ex-ante liquidity rejection or reason to replace an issuer.
4. Use SEC submissions Item 2.02 metadata to prioritize original releases; check
   against historical master indexes for missing accessions. Download each
   index, primary, release and explicitly referenced same-filing shareholder
   letter once. Reuse 2020–2022 current releases as later prior documents.
   Keep original non-2.02/6-K prior documents when independently qualified.
5. Build source/timing/fiscal/feature panels, preserve every failed slot, and
   publish per-year counts plus raw-unit and endpoint coverage before fitting.
   Missing predictors follow the registered shared missingness rule. Missing
   tradable marks, original narrative or outcome endpoints cannot become zero
   returns or silently dropped held positions.
6. Fit/validate only the development slice. Run one frozen 2022–2023 account
   evaluation after data gates pass. Root's long-only whole-share, 20-session,
   cost/cash and inactive-position rules govern the test; this document does
   not invent fill or corporate-action credit dates.

## Concrete remaining implementation/data blockers

- The collector is pinned to the old policy, directory, 2023 seed and four
  windows; `finalize_collected` also reinstates the old preliminary ambiguity
  gate. Do **not** rerun it against new paths by editing its frozen constants.
  Reuse its parsing and safe-fetch routines in a new bounded runner with v2
  full-release classification, year-specific provenance and no old writes.
- Historical security/alias and complete raw-price/action coverage remain
  prerequisites. PTN's current split-restated chart is not a qualified template
  for converting every historical OHLC/volume field. New cohort names can
  expose similar gaps; a vendor's survival-biased history cannot define membership.
- Source-grounded revenue/EPS extraction, duration/share-basis flags, aligned
  current/prior narrative and all missingness are not yet built for this panel.
  A document join is not numerical-feature readiness.
- The declared ATVI/SIVB ledger controls permit explicit receivable or marked/
  unpriced holdings; they do not by themselves supply a complete daily NAV or
  an executable forced exit. Root's frozen test must specify these outcomes
  before inspecting any returns.

This is the smallest recommended **chronological exploratory screen**, not a
replacement of the failed availability audit or a full academic replication.
Its practical next artifact is the frozen 2019 cohort with an exact deduplicated
source/price request manifest and actual per-year data counts.
