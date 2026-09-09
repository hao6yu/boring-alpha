# The rule's whole edge is the price of its borrowings: at the posted rate it is worth −0.00%/yr

Measured 2026-09-06, round 25. Tools changed: [`income_frontier.py`](../../tools/income_frontier.py) (`--sweep`),
[`book_power.py`](../../tools/book_power.py) (`--sweep`, `--borrow`); tests
[`test_sweep_repricing.py`](../../tests/test_sweep_repricing.py) (9).
Round 24 pre-registered this measurement and stated its expected answer in advance. The answer came back
partly as predicted and partly worse.

## The prediction, and what happened

Stated before running: *the ordering of plans survives, because every plan's cash leg moves together; the
rule's own edge does not.* Both halves are now facts, and a third thing happened that nobody had predicted.

## 1. The rule's edge is a financing assumption

`withdrawal_capacity.run` charges a loan as `cash_rate[month] + spread / 12.0`, and the paper book is
configured with a 3bp spread — so the rule borrows at roughly the bill rate. [`paper.py`](../../tools/paper.py)
says so itself: *"The borrow rate is this plus the spread, and it moves."* 3bp is the price of a fill. The
cheapest desk in the repo's own menu posts **4.90%** for money. The rule's weights average 1.023 and it is
levered in a majority of months, so this is its cost, not a rounding.

| cash leg | what the borrow costs | rule's excess | on $20,000 | book could resolve it at mo. 60? |
|---|---|---|---|---|
| archive bill curve | book: curve + 3bp | **+0.49%/yr** | +$8.18/mo | no |
| archive bill curve | **posted 4.90%** | **+0.09%/yr** | +$1.51/mo | no |
| sweep 0.02% | book: curve + 3bp | +0.61%/yr | +$10.14/mo | no |
| sweep 0.02% | **posted 4.90%** | **−0.25%/yr** | −$4.10/mo | no |

> **Corrected 2026-09-06, same day (round 26).** The four rows above originally read +0.40 / −0.00 / +0.51 / −0.34, and the note said the posted-rate row was "−0.00%/yr". The benchmark leg in `book_power.net_strategy_returns` was charging the strategy its fund's expense ratio while giving the comparator none — so every excess there is understated by one expense ratio, 0.0945%/yr. Fixed at the source; the rows are the table above. The finding is untouched by it, because the correction is a constant added to all four: the financing subsidy is still ~0.79%/yr and the residual at account-faithful terms is still inside nothing anyone could measure. Round 26 found it because a static-100% control row printed the expense as its own excess and the identity failed to close — see [`2026-09-06-unlevered-timing.md`](2026-09-06-unlevered-timing.md).

Read the middle column against the first: the same rule, the same weights, the same archive, priced at what a
desk actually posts for money, and **the edge is gone** (it is +0.09%/yr rather than +0.49%, a difference that matters to no decision at $20,000). Not negative because the rule is bad — negative
because it was a net borrower being credited with lending at the bill rate. Two notes follow from this row, and
both matter more than the number:

- **The live paper book is running on subsidised money.** Its own accounting accrues the rule's borrowings at
  the bill rate plus 3bp. That is why the book's numbers will always look a little better than any real
  account's, and why the `--borrow posted` switch is now part of the tool: any future claim about this rule
  that does not name which of those four rows it comes from should be treated as unpriced. The fix is a
  `borrow_rate` spec in `model.json`, stated the way the comparator spec is stated — and pinned as
  pre-registration for the next change to the book, since editing the accrual mid-book would move the meaning
  of entries already sealed.
- **Every published gap in this file series is a "book" row.** Rounds 19–22 compared plans inside one engine,
  so the subsidy is shared and the *ordering* is unaffected — which is exactly what the pre-registered
  prediction said, and it held (below). What is not unaffected is any statement of the form "the rule earns
  more than doing nothing", which is the sentence the whole project exists to earn.

## 2. The frontier under a sweep: the order survives, and the guardrail starts discriminating again

Twenty years, $400/mo floor, guardrail, cash leg replaced by the audited 0.02% brokerage default:

| plan | median/mo | ×floor | min end | verdict |
|---|---|---|---|---|
| candidate | $710 | 1.77× | 0.64 | pays 1.77× its promise |
| SPY | $597 | 1.49× | 0.12 | pays 1.49× |
| gateless | $608 | 1.52× | 0.27 | |
| flat at avg | $593 | 1.48× | 0.11 | |
| reversed | — | — | 0.00 | cannot keep 20 years: a start died at 2000-04 |
| cash | — | — | 0.00 | **cannot keep 20 years: a start died at 1993-02** |

- **Ordering survives:** candidate $710 > gateless $608 > SPY $597 > flat $593, same ranks as under the curve.
  Candidate over its own fund: **+$113/mo at 20 years** (was +$123), **+$73/mo at 10 years** — at ten years
  that is nearly three times round 18's $25-per-$20k noise floor, so the ordering claim survives the money.
- **The margin shrinks and stays inside the round-18 band at $100k**: $113 against a $125 band at that size.
  Round 20's "not a number the noise would excuse" was already the honest caveat; the sweep makes it worse, not
  better, and the caveat still governs.
- **The control still bites:** `reversed` dies at 2000-04 on the sweep curve, as it did on the bill curve.
  ITOT still cannot decide it (1.79×, `min end` 0.88) — the round-21 shape is unchanged.
- **The unearned credit was what was flattening the ranking.** Under the bill curve the guardrail's winner sat
  at 1.97–2.00× — pinned against its own 2× structural ceiling, which round 21 had to publish as
  `NOT DISCRIMINATING`. Take the unearned cash away and the winner lands at **1.77×**, clear of the ceiling, so
  the instrument that could not rank the plans starts ranking them again. An assumption in favour of the
  strategy was simultaneously making its own evidence less informative. That is the strongest argument this
  repository has yet found for pricing the dull legs first.
- **`cash` fails the twenty-year promise outright** — died at 1993-02, the first start in the record. Under the
  bill curve it survived. The do-nothing option's real cost is now visible: at a 0.02% sweep, holding cash for
  twenty years is not a conservative choice, it is a failed plan, while the same money in a bill ladder earned
  the curve. Round 24's $46/mo was not a bonus; it was the difference between a plan that works and one that
  does not.

## What this leaves standing for the actual goal

The de-risking rule's monthly-income advantage over simply holding the index **survives at the plan-ordering
level and does not survive as a claim of earning more than the index**. Its income advantage comes from
*sequence behaviour* — the crash-month exposure that round 23 showed the book can actually test — and its
dollar advantage over doing nothing is inside the noise at every size that matters and zero once its borrowings
are priced as money.

So the goal as stated — a model that earns extra each month and beats VOO/QQQ — is not met by this rule, and
the failure is now precisely located rather than statistical: **the rule trades dollars for drawdown, and the
dollars leg costs the financing subsidy to look positive.** The next candidate has to be one that does not
carry a borrow at all, or it will land on the same rock. That is a narrowing, not a defeat: after twenty-five
rounds the constraint is "unlevered, and worth more than the sweep rate it forgoes", which is a testable shape
that most of the archive can answer.

## Checks

9 new tests, 1.7 s, all offline: the posted monthly charge must be the monthly compound of the posted annual
rate and must be far below it (the bug this caught was mine and immediate — an annual 4.90% used per month is
58%/yr, and it produced a −10.07% row that a first-order estimate of 0.7%/yr should have killed on the spot);
an unlevered rule must cost *identically* under both borrow models, which is the leak test that makes the
switch trustworthy; the subsidy must have exactly one sign across all four pairs; no variant may be near
resolvable at month 60, so round 23's conclusion is re-checked against the edges round 25 actually measured;
`apply_sweep` substitutes rather than floors and passes `None` through untouched; and the substituted
`mean_cash` must satisfy `spread = MENU_PUBLIC − mean_cash` so the all-in stays at the posted rate — hold the
spread fixed while lowering the credit and the same edit cheapens leverage at the same time, and the two errors
partly cancel into a number nobody could defend. Full suite: **1442 passed, 233 subtests** (1451 after round 26). `journalctl verify`:
chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
