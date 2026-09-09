# An endpoint dates itself by what it serves

Round 109. The direction changed today: after 108 rounds whose honest answer was "the index is very hard to beat", the one fair excuse left
was **coverage** — every signal ever priced here was priced on four equity ETFs and some bills. So the question became what data can be
reached without paying for it, and the answer is "more than the last year's rounds assumed".

## What is reachable, through the fetcher's own TLS path

| source | what came back | usable for |
| --- | --- | --- |
| Coinbase Exchange candles | daily, BTC-USD from 2015-07-20, ETH-USD from 2016-05-18 | **a real backtest** — 4,068 and 3,763 candles |
| Kraken OHLC | daily, 720 days back | a cross-check venue later |
| Yahoo chart, same endpoint as the equity fetcher | `GC=F` futures, `^VIX`, and hourly SPY (143 bars/month) | futures dailies; vol regime; **cost realism**, not alpha |
| CBOE delayed quotes | current chain only, no history | a forward collector, never a backtest |

Only crypto has enough history to be *tested* rather than collected, so that is where the first new question goes, and the rest waits for a
question worth its storage. `tools/fetch_crypto.py` is the new channel: immutable snapshots under `data/crypto/snapshots/<STAMP>/`, a manifest
naming endpoint, window, request count and sha256, a poisoned candle refusing the whole fetch, the day still in progress never archived. First
live fetch: **7,831 candles, 271 requests, sha256 `1c6fb3d001d3…`**, re-fetched byte-identical.

## The hole that wasn't, and the holes that were

The first version carried a listing date from company folklore: `BTC-USD: 2011-08-17`, when Coinbase began quoting bitcoin. The tool reported
the mismatch faithfully — **1,433 missing sessions** — and the faithful report was still wrong about its own meaning, because an endpoint that
never served a day is not a hole in a record. So the floor is now *probed*: knock back by doubling years until a window comes back empty, then
bisect to the day; the record's floor is taken from the **first candle served**, so a probe landing a day early cannot manufacture a hole. The
next fetch found two genuine ETH holes (2016-05-21, 2016-05-22) and reported them rather than stitching them shut.

Two facts about the source, both now in the fetcher's docstring and pinned by tests: it answers **400 Bad Request** for a page wider than ~300
daily candles (which is what killed my first probe walk, whose steps grew past that), and its candles begin 2015-07-20, four years later than
the company's own story. `tests/test_fetch_crypto.py` asserts no probe window exceeds 30 days, that an endpoint serving nothing is a refusal
rather than an empty archive, and that the manifest's hole counts equal the counts a reader recomputes from the CSV — crypto having no weekend
to hide behind.

## The new class starts locked, not warm

`docs/strategies/BA-005.md` is written **before any crypto return was computed** — which is the only reason a shiny new asset class deserves
the same scepticism as an old one:

* **one instrument** (BTC-USD, the only complete record; ETH is archived but out of the test), **one rule** (hold above the 200-day mean,
  bills below, monthly), **no sweep** — round 57 measured what a parameter grid buys;
* **one window**, 2016-05-18 to 2026-09-04, chosen from the data's shape and not re-cuttable afterwards without a new revision;
* **costs decided the argument**: an assumed **60 bps taker + 5 bps** spread, written as assumptions that must be re-sourced against the
  venue's posted schedule on the day of the run, **with the run refusing if it cannot look them up**;
* **fail decided by the ruin promise, not the terminal**: pass needs terminal > plain QQQ on the same window, ruin probability no worse at
  QQQ's own affordable bill, and max drawdown within 1.25× QQQ's. The depths the spec leans on — **83.8%** (2017-12-16 → 2018-12-15),
  **76.7%** (2021-11 → 2022-12), **53.1%** inside the test window — are recomputed from the candles by `tests/test_fetch_crypto.py`, not
  remembered from a chart, because rule 100 says a figure in prose is a figure nobody re-prices.
* **P0 unchanged**: 100% VOO, priced before evidence. A pass licenses one thing: a fifth forward book. Not a skill claim — that still needs
  24 monthly entries.

## Checks

**2371 passed, 239 subtests** (2357 + 14 new; collected count printed before the run). Rules: **109**. Crypto archive current; equity
archive unchanged at `20260908T123726Z`; five books still sealed once at the anchor, first real seal 2026-09-30, 23 entries to a skill claim.

*Round 109. The excuse of coverage is closed for crypto and opened for three classes we cannot yet price. Nothing here has earned a claim;
BA-005 is a locked question, and next round it gets an answer — probably "no", and that answer is worth having.*
