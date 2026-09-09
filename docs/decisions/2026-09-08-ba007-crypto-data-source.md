# BA-007 data source: where the cross-section comes from, and what each refused venue taught

- **Date:** 2026-09-08
- **Decision:** the BA-007 crypto cross-section is priced on **Binance USDT-M perpetual futures** data served by the public archive
  `data.binance.vision` (S3 bucket `data.binance.vision`, region `ap-northeast-1`): daily klines and funding-rate history, one zip per
  symbol per month, each verifiable, delisted symbols included.
- **Status:** decided after live probes on 2026-09-08, before any BA-007 signal was computed. This record does not authorize a run; the
  charter that consumes this spine is pre-registered separately.

## Why a venue had to be chosen by probing, not by preference

A cross-sectional book needs, keylessly and from this machine: many liquid instruments, daily prices with years of depth, funding-rate
history (the carry signal), and symbols that remain listed **after they die** — a universe built only from today's listings inherits
survivorship bias before the first rank is computed. Every candidate was asked for the same three things; the answers differ, and the
differences decided the question.

| venue | probe | answer |
| --- | --- | --- |
| Binance `fapi` (futures API) | `GET /fapi/v1/ping` | **HTTP 451** — "Service unavailable from a restricted location" (all three endpoints tested) |
| Bybit v5 | `GET /v5/market/time` | **HTTP 403** — CloudFront: "configured to block access from your country" |
| OKX v5 | `GET /public/time`, `/public/funding-rate-history` | **HTTP 200** — but daily candles default to **UTC+8 day boundaries** (`1Dutc` needed), and funding history reaches only **2026-06-08** (~3 months): too shallow to score a carry signal |
| Deribit | `GET /public/get_instruments?currency=USDT&kind=future` | 200 with **zero instruments** — no USDT perp cross-section to rank |
| Gate v4 | `GET /futures/usdt/funding_history` | 400 `MISSING_REQUIRED_HEADER: Timestamp` — signed-client gating on a public endpoint |
| Bitget v2 mix | `GET /history-fund-fund` | 404 on the documented path |
| KuCoin futures | `GET /contract/funding-rates` | 400 Bad Request |
| **Binance Vision (S3 archive)** | klines, fundingRate zips, CHECKSUM files | **HTTP 200 everywhere probed** |

## What the chosen archive demonstrated, by asking it

- **1,032 symbol directories** under `data/futures/um/daily/klines/` — including **delisted symbols**: `FTTUSDT` (died with FTX) still
  serves its full daily history, HTTP 200. A universe enumerated this way can be survivorship-bias-free; one enumerated from a live
  exchange's instrument list (OKX: 458 live USDT swaps) cannot.
- **952 symbol directories** under `data/futures/um/monthly/fundingRate/`, monthly zips through the **last complete month** (2026-08
  exists, 2026-09 does not; no daily funding zips exist — `…/daily/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-09-07.zip` → 404).
- Kline CSV columns: `open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore`,
  millisecond UTC stamps. Funding CSV columns: `calc_time,funding_interval_hours,last_funding_rate` (8h cadence on BTCUSDT).
- `.CHECKSUM` sidecars (sha256) exist per zip. This fetcher verifies transport integrity by the zip's own CRC (a corrupted archive fails
  to decompress) and pins each extracted CSV by the sha256 it records in its manifest — the same guarantee, paid for in half the requests.

## The rules this spine inherits

Same discipline as the equity and Coinbase fetchers, unchanged: immutable snapshots under `data/perps/snapshots/<STAMP>/`;
`data/perps/current` repointed only after a complete write; a manifest naming endpoints, request count, per-symbol floors and the sha256 of
every archived CSV; a poisoned row (non-numeric price, high below low, non-positive price, absurd funding rate) refuses the whole fetch and
names the symbol and day; the session still in progress is dropped; a hole *inside* a served record is reported and counted, never quietly
stitched; and the record's floor is the first month the archive actually serves, discovered by walking backwards — never a date from a
press release. Absent months before a symbol's first served month are expected, not holes.

## Known limitations, stated before anything is scored on this spine

1. **Funding lags to the last complete month.** A mid-month fetch cannot price the current month's funding from this archive. For a
   weekly-rebalanced backtest this is immaterial; a live book consuming this spine would owe either a lag or a separate live source, and
   that question belongs to the charter, not to the fetcher.
2. **`FTTUSDT`-style archives prove delisted symbols are kept; the reverse is not proven.** A symbol whose directory was removed from the
   listing entirely would be invisible to enumeration. The manifest records the listing counts it saw, so a later fetch that finds fewer
   directories is a finding, not a coincidence.
3. **All prices are USDT-margined quotes.** The cross-section is priced in USDT units; the USDT/USD peg is a real risk the charter must
   name, not something the fetcher can diversify away.
4. **Funding cadence varies and has moved**: measured 2026-09-08 across a 30-symbol sample of the newest funding month — 2,451 rows at
   4h, 1,402 at 8h, and 6 at **1h** (the newest listings). The validator accepts the declared cadence family {1h, 2h, 4h, 8h} and refuses
   anything else; events are archived raw with their interval, so any daily aggregation or annualization is a decision for the engine,
   made once, in the open.
5. **Symbol records are enumerated, not walked.** Each symbol's served months are listed from the archive's own keys before anything is
   fetched, so a delisted symbol keeps its whole history (a backwards month-walk with a termination rule would have silently truncated
   every symbol delisted more than a few months before the fetch — this was built, caught by the offline tests, and replaced). Day holes
   are judged only inside the observed span (first to last candle served); trailing silence after the last candle is the record's end,
   which is indistinguishable in this archive from a mid-month delisting, so the manifest's `last_candle` is what a later round judges.

## Reproducing

```sh
.venv/bin/python tools/fetch_perps.py          # new immutable snapshot under data/perps/snapshots/, moves data/perps/current
```

The suite's tests for this fetcher are offline: `tests/test_fetch_perps.py` drives a fake S3 archive that enforces the month-walk stop,
the served floor, the in-progress-day drop, poison-row refusal, hole reporting, and the manifest's sha256 pinning.
