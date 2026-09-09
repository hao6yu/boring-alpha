# Failure has to be simulated, not averaged: the CAGR shortcut was wrong by 4.3× — on the sample that looked safest

Measured 2026-09-07, round 52. Tool: [`plan_survival.py`](../../tools/plan_survival.py) (new). Tests: 13 in
[`test_plan_survival.py`](../../tests/test_plan_survival.py).

## Round 51's failure count was a shortcut, and the shortcut had a direction

Round 51 reported that a $50,000 plan withdrawing $500/mo for 10 years "would have failed in 8% of VOO's windows and
69% of SPY's". That number came from counting windows whose **compound return fell below the required return** — a
mean-based proxy, and wrong in principle the moment money leaves the account on a schedule. Terminal wealth is not a
function of a window's CAGR: +30% then −50% and −50% then +30% have identical compound returns and end $1,600 apart
on the same $50,000 with the same withdrawals (pinned as the first test in the new file, because if it were not true
the tool would be pointless).

Simulated on actual paths, monthly, expenses charged:

| sleeve | windows | shortcut | simulated | the shortcut's error |
|---|---:|---:|---:|---:|
| **VOO** | 72 | 8% | **36%** | **understated 4.33×** |
| SPY | 284 | 69% | 71% | 1.02× |

The error is not spread evenly, and where it lands is the whole point: **the shortcut was nearly exact on the
hostile sample and off by more than four times on the friendly one.** A steadily-rising sample with occasional
drawdowns — which is what a friendly sample *is* — fails not because the average return misses the target but because
the withdrawals land during the drawdowns and sell at the bottom. The windows the CAGR test counts as passing are
exactly the ones where sequence risk is the only thing that can hurt you. An approximation whose error is worst where
the news is best is the most dangerous kind of approximation this project has caught itself using.

## The same plan, priced three ways, per failure budget

$500/mo, principal intact, capital required:

| sleeve | P(fail) ≤ 10% | ≤ 5% | = 0, always | price of "always" |
|---|---:|---:|---:|---:|
| VOO (10y) | $53,685 | $53,996 | $55,205 | **1.02×** |
| VTI (10y) | $108,288 | $129,528 | $185,040 | 1.43× |
| SPY (10y) | $283,698 | never | **never** | **unreachable** |
| SPY (20y) | $147,301 | $151,232 | $188,429 | 1.25× |
| VTI (20y) | $86,384 | $87,158 | $98,524 | 1.13× |
| QQQ (20y) | $269,397 | $322,302 | $504,748 | 1.57× |
| VOO (20y) | untested | untested | untested | — |

Three honest findings sit in that table.

**1. On SPY at 10 years, no amount of money buys certainty.** Not "a lot" — none. In the worst window in the record
the index itself finished below where it started, so a level-withdrawal plan cannot finish there either at $500m or
$5bn: the failure is arithmetic, not a funding gap. Money buys a bigger buffer; only a different asset buys a floor.
This is a new kind of answer for this repository — a requirement that is *not* priced, because it is not for sale.

**2. The price of the word "always" is set by the sample, not by the plan.** 1.02× on VOO, 1.13× on VTI, 1.25× on
SPY, 1.57× on QQQ, unreachable on SPY-10y. VOO's premium looks nearly free because 72 windows since 2010 contain no
lost decade; VTI's is cheap for the same reason (its record starts 2011). Round 51 said the *bar* is a sample
artefact; this says the *insurance premium on top of the bar* is one too.

**3. The guarantee engine and this one cross-validate, and their gap is itself a price.** Round 50's guarantee says
$500/mo for 20 years needs **$137,195**. This tool's zero-failure figure is **$188,429 — 1.37× higher**, because it
demands more: `capacity` asks that the account *never be liquidated*, this asks that it also *finish whole*. The
extra promise costs 37% of capital, and neither engine was lying. That is now a test (`ratio < 1.8`, direction
pinned), so if the two ever drift apart in the wrong direction the file fails.

Also: untested is not failed. VOO has 192 complete months, so it has **no** 20-year window; `survival` returns
`p_fail = None` and `capital_for` returns `None`, deliberately distinct from `inf`. An empty sample printed as a
failure would put VOO's missing history in the same column as SPY's arithmetic impossibility, which is how a table
like this one lies.

## Checks

13 tests, 1.9 s, offline. The order-effect pair must differ by > $500 at identical CAGR; a liquidated-then-recovered
run must still be reported as destroyed (a plan that dips to −$4,000 in month 30 was closed by the broker in month
30); no-withdrawal/no-cost must reproduce buy-and-hold to 8 places; the expense must satisfy the exact identity
`c0·(1−er/12)^120` at zero return; P(fail) must be monotone in capital and in target; the window counts must equal
`required_edge.rolling_cagr()["n"]` for three sleeve/horizon pairs — two tools now slice the same record and must
agree on what a window is; the friendlier sample must stay ≥20pp friendlier; and the cross-engine ratio must sit
between 1.10 and 1.80. Two of my first-draft assertions were wrong and are recorded as such: one charged a single
year's expense against ten years of compounding ($1,702 measured against a $94 expectation), and the other divided by
a monthly rate while calling it annual ($1.65m of required capital out of a $137k fact). Full suite **1638 passed**
(collected first: 1625 + 13). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
