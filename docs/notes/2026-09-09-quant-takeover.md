# Quantitative trading takeover: audit and first U.S. feasibility screen

Date: 2026-09-09. Starting revision: `314b31b`. Working branch:
`codex/us-crypto-research`. Current mandate: [active quantitative trading](../QUANT_RESEARCH.md).

The prior research does not establish a deployable edge, but it also does not
establish that quantitative trading is exhausted. Several simulator defects
make its exact returns, control comparisons, and confidence intervals unreliable.
The old artifacts and charter remain historical records. This revision is a
repair diagnostic, with some explicitly conservative protocol changes; it is
not a new sealed test or evidence of profitability.

## Accounting audit and repairs

| Finding in BA-007 v1 | Consequence | Revision 2 behavior |
| --- | --- | --- |
| Seven-day momentum divided by the most recent prior close | It measured one-day momentum on a complete daily panel | Uses the close exactly seven calendar days earlier; requires all intervening bars |
| Daily P&L used fixed portfolio weights while fees were charged on weekly weight changes | Simulated continuous rebalancing without its trades or costs | Holds signed quantities between trades; marks actual P&L and charges each changed unit |
| A missing held bar deleted the position | Data gaps could erase subsequent losses and imply an unexecutable exit | Stops on missing held prices, skipped held sessions, or missing daily funding, including an absent funding series |
| Signal used a closing price and filled at that same close | Timing could use information unavailable when an order must be placed | Records signal date and executes at the following day's close |
| Partial lookbacks and absent funding could become valid scores | Unknown observations could be mistaken for economic information | Requires complete 60-day prior prices, 30-day prior volume, and three observed carry days |
| Random seed reset to the same value each week | Stable universes reused the same random portfolio and changed the turnover comparison | Deterministic seed includes the week; controls change assignments weekly |
| “Stationary bootstrap” used Gaussian block lengths | Reported method did not match the implementation | Uses geometric block lengths with the declared mean |

A hand-checkable counterexample: enter a $0.50 long and $0.50 short at prices
100, hold quantities while the long moves 100 → 200 → 100 and the short stays
flat. Before costs the final P&L is zero. The old weight-based calculation
produced +12.5%. Regression tests now pin the correct answer, actual drifted
turnover, funding signs and event marks, complete lookbacks, and missing-data
behavior. Earlier tests that encoded incorrect return identities were corrected.

The complete-history rule, prior-only volume window, and next-close fill are
conservative changes to the evaluation protocol, not a claim to replay the
original charter exactly. No additional untouched BA-007 window was opened.

The real default diagnostic now stops on **2022-02-26**, where held prices are
missing for FTMUSDT, LRCUSDT, LUNAUSDT, MANAUSDT, NEARUSDT, ONEUSDT, SANDUSDT,
and XRPUSDT. It returns an explicit data error and issues no repaired verdict.
These gaps require source verification; they must not be filled with invented
exits or selectively dropped from performance.

Remaining limitations are material. Daily summed funding rates use daily-close
marks, not the marks at each settlement; intraday event completeness has not
been established. The reusable ledger supports event marks, but the legacy
archive does not supply them. BA-007 still lacks executable spreads, margin
and liquidation, collateral yield, and taxes. Weekly scrambled controls are
not matched for turnover or factor exposure. Legacy PASS/FAIL helper fields
remain numerical diagnostics, explicitly labeled: they do not fully implement
stress-control comparisons or authorize deployment. Statistical insignificance
is not proof of an exactly zero effect.

## Published fees and research assumptions

The dated [machine-readable fee record](../../research/us-crypto-fees-2026-09-09.json)
separates public evidence from unknown account terms. Percentages below apply
per filled side, with spread and slippage additional.

- **Robinhood Crypto exchange routing:** below $10,000 trailing 30-day routed
  volume, taker 0.95%, maker 0.50%; $10,000–$50,000, 0.75%/0.35%;
  $50,000–$250,000, 0.25%/0.125%. This is executed volume, not account capital.
  Market-maker routing has no commission, but that does not establish zero
  execution cost. No Robinhood quotes were measured in this screen.
  [Official fee schedule](https://cdn.robinhood.com/assets/robinhood/legal/rhc-fee-schedule.pdf)
- **Coinbase Advanced spot:** the official help page directs users to sign in
  for the full schedule. The screen therefore uses explicit taker assumptions
  of 0.60%, 1.20%, and 2.40%, with 1.20% as the base scenario. These are neither
  a verified customer average nor a guaranteed upper bound. Maker fills are
  not assumed. [Official fee explanation](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees)
- **Coinbase U.S. perpetual-style futures:** the July 2025 launch disclosure
  advertised fees as low as 0.02%, inclusive of exchange, clearing, and NFA
  fees, with a $0.15 minimum per contract. The formula takes the greater of
  notional fee and minimum; it does not add them. Current account terms are
  unverified. The screen tests 0.02%, 0.05%, and 0.10%, using 0.05% as its base.
  [Official launch disclosure](https://www.coinbase.com/blog/perpetual-futures-have-arrived-in-the-us)

An arithmetic average across venues or maker/taker schedules would not measure
this strategy's costs. Research uses fees on actual modeled turnover, on both
entry and exit, with a separately measured spread and a range for unknown fees.

## BA-009: first public cost screen

[BA-009](../strategies/BA-009.md) studies buying spot and shorting the same
underlying quantity in Coinbase's U.S. futures. This is a new feasibility
hypothesis, not an approved trading model. The public collector uses no keys
and saves raw responses, timestamps, source URLs, hashes, fee assumptions, and
policy inputs. Offline replay verifies the archived inputs.

Snapshot: `data/us_crypto/snapshots/20260909T233523573534Z/`.
Products: BTC `BIP-20DEC30-CDE`, ETH `ETP-20DEC30-CDE`. Public FCM metadata
identifies these as expiring contracts with hourly funding; the international
venue's product type and rates must not be substituted.

Each asset below is a separate hypothetical $5,000 account, not two simultaneous
positions in one account. The screen caps each leg at half the capital,
requires $1,000 beyond initial margin after entry fees, and compares against
4% and 6% cash on the full $5,000. Idle collateral earns zero in this model.

| Base scenario: 1.20% spot / 0.05% futures, 30 days, 4% cash | BTC | ETH |
| --- | ---: | ---: |
| Contracts short | 3 | 10 |
| Approximate notional per leg | $2,346.53 | $2,466.75 |
| Entry + exit fees and current spread | $58.98 | $62.82 |
| One-hour rate, simply annualized on notional | 3.50% | 8.76% |
| Excess over cash if that rate and basis remain unchanged | −$68.66 | −$61.49 |
| Required annualized funding on notional over 30 days | 39.10% | 39.09% |
| Futures collateral headroom after a 50% price rise | $372.14 | $30.38 |

Those are scenarios, not forecasts or backtested returns. The last row assumes
the current margin rate and no transfer of spot gains. ETH's $30 headroom is
thin; the initial reserve does not guarantee protection from liquidation or a
$1,000 loss limit. Basis changes, higher margin, delayed transfers, or different
fills can materially change the outcome. Taxes and operating overhead are excluded.

## Public U.S. funding history obtained

The [Coinbase market-data portal](https://www.coinbase.com/market-data/derivatives?funding_venue=cde)
has an Export CSV control after selecting **Coinbase Derivatives**, then
**BIPZ30** or **ETPZ30**, and **90D**. These symbols match the contract roots
and December 2030 expiry in the snapshot. Both files were downloaded without
login, copied unchanged, and hashed under
`data/us_crypto/funding-history/2026-09-09-cde-90d/`.

`tools/us_funding_history.py` validates column units, finite values, UTC hour
boundaries, timestamp order, duplicates, gaps, file hashes, and consistency
between the hourly rate and the portal's rounded APR. Each export has 2,160
hours from June 12 00:00 through September 9 23:00 UTC, with no internal hourly
gaps. Export completeness does not establish settlement reconciliation.

| Reported funding, June 12–September 9 | BTC / BIPZ30 | ETH / ETPZ30 |
| --- | ---: | ---: |
| Sum of hourly rates over 90 days | 1.7805% | 2.1672% |
| Mean hourly rate, simply annualized | 7.22% | 8.79% |
| Hours with positive funding | 88.80% | 92.18% |
| Median 30-day sum, overlapping windows | 0.5982% | 0.7286% |

These percentages describe constant dollar notional, not fixed-quantity
strategy P&L or return on the full account. For context, the snapshot's 90-day
base-cost funding hurdles are 18.72% BTC and 18.44% ETH annualized on notional.
Even the lower 0.60% spot-fee sensitivity needs 13.85% and 13.57%, respectively.
That comparison makes simple always-on carry unattractive under these modeled
costs and capital constraints. It is not a historical execution backtest:
current spreads and fees were not historical observations, and funding can
change. No timing rule or predictive edge has been tested.

## Validation and continuation

Focused regression coverage includes the corrected engine and ledger, public
cost scanner, funding import, existing perp fetcher, venue fees, and research
boundary/freeze checks. The full repository suite also contains expensive
unrelated ETF Monte Carlo work; one full-suite attempt was interrupted after
27 tests passed in 222.62 seconds. A full-suite pass is not claimed.

Final focused run: **163 passed in 9.13 seconds**. Both the saved order-book
snapshot and funding-history analysis reproduced their archived reports
offline; the local documentation links and `git diff --check` passed.

The next research step is to reconcile public funding with settlement marks
and obtain historical basis, executable spread, and margin data. Simple
always-on carry has not earned further model complexity from this screen.
A separately recorded dated-futures basis test can investigate a different
mechanism before fitting a funding-timing model. New hypotheses are allowed;
rules selected using observed data need subsequent independent evaluation.

No account access, order, transfer, paid subscription, outreach, or scheduled
monitoring occurred. The public work does not require pilot capital yet.
