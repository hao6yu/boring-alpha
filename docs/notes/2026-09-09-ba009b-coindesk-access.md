# BA-009B: CoinDesk API access check

Checked September 9, 2026 America/Chicago (September 10 UTC).

**CoinDesk has a technically suitable API family, but usable account access
and the exact expired contract coverage remain unverified.** The user's
[linked introduction](https://developers.coindesk.com/documentation/data-api/introduction)
was inspected in the browser. The API base is `https://data-api.coindesk.com`;
it supports header-based API key authentication.

## Documented path to the needed data

The [derivatives product page](https://data.coindesk.com/derivatives) explicitly
lists Coinbase Derivatives and advertises historical calendar and perpetual
futures data. Relevant [Futures endpoints](https://developers.coindesk.com/documentation/data-api/futures):

- `/futures/v2/markets`: verify exchange identity; `coinbase` and
  `coinbaseinternational` are distinct documented market values.
- `/futures/v1/markets/instruments/unmapped`: discover native identifiers;
  request `EXPIRED` contracts explicitly instead of relying on the default
  `ACTIVE` filter.
- `/futures/v1/historical/hours`: fetch a small exact-contract sample before
  attempting a historical import.

The [hourly endpoint](https://developers.coindesk.com/documentation/data-api/futures_v1_historical_hours)
documents backward pagination with at most 2,000 points, inclusive `to_ts`,
and `fill=false` to omit periods without trading. A future importer must
verify the native instrument mapping, use unmodified prices where appropriate,
retain gaps, and distinguish carried-forward OHLC from actual trades.

Two new anonymous requests at 01:27:55 UTC were archived:

| Request | Result |
|---|---|
| Futures markets, `markets=coinbase`, groups ID/BASIC | HTTP 401, API key required |
| Unmapped futures instruments, `market=coinbase`, status EXPIRED | HTTP 401, API key required |

The [local manifest](../../../data/us_crypto/coindesk-access-probes/20260910T012755427674Z/manifest.json)
records exact URLs, timestamps, and raw-response hashes. Authentication was
not attempted; these errors do not establish missing contracts or denied
entitlements for an authenticated account.

## Account and plan observations

The browser was already signed in. Following the documentation's key-settings
link and directly navigating to
[API-key settings](https://developers.coindesk.com/settings/api-keys) both
ended at the [pricing page](https://developers.coindesk.com/pricing/).
No usable key or authenticated account entitlement was obtained. The cause
of the redirect was not independently diagnosed.

Current visible pricing lists:

- Personal: aggregate data, capped lifetime calls, 365 days daily history,
  7 days hourly history, 1 hour minute history; an Apply link leads to key
  settings, which again returned to pricing in this session.
- Start-Up: aggregate and exchange OHLC, 30 days hourly history, contact-based
  access.
- Enterprise: explicitly includes derivatives, with contact-based access.

The [April 17 retirement notice](https://data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access)
says the former free API tier ended May 21, 2026. The current Personal listing
does not establish that a free CDE futures entitlement exists. The derivatives
page separately advertises team-arranged trials. No numeric price, trial
duration, or applicable exact-contract entitlement was verified.

## Concrete next access request (draft only; not sent)

> I am a US-based individual researching a quantitative futures strategy for
> personal use. Could you provide a small trial sample or API entitlement for
> Coinbase Derivatives Exchange's expired August 2026 nano BTC and ETH futures
> (Coinbase Advanced IDs BIT-28AUG26-CDE and ET-28AUG26-CDE), together with their
> perpetual-style counterparts BIP-20DEC30-CDE and ETP-20DEC30-CDE? Please confirm
> your native instrument identifiers, available hourly history through August
> 28, 2026, and permission for local research/export. Initially we only need
> August 24 UTC hourly prices, volume, and contract metadata to verify coverage.
> Please state any trial charges before enabling paid access.

No application or vendor message was submitted, credential created, or plan
purchased. BA-009B's historical retest remains parked. Catalog confirmation
and a validated sample must precede a full importer or renewed strategy claim.
