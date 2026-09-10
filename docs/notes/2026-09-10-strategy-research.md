# Strategy research before further implementation

Research date: September 10, 2026. Scope: three economic mechanisms, primary
research, current U.S. contract access and published costs. No strategy code,
backtest, paid data, account changes or trades were undertaken for this review.

## Decision

**The strongest candidate for further systematic-strategy research is slow,
diversified, long/short futures trend.** Dated crypto cash-and-carry is a second,
opportunistic candidate with a more directly observable entry hurdle. Defined-risk
option selling ranks third and should receive no implementation effort now.

These are research priorities, not approved investments. Published evidence can
support a mechanism; it cannot establish that our attainable implementation will
beat cash. Neither candidate has a defensible expected return or probability of
success for this account yet.

The mandate remains active quantitative trading, a possible $5,000 pilot and
roughly $1,000 drawdown tolerance. Use 4% and 6% cash comparison scenarios, with
6% the harder hurdle; neither is a verified currently available fixed rate.
At $5,000, those hurdles are $200 and $300 annually before tax. That makes
recurring data, trading and operating costs economically significant.

| Priority | Proposed strategy | Economic rationale | Main unresolved question |
|---|---|---|---|
| 1 | Monthly long/short futures trend across distinct markets | Prices can adjust gradually; persistent moves may survive slow trading costs | Can accessible whole contracts preserve diversification and risk control? |
| 2 | Fully paid spot plus equal-quantity short dated crypto future | Buyers of leveraged exposure sometimes pay a futures premium | Is an executable premium sufficient after costs and capital reserves? |
| 3, parked | Monthly defined-risk index option spreads | Investors pay for protection against adverse outcomes | Does premium remain after the protective wing, losses and retail friction? |

## 1. Slow, diversified futures trend

### Evidence and counterevidence

Moskowitz, Ooi and Pedersen studied 58 instruments across equity indices, bonds,
currencies and commodities over 1985–2009. Their canonical approach uses the sign
of trailing 12-month excess returns, monthly holding periods and volatility
scaling. This supports researching a broad, slow implementation rather than
extrapolating from one intraday market. Gradual information response and hedging
demand are proposed explanations, not demonstrated causes.
[Original paper](https://fairmodel.econ.yale.edu/ec439/mosk.pdf)

Hurst, Ooi and Pedersen extend the historical evidence back to 1880. That broadens
the range of environments, but the study uses reconstructed older data and
estimated costs and shares authors with the original paper. It is neither an
independent live replication nor a forecast of our return.
[Century study](https://images.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf)

Kim, Tse and Wald challenge the interpretation: much of the original result may
come from volatility scaling rather than the directional signal. A fair later
evaluation must compare identical instruments and risk weights with the signal
removed, and distinguish scaled from unscaled results. Those are diagnostic
controls, not passive-investment recommendations.
[Counterevidence](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2786955)

Our own record also matters. [BA-001](../strategies/BA-001.md) already studied
12-month trend; [BA-002](../strategies/BA-002.md) blended 9/12/15-month signals.
They used equal-dollar, long/cash ETF sleeves and produced weak results, including
before tax in BA-002's repaired-source review. Futures would add shorts,
volatility-based sizing, separate currency/commodity exposures, and collateral
and roll mechanics. This is a justified extension to examine, **not a newly
discovered signal or a reset of the prior failures**.
[Prior source-sensitivity review](../reviews/BA-002-source-sensitivity.md)

### Concrete proposed design

Start with one transparent specification: the sign of trailing 12-month futures
excess returns, evaluated monthly; long positive signals, short negative ones,
flat at zero; size using trailing volatility and portfolio risk limits. Observe
the signal before the execution window. Rolls and actual contract P&L must be
accounted for separately from signal-series construction. Do not calculate
percentage returns naively from arbitrary back-adjusted price levels.

No lookback contest, machine-learning filter or combination with the failed MES
rules. The eventual sizing, roll, execution and halt protocol must be fixed before
examining candidate returns. This review specifies the strategy architecture;
it does not pretend that an executable risk protocol has already been validated.

### What changed in retail feasibility

CME's E-nano equity contracts are now live. NES is $0.50 per S&P index point,
one-tenth MES; its minimum tick is 0.5 points, worth $0.25. Smaller exposure helps
position sizing, but does not establish liquidity or a trading advantage.
[CME specifications](https://www.cmegroup.com/articles/faqs/faq-e-nano-equity-index-futures.html)

A five-market feasibility universe, **not a proposed one-contract-each portfolio**:

| Exposure | Contract | Approximate long overnight initial margin |
|---|---|---:|
| U.S. equity index | NES | $324 |
| Treasury duration | MTN | $711 |
| EUR/USD | M6E | $329 |
| Gold | 1OZ | $460 |
| Corn | MZC | $207 |
| Sum of these illustrative units | | **$2,031** |

These are rounded public IBKR requirements retrieved September 10, not
account-specific quotes. Short requirements differ and margins can change.
Margin measures required collateral, not maximum loss.
[IBKR margin table](https://portal.interactivebrokers.com/en/trading/margin-futures-fops.php?ex=us&hm=us&pm=0&rgt=0&rsk=1&rst=101004110808)

Thus $5,000 is not automatically excluded by contract margin alone. However,
five whole-contract positions cannot generally match five desired risk weights.
Doubling the illustrative initial-margin sum would require about $4,062 before
trading losses; that arithmetic shows how little stress capacity may remain.
It does not predict a margin increase or liquidation threshold.

Validate MTN as **price-based** Treasury exposure, not a yield future; verify
each contract's multiplier, expiry and settlement mechanics. Micro grains are
500 bushels and one-ounce gold is cash settled.
[Treasuries](https://www.cmegroup.com/markets/interest-rates/micro-treasury-futures.html),
[grains](https://www.cmegroup.com/articles/faqs/faq-micro-agriculture-futures.html),
[gold](https://www.cmegroup.com/articles/faqs/faq-1-oz-gold-futures.html)

The main failure modes are prolonged sideways markets, abrupt reversals,
correlated losses, poor small-contract liquidity and excessive minimum position
size. Larger capital improves sizing and buffers; it does not improve the
underlying signal. There is no verified minimum viable account size yet.

## 2. Dated crypto cash-and-carry

### Mechanism and evidence

Buy spot and short an equal quantity of an expiring future at a sufficient
premium. Hold the hedge to settlement under a predetermined exit procedure.
This is an extension of [BA-009](../strategies/BA-009.md); it differs from its
initial perpetual-style funding implementation and BA-009B's dated/perpetual
spread. It requires no forecast of hourly funding persistence.

The authors of *Crypto Carry* link premiums to leveraged demand and market
segmentation. Their December 2025 summary also finds that spot-ETF introduction
compressed carry, with a particularly large reduction on CME. Their historical
offshore carry figures cannot become a U.S. retail yield assumption. The payer
is credible, but competition can remove the opportunity.
[Authors' evidence](https://cepr.org/voxeu/columns/crypto-carry-market-segmentation-and-price-distortions-digital-asset-markets)

CME MBT represents 0.1 BTC; BFF represents 0.02 BTC with weekly Friday expiries.
Coinbase dated nanos represent 0.01 BTC or 0.1 ETH. Smaller units help funding,
while short maturities leave little premium to cover repeated costs. Coinbase
retail documentation limits when the next monthly contract becomes tradable;
an exchange listing alone does not prove account access.
[MBT](https://www.cmegroup.com/education/courses/introduction-to-bitcoin/micro-bitcoin-futures-product-overview),
[BFF contract card](https://www.cmegroup.com/markets/cryptocurrencies/files/bitcoin-friday-futures-fact-card.pdf),
[Coinbase retail rules](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-intro)

IBKR lists Coinbase BIT/ET at $0.20 broker commission plus $0.10 exchange and
$0.01 regulatory fee per contract per side: $0.31 before any applicable carrying
or other charges. This is a verified route to evaluate, not proof that total
cost is lower than alternatives. Spot fees, spreads and exit costs remain material.
[Commission schedule](https://www.interactivebrokers.com/en/pricing/commissions-futures.php),
[exchange/regulatory charges](https://www.interactivebrokers.com/en/accounts/fees/Coinbase.php)

### A complete hurdle, not a headline yield

Use all capital dedicated to the strategy, including idle reserve:

`C = spot acquisition + initial margin + accessible cash reserve`

`expiry P&L = q × (entry future − entry spot)`
`           + q × (actual spot exit − futures settlement index)`
`           − all costs + actual interest received`

Compare that P&L with `C × cash rate × holding days / 365`. An indicative midprice
is not an executable entry; future exit/index mismatch remains uncertain.

**Illustration only:** dedicate $5,000, of which $2,500 purchases spot, for 30 days.
The 6% cash hurdle is $24.66. If total transaction costs are $10, the hedge must
capture over $34.66 gross, equivalent to roughly **16.9% annualized basis on the
$2,500 spot notional**, even assuming perfect settlement matching. At $25 costs,
the hurdle rises to about **24.2%**. These are sensitivity calculations, not quotes
or expected returns. A 12% notional carry would only equal 6% on total capital
before any costs in this example.

IBKR's first $10,000 of uninvested USD cash earns no ordinary interest, and
commodity-segment cash does not earn it. Do not silently add a T-bill return
to a small broker account. Separately held interest-bearing collateral would
require its own liquidity and transfer accounting.
[IBKR interest rules](https://www.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php)

Spot gains cannot automatically pay futures variation margin across accounts.
Basis widening, higher margin, settlement-index mismatch and failed hedge
execution can create losses or forced liquidation. Paying for spot in full
does not cap account losses at $1,000. No synchronized executable dated basis
was established in this review; no currently attractive entry is claimed.

## 3. Defined-risk option premium: park for now

Research supports demand for protection around economic uncertainty, but that
does not establish excess profits for sellers after crash losses.
[Federal Reserve research](https://www.federalreserve.gov/econres/ifdp/the-price-of-macroeconomic-uncertainty-evidence-from-daily-options.htm)

XSP is cash settled and European exercise, with a $100 multiplier. A hypothetical
one-point vertical sold for 0.20 earns $20 with $80 maximum expiration loss
before costs, if that strike width and price are available. IBKR's $1 minimum
applies to each combo leg: $4 base commission for opening and closing a
one-contract vertical, before other fees and execution spread. That consumes
20% of this hypothetical credit.
[XSP specifications](https://www.cboe.com/tradable_products/sp_500/mini_spx_options),
[IBKR options fees](https://www.interactivebrokers.com/en/pricing/commissions-options.php)

Protective wings cap individual contractual losses, not cumulative strategy
drawdown. Cboe's historical CNDR/BFLY illustrations include T-bill collateral
and exclude fees and taxes; they are not a small-account return forecast.
The implementation-specific edge is insufficiently established to justify
options-data purchases or a third development branch.
[Benchmark methodology caveats](https://www.cboe.com/insights/posts/benchmark-indices-series-volatility-management-with-cboes-bfly-and-cndr-indices)

## Fixed next research budget and decision rules

This literature/access review is complete. The proposed next stage is **one
research session, at most two hours, $0 paid data, no strategy code**, producing
one feasibility worksheet. This is a scope cap, not a promise that time alone
can supply missing evidence.

1. **Trend, at most 75 minutes:** the five named contracts only. Document current
   fees, spreads/depth and volume with timestamps; whole-contract dollar risk;
   roll/expiry restrictions; and margin/price-shock scenarios at $5k, $25k and
   $100k. Use published or already available risk inputs and label proxies.
   Larger scenarios are comparisons, not requests to invest more.
2. **Carry, at most 30 minutes:** BTC and ETH dated nanos only. Obtain a
   time-aligned executable spot/futures quote packet if publicly available,
   exact active-contract settlement terms and all-capital break-even basis.
   Document account eligibility as unknown unless verified. No vendor tour.
3. **Decision, 15 minutes:** advance at most one candidate to a frozen evaluation
   protocol. Record measured facts, assumptions, missing evidence and the exact
   reason to proceed or stop. An unattractive quote rejects that entry; absent
   data leaves a question unresolved. Neither proves an entire family impossible.

Trend earns further work only if a practical portfolio retains distinct risk
exposures, leaves credible liquidity reserves and has tolerable friction under
conservative assumptions. Carry earns further work only if its executable
economics exceed the cash hurdle plus a documented allowance for residual
risks, without stretching the capital reserve. If neither qualifies, stop this
round rather than invent a fourth strategy.

A later empirical evaluation must separate strategy P&L from collateral yield,
report cash-relative return and dollar drawdown, include costs and operational
stress, and disclose statistical uncertainty. Positive gross returns alone are
insufficient. Taxes have not been modeled here; a funded proposal needs a
consistent after-tax comparison without assuming favorable treatment.

Preserve the research ledger: ETF development/validation history and MES
2021–2023 remain seen. Existing unopened holdout files remain unopened; calendar
years examined in another instrument are not wholly unseen economic regimes.
New small contracts have no prelaunch execution history: parent-market data
can inform signals and risk, but cannot fabricate historical nano fills.

The credible eventual build is a slow trading and risk system around one
validated mechanism. A more capable coding model can improve the research and
implementation; it cannot supply evidence that markets have not provided.
