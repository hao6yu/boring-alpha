# After-tax implementation corrections

Date: 2026-09-04
Baseline reviewed: `16ee714`, branch `after-tax-overlay`
Design: [revision 3.3](../superpowers/specs/2026-09-04-after-tax-evaluation-design.md)

The implementation review found wrong tax amounts despite a passing suite.
This round corrects the accounting and the replay boundary before completing
the BA-001 post-hoc diagnostic. BA-001's charter, pre-tax classification and
sealed period are unchanged.

## Accounting corrections

- **Carried losses enter their character pools before netting.** A $100
  short-term carryover against a $100 long-term gain now consumes the loss
  with zero capital-gains tax; the reverse does too. Remaining loss pools
  retain character without counting incoming carry a second time. The
  carry-used fields attribute current-year losses before older losses of the
  same character; that reporting convention does not affect the tax bill.
- **Partial wash matches split replacement purchases.** Only matched shares
  receive extra basis and the transferred holding period. In the review's
  example, a four-share HIFO sale after the wash realizes $40, not $64; six
  unmatched shares keep their original basis and date.
- **FIFO follows acquisition order.** Transferring a capital-gain holding
  period cannot move a replacement purchase ahead of an older acquisition.
- **Buys and reinvestments share chronological wash matching.** The previous
  reservation of future fills has been replaced by a loss ledger that offers
  each purchase, including a reinvestment, in occurrence order. A January
  purchase can adjust the preceding December's loss before annual tax is
  calculated. Different source holding periods create distinct replacement
  portions rather than applying a maximum holding period to the entire buy.
- **Dividend qualification follows each disposed portion.** Partial sales
  retain their own dividend entitlements and disposal dates. The review's
  $9.90 distribution now splits into $4.90 qualified and $5 ordinary. The
  inclusive 121-day window excludes acquisition day and includes disposal
  day; an old lot sold on its ex-date has 61 eligible days.

These mechanics follow the capital-loss, wash-sale, basis-identification and
qualified-dividend rules described in [IRS Publication 550](https://www.irs.gov/publications/p550).
The project's declared approximations remain explicit below.

## Independent replay validation

The tax identities are insufficient to establish that the supplied trade
ledger describes the archived account. The replay boundary now reconstructs
cash and adjusted-unit positions from initial capital and fills, accrues cash
session by session, and compares reconstructed cash, exposure and equity with
every archived observation. It checks chronology, complete session coverage,
fill arithmetic, execution prices and finite values. Missing variants and
cropped run windows are refused against the manifest.

The reconciliation tolerance is 1e-9 relative with a $1e-7 absolute allowance
for floating-point accumulation and the engine's near-zero cash clamp. It is
independent of the source-price rounding tolerance used by the tax share
identity. An empty trade ledger passes only for an actual cash-only account.

## Identity and provenance

`DistributionTable.sha256` now identifies the input the overlay actually
uses: a canonical CSV hash, methodology, sorted period-truncated split records,
and `fingerprint_version = "distributions-input-v1"`. Raw source bytes and the
snapshot creation time are provenance, recorded separately. Changes confined
to future rows or future split records do not alter a development input hash.
Changes within the evaluated input produce a new sweep identity.

New sweep manifests contain `artifacts_sha256` for archived inputs, equity
curves, trade ledgers and recorded decisions. Replay checks those bytes and
the restored market fingerprint before scoring. Legacy archives lacking
per-file checksums are explicitly identified as such; their market fingerprint,
run coverage and account reconciliation still have to pass. This cannot
retroactively provide missing historical per-file checksums.

Post-hoc filenames retain their three components:
`tax-<policy12>-<distribution-input12>-<code12>.json`. Source provenance is
appended separately to `distributions_provenance.jsonl`, so a refetch with
identical evaluated inputs does not create an integrity alarm.

## Reports and tests

The readable benchmark identifies target exposure and cadence. Undefined
after-tax CAGR is displayed as unavailable rather than crashing the CLI.
Identity failures are reported across all scenarios. The task-9 extraction
instructions take exact output paths and verify the implementation and policy
hashes, instead of sorting hash filenames.

New regression fixtures use separately calculated expected amounts for the
interactions above. Deliberately reintroducing blended replacement basis,
FIFO by transferred date, skipped earlier reinvestments, or last-share
dividend qualification makes the corresponding regression fail. Disabling
replay reconciliation or archive checksum verification also fails its targeted
test. The tax-extras wiring test now captures the actual profile argument.

Full verification: `.venv/bin/python -m pytest -q` reports **496 passed,
46 subtests passed**. `git diff --check` is clean. These are execution counts,
not a claim about distinct declared test methods. Additional independent
synthetic checks covered engine/replay agreement and conservation through
random sequences of partial purchases and sales; no historical strategy
parameters were selected by those checks.

## Remaining scope

The output is a stylized federal-only sensitivity analysis. It still omits
state tax, NIIT, historical rate changes, the ordinary-income capital-loss
offset, foreign tax credits and GLD expense-sale accounting. It uses fixed
qualified fractions and two commodity-pool scenarios instead of reproducing
DBC K-1 allocations. The long-term holding rule still uses the declared
more-than-365-days approximation.

The NAV convention scales the pre-tax path after annual tax. It does not
execute tax-funding sales, their costs or taxable gains, or the resulting
exposure drift. Their size has not been bounded here; the old blanket claim
that every comparison holds sufficient cash has been removed. Drawdown stays
explicitly pre-tax. The eight scenarios quantify their selected assumptions,
not all uncertainty in the model.
