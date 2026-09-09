# Round 14 — the door round 13 left open, priced (`tools/accuracy_bar.py --cadence`)

Round 13 ended on a promise it did not test: *"the same arithmetic does say the bar falls as a rule
makes more, smaller bets … the reason to keep the fast door open rather than shut."* That sentence is
the only thing in thirteen rounds that argued *for* the goal's own instinct — short-term trading — so it
deserved to be priced rather than admired. A bar that falls and a skill that falls with it is not a
wider door, and only one of the two numbers is attached to money.

`--cadence` moves the review frequency and nothing else. Every lookback stays in **sessions**, so a
200-session trend filter is asked the same question on the same Tuesday whether the clock between
decisions is one session or five: what changes is how fast it finds out, how many runs that cuts the book
into, and how often the toll is paid. Deposits, the drag on the fund leg, and the switch charge are
re-derived per bar width; the run-affine composition, the inversion and the four controls are untouched.

Run: `.venv/bin/python tools/accuracy_bar.py --cadence 1 --reps 120` (a daily grid costs about five times
a weekly one, ~2 minutes a sleeve). Pre-registered before the grid, in this order: **if** the daily bar is
not meaningfully below the weekly one, the door was never open; **if** it is, then the gap, not the bar,
decides — and the test file pins the bar falling (`test_a_faster_review_really_does_lower_the_bar`) so a
future edit cannot quietly lose the effect by claiming cadence does nothing.

## Result 1 — the bar falls by two points and the skill falls by more

SPY, full window, 2 bps one-way, 120 shadow draws. `gap` is skill minus bar, as everywhere in this note.

| rule | runs, weekly → daily | bar | gap | $/mo, weekly → daily | Δ$ |
|---|---|---|---|---|---|
| 200-session trend | 107 → 215 | 70.1% → 68.3% (−1.8 pp) | −11.3 → −9.9 pp | −465 → −448 | **+17** |
| 126-session trend | 157 → 347 | 68.5% → 65.8% (−2.7 pp) | −10.7 → −15.5 pp | −502 → −763 | −262 |
| 50-session trend | 267 → 587 | 65.0% → 63.1% (−1.9 pp) | −11.2 → −15.2 pp | −647 → −868 | −221 |
| dual MA 50/200 | 31 → 31 | 73.3% → 73.1% (−0.2 pp) | −6.2 → −6.6 pp | −225 → −240 | −15 |
| 4-week momentum | 353 → 805 | 63.0% → 61.3% (−1.8 pp) | −12.1 → −9.7 pp | −736 → −764 | −29 |
| 13-week momentum | 157 → 377 | 68.4% → 64.7% (−3.7 pp) | −12.1 → −15.0 pp | −540 → −763 | −223 |
| 52-week momentum | 37 → 85 | 77.2% → 74.5% (−2.6 pp) | −11.5 → −14.1 pp | −336 → −434 | −97 |
| coin flip ×25 | 844 → 4,228 | 58.1% → 56.6% (−1.5 pp) | −8.7 → −6.9 pp | −823 → −1,065 | −242 |

The promise held in the one column it was making: **every bar fell**, by 0.2 to 3.7 points, and the coin's
fell exactly where the run-count arithmetic said it would. The promise failed in the two columns that pay.
Five of the eight rows are further from their bar than they were, seven of eight lose more money, and the
one that improves — the slowest trend filter, +$17 a month — improves by a rounding error on a book $448
short. Widen out from this cell and it is the same picture: across the 33 rule×window rows where the same
rule was priced on both clocks at 2 bps, **22 lose more on the daily clock, 10 lose less, one is
unchanged**, median −$23 a month and mean −$68, the best case +$248 and the worst −$461. The gap widens
wherever the rule trades often enough for the extra decisions to be its own noise: the 126-session filter
goes from 157 runs to 347 and from $502 to $763 a month of damage, and its hit rate collapses from 27.4%
to 15.6% because a daily clock counts a two-day whipsaw as a decision the weekly clock never made.

## Result 2 — the toll is not the excuse

At 2 bps a faster clock obviously pays more toll, and the honest objection is that the whole result is
that toll. It is not. Same grid, SPY full, daily review at **0.3 bps** — a fifteen-fold cut:

| rule | weekly @2.0 | daily @2.0 | daily @0.3 | daily gain at 0.3 | toll's share of the daily loss |
|---|---|---|---|---|---|
| 200-session trend | −465 | −448 | **−409** | +55 | 8 bps of a 170 bps gap |
| 126-session trend | −502 | −763 | −728 | −226 | $35 of $226 |
| 50-session trend | −647 | −868 | −821 | −173 | $47 of $221 |
| 13-week momentum | −540 | −763 | −725 | −184 | $39 of $223 |
| 4-week momentum | −736 | −764 | **−678** | +58 | $86 of $29 (the toll was all of it, and more) |
| coin flip | −823 | −1,065 | −831 | −8 | $234 of $242 |

Two rules — the 200-session trend and 4-week momentum — do turn positive at a cheap desk, worth +$55 and
+$58 a month, and for the 4-week filter the daily penalty is entirely the toll. Neither reaches DCA: the
best daily row anywhere on the grid is **−$58 a month** (52-week momentum, SPY, 2022→2026 — a calendar on
which no accuracy at all reaches DCA, bar and all). For the rest, cheapening the trade recovers a fifth of
the damage at most. The rest of it is
the decisions themselves: a faster clock does not add information, it adds *events*, and each one costs a
switch and is graded on a span of days rather than quarters.

**0 of 42** daily real-rule rows — five cells across three sleeves, at both 2 bps and 0.3 — are
money-positive, and none clears its own bar. It is a smaller grid than round 13's and it is reported as
one: a daily solve costs about five times a weekly one, so the sweep is five cells rather than twelve. `TheCadenceIsAFreedomNotAnEdge` pins all of it, including the
two structural facts that make the arithmetic trustworthy rather than plausible: a daily slice has 5.0× the
bars and the *same* total deposits, and the trend signal answers identically on every session the weekly
slice can see (`test_a_faster_clock_adds_bars_and_not_signals`, 1,000+ sessions cross-checked).

## What this does to the goal

It closes the version of "short-term trading" that means *the same price signal, checked more often*, and
it closes it in both directions:

- at a weekly clock the required accuracy runs 63–98% across the cells where a rule actually traded, and
  the rules here show 41–83% of it, with medians of 52–72%;
- at a daily clock the bar really does fall, to 61–92% — two to four points of genuine relief — and the
  rules show *less* of it, not more, because the extra decisions are whipsaws and the toll triples.

So the goal cannot be reached by trading an index fund faster on its own price. That leaves exactly three
things that have ever produced dollars in this archive, and round 14 says nothing about any of them:

1. **Sizing** — constant leverage clears the financing menu from 1.25x (round 11), and the levered
   candidate beats DCA on both axes at 1.25x in 12 of 15 cells (round 12). The money is the borrowing.
2. **The withdrawal frame** — a shallower worst month is worth something at flat dollars, and the
   candidate is the shallowest drawdown in 15 of 15 cells (round 10).
3. **Information this archive does not contain** — flows, positioning, news, earnings calendars, other
   sleeves' prices beyond these twelve. Round 13's arithmetic says such a signal must carry ~58% at a
   coin's turnover, and the ~1,691 independent weekly calls a fast rule needs cannot come from one
   autocorrelated price series. They could come from something that is not price.

The honest reading of fourteen rounds: the bot is not missing, it is *unfunded by the data*. Every
mechanism that can be priced from twelve daily price series and a T-bill path has now been priced, and the
only one that clears is borrowing money cheaply to hold more index — which is a leverage decision, not a
trading model, and reverses on the custodian's price. If the goal is to be met, the next thing to build is
the input, not the signal: a second, non-price feed and the same bar applied to it.

## Checks

Full suite **1299 passed, 233 subtests**; `journalctl verify` reports the ledger chain intact and the
pinned comparator untouched. `tests/test_accuracy_bar.py` is 29 tests, ~5 minutes: five of them new, on
the cadence axis — bar-count and
deposit invariance, the drag compounding per session held (`daily.drag ** 5 == weekly.drag` to twelve
places), the bar falling when the clock speeds, the skill and the gap moving the wrong way with it, and the
whole daily grid pinned to lose. Full suite and `journalctl verify` reported with the round.
