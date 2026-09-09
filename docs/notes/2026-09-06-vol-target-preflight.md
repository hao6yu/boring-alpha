# BA-005 preflight — volatility targeting, and what actually buys the beat

Date: 2026-09-06. Status: **fails the money bar. No charter drafted.**
Scan: `tools/run_voltarget_scan.py`. Module: `src/boring_alpha/signals/voltarget.py`.
Tests: `tests/test_voltarget.py` (14, including a look-ahead negative control).

## Why this candidate

The three failed strategies share a shape: rank eight sleeves, hold the winners,
rebalance monthly. All three died on cost — BA-001's own review puts its drag at
15.7 bps/yr against the benchmark's 5.7 — while their *direction* was supported by
the data. So the constraint is turnover, not signal family, and the cheapest way to
respect that constraint is to stop choosing between assets and instead vary *how
much* of one asset to hold. Volatility targeting does exactly that, it needs no
forecast, and volatility clustering is the most durable regularity in the data.

It was worth a day. It is also different enough from the failed family that a
positive result would have been new information rather than a fifth swing at the
same idea.

## Result: it reduces risk and does not make more money

$5,000 plus $500/month, SPY, 2 bps per unit of turnover, 9.45 bps expense ratio,
borrowing at the archive's cash index plus 150 bps, margin forced to 1× below a 30%
equity cushion. Comparator is plain dollar-cost averaging into the same fund on the
same schedule.

| window | doing nothing | best of 24 configs | verdict |
|---|---:|---:|---|
| full 1993..2026 | $1,938,442 | $1,855,020 | lose $83,422 |
| seen A 2007-06..2017-12 | $140,075 | $145,769 | beat $5,694 |
| seen B 2018..2021 | $46,045 | $42,906 | lose $3,139 |
| recent 2022..2026 | $52,370 | $50,682 | **lose $1,688** |

Every grid configuration loses in the recent window — the only window that says
anything about what this would do next. Seen A's small win was produced by the
largest leverage in the grid, not by the volatility rule; and the best of 24
selected on the same data it is scored on, so even that $5,694 is optimistic.

**The cleanest cut through the grid:** of the twelve configurations capped at 1× —
volatility targeting with no borrowing at all, both targets, all three windows
sizes, gate on and off — **none beat doing nothing in any of the four windows.**
Zero of twelve, every window, worst to best spanning −$10,785 to −$33,540 in seen A
alone. Every winning row in the grid carries the 1.5× cap. So the volatility rule
added nothing to the dollar outcome anywhere it was tested; the borrowing did all
of the work, and the risk reduction is real but is not the objective.

The risk result is genuine and consistent: max drawdown −33.6% against −52.8% over
the full period, −14.0% against −16.1% recently, with the trend gate taking it to
−7.5% in the recent window. If the objective were "sleep better", this is a real
finding. The objective is dollars, and on dollars it is Redundant.

## The bug that made it look like +$10.2 million

This is the most useful thing in the note.

Before the look-ahead fix, the best configuration reported **$12.1m against the
comparator's $1.9m over the same 33 years — a 18.6% IRR, 699 trades, and a max
drawdown of −13% including 2008 and 2020.** The line responsible:

```python
if average is not None and closes[position] < average * 0.99:   # WRONG
```

The weight applied to day *t*'s return was being decided using day *t*'s closing
price. The volatility half was correctly lagged, which is why nothing else looked
strange. One symbol, and a strategy that loses $83k becomes one that makes eleven
times the money you put in. There is now a test with the corresponding negative
control (`test_yesterdays_close_still_can`) so that a future refactor cannot
quietly reintroduce it and pass.

A separate earlier bug was worse in kind: the funded simulator debited nothing for a
buy, so every purchase created equity from nothing. On flat prices and zero interest
it turned $10,500 of contributions into $2.85m. The flat-price fixture is now part
of how this sim is trusted.

## The control that did beat the index, and why it is not the answer

Constant leverage, no signal at all, priced at cash + 150 bps:

| exposure | full 1993..2026 | recent 2022..2026 | max drawdown |
|---|---:|---:|---:|
| 1.25× | +$480,447 | +$2,667 | −62.5% / −19.8% |
| 1.5× | +$1,224,288 | +$6,643 | −69.1% / −25.3% |
| 2.0× | +$2,812,443 | +$14,106 | −79.7% / −33.5% |
| 3.0× | +$5,104,452 (8 margin calls) | +$27,357 (2 calls) | −93.8% / −47.8% |

It wins in every window, monotonically, with nothing in it but borrowing. That is
not a discovery about markets, it is the definition of levered exposure to a rising
asset, and it says the uncomfortable thing clearly: **at this account size, the
reliable way to beat VOO in dollars is to buy more VOO with borrowed money, which
is a risk decision, not an edge.** The 3× row survives only because a $500 monthly
contribution keeps topping up the cushion; strip that out and it is a margin call
with a funding plan attached. Above about 1.5× I would not put a number on it at
all.

1.25× to 1.5× is where this is worth taking seriously, and it is the one finding
here that would survive being argued with.

## Where this leaves the objective

Three things now look established rather than guessed:

1. **Instrument choice dominates.** $90,298 of spread across eight funds on $68,000
   paid in, versus $8,815 for the entire leakage bundle and $5,694 for a tuned
   volatility rule.
2. **Risk timing is cheap and real; return timing is not.** The gate halves
   drawdown every time it is tested and loses money every time it is tested.
3. **Dollars above the index, at this size, come from leverage or from a signal
   nobody has found here yet.** Three families and two diagnostics have not found it.

The infrastructure this preflight produced is worth keeping and is what makes the
next attempt cheaper: a daily funded simulator with deposits, a comparator, a
margin rule, and a no-look-ahead test harness. Everything up to now was monthly.
Daily is the shortest horizon the archive supports — no intraday bars, no order
book, no news feed — so a short-term model is testable at 1-to-20-day holding
periods and not below that.
