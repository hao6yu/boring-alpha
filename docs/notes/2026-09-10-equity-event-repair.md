# Earnings-event repair: 93/100, data gate still fails

September 10, 2026, America/Chicago. The user authorized one targeted repair
after the [100-slot pilot](2026-09-10-equity-event-pilot.md). The frozen budget
was one hour and $0 in new paid data. Initial evidence reconciliation took
about 17 minutes; final synthesis took about 19 minutes. Documentation and
review also finished within the hour. No model training or strategy-return
calculation occurred.

**Decision: stop this free-source repair path. The same 100 slots now produce
93 qualified combined joins, below the unchanged requirement of 95.** Four
admissions come from an explicit event-rule amendment, not newly repaired data
or evidence of profitability. Seven data gaps remain. The original 89/100
result and its input artifacts are preserved byte-for-byte.

## What changed

| Check | Original pilot | Repair v2 |
| --- | ---: | ---: |
| Fixed event slots | 100 | 100 |
| Original full current releases | 99 | 99 |
| Original prior-release matches | 97 | 97 |
| Qualified price windows | 95 | 95 |
| Date coverage including unqualified alternative prices | 95 | 99 |
| Combined qualified joins | 89 | **93** |
| Required combined joins | 95 | **95** |
| Inactive-security treatment | Unresolved | Declared ledger policy only passes |

These counts overlap; they must not be added. The missing-current DTSS slot
has no qualified event anchor for a price window. All 100 slots and all 99
selected accessions are unchanged. Twenty original exact-timestamp conflicts
remain visible; the accepted daily entry is invariant to the two recorded
timestamp interpretations. No clock conflict was silently corrected.

### Full release versus preliminary information

The explicit v2 target is the earliest original, regularly scheduled **full**
quarterly or year-end earnings release in each fixed window. Preliminary
results, estimates, guidance and selected metrics remain dated information
predecessors. This clarifies the target for every slot and resolves four
previous ambiguities: APRN W1, SDPI W2, SNBR W2 and CVLT W2.

This is an exploratory policy amendment made after inspecting documents and
before inspecting strategy returns. It does not establish that the original
rule was unambiguous or that the full release was the first public earnings
news. Five slots have known preliminary information, including UMBF's earlier
selected loan/deposit metrics. Guidance and accounting-transition presentations
have separate categories. Other slots retain limited-search/unknown coverage;
none receives a verified-absence claim.

Both future numerical-only and text-plus-numerical models must receive the same
predecessor, search-coverage and other source metadata. Earlier information
must not become a hidden advantage supplied only to the text model.

### PTN: downloaded, but not qualified

A bounded public Yahoo chart request returned all 336 expected sessions from
July 1, 2022 through October 31, 2023. Each of the four required 81-session
windows has structurally valid rows. However, the downloaded historical close
is demonstrably split-restated: Palatin's FY2023 report identifies a contemporaneous
June 16 close of $2.19, while the current chart reports $109.50, exactly 50 times
that amount. This agrees with the later announced reverse split; it does not
validate an entire raw OHLC/volume reconstruction.
[Issuer FY2023 report](https://www.annualreports.com/HostedData/AnnualReportArchive/p/AMEX_PTN_2023.pdf),
[issuer split announcement](https://palatin.com/press_releases/palatin-announces-1-for-50-reverse-stock-split/).

Complete subsequent corporate actions, all OHLC adjustment semantics and volume
basis remain unverified. The issuer's no-dividend statement does not establish
coverage through October 2023; an absent dividend field is not proof of zero
dividends. The four windows therefore remain unqualified. No raw reconstruction
was forced. The later split announcement is corporate-action metadata; no
2024–2025 strategy price history was opened.

Nasdaq's bounded historical request returned no rows; Stooq returned browser
verification HTML. The pass stopped after ten free source attempts. More dates
downloaded is a coverage improvement, not a data-gate pass.

### DTSS: original prior releases still missing

The two required original releases for quarters ended September 30 and December
31, 2021 were not recovered. Cached submissions contain no 8-K/6-K in the
examined prior-release windows. Three additional original filing indexes—the
November 2021 and February 2022 10-Qs and a November 2021 S-1/A—contain no
separately attached earnings release. This is a bounded unsuccessful search,
not proof no release existed anywhere.

Current-release comparative numbers and a 10-Q cannot manufacture an original
prior-release narrative. DTSS W1/W2 retain that failure; W3 still lacks its
current full release. No replacement issuer was sampled.

### Inactive holdings: a usable rule, with explicit limits

Nasdaq identifies October 12, 2023 as ATVI's last trading day, with the halt
after 20:00 Eastern. The provider's October 13 row is therefore ineligible as
a regular Nasdaq closing fill. Eligible held shares become a separate $95 per
share merger receivable on completion. Carrying that claim at face value is a
declared accounting convention; actual cash credit remains unknown and the
claim stays unavailable for spending or reinvestment.
[Nasdaq corporate-action alert](https://nasdaqtrader.com/TraderNews.aspx?id=ECA2023-588),
[issuer completion filing](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b).

For SIVB, preserve existing shares as unpriced through the March 10–27 halt,
with no invented fill or cash credit. The documented March 28 transition to
SIVBQ preserves the same common-share identity. The 45 matched post-transition
vendor closes through May 31 can be explicitly labeled holding-value proxies.
A valuation does not execute a sale.
[Nasdaq halt notice](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-halts-svb-financial-group),
[OCC identity and symbol-change memo](https://infomemo.theocc.com/infomemos?number=52179).

This passes the narrow ledger-policy requirement. Complete daily NAV/drawdown
through an unpriced halt and a forced 20-session liquidation still need declared
valuation, delayed-exit and execution/cost conventions before returns. Ultimate
bankruptcy recovery is unnecessary for a horizon ending on an available marked
holding. Neither a zero recovery nor guaranteed liquidity was assumed.

## Accounting is specified, not fully extracted

The [feature contract](../../research/equity-event-repair-2026-09-10/feature-contract.md)
defines reported GAAP revenue and diluted EPS, comparable periods/currencies,
historical share basis, missing-value flags and matched original text. It
distinguishes numerical comparatives available in the current original release
from the mandatory original prior document used for language and provenance.
Input imputation, if later registered, must learn only from past training data;
missing prices or outcomes cannot be imputed into returns.

Three [source-hashed examples](../../research/equity-event-repair-2026-09-10/accounting-examples.json)
check concrete edge cases:

- TEAM supplies same-basis current-original GAAP comparatives despite the prior
  release using IFRS. The two versions remain separate.
- SNPO compares a 13-week quarter with a 14-week quarter. Initial growth
  features stay missing; no average-week normalization is assumed.
- NXTC's selected annual EPS remains annual. A missing revenue row does not
  establish zero revenue. Currency/accounting-basis confirmation and share-price
  alignment are not certified by this example alone.

These examples do not certify all 100 slots' numerical features. The availability
sample also remains unsuitable as a performance universe: its Q3 2023 issuer
selection occurred after some of the sampled events.

## Stop condition and concrete reopening requirement

Do not train on the 93 survivors, lower the threshold, replace PTN/DTSS, or
start another model variation to avoid these failures. This result does not
reject the earnings-language hypothesis on profitability; profitability is
still unknown.

The next useful decision is access to a **small, independently qualified PTN
historical raw-price and corporate-action sample**, not another open-ended free
vendor search or a broad data subscription. It must cover the existing date
windows, historical share/volume units and actions. No provider coverage or
price is assumed here, and no purchase or vendor contact was made.

Recovering all four PTN windows would bring this unchanged cohort to 97/100;
the three DTSS failures would remain disclosed. Alternatively, verified original
DTSS releases could restore their own slots. Any supplied repair must be checked
against the same fixed gate. Even a pass would authorize planning a separately
registered, point-in-time multi-year experiment, not funding or a profit claim.

## Verification and artifacts

The independent offline audit reconciled original input/source hashes, unchanged
events, predecessor flags and each slot's admission state with no validation
failures. The independent count is 93; the separate synthesis agrees. Source
qualification is inherited from the source-specific audits, not claimed to be
an independent reconstruction of every price. Costs were $0 in new data: three
new SEC index requests, ten PTN source attempts, and bounded primary-source web
research for inactive controls. No new Tiingo request occurred.

- [Frozen policy](../../research/equity-event-repair-2026-09-10/policy.json)
- [Reconciled result and all 100 slots](../../research/equity-event-repair-2026-09-10/result.json)
- [Independent audit](../../research/equity-event-repair-2026-09-10/repair-audit.json)
- [PTN qualification](../../research/equity-event-repair-2026-09-10/ptn-qualification.json)
- [DTSS search boundaries](../../research/equity-event-repair-2026-09-10/dtss-repair.json)
- [Inactive-security ledger policy](../../research/equity-event-repair-2026-09-10/source-backed-ledger-policy.md)

Reconciliation is reproducible offline from the repository root with
`.venv/bin/python research/equity-event-repair-2026-09-10/synthesize_repair.py`.
Original source files remain local and unchanged. No trades, account changes,
subscriptions, return tests or reserved-period price inspection occurred.
