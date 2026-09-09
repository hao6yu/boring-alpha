# The short-term trading hypothesis, tested: two bugs 230× apart, both invisible in the benchmark, and a sign flip by era

Measured 2026-09-07, round 55. Tool: [`trend_cost_test.py`](../../tools/trend_cost_test.py) (new). Tests: 12 in
[`test_trend_cost_test.py`](../../tests/test_trend_cost_test.py).

The objective's hypothesis is short-term trading on trend. Fifty-four rounds had priced leverage, cash yield,
financing, withdrawal plans and allocation, and had never scored that hypothesis directly. Six rules are declared
before the results and all six are reported.

## First, the two bugs, because they are the methodological finding

The first run reported MA200 at **+2036% a year** — 190× the benchmark, with a plausible 11% max drawdown and a
plausible 215 switches. The buy-and-hold row said **10.77%**, which is exactly right, so the table looked healthy.

**Bug 1 — the off-risk leg.** `data.cash_factors` is keyed by trading day and holds a daily **factor** (1.0000 to
1.000247). My `daily_bills()` read it as a *monthly rate* and divided by the days in the month, paying the cash leg
roughly **190% a year**. Any rule that ever held bills was inflated; the benchmark never holds bills, so it was
untouched. Correct fix: the daily rate is `factor − 1`, exactly — and compounding those daily factors across a month
reproduces `wc.monthly`'s monthly factor to 1e-12, which is now a test. **A control that never touches the corrupted
leg cannot detect its corruption.** When a new leg appears only in the treated arms, the new leg needs its own
independent check before any treated number is read. → MA200: 2036% → **20.33%**.

**Bug 2 — one day of lookahead.** `exposures()` returns the exposure decided at close *i*; `rets[i]` is the return
**of the day ending at that same close**. Applying `expo[i]` to `rets[i]` earns the day that produced the signal.
The file's docstring asserted the opposite while its code did this. Shifted so a decision at close *i* is held over
day *i+1*. → MA200: 20.33% → **8.86%**.

Two corrections, and the headline moved by a factor of **230**. The benchmark moved by 0.02pp.

## The results, SPY, 8,457 days, 1993-02-01 to 2026-09-04, no lookahead, 0.02% one-way

| rule | avg exposure | switches | CAGR | max DD | vs hold | vs exposure-matched passive |
|---|---:|---:|---:|---:|---:|---:|
| **hold** | 100% | 1 | **10.75%** | 55.2% | — | — |
| ma200 | 75% | 215 | 8.86% | **23.3%** | −1.88pp | −0.15pp |
| ma50x200 | 75% | 31 | 10.20% | 33.7% | −0.54pp | −0.29pp |
| mom3m | 71% | 393 | 7.26% | 27.0% | −3.48pp | −0.11pp |
| mom12m | 79% | 99 | 10.01% | 31.2% | −0.74pp | +0.40pp |
| voltarget | 83% | 8,399 | 8.52% | 32.0% | −2.22pp | −0.31pp |

**All five lose to plain buy-and-hold.** The second comparator is the one that matters: a rule out of the market 25%
of the time has de-levered, and de-levering is free, so the fair benchmark is the same average exposure held
passively with the rest in bills. Against that, four of five are within ±0.4pp and the fifth is +0.40pp — **no timing
value anywhere in the sample, at any cost level.** The cost ladder at 8× slippage moves MA200 to 7.89% and 3-month
momentum to 5.52%; turnover is a tax, never a rescue. The drawdown reduction is genuine (55.2% → 23.3%) and it is not
the objective: it can be bought without a signal by holding the same average exposure in bills.

## The whole-sample average hides a sign flip

| era | days | hold | ma50x200 | mom12m | timing value of ma50x200 | of mom12m |
|---|---:|---:|---:|---:|---:|---:|
| 1993-2009 | 4,263 | 7.45% | **11.10%** | **10.45%** | **+4.47pp** | **+3.78pp** |
| 2010-2019 | 2,516 | 13.16% | 8.19% | 9.23% | **−3.14pp** | −3.31pp |
| 2020-now | 1,678 | 15.33% | 10.55% | 9.65% | −2.58pp | **−3.81pp** |

Trend timing was not imaginary: in the archive's first seventeen years it added **+4.47pp and +3.78pp over
exposure-matched passive** — real timing value, not leverage in disguise. **In every era since it has subtracted
roughly 3pp a year**, and the span where it is worst (2010-2019, −3.14pp) is the only span in which VOO exists as a
ticker. The objective names VOO as the bar and asks for short-term trading; on the record where that bar exists, the
trend family is worth −3pp/yr against a bill-holding clone of itself. A whole-sample statistic that averages a
positive regime from 1993-2009 with a negative one since is not a summary, it is a cancellation — and the era you
will trade in is the one that must be scored.

## Checks

12 tests, 0.9 s, offline: the daily bill leg must compound to `wc.monthly`'s monthly factor to 1e-12, and no day may
pay more than 10% annualised; an all-cash rule must land between 0.5% and 5%/yr (the generalised sentinel for bug 1);
a three-day hand-computed path pins the shift, distinguishing the −50% day avoided from the +60% day captured —
which is exactly the assertion bug 2 violated; warm-up must hold cash, never guess; exposures clipped to [0,2];
CAGR monotone decreasing in cost for every rule and flat for buy-and-hold; the constant comparator invariant to the
shift; an undeclared rule raising rather than returning zeros. `test_every_tested_rule_loses_to_plain_buy_and_hold`
carries a message telling a future reader to check the shift and the bill leg before believing a win — two of the
three times this file's numbers moved, that is what had happened. Full suite **1676 passed** (collected first: 1664 + 12). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00
paid in.
