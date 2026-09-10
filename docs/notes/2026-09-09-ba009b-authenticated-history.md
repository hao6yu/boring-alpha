# BA-009B: authenticated Coinbase history probe

Checked September 9, 2026 America/Chicago, September 10 at 01:22 UTC.

**Authentication succeeded; expired August candle access still failed.** A
user-provided Coinbase CDP key had `can_view=true`, `can_trade=false`, and
`can_transfer=false`. Four GET requests were made: key permissions, one
existing perpetual futures control, and the two expired dated contracts.
No order, balance, transfer, account-change, or subscription request was made.

Every candle request used the same interval: August 24, 2026 00:00 UTC through
August 25 00:00 UTC, exclusive, with hourly granularity and a 300-bar limit.

| Product | HTTP | Result |
|---|---:|---|
| `BIP-20DEC30-CDE` | 200 | 24 validated hourly candles |
| `BIT-28AUG26-CDE` | 400 | `INVALID_ARGUMENT`, invalid product ID |
| `ET-28AUG26-CDE` | 400 | `INVALID_ARGUMENT`, invalid product ID |

The expired failures reproduce the earlier anonymous result despite successful
authentication and a working futures control. They establish that this
authenticated Advanced Trade route, with this account and these exact IDs,
does not supply the requested history. They do not prove Coinbase has no
archive elsewhere. Failed candle counts remain unknown, not zero.

## Authentication documentation conflict

The [Coinbase App authentication page](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication)
contains an ECDSA-only instruction. However, the
[official compatibility matrix](https://docs.cdp.coinbase.com/get-started/authentication/overview)
explicitly supports Ed25519 for direct Advanced Trade API calls, and the
[current official Python signer](https://github.com/coinbase/coinbase-advanced-py/blob/master/coinbase/jwt_generator.py)
supports base64 Ed25519 keys. This probe used Ed25519 successfully. An earlier
claim in the conversation that this key format required replacement was
corrected before the live test.

The [key-permissions endpoint](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/data-api/get-api-key-permissions)
verified view-only access before the
[authenticated candles endpoint](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/get-product-candles)
was queried. Credentials and JWTs were held only in process memory, entered
through hidden terminal prompts, and omitted from project files and output.
The supplied secret was already present in the conversation; the user should
revoke it after this test and provision future secrets locally.

## Reproduction and disposition

The bounded probe is `tools/coinbase_history_auth_probe.py`; its network
allowlist permits only these four GET URLs and blocks HTTP redirects.
Optional dependencies are declared under `coinbase-research`:

```sh
.venv/bin/python -m pip install -e '.[coinbase-research]'
.venv/bin/python tools/coinbase_history_auth_probe.py
```

The sanitized [local result](../../../data/us_crypto/authenticated-history-probes/20260910T012227555299Z/report.json)
contains request URLs, timestamps, status codes, response hashes, permission
booleans, and normalized control candles. Raw bodies are not retained, so
the hashes are provenance records rather than independently replayable raw
responses. No account identifiers or arbitrary server messages are retained.

Validation: 47 focused offline tests passed across the authenticated probe
and existing hourly importer. They cover synthetic signatures, request
binding, redirect refusal, report sanitization, and candle integrity.

BA-009B remains parked pending usable data. Coin Metrics still has verified
catalog coverage, but its download portal requires a separately entitled API
key and its key-request link leads to a sales form. No vendor form was
submitted, account created, or data purchased. The next historical-data step
is an entitled sample of the exact contracts, or another verified archive;
a successful Coinbase login alone does not resolve the missing input.
