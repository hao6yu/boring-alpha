# Late-day MES feasibility: no-go on the available evidence

Completed September 9, 2026. Scope: the single feasibility review authorized
after the [three-family shortlist](2026-09-09-shortlist-screen.md).

**Subsequent update:** the user authorized one direct test to resolve this
evidence gap. [BA-011 failed its fixed development test](2026-09-09-ba011-development.md).
The following retains the earlier paper-screen decision and its limitations.

**Decision: do not implement or backtest this candidate. Close this shortlist
round.** The evidence does not supply the S&P-specific trade expectancy needed
to clear the declared cost/cash hurdle. This is an insufficient-evidence decision,
not a finding that a tested MES strategy loses money.

No market-price files were opened, no strategy returns calculated, no new data
purchased, and no account connected. Only existing archive/calendar metadata
was inspected locally. The 2024–2025 strategy holdout remains unused.

## What the paper actually establishes

Source: Baltussen, Da, Lammers and Martens, [Hedging demand and market intraday
momentum](https://academicweb.nd.edu/~zda/intramom.pdf), JFE 142 (2021), 377–403.
Page numbers below are journal pages.

- S&P: April 23, 1982–May 1, 2020; 9,535 observations (Table A1, p.395).
- Sign of prior-close→15:30 return determines long/short exposure until 16:00
  Eastern (Eq.12, p.385).
- The 6.86% return/1.73 Sharpe describes diversified equity futures before
  costs (Table 6, p.387).
- Single-S&P results are regressions, not trade expectancy (Table B1, p.397).
- Positive S&P net Sharpe is claimed at one tick; its value and the cost
  convention are unspecified (p.386).

We could not recover S&P mean gross profit per trade. Independent extraction
agreed; the numerical rows were checked against the source table text.

## MES costs and the actual hurdle

Public pricing rechecked for this review: $0.25 broker, $0.35 CME and $0.01
regulatory charge per side. Total fees: **$1.22 round trip**.
[IBKR commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php),
[CME fee schedule](https://www.interactivebrokers.com/en/accounts/fees/CME.php).

MES is $5 per index point and $1.25 per 0.25-point tick.
[CME specification](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html).
Retain the existing modeled execution costs, rather than lowering them to fit
the paper:

| Round-trip scenario | Fees | Slippage | Trading friction | MES tick equivalents |
| --- | ---: | ---: | ---: | ---: |
| Base: one adverse tick per fill | $1.22 | $2.50 | **$3.72** | 2.976 |
| Stress: two adverse ticks per fill | $1.22 | $5.00 | **$6.22** | 4.976 |

The $1.55/month nonprofessional CME L1 assumption remains $18.60/year.
[IBKR market data](https://portal.interactivebrokers.com/en/pricing/market-data-pricing.php?menu=B).
These are research scenarios, not verified fills or the user's account bill.

With zero modeled interest on idle cash, the first-year 6% comparator on $5,000
requires $300 net. Required average gross profit per trade is:

`round-trip friction + ($18.60 data + $300 cash target) / annual trade count`

| Illustrative trades/year | Base gross hurdle/trade | Stress gross hurdle/trade |
| --- | ---: | ---: |
| 250 | $4.9944 | **$7.4944** |
| 100 | $6.9060 | **$9.4060** |

For 250 trades, stress therefore needs approximately **1.50 index points / six
MES ticks gross per trade**. These counts are illustrative, not forecasts.
Taxes and additional hosting/electricity are excluded. Clearing an average-return
hurdle would still not prove an acceptable drawdown or statistical confidence.

The paper's one-tick statement does not establish profitability at our roughly
three-to-five-tick trading friction, much less the additional cash hurdle.
It also does not establish failure at those costs: the necessary magnitude is
missing. This distinction determines the no-go label.

## Capital, data, and execution implications

Current public MES long initial margin is about $3,240 under the conservative
overnight proxy, leaving approximately $1,760 from $5,000. The existing $4,240
entry-equity floor leaves only $760 of initial-loss room before idling the
account. The planned $1,000 trailing drawdown is a trigger, not a guaranteed
maximum loss. Margin permits consideration of one contract but does not
establish that the strategy fits this risk budget.
[IBKR margins](https://www.interactivebrokers.com/en/trading/margin-futures-fops.php?ex=us&hm=us&ot=0&pm=0&rgt=0&rsk=1&rst=1).

If a later, separately authorized review supplies stronger economic evidence,
the implementation would still require these explicit adaptations:

1. Use information available by 15:30, then enter after a declared delay
   (for example, 15:31). An exact signal-boundary fill cannot be assumed. Exit
   near 16:00; the existing BA-010 runner exits at 15:55 and cannot be reused
   unchanged. Delays and risk exits change the published rule's returns.
2. The signal spans a previous close. Never subtract prices across different
   raw contracts in the unadjusted continuous series. Our metadata identifies
   roll dates; absent the preceding close for the same contract, a new protocol
   would need causal abstention. No history purchase is warranted for this
   unresolved candidate.
3. Re-audit required closing-boundary bars and previous-session references.
   The full raw archive contains extended-hours records, while normalized
   BA-010 inputs stop at the bar labeled 15:59. Exact 16:00 execution availability
   has not been verified here. Dealer gamma is not present in these OHLCV bars.
4. Define pilot loss controls before testing. Any added stop or filter would
   be an adaptation whose expectancy and drawdown the paper does not establish.

## Work boundary

No BA-011 charter or implementation was created. The simple overnight candidate
was already rejected on cost evidence; pre-FOMC remains deprioritized. Do not
automatically replace this result with another strategy, a machine-learning
model, a larger account, or a new vendor search.

Useful work remains preserved: the existing data, tested accounting tools,
BA-010 failure record, and this evidence screen. Reopening the round requires
a deliberate change in research scope or new evidence that addresses the
missing single-instrument economics. The current round is complete.
