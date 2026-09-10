# BA-012 settlement download completed

**All 181 requested settlement queries are downloaded and verified.** The user
extended the earlier download time allowance. Completed files were reused;
the frozen contract, date, settlement-selection and sizing rules were retained.
The earlier bounded-attempt result remains preserved as a historical record.

The archive contains 3,277,624 raw statistics records, totaling 1,019,518,878
uncompressed bytes. All 181 exact query identities match the frozen active
contract/date plan exactly once. Compressed hashes, raw hashes and record counts
verify. There are no pending downloads, orphan files or remaining download locks.

## Estimated data usage

| Component | Reserved provider estimate, USD |
| --- | ---: |
| Original reference-minute acquisition | 0.162474512840 |
| Settlement acquisition, including unsuccessful attempts | 0.448956340545 |
| **Cumulative total** | **0.611430853385** |

The settlement ledger contains 187 paid attempts: 181 successful, four transport
errors, one initially rejected HTTP 206 response, and one interrupted request.
All six unsuccessful or uncertain reservations remain counted. Actual provider
billing was not queried. The cumulative estimate remains below the $1 ceiling.

The continuation used up to four downloads at once. After repeated connection
failures, the connection/read timeout was increased from 60 to 180 seconds and
isolated transport failures were allowed to leave other planned files running.
Failed files were retried in separate, newly quoted runs; successful files were
reused. The final run completed all its remaining requests. Twelve focused
collector tests passed, including cost accounting, preservation of in-flight
results, reuse and isolation of failed requests.

## Coverage under the unchanged version 2 rules

The complete archive yields 8,488 eligible references out of 10,211 required
references. The remaining 1,723 are unresolved under the frozen selection rules;
they are no longer unfinished download requests.

| Parent market | Eligible references | Unresolved references |
| --- | ---: | ---: |
| ES | 1,664 | 375 |
| TN | 1,642 | 397 |
| 6E | 1,639 | 400 |
| GC | 1,661 | 386 |
| ZC | 1,882 | 165 |

Of the unresolved references, 1,019 fall in 2016, 665 in 2017, three in 2018,
35 in 2020 and one in 2021. Reason labels overlap: 1,686 have no eligible
pre-cutoff settlement and 207 trigger the receive-time gate. These labels alone
do not mean settlement messages were absent. For example, all required 6E dates
have pre-cutoff messages, but 348 legacy references lack the required actual
settlement flag and 52 modern references include receipt times earlier than
their event times. Those rules were not relaxed after observing the data.

## Existing $5,000 sizing check

Twenty-five monthly windows have all 252 required intervals. They cover
August–December 2019, January 2020, June–December 2022, and all of 2023.
The unchanged sizing check returned verified cash decisions for all 25.

Each complete case has a necessary infeasibility proof: fewer than three market
groups can hold even one contract within the individual risk and money limits.
Gold is eligible in all 25 cases and NES in 13; MTN, M6E and MZC are eligible
in none. The required three-group basket therefore cannot be formed in these
observed complete cases at $5,000 under the frozen 8% volatility policy.

The other 47 monthly windows remain unresolved, with null quantities. They are
not cash observations. Because the protocol requires all 72 cases for its
overall capital rejection, the formal result remains
`INCOMPLETE_STUDY_NO_CAPITAL_VERDICT`. No strategy return, holdout performance,
larger-capital outcome or funded trading result was calculated.

Download completion is established. The remaining questions concern reference
eligibility and the proposed portfolio's capital requirements.

## Records

- Completion and ledger summary: `research/ba012-stage-a/download-completion-v2.json`
- Full input and sizing report: `research/ba012-stage-a/settlement-inputs-v2-continuation.json`
  (SHA256 `2b309c135d3b8982450a186e4e05f0d400bd02ec71f8ba6c98044cb77c3986cf`)
- Download-time extension: `research/ba012-stage-a/download-continuation-20260910.json`
- Archives: `data/futures/ba012-settlements/`, seven manifests
- Final acquisition run: `20260910T171039613878Z/manifest.json`

Independent reviews confirmed archive completeness, reserved-cost accounting,
frozen hashes, and the separation of the 25 cash results from 47 unresolved cases.
