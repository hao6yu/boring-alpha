# Research reset after BA-012

Date: September 10, 2026. Scope: primary-source review and research decisions;
no new backtest, paid data, account access or trading.

## Decision

Pause BA-012 variations. This review does **not** nominate a new bot for
implementation or establish an expected return. Two architectures still merit
conditional consideration: expiring crypto cash-and-carry and broad, slow
futures trend/carry. Both extend families already considered; neither resets
their failure history.

The priority is to establish whether an economic advantage can survive an
attainable implementation before building another detailed simulator. A model
name such as XGBoost, a neural network or reinforcement learning does not answer
that question.

The mandate remains active quantitative trading, U.S. access, an eventual
$5,000 pilot and approximately $1,000 tolerated decline. Larger capital remains
conditional. The 4% and 6% cash rates are comparison scenarios, not verified
current offers. No ordinary-stock or ETF allocation is proposed.

## What the completed work establishes

[BA-012's completed shorter diagnostic](2026-09-10-ba012-traded-profitability.md)
lost money at both $25,000 and $100,000 under base and stress costs. The $5,000
version could not trade under its rules. This is evidence against the tested
configuration, not a test of every trend strategy.

It combined a five-market universe, one directional signal, integer sizing,
contemporary margin proxies and a strict liquidation policy. Costs changed
subsequent positions as well as net profit. Without matched controls we cannot
attribute the entire result to directional forecasting. The continuous
profitable-strategy claim remains unsupported, and the intended longer study
remains incomplete.

My process judgment: the original broad-market evidence was adapted to a small
account before we established how much of the advantage survived the reduced
universe. Future work should distinguish signal evidence, feasible portfolio
construction and account execution. The proposed fractional/all-long BA-012
diagnostic is deferred by this reset, not silently run or treated as mandatory.

## Which architectures remain credible enough to consider?

| Architecture | Evidence and mechanism | Decision for this project |
| --- | --- | --- |
| Fully paid spot plus an equal-quantity short expiring crypto future | Leveraged demand and limits on arbitrage capital can create a premium; expiration supplies convergence | At most one bounded economics screen before further implementation |
| Broad slow futures trend plus carry | Long-run evidence across markets; price persistence and compensation associated with financing/curve characteristics | Park pending affordable long-history data and attainable breadth |
| Statistical pairs/mean reversion | Temporary imbalances can reverse; correlation alone supplies no contractual convergence | No current candidate; after-cost and recent-period evidence must justify reopening |
| Defined-risk option selling | Protection buyers pay for risk transfer; losses can cluster in adverse markets | Park: the premium on a naked exposure does not establish net profit on a hedged spread |
| Generic price-only deep learning, RL or market making | Model classes or execution activities, without a specified information or execution advantage here | Do not open a model search without a concrete hypothesis and credible evaluation data |

### Expiring cash-and-carry: measurable hurdle, conditional opportunity

The peer-reviewed *Crypto Carry* study supports leveraged demand and capital
frictions as explanations for premiums. The authors also report compression
after spot ETF introduction, particularly on CME. Historical offshore yields
cannot become a current U.S. return assumption.
[Published study](https://doi.org/10.1287/mnsc.2024.05069),
[authors' discussion](https://cepr.org/voxeu/columns/crypto-carry-market-segmentation-and-price-distortions-digital-asset-markets).

This extends [BA-009](../strategies/BA-009.md). Its original perpetual funding
screen and BA-009B dated/perpetual work remain adverse evidence about those
implementations. A spot/expiring-future hedge has a different terminal payoff,
but still faces fees, cash calls, settlement mismatch and custody/execution risk.

The first model would be an entry-hurdle and liquidity calculation:

`net P&L = quantity × (entry future − entry spot)`
`        + quantity × (spot exit − settlement index)`
`        − all costs + actual interest`

Divide by all dedicated capital, including spot funding and accessible margin
reserves, counting each dollar once. As an illustration, if spot occupies half
the capital and interest is zero, annualized basis must exceed 12% before costs
to beat a simple 6% annual hurdle. This is arithmetic, not an observed quote.
Do not assume broker collateral earns cash-account interest: IBKR excludes the
first $10,000 of ordinary uninvested USD and pays no interest on commodity-segment
cash. [IBKR rules](https://www.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php).

No executable quote packet was collected in this review. Current attractiveness
therefore remains unknown. Better contract granularity at larger balances does
not increase the percentage premium.

### Broad trend/carry: evidence worth preserving, no automatic retry

The original momentum study spans 58 liquid instruments. The longer historical
study spans 67 markets and includes reconstructed early exposures and estimated
costs. Neither validates our five-market implementation. These studies also
share authors, limiting their value as independent replications.
[Original study](https://fairmodel.econ.yale.edu/ec439/mosk.pdf),
[long-history study](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf).

Kim, Tse and Wald find that volatility scaling accounts for much of the apparent
advantage in their tests. Any renewed study needs matched risk-allocation and
constant-direction controls, used as experiments rather than investment
recommendations. [Counterevidence](https://www.sciencedirect.com/science/article/pii/S1386418116301379).

Cross-asset carry is distinct from trend, but can suffer common losses during
recessions and liquidity shocks. Combining them is a hypothesis; trend is not
a guaranteed carry-crash hedge. Curve observations and seasonality treatment
would require separate data. [Carry study](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf).

No minimum viable capital has been established. Treat $5,000 as a possible
operational pilot, not proof that a representative broad futures portfolio fits.
Neither $25,000 nor $100,000 automatically solves the breadth requirement.

### Why pairs and options do not become the next default

Do and Faff find historical after-cost pairs profits, but their studied pairs
and reversal strategies are largely unprofitable after 2002. This does not
exclude every modern relative-value strategy; it defeats an assumption that
generic cointegration plus more model complexity supplies an edge.
[After-cost pairs study](https://onlinelibrary.wiley.com/doi/10.1111/j.1475-6803.2012.01317.x).

Option research documents a variance risk premium, while implementation studies
show the importance of costs and margin calls. Buying a protective option uses
some of the premium received. Small defined-risk positions fitting an account
does not establish profitable expectancy or an acceptable portfolio drawdown.
[Variance-premium study](https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf),
[cost and margin study](https://novaresearch.unl.pt/en/publications/option-strategies-good-deals-and-margin-calls/).

## Where machine learning could help

Jensen, Kelly, Malamud and Pedersen's 2026 study incorporates trading costs and
signal persistence directly into portfolio learning. It demonstrates why gross
prediction accuracy can select economically poor trades. Its equity setting and
cost assumptions do not transfer automatically to retail futures or crypto.
[Machine Learning and the Implementable Efficient Frontier](https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhag022/8524346).

Our inference: ML is a candidate tool for a specified forecasting or allocation
problem. It need not wait for a separately proven profitable simple signal, but
it must compete against simple rules and regularized linear baselines on the
same net-cost, risk and data assumptions. A credible information hypothesis,
sufficient independent observations and a limited model-search budget come
first. Additional parameter searches consume evidence; repeatedly inspected
history cannot be relabeled unseen.
[Backtest-overfitting research](https://escholarship.org/uc/item/4w1110bb).

## Recommended next decision and effort boundary

The cheapest next question is whether an accessible **expiring** spot/futures
hedge can clear a conservative all-capital hurdle. This is a proposal, not a
claim that a viable entry exists or an instruction to trade.

For a follow-up, cap the screen at two hours and $0 of new paid data. Use one
venue route and at most BTC and ETH. Produce a single table containing exact
expiry, synchronized executable leg prices and sizes, fees, dedicated capital,
margin/reserve scenarios, settlement mismatch allowance and 4%/6% hurdles.
Exact account eligibility remains a separate unresolved requirement if it
cannot be verified publicly. An indicative quote must remain labeled as such.

Stop if public inputs cannot establish the economics within the limit; record
an unknown rather than entering another data-vendor search. Reject any sampled
entry that fails the hurdle. A passing packet would justify a separate proposal
for repeated observations and risk validation, not funding or an annual-return
claim. No monitor is scheduled by this note.

Broad trend/carry remains parked unless a short feasibility proposal first
identifies affordable multi-decade data, credible evaluation periods and a
representative attainable universe. A later study would fix trend, carry and
one combination in advance, with matched controls and conservative costs. It
would not tune BA-012 on its revealed history.

Research success at this stage is a supported go/no-go decision. This review
finds plausible mechanisms, but no strategy currently justified for deployment.
