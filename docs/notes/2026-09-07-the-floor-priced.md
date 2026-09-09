# The floor has a price, an interior maximum, and a convention that was hiding 21% of it

Measured 2026-09-07, round 54. Tool: [`allocation_floor.py`](../../tools/allocation_floor.py) (new). Tests: 13 in
[`test_allocation_floor.py`](../../tests/test_allocation_floor.py).

Round 52: an all-equity withdrawal plan on SPY cannot be made certain at any account size. Round 53: a cash bucket
does not buy the floor, because it only moves the timing of a sale. Both pointed at a second asset held all the way
through. This round prices that — a constant mix, rebalanced monthly, both legs charged their expense — and finds an
answer, a price, and a discrepancy that turned out to be a definition.

## First, the convention was worth more than the allocation

Guaranteed first-year cheque on $100,000 over 20 years, all-equity:

| promise | cheque |
|---|---:|
| level $/mo, never liquidated | **$447.73** |
| indexed at 2.5%/yr, never liquidated | **$368.83** |
| the capacity engine's `guarantee()`, stride 1 | $364.45 |
| the capacity engine's `guarantee()`, stride 3 | $378.52 |

This file's first run disagreed with the capacity engine by **18.3%** — an alarming number, since both claim to
compute the guarantee. Neither implementation was wrong. `wc.capacity` has always withdrawn an **inflated** cheque
(`inflate=0.025`, a default that has been in the code since it was written and appears in none of the headline
numbers), and this file withdrew a level one. With the convention matched, the two engines that share no code agree
to **1.2%** (1.2% at stride 1, 2.6% at stride 3).

Two lessons, in order of how badly they could have hurt: **when two implementations disagree, diff the conventions
before the code** — the cheapest explanation is usually an argument one file passes and the other does not. And
**a withdrawal rule is not one number**: level versus indexed is worth 21% of the headline, more than every
allocation finding below. A "guaranteed income" quoted without naming its convention is holding two numbers and
showing you one.

## The allocation curve is an inverted U, and the corner is worse than the origin

Guaranteed (never-liquidated) first-year cheque per $100,000, SPY, 20 years, 164 windows:

| bills | level cheque | indexed cheque | Δ indexed | median terminal | P(erasure) at $500/mo |
|---:|---:|---:|---:|---:|---:|
| 0% | $447.73 | $368.83 | — | 2.10× | 28% |
| 10% | $459.88 | $378.02 | +$9.19 | 1.77× | 31% |
| 20% | $470.52 | $386.14 | +$17.31 | 1.46× | 35% |
| 30% | $479.86 | $392.65 | +$23.82 | 1.20× | 40% |
| 40% | $487.77 | $397.53 | +$28.70 | 0.93× | 64% |
| 50% | $494.10 | $400.96 | +$32.13 | 0.69× | 80% |
| **65%** | $500.37 | **$403.18** | **+$34.35** | **0.40×** | **100%** |
| 80% | $502.42 | $401.67 | +$32.84 | 0.17× | 100% |
| 100% | $463.88 | **$366.06** | **−$2.77** | 0.04× | 100% |

**Bills do buy the floor.** P(liquidation) on a $500/mo plan falls monotonically 10% → 9% → 7% → 4% → 2% → 1% → 0%
as the bill weight climbs to 65%, exactly as rounds 52 and 53 said it should: this is a second asset, not a second
bucket. And the maximum guaranteed income is an **interior** maximum at about 65% bills, worth **+$34.35/mo (+9.3%)**
over holding no bills at all.

**Then the curve turns over.** At 100% bills the indexed guarantee is **$366.06 — worse than holding no bills at
all** ($368.83), and liquidation probability jumps to 45%. The mechanism is in the archive: SPY's 20-year windows
straddle ZIRP, where the bill leg paid a monthly factor of 0.00001 at its worst, 1.86%/yr on average. A plan living
off T-bills through 2012–2021 fails harder than one living off equities. The floor is real, it is bought with bills,
and it is bought with *some* bills.

## The cheque and the estate are opposite ends of this curve

Look at the last two columns together. The allocation that maximises guaranteed income — 65% bills — has **P(erasure)
= 100%**: on every start date in the record, the plan finishes below where it started, and the median window ends at
**0.40× of the capital** against 2.10× for the all-equity plan. It guarantees the cheque by guaranteeing the erosion
of the estate, month by month, in every window. There is no allocation on this curve that does both. Any "safe
withdrawal" figure that reports only the survival of the cashflow is describing the consumption of the account, and
round 52's stricter promise (never liquidated *and* ends whole) priced that difference at 1.37× the capital.

## The cross-engine check that caught a convention

Three engines now simulate the same all-equity plan on the same archive. At $500/mo, 20 years, 164 windows, all bills
off:

- median terminal identical to 6 decimal places (2.104967);
- liquidated windows **16 = 16** (`allocation_floor` vs `plan_survival`'s destroyed count);
- failed windows **46 = 46** (`p_erase` vs `plan_survival`'s failures);
- minimum terminal differs **by convention**: 0.0000 here (a liquidated account ends at zero) against −0.0049 in
  `plan_survival`, which reports the signed shortfall — a severity measure, not an ending.

That last difference was found by writing the test, not by reading the code, and the test now compares the two
minimums by sign rather than value.

## Checks

13 tests, 9.8 s, offline: the two-engine agreement inside 3% on the matched convention, *and* a pinned assertion that
the level figure still misses the indexed engine by >15% (if the two conventions ever merge, that test fails and
someone re-reads what the headline means); the inverted-U interior maximum with the corner worse than the origin;
monotone liquidation up to the kink; median terminal strictly decreasing in bills; the trough never above the ending;
bisection legality in the failure budget; at full bills the equity leg cannot be heard; and untested horizons
returning `None`, not zero. Full suite **1664 passed** (collected first: 1651 + 13). `journalctl verify`: chain
intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
