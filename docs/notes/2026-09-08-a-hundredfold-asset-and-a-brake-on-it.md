# A hundredfold asset and a brake on it

Goal round 1 (of 96), `goal-91eb485f…`. Step 1 (the cost record) is blocked on a number only the account holder can read, so this round took
step 2 as far as it can go without that number — and it turned out to go all the way to a verdict.

## What ran

`tools/ba005.py`, exactly the locked rule: BTC-USD, hold above its own 200-day mean, bills below, monthly, on the archive's completed-month
grid, 123 months from 2016-06-01 to 2026-08-03, $100,000 paid in (scale-parametric — every figure below is per $100k):

```
  BA-005 · BTC-USD above its 200-day mean, monthly · 2016-06-01 to 2026-08-03 · 123 months
    gross (fee = 0, which is not a possible world): $12,215,315 on $100,000, CAGR +60.39%, max DD 56.5%
      held crypto 75/123 months · 20 switches (10.0 round trips) · 0 months lost to the 200-day warm-up
    the bar on the same months: QQQ $697,992 (+21.05%, DD 32.6%) · VOO $428,014 (+15.37%, DD 23.9%) [P0]
    and simply holding the asset, no signal at all: $11,866,448 (+59.93%, DD 76.7%) — the timing is worth +2.9% over the decade
    of holding, and its drawdown is 20.2% points shallower
    break-even taker fee: 1,333 bps to tie QQQ · 1,543 bps to tie VOO

    FAIL, and the fee record cannot change it: the deepest drawdown this rule reaches anywhere on the grid is 56.5%, and
    the spec allows 40.7% (1.25x QQQ's 32.6%).
```

Sanity first, because a 60% CAGR is the kind of number that should make a reader suspicious rather than happy: BTC's own closes in this
archive run from $211.16 (2015-08-24) to $124,720.09 (2025-10-06) across 4,068 candles, so ~100× over the window is a CAGR in the high 50s
before any signal — the model is not inventing the return, the asset supplied it. Fees at 60 bps per switch cost 11.3% of paid in over ten
years, which matches 20 switches to two decimal places. The drawdown of the *rule* (56.5%) sits between the asset's own worst fall inside the
window (76.7%) and QQQ's (32.6%), which is exactly where a brake belongs.

## The verdict, and why it exists without the fee

The spec was locked this morning with the failure condition attached to the **ruin promise**, not to the terminal. That decision — made before
any number was computed — is what let today's run finish: the drawdown gate fails at every fee on the grid, and a fee only ever takes money
out of a path. So `ba005.py` distinguishes two refusals: `NO VERDICT` (exit 3) when the missing fee is the thing that decides, and `FAIL`
(exit 1) when a gate is fee-independent. Printing "no verdict" here would have been rule 106's sin in a lab coat: silence about a conclusion
the data already forces.

The fee grid is the second thing worth keeping. Break-even at **1,333 bps per side** means Coinbase's fee is *irrelevant to the terminal* — a
total inversion of everything the equity book has ever concluded, where a 3 bps convention change was news. Costs stopped being the story the
moment the asset changed, and the thing that killed BA-005 is the thing costs were never about: an 80%-class drawdown in an asset that had
one, two, and three-year stretches of losing most of itself inside the only decade of record it has.

## What this does and does not mean for the objective

It does not mean crypto pays. The timing rule added **+2.9% over ten years** to just holding the coin. Read plainly: BA-005 is an asset bet
with a brake fitted, and the brake is the only part that was "the model". If the objective is a *trading model* that earns extra each month,
this is evidence that the extra would come from owning bitcoin — a decision the objective could make directly, no model required — and that
the model's own contribution on the archive's terms is 2.9% of a decade, against a drawdown that still fails the promise.

It does mean the pre-registration earned its keep. Had I looked at the terminal first, the mood of this note would have been very different,
and the drawdown gate would have been under pressure to look pedantic. Locking it first is the only reason the number above is a finding
rather than a sales pitch.

Still owed: the ruin test at QQQ's own affordable monthly bill (step 3), reported whichever way it lands — and it is not a formality, since
the bill half is what "earn extra each month" actually asks. No fifth forward book: step 4 says a failure ends it, and the gate fired.

## Checks

**2396 passed, 239 subtests** (2382 + 14 new; collected count printed before the run). Rules: **111**. `tools/ba005.py` reads its window,
average length, instrument, and drawdown limit out of the spec text, so the spec and the runner cannot drift apart silently. Forward loop
untouched: first real seal 2026-09-30, 23 entries to a skill claim.

*Goal round 1. The Coinbase model was built, priced, and failed on its own locked terms in the same day it was written — and the failure is
the interesting result: not "crypto doesn't work", but "the model added almost nothing to owning it, and what it added was a brake".*
