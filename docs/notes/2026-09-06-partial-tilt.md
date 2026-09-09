# The partial tilt: sizing the rotation down does not size the problem down

Measured 2026-09-06 on `data/current` (`methodology: yahoo-adjusted-v2+dgs3mo-v1`, dividend-adjusted
closes, every sleeve ending 2026-09-04). Tool: [`../partial_tilt.py`](../../tools/partial_tilt.py),
tests: [`../tests/test_partial_tilt.py`](../../tests/test_partial_tilt.py). Reproduce with
`.venv/bin/python tools/partial_tilt.py [--cost-bps 0.3|2|5] [--window …]`.

## Why this round exists

Round 15 closed full-weight cross-sectional rotation with two numbers instead of a shrug: the ranking
beat its own reversal by $413 a month, and holding nine sleeves instead of one cost $520 a month. It also
left an honest excuse standing — nobody would ever trade that book. A $5,000-plus-$500-a-month account
does not hold one-ninth of a commodity pool and one-ninth of a 20-year bond fund. What it would do is
keep the index fund and *point a slice of it* at whatever the ranking prefers this month.

A tilt moves money, it does not create it, so the counterfactual to `w` in sleeve X is exactly the money
that would otherwise have sat in the fund. The tilt's entire return is one series — `r_pick − r_index`,
net of the turnover the *tilt* caused — and everything else is presentation.

## Fixed before the first run

Inherited from round 15 and deliberately not re-touched: the nine ranked sleeves, the 12-1 lookback, the
monthly calendar, both comparators, the SPY→VOO benchmark splice. New and locked before the first cell was
computed:

- **The grid, printed whole:** tilts of 5, 10, 20, 30 and 50% of the account, K of 1 and 2, forward and
  reversed, four windows. Forty forward cells and forty controls. No cell may be dropped, and `verdict()`
  now raises if a cell is *missing* rather than quietly grading the ones that showed up.
- **The pass rule:** positive versus the index in *every* window, annualised Sharpe of the spread series
  ≥ 0.5 in every window, the reversed tilt losing in every window, and not mooted by the $25/month floor
  inside which the choice of near-identical benchmark fund already moves the answer.
- **The prediction, from round 15's own arithmetic:** the full-weight rotation carried +$413/month of
  signal and finished −$351/month against the index, so whatever survives the index's own contribution is
  thin. A partial tilt should land near zero over the whole record and positive in regimes where the top
  sleeve beat large-cap US equity. The stated falsifier: **if every fraction comes back positive in every
  window, the file has a bug** — a fraction of a loser cannot be a winner unless the accounting is wrong.

## The result: 10 of 40 cells positive, and they are all the same window

$/mo against plain index DCA, at 2 bps a leg, on the same deposits:

| tilt | full record 2007–2026 | seen A 2007–2017 | seen B 2018–2021 | recent 2022–2026 |
|---|---|---|---|---|
| top-1 @ 5% | −$16 | −$14 | −$11 | +$5 |
| top-1 @ 10% | −$32 | −$28 | −$22 | +$10 |
| top-1 @ 20% | −$65 | −$55 | −$43 | +$19 |
| top-1 @ 30% | −$101 | −$82 | −$65 | +$28 |
| top-1 @ 50% | −$176 | −$133 | −$107 | +$43 |
| top-2 @ 20% | −$66 | −$43 | −$40 | +$19 |
| top-2 @ 50% | −$171 | −$106 | −$99 | +$45 |
| *reversed* top-1 @ 20% | −$314 | −$90 | −$48 | −$67 |
| *reversed* top-2 @ 20% | −$222 | −$71 | −$42 | −$38 |

**No cell in the grid passes the rule.** Every window that ends before the present loses money at every
tilt size, and the one window that pays is worth +$5 to +$45 a month. Four readings, in order of how much
they matter:

**1. The ranking is still doing its job; the default sleeve is the problem.** At every tilt size the
forward tilt beats the reversed tilt — −$65 against −$314 at 20% on the full record, a factor of five. What
kills the tilt is that the counterfactual is SPY or VOO, and 2007–2026 was the era in which American
large-cap equity beat everything else on this shelf almost every year. Any deviation from it, well-ranked
or not, loses on average. The signal is not the broken part and this is now the second independent
measurement saying so.

**2. Sizing down scales the loss and not the risk.** The 50% tilt loses 11.3× what the 5% tilt loses, not
10× — variance drag on the compounded balance, which is pinned in `test_the_ending_gap_grows_faster_than_the_tilt`
so nobody re-learns it in production. Halving the tilt halves the arithmetic P&L and takes less than half
the pain off the terminal number.

**3. The best cell in the file rests on 21 months.** In the recent window the spread series has a lag-1
autocorrelation of **+0.46**, so 57 calendar months are **21** independent ones. Its Sharpe is +0.38, which
fails the 0.5 bar on its own; the tilt is +$19/month at 20% of the account; and the account it is measured
on is $52,935. Discounting a mean by its own persistence is the same arithmetic that round 13 applied to
run counts, applied here to months, and it is the difference between "ten years of evidence" and "two years
of a regime".

**4. Below 20% the question is moot, and above 20% it is a bet.** The toll is not what limits reading this
table: the same index book at 0.3, 2 and 5 bps ends $568,968, $568,889 and $568,749, which restated as
monthly equivalent is **$0.45** on the full window and $0.06 on the recent one — a book that rebalances
twice in nineteen years is cost-insensitive by construction. What sets the floor is round 15's other number,
the $24 a month that separates two funds tracking the same index at a 6.45 bps fee gap, and that is why the
tool calls $25 a month moot. Every 5% cell and six of ten 10% cells sit inside it; every cell at 20% or
above is outside it, and at those sizes the tilt is not a side income strategy, it is an active position
with a view that the index fund is not the best thing on the shelf.

## The bug the tests caught, which is the reason to write tests here

`spread()` originally charged each tilted book its *own* full turnover. One month in 235 disagreed with the
proportionality the file depends on — month 42, **2010-09-30**, the month the benchmark itself splices from
SPY to VOO. The whole base leg moves in that month, and a tilted account moves only the part not already
committed: a 50% tilt should pay half the leg a plain account pays, and it was being billed the whole thing.
The spread for that month came out 11.8× instead of 10× and the tilt looked ~1% worse than it earned. The
cost term is now an increment against the comparator's own churn, `test_the_spread_series_is_exactly_proportional_to_the_tilt`
holds every one of the 235 months to nine decimals, and the Sharpe came out scale-free to the last printed
digit — which it never would have been otherwise.

## What this does to the goal

This closes the last shape a price-only, cross-sectional trade can take in this account at this size: full
weight (round 15, redundant), and any fraction of it (this round, negative in three of four windows and
noise-sized in the fourth). Every mechanism in this repository that beats plain DCA into the index fund now
shares one property — **none of them is a signal**. Constant 1.25–1.5× exposure (rounds 11 and 12) beats DCA
in 12 of 15 cells and pays a median +$95 a month at a cheap desk, and it contains no forecast whatsoever.

That is a finding about where the remaining money is, and it argues for stopping the search for a *rule* and
finishing the one *decision* that survived: turn the levered-index result into an executable policy artifact
with a pain-matched cap and a real desk's financing line, and open the forward record on it. The goal's
stated instinct — short-horizon decisions informed by news and trends — is not yet disproved, but it needs an
input this archive does not contain, and no further window of these twelve sleeves can supply it.

## Checks

`tests/test_partial_tilt.py`, 13 tests: a zero tilt reproduces the index book to nine decimals; the spread
series is exactly 10× at a 50% tilt in *every* month; the ending gap is super-linear at 50% (variance drag,
pinned as a direction); the Sharpe is identical across five tilt sizes; a dearer toll never helps any forward
cell; the forward tilt beats the reversed one at every size while still losing money; `n_eff` may discount a
count and never inflate it; a 12-month series refuses to print a Sharpe; `deploy` is zero when the rule keeps
landing on the fund the account already holds, and equals the label here only because the top pick was never
the benchmark in 235 months (checked independently); the pass rule **can** return a pass, does return a fail
when one window is doctored negative, and raises when a cell is missing from the grid; and the sign
prediction written before the run is asserted per cell. Full suite: **1331 passed, 233 subtests**.
`journalctl verify`: chain intact (1 entry), comparator spec `100% SPY, fee 0.000945` unchanged — the
sealed ledger is untouched at one entry and $0.00 paid in.
