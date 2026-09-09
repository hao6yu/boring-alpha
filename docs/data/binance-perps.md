# Binance USDT-M perps: what the BA-007 spine archives, and what it refuses to assume

One input family serves BA-007, and it is treated exactly like the equity corpus and the Coinbase spot archive: **fetched, hashed,
archived**. Source: the public S3 archive `data.binance.vision` (bucket `data.binance.vision`, region `ap-northeast-1`) — chosen by live
probes recorded in [`docs/decisions/2026-09-08-ba007-crypto-data-source.md`](../decisions/2026-09-08-ba007-crypto-data-source.md), after
every live API answer on this machine was refused or too shallow.

## The first full archive

`tools/fetch_perps.py` → `data/perps/current` (a symlink onto immutable `snapshots/<STAMP>/`):

| field | value |
| --- | --- |
| snapshot | `20260909T053321419791Z` |
| daily prices | `perps_daily.csv`: **703,507 rows over 1,018 symbols** (of 1,032 listed directories; 14 with no monthly archive) |
| funding | `funding_events.csv`: **2,831,180 events**, cadence declared per event (1h/2h/4h/8h family) |
| requests | 41,966 in the completing pass (0 answered absent); earlier partial passes' requests are not in this count — the resumable ledger, not the request counter, is the audit trail of the whole bootstrap |
| sha256 prices | `9fe74b854af0b7d8…` (48 MB) |
| sha256 funding | `030c3f05cf73792e…` (112 MB) |
| day holes | **2,221** calendar days missing inside served spans — reported and counted, never stitched |
| delisted symbols | included by construction (the enumeration lists the archive's own directories; FTTUSDT-style deaths keep their history) |
| synthetic | `false` — every row is an archive observation, none interpolated |

Span facts from the smoke test and the manifest: BTCUSDT's first served daily candle is **2020-01-02**; the oldest listings on the venue
reach back to 2019 (FIL-USDT-SWAP 2019-08 by listing time; BTC/ETH perps 2019-11). Daily bars are 00:00-UTC aligned (`1Dutc` semantics in
the OKX probe; Binance Vision ships UTC-aligned daily candles directly).

## Things this archive taught the tooling, in the order they were learned

- **The universe is enumerated, not walked.** The first design walked months backwards and stopped after three absent ones — which would
  have silently truncated every symbol delisted more than three months before the fetch. Replaced by listing each symbol's own keys; the
  offline tests caught it before a single real request was spent.
- **Five listed symbols have Chinese names** (哈基米USDT, 币安人生USDT, 我踏马来了USDT, 牛来USDT, 龙虾USDT). A URL built from them cannot
  be sent as ASCII; symbols are percent-encoded where requests are built, archived under their raw names. One of them lists a directory
  with no monthly files at all — recorded as "no monthly kline keys served", not treated as a refusal.
- **Funding cadence is a measured fact**: a 30-symbol sample of the newest funding month found 2,451 rows at 4h, 1,402 at 8h, and 6 at 1h.
  The validator accepts the declared family {1h, 2h, 4h, 8h} and refuses anything else.
- **The endpoint throttles twice**: first by dropping new TCP handshakes (a connection parked in SYN_SENT for minutes while established
  ones served — fixed by keep-alive, one persistent connection per worker thread), then by sustained-volume slow lanes (measured 5 KB/s
  against a 145 KB/s smoke minutes earlier). The fetch is therefore **resumable**: per-symbol part files plus an atomic ledger, so a stall
  costs the symbol in flight and never the hours before it. The bootstrap that produced this archive resumed once, from 244 symbols, after
  a process death, and lost nothing.
- **Monthly zips are complete months only.** The running month arrives as daily zips; its in-progress day is never an observation.

## What consumes it

`tools/ba007.py` (the BA-007 engine) reads `data/perps/current/{perps_daily.csv,funding_events.csv}`. The first sweep's verdict and its
reading live in [`docs/notes/2026-09-09-ba007-first-cross-sectional-sweep.md`](../notes/2026-09-09-ba007-first-cross-sectional-sweep.md).

## Reproducing

```sh
.venv/bin/python tools/fetch_perps.py     # new immutable snapshot; resumes any .partial workspace; moves data/perps/current
.venv/bin/python tools/ba007.py           # the pre-registered sweep: both signals, both seen periods, controls, verdict, artifacts
```
