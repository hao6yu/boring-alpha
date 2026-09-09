# What a crisis pays, with no date chosen — and the two honest answers disagree

Measured 2026-09-06, round 45. Tool: [`cash_yield_gap.py`](../../tools/cash_yield_gap.py) (`drawdown`,
`bear_sweep`, `BEAR_DEPTHS`); tests [`test_cash_yield_gap.py`](../../tests/test_cash_yield_gap.py) (28, 6 new).

## The input I had not admitted to choosing

Round 44 established that the deposit switch — the only income in the repository requiring no borrowing — pays
$5.77/mo through the GFC and $6.66/mo across 2010-2021, against a record mean of $39.85. Every one of those numbers
sat inside a window whose start and end **I typed in**. That is the same class of input that moved round 34's cadence
answer by 11 points, round 38's guarantee by $26/mo, and round 41's QQQ cell by $94/mo. A hand-drawn `2008-08…2009-06`
is a knob, and r37's rule says a figure that moves when you turn a knob gets reported across the knob's range.

So the claim was re-run with no date chosen at all. A **bear month** is one where SPY sits more than *D*% below its
own trailing peak, computed from the return series and nothing else. *D* = 10%, 20%, 30%. Episodes are maximal runs.

## The claim strengthens

| depth | bear months | episodes | switch in bear | switch in calm | per-episode median | range |
|---:|---:|---:|---:|---:|---:|---|
| 10% | 118 | 9 | **+$27.19** | +$45.07 | +$32.54 | −$1.54 … +$95.71 |
| 20% | 65 | 6 | **+$15.68** | +$44.48 | +$11.95 | −$1.60 … +$76.18 |
| 30% | 28 | 3 | **+$12.87** | +$41.86 | +$19.32 | +$1.91 … +$30.08 |

**Pay falls monotonically with drawdown depth at every threshold, and nothing was tuned to produce that.** Calm-month
pay barely moves ($45.07 → $41.86), so this is the bear months getting worse, not the calm ones getting redefined —
which is the right check, since deepening the threshold necessarily removes months from the calm set.

## And a second thing appears that the hand-drawn table could not show

Month-weighted, a crisis pays **$27.19**. Episode-weighted, the same nine episodes average **$32.54**. Both correct,
from the same months, and they differ because **a two-month episode paying $95.71 and a 32-month episode paying
$3.95 are each "one crisis."** There is no fact of the matter about what a crisis pays; there is only what the
months inside these episodes paid, and how much weight each is given. Reporting one number would have been reporting
the weighting choice while hiding it, which is r42's lesson in a new costume — there the hidden input was the start
stride, here it is the unit of observation.

## The episodes, and what the rate did inside each

| episode | months | index | pay | bill rate | path |
|---|---:|---:|---:|---|---|
| 1998-08 | 1 | −14.1% | +$80.41 | 4.93% → 4.93% | flat |
| 2000-11…12 | 2 | −7.9% | +$95.71 | 6.19% → 5.52% | easing |
| 2001-02…2005-12 | 59 | −1.5% | +$32.54 | 4.43% → 3.89% | easing |
| 2008-01…03 | 3 | −9.3% | +$32.28 | 2.85% → 1.24% | easing |
| **2008-06…2011-01** | **32** | −2.5% | **+$3.95** | 1.87% → 0.14% | easing |
| **2011-08…12** | 5 | −1.8% | **−$1.54** | 0.03% → 0.01% | flat |
| 2018-12 | 1 | −8.8% | +$34.08 | 2.15% → 2.15% | flat |
| 2020-03 | 1 | −12.5% | +$4.22 | 0.36% → 0.36% | flat |
| **2022-04…2023-05** | **14** | −5.9% | **+$54.51** | 0.71% → 5.41% | **tightening** |

The last row is the one that keeps the mechanism honest: **during a 14-month drawdown the switch paid above its own
record average, because the bill rate was being raised from 0.71% to 5.41%.** If the story were "crises pay badly,"
2022 would refute it. The story is "the switch earns the policy rate," and the pay deficit inside drawdowns is a
consequence of central banks easing into them — which they do, on average, but not as a law, and the 2022 episode is
the exception running at $54.51/mo against a $39.85 mean.

So the two statements that survive are narrower than round 44's phrasing and harder:

1. **Inside drawdowns the switch pays less, monotonically in depth, date-free** — because easing is the common
   response, not because falling prices reduce a bill ladder's yield.
2. **What a crisis pays is not a single number** — the month-weighted and episode-weighted answers differ by $5.35/mo
   on the same nine episodes, so the weighting belongs in the open.

For the goal, this closes the last romantic reading of the switch: it is a **position on the front end of the curve**
wearing an income's clothes, and it is worth owning for the same reason any cash-management choice is worth owning —
it beats the alternative at the same risk — and not for hedging the equity sleeve it sits next to.

## Checks

28 tests in this file, 6 new, 1.0 s, offline: the pay-depth relation must be monotone at all three depths and bear
must sit below calm at each; the month counts must nest, so the sweep is one story rather than three; the two
weightings must **disagree**, and the episode range must still contain a negative episode (if they ever converge the
caveat gets deleted rather than carried); the 2022-04 episode must exist, be classified `tightening`, pay above the
record mean, and have a negative index return — the counterexample is pinned so the mechanism cannot degrade into
"crises pay badly"; `drawdown` must see the archive's ~−52% trough, return nothing for an empty series, and produce
**no** negative values for a rising one; and doubling the balance must double every dollar while changing no month
or episode count. Full suite: **1568 passed, 233 subtests** (collection matched the prediction of 1568, and the run
confirmed it). `journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
