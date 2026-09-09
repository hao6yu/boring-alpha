# Round 2 — where the toll goes, and the first candidate that gets close

> **Table superseded the same day, two rounds later.** The funded simulator's review-cadence
> argument turned out not to bind, so every row below that claims a reviewed policy was priced
> as a band-rebalance rule instead. The correction, the re-measured numbers and the verdict that
> did not move are in [the cadence gate note](2026-09-06-cadence-gate.md). The table is left as
> printed: a revised claim is a record, a rewritten one is nothing.
Date: 2026-09-06. Tools: `tools/overnight_split.py`, `tools/run_voltarget_scan.py --candidate`.
Module: `src/boring_alpha/signals/voltarget.py` (cadence added). Tests: 18 in
`tests/test_voltarget.py`. Bot: `tools/paper.py --model voltarget`.

## The measurement that sets the shape of everything else

Any model that is flat when the market is closed pays a round trip for every night
it wants exposure. Before writing another signal, worth knowing how much those
nights carry and what the toll is. SPY, total-return series, exact decomposition
`close/close(t-1) = (open/close(t-1)) × (close/open)`:

| window | overnight | intraday | held all day |
|---|---:|---:|---:|
| full 1993..2026 | 10.05%/yr (Sharpe 0.96) | 0.76%/yr (0.13) | 10.89%/yr (0.65) |
| seen A | 7.76% | 2.80% | 10.77% |
| seen B | 10.44% | 3.86% | 14.71% |
| recent 2022..2026 | 6.36% (0.64) | 5.67% (0.45) | 12.38% (0.76) |

**The nights are 93% of the compounding over the full archive** — an independent
reproduction of a well-documented regularity, which is also a decent check that the
data plumbing is honest. Two conclusions, and the second matters more:

1. The overnight leg carries far more risk-adjusted return than the intraday leg.
2. **It cannot be collected by trading for it.** A nightly round trip at 0.3 bps a
   leg — roughly what SPY actually costs — is 1.5%/yr of toll, leaving 8.54%/yr
   against 10.89% for simply holding. At a genuinely pessimistic 2 bps it is
   −0.03%/yr. In every window, at every cost level tested, night-only trails just
   holding. And the premium is shrinking: since 2022 the intraday leg has caught up
   (5.67% vs 6.36%), so the recent window is 53% nights, not 93%.

This is not a refutation of short-term trading. It is the arithmetic that says
**the review interval, not the signal, is the binding constraint.** A model that
rebalances daily pays about 1.5%/yr before it has expressed any view at all. That
is more than the entire intraday leg is worth and a third of the way to the
benchmark's whole return.

## Cadence, implemented and tested

`review_every` added to `VolTargetPolicy`: the volatility estimate still updates
daily, but the book only acts on review sessions. On a fixture that genuinely
churns volatility, daily review trades 196 times, weekly 46, fortnightly 30,
monthly 19. The invariant is pinned by test — **no trade ever lands on a
non-review session** — rather than by counting trades, because counting trades
proved nothing: the first version of that test passed vacuously. An alternating
±2% series has *constant* standard deviation, so a volatility target never moves
and every cadence trades exactly once. A fixture that cannot fail is worse than no
test, since it looks like coverage.

## The pre-registered candidate, and the two harness bugs that preceded it

One configuration, fixed before the run, reasoning from the toll above rather than
from any result: weekly review, volatility target 18% on a 30-day window, capped at
1.3×, **floored at 30% rather than zero** — because the previous round's gate lost
money by going all the way to cash and missing the recovery — 200-day trend gate,
10% band. The floor choice is an inference from the previous round's gate, which lost
money while sitting in cash — plausible, and not something I proved. Bar: beat the
comparator in all four windows.

| window | doing nothing | candidate | verdict |
|---|---:|---:|---|
| full 1993..2026 | $1,903,583 | $2,060,505 | **beat +$156,921** |
| seen A | $138,884 | $143,973 | **beat +$5,089** |
| seen B | $45,245 | $44,050 | lose −$1,195 |
| recent 2022..2026 | $52,216 | $51,949 | lose −$268 |

Max drawdown −25.2% against −52.7% full period, −10.8% against −16.1% recently.
241 trades over the full archive; total costs $6,165 on an account that ended
near $2.1m, against $41 for the comparator, which never trades beyond topping up a
contribution.

**Verdict: fails the bar.** Two of four, and it loses in the two windows that say
anything about the future. It is nonetheless the first candidate in this repository
to come within 0.5% of the comparator on dollars while roughly halving the
drawdown, so the risk half of the claim is solid and the return half is not.

Two harness bugs had to die first, both of which flattered it:

- The candidate row passed `band=0` to the simulator, which rebalanced to target
  **every single session** — 8,427 trades for a model specified as a five-session
  review — and charged $7,599 for the privilege. Fixed with an explicit allow-set of
  the sessions the policy decided to trade.
- A 200-day warm-up silently started the candidate ~11 months after the comparator,
  so its paid-in was lower and its window shorter. Fixed by pinning both to the same
  first session; the comparator's own figure is now printed alongside.

## What the bot is doing now

`tools/paper.py --model voltarget` runs this configuration forward on a hash-chained
paper book. On current data it wants **128% of equity in SPY** and the book has
executed that, charging itself 2.1 bps of spread and reporting the fee as 0.51% of
deposits. The skill verdict stays withheld — 22 entries and $4,500 short — while the
cost findings, which need no statistics, are live from entry one.

**The model as specified requires a margin account.** At 1.3× it is borrowing. That
is not incidental: across four mechanisms now — cross-asset trend, multi-horizon
trend, source-sensitivity, single-asset volatility targeting, and the mirror-image
reversal idea killed pre-emptively — **every unlevered configuration tested has lost
to plain dollar-cost averaging on dollars.** The ones that beat it all borrow. The
honest reading is that this archive contains no free lunch and one very expensive
one: leverage delivers the beat, at the price of the drawdowns in the table above.

## The amendment I am not allowed to make yet

Raising the cap from 1.3× to 1.5× would very likely clear seen B and the recent
window too, because the leverage controls beat in all four windows monotonically.
Proposing that now would be selecting a parameter after seeing the result it is
scored on, which is precisely the error that produced BA-004's hollow pass. So:
recorded as an amendment, labelled post-hoc, **to be judged only on forward
months**, not on this archive. The paper book is the instrument for that, and it is
now pointed at the configuration rather than at a baseline nobody believes.
