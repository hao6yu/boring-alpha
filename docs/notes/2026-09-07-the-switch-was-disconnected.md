# Rotation priced against a control that thinks nothing: the ranking was fine, the switch was disconnected

Measured 2026-09-07, round 56. Tool: [`rotation_edge.py`](../../tools/rotation_edge.py) (new). Tests: 13 in
[`test_rotation_edge.py`](../../tests/test_rotation_edge.py).

Round 55 killed single-asset timing after 2010. This round tests the other short-term family — the one that never
predicts the market, it just holds whichever sleeve has been strongest. Ten sleeves, common window **2006-02-07 to
2026-09-04** (5,177 days; the window is set by DBC, the thinnest sleeve), month-end signals held one month, turnover
0.0002 one-way, four pre-declared rules and three comparators.

## A units error that left every headline number correct

The first version ranked sleeves by `compound(...)` — a **growth factor** — and compared that factor against
`compound(...) − 1` for the bill yield, a **net return**. Ranking is monotone under subtracting one, so every
CAGR, every drawdown, every comparison in the table below is *unaffected*. What was affected is the only place the
two quantities meet: `dual_top1`'s absolute overlay asked "did the best sleeve beat cash?" as "is 0.64 bigger than
0.014?" — **always yes**. The overlay never fired, across 235 signals, in a window containing 2008.

Symptom: `dual_top1` and `rs_top1` printed identical numbers in every era and every cost block. Diagnosed by
listing the signals that fired (zero), then printing the crisis months — which displayed IWM at "+66.5%" in December
2008, because 0.665 was being read as a return. The panel itself was correct: SPY's own slice compounded to 0.6376,
exactly −36.24%, matching its closes ratio to twelve places.

After the fix, `dual_top1` goes to cash in December 2008 and its maximum drawdown halves. **An overlay that never
fires is not evidence of safety; it is evidence the switch is disconnected.** This is the second time in three rounds
that a component had to be shown to *move* before its effect meant anything (r53 said it of a rebalancing band).

## The results, unposted expenses at 0.35%

| rule | exposure | trades | CAGR | max DD | cost/yr | vs SPY hold | vs static 60/40 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rs_top1` | 95% | 49 | 10.72% | **61.7%** | 0.0945% | **−0.43pp** | +2.41pp |
| `rs_top3` | 95% | 78 | 10.54% | 59.5% | 0.0568% | −0.61pp | +2.23pp |
| `dual_top1` | 83% | 50 | 10.19% | **29.3%** | 0.0886% | −0.96pp | +1.88pp |
| `static_60_40` | 95% | 1 | 8.31% | **30.1%** | **0.0010%** | −2.84pp | — |
| **SPY hold** | 100% | 1 | **11.15%** | 55.2% | 0.0010% | — | −2.84pp |
| VOO hold, own record | | | 14.92% | | | 4,020 days from 2010-09-10 | |

**No rotation beats plain SPY.** The ranking rules are not merely unprofitable relative to the bar, they carry *more*
drawdown than it (61.7% against 55.2%) while paying 90bp a year in costs that buy-and-hold does not pay. That is the
worst quadrant available: more risk, less return, higher cost.

The one genuine result belongs to the absolute overlay: `dual_top1` cuts the maximum drawdown from 61.7% to **29.3%**
and its exposure from 95% to 83%, for −0.96pp of return. And the control is what makes that result honest —
**a static 60/40 that computes nothing, trades once a month and pays 0.0010% has a maximum drawdown of 30.1%**, within
0.8pp of the rotation's. The entire risk benefit of the news-and-trend machine is available from a fixed allocation
chosen while asleep, at about an eighth of the cost.

## The expense assumption is not load-bearing

Doubling every unposted sleeve to 0.70% — worse than any fund here has ever cost — moves each rule by **−0.12 to
−0.14pp**, leaves the ordering of all four identical, and leaves all four still behind SPY. So the conclusion is not
the assumption, which was the point of running it twice rather than looking the ratio up and quoting it as if it were
history. (Historical ratios were higher than today's, so both blocks understate the older sample.)

## By era, because round 55 proved that is where the answer lives

| era | days | `rs_top1` | `rs_top3` | `dual_top1` | `static_60_40` | SPY hold |
|---|---:|---:|---:|---:|---:|---:|
| 2006-2009 | 982 | +2.41% | −0.53% | **+6.47%** | +1.17% | **−1.00%** |
| 2010-2019 | 2,516 | 10.36% | 12.19% | 8.41% | 11.51% | **13.35%** |
| 2020-now | 1,678 | **16.44%** | 14.99% | 15.21% | 7.90% | 15.49% |

Every rule beats SPY in the crisis and every rule loses in the decade that follows it — `dual_top1` by **4.94pp** in
2010-2019, having made its name in 2008. The pattern is the same one round 55 found in MA200: these are
crisis-exit devices, they pay for the exit in the longest bull market on record, and the whole-window average is the
sum of those two facts, not a description of either. Only `rs_top1` beats SPY in the current era, by 0.95pp — the
era that includes 2020, the fastest V-shaped recovery in the record, which is exactly the shape a one-month-lagging
relative-strength rule is built to catch.

## What this says about the objective

The bar named is VOO at **14.92%** over its own record, which is not a ticker effect: SPY itself made 13.35% in
2010-2019 and 15.49% since 2020 on this same panel. Against that, the two families of rule a person can actually run
from a laptop — timing one asset (round 55) and ranking many (this one) — both land at or below holding the index,
and the better risk record either of them produced is reproduced by a fixed 60/40 with no information at all.

## Checks

13 tests, 1.1 s, offline: every sleeve's panel return must match its own closes ratio on its own calendar to 12
places; the common window may not start on any sleeve's first day (`index − 1` on day zero is the last element, not
a missing value); the bill leg must be the same daily factor the rest of the repository compounds; **a single-day
run over the signal day must return exactly `1 + bill` (0.0199% on 2007-02-28) and not the new position's +1.03%**,
which fails by 80bp if the one-day shift is ever removed; the December-2008 signal must put `dual_top1` in cash and
it must be in cash on more than 100 days; `dual_top1` must cut the drawdown by more than a third and pay return for
it; the four rules must cost more than the control and reorder by less than 0.25pp when expenses double; a sleeve
outside the universe raises rather than becoming an all-cash portfolio. Full suite **1689 passed** (collected first:
1676 + 13). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
