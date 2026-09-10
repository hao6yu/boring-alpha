# BA-009B: minute alignment audit

**Result:** tighter trade-time alignment reduces some apparent hourly
extremes, but the positive dated/perp price gap remains throughout this
48-hour sample. This does not establish an executable spread or a profitable
trade. An expiry premium can reflect expected funding and other costs.

The sample and method were fixed before minute collection: September 8,
2026 00:00 UTC through September 10 00:00 UTC, exclusive. The research date
is September 9 in America/Chicago; the data collection occurred September
10 at approximately 00:31 UTC. There was no signal fitting or selected entry
time. This is a retrospective timing diagnostic, not an independent forecast
test or a new holdout.

## Inputs and method

The archive is
`data/us_crypto/minute-audits/20260910T003123921821Z/`.
It contains original bytes for **40 minute-candle responses and four current
product responses**, using only public unauthenticated Coinbase endpoints.
Exactly **44 network requests** were used, with no retries or additional
probes. Each request covers at most 300 minutes, reflecting the effective
ceiling observed in the earlier hourly audit. The
[official public candle endpoint](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles)
supports `ONE_MINUTE` candles. Requests use `end=b-1` to express a half-open
interval `[a,b)` without overlapping boundary buckets.

The new archive also contains byte-for-byte copies of the four relevant raw
hourly responses and their original manifest from
`data/us_crypto/futures-history/20260910T000515491884Z/`. Thus offline replay
does not depend on retaining the original directory at its original path.
Both new network responses and copied reference inputs retain hashes and
source URLs. Request times, receipt times, HTTP dates, exact contract IDs,
the fixed sample, and code hashes are recorded. Original files are not
overwritten; a new collection creates a fresh archive directory.

For each hour, the audit:

1. Finds each leg's last reported minute with positive volume. It records
   how many minute buckets that trade precedes the final `xx:59` bucket.
2. Checks whether that minute's close exactly reproduces the previously
   archived hourly close. A mismatch is excluded from timing-only summaries.
3. Finds the **last minute within the same hour in which both legs report
   positive volume**. No price is carried forward or across an hour boundary.
4. Compares the original hourly gap with the gap between those two common
   minute closes. It reports the five largest absolute hourly gaps using a
   fixed ranking, plus every hourly comparison.

The gap always means dated close minus perp close, in dollars **per underlying
BTC or ETH**, rather than per nano contract. A reported trade minute gives
only a bucket, not the last trade's exact second. Two trades within the same
minute may still occur at different times and opposite sides of the market.

## Coverage and timing

| Exact product | Positive-volume minute bars | Of 2,880 calendar minutes | Hourly reference bars |
|---|---:|---:|---:|
| BIP-20DEC30-CDE | 2,759 | 95.80% | 48 |
| BIT-25SEP26-CDE | 1,911 | 66.35% | 48 |
| ETP-20DEC30-CDE | 2,569 | 89.20% | 48 |
| ET-25SEP26-CDE | 1,241 | 43.09% | 48 |

Every returned minute has positive reported volume. Missing calendar minutes
remain missing; they are not assumed to have zero prices or interpolated
trades. BTC has **1,878** common positive-volume minutes and ETH has **1,159**.
Both pairs have at least one common minute in **all 48 hours**, and all **192
individual hourly closes** exactly reconcile to their latest minute closes.

| Timing measure | BTC | ETH |
|---|---:|---:|
| Hours with different last-trade minute buckets | 13 / 48 | 29 / 48 |
| Median separation between legs' final trade minutes | 0 minutes | 1 minute |
| Maximum separation | 5 minutes | 14 minutes |
| Median lag of last common minute from `xx:59` | 0 minutes | 1 minute |
| Maximum common-minute lag | 7 minutes | 14 minutes |

For individual legs, the maximum last-trade minute lag is 1 minute for the
BTC perp, 5 for the BTC dated future, 2 for the ETH perp, and 14 for the ETH
dated future. The dated legs are the less active side of these pairs in this
sample. Activity within a minute does not establish enough order-book depth
to trade both legs.

## How much do the gaps change?

| Same 48 matched hours | BTC hourly closes | BTC common-minute closes | ETH hourly closes | ETH common-minute closes |
|---|---:|---:|---:|---:|
| Minimum gap | $160 | $170 | $3.50 | $3.50 |
| Median gap | $230 | $227.50 | $6.00 | $6.50 |
| Maximum gap | $305 | $275 | $10.50 | $9.00 |

The median absolute adjustment is **$0/BTC** and **$0.50/ETH**; the mean is
$6.56/BTC and $0.75/ETH. The maximum absolute difference between the two
measurement methods is **$105/BTC** and **$3.50/ETH**. The gap changes in 8
of 48 BTC hours and 27 of 48 ETH hours. No matched gap changes sign: all
hourly and common-minute gaps are positive in this sample.

The most prominent timing examples are:

| Hour, UTC | Original gap | Last common-minute gap | Relevant timing |
|---|---:|---:|---|
| BTC, September 9 02:00 | $305 | $200 | Perp last traded in 02:59, dated in 02:54; last common minute is 02:52 |
| BTC, September 8 07:00 | $160 | $220 | Final trade minutes are 07:59 and 07:56; common minute is 07:56 |
| ETH, September 8 02:00 | $10.50 | $8.00 | Final trade minutes are six minutes apart; common minute is 02:53 |
| ETH, September 8 10:00 | $7.50 | $4.00 | Final trade minutes are five minutes apart; common minute is 10:54 |
| ETH, September 9 05:00 | $3.50 | $7.00 | Final trade minutes are eleven minutes apart; common minute is 05:48 |

The **hourly BTC maximum itself** falls from $305 to $200 at its common
minute; the $275 maximum of the aligned series occurs in a different hour.
Likewise, the original $10.50 ETH maximum becomes $8, while the aligned
series maximum is $9 elsewhere. Comparing only overall minima/maxima would
hide that distinction.

This shows that asynchronous endpoints materially affect some apparent
opportunities. It does not prove that every dollar of the adjustment is
an artifact: moving to an earlier common minute also changes the measurement
time, and the actual spread may move in between. The fixed recent sample
also does **not** include or resolve the older 90-day extrema of $1,290/BTC
and $30/ETH. Those would require a separately declared investigation.

## What this permits next

Hourly close gaps should not be used as executable entry quotes. Tighter
alignment is a necessary improvement, but minute closes still lack paired
bid/ask prices, exact trade timestamps, fillable depth, legging behavior,
and event-time funding marks. Neither the positive premium nor its partial
survival after alignment is evidence of net profit.

The useful next step is to evaluate synchronized public bid/ask snapshots
against a frozen cost and funding hurdle, or obtain an appropriate historical
quote dataset. This audit itself does not place orders, fit a trading rule,
estimate realized funding cash flow, calculate P&L, or schedule collection.

## Reproduction and interface

```sh
.venv/bin/python -B tools/us_futures_minute_audit.py --snapshot data/us_crypto/minute-audits/20260910T003123921821Z
.venv/bin/python -B -m pytest tests/test_us_futures_minute_audit.py -q -p no:cacheprovider
```

All **15 tests pass**, including fixed sample/request budget, page boundaries,
false synchronization, missing data, zero-volume exclusion, hourly/minute
reconciliation, malformed candles, stable extreme selection, source URLs,
hash checks, and fully offline replay after moving the original hourly
archive. The saved real-data report also reproduces exactly offline. Running
the collector without `--snapshot` would create a new collection; it is not
needed to reproduce this result.

```python
from pathlib import Path
from us_futures_minute_audit import load_snapshot, analyze

folder = Path("data/us_crypto/minute-audits/20260910T003123921821Z")
manifest, minutes_by_id, hourly_by_id, products_by_id = load_snapshot(folder)
report = analyze(folder)
btc_hour_comparisons = report["pairs"]["BTC"]["hours"]
```

Add `tools` to the import path if calling from elsewhere. Every hourly
comparison preserves both last-trade minute buckets, the common minute,
both gap measurements, reconciliation flags, and whether the comparison
entered the aggregate summaries. Missing observations remain `None`.
