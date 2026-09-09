# The only zero-variance line in the whole file series is worth 8× the trading model — and the backtests have been paying it away

Measured 2026-09-06, round 24. Tool: [`cash_yield_gap.py`](../../tools/cash_yield_gap.py), tests
[`test_cash_yield_gap.py`](../../tests/test_cash_yield_gap.py) (8).
Round 23 proved that at a $20k account no stochastic edge of the size this repository has ever found can be
*measured* — and that no increase in deposit size changes it, because an edge and its noise both scale with
capital. That leaves one kind of improvement worth chasing: **the kind with no variance.** This file prices the
one that exists, and then finds it has been quietly credited to the simulations all along.

## 1. The decision you control, priced

The bill leg needs no external source: it comes off the sealed archive's own cash curve, the same series every
backtest here accrues against — **2.88% quoted today**, 3.51% over the last year, 4.42% over three, 2.46% over
ten. The sweep leg is external and audited: the median default brokerage bank-sweep across eleven tracked firms
was **0.02% APY as of 2026-09-02**, while the median money-market option at those same firms paid **~3.40%**
([switchwize audit](https://www.switchwize.com/learn/brokerage-sweep-account-rates);
[realcostreport](https://www.realcostreport.com/investing/brokerage-tools/cash-sweep-rates/) has the large-broker
defaults at ~0.05%). Fund legs: [SGOV 0.09%, BIL 0.14%](https://portfolioslab.com/tools/stock-comparison/BIL/SGOV).

Two of those sources disagree by **52bp** (3.40% audited MMF versus the archive's 2.88% curve). Both bill legs
below use the archive's own lower number; the conservative line at the bottom uses the bill leg alone and never
the external quote.

| idle cash | at a 0.02% sweep | broker MMF ~3.40% | SGOV (bill − 0.09%) | bill ladder | gain, best leg |
|---|---|---|---|---|---|
| $2,000 | $0.03/mo | $5.67/mo | $4.65/mo | $4.80/mo | **+$5.63/mo** |
| $5,000 | $0.08/mo | $14.17/mo | $11.61/mo | $11.99/mo | **+$14.08/mo** |
| $20,000 | $0.33/mo | $56.67/mo | $46.45/mo | $47.95/mo | **+$56.33/mo** |
| $50,000 | $0.83/mo | $141.67/mo | $116.13/mo | $119.88/mo | **+$140.83/mo** |

**Break-even sweep rate: 2.79%.** Below it the bill fund wins, above it the sweep wins and no further analysis
is needed — that single number is worth reading off a statement, because it makes every other figure in this
table checkable in ten seconds without trusting anything here.

Set against the two decisions twenty-three rounds have priced, at $20,000:

| decision | value | variance |
|---|---|---|
| switch index fund (SPY vs VOO) | ~$1.07/mo (r38: the ~$25 figure was the noise floor) | none (round 18) |
| run the trading rule | ~$5.61/mo | p10 −$17/mo (round 23) |
| **move idle cash out of the default sweep** | **$46.12/mo** | **none: it is a quoted rate** |

Eight times the trading edge, and the month-to-month variation in that yield over the last three years is
σ = 0.077% a month — the p10 of a month's cash is the rate you were quoted at the start of it. The honest
caveats are liquidity, not risk: sweep cash is FDIC-swept and spendable, a T-bill ladder costs about fifteen
minutes a month, and an ETF costs a tick. Keep the emergency tier wherever it needs to be spendable; this
concerns settlement cash and the contribution stream. Tax is excluded per standing instruction, and that
exclusion makes these numbers *smaller* than reality, since Treasury interest is state-tax-exempt in most states.

## 2. The same number, seen from the other side, costs the file series its headline

Every simulation here credits the rule's *uninvested* slice with the archive's bill curve. The rule sat idle on
average **15.7%** of a 404-month record (and levered 18.0% of it), so the credit is worth
**0.45%/yr — against a measured edge of 0.34%/yr.**

**The unearned cash credit is 1.3× the entire edge the rule is credited with.** Not disproved, but unaccounted
for: every figure in this series showing the rule beating its own fund has paid the rule a yield that an account
parking its cash at 0.02% would never have received.

The way out is the same act as section 1, which is the tidy part. The archive curve is exactly what a T-bill
ladder or SGOV earns — so the credit is *available*, but only to an account that has already moved its cash out
of the sweep. Do section 1 and the audit's objection disappears at zero cost; don't, and the rule's edge is
smaller than the assumption underneath it. **The cash decision is not a side note to the trading decision, it is
the precondition for the trading decision meaning anything.**

Pre-registered for the next round, before any re-measurement is quoted: re-run the income frontier with the
cash leg forced to a stated sweep rate (`--cash-floor`), so every published gap is priced against the yield the
account would actually have been paid, and report which of rounds 19–22's conclusions survive it. The
expectation, stated in advance so the result can be wrong: the *ordering* of plans survives (they all earn the
same cash), and the rule's own edge does not.

## Checks

8 tests, 0.3 s, offline: every window of the bill curve recomputed from the archive by hand (a rename that left
`b["now"]` in the audit raised a KeyError, which is exactly the class of defect a test earns its place catching);
σ of the monthly rate pinned below 0.2%; the gain line recomputed independently and pinned to a band; the
break-even shown to be bill-minus-expense and nothing else; an above-break-even sweep producing a gain of
exactly zero rather than a negative number dressed as advice; idle and borrow fractions taken as positive parts
and both non-trivial; and the *unearned credit greater than the edge* pinned, so the finding has to be argued
with rather than drifted away. Full suite: **1433 passed, 233 subtests**. `journalctl verify`: chain intact
(1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.

> **Restated in round 47.** The spot bill yield quoted in this note (**2.88%**, and the **+$46.12/mo** built from
> it, and the "55th percentile of the record") was computed by annualising the last three monthly buckets of the
> cash curve — and the last of those was a **four-day stub**: the archive seals after a session, and the September
> 2026 bucket held trading days 1-4 only. Compounding a four-day accrual as a month pulled the spot down **103bp**.
> On complete months the archive's own last full month is **3.81%**, the three-month spot is **3.91%**, the switch
> is worth **+$63.34/mo** at $20,000, and today sits at the **65th** percentile — *above* the record median, not
> below it. Every distribution figure in these notes (mean $39.85, median $33.72, quartiles) moved by pennies;
> only the spot and the percentile it was compared against were wrong. See
> [`2026-09-06-the-seal-is-not-a-month.md`](2026-09-06-the-seal-is-not-a-month.md).
