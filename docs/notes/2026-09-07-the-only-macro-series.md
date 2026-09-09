# The only macro variable in the archive, tested: it costs growth and buys drawdown, and the trend rule's win is era-specific

Measured 2026-09-07, round 59. Tool: [`rates_gate.py`](../../tools/rates_gate.py) (new). Tests: 13 in
[`test_rates_gate.py`](../../tests/test_rates_gate.py).

The objective's plan is to read "trading and global news". The archive contains exactly one macro series: the daily
DGS3MO factor already used as the bill leg. It is not news, but it is the closest offline proxy the lab has, and it is
the variable a person actually faces when choosing between equities and waiting. Its record here runs **0.011% to
6.89% annualised, now 3.87%**, so the regimes are not hypothetical. Four gates, pre-declared, monthly, decided on the
previous month's yield and applied to the next month's return.

## All seven legs, $100k, 10-year plan, 5% failure budget, monthly convention

| leg | months | CAGR | max DD | ends whole $/mo | never zero $/mo | P(fail) at $435.47/mo |
|---|---:|---:|---:|---:|---:|---:|
| SPY hold | 402 | **10.84%** | 50.8% | **$0.00** | $763.82 | 20% |
| MA200 monthly | 402 | 10.50% | 21.6% | **$557.91** | **$1,098.43** | **0%** |
| `yield_gate` | 366 | 7.53% | 48.9% | $0.00 | $769.39 | **49%** |
| `carry_flip` | 390 | 6.23% | 23.2% | $300.15 | $964.98 | 28% |
| `tightening_exit` | 396 | 10.25% | 50.8% | $0.00 | $803.97 | 23% |
| `ma200_and_gate` | 366 | 7.95% | **16.2%** | $332.75 | $974.33 | 18% |
| static 60/40 | 402 | 7.73% | 33.5% | $68.39 | $853.86 | 43% |

The gates fire, so nothing below is an artefact of an inert switch: `yield_gate` was risk-on in 207 of 367 signalled
months (56%), `carry_flip` in 149 of 391 (38%), `tightening_exit` in 359 of 397 — it fires *off* only 10% of the time,
which is exactly why its max drawdown is identical to the index's 50.8% and its CAGR only 0.6pp lower.

**No rates gate beats the trend rule at the same payout, and the most natural one is worse than doing nothing.**
`yield_gate` — hold equities only while cash pays less than its own 3-year average, the plain "easy money" story —
fails 49% of the time at the index's own $435.47/mo, against the index's 20%. It gives up 3.3pp of CAGR, cuts the
drawdown by less than 2pp, and cannot meet the "ends whole" promise at any withdrawal, exactly like the index it was
supposed to protect. The mechanism is visible in the era table below: in the high-rate 1990s the gate was off or
flipping through the best years, and it fails **72%** of windows started 1993-2004 against the index's 47%.

**The macro filter subtracts from the price filter.** Combining MA200 and the yield gate (risk-off if *either* says
so) pays $332.75/mo where MA200 alone pays $557.91, and fails 18% of the time where MA200 alone fails 0%. What it does
buy is the **lowest maximum drawdown in the repository, 16.2%** — so the macro overlay is a risk reducer that a person
could reach more cheaply by holding bills, not an information advantage. That is the fifth consecutive round in which
the risk benefit of a signal has been reproduced, more cheaply, by allocation.

## The era split, which is the round's real business

Failure rate at a fixed $435/mo over a **5-year** plan (a 10-year plan leaves only a handful of windows in the newest
era), grouped by the decade the window starts in:

| leg | 1993-2004 | 2005-2015 | 2016-now |
|---|---:|---:|---:|
| SPY hold | 47% (n=142) | 32% (n=132) | **0%** (n=69) |
| MA200 monthly | **11%** | **8%** | **17%** |
| `yield_gate` | 72% (n=142) | 25% | 0% (n=33) |
| `carry_flip` | 54% | 31% | 33% (n=57) |
| `tightening_exit` | 52% | 27% | 0% (n=63) |
| `ma200_and_gate` | 32% | 23% | 18% (n=33) |
| static 60/40 | 51% | 35% | **0%** (n=69) |

The trend rule beats the index by 36pp and 24pp in the two older eras and **loses by 17pp in the newest one**, where
the index fails no windows at all. This is the same sign flip round 55 found in the timing rules and round 56 in the
rotation, now measured on round 58's *income* metric rather than on a growth rate: **MA200's +36% income advantage
over the index is a property of the decades it happens to include.** The sample sizes differ across the rows (the
gates start later, having waited for their own warm-up) and the counts are printed for that reason.

## Convention, measured rather than disclaimed

This file charges expense monthly; the round 56-58 panel engine charges it daily. On the same sleeve over the same
247 months the difference is **0.027pp of CAGR** (11.1201% against 11.1475%) and **$6.38 a month of safe income**
($441.85 against $435.47, 1.5%). Both are asserted, so the number this note quotes cannot quietly belong to whichever
engine flattered it.

## What this says about the objective

The "global news" half of the plan, operationalised with the only macro series the lab owns, **loses to the price
signal it would be combined with, and loses to the index it would be used to protect**. It is not a small or
underpowered negative either: 403 months, four pre-declared constructions, and the best of them adds nothing while
halving a drawdown that bills already halve. Rounds 55, 56, 57, 58 and 59 now agree from four different directions —
price timing, cross-sectional ranking, trading frequency, and macro conditioning — that the model's edge on this
archive is small, era-dependent, and cheaper to obtain by allocating than by forecasting.

## Checks

13 tests, 4.6 s, offline: the yield series must contain both a near-zero and a above-5% regime, or the gate has only
one regime to learn from; every gate must be on between 5% and 95% of its signalled months, so a stuck switch fails
rather than surviving as a "result"; the gate must be off in December 2023 (5.2% cash) and on in December 2021
(0.06%); no gate may exist before its own warm-up; the combined gate must be the element-wise `min` of its parts and
strictly less invested than either; the monthly and daily conventions must agree within 0.1pp and the fixed payout
within $15 of the figure round 58's engine produces; no rates gate may match MA200's failure rate at the fixed
payout; the combined gate must price *below* MA200 alone and must hold the lowest drawdown; and MA200 must beat the
index in the two older eras and **lose** in the newest, with at least 30 windows behind the newest era's conclusion.
Full suite **1728 passed** (collected first: 1715 + 13). `journalctl verify`: chain intact, comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
