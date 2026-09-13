# Expiring crypto cash-and-carry: bounded entry screen

**Decision: reject the sampled BTC and ETH entries.** Under the fixed capital
and reserve policy, both fall short of the 4% cash comparison even with zero
fees and a spot exit exactly matching the settlement index. Larger balances
do not resolve the shortfall. This closes the proposed economics screen; it
does not establish that every future carry opportunity will be unattractive.

## Actual quote packet and route

Coinbase retail Advanced spot plus Coinbase Financial Markets dated nano
futures, collected September 10, 2026 at approximately **22:03:34 UTC**
(17:03:34 Chicago). No authentication, purchases or orders were used.

- BTC: `BTC-USD` plus `BIT-25SEP26-CDE`, 0.01 BTC per contract.
- ETH: `ETH-USD` plus `ET-25SEP26-CDE`, 0.1 ETH per contract.
- Both expire **September 25, 2026 at 15:00 UTC**, about 14.706 days after the
  quote. The nearest publicly tradable dated expiry was selected before book
  collection. October and November contracts were view-only; hourly-funded
  perpetual-style contracts were excluded.
- Every book was less than one second old at receipt. BTC's two book timestamps
  differed by 0.438 seconds; ETH's by 0.191 seconds. This passed the fixed
  15-second freshness and 2-second pair-skew limits on the first attempt.
- Public product flags supported trading, but personal futures approval,
  position limits and actual fees were not verified. Displayed depth is not a
  fill guarantee; these prices are an archived observation, not a current offer.

The public API supplies product metadata and bid/ask depth without an API key.
[Product book documentation](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-book).
Coinbase documents cash margin, whole futures contracts and restricted access
to later monthly expiries. [Retail mechanics](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-intro).

## Capital, prices and costs

Each asset is a **separate alternative**, not a second simultaneous allocation
of the same account. Size uses the largest whole-contract position with each
executed leg at most half the stated capital, and at least 20% of capital free
after spot purchase, initial margin and stressed entry fees. The remaining cash
is dedicated to the hedge and stays in the return denominator. Interest is zero.

Buy spot at ask-depth VWAP; sell futures at bid-depth VWAP. Initial margin uses
the futures ask-depth buyback mark and the observed overnight short rates:
**28.9% BTC / 31.6375% ETH**. These API rates are public proxies, not binding
account requirements. Entry spreads are already in the leg prices and are not
charged again.

The same quantities are evaluated under each fee scenario:

| Fee case | Spot fee per side | Dated future fee budget per side |
| --- | ---: | --- |
| Low assumed | 0.60% | Greater of 2 bps of notional or $0.15 per contract |
| Base assumed | 1.20% | Greater of 5 bps of notional or $0.15 per contract |
| Stress assumed | 2.40% | Greater of 10 bps of notional or $0.50 per contract |

These are sensitivities, **not verified personal tiers or guaranteed fee
bounds**. Current Advanced help requires sign-in for the full schedule.
[Advanced fees](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees).
The published exchange component is $0.10 per BIT/ET contract per side, but is
not the full customer charge. It is not added again to the assumed all-in fee.
[Exchange schedule](https://assets.ctfassets.net/k3n74unfin40/sgInuF26edJX4v4nUlE29/87f18103cd35feede93f0bb92a5f1065/Fee_Schedule_1.26.2026.pdf).

Fee budgets use unchanged entry prices for the eventual spot disposal and
futures close/settlement. That convention is not a forecast of the expiry price.
The futures terminal charge is budgeted once; a closing commission and expiry
charge are not both added. Actual expiration charges remain unverified.

## Decision table

All figures are USD except quantities and prices. Net columns assume perfect
spot/index matching and exclude tax and operating overhead. Cash comparisons
use simple `capital × annual rate × actual holding days / 365`.

| Capital | Asset / contracts | Spot quantity | Spot ask VWAP | Futures bid VWAP | Initial margin | Free cash after margin and stress entry fees | Fee-free capture | Base fee net | 4% / 6% cash gain |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| $5,000 | BTC / 3 | 0.03 BTC | $77,103.22 | $77,305.00 | $670.36 | $1,958.71 | **$6.05** | **−$51.78** | $8.06 / $12.09 |
| $5,000 | ETH / 10 | 1 ETH | $2,458.02 | $2,462.00 | $779.23 | $1,698.76 | **$3.98** | **−$58.01** | $8.06 / $12.09 |
| $25,000 | BTC / 16 | 0.16 BTC | $77,103.30 | $77,305.00 | $3,575.28 | $8,779.75 | $32.27 | −$276.17 | $40.29 / $60.43 |
| $25,000 | ETH / 50 | 5 ETH | $2,458.05 | $2,462.00 | $3,896.16 | $8,493.65 | $19.77 | −$290.19 | $40.29 / $60.43 |
| $100,000 | BTC / 64 | 0.64 BTC | $77,104.81 | $77,305.00 | $14,301.11 | $35,118.01 | $128.12 | −$1,105.68 | $161.16 / $241.74 |
| $100,000 | ETH / 203 | 20.3 ETH | $2,458.13 | $2,461.69 | $15,820.71 | $32,980.06 | $72.23 | −$1,186.28 | $161.16 / $241.74 |

For the $5,000 alternatives, spot purchase costs are $2,313.10 BTC / $2,458.02
ETH. Base total fee budgets are $57.83 / $61.99. Even the low assumed fee case
produces losses of **$22.63 / $28.52**. Stress fee losses are $109.61 / $124.00
before settlement mismatch. Every capital/asset combination is rejected.

The available total cost budget to beat 6% is already **negative** before
fees: −$6.03 BTC / −$8.11 ETH for the $5,000 accounts. Obtaining the personal
fee screen would not rescue these entries under the stated assumptions.

As an auxiliary capital-efficiency check, use one unit, no fees, no reserves,
fractional sizing and only spot funding plus observed initial margin. At best
displayed prices, the matched-settlement capture annualizes to **5.04% BTC /
3.05% ETH** on that smaller capital denominator. Both remain below 6% even
in this generous calculation. It is not an executable allocation, an annual
forecast or a reason to remove cash reserves.

## Settlement and cash risks

The dated products cash-settle to the MarketVector Coinbase Bitcoin/Ethereum
Benchmark Rates. September expiry at 16:00 London matches the API timestamp.
Daily settlement at 15:00 Chicago is a separate event. Selling spot may realize
a different price from the final index.
[August 2026 rulebook, Rules 1106–1107](https://assets.ctfassets.net/k3n74unfin40/23uJIkpQ2WjBwAvgpvKG6u/e47d63995663375e1275564a11dac608/Coinbase_Derivatives_Rulebook_Aug172026.docx.pdf).

The payoff decomposition is:

`quantity × (entry futures bid − entry spot ask)`
`+ quantity × (actual spot exit − final settlement index) − costs + actual interest`.

Adverse exit mismatches of 10 and 25 bps of initial spot notional are evaluated
separately for every fee case. For $5,000, 25 bps subtracts another **$5.78 BTC /
$6.15 ETH**, taking the base net to −$57.56 / −$64.16. These are allowances,
not worst-case bounds. A favorable mismatch could raise P&L, but no model here
predicts such an advantage.

Cash stress uses `F_stress = F_entry + (price rise + extra basis) × S_entry`.
Stress entry fees are paid once; unsold spot appreciation is unavailable for
cash calls. Margin is recalculated at the stressed futures price.

| $5,000 account: cash beyond required margin | BTC | ETH |
| --- | ---: | ---: |
| 50% price rise, current margin rate | $468.04 | $81.23 |
| 50% rise, doubled margin rate | **−$536.43** | **−$1,086.51** |
| Above plus 5% of initial spot price in extra futures basis | **−$718.94** | **−$1,287.18** |

The first row is positive but falls below the initial 20% free-cash reserve;
that reserve is an entry condition, not a promised continuing buffer. Later
rows show funding deficits. Larger balances also fail the doubled-margin
scenarios at these chosen position sizes. These shocks are policy assumptions,
not calibrated loss probabilities. Variation margin is a cash outflow even
when spot gains offset much of it economically; it is not automatically an
equal portfolio loss. The hedge does not guarantee a $1,000 drawdown limit.
[Coinbase cash mechanics](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-cash-balance).

## Evidence and closure

- [Frozen policy](../../research/ba009-dated-screen-2026-09-10/policy.json):
  SHA-256 `6344b9189e2196761b8827d3436a08f427b1357bd028071d07dac1110aea6ce7`.
  Written after product discovery and before book collection.
- [Product selection](../../research/ba009-dated-screen-2026-09-10/selection.json),
  [source manifest](../../research/ba009-dated-screen-2026-09-10/manifest.json),
  [full arithmetic](../../research/ba009-dated-screen-2026-09-10/result.json),
  [offline calculation](../../research/ba009-dated-screen-2026-09-10/analyze.py).
- Immutable raw responses remain locally under
  `data/us_crypto/dated-screen-2026-09-10/`, excluded from Git and pinned by
  hashes. Offline replay verifies each response and the frozen policy hash.
  Shared parsing/depth helpers are from commit `7354bb8`.
- Independent Decimal arithmetic from the raw books reconciled all six account
  alternatives, 18 fee cases, 54 mismatch outcomes and simple cash hurdles.
  The margin and liquidity calculations also reconciled. Source hashes match.
- One product-list request, two spot-product requests and four book requests;
  first packet passed validation. No quote retry or favorable-entry selection.
  New paid-data cost: **$0**. No account change, backtest or trade.

The result is **insufficient entry premium**, not a data-access blocker.
No implementation, paid history request or recurring monitor follows this
rejection. Broad trend/carry remains parked under the separate
[research reset](2026-09-10-research-reset.md).
