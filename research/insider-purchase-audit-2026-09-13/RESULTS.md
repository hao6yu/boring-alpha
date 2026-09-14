# Public insider purchases: bounded evidence and data audit

**Follow-up:** the user authorized the proposed fixed test. It
[stopped at its sample-size gate](../insider-purchase-test-2026-09-13/RESULTS.md)
after successful public-data acquisition; profitability was not tested.
The audit and proposal below are preserved as the earlier decision record.

Completed September 13, 2026. **Recommend one fixed exploratory test, conditional
on reconstructing the required history within its budget.** Basic filing
extraction works. Modern profitability, historical coverage and $5,000 account
economics remain unverified. This is neither a backtest pass nor a profitability
failure. No strategy has been promoted.

The authorized audit used **$0 of new paid data**, captured 1,585,467 bytes, and
made 42 SEC requests: 40 succeeded and two returned HTTP 403. It remained within
the two-hour, 60 MB and 45-request limits. No security return observations were
read, no insiders were classified, and no accounts or orders were accessed.

## Evidence that actually supports the hypothesis

**Published reference.** Cohen, Malloy and Pomorski (2012) initially classify an
insider after trades in each of three preceding calendar years. Trading in a
common calendar month across all three makes the insider routine; otherwise
opportunistic. Their main classification keeps routine status permanently and
rechecks opportunistic insiders annually. The sample ends in 2007. The headline
82 basis points monthly is a value-weighted long/short factor alpha, not a
long-only net return. Appendix Table A7 shifts regression returns to the 11th
of the following month, addressing reporting delay; it does not establish a
retail portfolio after fees.
[Full paper](https://dash.harvard.edu/server/api/core/bitstreams/7312037e-2b77-6bd4-e053-0100007fdf3b/content),
[publication](https://doi.org/10.1111/j.1540-6261.2012.01740.x).

**Recent positive evidence is incomplete.** Zhao's February 2026 preprint uses
2018–2024 microcap purchases and reports predictive performance on 2024 after
earlier training/validation. Its target is a large subsequent abnormal return,
not net account profit. Code is offered on request, the institutional price
source is unnamed, and the cost discussion is a rough subtraction rather than
an execution simulation. Filing-date closing inputs and next-day returns need
an explicit tradable entry: an after-hours follower cannot buy at the preceding
close. I did not reproduce its results.
[Preprint](https://arxiv.org/html/2602.06198v1).

**Recent counterevidence deserves attention.** Equibles' August 2026 vendor
study covers 47,458 disclosure events and reports no timing premium against
shifted windows, including its routine/opportunistic variants. It is commercial
primary research, not a peer-reviewed replication. The source acknowledges
missing delisted firms; its classification, median-return statistics and
benchmarks also differ from the academic study. These limitations prevent a
general rejection of insider signals, but weaken the case for assuming an
easy modern edge. I did not reproduce its results.
[Study and methodology](https://equibles.com/research/what-happens-after-an-insider-buys-evidence-from-47-458-open-market-purchases).

**Research judgment:** there is a defensible information hypothesis and enough
public timing evidence to justify one modest test. The sources do not support
an expected return, a probability of success, or funding a pilot.

## What the filing audit established

The SEC's quarterly ZIP returned 403, so the original transaction-stratified
sample could not run. A documented amendment fixed 10 original Form 4 and two
Form 4/A filings by hashing accessions in the previously cached 2023-Q1 index.
All 12 were retained. They contained no purchase-code P transactions, so a
second amendment added one explicitly selected positive parser control.

This is a convenience sample for field mechanics, not a random sample of the
market or an estimate of how often the strategy trades. Original XML was
compared with separately parsed rendered filing tables; both representations
derive from the same filing, so this does not verify the filer's accuracy.

| Requirement | Direct observation | Remaining condition |
|---|---|---|
| Transaction extraction | All 23 non-derivative rows across 11 filings matched on seven fields; two other filings had matching empty tables. | Sample success does not establish population accuracy. |
| Public timestamps | 11 of 12 cached metadata timestamps matched filing indexes; one conflicted. The extra purchase control has index-only timing. | Quarantine conflicts; never silently reinterpret a `Z` timestamp. |
| Delayed entry | 12 of these 13 indexes show acceptance at or after 16:00 Eastern. | Entry must follow actual publication and a tradable session; this proportion is not a population estimate. |
| Real purchases | The positive control contains three P acquisition rows with positive shares and prices. | P alone does not establish discretionary, open-market buying; private transactions and footnotes require review. |
| Identity and duplicate ownership | The purchase control has one issuer and three joint reporting owners; the archive directory identifies an owner, not the issuer. | Read issuer CIK from the filing. Do not multiply transactions by the number of owners. |
| Trading plans | Two filings mention 10b5-1 plans in footnotes, including the purchase control. | A missing checkbox is not proof of an unplanned trade. A trading plan and the paper's statistical routine classification are different concepts. |
| Amendments | Both amended forms supply an original-submission date; one describes an omitted withholding transaction. | Corrections become known on amendment publication, not retroactively on the original date. |
| Insider history | Individual owner CIKs and transaction dates are present. | Complete past histories were not acquired; zero insiders are classified. |
| Returns and execution | No market return data were inspected. | Historical security mapping, delistings, dividends, liquidity and attainable fills remain unverified for this signal. |

The purchase control reports **$4,665,376.89** in aggregate transaction notional,
counted once. Its footnotes identify prearranged purchases and common beneficial
ownership. It is a parser control, **not a qualifying discretionary signal**.
[Original filing](https://www.sec.gov/Archives/edgar/data/1056513/000089924323008575/xslF345X03/doc4.xml).

### Preserved timestamp conflict

Accession `0001626199-23-000025` has cached SEC submissions metadata of
`2023-01-05T19:32:19.000Z`. Its filing index says `2023-01-05 19:32:19`, which,
interpreted in Eastern time, is `2023-01-06T00:32:19Z`: five hours later.
The original cached JSON contains that value; the discrepancy was not introduced
by this audit's parser. A request for the linked complete-submission text
returned 403, ending further SEC retrieval under the amended policy.

The cause remains unresolved. Both observations are preserved and this filing
is flagged `CONFLICT_QUARANTINE`. It contains a derivative grant and would not
supply a purchase signal anyway. That does not justify ignoring the timestamp
problem in future collection.
[Filing index](https://www.sec.gov/Archives/edgar/data/1626199/000162619923000025/0001626199-23-000025-index.html).

## Free history route: available listing, incomplete validation

The SEC publishes quarterly ownership extracts, but their availability page
did not translate into successful bulk access in this environment.
[Official dataset](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets).

Harvard Dataverse's Layline dataset metadata was accessible without an account.
The inspected version was 430, released May 21, 2026. Its submission,
non-derivative, reporting-owner and footnote archives total approximately
**2.60 GB compressed**. These were not downloaded within the audit's 60 MB cap;
listing a file does not establish its historical completeness or accuracy.
[Dataset](https://doi.org/10.7910/DVN/VH6GVH),
[captured metadata endpoint](https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/VH6GVH).

I inspected the published 19 KB panel-construction script without executing it.
It aggregates owner roles at filing level and drops individual owner CIKs from
its convenient combined panel. Therefore that panel alone cannot support this
insider-history classification. Use the underlying tables and preserve issuer,
owner and transaction identities separately; footnotes remain necessary.
[Published construction code](https://dataverse.harvard.edu/api/access/datafile/7082855).

## Proposed next experiment — not started

**One four-hour exploratory replication, $0 new paid data, at most 3 GB of
compressed source downloads.** Freeze the full protocol before opening outcomes.
No ML model contest, alternate holding-period sweep or automatic extension.

1. **First gate: reconstruct events.** Obtain the underlying free tables and
   verify acceptance times, owner histories, duplicate handling and amendments
   against original controls. Keep all 200 issuers from the already fixed
   historical equity cohort, including unavailable and ineligible names.
   A source gap is a recorded gap, not permission to substitute a surviving
   ticker. Stop if usable events cannot be constructed inside the budget.
2. **One explicit adaptation.** Use a rolling three-calendar-year classification
   instead of the published main rule's permanent routine status. Require
   eligible trading in each year; insufficient history is unknown. Buy only
   publicly disclosed, non-routine common-stock purchases by officers/directors,
   excluding disclosed plans, private purchases and unresolved classifications.
   Label this a long-only follower adaptation, not an exact paper replication.
3. **One account and schedule.** Evaluate 2022–2023 as already exposed,
   exploratory market history. Use monthly selection, information public by
   the prior month-end, and entry in the next regular session. Model $5,000,
   whole shares, no leverage, four positions capped at 20% each, and cash when
   fewer qualify. Use a frozen hash ordering for excess signals. Specify
   liquidity, fill, exit, corporate-action and cash-account rules before testing.
4. **Ask the economic question.** Compare with routine-purchase and matched
   non-event controls, with identical portfolio constraints and costs. Report
   effect uncertainty and incremental performance, not only raw stock returns.
   Check event counts and missingness before outcomes; define the minimum sample
   in the protocol and stop if it is too sparse.
5. **One decision.** Apply the existing base/stress cost conventions and 6% cash
   hurdle to complete account results. Preserve the $1,000 loss-budget halt and
   report gap overshoot and drawdown separately. A weak or unresolved result
   ends this version. Even a positive exploratory result would require fresh
   confirmation before real-money use. The reserved 2024–2025 equity strategy
   window stays closed in this proposed test.

Small-account costs are material. IBKR Pro Fixed currently lists $0.005/share
with a $1 minimum per US stock order. As a **cost illustration only**, replacing
four $1,000 positions monthly makes 48 round trips per year: minimum commissions
plus 10/50 bp per-side execution loss total about $192/$576, or 3.84%/11.52% of
$5,000. This assumes constant trade sizes and excludes regulatory charges and
taxes; it is not forecast turnover, measured slippage or a strategy return.
Account conversion and actual pricing remain unverified.
[Published commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).

## Audit artifacts

- [Original limits and selection](audit-policy.json),
  [bulk-access sample amendment](sample-amendment.json), and
  [positive-control amendment](positive-control-amendment.json).
- [Frozen filing selection](filing-selection.json),
  [source URLs, statuses and hashes](sources.json), and
  [field observations, including the conflict](field-audit.json).
- [Offline comparison script](audit_fields.py) verifies captured source hashes
  and compares XML with rendered tables. Run from the repository root with
  `.venv/bin/python research/insider-purchase-audit-2026-09-13/audit_fields.py`.
  It reads local audit snapshots only and requests no market data.

Raw captures remain in the ignored local snapshot directory. The previous
failed strategies and earnings results are preserved. No framework was
installed, no strategy backtest was run, and no commit or push was made by this
audit.
