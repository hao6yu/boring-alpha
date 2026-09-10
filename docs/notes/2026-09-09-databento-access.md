# Databento: working expired-futures history and quoted research costs

Checked September 9, 2026 America/Chicago; API requests completed September 10
at 03:00 UTC. This is a data-access result, not a strategy or profitability test.

## Verified access

The user supplied a Databento key for the proposed futures research. The signed-in
billing page showed **$125 remaining credits and a $0 balance** before the probe.
No subscription, license, payment method, or account setting was changed.

Authenticated metadata requests and a historical data download returned HTTP 200.
The downloaded instrument was **MESZ5**, the December 2025 Micro E-mini S&P 500
future, now expired. We requested November 3, 2025, 14:30–21:00 UTC, representing
09:30–16:00 New York time that day.

- 390 one-minute OHLCV bars returned; all 390 expected minute timestamps present.
- One instrument ID, strictly increasing timestamps, positive volume, valid OHLC
  ordering, and prices on the 0.25 index-point tick grid.
- The raw JSON uses nanosecond timestamps and fixed-point prices scaled by 1e-9.
- Raw response: 79,037 bytes; SHA-256
  `ba92bc6f658ccfd5f5cf7961ca156c2b73b4e6381a83d06abc4c448a1aea7277`.

Local immutable artifacts, excluded from Git:

- `data/futures/databento-probes/20260910T030019553635Z/report.json`
- `data/futures/databento-probes/20260910T030019553635Z/mesz5-20251103-ohlcv-1m.jsonl`

## Live API quotes

| Request | Estimated USD | Downloaded? |
| --- | ---: | --- |
| MESZ5 sample, 390 one-minute bars | 0.001423805952 | Yes |
| MES.v.0, one-minute bars, 2025-01-01 through 2026-01-01 exclusive | 1.287164390087 | No; quote only |
| MES.v.0, one-minute bars, 2021-01-01 through 2026-01-01 exclusive | 6.454313173890 | No; quote only |

These are provider quotes, not invoice reconciliation. Credits were verified
separately in the portal; their exact post-download deduction was not measured.
The sample was requoted immediately before downloading, under a $1 estimate
ceiling and a fixed 390-record request limit. This ceiling is a local quote check,
not a provider-enforced billing limit. No larger data order was submitted.

The feed-level range returned for GLBX.MDP3 began June 6, 2010. This is **not** a
claim that MES itself traded in 2010. Likewise, continuous-contract cost quotes
do not establish per-contract history completeness or a valid roll ledger.

## Research direction

The user requested an IBKR Lite-to-Pro switch and reports that review is pending.
That does not block independent historical research. CME data does not repair
the missing Coinbase contracts in BA-009B; that experiment remains parked.

MES is the first candidate instrument for a new intraday experiment, pending a
separately written strategy specification. Current public IBKR requirements put
the larger MES overnight initial margin near $3,240 per contract, leaving roughly
$1,760 of a $5,000 account. These are indicative, changeable requirements; an
account-specific check is still necessary before a pilot. Micro Gold's roughly
$4,600 initial margin leaves too little cushion for this initial account size.

MES has a $5-per-index-point multiplier and a $1.25 tick. Published entry-tier
IBKR broker/exchange/regulatory charges total about $1.22 per round trip; one
tick of modeled slippage on each side increases that to $3.72. These assumptions
exclude market-data costs and applicable overnight charges, and do not guarantee
fills. A $50–$100 gross price-risk budget corresponds to a 10–20 point adverse
move on one contract; fees and actual slippage add to the loss. A stop must be
justified by the strategy, not tightened merely to make the account fit.

Next: specify one intraday hypothesis, its timing, abstention/risk rules, costs,
and chronological development/holdout periods before evaluating it. Then acquire
the quoted history with instrument mappings, audit sessions and rolls, and test
returns after costs. Price candles alone do not establish executable fills.

## Reproduction and credential handling

`tools/databento_history_probe.py` has a fixed historical endpoint/request allowlist,
blocks redirects, omits arbitrary provider error text, validates the sample, and
archives sanitized metadata and market observations. No credential is stored in
project files, environment files, command arguments, or the data report. The key
was passed through hidden terminal input and used only in process memory.

Validation: 100 focused offline cases passed. They cover malformed/overflowing
quotes, exact decimal budget comparison, metadata errors, request restrictions,
redirect refusal, secret/error containment, fixed-point prices, timestamps,
OHLC invariants, and missing/duplicate bars. The archived live sample's hash and
all 390 normalized rows were also rechecked without another API request.

```sh
# Metadata and quotes only; enter a key at the hidden prompt.
.venv/bin/python tools/databento_history_probe.py

# Also fetch the fixed sample, after a fresh quote <= $1.
.venv/bin/python tools/databento_history_probe.py --download-sample
```

The key already appears in the conversation. Future durable setup should use a
replacement credential provisioned locally rather than copying it into chat.

## Primary sources

- [Databento quickstart](https://databento.com/docs/quickstart)
- [Historical API and authentication](https://databento.com/docs/api-reference-historical/basics/authentication)
- [Cost quotes](https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost)
- [Pricing and credits](https://databento.com/docs/faqs/usage-pricing-and-data-credits)
- [MES catalog](https://databento.com/catalog/cme/GLBX.MDP3/futures/MES)
- [CME Micro E-mini specifications](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html)
- [IBKR U.S. futures margin](https://www.interactivebrokers.com/en/trading/margin-futures-fops.php?ex=us&hm=us&ot=0&pm=0&rgt=0&rsk=1&rst=1)
- [IBKR base commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php)
- [IBKR CME exchange/regulatory charges](https://www.interactivebrokers.com/en/accounts/fees/CME.php)
