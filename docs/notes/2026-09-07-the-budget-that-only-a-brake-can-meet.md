# The budget that only a brake can meet

Measured 2026-09-07, round 78. New tool: [`mix_sweep.py`](../../tools/mix_sweep.py). Tests: 14 in
[`test_mix_sweep.py`](../../tests/test_mix_sweep.py).

Round 77 found plain QQQ beating the diversified blend on capacity *and* on failure probability on both windows it used, and
recorded the reason not to believe it: the calendar every recent round has shared begins **2005-09-06**, set by the youngest
leg of a five-asset pool plus a 200-day warmup, so the growth index's own collapse — 2000 to 2002, −82% — sits inside none of
the 132 or 63 windows that produced those numbers. A tail that is never sampled cannot appear in a failure probability. This
round moved the sample rather than the hypothesis, and the answer moved with it.

The record now starts **1999-12-22**, which is QQQ's first trading day plus the engine's own 200-day warmup: the earliest date
on which this two-fund family can be scored at all, printed rather than chosen, and earlier than round 73's long window
(2002-08-01) as well. It contains the dot-com unwind, 2008, 2020 and 2022. Nothing in this grid holds a shelter — the brake
parks in cash on the bill curve, so no shelter's warmup shortens the tail being tested, and that choice is on every row rather
than in a footnote (`dm12_sq` is absent from this grid for exactly that reason; round 77 prices it). One shared dollar scale:
**$1,101.66/mo per $100,000**, the 50/50 control's own capacity on the recent window, used unchanged in both tables so only the
history moves.

| row | QQQ | capacity, deep | fails ≥ $1/mo? | 1.00x deep | worst DD, deep | capacity, recent | 1.00x recent |
|---|---:|---:|---:|---:|---:|---:|---:|
| mix_00 (plain SPY) | 0% | **none** | 5.5% | 84.6% | −55.2% | $919.02 | 69.8% |
| mix_25 | 25% | **none** | 5.5% | 68.7% | −59.3% | $1,010.70 | 41.3% |
| mix_50 (control) | 50% | **none** | 6.0% | 54.7% | −69.0% | $1,101.66 | 4.8% |
| mix_75 | 75% | **none** | 6.5% | 52.2% | −76.8% | $1,186.87 | 0.0% |
| mix_100 (plain QQQ) | 100% | **none** | 7.0% | 51.7% | **−83.0%** | $1,269.14 | 0.0% |
| brake_50 (cash brake) | 50% | **$458.06** | 0.0% | 86.6% | −30.9% | $939.89 | 58.7% |
| brake_75 (cash brake) | 75% | **$466.68** | 0.0% | 75.6% | −30.8% | $1,020.00 | 33.3% |

## Nothing static clears the budget once the sample is honest

**Zero of five static mixes meet a 5% failure budget at any payout on the deep record.** Not "barely": the withdrawal is
pushed down to **one dollar a month** and they still fail on 5.5% to 7.0% of ten-year windows, which means the budget is
unreachable rather than tight. And the failure rate at $1/mo **rises monotonically with the growth weight** — 5.5, 5.5, 6.0,
6.5, 7.0 — with a worst drawdown that walks from −55.2% to −83.0%. So the tilt's entire capacity premium on the last fifteen
years (+$350.12/mo of capacity for all-QQQ over all-SPY, round 77) is payment for exactly the risk that the 2005 calendar was
structurally unable to sample. Rounds 75, 76 and 77 are not wrong; they are conditional on a benign start date, and this file
is the boundary of that conditionality.

## The first construction the risk measure *requires*

For 77 rounds every risk-reducing overlay was optional — it cost capacity and bought a benefit the measure scored at zero.
Here the ranking inverts completely: **the only two rows on the page that can fund the record at all are the braked ones**, at
$458.06 and $466.68 per month, with worst drawdowns of −30.9% and −30.8% instead of −83%. A monthly cash brake is the difference
between "no payout meets a 5% budget" and "this book funds $458/mo".

It is still expensive, and the table does not hide that: $458.06 is **0.42x** of the withdrawal the recent window supports, and
at that withdrawal the brake fails on 86.6% of deep windows where the unbraked blend fails on 54.7% — because at $1,101/mo
everything fails, and the brake has less return to rescue it. The brake buys the *existence* of capacity on the long record by
giving up most of it on the recent one. That is the same trade round 76 measured, now visible at the level where the measure
notices.

## What did not move

The recent window reproduces the published numbers to the cent through a different tool and a different calendar: plain SPY
$919.02, the blend $1,101.66, plain QQQ $1,269.14 — asserted against `binding_payout.py`'s own rows rather than typed in. On
the recent window the mix ladder is monotone in capacity ($919 → $1,269) and nearly flat in sampled drawdown (−33.7% →
−35.2%), which is why fifteen years of data would tell anyone to hold growth. The deep record says the same ladder ends at
−83% with no capacity at either rung.

## The objective, restated at the boundary

Two positions are now defensible from this archive, and no construction in it is both:

- **Withdraw well inside what the book funds, over a horizon like the last fifteen years** → capacity is the only thing that
  binds, the growth tilt dominates the index on it, the failure probability of every candidate is zero, and a bot has to beat
  the tilt rather than the index. Nothing tested here — rounds 61, 72, 74, 75, 76 — beats a static tilt on that measure.
- **Require a 5% failure budget over the whole record this family can score** → only a brake qualifies, funding $458–$467/mo
  per $100k, about 0.42x of the recent-window answer, and the honest description of that is insurance, not income.

The gap between the two — roughly 2.4x in capacity — *is* the price of the budget, and that number, not another moving
average, is what the last four rounds produced. Which position to take is a question about a horizon and a withdrawal, not
about the data; the data has now said everything it can on daily closes at monthly cadence.

## Checks

14 tests, 5.6 s, offline: the start date is recomputed from the archive's own warmup limit, not typed; the −82% episode is
asserted to be *inside* the window (a grid that quietly tested the wrong decade fails here); the drawdown helper is pinned on
a synthetic path; every static mix is asserted to miss the budget and both braked rows to meet it; the $1/mo failure rate is
asserted monotone in the growth weight; the recent-window capacities are differential-tested against `binding_payout.py`; no
mark is issued when one sleeve is silent; weights never exceed the book and the brake is asserted to reach cash; the verdict
string is checked to contain the cell's own numbers. Suite: **2005 passed** (collected first: 1991 + 14); ledger chain intact.

**Next.** The repository now has four tools that disagree in informative ways and no single page that states what to do about
it. Round 79 should stop widening the evidence and make it decidable: a generated decision sheet, in the spirit of round 71's
rule, that reads these tools, prints only numbers they measured, states both positions with their prices, and refuses requests
the archive cannot support.
