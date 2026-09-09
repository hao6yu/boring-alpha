# I published a lucky draw as a finding: the cadence edge is +0.91%/yr, not +3.54%/yr

Measured 2026-09-06, round 37. Tool: [`daily_reset.py`](../../tools/daily_reset.py) (`cadence_profile`), tests
[`test_daily_reset.py`](../../tests/test_daily_reset.py) (19).

## What round 34 printed, and what it should have printed

Round 34 compared a daily-reset book against a monthly-reset book on the same 8,458 daily sessions and reported the
monthly book ahead by **+3.54%/yr over the record** and **+6.40%/yr in the corona year**. I built a route
recommendation on that. The comparison had one flaw I never examined: the monthly book was measured on **one**
sequence of 21-session blocks, the one starting at session zero, because that is where a loop that increments by 21
happens to begin.

A backtest with a fixed start date has a sampling distribution whether or not anyone computes it. Computing it:

| cadence | phases | mean | worst start | best start | spread | bill | mean net |
|---|---:|---:|---:|---:|---:|---:|---:|
| daily | 1 | 22.80% | 22.80% | 22.80% | 0.00% | 0.12% | 22.68% |
| weekly | 5 | 24.31% | 23.31% | 24.81% | 1.50% | 0.05% | 24.26% |
| monthly | 21 | 23.71% | 15.43% | 26.58% | **11.15%** | 0.03% | 23.68% |
| quarterly | 63 | 17.47% | **−56.19%** | 27.52% | **83.72%** | 0.02% | 17.45% |

At 3× leverage, **monthly beats daily by +0.91%/yr on the average of all 21 possible start days, not +3.54%.** The
number I published was the near-best of 21 draws — 26.34% against a 23.71% mean — and the worst start day yields
**15.43%, which is below daily rebalancing.** Every claim built on the size of that edge was built on a draw I
picked by accident of where the array started.

## The direction survives. The magnitude does not.

This is not a retraction of the recommendation, and the distinction matters for what to do with it. Averaged over
all start days, at **every** leverage tested, rebalancing less often wins the mean and wins the bill:

| leverage | daily net | weekly | monthly | quarterly |
|---|---:|---:|---:|---:|
| 1.25× | 13.11% | 13.18% | 13.27% | **13.29%** |
| 2.00× | 18.67% | 19.23% | 19.49% | **19.64%** |
| 3.00× | 22.68% | **24.26%** | 23.68% | 17.45% |

Every less-frequent cadence beats daily at 1.25× and 2×, and at those two leverages **quarterly is the mean-max**
by two to sixteen basis points. At 3× the ranking inverts — weekly takes the mean and quarterly falls to last. What breaks under leverage is
not the average, it is the **dispersion**: the spread across start days is 0.24% at 1.25×, 1.13% at 2×, and 11.15%
at 3× for the same monthly cadence. **Cadence is a leverage decision, not a schedule.** The cost of rebalancing
rarely is worth paying and the risk of rebalancing rarely grows faster than the gain — until 3×, where quarterly
rebalancing has a worst observed start at **−56.19%**, worse than the daily reset by 79 points.

## The reversal that makes this note necessary rather than editorial

Averaging over start days inside each regime rather than across the whole record is where the recommendation
actually dies. Phase-averaged, 3× leverage, monthly against daily:

| window | sessions | daily | monthly mean | worst start | gain |
|---|---:|---:|---:|---:|---:|
| full record | 8,457 | 22.80% | 23.71% | 15.43% | **+0.91%** |
| dot-com 2000-02 | 752 | −47.72% | −45.09% | −52.46% | +2.64% |
| crisis 2007-09 | 756 | −35.83% | −35.26% | −53.45% | +0.57% |
| **corona 2020** | 253 | +16.10% | −1.86% | **−93.53%** | **−17.96%** |
| bear 2022 | 251 | −54.24% | −47.68% | −55.24% | +6.56% |
| calm 2017 | 251 | +78.18% | +73.98% | +69.95% | −4.19% |

Round 34 quoted **+6.40%/yr in the corona year**. Phase-averaged the corona window says **−17.96%**, and the worst
start day there returns **−93.53% against daily's +16.10%** — a 110-point spread on the same strategy in the same
twelve months. The figure I published was the best of 21 draws, quoted for precisely the window whose rhetorical
job was to prove infrequent rebalancing was safe under stress. Two of six regimes flip sign against the record.
**The cadence advice is regime-conditional and was never global**, and the window that matters most to a leveraged
account — a sharp V — is the one where rebalancing rarely hurts most, because the account is under-levered on the
way down and cannot get back on the way up.

At the leverage this project actually contemplates — **1.25×** — the entire cadence question is worth **0.24% of
luck and +0.16%/yr of mean**. It is not a lever. Rounds 33 to 36 have been arguing over a route choice that turns
out to be worth about fifteen basis points at the only leverage the account can survive.

## Why this error was so easy to make, and the rule that catches it

Nothing about the flaw is exotic. A loop over blocks has to start somewhere; starting at zero is the default; the
default produces a number; the number looks like a measurement because it *is* one — a single, honest,
unrepresentative sample. The mistake was treating a deterministic backtest as if determinism meant precision. It
meant only that I had fixed an input I never declared.

The check that generalises: **any backtest whose result moves when you change a cosmetic input — start date, block
offset, sort order on ties — must report the distribution over that input, not one value from it.** Phase-averaging
is three lines: loop the offset, take the mean, report min and max. The first version of `cadence_profile` cost less
than the paragraph of prose it invalidated.

## Checks

19 tests, 0.4 s, offline: the phase-averaged monthly mean must beat daily but **by less than 2%**, so the corrected
figure cannot silently re-inflate; the naive single draw must sit **above** the mean, pinning the bias's direction
rather than merely its size; phase spread must be monotone in the interval and quarterly's worst draw must be below
−50%, so the leverage warning cannot be optimised away. Full suite: **1523 passed, 233 subtests**. `journalctl
verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
