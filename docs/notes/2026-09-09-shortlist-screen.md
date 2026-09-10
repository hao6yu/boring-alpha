# Bounded shortlist: evidence before another strategy

September 9, 2026. Three families reviewed; five primary papers/publication
records consulted. No market-data return calculation, new strategy code,
purchase, account connection, or holdout evaluation in this screen.

**Follow-up complete:** the [late-day cost/implementation review](2026-09-09-late-day-feasibility.md)
returned **no-go for insufficient evidence**. The paper does not provide the
single-S&P trade expectancy needed to clear the MES hurdle. This round is
closed; no candidate advanced to implementation or a backtest. The initial
ranking below is retained as the decision history.

Decision: **advance only late-day futures momentum to a cost/implementation
feasibility review.** This is a research priority, not a validated trade.
BA-010 remains retired. No new candidate is registered or approved for backtesting.

## 1. Late-day futures momentum — first priority

Hypothesis: some hedging and rebalancing demand reinforces the day's price move
near the close. Baltussen et al. study more than 60 futures through May 2020;
their prior-close-to-final-half-hour return predicts that final interval. They
present evidence relating this to options and leveraged-fund hedging. This
supports a mechanism worth inspecting, but does not establish present-day MES
profitability. [Authors' paper](https://academicweb.nd.edu/~zda/intramom.pdf)

Gao et al.'s earlier predictor uses the previous close through the first half-hour
in ETF data. It is a different signal, not an interchangeable implementation.
The shortlist prioritizes the later futures formulation; we will not try both
and choose the best historical result.
[Original publication](https://profiles.wustl.edu/en/publications/market-intraday-momentum/)

Main unknowns: S&P-specific effect size, exact close/entry conventions, attainable
MES execution costs, and compatibility with one contract and the pilot's loss
tolerance. Existing price bars can support a timing-rule test, but cannot measure
dealer gamma or prove its mechanism. Any gamma-conditioned rule would require
additional inputs and a new feasibility decision.

## 2. Overnight inventory reversal — simple version rejected at this screen

The New York Fed study connects overnight returns around European trading hours
to preceding order imbalances. Crucially, its simple 02:00–03:00 ET strategy's
Sharpe falls from 1.1 gross to −0.5 after bid–ask costs; the wider 01:30–03:30
window reaches only 0.3 after spreads. This is direct evidence against spending
a backtest on the simple daily rule. Conditional order-flow versions need
signed-volume observations that our minute OHLCV archive does not contain.
[Authors' paper, introduction](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf)

Do not widen windows or substitute price declines for signed volume to rescue
this family within the current round.

## 3. Pre-FOMC drift — deprioritized

A follow-up study finds the original effect essentially disappeared after 2015.
[Kurov, Wolfe and Gilbert](https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf)

A 2026 Fed review complicates that conclusion: its later sample retains gains
in a pre-announcement overnight window, with subsequent reversals. It does not
establish that the original full-window strategy remains profitable. Window
definitions and a small event sample make selection risk material.
[Knox and Vissing-Jorgensen, section 5.2](https://www.federalreserve.gov/econres/feds/files/2026023pap.pdf)

Calendar data is accessible in principle, but this family does not justify
trying several announcement windows against the local history. No test queued.

## Next decision and stop conditions

One focused follow-up on candidate 1 must produce a short go/no-go note:

1. Extract the published S&P-specific signal, timing, return magnitude and cost
   assumptions. Separate those from diversified futures portfolio statistics.
2. Translate the evidence to one MES contract, delayed executable prices and
   the existing base/stress fees. Identify exact missing data and engine changes.
3. Check capital, overnight exposure, stop policy and likely sample adequacy.
   A risk-control adaptation must be disclosed as a new strategy, not a faithful
   replication of the paper.
4. Advance only if the documented magnitude plausibly covers costs and the
   cash hurdle. Otherwise close this round; do not automatically add candidate 4.

For scale, using the **existing research assumptions**, a hypothetical 100-trade
year requires more than $9.41 average gross per one-contract trade to cover
$6.22 stressed round-trip friction, $18.60 annual data fees, and a $300 first-year
6% cash target on $5,000. Calculation: `6.22 + (18.60 + 300) / 100 = 9.406`.
This is a screening hurdle, not a forecast; trade count is illustrative, taxes
and additional overhead are excluded, and average profitability alone cannot
establish an acceptable drawdown.

Only a passing feasibility note leads to **one** separately registered strategy
and one development test. Keep 2021–2023 labeled seen history, 2024–2025 unused
for strategy evaluation, and count every candidate attempted. Preserve the
existing pilot constraints; do not increase capital to make a failed test pass.
The present scope is evidence and feasibility, with no additional data spending.
