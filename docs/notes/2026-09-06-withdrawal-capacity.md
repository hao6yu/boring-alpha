# What this pays per month: leverage makes the floor smaller, and my best number was a mirage

Date: 2026-09-06 · Round 7 of the trading-model goal · tool: `tools/withdrawal_capacity.py`
Status: **a measured result that contradicts the direction of the last three rounds, plus a
self-catch worth more than the result.** The objective is not met.

## Why this question and not another signal

Round 6 left two named debts. One was that the archive had never contained the benchmark the
goal names. The other was the worse one:

> Round 4's "+$346 a month" is an accrual on a paper equity line that spends 71% of its
> height underwater, not cash someone could take out.

Everything measured so far is an accumulation number: what a balance becomes if nobody
touches it. The stated goal is *a monthly amount*. Those questions have different answers,
and the second has an enemy the first does not — the order the returns arrive in. So this
round stopped auditioning mechanisms and measured the objective in its own units:

> Start with a lump. Withdraw W every month for N years. Pay real costs. Find the largest W
> that **every start date in the record survives.**

Quoted as a guarantee, not an average, because a sequence-of-returns figure averaged over
start dates blends the person who started in 1999 with the one who started in January 2000,
and only one of them ran out of money.

## The archive now contains what the goal names

`tools/fetch_market_data.py` line 93 gained **QQQ, VOO, VTI, ITOT**; snapshot
`20260906T203953Z`, 73,009 bars through 2026-09-04, `data/current` repointed.

- All 50,037 previous rows survive; revisions to shared values cap at **0.022 bps** — float
  noise again, matching round 5, not a restatement.
- QQQ from 1999-03 (6,916 sessions, including the bust), VTI 2001, ITOT 2004, VOO 2010.
- **VOO is refused a number**: 192 months cannot contain a 20-year window, and printing a
  truncated plan as though it had survived one is the oldest trick in factor research.
- Side effect recorded: the forward book's entries price whatever the archive holds, so
  future entries carry 12 quotes where the anchor carries 8. No decision, comparator, or
  sealed hash changes — still 100% SPY at 9.45 bps, `journalctl verify` exits 0.

## The table

SPY, 20-year plan, $100k lump, withdrawal indexed 2.5%/yr, 55 start months, real costs:

| leverage | worst start | median | best start |
|---|---|---|---|
| 1.00× | **$379/mo** | $626 | $896 |
| 1.25× | $335 | $649 | $945 |
| 1.50× | $300 | $630 | $1,012 |
| 1.75× | $266 | $634 | $1,091 |
| 2.00× | **$233/mo** | $626 | $1,136 |

The floor falls **38%** from 1× to 2×. The ceiling rises 27%. The median moves by less than
the search's own resolution and is printed as *indistinguishable* rather than as a winner.

**Leverage on an index sleeve buys dispersion, not income.** It widens a distribution whose
centre does not move. For a plan whose purpose is a number you can count on, the floor *is*
the product, and the floor goes down.

Round 4's conclusion survives intact in its own frame: levered SPY accumulated more dollars
in every window. Both are true. Nobody was withdrawing in round 4.

## The mechanism is not the one round 4 found

The tempting reading is "margin is expensive". Borrowing for **nothing** changes almost
nothing:

| SPY, 20-year floor | 1.00× | 1.25× | 1.50× | 2.00× |
|---|---|---|---|---|
| margin, cash + 150 bps | $379 | $335 | $300 | $233 |
| financing free | $379 | $340 | $316 | $261 |
| ETF wrapper, uncallable | — | $320 | $285 | **$213** |

At 1.5×, of the $79 shortfall roughly **$17 is financing and $62 is sequence risk**. The
wrapper — the instrument round 4 found superior, the one that cannot be force-sold — does
*worse* than margin, not better.

So the binding mechanism is the volatility itself. A levered drawdown is deeper, a
withdrawal inside it sells more units at worse prices, and the recovery rebuilds from a
smaller base. The 30% maintenance rule and the 150 bps spread are both real and neither is
the reason. Round 4's instrument finding was about accumulation and does not transfer across
the change of question — which is why it had to be re-measured rather than assumed.

The floor is set by the **May 2000** start on SPY and **April 2000** on QQQ. The tool prints
which start binds, because an undated headline invites every reader to imagine their own.

## QQQ is the worst place to put a spending plan

| sleeve | floor at 1× | floor at 1.25× | typical at 1× |
|---|---|---|---|
| SPY | $379 | $335 | $626 |
| QQQ | **$171** | **$0** | $728 |
| VTI | $509 *(thin)* | $498 | $645 |
| ITOT | $607 *(11 starts)* | $616 | $634 |

QQQ has the highest typical case — it grew fastest — and a floor **45% below SPY's**. At
1.25× leverage its floor is **$0**: no withdrawal at all can be relied on across every
20-year window in its record. The goal names QQQ as the thing to beat, and QQQ is
simultaneously the best average and the only sleeve that refuses the question outright.
Anything built on it is a bet on the start date, not an income.

*Thin* rows have too few starts (VTI 22, ITOT 11) to support a floor claim. They are printed
rather than hidden because the funds the goal names are the ones with the least history —
that is a fact about the instruments, not a rounding problem.

## The horizon is the real variable, and reporting only the 20-year answer would be cherry-picking

| setting | floor at 1× | floor at 2× | typical at 1× | typical at 2× |
|---|---|---|---|---|
| 20 years, indexed | $379 | $233 | $626 | $626 |
| 10 years, indexed | $627 | $359 | $1,204 | $1,298 |
| 20 years, no indexation | $465 | $284 | $754 | $724 |

At 10 years the typical start really does improve (+$94/mo at 2×) while the floor still
falls 43%. Sequence risk needs time to bite, and a shorter plan mostly means you keep
working. The honest statement is not "never leverage a spending account" but **the shorter
the horizon you can honestly claim, the more dispersion you can afford** — and the goal as
written ("earn extra each month") is a floor claim, not a ceiling claim.

## The mirage, and the column that killed it

A guardrail — cut the withdrawal by half when the account falls 25% from its high — looked
like the answer. It produced a **$720 first cheque at 1× (8.63%/yr)** against the fixed
plan's $379, an improvement bigger than anything leverage did in either direction. That is
exactly the kind of number this repository exists to distrust, so the run reported the
*smallest* cheque ever handed over, not just the first:

| SPY, 1×, 20 years | first cheque | smallest cheque | median |
|---|---|---|---|
| fixed, indexed | $379 | $379 | $626 |
| guardrail 25% / half | **$720** | **$363** | $1,024 |

The 8.63% figure is the largest plan that *survives* — and it survives by paying $363 a
month in the worst stretch, **below** the $379 the fixed plan promises throughout. The
guardrail did not raise the floor. It renamed it, and put the flattering month first.

Under the guardrail, leverage still monotonically destroys the floor: smallest cheque 363 →
229 from 1× to 2×. So the conclusion is unchanged, and the mechanism that appeared to
overturn it turned out to be a labelling artefact caught by a column added specifically to
try to overturn it. That column stays in the tool permanently for that reason.

A guardrail is still worth owning — most windows never trigger it and pay a much larger
median. But it is a different contract: *higher starting income with a stated risk of
halving*, not a bigger promise. Anyone comparing $720 against $379 without the smallest
cheque in view has been sold a number, not a plan.

## Method: two more vacuous tests, caught the same way as round 6's

20 tests in `tests/test_withdrawal_capacity.py`. Two passed while the thing they claim to
test was deleted:

- "a -50% month kills a 2× wrapper" **passed with the leverage switched off underneath it**,
  because an unlevered fund dies on that path too. Replaced with a two-sided monotonicity
  test — round 3's lesson, applied to a mechanism instead of a table.
- "the forced-sale fee is taken from the position" **passed with the fee deleted**, because
  the same run also pays rebalancing and withdrawal fees: *some* fee being charged is not
  the assertion. Replaced with a run whose withdrawal is zero and whose band is wide enough
  that no rebalance can fire, leaving the forced-sale fee as the only fee that exists.

Five defects reintroduced, five distinct failures, clean code green:

| defect | caught by |
|---|---|
| borrow charged at the cash rate | `test_a_levered_flat_account_loses_exactly_its_carry` |
| forced-sale fee clamped into cash | `test_the_maintenance_fee_is_taken…` |
| wrapper leverage silently ignored | `test_the_leverage_actually_levers_in_both_directions` |
| wrapper expense ratio dropped | `test_the_wrapper_pays_its_own_expense…` |
| maintenance test removed entirely | `test_a_deep_crash_triggers_a_call…` |

Plus two disciplines inherited rather than assumed. `capacity` probes its predicate on a
grid and reports `gaps`, because the forced-sale rule genuinely breaks monotonicity —
selling more *raises* the equity ratio, so withdrawing more can talk a run out of a call a
smaller withdrawal suffers; the reported frontier is the first failure, i.e. reliable all
the way down to zero. And the guardrail tests assert `cuts > 0` before crediting it with
anything.

## Reproduce

```
.venv/bin/python tools/withdrawal_capacity.py --verbose
.venv/bin/python tools/withdrawal_capacity.py --sleeve SPY --spread 0
.venv/bin/python tools/withdrawal_capacity.py --sleeve SPY --instrument wrapper
.venv/bin/python tools/withdrawal_capacity.py --window-years 10 --sleeve SPY
.venv/bin/python tools/withdrawal_capacity.py --sleeve SPY --guardrail 0.25 --cut 0.5
.venv/bin/python -m pytest tests/test_withdrawal_capacity.py -q
```

## What this does to the plan

The pre-registered candidate is a 128% SPY book: ~1.25× in this frame, so **$335 per $100k
against $379 for doing nothing**. Same verdict the backtests reached on accumulation,
arriving in the unit the goal is written in.

*Priced nine rounds later* in [`2026-09-06-income-frontier.md`](2026-09-06-income-frontier.md), which took
that conclusion as the opening question rather than the closing one: four spending rules, equalised on a
guaranteed floor across every start date, on plans including the T-bill account this tool could not score —
its ruin test killed a cash plan in its first month, so the benchmark quoted above has been computed against
an engine that could not have produced it. The guardrail is worth 1.32x to 1.59x a fixed cheque's income at an
identical promise, and the loan is Redundant in this unit.

Three consequences, largest first:

1. **The spending rule beats the trading rule.** Nothing measured here — not a signal, not a
   wrapper, not a leverage dial — moved the reliable monthly number as much as the decision
   about whether the cheque is allowed to shrink. That decision costs nothing, needs no
   forecast, and is the user's to make. It should be made before another mechanism is built.
2. **The search space narrowed by most of itself.** No leverage on any sleeve in this
   archive clears the bar, and it is not a cost problem a cheaper instrument solves. Rounds
   4 and 6 optimised a dial this round measures as counterproductive for the stated
   objective.
3. **What could still raise a floor is a policy that de-risks in a drawdown.** The candidate
   already contains a trend gate and a volatility target, and neither has ever been scored in
   withdrawal units. The floor is set by 2000–2002, exactly the regime a trend gate claims to
   read. That is now the most valuable unasked question here, and it is round 8.

One thing this round does *not* settle: whether the goal itself is right for this account. A
monthly-income objective on a small accumulating account may be the wrong objective — a 10-
year horizon is where leverage earns its dispersion. That is the user's call, not the
simulator's, and it is worth asking before more rounds are spent.
