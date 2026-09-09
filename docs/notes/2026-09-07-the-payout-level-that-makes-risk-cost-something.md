# The payout level that makes risk cost something

Measured 2026-09-07, round 77. New tool: [`binding_payout.py`](../../tools/binding_payout.py). One change to a published
tool: `rotation_search.score` now takes optional payout levels. Tests: 13 in
[`test_binding_payout.py`](../../tests/test_binding_payout.py).

Round 76 ended on a clause that could not fire. Every construction — brake, control, single fund — had a failure probability
of 0.0% at the published $435.47/mo per $100,000, so the repository's measure of risk could not see the thing a brake is for,
while its measure of capacity priced the brake's cost to the cent. That is not evidence against brakes. It is evidence that
the question was asked at a level where it has no answer. So the same six books were priced again, this time at withdrawals
that bind, expressed as multiples of the static 50/50 blend's own capacity — because since round 75 the blend, not the index,
is the thing to beat. The scale is set in a second pass over the control, so the ruler is one of the things being measured;
payout levels go into the scorer as dollars, and `rotation_search.score` remains the only thing that prices a plan.

**The decision rule, fixed before the first run:** risk has a measurable price if some construction fails less often than the
control at the same withdrawal, at a multiple no larger than 1.25x on the long record. Above that, a plan is being asked to
pay out more than it can fund and the number describes the withdrawal, not the strategy.

Capacity of the control: **$589.65/mo** long, **$1,101.66/mo** recent. Failure probability, month-start readings:

| long record | 0.90x | 1.00x | 1.10x | 1.25x | 1.50x | 2.00x | own capacity | fails at 1.10x |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| spy_only | 20.5% | 23.5% | 25.0% | 27.3% | 28.8% | 87.9% | 0.739x | 33 of 132 |
| qqq_only | 0.0% | 0.0% | 0.0% | 7.6% | 22.0% | 27.3% | 1.221x | 0 of 132 |
| blend_sq (control) | 0.0% | 5.3% | 16.7% | 22.7% | 27.3% | 49.2% | 1.000x | 22 of 132 |
| brake_both | 0.0% | 2.3% | 12.9% | 21.2% | 37.1% | 91.7% | 1.014x | 17 of 132 |
| brake_either | 0.0% | 0.0% | 4.5% | 20.5% | 29.5% | 89.4% | 1.103x | 6 of 132 |
| dm12_sq (round 75's rule) | 0.0% | 0.0% | 0.0% | 0.0% | 15.2% | 51.5% | **1.428x** | 0 of 132 |

| recent record | 0.90x | 1.00x | 1.10x | 1.25x | own capacity |
|---|---:|---:|---:|---:|---:|
| spy_only | 39.7% | 69.8% | 92.1% | 100.0% | 0.834x |
| qqq_only | 0.0% | 0.0% | 0.0% | 41.3% | 1.152x |
| blend_sq (control) | 0.0% | 4.8% | 41.3% | 85.7% | 1.000x |
| brake_both | 41.3% | 77.8% | 85.7% | 100.0% | 0.798x |
| brake_either | 28.6% | 54.0% | 82.5% | 100.0% | 0.849x |
| dm12_sq | 0.0% | 28.6% | 65.1% | 100.0% | 0.914x |

**The decision rule fires.** Four constructions fail less often than the control at a withdrawal the rule allows. Round 76's
inert clause is now the most informative one on the page.

## Reading it without fooling anyone

**The brake's protection is real and mostly small.** `brake_both` fails on 17 windows where the control fails on 22 — five
windows out of 132, which is not a difference to build anything on. `brake_either` fails on 6, and `dm12_sq` and plain QQQ on
none: those are differences worth reading. The counts are printed next to every percentage and **no confidence interval is
computed on them, because the ten-year windows overlap each other** and treating 132 overlapping windows as 132 trials is how
a spurious significance gets published.

**The protection is worth something on exactly one record.** On 2011-2026 the same brakes that helped are the worst rows on
the page: at the control's own capacity, `brake_both` fails on 77.8% of windows against the control's 4.8%, and its capacity
there is 0.798x of the control's — it fails *earlier and more often*. Round 76's conclusion survives being measured properly:
a brake is insurance, and the last fifteen years were not a time when insurance paid.

**One construction dominates the control on the long record and loses on the recent one.** `dm12_sq` — round 75's best rule,
the one a control beat — has 1.428x the control's capacity, zero failures through 1.25x, and 0.914x of the capacity with 28.6%
failures on the recent window. Same twelve months of code, opposite verdicts, window deciding. Every sheet in this repository
prints both for that reason.

**The row nobody expected is the honest one to distrust.** Plain QQQ has more capacity than the "diversified" blend on both
windows (1.221x long, 1.152x recent) and zero failures through 1.10x on both, at its posted 20 bps. But the shared calendar
starts 2005-09-06 — set by the youngest leg plus a 200-day warmup — so the growth index's own collapse in 2000-2002, an 82%
drawdown, is not inside a single window measured here. Round 73's long window starts 2002-08, and that is where that tail
lives. The defensible sentence is *"QQQ dominates on every window this calendar can share,"* and the test asserts the calendar's
start year so the caveat travels with the number.

**Plain SPY is the floor.** It is the only row that fails at 0.90x on either record, and it is the lowest-capacity book on the
page — the objective's stated benchmark, `VOO`, is the thing everything here has to beat and nothing here wants to hold.

## What this changes about the objective

It changes the question that matters. "Beat the index monthly" is a capacity question, and at withdrawals well inside capacity
the failure probability of every one of these books is zero — the brake buys nothing a person at 0.6x of capacity can use, and
costs them the difference in capacity. At withdrawals near or above capacity, which is what "live off it" means and not what
"extra money each month" means, the ordering inverts on the long record and stays inverted on the recent one. So the useful
thing the repository can now say is parametric and small:

- withdrawing **well below** what the book can fund → capacity is all that matters → the highest-beta book you will not sell
  out of is the answer, and a bot has to beat *that*, not the index;
- withdrawing **near** what it can fund → the recent table is the one that applies, and no brake tested here helps;
- withdrawing **more** than it can fund → no rule saves you; the withdrawal is the problem.

The bot the objective describes still does not exist in this archive, and round 72's refutation of the news corpus plus rounds
73-76's three families all point the same way: at daily closes, monthly cadence and retail costs, decisions cost capacity.
What is left is not another overlay. It is either a data source that can support the short-horizon decisions the objective
actually named — intraday prints, quoted spreads, a labelled news feed — or the conclusion that on daily closes the answer is
the book, not the bot.

## Checks

13 tests, 4.6 s, offline: the multiples arrive as dollars and at least one row fails at 2.00x (the all-zeros bug that the first
version of this file printed is now an assertion rather than a believable table); failure probability is monotone in the
withdrawal for every row; `inside`, `beats_control` and the counts are all recomputed from the row; the control's capacity is
the same number round 76 published, to six decimals, through a different tool; the calendar is the one round 75 published; an
unknown construction raises rather than defaulting. Suite: **1991 passed** (collected first: 1978 + 13); ledger chain intact.
