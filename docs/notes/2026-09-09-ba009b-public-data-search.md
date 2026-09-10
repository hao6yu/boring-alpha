# BA-009B: public historical-data source search

Checked September 9, 2026 America/Chicago (September 10 UTC).

**Result: exact vendor coverage was found, but no working free source of the
required expired-contract intraday prices was verified.** Coin Metrics is
the strongest lead because its public catalog identifies the exact four
contracts, their multipliers, and historical coverage. Download access is a
separate question: its Community price requests were denied.

This search follows the [conditional screen](2026-09-09-ba009b-conditional-screen.md).
The target is Coinbase Derivatives Exchange (CDE), with expired August nano
BTC/ETH dated futures and their U.S. perpetual-style counterparts. Coinbase
spot, International Exchange, generic BTC prices, and continuous futures
that silently roll contracts do not supply this experiment's missing inputs.

## Strongest lead: Coin Metrics

The [public exact-market catalog](https://community-api.coinmetrics.io/v4/catalog-all/markets?markets=coinbase_derivatives-BITQ26-future,coinbase_derivatives-ETQ26-future,coinbase_derivatives-BIPZ30-future,coinbase_derivatives-ETPZ30-future)
lists:

| Coin Metrics market | Coinbase Advanced product | Underlying per contract |
|---|---|---:|
| `coinbase_derivatives-BITQ26-future` | `BIT-28AUG26-CDE` | 0.01 BTC |
| `coinbase_derivatives-ETQ26-future` | `ET-28AUG26-CDE` | 0.1 ETH |
| `coinbase_derivatives-BIPZ30-future` | `BIP-20DEC30-CDE` | 0.01 BTC |
| `coinbase_derivatives-ETPZ30-future` | `ETP-20DEC30-CDE` | 0.1 ETH |

The [candle catalog](https://community-api.coinmetrics.io/v4/catalog-all-v2/market-candles?exchange=coinbase_derivatives&page_size=1000)
reports August BTC minute coverage beginning June 24, 2026 at 22:55 UTC,
and August ETH beginning June 29 at 14:15 UTC. Both extend to August 28;
the perpetual contracts' coverage begins July 18, 2025. Market metadata
also describes trade and book coverage. These are catalog declarations,
not a validation of downloaded price records.

The Community API rejected both hourly and daily August BTC price probes
with HTTP 403 and a market-entitlement error. Its Community-access candle
catalog exposed no CDE markets. [Coin Metrics access documentation](https://gitbook-docs.coinmetrics.io/getting-started)
distinguishes the free Community service from Pro access. A reproducible
[hourly probe](https://community-api.coinmetrics.io/v4/timeseries/market-candles?markets=coinbase_derivatives-BITQ26-future&frequency=1h&start_time=2026-08-01&end_time=2026-08-02&page_size=10)
therefore establishes an access barrier, not a missing or zero-trade day.

One quality issue must be reconciled if data is later obtained: Coin Metrics
metadata lists August expiry at 16:00 UTC, while Coinbase's own metadata
lists 15:00 UTC. Coin Metrics' trade coverage ends around 14:59 UTC and
book coverage around 15:00, but its candle catalog extends to 23:59. Do not
interpret the latter as continued trading without inspecting volume,
timestamp conventions, and any carried-forward prices.

## Other sources checked

The subsequent [CoinDesk API access check](2026-09-09-ba009b-coindesk-access.md)
records exact catalog probes and the current signed-in pricing/key-settings
behavior. It did not obtain a usable key or the expired-contract sample.

| Source | Finding | Use for this retest |
|---|---|---|
| [CoinDesk Data derivatives](https://data.coindesk.com/derivatives) | Explicit CDE coverage and tick/minute/hour historical products; anonymous market request requires a key. Exact August instrument coverage not verified. | Possible vendor alternative, not an established free download. |
| [CoinDesk free-tier retirement notice](https://data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access) | April 17, 2026 notice retires the free API tier effective May 21, 2026. Older pages still mention free access. | A free account/key cannot be assumed sufficient; trial eligibility remains unverified. |
| [Tardis exchange catalog](https://api.tardis.dev/v1/exchanges) | Directly retrieved list includes Coinbase spot and Coinbase International, with no CDE entry. | Wrong venue for these exact contracts. |
| [CryptoDataDownload Coinbase page](https://www.cryptodatadownload.com/data/coinbase/) | Describes Coinbase Exchange spot data; currently says its Coinbase data is unavailable. | Does not establish expired CDE data. |
| [TradingView indexed August BTC page](https://in.tradingview.com/symbols/COINBASE-BIT1%21/?contract=BITQ2026) | Opening the indexed August URL redirected to the September contract. | Search labels and current charts do not verify an August archive. |
| [Sierra Chart current Denali documentation](https://www.sierrachart.com/index.php?page=doc/DenaliExchangeDataFeed.php) | No current Coinbase/FairX entry established; an older support thread describes FairX support in 2021–22. | Historical support does not verify a current public source. |
| [Amberdata expansion](https://docs.amberdata.io/changelog/coinbase-international-spot-futures-now-available) | The documented Coinbase futures venue is International. | Wrong venue. |
| [Public CBB26 order-book dataset](https://huggingface.co/datasets/deusmos/cbb26-timeseries-db) | Its explicit product list is a spot basket, including BTC-USD and ETH-USD. | Useful for other research, not this dated/perpetual pair. |

Broader searches of vendor documentation and public datasets, including
Databento, Barchart, CoinAPI, Kaiko, GitHub, and academic listings, did not
establish another exact, anonymously downloadable CDE dataset. This is a
bounded search result, not proof that no such source exists anywhere.

## Coinbase's own routes

A subsequent [authenticated probe](2026-09-09-ba009b-authenticated-history.md)
verified view-only retail API access and a successful futures control, but
both expired August candle requests still returned invalid-product errors.

The [public historical-data page](https://www.coinbase.com/derivatives/historical-data)
is linked from Coinbase's exchange site. Its reports could not be inspected
reliably in this session: web extraction was empty, a direct request returned
403, and the browser stalled before report controls rendered. Its report
contents and granularity remain unverified. A link titled Historical Data
is not evidence of an obtainable intraday dataset.

The [public block-trade page](https://www.coinbase.com/derivatives/block-trade-data)
contains individual reported block trades. These are privately negotiated
transactions rather than a continuous central-order-book history; the sampled
page does not reconstruct our hourly nano futures pair.

The documented [Advanced Trade public market-trades route](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-market-trades)
accepts start/end times. A new probe for each exact expired August ID returned
HTTP 400, invalid product IDs. Archived product metadata exposed no aliases,
so there was no supported alternate symbol to substitute.

The [CDE REST specification](https://docs.cdp.coinbase.com/derivatives/downloads/cde-public-api-spec.json)
contains expired-instrument metadata and historical funding, but no ordinary
candle route. The [historical funding endpoint](https://docs.cdp.coinbase.com/api-reference/derivatives-api/rest-api/funding-rate/get-historical-funding-rates)
does include `future_mark_price`, `spot_mark_price`, and `event_time`—a useful
lead for the previously missing funding-event marks. However, anonymous
funding and expired-instrument probes both returned HTTP 401 requiring
`CB-ACCESS-KEY`. The operation-level empty security settings in the OpenAPI
file do not match those observed responses. [Authentication documentation](https://docs.cdp.coinbase.com/api-reference/derivatives-api/rest-api/authentication)
requires separate Derivatives Command Center credentials; ordinary Coinbase
retail API access must not be assumed equivalent.

Raw responses and provenance are retained in
[Advanced API alternatives](../../data/us_crypto/api-alternatives/20260910T010219921074Z/manifest.json)
and [CDE access probes](../../data/us_crypto/cde-public-market-probes/20260910T010335953496Z/manifest.json).
The [vendor probe archive](../../data/us_crypto/vendor-source-probes/20260910T010553182691Z/manifest.json)
preserves Coin Metrics' exact-market and candle catalogs, the denied hourly
price response, and Tardis' exchange list, with URLs, timestamps, and hashes.

## Disposition

The public search has identified a specific vendor lead instead of an
unspecified missing-data problem. BA-009B remains parked pending usable data
access. Reopening it would require a usable sample of the
exact contracts with timestamps, volume, and preferably historical quotes,
plus access to funding-event marks. A catalog listing alone does not justify
buying a dataset or treating the strategy as validated.

No credentials, subscriptions, trials, account changes, or vendor outreach
were initiated. This round was a source-availability investigation and did
not recalculate or promote the strategy.
