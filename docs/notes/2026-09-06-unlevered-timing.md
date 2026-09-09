# The signal is worth +0.51%/yr and it is a drawdown device, not an income device: the anatomy

Measured 2026-09-06, round 26. Tool: [`unlevered_timing.py`](../../tools/unlevered_timing.py), tests
[`test_unlevered_timing.py`](../../tests/test_unlevered_timing.py) (9), one source fix in
[`book_power.py`](../../tools/book_power.py).
Round 25 left a sharp constraint: any candidate has to be **unlevered**, because the moment a rule borrows its
apparent edge is the loan rate. This round runs the same signal with borrowing forbidden and takes its
profit-and-loss apart by month type, which is the only decomposition of this rule that needs no statistical
power to read.

## Four rows, two controls, one identity

Accounting is round 25's account-faithful pair: idle cash at the audited brokerage sweep (0.02%), any borrow at
the posted desk rate (4.90%), capital $20,000. The comparator is the pinned one — 100% SPY **net of its own
expense ratio** — which is why the first row's excess is now exactly zero rather than the expense ratio itself.

| variant | mean weight | excess vs 100% SPY | $/mo | vs equal-exposure control | max drawdown | worst month |
|---|---|---|---|---|---|---|
| 100% SPY, do nothing | 1.000 | 0.00%/yr | $0.00 | +1.78% | −50.8% | −16.5% |
| the book's rule, cap 1.30 | 1.023 | −0.25%/yr | −$4.10 | +1.53% | −29.4% | −16.6% |
| **same signal, capped at 1.00** | 0.843 | −1.27%/yr | −$21.15 | **+0.51%/yr** | **−25.9%** | −14.1% |
| static at 0.843, the control | 0.843 | −1.78%/yr | −$29.62 | 0.00% | −44.7% | −13.9% |

The third row is the finding and the fourth row is why it can be believed. The capped rule holds 84.3% of the
fund on average, so comparing it with 100% measures *how much it holds*, not *when it holds it*. Against a
static 84.3% position — same average exposure, same cash leg, no timing at all — the capped rule gains
**+0.51%/yr**. That number is the signal, stripped of debt and stripped of size. It is also, at $20,000, about
**$8.50 a month**, which is a fifth of what the idle-cash switch in round 24 was worth and roughly what a
different share class of the same fund is worth.

The drawdown column says what the rule is actually for: **−25.9% against −50.8%** for the index and −44.7% for
the control at the same average exposure. It halves the worst peak-to-trough and it does that better than
holding the same average amount the whole time, which is the only version of the claim that survived 26 rounds.

## The anatomy: what it saved, what it paid

Same 404 months, same accounting, split by month type — 37 months where the fund fell more than 5%, 61 where it
rose more than 5%, 306 in between. Contributions sum to the headline exactly:

| | annualised | $/mo on $20,000 |
|---|---|---|
| what it saved in the 37 crashes | **+3.50%/yr** | +$58.30 |
| what it gave up in the 61 rallies | **−4.25%/yr** | −$70.88 |
| what it did in the other 306 months | −0.51%/yr | −$8.56 |
| **total** | **−1.27%/yr** | **−$21.15** |

Twenty-four months of crisis insurance pays $58.30 a month when the tape breaks and costs $70.88 a month in
every ordinary good month, plus $8.56 of drift. The premium is negative — the device costs more in rallies than
it returns in crashes — and the ratio is not close: **the rallies cost 1.22 times the crashes**, against 61
months of rallies and 37 of falls. This is round 22's +$21/mo premium seen from the other side, now stated as a
partition rather than a summary statistic, and it is the number to quote whenever anyone asks what the rule
does: **it converts about 25 points of drawdown into roughly 1.3%/yr of forgone return.**

## The correction this round had to make first

`book_power.net_strategy_returns` charged the strategy leg its fund's expense ratio and gave the benchmark leg
none, while the pinned comparator in `data/paper/model.json` is explicitly net of that fee. Every excess in
rounds 23 and 25 was therefore biased *against* the rule by one expense ratio, 0.0945%/yr. Fixed at the source;
round 25's four rows moved from +0.40 / −0.00 / +0.51 / −0.34 to **+0.49 / +0.09 / +0.61 / −0.25**, and its note
carries the correction in place. The finding survives untouched because the correction is a constant across all
four rows: the financing subsidy is still ~0.79%/yr and the account-faithful residual is still unmeasurable.

It was caught by a control row, not by reading the code: the static-100% variant printed **+0.00%** where it had
previously printed exactly the expense ratio as its "excess versus the index it is". A control that should be
zero is the cheapest bug detector there is, and this is the second time one has earned its keep in three rounds
(the first being the identical-legs test in round 23).

## What this leaves for the goal

The goal is a model that earns more each month than VOO or QQQ. On the record, under account-faithful costs,
this family of rules does not do that in any configuration: levered it is worth +0.09%/yr — a rounding error at
any size — and unlevered it is worth −1.27%/yr against the index while beating its own equal-exposure control by
+0.51%/yr. What it does have is a **real, small, un-levered timing signal and a halved drawdown**. So the
honest options at $20,000 are, in order of what the evidence supports:

1. the idle-cash switch (round 24: ~$46/mo, no variance, no model);
2. the cheapest share class (round 18: ~$25/mo, real but noisy);
3. running this rule **unlevered** for the drawdown, accepting that it is a −1.27%/yr decision dressed in a
   +0.51%/yr signal, and treating the difference as the price of halving a 51% drawdown;
4. anything that actually *beats* the index needs a signal the archive says does not exist in what this
   repository has built so far — which is a search result, not a guess, and the search has now covered trend,
   volatility targeting, leverage, attention/news, calendar, and sleeve choice.

## Checks

9 new tests, 0.6 s, all offline: the three month types must sum to the headline to nine decimals, because the
split is a partition and not a summary; the bucket thresholds are checked against a four-month fixture with one
month per bucket; the cap must take the maximum weight to exactly 1.000 and leave the book's rule above it, so
the control is doing something; the static control must match the capped rule's *average* weight to twelve
places; the drawdown ordering must hold (capped shallower than control shallower than nothing, by at least a
factor of 1.4); and a static full position in the comparator must earn **exactly** zero excess — the test that
would have failed for the whole of rounds 23 and 25 had it existed then. Full suite: **1455 passed, 233
subtests**, collected as 1455; 1451 before round 27 added its four tests. The previous note claimed 1452 for itself without having run the suite, and the
figure in this paragraph is the one that came out of the runner — asserting a test count instead of reading it
off a run is the same class of error as asserting a number from an unstated source, and it is recorded rather
than quietly corrected. `journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`,
$0.00 paid in.
