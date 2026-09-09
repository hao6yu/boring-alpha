# The rate card is worth more than the model: financing break-even, 4.90% to 12.00%

Measured 2026-09-06, round 46. Tool: [`financing_desk.py`](../../tools/financing_desk.py); tests
[`test_financing_desk.py`](../../tests/test_financing_desk.py) (9).

## The assumption every leveraged number in this repository rests on

Fourteen rounds of leverage work have priced the loan one of two ways: the archive's bill curve **+150bp**, or
`income_frontier.MENU_PUBLIC` = **4.90% all-in**, which round 30 sourced as the April 2026 posted flat tier of the
cheapest US retail desk (Public.com). Both are real rates that real people pay. Neither is what most retail
accounts pay, and the difference is not a rounding issue — an April 2026 survey of fifteen brokers has the base
tiers at **Schwab 10.00%, E\*TRADE 10.45%, Fidelity 10.575%, Merrill ~11.13%, Firstrade ~12.00%**, and explicitly
notes that base tiers are what accounts under $100k pay, because the tier discounts start above the balance a
starter account has ([source](https://sidebysidebrokers.com/blog/margin-rates-2026-comparison.html), [IBKR's own
page](https://www.interactivebrokers.com/en/trading/margin-rates.php) showing cash 3.13% / margin from 4.13%).

That is a **710bp spread on the same loan against the same collateral**, and no tool in this repository stated the
number that makes it checkable: **at what financing rate does the levered book stop beating the same money
unlevered?**

## The break-even, at a constant 1.25×

| sleeve | window | @4.90% | @12.00% | break-even | at the expensive desk |
|---|---|---:|---:|---:|---|
| SPY | full archive | +1.12pp | −0.70pp | **9.21%** | **the index wins outright** |
| SPY | the VOO era (192mo) | +2.18pp | +0.29pp | **13.15%** | keeps 13% of the edge |
| QQQ | full archive | +0.45pp | −1.36pp | **6.60%** | **the index wins outright** |
| QQQ | the VOO era | +3.25pp | +1.28pp | **16.89%** | keeps 39% of the edge |

At 2.0× the tolerable rate *falls* — SPY full-history **8.25%**, QQQ full-history **4.10%** — because variance
drag scales with the square of exposure while financing scales with (w − 1). Leaning harder makes the recommendation
**less** robust to the rate you are quoted, not more.

Two things follow directly, and neither was known before this round:

1. **A levered SPY book over the full archive loses to unlevered SPY at any rate above 9.21%.** Every large-custodian
   base tier on the menu is above that. The tilt survives at those desks only on the strength of the last sixteen
   years (13.15% break-even) — a bet that the post-2010 era repeats, made at a desk charging 10-12%.
2. **The era is worth 3.94 points of break-even** (9.21% → 13.15%). The same r39 finding — that the window is worth
   half the edge — reappears as a financing tolerance, which is the form in which it can actually change a decision.

## The comparison that ends the argument

The tilt's entire measured edge, SPY over the VOO era at 1.25× and the cheapest desk's money, is **+2.18pp/yr**.
The rate-card gap between the two ends of the menu, at that same 1.25×, costs **(12.00% − 4.90%) × 0.25 = 1.77pp/yr
— 81% of the edge**, and against SPY's full-archive edge of +1.12pp it is **163%**: the desk choice is worth more
than the strategy, over the whole history, at the leverage the recommendation actually suggests.

No signal this project has ever measured was worth more than ~2.5pp/yr net — not momentum, not volatility targeting,
not attention, not the news pipeline. Fourteen rounds of modelling moved the answer by less than switching brokers
does. That is not a criticism of the modelling; it is what it means for a market to be mostly efficient at a
$20,000 account size, and it inverts the priority order the goal implies. **The order is: desk, then leverage, then
fund, then model** — and the model is where the fun is, not where the money is.

The same asymmetry runs on the cash side of the same article: the desks charging 10%+ on margin pay under 1% on
sweep cash, while the cheap-margin desks pay 3%+. That is the finding of round 44's sibling work — the switch's
value depends on where the cash sits — arriving from the outside.

## What this does *not* say

It does not say borrow at 4.90% and lean to 2.0×. R40 measured the shape: at 1.25× the loan is under water 39.1% of
months and its worst month costs 2.6 years of the income the switch produces. It does not verify anyone's quote:
posted base tiers move with the Fed and a review page is a secondary source, which is why the tool prints the break-even
rather than a verdict about a named broker — the break-even is the number that stays useful when the rate card
changes, and it is checkable without saying who you bank with or how much you have.

## Checks

9 tests, 1.0 s, offline. The load-bearing one is an identity, not a measurement: **at w = 1.00 the excess must be
exactly zero at every rate on the menu** (`places=9`), because nothing is borrowed — if the cash leg and the
financing leg failed to cancel, every number above would be fiction and this test would know. Also pinned: the
excess is strictly decreasing in the rate (**the comparison was written backwards first, `assertLess` on a
decreasing series, and the test failed — the only reason the direction is known to be pinned**); the break-even
falls as leverage rises; the menu is ascending and its cheap end must equal `ifr.MENU_PUBLIC` so this file and
`income_frontier` cannot drift to pricing two different desks; `MENU_PUBLIC` must be restored after `excess`
returns (the tool patches a module global); `compounded` must return `None` for a destroyed account rather than a
complex number — the first draft of this round divided two monthly *returns* and reported `ann = −2.84%` for SPY's
benchmark, which is what catching that looks like; the era break-even gap is asserted at **three** points rather
than the four I first wrote, because the measurement is 3.94 and a threshold tuned to four is a test that fails on
a Tuesday. Full suite: **1577 passed, 233 subtests** (collected 1577 before the run). `journalctl verify`: chain
intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in. Forward book unchanged at 2026-09-04 — the
clock rolled to Monday but the session has not closed, so the pre-registered `voltarget` observation still cannot
advance.
