# BA-012 Stage A — input and static sizing checks

**Historical preparation snapshot.** The user subsequently approved the $1
aggregate Databento estimate budget. Acquisition is underway; the pending
approval and no-download statements below describe the earlier preflight.
See the [authorization record](../../research/ba012-stage-a/acquisition-authorization.json)
and [current status](../QUANT_RESEARCH.md) for subsequent work.

September 10, 2026. The user's subsequent “go” advances the frozen protocol to
the sizing-only evaluation. **No historical sizing result or strategy return
has been calculated.** This note records completed preparation and the exact
remaining evidence, not a pass for BA-012.

## What the account arithmetic establishes

The [frozen protocol](../strategies/BA-012.md) SHA-256 remains
`095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f`.

At $5,000, stress plus entry and reserved closing costs permit at most **four
total contracts**. At least three markets in three asset groups are required,
so no individual position can exceed two contracts. One contract in each of
the five markets consumes $1,079.23 of the $1,000 stipulated loss budget and
is therefore excluded before estimating volatility.

Nevertheless, the static rules are not contradictory. Exhaustive integer
enumeration finds 33 quantity patterns satisfying the stress budget and group
count. Of these, 28 satisfy doubled initial-margin funding for either direction
in every market, two depend on direction, and three fail for all directions.
These counts **omit** measured volatility, concentration, monthly signal
eligibility, target tracking and covariance risk during partial fills.

For example, one NES, one M6E and one MZC uses $669.54 of stipulated stress
and round-trip costs. Even using the more expensive initial-margin direction
for each contract, $2,555.509 covers those costs, twice initial margin and the
$100 buffer. This establishes mechanical possibility only; it is not a
proposed trade or a prediction of loss.

The [exact arithmetic](../../research/ba012-stage-a/static-constraint-bounds.json)
is reproducible with `tools/ba012_static_bounds.py --check`. An independent
exact-decimal enumeration reproduced all 33 records.

## A cheaper necessary risk test

Starting from cash, each selected sleeve by itself is a possible partial-fill
state. Consequently every selected quantity must satisfy `abs(q_i) * v_i <=
tau`. If fewer than three asset groups contain an eligible instrument whose
one-contract annual dollar volatility is at most $400, the $5,000 account
cannot enter a permitted basket. This is a mathematical consequence of the
frozen partial-fill rule, not a changed risk target.

| Virtual equity | Simulated loss budget | Annual dollar-volatility cap | Total-contract upper bound from stress/costs |
|---|---:|---:|---:|
| $5,000 | $1,000 | $400 | 4 |
| $25,000 | $5,000 | $2,000 | 24 |
| $100,000 | $20,000 | $8,000 | 98 |

The larger amounts are sensitivity cases from the protocol, not funding
recommendations. Passing a necessary test is insufficient: the complete
basket and every partial-fill state must still satisfy the frozen conditions.

## Data access and narrow acquisition proposal

The existing archive contains MES observations, not the ES/TN/6E/GC/ZC panel
required here. Existing 2024–2025 price files were not opened for this check.

Authenticated Databento metadata requests returned HTTP 200 and positive
record counts for all five parent roots from January 11, 2016 through
December 31, 2023. The all-minute, all-maturity price quote totals
**$106.921715587378**. A separate full-period instrument-definition quote is
$2.146186396480. Neither broad request was downloaded or purchased. Positive
aggregate counts do not establish coverage of the required exact contracts
and reference minutes.

The narrower [request manifest](../../research/ba012-stage-a/reference-acquisition-proposal.json)
contains 2,080 weekday windows, each 09:59–10:00 America/Chicago, across all
maturities of just those five parent roots. UTC timestamps account for DST.
Acquiring every weekday intentionally includes holidays as a superset;
strategy sessions are selected using an independently constructed exchange
calendar, never inferred from whether prices happen to be present. Including
maturities preserves both old and new roll legs without selecting by volume.

The [complete narrow quote](../../research/ba012-stage-a/20260910T074018356649Z/quote.json)
is **$0.156779289039** for all 2,080 windows. Metadata-only retries resolved 84
initial transport failures and then one remaining failure; both incomplete
snapshots are preserved and linked by checksums. No historical data download
has occurred. This is the provider's estimate for the exact request list, not
a statement that every required outright has a valid observation.

The prepared collector's offline preflight passes with a proposed **$1
aggregate estimate ceiling**, including failed/uncertain attempts. It makes no
data requests by default. Its 36 focused tests passed, and an independent
review checked credential handling, durable reservations, prior attempts,
resumption and exact request bounds. The shared transport regression checks
also passed in the implementation review. This validates collection controls,
not input quality or strategy performance.

Acquisition funding confirmation is pending; the exact request, full quote and
collector were prepared before requesting it. No account balance was inferred
from successful API authentication.
The browser billing session is signed out, so the remaining signup-credit
balance has not been reverified. Databento states that historical usage
consumes credits before charging money; the prior balance observation is not
a new billing confirmation.
[Pricing and credit rules](https://databento.com/docs/faqs/usage-pricing-and-data-credits).

The [metadata quote tool](../../tools/quote_ba012_inputs.py) has only cost/count
endpoints, receives the key through a hidden prompt, saves no credentials and
does not follow redirects. Its request-date checks cover winter/summer DST,
uniqueness and the exclusion of 2024–2025. Provider estimates do not enforce
a hard spending cap.
[Cost endpoint](https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost).

## Remaining evidence

Resolve acquisition funding; then obtain and validate the inputs, finish the
independent product-specific roll map, build matching-maturity dollar movements,
and evaluate the frozen monthly sizing rules. The
[calendar and unit review](2026-09-10-ba012-calendar-interpretation.md) records
2,007 independently reconstructed joint sessions, product-expiry questions and
vendor-reported historical coverage issues. Input gaps must stay explicit as
DATA_INCOMPLETE, rather than being misreported as capital infeasibility.
No bot, strategy-return backtest, account change, subscription or order follows
from these static checks.
