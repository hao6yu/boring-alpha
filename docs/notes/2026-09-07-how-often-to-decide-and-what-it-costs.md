# How often to decide, and what it costs

Measured 2026-09-07, round 80. New tool: [`cadence_sweep.py`](../../tools/cadence_sweep.py). Engine addition:
`sl.cadence_carry` in [`shelter_long_record.py`](../../tools/shelter_long_record.py). Tests: 16 in
[`test_cadence_sweep.py`](../../tests/test_cadence_sweep.py).

The objective says *short term*. Every rule this repository has tested reads once a month, and round 74 recorded that as a
limitation of the engine rather than a property of the world: "a different cadence … which the monthly engine cannot
represent." It can. This round removed the schedule constraint and held everything else fixed — same MA200, same twelve-month
relative strength, same 50/50 tilt, same 2 bps on purchases, same ten-year windows, same 5% budget, same costs — and, most
importantly, the **same lag**.

## The engine change, and the failure mode it closed

`sl.cadence_carry(dates, marks_by_index, symbols)` expands decisions made on a schedule of any period into daily weights,
holding each one for one full period. It is `sl.carry` generalised off the calendar month, and per round 69 it is not trusted,
it is **differentially tested**: on month-keyed marks it reproduces `carry` day for day, including the case where a scheduled
day declines to answer. Two kinds of "nothing happened on that day" had to be kept distinct, and the distinction is the newest
bug class this repository has had to name:

- `None` — the day arrived and the lookback could not answer. **Hold** the previous weight, exactly as `carry` treats a month
  absent from its marks.
- `{}` — the day arrived and the answer was *sell everything*. **Go flat**, exactly as `carry` treats a present-but-empty mark.

Conflating them lets a missing reading sell the portfolio, which is a worse failure than the lookahead round 75 found because
it looks conservative. The tests pin all four cases on one synthetic series, plus the direct no-lookahead property: on a
decision day and the day after it, the weight in force is still the previous period's.

## The table

Capacity per $100k at a 5% failure budget, both records as the last rounds left them (deep 1999-12-22, recent 2011-06-24):

| plan | schedule | capacity, deep | capacity, recent | switch/yr |
|---|---|---:|---:|---:|
| static 50/50 | no decisions | **none** | $1,101.66 | 0.0 |
| static 100% QQQ | no decisions | **none** | $1,269.14 | 0.0 |
| brake | weekly | $510.09 | $827.98 | 1.8 |
| brake | fortnightly | $481.51 | $768.25 | 1.5 |
| brake | every 21 days | $638.09 | $873.94 | 1.0 |
| brake | two-month | $614.17 | $980.97 | 0.7 |
| brake | quarterly | $307.87 | $899.58 | 0.7 |
| rot12 | weekly | $432.76 | $875.18 | 4.2 |
| rot12 | fortnightly | $456.19 | $1,074.98 | 3.3 |
| rot12 | every 21 days | $479.77 | $1,028.30 | 2.0 |
| rot12 | two-month | $398.43 | $1,060.25 | 1.6 |
| rot12 | quarterly | $136.98 | $1,116.74 | 1.4 |

The two static rows reproduce round 78's numbers to the cent through a different weight construction — constant vectors here,
monthly marks there — which is the differential that makes the rest of the table comparable at all.

## Short term is worse where the risk lives

On the record that contains the tail, **the fastest schedules have the least capacity**: the brake funds $510.09 weekly and
$638.09 every 21 days but only $307.87 quarterly; rot12 funds $432.76 weekly and collapses to $136.98 quarterly. There is no
cadence at which either plan recovers what the static books forgo — every row here meets the 5% budget where no static mix
could, and none of them comes close to the $1,101.66 and $1,269.14 the static books fund on the recent record. Where the
objective wants the trading to happen — fast — is exactly where this family's capacity disappears.

## Five schedules clear the bar. None clears the family it was picked from.

The claim written before the run: a faster schedule is recommendable only if it funds at least $25.00/mo per $100k more than
the same plan read monthly, and doesn't turn a funding record into a non-funding one. **Five of ten schedules pass** — brake
two-month +$107.03, rot12 quarterly +$88.44, brake quarterly +$25.64, rot12 fortnightly +$46.68, rot12 two-month +$31.95 —
and the second clause holds too, since every row here funds something.

They are not findings. The spread between the best and worst schedule of a single plan is **$212.71/mo** (brake) and
**$241.56/mo** (rot12) on the same recent window. Every "gain" above is 12% to 50% of the spread it was selected from, so
round 74's rule applies to the axis this file invented rather than only to the rules it inherited: **a winner chosen out of
five schedules is a five-way guess with a story attached, and here not even one winner clears its own family spread.**

## The detail that ends the argument

The same brake signal, read on exactly the same twenty-one-day rhythm, funded **$939.89/mo recent and $458.06/mo deep** in
round 78 when its readings were anchored to the **calendar month**, against **$873.94 and $638.09** here when anchored to every
21st trading day. Anchoring — which day the schedule happens to start on, a choice with no economic content whatsoever — moves
capacity by **$65.95/mo** on the recent window and **$180.03/mo** on the deep one. That is two to eight times larger than every
schedule effect in the table, and it points the wrong way on each record.

So the honest reading is not "monthly is best". It is that **on this archive, cadence is noise**: the thing a cadence sweep
measures is smaller than the arbitrary choices that define the sweep. Anyone who trades weekly versus quarterly because a backtest
said which is better is trading anchoring.

## What this closes

- Round 74's caveat — that other cadences could not be represented — is closed, and closed negatively: no schedule beats the
  monthly reading of the same signal by more than its own family spread, and none comes near the static books.
- The objective's "short term" is now priced on the only axis daily closes can price it on. What remains of it — intraday,
  spread-aware, news-informed — is refused by [`decision_sheet.py`](../../decision_sheet.py) with the missing data named, and
  no sweep of this archive's files changes that.
- Six families now, each with its own control and costs charged: rules (r74), rotations (r75), brakes (r76), payout levels
  (r77), mixes (r78), **schedules (r80)**. All six say the same thing: the static growth tilt is what funds the withdrawal,
  and the decisions are a cost centre.

## Checks

16 tests, 7.6 s, offline: `cadence_carry` equal to `carry` on month-keyed marks including declined months; declined ≠ flat
pinned on one series with all four cases; nothing held before the first decision; a reading never trades on its own day or the
day after; the static rows differential-tested against `mix_sweep.py`; the calendar comparator read from `mix_sweep.py` rather
than typed, with the anchoring claim asserted true rather than merely printed; spreads recomputed from the family; switches
rising as cadence rises; weights never exceeding the book and every brake actually reaching flat; warmup holding nothing for
both lookbacks; `decision_days`, `moving_average`, and `mark_at` on synthetic series; `pass_spread == 0` pinned so the
conclusion cannot quietly change in a refactor. Suite: **2037 passed** (collected first: 2021 + 16); ledger chain intact.
