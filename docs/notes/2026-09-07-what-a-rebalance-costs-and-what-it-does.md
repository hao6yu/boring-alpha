# What a rebalance costs, and what a rebalance does

Measured 2026-09-07, round 83. New: [`rebalance_cost.py`](../../tools/rebalance_cost.py),
[`test_rebalance_cost.py`](../../tests/test_rebalance_cost.py) (19). Changed: [`power_horizon.py`](../../tools/power_horizon.py)
(bands, periodic decisions, a per-sleeve expense burn, a sell tally counted at the trade).

Round 82 found that the tilt's monthly rebalancing sells the winner, and that the archive's engines charge it nothing for the
privilege — a constant weight vector has no turnover to price, so every capacity table from round 73 onward is built on a book
that rebalances continuously and pays nothing for it. That is a fair question about the evidence, so it got a claim written
down before the numbers were looked at: **billing the trades will not reorder the mixes, the tilt's advantage over plain VOO
will shrink, and a drift band will dominate monthly rebalancing.**

Two of those three survived. The claim about the tilt's advantage shrank to nothing, the claim about the band turned out to
have the wrong shape, and the round's real finding was in between: the idealisation is trivially cheap and the *policy* is
extremely expensive.

## The two numbers, kept apart

A spread bill and an end-value gap are not the same measurement and must not be added together or described in the same
sentence. One is a cost with a sign; the other is that cost plus whatever the market did.

| construction, 16 years ($100k in, $10k/mo) | charged nothing | drift, buys billed | monthly rebalance, 3 bps | band 5 pts | annual | spread paid | months it sold |
|---|---|---|---|---|---|---|---|
| plain VOO | 7,856,031 | 7,853,675 | 7,853,675 | 7,853,675 | 7,853,675 | 606 | 0 |
| 25% QQQ | 8,723,125 | 8,874,208 | 8,719,250 | 8,756,630 | 8,750,803 | 1,301 | 95 |
| **50% QQQ, the live book** | 9,783,165 | **9,988,324** | **9,778,203** | 9,812,538 | 9,824,371 | 1,697 | **100** |
| 75% QQQ | 10,947,473 | 11,102,440 | 10,942,639 | 11,001,368 | 10,980,362 | 1,446 | 92 |
| 100% QQQ | 12,220,221 | 12,216,556 | 12,216,556 | 12,216,556 | 12,216,556 | 606 | 0 |

- **The cost.** The 50/50 book paid $1,697 of spread over 193 months; the identical book left to drift paid $606. The
  rebalancing itself cost **$1,091 — 0.054% of everything paid in.** The archive's free-rebalancing idealisation understated
  costs by five hundredths of a percent of contributions. On this axis the evidence in rounds 73, 78 and 79 was not bought
  with an untaxed assumption, and the ranking of the mixes is identical under every charged regime, in both windows.
- **What the policy did.** The same book, rebalanced monthly rather than left to drift, ended **$210,122 behind** — 10.4% of
  everything paid in. That is not a fee. It is roughly 190 times the fee, and it is the winner the book kept selling.
- **The sign is the tape's.** On the last five years the same comparison flips: monthly rebalancing finished **$1,319 ahead**
  of drifting, because in that window there was no persistent divergence to sell away. So a drift band is not "better", it is
  a different exposure, and the tool reports the two windows separately and refuses to average them.

Against plain VOO on identical charges the 50/50 book is **$1,924,527 ahead** over the witness's whole life — the objective's
central comparison barely moved when the trades were billed, because the trades were never where the money was.

## Rebalancing is a cost of mature accounts

The 50/50 book sold in 100 of 193 months. But a book whose monthly deposit is large relative to what it already holds **never
sells**: arriving cash restores the weights by buying both sleeves. On a synthetic pair diverging 5% a month, a book funded at
100% of its opening per month sold zero times in 24 months, while a lump-sum book sold in almost all of them
([`test_a_heavily_funded_book_rebalancing_monthly_buys_rather_than_sells`](../../tests/test_rebalance_cost.py)). The selling
starts when the drift outgrows the deposit — for this book, at the journal's own 10% deposit ratio, after a couple of years of
growth. A young accumulating account that rebalances monthly is paying for a service it is not using.

## The ticket, which does not scale

At $9.95 a ticket: two funds, 384 tickets = **3.78% of every dollar deposited** at a $5,000 account against 0.08% at
$250,000; one fund, 192 tickets = 1.89% and 0.04%. **A band does not reduce the ticket count at all** — a book adding money
monthly buys every sleeve every month whatever its band; a band only stops the *selling* (100 months down to 2). So the
answer to "my broker charges per order" is the fund count and the broker, not the policy. That is round 82's conclusion
arriving with a mechanism attached: the only scale-sensitivity in the account is the flat charge, and it is 20 times larger on
the small account.

## Three defects, each found by asking the code to prove itself

1. **A sell counter that could only ever read zero.** It read `units` after the month's orders had settled the account, at
   which point every sleeve sits exactly at its allocation and no trace of the sale remains. It reported that a book which
   sold in half its months had never sold. Counted at the trade now, with the reason written where the counting happens.
2. **A band that confiscated the opening deposit.** Suppressing the first rebalance meant the account's largest single sum sat
   in cash for the entire record, so the band's apparent advantage was partly a cash drag nobody chose. The first buying month
   now always invests — which is also what the journal's own anchor does.
3. **An expense burn that charged each fund the book's average fee.** The burn was pro-rata on a summed expense, so SPY was
   eroded at 20 bps and QQQ at 9.45 bps: round 81's fee-ordering bug wearing a different hat. It is *value-preserving* in
   total, so no end-value figure in this note moved by more than a hundredth of a percent — and it was caught anyway, by an
   oracle test that computes the same account a different way: a never-rebalanced 50/50 book must equal two single-fund
   accounts holding half the money each. Each sleeve now burns by its own ratio.

That is the third time this week an independent recomputation — not a spot check — found an accounting error: the differential
against the sealed witness (round 82), the fee ordering (round 81), the burn oracle (now). The pattern is consistent enough to
be a rule, and became one.

## What this changes about the objective, and what it does not

Two changes are worth real money and neither is a signal: **a drift band** (which on the record captured $210k of the
$2.0M gap the tilt gave up, and cut selling from 100 months to 2) and **commission-free execution** (worth 1.89% of every
dollar at the live book's size, halved by holding one fund instead of two). No new forecast, no news feed, no regime
detection.

This does not license editing the live book. Round 70's rule is one construction per book: `tilt` was anchored as
*monthly-rebalanced 50/50 against plain VOO*, and that is what it stays until it is superseded in the open — a band would be a
new book with its own anchor, not an amendment to a sealed one. If the policy change is made, it should be made forward, on a
second book, where the answer arrives in years rather than in a backtest.

Deferred, and printed as a deferral rather than an omission: the brake constructions park cash in their flat months, and
comparing a cash-parking book against an always-invested one requires a bill curve this file does not model. Borrowing the
backtest's cash rate here would change two things at once.

## Checks

19 new tests, 0.7 s: single-fund books identical under every charged regime; a charged policy never beating the same policy
charged nothing; `band 10` never selling more than `band 5` more than monthly; the sell tally non-zero where it must be and
zero where it must be; tickets = one per sleeve per month, independent of the band; the cost field recomputing from the spread
tallies and being strictly positive while the end-value gap is not; the never-rebalance oracle matching two half-accounts to
under a dollar; an annual decision selling in a twelfth of the months; the report scoring its claim on both windows and
printing its deferral; and the JSON carrying every figure the report speaks. Suite: **2096 passed** (collected first, 2077 +
19); ledger chain intact.

## Correction, round 85: two cells in the table above are wrong

Round 84 changed the convention this table was computed under — drift is now measured across the invested book rather than
across equity including each arriving deposit (the old reading invented about five points of drift every month on a book funded
at 10% a month, which is a phantom, not a signal). The table above was published before that fix, so **two cells are stale**:

| construction, 16 years | band 5 pts, as published in this note | corrected |
|---|---|---|
| 25% QQQ | 8,756,630 | **8,792,165** (+$35,535) |
| 75% QQQ | 11,001,368 | **11,008,766** (+$7,398) |
| 50% QQQ | 9,812,538 | 9,812,538 (unchanged) |

The direction of the error is uniform: the phantom drift made the banded books believe they had to trade when nothing had
really moved, and every trade they took on that false reading cost them the spread and let the winner go. The smaller the QQQ
weight the larger the error, because the cheaper sleeve drifted further from its target in *value* terms and the old measure
conflated that with the deposit. The ticket table moved too, in the same direction and by the same mechanism: a $5,000 account
with two funds and a band ends at $473,609 rather than $480,752 published here.

Everything this note concluded survives the correction, and it was re-scored rather than assumed: the mixes' ranking is
identical under all three charged regimes in both windows; the rebalancing bill the idealisation omitted is still
0.003–0.054% of paid-in and still a cost in every window; the end-value effect of the same choice is still not one-signed
(monthly rebalancing ended $210,122 behind the drifted book over the record and $1,319 ahead of it over the last five years);
and the tilt's lead over plain VOO on identical charges is $1,924,527, against the $1,924,527 published. In the five-year
window the band no longer triggers at all — the drifted and banded books are the same book there, to the dollar, which is the
cleanest possible statement of what a band is: a policy that does nothing until something has actually moved.

The figures are now pinned by name in [`test_rebalance_cost.py`](../../tests/test_rebalance_cost.py), so the next time an
accounting convention changes, the table has to refuse rather than quietly re-quote itself.
