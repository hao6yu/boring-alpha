# BA-009B first feasibility result

September 9, 2026, America/Chicago; public data collected just after midnight
September 10 UTC. Candidate: [dated/perpetual futures spread](../strategies/BA-009B.md).

**Result: no pilot entry justified.** The construction fits the initial capital
and margin scenarios, and its modeled trading costs are lower than BA-009's
spot/futures construction. The observed premium is small after those costs.
Historical candles support exploratory description, but not an executable
backtest or a funding-settlement ledger. No predictive model has been fitted.

This result completes the first feasibility investigation; it does not
establish that every future spread opportunity will fail. Further work should
address synchronized quotes and funding marks before optimizing an entry rule.

## What was built and checked

- `tools/us_futures_spread.py` collects public product metadata and four books
  concurrently, validates tradability, book age (15 seconds maximum at
  collection completion), and pair timestamp skew (2 seconds maximum).
- Product selection uses one hourly-funded BTC/ETH perp and the nearest
  eligible dated expiry in the observed listing. Later view-only contracts
  are excluded. Current product flags are not account approval.
- Each alternative uses a separate $5,000 account, fixed equal underlying
  quantities, and an initial gross-notional cap of $5,000. Each leg is capped
  at half the account. Long-perp and short-dated overnight margins are summed
  without offset credit. The $1,000 buffer is tested after fees and the
  immediate mark loss from crossing both spreads.
- Four commissions, signed funding, spread/depth, the full-account cash
  benchmark, and 1/7/14-day horizons are priced explicitly. Scenarios vary
  fees, funding, terminal gap, and unchanged/doubled exit widths. Horizons
  within 24 hours of expiry are excluded. Zero terminal gap is a hypothetical
  favorable scenario, never a promised convergence or the selected forecast.
- `tools/us_futures_history.py` archives the exact U.S. products' hourly
  candles, verifies hashes and request ranges, and leaves missing hours
  missing. A real API pagination discrepancy was detected and corrected.

The pricing equation uses bid/ask fills directly; spread is not deducted a
second time. Both futures sit in the futures account: common price movement
nets their signed P&L. Not assuming margin-offset credit does not mean
discarding the profitable leg's mark-to-market gains.

## Quote result

Archive: `data/us_crypto/spread-snapshots/20260910T000602055125Z/`.
The BTC and ETH book timestamp skews were 0.66 and 0.33 seconds respectively.
These are near-simultaneous indicative books, not an atomic pair execution.

| Initial position alternative | BTC | ETH |
| --- | ---: | ---: |
| Long perp / short September future, contracts per leg | 3 | 10 |
| Underlying quantity per leg | 0.03 BTC | 1 ETH |
| Approximate notional per leg | $2,350–$2,356 | $2,469–$2,474 |
| Midpoint dated-minus-perp gap per underlying unit | $219.17 | $5.75 |
| Executable entry gap per underlying unit | $205.00 | $4.50 |
| Sum of initial margin requirements | $1,258.22 | $1,388.55 |
| Marked equity beyond initial margin after entry fees | $3,739.00 | $3,607.20 |

Base fees are assumed to be 5 bps per side on each instrument, with a $0.15
minimum per contract. The dated floor is also an assumption. Funding below
holds the currently reported hourly rate and reference perp price constant;
future funding and prices can differ. Exit widths equal current observed widths.

| Entire midpoint gap reaches zero by exit | BTC net P&L | BTC excess over 4% cash | ETH net P&L | ETH excess over 4% cash |
| --- | ---: | ---: | ---: | ---: |
| 1 day | +$0.91 | +$0.36 | −$3.34 | −$3.89 |
| 7 days | +$0.23 | −$3.60 | −$6.90 | −$10.73 |
| 14 days | −$0.56 | −$8.23 | −$11.04 | −$18.72 |

The BTC one-day scenario needs approximately **$207.11/BTC of midpoint gap
narrowing**, against an initial $219.17 gap, to beat 4% cash. That leaves very
little room for residual basis, delays, worse execution, or fee error. Half
the gap closing in one day loses $2.93 against cash in the base case.

With a $0.50 assumed dated-contract minimum, even the one-day zero-gap BTC
scenario loses $0.29 against cash. Doubling exit widths also removes the small
base-case surplus. At the lower fee assumptions a positive scenario exists,
but the experiment has not estimated a probability or a predictive entry
condition for that outcome. Selecting the best grid row would not establish
an edge.

For the one-day zero-gap scenario, base round-trip fees plus current spreads
are approximately **$5.55 BTC / $8.50 ETH**, versus roughly $59/$63 in the
earlier spot construction. ETH's four per-contract fee floors alone total
$6 at ten contracts per leg. Fees therefore remain meaningful even after
removing the spot leg. The earlier and current quotes were collected at
different times; this is a modeled cost comparison, not a simultaneous test.

## Margin and execution stresses

A common underlying rise of 50%, preserving the dollar gap, combined with a
1.5x increase in margin rates leaves approximately $2,168 BTC / $1,874 ETH
of modeled equity headroom. These quantities pass that scenario without
assuming collateral offsets. A separate 1%-of-underlying additional gap
widening loses approximately $23.50/$24.69. A failed hedge followed by a 20%
adverse underlying move loses roughly $471/$495 on the isolated leg before
funding, emergency execution costs, and fees.

These are particular stresses, not a maximum possible loss or a guarantee
that losses stop at $1,000. Initial notional caps can be exceeded as fixed
quantities change in value. No liquidation simulation or fill adapter exists.

## Fees and historical evidence

The [exchange fee schedule effective January 26, 2026](https://assets.ctfassets.net/k3n74unfin40/sgInuF26edJX4v4nUlE29/87f18103cd35feede93f0bb92a5f1065/Fee_Schedule_1.26.2026.pdf)
lists $0.10 per contract per side for BIT/BIP/ET/ETP electronic professional
and non-professional trading. This is exchange-only, not the customer's
complete brokerage/clearing commission. The [dated evidence record](../../research/ba009b-fee-evidence.json)
and [scenario policy](../../research/ba009b-feasibility-policy.json) keep those
facts separate from assumed all-in prices.

The usable 90-day candle archive is
`data/us_crypto/futures-history/20260910T000515491884Z/`:

- Both perps have 2,144 returned hourly bars out of 2,160 requested calendar
  hours. September dated contracts have 669 BTC and 619 ETH bars, with first
  returned bars in late July. Current metadata cannot reconstruct when each
  contract was tradable through the user's broker.
- Descriptive median close gaps were $435/BTC and $10.50/ETH. Consecutive
  paired 24-hour windows had median gap changes of −$15/BTC and −$0.50/ETH.
  These are overlapping, unconditional, asynchronous last-trade comparisons.
  They do not establish attainable P&L or exclude a conditional opportunity.
- There are no uninterrupted seven-day calendar windows under the importer's
  strict rule; regular maintenance also breaks this rule. That count must
  not be presented as proof that no seven-day trade could be evaluated with
  a properly reconciled market calendar.
- Funding export rows are not confirmed settled events. Coinbase says a fully
  closed hour has no published funding rate, and funding uses representative
  futures marks rather than hourly last trades. Continuous exported rows
  therefore need reconciliation with the market calendar and event marks.
  [Official funding mechanics](https://help.coinbase.com/en/coinbase/derivatives/us-perpetual-futures-overview)

The [historical-data note](2026-09-09-ba009b-history.md) documents the 300-bar
effective API ceiling despite a documented 350 limit, all missing ranges,
timestamp conventions, and the exact collection/replay commands. The earlier
truncated download is retained with a warning; it is not the analyzed dataset.

## Decision and next useful work

**Do not fund a pilot from this result.** The sampled entry is not robustly
attractive after reasonable cost stresses. Historical data leaves the
conditional spread hypothesis unresolved. No opposite-direction search,
parameter sweep, or ML fitting is justified by the present result.

The next useful evidence is synchronized executable quote history, plus
verified final funding rates/marks and the trading calendar. Public forward
quote collection or a documented historical source can supply that evidence;
it need not require an account deposit. A candidate rule and independent test
can be defined once data quality and the available spread movement justify it.
No recurring collection, paid data, account change, outreach, or live execution
was started by this first test.

## Reproduce

```sh
.venv/bin/python -B tools/us_futures_spread.py --snapshot data/us_crypto/spread-snapshots/20260910T000602055125Z
.venv/bin/python -B tools/us_futures_history.py --snapshot data/us_crypto/futures-history/20260910T000515491884Z
.venv/bin/python -B -m pytest tests/test_us_futures_spread.py tests/test_us_futures_history.py tests/test_us_crypto_carry.py tests/test_futures_account.py tests/test_us_funding_history.py -q -p no:cacheprovider
```

The focused checks cover hand-calculated P&L and fee/funding units, entry mark
loss, separate margin accounting, expiry cutoffs, contract sizes, closed and
view-only markets, quote skew, source integrity, and missing data. Both saved
analyses replay offline without replacing their reports.

Validation: **46 focused checks passed**, followed by **186 relevant regression
checks passed in 9.31 seconds**, including the corrected BA-007 engine, perp
fetching, fee accounting, and research-boundary tests. Both archived reports
reproduced exactly; local links and `git diff --check` passed. The unrelated
full repository Monte Carlo suite was not rerun.
