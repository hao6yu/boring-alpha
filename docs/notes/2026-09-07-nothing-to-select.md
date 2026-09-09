# Twenty-eight things were tried. Every one of them has a negative information ratio, so there is no winner's curse to correct for

Measured 2026-09-07, round 61. Tool: [`deflated_edge.py`](../../tools/deflated_edge.py) (new). Tests: 19 in
[`test_deflated_edge.py`](../../tests/test_deflated_edge.py).

Rounds 55 to 60 evaluated **28 pre-declared configurations** — price timing (6), cross-sectional ranking (4), signal
× frequency (12), macro conditioning (6) — and each round reported a winner. Reporting a winner after trying 28
things is exactly how a backtest lies, and not one round checked whether the pattern could have come out of noise.
This round does, on the strategies *as they were tested*: same legs, same costs, one common grid
(2006-03 → 2026-08, **246 months**, 27 distinct monthly paths — `r56:dual_top1` and `r57:mom_top1@monthly` realise the
identical one). Two statistics: the **Deflated Sharpe Ratio** (best-of-N threshold from Bailey & López de Prado,
consuming each series' own skew and kurtosis) and a **block-bootstrap Reality Check** (2000 draws, circular blocks of
12 months, all 26 columns resampled on a shared index so cross-strategy correlation survives).

## The calibration comes first, because a screening tool that can only say "nothing" has not been tested

| field | 120 months | 246 months |
|---|---:|---:|
| 26 columns of seeded pure noise | p = 0.962 | p = 0.635 |
| same field, one column planted with a real +1.2%/mo edge | p = 0.015 | p = 0.000 |

The planted edge is attributed to the right column in every case. So the machinery calls noise noise and finds an
edge when one exists — which is what gives the archive result below any standing.

## Two nulls, and only one of them is the question

**Raw returns.** Best of the set: `r59:MA200 monthly` at Sharpe **0.95** against a best-of-27 threshold of 0.63,
Deflated Sharpe 0.916, Reality-Check **p = 0.000**. Read plainly that says the set contains something real. It does
not: the panel is long equity for every one of its 246 months, so the test measured the **equity premium**, which the
benchmark column earns too (Sharpe 0.78) and which is available for 0.03% a year in a shell. My first version of this
file reported that number as the finding. It was the same mistake as a fund claiming a 0.9 Sharpe while being an
unmodified index clone, and it is worth writing down because it is the most common way a quant result flatters itself.

**Excess over the index** — compounded relative to the benchmark, the benchmark's own column dropped, and
`r55:hold` dropped as a benchmark duplicate (same position in a different convention, mean gap **−0.09pp a year**,
which is round 59's convention measurement appearing from a second direction):

| | |
|---|---|
| columns scored | 26 (25 distinct paths, 246 months) |
| best information ratio | `r56:rs_top1` at **−0.01** annualised (−0.0037 per month) |
| its Deflated Sharpe | **0.002** |
| Reality-Check p of that best | **0.981** (null median max t 1.35, p95 5.85) |
| configurations with a positive information ratio | **0 of 26** |

The best of the set is `r56:rs_top1`, at −0.01. The bottom of it is `r59:yield_gate` at −0.43 and
`r57:mom_top1@annual` at −0.40. Nothing is above zero, so the multiplicity correction has nothing to bite on: **the
search did not fail to find an edge at this resolution; there is no candidate to be suspicious about.** Where
Deflated Sharpe and the Reality Check disagree in spirit, the Reality Check governs — DSR assumes the 28 trials were
independent, and 28 long-equity legs are about as far from independent as a set can be.

## What this does not say

It tests **mean excess return** and nothing else. Two findings from earlier rounds are not addressed by it and remain
standing, because they are not claims about mean excess return:

* **round 58's income advantage** — the trend leg supported 36% more monthly withdrawal at the same failure budget,
  on the *withdrawal* metric, which is a statement about the shape of the path, not its average slope.
* **round 60's tail result** — 4.2% of 10-year windows on the long record left a plain-equity contributor with less
  than they deposited; the trend rule has no such window.

A rule can lose on mean excess and still be worth owning for the shape. What round 61 establishes is that it cannot
be sold as "beating VOO", because on this archive, net, it does not — and that the six rounds of negative results were
not a broken search. They are consistent with an empty null.

## Three things this round caught in its own machinery

1. **The observed statistic was first computed on centred series**, which makes it identically zero and every p-value
   identically 1.000. Nothing in the output looked wrong — a screening tool returning "nothing" is the shape of its
   normal output. The planted-edge calibration is what caught it, which is the entire reason that calibration exists.
2. **One merged month-map for all 28 columns.** Two legs share every month key, so the last writer won and all 26
   columns would have held the same series. A guard now raises on that, and it then correctly fired on a *genuine*
   tie (`dual_top1` and `mom_top1@monthly` realise the same path) — which was multiplicity to count, not a bug to
   raise on, so the threshold is set by the number of distinct paths (27 of 28) while every label is still shown.
3. **A daily rule replayed to month ends must compound to what the engine reports.** `trend_cost_test.run` returns
   aggregates, so this file replays its arithmetic; the replay is pinned to it to eight places for all six rules, and
   got the array lengths wrong twice before it was right.

## Checks

19 tests, 4.4 s, offline: `phi`/`inv_phi` at the usual quantiles and round-tripped, refusing the tails it cannot
represent; the best-of-N bar monotone in trials and in sample length, and exactly 0.0 for a single trial (one trial is
no selection to price); hand-computed skew and excess kurtosis for `[1,1,1,2]` (1.1547, −0.6667); a flat series raising
rather than returning an infinite Sharpe; noise not significant at 120 and 246 months; a planted edge detected at both
lengths and attributed to the planted column; the null's median maximum rising with the number of columns; the seed
reproducing its own answer; ragged panels refused; the monthly replay matching `trend_cost_test.run` for all six
rules; no aliasing among the columns beyond two reported duplicates; the benchmark's own excess exactly zero; and **no
configuration having a positive information ratio**, which is the finding itself, so that a future change which
produces one has to say so out loud. Full suite **1758 passed** (collected first: 1739 + 19). `journalctl verify`:
chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
