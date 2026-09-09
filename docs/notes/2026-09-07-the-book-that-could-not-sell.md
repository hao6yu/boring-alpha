# The book could not sell

Measured 2026-09-07, round 69. Live artifact changed: [`paper.py`](../../tools/paper.py). Tests: 14 new in
[`test_paper_shelter.py`](../../tests/test_paper_shelter.py), 3 in [`test_paper.py`](../../tests/test_paper.py), 1
corrected in [`test_paper_constant.py`](../../tests/test_paper_constant.py).

Rounds 55 to 68 converged on one defensible construction and backtesting it further cannot produce evidence the archive
does not already contain. The remaining gap is a forward record. But the paper book that exists to produce one was
running `voltarget` — the single-asset candidate this repository concluded loses to the comparator once the account is
charged what an account is charged — while the construction that measured +$130/mo over plain VOO on withdrawal capacity
had never been run forward at all. So the book was brought to the belief, and found to be broken in two ways, one of them
serious.

## The book could not sell

`orders_for` built its Order with a **signed** quantity, `delta / price`, and `command_step` applied orders as
`+ units` on a buy and `- units` on a sell. Two sign conventions cancelling in the wrong place: a SELL order carried a
negative quantity, subtracting it *added* to the position. Stepping the sheltered model through May, June and July 2025 —
sheltered, sheltered, back to equities — the July step was supposed to close 65.73 units of IEF and instead recorded
**131.45879762**, exactly doubled:

| step | holdings recorded | closing value |
|---|---|---:|
| 2025-05-30 (shelter) | IEF 61.25044553 | 5,496.74 |
| 2025-06-30 (shelter) | IEF 65.72939881 | 5,994.86 |
| 2025-07-31 (exit) — **before the fix** | **IEF 131.45879762, SPY 10.38922942** | wrong |
| 2025-07-31 (exit) — after | SPY 10.38922942 | 6,490.60 |

Nothing had ever noticed because no model in this book had ever held a position it then wanted out of: `voltarget` scales
one symbol up and down, and the chain sealed so far contains only its anchor. That is the general lesson, and it is the
reason this round is worth doing rather than a bookkeeping chore — **a path that no live model exercises is untested,
however many months the artifact has been running.** A forward book whose only tested transition is "buy more" is a book
that has not yet been asked the question it exists to answer. Fixing the exit also exposed a smaller one: a fully closed
sleeve was re-sealed as a holding with `0.00000000` units, because the filter tested the unrounded float (`(u*p)/p` is
not `u`) while the stored value was the rounded one.

## The other two, both flattering the strategy

**One expense ratio for whatever the book holds.** `fee_month = EXPENSE_RATIO / 12 * held_after`, with `EXPENSE_RATIO`
being SPY's 9.45 bps. Harmless for a one-fund book; wrong the moment the off-equity leg is an ETF whose fee this
repository has not posted, under-charging a sheltered month by nearly **four times** — and the shelter's entire case
rests on it paying something. The book now charges per symbol (`FEES`, carried from the same posted table the research
tools use, tested against it so the two cannot drift), charges a labelled flat **35 bps** for the unposted sleeves
instead of the flattering zero rounds 56 and 58 warned about, and **refuses** a symbol it has no fee for rather than
holding it for free. The sealed note names which fee was charged on which sleeve:
`paper; snapshot 20260906T203953Z; spread 1.65, expense 1.60 on fund value (IEF 0.35%), borrow 0.01 at 6.74% on 2 avg borrowed` — the May 2025 shelter month, quoted from a sealed entry rather than from memory.

**The stale borrow spread.** `BORROW_SPREAD` was 150 bps while round 30 measured a desk at 202, and paper.py's own comment
said any re-init should pin 0.0202 — because mid-chain that change would make a book incomparable with its own history
for a reason unrelated to the market, and only an anchor is a legitimate moment for it. This is an anchor, so it is
pinned: **0.0202**. `tests/test_paper_constant.py` keeps that a loud decision rather than a silent edit.

## The bug I introduced, and the test that caught it

My first draft of the live rule read the trend on the **last** trading day of the prior month. That is not the rule round
66 pinned as conservative — it is r66's friendlier reading, $60/mo apart on the same windows, and it would have quietly
made the forward record measure something more flattering than the thing the backtest measured. The cross-check test —
`paper.shelter_weights` against `shelter_long_record.month_signal(..., "start")` and `carry`, day by day since January
2023, two independent implementations of the same rule — failed on **2023-01-03** and forced the correction. The
transferable rule: a reimplementation of a measured rule needs a differential test against the original, not a comment
claiming they agree. (paper.py reimplements on purpose; the live book must not import a research script.)

## What is running now

```
paper book anchored at 2026-09-04 with $5,000.00 cash · shadow comparator anchored alongside
MA200 monthly (first-day reading) -> 100% SPY at 0.09%, as of 2026-09-04:
   SPY  100.0%  BUY      gross 100%  cash to cash-line 0%
```

`model.json` records `model_key: shelter`, `sleeves: [SPY, IEF]`, `fees: {SPY 0.09%, IEF 0.35%}` and
`trend_reading: first trading day of the month BEFORE the one it governs`, alongside the snapshot id it was sealed
against. September 2026 is not a sheltered month under this rule, so the opening decision is fully in equities,
unlevered; the first step seals at the September close, the deposit is $500/mo, and the benchmark is a second append-only
chain rather than a derived number. The prior `voltarget` chain is not deleted: it sits in
`data/paper/superseded/` as `ledger-2026-09-07-pre-shelter-model.jsonl`, `shadow-…` and the config that went with it,
with a second superseded anchor pair from this round's own correction.

## What a forward book can and cannot settle here

It **can** settle whether the model's switches cost what this book charges them — 3 bps side-equivalent, per-symbol
expense, borrow at cash+202 — and whether the sealed book and the research rule keep agreeing as new data arrives, which
is the drift the differential test will catch if it ever happens. It **can** settle whether the plan tracks the shadow
comparator within costs over the next twelve seals.

It **cannot** settle a 5% failure budget: that is a distribution over 169 windows and one forward path samples one. Nor
does a paper fill exist: there is no queue, no impact, no tax lot, and IEF's real spread is far tighter than 3 bps while
the book charges it the same flat figure as everything else. So twelve months from now the honest sentence will still be
the one in round 68 — +$130 to +$145/mo per $100,000 of *withdrawal capacity* over plain VOO, nothing on return — and the
book's contribution will be that it is no longer only a backtest.

## Checks

17 new tests plus 1 corrected pin, and the whole suite at **1868 passed** (collected first). The live chain is intact:
`journalctl verify` reports one entry and the pinned comparator, and the paper book's own two chains verify with it. The
shelter fee is pinned to be more than three times the old global figure, so the fix cannot be quietly reverted; the
differential test covers every session since 2023-01-01; a held symbol absent from the target must be sold; a full exit
leaves no holding, not a zero-unit one; and the config records the rule it was anchored with.
