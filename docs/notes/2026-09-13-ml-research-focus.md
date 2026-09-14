# Research focus: monthly stock selection with combined signals

Decision date: September 13, 2026, local time. This records the research direction
recommended after commit `06641c7`. It is a planning decision, not a frozen
experiment, profitability claim, or authorization to buy data or trade.

Follow-up: the [costed proposal](../../research/ml-stock-selection-design-2026-09-13/PROPOSAL.md)
now identifies Sharadar's direct full-history personal bundle at $69/month.
Public Apple samples work; paid coverage and purchase approval remain pending.
The proposed universe is historical S&P 500 membership, with two fixed models
and an eight-active-hour effort cap after access. This supersedes the unresolved
provider-selection status below; the broader data still has not been acquired.

## Recommendation and financial hypothesis

Focus on active, long-only US stock selection at monthly frequency. Study
whether a model combining valuation, profitability, lagged price momentum,
and risk information ranks next-month returns better than a simple model
using exactly the same information. Retain $10,000 as the simulated pilot size
and the user's approximately 20% drawdown tolerance as an implementation
constraint, without treating a stop order as a guaranteed loss ceiling.

The economic hypothesis is that valuation and business quality help distinguish
stocks with similar recent price performance. A learned interaction may add
information beyond a fixed weighted average. This is a hypothesis about
incremental prediction, not established mispricing: those characteristics can
also reflect compensation for risk, and public information can already be
incorporated into prices.

Choose monthly decisions to make turnover, data cadence, and operational work
more compatible with a small account. This is a practical design preference,
not evidence that monthly trading is profitable. Holdings may persist through
multiple reviews; a monthly forecast need not cause a complete monthly sale
and repurchase. Active stock selection remains exposed to falling stock markets.

## Concrete model question

- Proposed target: next-calendar-month total return relative to the eligible
  stock universe's return. Relative prediction is assessed separately from
  the account's absolute return, risk, and cash opportunity cost.
- Start with a small, economically specified input set spanning valuation,
  profitability, lagged returns, volatility, and liquidity. Exact definitions
  depend on verified historical availability and must be fixed before training.
- Compare a regularized linear model with one gradient-boosted tree model.
  They receive identical inputs, training dates, and evaluation treatment.
  A tree model can represent interactions; it is not assumed to be superior.
- Include a transparent fixed combination of the input ranks as a reference.
  Model-selection effort and any tuning allowance must be registered and
  counted; an unsuccessful result must not trigger an unrecorded model sweep.
- Research breadth must reflect the intended liquid-stock opportunity set
  through time, including removed and failed companies. The exact universe
  and training/evaluation dates are not selected yet. Do not replace the
  current 200-company cache with today's surviving stock list.

A language model can support source extraction, research and implementation.
The trained numerical model has the narrower task of producing repeatable
stock scores from timestamped inputs. Historical language-model extraction,
if later proposed, also requires controls for knowledge of subsequent outcomes.

## Why this direction, and what the sources do not establish

Gu, Kelly and Xiu's original empirical asset-pricing work studies machine
learning forecasts, including trees and neural networks, with gains attributed
to nonlinear predictor interactions. It motivates testing combinations rather
than expecting one standalone rule to carry the account. Its reported results
do not establish a return attainable in this user's account.
[Original research](https://www.nber.org/papers/w25398).

AQR's November 2024 paper studies nonlinear combinations of economically
motivated signals, including valuation, momentum and profitability. Its
illustrations use long/short portfolios; the reported stock-selection results
exclude transaction costs. Its rolling 360-month estimation also differs
substantially from our short cached sample. Borrow the question and comparison
logic, not the reported performance or a claim of direct replication.
[Paper](https://www.aqr.com/-/media/AQR/Documents/Alternative-Thinking/Alternative-Thinking-2024-Issue-4-Can-Machines-Build-Better-Stock-Portfolios.PDF?sc_lang=en).

Man Group's discussion recommends establishing a simple model and requiring
additional value from complexity. A richer model is a challenger whose
incremental benefit must be measured.
[Practitioner discussion](https://www.man.com/insights/intro-machine-learning).

This direction extends previously explored stock, earnings, and momentum
ideas. It is not an independent new economic family and does not erase prior
failures or turn already-reviewed years into unseen data.

## Data plan and unresolved dependency

Use Open Source Asset Pricing for definitions and historical research
references. Its downloadable characteristics are historical outputs, not a
verified current trading feed. Regenerating signals can require licensed
underlying data. Do not assume its availability solves price histories,
delisting proceeds, security identifiers, or original publication timing.
[Data](https://www.openassetpricing.com/data/),
[Timing and methodology](https://www.openassetpricing.com/faq/).

The current 200-issuer cache has already-documented gaps and too little varied
evaluation history to justify the intended research scope. Reuse its accounting
engine and source-checking lessons; do not let its coverage dictate the new
financial question. Broader historical prices, security lifecycles, and
financial statements as they were known at each date are the main dependency.
No provider, license, coverage level, or total acquisition cost has yet been
verified for that combined requirement. Do not label this a ready-to-train plan.

The next deliverable is one costed data-and-experiment specification: identify
a feasible historical-to-current data path, estimate the complete cost, fix
the opportunity set and chronology, and state the bounded model comparison.
Use public documentation and existing local records first. Present a concrete
paid-data proposal only if it is necessary; no purchase is implied here.

## Evidence and stopping decisions

Judge ranking improvement on later dates excluded from fitting and selection,
with preprocessing fitted on training data only and labels fully available
before each refit. Respect shared market dates when assessing uncertainty;
many stocks in one month do not provide independent market regimes.
Maintain the existing seen-data ledger. The reserved 2024–2025 strategy windows
remain unopened and are not implicitly released by this direction decision.

Assess implementation economics alongside predictive evidence: whole shares,
turnover, entry/retention rules, commissions, spreads, dividends, corporate
actions, and realistic cash treatment. Before any final untouched evaluation,
freeze the account and risk rules. Do not design a halt or exposure overlay
after seeing losses. Account-level evaluation must compare like risk exposure,
the simpler model, and the user's cash reference scenarios after costs.

Stop this research track if adequate data is disproportionate in cost, the
model adds no credible predictive value under the bounded protocol, or that
value fails realistic account costs and risk constraints. Positive research
would justify a separately specified forward paper test; it would not
authorize funded execution or establish dependable income.
