# The loan's mean clears the bar and its shape disqualifies it, and that is the goal's real answer

Measured 2026-09-06, round 40. Tool: [`combined_account.py`](../../tools/combined_account.py)
(`monthly_edge`, `rolling_edge`, `streaks`); tests [`test_combined_account.py`](../../tests/test_combined_account.py) (15).

## The question this project has been answering in the wrong units

The goal says *"earn extra each month."* Every figure this repository has ever produced for the winning plan is an
**annualised mean**: +1.63%/yr, $27.24/mo. A mean is the wrong statistic for a sentence containing "each month",
because a mean is exactly what a plan can satisfy while paying you nothing for a year. Round 39 established that the
*level* of that mean belongs to a window. This round prices the *shape*, using the same engine on the same 404
months, and the shape is what settles it.

## The shape of $27.24 a month, on SPY, 1993-02 to 2026-09

| | measured | at $20,000 |
|---|---:|---:|
| average incremental month | +0.136% | **+$27.24** |
| months negative | **39.1%** | two in five pay nothing |
| longest losing run | 5 months | — |
| worst single month | −4.23% | **−$846** |
| deepest drawdown **in the excess itself** | **−22.2%** | **−$4,434** |
| how long that hole took | **9 years**, 2000-04 → 2009-02 | — |

That last row is the whole argument. The excess series — the loan *minus* just holding the index — went underwater
in **April 2000** and did not surface until **February 2009**. The holder sat through dot-com **and** the financial
crisis inside one single hole, 22 points deep at the bottom, on a plan whose advertised pay is $327 a year. The worst
single month cost **$846**, which is **2.6 times a full year** of the average pay the plan is sold on.

| rolling window | positive in | worst window | best |
|---|---:|---:|---:|
| 1 year | **76.3%** of 393 | **−14.52%/yr** | +10.47% |
| 3 years | 78.6% of 369 | −5.26%/yr | +6.03% |
| 5 years | **71.0%** of 345 | −2.69%/yr | +5.34% |
| 10 years | 84.6% of 285 | −1.79%/yr | +2.84% |

**One year in four the levered account ends the year behind plain holding**, and the worst year in the record cost
**14.5 points** more than doing nothing. The worst three-year windows are 2000-03 and 2006-09 — the same two regimes
round 30 identified as binding. The hit rate is *lowest at five years* (71.0%), below both one and ten, because
five-year windows are the ones that straddle the crises without being long enough to recover from them. Time does
repair this — but only in decades, and the goal asks about months.

## The synthesis the shape forces, and it is the most useful thing in this note

The two candidate actions in the ledger **fail in opposite directions**, and neither fails the same way as the other:

| | average | shape | level vs VOO |
|---|---:|---|---|
| idle-cash switch (all cash) | **+$39.85/mo** across the archive (+$46.12 at today's bill) | positive in **80.9%** of months, worst month **−$1.65**, no drawdown | **−11.89%/yr** |
| constant 1.25× loan | **+$27.24/mo** (404 months, SPY) | positive in **60.9%**, worst month **−$846**, **−22.2%** over 9 years | **+1.63%/yr** |

The switch is beautifully behaved — because its variance is bounded by a **fee schedule**, not by an index — and it
sits in an account that forfeits the market entirely. The loan beats the market and behaves like the market, because
that is what it is. **The action with the good shape is the one that loses to the index, and the action that beats
the index is the one with the bad shape.** There is no stance in this archive that is simultaneously positive in
level and well-behaved in shape — round 38 proved no middle stance exists at all, and this round supplies the
distributional reason why none could.

So the goal as literally worded — *a bot that earns extra each month and beats VOO* — has a complete answer now, and
it is not "not found yet":

  * **Beating the index requires exposure.** Every cash-holding stance loses to it, monotonically.
  * **Exposure inherits the index's shape, amplified.** A levered index position has a one-in-four losing year and a
    nine-year hole, by construction and not by defect of the model.
  * **A monthly paycheque requires a bounded, non-market source.** The only such source found in 40 rounds is the
    deposit spread: worth **$39.85/mo** averaged across the archive and $46.12 at today's bill, positive in four
    months in five, and never worse than **−$1.65** in a month. It is bounded because its variance comes from a fee
    schedule and a bill curve, not from an index — and it costs the market to have.

These three facts together are the finding. Thirty-nine rounds of measurement produced the first two; this round
produced the third as a consequence of asking about the shape rather than the mean.

## What this changes about what to actually do

Nothing in the arithmetic changes the recommendation, but it changes what the recommendation *is*: the honest plan is
**a cheap index fund, held, with the deposit spread collected and the borrow decision taken deliberately as a
survivability trade-off rather than described as income.** If the account needs money to arrive monthly, take the
switch and accept the index. If it can leave the money alone for a decade, the loan is worth ~2.45%/yr on a broad
index over the last sixteen years — and it must be sized so that a −22% relative hole in year one is survivable,
because that is the hole the archive's worst stretch produced.

## Checks

15 tests, 0.5 s, offline: the monthly series must reconcile with the ledger's annualised row within **$1/yr** (the
row is stored to cents; measured gap $0.0514); the share of negative months must exceed a third; the worst month
must cost more than **two years** of average pay; the excess drawdown must be deeper than 15% with `trough_years ==
9`, starting in 2000 and surfacing in 2009 — the nine years is asserted, not narrated; the five-year hit rate must be
below the ten-year one, so the "time repairs it" claim cannot be quietly optimised away; and `streaks` must return
**zero** for a series that never goes backwards, because a function that always finds a hole has no meaning. Three
tests failed before passing: a tautological assertion I wrote and then replaced with the real one, a reconciliation
tolerance tighter than the stored row's precision, and a percent-versus-dollar comparison. Full suite: **1542
passed, 233 subtests**. `journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.

> **Restated in round 47.** The spot bill yield quoted in this note (**2.88%**, and the **+$46.12/mo** built from
> it, and the "55th percentile of the record") was computed by annualising the last three monthly buckets of the
> cash curve — and the last of those was a **four-day stub**: the archive seals after a session, and the September
> 2026 bucket held trading days 1-4 only. Compounding a four-day accrual as a month pulled the spot down **103bp**.
> On complete months the archive's own last full month is **3.81%**, the three-month spot is **3.91%**, the switch
> is worth **+$63.34/mo** at $20,000, and today sits at the **65th** percentile — *above* the record median, not
> below it. Every distribution figure in these notes (mean $39.85, median $33.72, quartiles) moved by pennies;
> only the spot and the percentile it was compared against were wrong. See
> [`2026-09-06-the-seal-is-not-a-month.md`](2026-09-06-the-seal-is-not-a-month.md).
