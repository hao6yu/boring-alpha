# Insider-purchase test: stop at the sample-size gate

**The fixed 200-company experiment cannot meet its registered sample minimums
in the acquired records. Profitability was not tested.** The source gate closed
after approximately 40 minutes and $0 of new paid data. No market price history,
strategy return, order or account was accessed in this run.

The full four-hour allowance was a cap, not a requirement to keep working after
a decisive failure. The remaining historical footnote review and portfolio
implementation would not rescue the source-size bound, so they were not pursued.
This version is closed, with the original cohort and thresholds unchanged.

## Decisive result

A company-month means one issuer with a potential signal in a disclosure month,
regardless of how many transaction rows or insiders it reported. The figures
below are **optimistic upper bounds**, not certified eligible signals or trades.
Actual eligibility can be lower after resolving all source details and liquidity.

| Registered requirement | Required | Optimistic maximum | Result |
|---|---:|---:|---|
| Non-routine purchase company-months | 80 | **75** | Fail |
| Non-routine distinct companies | 30 | 37 | Upper bound does not reject |
| Non-routine active months | 18 | 22 | Upper bound does not reject |
| Routine-purchase control company-months | 40 | **30** | Fail |
| Routine-control distinct companies | 20 | **14** | Fail |
| Routine-control active months | 12 | 16 | Upper bound does not reject |

These minimums were frozen before acquisition. They are operational research
floors, not a claim that 80 observations automatically establish statistical
power or that 75 observations cannot contain useful information.
[Frozen policy](experiment-policy.json), [final decision](final-decision.json).

## What was completed

- Downloaded all four planned public archives: submission, reporting-owner,
  non-derivative transaction and footnote tables. Total **2,596,778,046 bytes**;
  each matched its published MD5 checksum and received a local SHA-256 hash.
- Indexed **1,116,270 unique 2018–2023 Form 4/4-A accessions**. Projected the
  fixed cohort and cross-issuer history for 2,709 potentially relevant owners,
  covering 68,925 filing accessions.
- Retained all **200 issuers and 4,800 issuer-month slots**, including months
  without observed purchases. The initial cohort sample contained 1,898 P-code
  rows across 350 issuer-months, before strategy exclusions.
- Compared the new bulk tables with **13 original SEC filing controls**. All
  timestamps, issuer/owner identifiers, footnotes and the 23 non-derivative
  transaction rows matched the previously captured originals.
- Reconciled **47,386 known accessions** from cached SEC indexes: none was
  missing from the acquired metadata. The 440 cases where an index CIK differs
  from the actual issuer are preserved; an index can refer to a reporting owner.
  No ticker or directory CIK was substituted for the issuer identity.

The public source is the [Layline Insider Trading Dataset](https://doi.org/10.7910/DVN/VH6GVH),
version 430, released May 21, 2026, with its
[data publication](https://doi.org/10.1038/s41597-023-02147-6).
No new account, subscription or credential was needed.
[Download manifest](download-manifest.json),
[original-source audit](original-source-audit.json).

## Why the optimistic bound is sufficient to stop

First, apply only clear current-purchase exclusions. The sequential exclusions
were 885 rows covered by six explicitly reviewed trading-plan disclosures,
27 amendment rows, 32 clearly non-common securities, and 86 rows without an
officer/director or ambiguous role. That leaves a deliberately generous current
pool of 868 rows across 313 issuer-months. Ambiguous cases remain possible.

Then make the historical side more permissive than the actual strategy:
count all source P/S transactions, including amended, planned, private,
non-common and missing-price rows. Give unparseable dates the benefit of every
historical month, and give an unprojected owner the benefit of both classes.
The non-routine ceiling even includes owners who might ultimately be routine.
Neither prices nor returns influence this calculation.

Even that generous history sometimes cannot supply a transaction in each of
the required three prior calendar years, or the same calendar month in all
three years for the routine control. The registered rule requires every
relevant owner in a qualifying issuer-month to meet its classification. A
valid current purchase by an owner who cannot meet that necessary history
condition prevents that group from qualifying.

Only a current purchase that has already cleared the basic source checks can
establish such an exclusion. A single reporting owner is required for these
checks; any issuer-month with a known amendment is ignored. Comparisons use
exact security titles, preserving alternative potential share classes. Cases
still needing source review cannot tighten the bound. This yields the 75/30
ceilings above, before further filtering could reduce them.

A separate SQL/calendar calculation verified **all 691 supporting purchase
rows across 331 distinct owner-years**, then reproduced the final counts.
It shares audited source inputs with the first calculation; it is an internal
cross-check, not an external replication.
[Bound](opportunity-upper-bound-mandatory-witnesses.json),
[supporting history records](necessary-history-witnesses.json),
[verification](necessary-bound-verification.json).

## Important interpretation limits

- **No return verdict exists.** The annual return, drawdown, cash benchmark,
  commission/slippage and incremental-performance tests were not reached.
- The fixed 2019 incumbent cohort is too sparse for this particular rule and
  its controls. This result does not establish whether a broader insider
  strategy would be profitable. A broader cohort would be a separate experiment.
- The initial detailed classification was explicitly provisional. Its 32/7
  counts are not final signal counts and must not be promoted as results.
  Historical footnote and amendment reviews remain incomplete; the optimistic
  bound lets the registered test stop without pretending those reviews passed.
- Eight current-purchase note contexts were reviewed. Two apparent exclusion
  flags concerned separate grant or preferred-security rows; their common-stock
  purchases were allowed. This avoided blindly excluding an entire filing
  because an unrelated footnote mentioned the issuer or a public offering.
- The 35 timezone-bearing transaction-date strings that the preliminary parser
  did not normalize received maximally favorable treatment in the upper bound.
  They therefore cannot make that ceiling artificially small.
- Upstream error logs were retained and reconciled. Seven apparent missing
  index records proved to be Form 3/3-A records outside the strategy's Form 4
  scope. One globally missing accession has neither a cohort nor a relevant
  owner CIK in its available references. No known relevant missing accession
  was found. These checks are not a guarantee of population-wide data accuracy;
  the bounds are conditional on the acquired source records.

[Footnote decisions](footnote-review.json),
[upstream error reconciliation](upstream-error-reconciliation.json).

## Reproduction and retained work

The data and source-processing tools remain available locally. The immutable
policy checksum is
`6519c99f01e44c233f0034f2f963477d883fa3c97d648e72229c26760bab7a42`.
Raw archives, projected SQLite tables and the complete 4,800-slot ledger are
in the ignored `data/snapshots/insider-purchase-test-2026-09-13/` directory.
The final decision records the slot ledger's checksum.

From the repository root, reproduce the offline decisive calculation with:

```sh
.venv/bin/python research/insider-purchase-test-2026-09-13/opportunity_upper_bound.py --current-rules
.venv/bin/python research/insider-purchase-test-2026-09-13/opportunity_upper_bound.py --current-rules --mandatory-witnesses
.venv/bin/python research/insider-purchase-test-2026-09-13/verify_necessary_bound.py
.venv/bin/python -m pytest research/insider-purchase-test-2026-09-13/test_insider_rules.py -q
```

The six focused rule tests passed. No new account simulator was built, no
2024–2025 equity strategy price window was opened, and no cohort expansion or
variation follows automatically. Earlier failures and their commits are
preserved. This run did not commit or push the new research files.
