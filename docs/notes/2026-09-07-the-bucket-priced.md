# The cash bucket, priced: it eliminates 99.9% of forced selling and buys exactly none of the floor

Measured 2026-09-07, round 53. Tool: [`bucket_plan.py`](../../tools/bucket_plan.py) (new). Tests: 13 in
[`test_bucket_plan.py`](../../tests/test_bucket_plan.py).

Round 52 ended on a sentence that was an assertion: an all-equity withdrawal plan on SPY cannot be made certain at
any account size, and "only a different asset buys a floor". The natural response in any retirement forum is the
**bucket** — keep N months of spending in bills so you never have to sell equities in a crash. This round prices that
response on the archive, with the bill leg earning the record's own DGS3MO less SGOV's expense, withdrawals taken
monthly, expenses charged, every window simulated.

## The invoice, SPY, $500/mo on $100,000 over 20 years, 164 windows

| buffer | P(fail) | median terminal | median trough | forced sales (months/window) |
|---:|---:|---:|---:|---:|
| none | 28% | 2.10× | 0.53× | **237.3** |
| 6mo | 29% | 1.99× | 0.54× | 0.1 |
| 12mo | 32% | 1.87× | 0.55× | 0.1 |
| 24mo | 35% | 1.62× | 0.58× | 0.1 |
| 36mo | 37% | 1.39× | 0.60× | 0.2 |
| 60mo | **62%** | 0.82× | 0.64× | 0.2 |

Read the two columns on the right together, because they are the finding.

**The benefit is real and it is enormous.** Forced selling — the month the plan must sell equities because the cash
ran out — collapses from 237.3 months per window to 0.1. That is not a marginal improvement; the unbuffered plan is
forced to sell *every month by construction* (there is no other way to pay the cheque), and a 12-month buffer all but
eliminates it.

**And it buys nothing that keeps the plan alive.** Failure *rises*, monotonically, with every buffer: 28% → 32% at
12 months → 62% at 60. Across nine capital/target/horizon combinations and four buffer sizes — 36 comparisons —
**not one buffer reduced the failure probability**, and more than ten made it worse. At $250,000 funding the same
$500/mo, the unbuffered plan never fails at all (P = 0, consistent with round 52's $188,429 zero-failure threshold),
so the bucket has nothing left to protect and only cost to bring.

**The depth it buys is two points.** The median trough — how deep the account was ever seen in a typical window, the
hole an investor has to watch — moves from 0.53× to 0.55× at a 12-month buffer, for a 23-months-of-spending-per-window
reduction in forced selling and a 0.23× cut in median terminal wealth. To buy 7 points of trough depth you need a
36-month buffer, which costs a third of the ending balance.

## Why the folklore is wrong here, mechanistically

A bucket is not a return strategy. It changes nothing about what the assets pay; it changes only *when* the selling
happens. In this archive the failure mode is not a liquidity squeeze — it is a **withdrawal rate facing a decade that
could not pay it**. The plan dies when cumulative returns fall short of cumulative withdrawals, and no schedule of
selling changes that sum. Moving the sale earlier (into cash, funded at 3.8–5% while equities were the growing asset)
makes the shortfall arrive *sooner*: the buffer is a permanent short position in the return, which is exactly what the
monotonic column shows. A bucket protects against sequence risk, and sequence risk is only the binding constraint when
the plan would otherwise have survived — a treatment for a disease this archive does not show at these parameters.

## The policy debate inside the bucket is inert

Three refill policies were implemented — top-up-only, top-up-plus-sweep-back, and fixed-weight rebalancing — and a
no-trade band around the target.

| policy | band | P(fail) | median terminal | median trough |
|---|---:|---:|---:|---:|
| refill-only | 0% | 32% | 1.87× | 0.55× |
| refill-only | 90% | **30%** | **1.92×** | 0.54× |
| two-way | 0–90% | 30–32% | 1.87–1.92× | 0.54–0.55× |
| constant-weight | any | 32% | 1.87× | 0.55× |

Two-way and refill-only **agree to the dollar at every band**, because the sweep-back leg can never fire: cash rises
above its target only if you are not spending it, and a plan whose withdrawals outrun the bill yield cannot accumulate
a surplus. You cannot sweep back money you are living on. Constant-weight ignores the band by construction. With a
band as wide as the bucket, all three policies are one policy: hold a small cash weight and trade it rarely. The band
is the only knob that moves anything — 32% → 30% and 1.87× → 1.92× — and it moves them for one reason: it leaves more
money in equities longer, which is the same lever as a smaller buffer seen from the other side.

## What the bucket actually costs, in closed form

In a flat market with no equity expense and no bill yield, the ending balance is capital minus spending minus
**SGOV's expense on the bucket**, and the last term is exact: `0.0009 × buffer × years` — $27, $54, $108, $162 for
6/12/24/36-month buckets over a decade, to the cent. That is now a test. My first draft of that test predicted no
leak at all and measured a $54 shortfall on a 12-month bucket: not a bug, but the price of the wrapper, which had not
been written down anywhere in this repository before.

Two arithmetic guards came out of the same file. A buffer larger than the capital ($120,000 of cash inside a
$100,000 account) is now **refused rather than simulated** — left alone it would have produced a negative equity leg
and a probability table built on a sign error. And a destroyed window reports its trough at zero, because a run that
stopped in month 201 cannot contribute a full 240 months of forced sales to an average: the archive mean is 237.3, and
the identity "forced = every month" holds only on surviving paths, which is where it is now pinned.

## Checks

13 tests, 1.3 s, offline: the flat-market drag identity at four buffer sizes; the buffer-vs-capital refusal raising
rather than computing; conservation (a bucket cannot create or destroy money); refill-only ≡ two-way at three bands;
constant-weight band-invariance; monotone terminal cost; P(fail) never reduced anywhere in a 36-cell grid; the trough
gain pinned between 0 and 5pp while forced sales fall >50×; and the paired (equity, cash) window count matching
`plan_survival` and `required_edge` exactly, so three tools slicing one record agree on what a window is. Two
first-draft assertions were wrong — both mine, both recorded above. Full suite **1651 passed** (collected first:
1638 + 13). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
