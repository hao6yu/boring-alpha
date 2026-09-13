# Earnings-release data pilot: result and remaining work

**Result: the data gate did not pass.** Of 100 fixed event slots, 89 passed
the combined document, event-definition, identity, timing and price-window
checks; the requirement was at least 95. Inactive-security treatment also
remains unresolved. Profitability is untested: no model was trained, no strategy
returns were calculated, and no trade was placed.

The collection and reconciled result took approximately 42 minutes, within the
two-hour limit. New paid data cost was **$0**. Used public SEC documents and the
existing Tiingo connection; no account or subscription changes were made.

This follows the [earnings-release hypothesis and initial audit](2026-09-10-equity-event-feasibility.md).
The candidate remains a long-only, 20-session text-plus-numerical model compared
with an otherwise identical numerical baseline. This pilot neither validates
nor rejects its ability to earn money.

| Check | Result out of 100 fixed slots |
| --- | ---: |
| Original full earnings releases recovered | 99 |
| Original prior-year fiscal-period releases matched | 97 |
| Historical cover identities / daily timing proxies | 99 / 99 |
| Complete, structurally valid price windows | 95 |
| Document-and-price joins before event-definition admission | 93 |
| Combined checks, including event definition | **89** |

These are availability and consistency counts. They do not certify every
accounting feature, corporate action, market fill or first-publication timestamp.
The [reconciled result](../../research/equity-event-pilot-2026-09-10/result.json)
retains all 100 slots and every overlapping failure reason.

## The eleven blocked slots

| Cases | Slots | Exact remaining issue |
| --- | ---: | --- |
| Palatin / PTN, all four windows | 4 | The requested 2022–2023 price history is empty. Tiingo's PTN metadata starts November 12, 2025. A targeted PTNT lookup also returned no requested history and names Internet Patents Corp in provider metadata, so it cannot establish the required Palatin mapping. |
| Datasea / DTSS, first two windows | 2 | No matching original prior-period release was verified in the targeted original 8-K/6-K searches. This does not establish that no release exists anywhere. |
| Datasea / DTSS, April–June 2023 | 1 | No qualifying original Item 2.02 earnings event was found for the fixed window. The slot remains in the denominator. |
| APRN W1; SDPI, SNBR and CVLT W2 | 4 | Earlier preliminary disclosures contain actual or estimated results for the ended period. The frozen wording did not explicitly decide whether these or the later full releases define the event. |

The collector used the first full, non-preliminary release. I had not specified
that distinction clearly enough before collection, so the four ambiguous cases
remain admission failures. For example, CVLT disclosed preliminary revenue/EPS
on January 10 before its January 31 full release. A later test must explicitly
define its event and account for information already released. Guidance,
liquidity updates and preliminary earnings are retained as distinct predecessors;
the later full release is not labeled the first earnings information.

Removing this ambiguity alone would leave **93/100** document-and-price joins,
still below the threshold. Failed issuers were not deleted, given replacement
price series from other companies, or assigned zero returns.

## What the audit established

The sampling rule was fixed before downloading: rank historical Q3 2023 SEC
issuers by a seeded hash and select 25 qualifying issuers, then inspect four
calendar release windows from October 2022 through September 2023. These are
**100 slots**, not a promise that every company announced earnings in every
window. The Q3 issuer selection can postdate earlier events; this cohort is an
availability diagnostic and cannot serve as a point-in-time performance universe.

Independent review caught a sampling implementation error: the classifier missed
BSBK's genuine quarterly release because its headline said “three and six months.”
Correcting the frozen rank rule included BSBK and displaced CCLD from the initial
published 25. The initial issuer list, initial 100-slot records and CCLD data
remain preserved separately. The
[correction record](../../research/equity-event-pilot-2026-09-10/sec-selection-correction.json)
documents this change; the original policy hash was not rewritten. Reported
counts above refer to the corrected, independently audited cohort.

The SEC collector acquired **705 distinct successful payloads in 730 attempts**.
The 25 recovered failures—23 transport failures and two HTTP 503 responses—remain
in the ledger. Historical ranking, source hashes, prior-period evidence and the
final price-join bindings passed independent checks with no global validation
failures. [Independent document audit](../../research/equity-event-pilot-2026-09-10/sample-audit.json).

There were **20 exact clock discrepancies** between SEC index Eastern acceptance
times and API timestamps labeled UTC. For all 99 recovered current releases,
both interpretations produced the same following regular-session entry date
after considering the official filing date. The daily proxy is therefore
resolved under the declared rule; exact clock conflicts remain recorded.
Acceptance does not establish first website availability or first issuer news.
[SEC timing explanation](https://www.sec.gov/about/webmaster-frequently-asked-questions).

Price checks used 60 preceding sessions, the entry session, and 20 following
sessions: **81 sessions per available event window**. The 31 main Tiingo requests
and three inactive-control requests stayed within the reserved limits; none
returned HTTP 429. Independent Decimal-based checks reproduced all 100 join
results with zero mismatches. Raw/adjusted OHLC, action fields, calendar coverage
and adjustment-factor consistency were checked. CIDM and CNVS responses were
byte-identical. Raw licensed prices remain git-ignored and internal.
[Independent price audit](../../research/equity-event-pilot-2026-09-10/price-validation.json).

Original document matching required more than finding a date one year earlier.
TIL's prior release was in a non-Item-2.02 8-K; TEAM's four priors were on 6-Ks.
Their original releases were recovered. TEAM also transitioned from IFRS to
U.S. GAAP, SNPO compares a 13-week quarter with a 14-week quarter, and some
releases contain both annual and quarterly columns. ENVX supplies a short
press release and a separate financial shareholder letter. These distinctions
remain explicit. The pilot does **not** certify unchanged numerical definitions
or silently normalize accounting measures.
[Manual period review](../../research/equity-event-pilot-2026-09-10/manual-period-review.json).

## Inactive stocks need explicit treatment

SIVBQ's history includes 12 rows during the March 10–27 Nasdaq halt, including
four with positive volume. Those rows cannot establish executable Nasdaq trading.
The [Nasdaq halt announcement](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-halts-svb-financial-group)
and [OCC symbol-change memo](https://infomemo.theocc.com/infomemos?number=52179)
must be joined to the price series rather than inferring trading status from
row existence.

ATVI's acquisition-date price and dividend fields do not encode its documented
$95 cash entitlement. The
[issuer's completion filing](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b)
supports entitlement, but this pilot did not establish a broker cash-credit
date or an executable acquisition-day closing trade. An extended dividend
check confirmed an adjustment-factor change across August 1; it did not find
the initially suspected missing adjustment. No terminal return, halt fill or
cash-availability date was imputed.
[Inactive-controls audit](../../research/equity-event-pilot-2026-09-10/inactive-results.json).

## Recommendation

Keep the earnings-release hypothesis at the research stage. The next useful
deliverable is one bounded repair proposal covering the missing historical
price source, an explicit preliminary-versus-full-release rule, and halt/merger
accounting. It must also define numerical comparability before feature extraction.
Preserve the Datasea gaps and the original sample; any future performance
universe must be fixed from information available at each historical decision.

Only after those requirements are resolved should a separate multi-year
experiment test incremental text value after costs against the numerical
baseline and cash. The 2024–2025 equity strategy evaluation remains reserved.
The evidence here supports a specific data-repair decision, not a profitability
claim or a funded pilot.
