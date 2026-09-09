# Coinbase US spot: what this repository archives, and what it refuses to assume

Two inputs come from Coinbase, and they are treated completely differently. **Prices are fetched, hashed, and archived** under the same
immutability rules as the equity corpus. **Fees cannot be fetched at all**, and so they arrive as an operator-supplied, dated, hashed record
or the tools that trade do not run.

## The daily candle archive

`tools/fetch_crypto.py` → `data/crypto/current/` (a symlink onto an immutable `snapshots/<STAMP>/` directory):

| field | value |
| --- | --- |
| endpoint | `https://api.exchange.coinbase.com/products/{pair}/candles?granularity=86400` |
| granularity | 86400 s (daily), one row per calendar day the venue served |
| pairs | `BTC-USD`, `ETH-USD` |
| fetched at | `2026-09-08T14:58:06Z`, 271 requests, 7,831 rows |
| sha256 of the CSV | `1c6fb3d001d3e2e3176315e8efbcdd9f0c96d6b9186136bc0e9268fc020f6f89` |
| synthetic | `false` — every row is a venue observation, none is interpolated |
| first candle served | BTC-USD **2015-07-20** (4,068 sessions), ETH-USD **2016-05-18** (3,763) |
| holes | ETH-USD **2016-05-21, 2016-05-22** — reported, not stitched |

Things this endpoint taught the tooling, in the order they were learned:

- **The window cap is about 300 daily candles.** A 590-day probe comes back `400 Bad Request`, so every request — including probes — is
  chunked at 29 days.
- **The record's floor is what the endpoint serves, not what a probe reaches.** The start date is found by a doubling-lookback probe bisected
  to the day, and the archived floor is then *the first candle actually served* (BTC-USD probed 2015-07-19, first candle 2015-07-20). Using
  the probe date would manufacture a hole that does not exist.
- **The in-progress day is dropped.** A candle for the current UTC day is not a completed observation and is never archived.
- **An empty window is refused, not believed.** If the endpoint serves nothing before today, the fetch refuses to archive an empty record
  rather than concluding the market began today.
- A snapshot is never overwritten (`immutable`), the manifest seals the CSV's sha256, and validation refuses the whole fetch on a single
  non-numeric or impossible candle, naming the day.

## The fee schedule, which no script can read

The posted US spot fee schedule is unreachable to any non-browser client. Recorded attempts, all on 2026-09-08, kept in the probe log that
`tools/venue_fees.py` prints whenever it refuses:

| attempt | outcome |
| --- | --- |
| `help.coinbase.com/en/exchange/trading-and-fees/exchange-fees` | `403 Forbidden`; unchanged with a browser user-agent and `Accept-Language` |
| `coinbase.com/advanced-fees`, `/fees`, `/legal/trading-rules/exchange` | `403 Forbidden` |
| the harness's own fetcher on the same URLs | `403`, body `Just a moment…` (a JS challenge) |
| Wayback snapshot `20260506154253` of `/advanced-fees` | 200 OK, 12,367 bytes, sha256 `139b5b1a2fb53de2…`, **0** occurrences of `taker`, `maker`, or any `d.dd%` — the archive captured the client-side shell, not the rendered table |
| `api.exchange.coinbase.com/fees` | not attempted: requires account credentials, which this lab holds none of and asks for none |

Consequences, all enforced in code:

- `tools/venue_fees.py` holds **no fee number of its own** — no constant, no fallback — and a test greps the source to keep it that way.
- The fee arrives by `ingest`, is dated, is refused past **90 days**, and a superseded record is archived rather than deleted.
- What *is* measurable without a key is the **order book** (`/products/{pair}/book?level=2`, rows are `[price, size, number_of_orders]`) and
  the retail quote line. Measured 2026-09-08: BTC-USD touch **0.094 bps**, ETH-USD **0.040 bps**. The retail quote line is printed as a noise
  floor, not a cost: it read **+6.1 bps** over the book mid and then **−1.6 bps** minutes later.
- Every tool that prices a Coinbase trade (`tools/ba005.py`, `tools/ba006.py`) reads the fee from this one record, and the semantics are
  asymmetric on purpose: **a FAIL is publishable without the record** (a gate that fails at a fee of zero fails at every fee), **a PASS is
  not** — a pass is a trade licence, and this repository does not issue one against a cost it cannot see.

## The stablecoin / fiat conversion line, which turned out not to be a market

The objective asks for the conversion line beside the fee. It was probed on 2026-09-08 with the same keyless endpoints, and the answers are
negative — which is a result, not a failure to measure:

| probe | answer |
| --- | --- |
| `GET /products/USDC-USD/book?level=2` | `404 Not Found` — there is no such product |
| `GET /products` (837 listings, keyless) | `USDC-USD` is **not listed**; `BTC-USDC` and `ETH-USDC` are listed but `status: delisted`, `trading_disabled: true`; the only online USDC-quoted books are `AUDD-USDC, EURC-USDC, TGBP-USDC, USDT-USDC, XSGD-USDC` |
| `GET /v2/prices/USDC-USD/buy` | `{"data":{"amount":"1"}}` — exact parity, because both legs are dollars |

Three consequences, in the order they bite:

1. **There is no spread to measure, and therefore no conversion cost to archive.** The tool prints the line as *unpriced*, never as free, and
   a test asserts no conversion, peg, or USDC constant appears in its source.
2. **The USDC route to the trade is not executable.** `BTC-USDC` is delisted, so the only way to hold bitcoin on this venue is `BTC-USD`, and
   the cash leg of any plan on this venue is USD, not a stablecoin.
3. **The question that does decide the cash leg is a yield, not a fee.** BA-005 and BA-006 credit the below-the-line cash with a T-bill
   yield, and a T-bill is held at a broker rather than on the venue; what idle USD earns *there* is a product fact behind the same 403 wall
   that hides the fee schedule. Rather than assume it either way, `tools/ba006.py` prices the cash leg both ways on every weight:

| weight | bill, T-bill cash | bill, zero-yield cash | the yield was worth |
| --- | --- | --- | --- |
| 5% | $919/mo | $915/mo | $4/mo |
| 10% | $980/mo | $971/mo | $8/mo |
| 20% | $1,045/mo | $1,028/mo | $16/mo |

   so the unsourced assumption is **not load-bearing**: at most 2.0% of P0's bill turns on which cash the account holds, and the 20% row
   survives a cash leg that earns nothing. (This block caught a real bug while being written: it first reused a variable the fee grid had
   rebound and printed the 240 bps bills under a "T-bill" heading — plausible, wrong, and now pinned by
   `test_the_cash_column_in_the_variants_block_is_the_same_number_as_the_main_table`.)

## The measured probes are archived, hashed, one line per run

`tools/venue_fees.py snapshot` re-runs every reachable probe (both coin books, the retail quote, the conversion quote, the product list) and
appends one JSON line to [`data/venues/measures.jsonl`](../../data/venues/measures.jsonl): the UTC time, and for each URL the byte count and
the sha256 of the payload as fetched. Nothing else about a measured probe can be archived — the payloads are a megabyte of order book that is
stale within the hour — and this is the same discipline the fee schedule would have been held to, applied to the half of the cost stack that
is actually reachable. The file is append-only and never edited; the archive is what lets a later round see the venue's answers move instead of
trusting one day's prose.

It changes no verdict. A measurement is not a licence: `taker` still refuses while the fee record is absent, and a test exists specifically to
keep it that way (`test_an_archived_measurement_still_does_not_license_a_price`). The archive began 2026-09-08 with one entry; six lines written
by a non-hermetic first version of its own test were discarded rather than kept, because an evidence file whose provenance is a test artifact
is not evidence.

## Reproducing

```sh
.venv/bin/python tools/fetch_crypto.py                    # new immutable snapshot, moves data/crypto/current
.venv/bin/python tools/venue_fees.py report               # measured spread, the conversion probes, and the fee refusal
.venv/bin/python tools/venue_fees.py ingest --product advanced-trade --taker-bps N --maker-bps N \
    --tier "…" --as-of YYYY-MM-DD --note "…"              # the fee, from the operator's own fee screen
.venv/bin/python tools/ba005.py                             # the locked rule's verdict, or the refusal it deserves
.venv/bin/python tools/ba006.py                             # the sized sleeve, its roll ladder, and both cash legs
```

The suite's Coinbase tests are offline: `tests/test_fetch_crypto.py` drives a fake exchange that enforces the chunk cap, the served floor and
the missing days; `tests/test_venue_fees.py` answers the book, quote and product-list URLs from a fixture and asserts that the conversion line
is reported as unpriced rather than free.
