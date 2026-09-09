# The book cannot see the edge it was built to test: 6% power, at any deposit size, at any horizon

Measured 2026-09-06, round 23. Tool: [`book_power.py`](../../tools/book_power.py), module function
`boring_alpha.metrics.bootstrap.book_power`, tests [`test_book_power.py`](../../tests/test_book_power.py) (10).
This round contradicts a recommendation this file series has made in every note since round 16. Read it
before repeating the sentence "the forward book will settle it".

## Why

The book's own report line says `skill: underpowered — 23 more monthly entries, $5,000 more paid in required`.
That line implies the underpowering is temporary and curable by waiting. Nobody had checked, so I asked the
only question that makes that sentence meaningful: **at $5,000 in and $500 a month, how large would the
edge have to be for this instrument to see it?** The answer is a property of the deposit schedule and the
volatility, not of the strategy, so it was computable today.

Everything is read from the book rather than restated: the model, comparator, expense, deposit schedule and
spread all come from `data/paper/model.json` and the sealed first entry. Re-pin the book and this follows.

## The measurement

The strategy leg is the rule the book actually runs — the same weight path the backtests use — converted to a
monthly net return: the fund on `w`, the cash curve on `1−w`, that curve **plus the book's spread** on the
borrowed part, the expense ratio on the invested share, and the archive's per-side friction on every pound the
rebalancing band moves. Over 404 months that is **+0.34%/yr against the fund, which is $5.61 a month on a
$20,000 account.**

The null hypothesis is that the rule has no edge at all: its monthly difference against the fund is shifted to
exact zero, and blocks of three months are resampled **in pairs** so the correlation and the volatility
clustering survive. Each resample is then run as an account — opening balance, $500 in at each month start,
both legs — and the terminal dollar gap recorded.

| month | null gap, p05..p95 | smallest edge it can resolve | as a rate | power at the $5.61 it actually has |
|---|---|---|---|---|
| 6 | −$577 .. +$573 | $133/mo | 19.98%/yr | **6%** |
| 12 | −$1,048 .. +$1,075 | $125/mo | 13.69%/yr | 6% |
| 24 | −$2,330 .. +$2,377 | $132/mo | 9.35%/yr | 6% |
| 60 | −$9,120 .. +$8,601 | $169/mo | 5.79%/yr | 6% |
| 120 | −$36,830 .. +$30,825 | $236/mo | 4.35%/yr | 6% |
| 240 | −$237,214 .. +$190,588 | $391/mo | 3.76%/yr | 5% |

## Three findings, each worse than the last

1. **Power is 6%, and it is flat in the horizon.** The smallest edge this schedule can resolve at month 60 is
   **17 times** the edge the archive says the rule has. Twenty years of deposits — 240 months, eight times the
   23 the report asks for — buys down to 11 times too coarse.
2. **Money does not buy power. The account size is a red herring.** Rerunning the same horizon at
   $50,000 + $5,000/mo and at $250,000 + $25,000/mo gives a detectable rate of **5.79%/yr in all three cases**
   — identical to two decimals across a 50× range. The gap and its noise are both proportional to capital, so
   the ratio, which is what a test depends on, does not move. The intuition "run it with real money and you'll
   know" is false, and it is the intuition that has been sitting behind every `underpowered` line.
3. **Waiting helps fast for two years and then stops.** 9.35%/yr at month 24 → 5.79% at 60 (real progress) →
   4.35% at 120 → 3.76% at 240. The curve flattens because the account's *variance* compounds along with its
   balance: an edge that scales with the account is measured against noise that also scales with it. A test
   that becomes possible in year 20 at 11× the resolution it needs is not a delayed test.

## The correction this forces

Every note since round 16 has closed with some version of *the forward book is the only evidence the archive
cannot supply*. That sentence is true about **behaviour** and false about **skill**, and this round found which
is which. The ledger will never arbitrate a 0.34%/yr dollar edge at this size. It will arbitrate this, and
quickly:

```
fund fell >5% in 37 months of 404 (1.1 a year); >10% in 5
the rule's mean weight in those months: 0.71 (95% 0.58..0.84) against 1.00 for doing nothing
expected episodes in the next 24 months: 26.4, in 60: 65.9
```

A dollar gap compounds and so does the noise around it; **an exposure does not compound**. The claim "when the
fund dropped more than 5% in a month, this rule held 0.71 of itself in it instead of 1.00" is a per-event
statistic with 37 events in the archive and ~26 expected in the next two years of trading, and the ledger will
either confirm it or not the first time the tape moves. That is the book's real claim, and it is the one worth printing beside the skill line. To be exact about blame: the
line in `journal.py` says *23 more entries required*, which is a stated **minimum** and is true — the error was
the reading that followed it everywhere else, that a minimum is a plan and that enough patience turns a coin
into a measurement. `paper.py report` should print this tool's resolution figure beside the skill line so the
two are never read apart.

For the decision this file series exists to serve: **the money question will not be settled by observation at
this scale.** It has to be settled by argument about the mechanism plus the backtest's own evidence — and
round 22's premium is the honest price of that argument: about $21 a month on the median decade at $20k,
against an expected $5.61. Which is to say the insurance costs more than the claim is worth, and the reason to
hold it anyway has to be the promise, not the money.

## Checks

10 new tests, 0.7 s, all offline: **calibration** — an injected noisy edge of known size must be recovered
within 20× and above 5%, which is the test that would have caught the month/annual slip this tool shipped
with; **paired-ness** — a strategy identical to its benchmark must show a gap of exactly zero and not a small
plausible drift; **size invariance** — a 10× schedule multiplies the dollar MDE by 10 and leaves the rate
alone; an unfilled horizon raises rather than truncating; the behaviour line reports *exposures* (all weights
inside the policy's band) and not returns; the schedule is read from the book. One test hung the suite for ten
minutes by calling `list()` on an infinite generator, which is worth recording because it looked exactly like a
slow bootstrap and was nothing of the kind. Full suite: **1425 passed, 233 subtests**. `journalctl verify`:
chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
