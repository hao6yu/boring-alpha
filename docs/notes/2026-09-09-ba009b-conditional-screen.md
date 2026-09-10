# BA-009B: conditional gap screen and retail availability audit

Research date: 2026-09-09 America/Chicago; artifacts created September 10 UTC.

**Decision: no paper execution build or funded pilot is justified.** The
tested ETH rule has weak economics, and the apparent BTC result depends on
sparse observations that precede the retail opening implied by Coinbase's
currently published rollover rule. This is an exploratory price diagnostic,
not a return estimate or a conclusive rejection of every futures spread rule.

The next bounded experiment would use the actual monthly contract universe
at each historical time. Its immediate prerequisite is a usable public source
for expired-contract prices: the four-request probe below failed. Preserve
this result, declare any universe correction as a new candidate version, and
keep this screen's thresholds and timing fixed. Park the historical retest
until that data is available; do not search for a better percentile or hold.

## Inputs and fixed calculation

- [Recorded policy](../../research/ba009b-conditional-screen-policy.json), written
  before calculating this conditional screen, but after inspecting the broad
  historical distribution. It is **not independent preregistered evidence**.
- [Saved hourly inputs](../../data/us_crypto/futures-history/20260910T000515491884Z/manifest.json):
  exact September BTC/ETH dated contracts against their perpetual-style contracts.
- [Saved quote reference](../../data/us_crypto/spread-snapshots/20260910T000602055125Z/report.json).
- [Conditional result](../../data/us_crypto/conditional-screens/20260910T003307209820Z/report.json),
  including every eligible signal, missing outcome, and weekly comparison.
- [Minute timing audit](2026-09-09-ba009b-minute-audit.md): a separately fixed
  September 8–9 sample, not an audit of the older August signal dates.

At each positive-volume paired hourly observation, calculate the 90th
percentile of the preceding seven calendar days, requiring at least 84 prior
paired bars and excluding the current bar. Flag a positive gap strictly above
that threshold. The signal candle starting at `s` is known at `s + 1h`;
the delayed entry proxy uses the next candle's close, known at `s + 2h`.
Measure its gap change to the close 24 hours later. Both legs' closes are
last-trade proxies, potentially at different times within the same hour.

For equal fixed underlying quantities, price movement is
`(entry dollar gap - exit dollar gap) / entry perp price × 10,000`.
This avoids inventing profit from changing denominators. All reported basis
points are relative to **one perp leg's notional**, not return on the $5,000.

Before checking outcomes or high/ordinary group membership, a second view
selects eligible observations at least 25 hours apart. Missing entry/exit
bars remain visible; endpoint availability does not establish survival,
marks, or margin compliance between them. The final 25 signal hours can
have outcomes beyond the archive and are identified separately.

## Raw conditional results

| Measure | BTC | ETH |
|---|---:|---:|
| Eligible hourly signals, including ordinary times | 435 | 404 |
| High-gap signals | 22 | 11 |
| High-gap signals with both outcome endpoints | 11 | 9 |
| High-gap signals missing an endpoint | 11 | 2 |
| Mean delayed gap narrowing, basis points | 31.57 | -6.76 |
| Median delayed gap narrowing, basis points | 35.62 | 6.01 |
| Mean ordinary-time narrowing, basis points | 3.13 | 1.13 |
| Median reference cost hurdle for high observations, basis points | 28.82 | 39.32 |

The reference hurdle assumes integer contracts within a $2,500 cap per leg,
the prior base commission scenario, the prior quote's spread, 10% annual
funding paid by the long perp, and 4% cash opportunity cost on the full
$5,000. It is **not actual historical cost**. Commission floors are included.
Depth was sampled at the original snapshot quantity, not matched to each
historical quantity. The report also includes doubled spreads and stressed
commissions. Funding rates are assumptions here; no settled funding ledger
or historical fills have been reconstructed.

BTC's 22 high signals occur on just four UTC dates: August 7 and August
22–24. Seven of the eleven observed outcomes have missing interior bars.
Only **one observed high-gap outcome** remains in the globally spaced view,
plus one high signal with a missing outcome. Most high observations cluster
in week 34, where the three observed ordinary-time outcomes actually have
larger mean narrowing. The pooled high/ordinary difference therefore does
not isolate predictive information from calendar effects or missingness.

ETH's gap narrows by a mean 35.54 basis points before the delayed entry
over its eleven observed entries. After entry, its nine observed 24-hour
outcomes average widening, and none exceeds the base reference cost hurdle.
The globally spaced view contains no ETH high signals; it provides no
independent-event corroboration.

## Retail contract availability changes the interpretation

Coinbase's [contract-rolling documentation](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-contract-rolling)
says the next contract opens for trading at 6 PM ET two days before front-month
expiration. Its [U.S. futures introduction](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-intro)
also describes the two-day opening rule. Public product metadata for
[August BTC](https://api.coinbase.com/api/v3/brokerage/market/products/BIT-28AUG26-CDE)
and [August ETH](https://api.coinbase.com/api/v3/brokerage/market/products/ET-28AUG26-CDE)
reports expiry on August 28, 2026 at 15:00 UTC.

Applying the currently documented rule implies the September contracts
opened on **August 26 at 22:00 UTC**. Neither help page provides a historical
policy effective date or account entitlement history. This is an explicitly
labeled eligibility sensitivity, not proof that a particular account could
or could not trade at that past time. Historical exchange candles alone
cannot establish accessibility through Coinbase Financial Markets.

Keeping the original classifications and including only signals known at
or after that implied opening gives the following
[saved sensitivity](../../data/us_crypto/availability-audits/20260910T004331445246Z/report.json),
which records the input report hashes, rule source, cutoff, and selection:

| High-gap observations after implied retail opening | BTC | ETH |
|---|---:|---:|
| Signals | 0 | 7 |
| Observed outcomes | 0 | 7 |
| Mean delayed narrowing, basis points | — | 10.57 |
| Median delayed narrowing, basis points | — | 8.03 |
| Median base reference hurdle, basis points | — | 39.30 |
| Price movements exceeding their base hurdle | — | 0 of 7 |

These are overlapping observations, not independent trades or a win rate.
Past exchange candles remain in the original signal lookback; this does
not reconstruct a front-month strategy or change the original screen.
The sensitivity makes BTC's apparent opportunity ineligible as evidence of
a historically executable Coinbase retail edge. ETH still lacks sufficient
movement to meet the assumed costs.

## Timing audit

All 192 individual hourly closes in the separate 48-hour sample reconcile
to their respective latest traded minute. They are still not simultaneous:
BTC's largest hourly gap of $305 per BTC becomes $200 at the last minute
when both legs traded; the final trades were five minutes apart. ETH's
largest hourly gap of $10.50 becomes $8 at its last common traded minute.

Positive gaps remain in all 48 paired hours for each asset. Common-minute
closes still may come from different seconds, and their differences can
also include genuine movement between the common minute and the hour end.
This audit does not establish executable prices or explain the August events.

## Next experiment and stopping rule

The [expired-history probe](../../data/us_crypto/expired-history-probes/20260910T003910124094Z/report.json)
made exactly four public requests: metadata and August 24 hourly candles
for each August BTC/ETH contract. Both metadata calls succeeded, but both
candle calls returned HTTP 400, `product_id argument is invalid`. Counts
are unavailable, not zero. The endpoint recognizes expired metadata but
did not provide those expired prices. No alternative free historical source
has been verified in this round; this is not a claim that none exists.

1. Establish a public expired-contract history source before implementing
   the universe retest. Do not substitute current September contracts for
   August's tradable contract or pay for data to rescue this weak result.
   If usable public history cannot be established in a bounded source check,
   park this branch; a forward data archive would be a separate research
   decision, not a reason to build paper execution now.
2. With suitable inputs, construct a short history of monthly contracts selected using a
   documented, time-aware retail availability convention. Record uncertainty
   where historical access cannot be verified. Preserve exact contract IDs;
   never stitch a contract switch into apparent spread profit. Reset the
   per-contract signal lookback and exclude positions crossing a switch or
   expiry unless the actual closing and reopening costs are modeled.
3. Declare the changed universe as a separate exploratory version. Retain
   the seven-day/90th-percentile signal, one-hour entry delay, 24-hour hold,
   costs, missingness reporting, and comparable ordinary-time controls.
   Obtain tighter time alignment for any events that appear economically
   material before interpreting them as opportunities.
4. Stop this rule if the correctly selected contracts offer no credible
   movement beyond the cost range or the apparent result again depends on
   stale prices and a few missing/clustered observations. If data remain
   inadequate, park it as unresolved rather than tune around the gaps.
   Build paper execution only after that screen warrants it and funding,
   marks, fills, and margin can be reconciled.

This keeps the next research step finite. It authorizes no deployment,
recurring recorder, paid data, account access, or change to the user's capital.

## Reproduction and checks

```sh
.venv/bin/python -B tools/us_spread_conditional.py --snapshot data/us_crypto/conditional-screens/20260910T003307209820Z
.venv/bin/python -B tools/us_futures_minute_audit.py --snapshot data/us_crypto/minute-audits/20260910T003123921821Z
```

Conditional replay matches the saved calculations and input manifest hashes;
its comparison excludes the analysis source hash because only the CLI replay
and display behavior changed after calculation. Minute replay uses copied
hourly reference responses and works independently of the original hourly
archive's location. Inputs are immutable and hash checked.

The focused futures/crypto accounting, data, bootstrap, and new diagnostic
regression run passed **145 tests**. This is not a full-repository test claim.
