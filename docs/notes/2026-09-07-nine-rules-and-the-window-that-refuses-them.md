# Nine rules and the window that refuses them

Measured 2026-09-07, round 74. New tool: [`rule_search.py`](../../tools/rule_search.py). Tests: 16 in
[`test_rule_search.py`](../../tests/test_rule_search.py).

Round 73 named the binding constraint and it is not "find a better shelter": on the window every fund shares — 2011-06-24
on — the MA200/IEF construction loses to holding the fund by about $159 a month per $100,000. So this round went looking for
a rule that clears it, and it went looking in the way that survives being read later: the grid and the pass rule were
written into the file **before the first run**, the pass rule demands the bar on *both* the long record and the recent
window at both readings, and the tool prints the family's own spread so the size of the mining is visible on the same page
as any winner. The nine rules were chosen to attack the specific way the incumbent loses — standing aside during rallies —
not because any was expected to win.

| rule | Δ long | Δ recent | Δ recent, end-of-month | duty | switches | verdict |
|---|---:|---:|---:|---:|---:|---|
| ma200 (incumbent) | +130.46 | −159.06 | −357.91 | 14.6% | 24 | fails the recent window |
| ma100 | +97.86 | −405.79 | −535.46 | 20.7% | 38 | fails |
| ma50 | −116.42 | −457.82 | −630.77 | 27.7% | 68 | fails |
| ma200_band (±2% hysteresis) | +36.00 | −257.88 | −132.65 | 13.0% | 14 | fails |
| **ma200_slope** (in while the average rises) | **+331.23** | **−111.05** | −188.34 | 6.5% | 10 | fails |
| mom12 | +79.97 | −423.18 | −401.61 | 12.0% | 14 | fails |
| mom_12_1 | +176.78 | −178.81 | −354.57 | 10.8% | 16 | fails |
| voltarget (10% target, half-units) | +53.54 | −435.76 | −299.17 | 22.1% | 66 | fails |
| dd_stop (out 15% below 12m peak) | **+258.21** | −117.21 | −188.04 | 4.4% | 10 | fails |

**Zero of nine clear the recent window.** The family spans −$457.82 to −$111.05 there, a spread of $346.77 — printed by the
tool beside the verdict, because a grid that reports only its winner is a lottery result wearing a conclusion.

## Why nothing in this family can win there

On the recent window the fund's own failure rate is **0.0%**, so there is no insurance payout to collect and every dollar of
capacity has to come from return. Every rule above holds Treasuries some of the time, through the best fifteen years the
index has had, at a shelter whose yield was near zero for most of them — so each one has *less* return than the fund, and on
a window with no failures, capacity is return. That is not pessimism, it is the arithmetic of `safe_amount` on a
distribution that never touches the floor. Round 61 had already found 0 of 26 return-seeking configurations beating the
index on return; round 74 now finds 0 of 9 capacity-seeking rules beating it on the same window, from the other direction.
The two results are the same sentence: **within a single fund plus a shelter, rebalanced monthly, unlevered, at posted
costs, there is no rule in this archive that beats plain DCA on the recent window.**

## Three things the grid did say

**The incumbent is not the best of its own family, and saying so is the point.** `ma200_slope` — stay in while the 200-day
average is rising even when price is under it — earns **+$331.23/mo** on the long record, two and a half times the
incumbent's +$130.46, at less than half the duty cycle (6.5% vs 14.6%) and 10 switches instead of 24. It is the repair for
V-shaped recoveries: it re-enters on the slope rather than waiting for price to cross. It still loses $111/mo on the recent
window, so it does not pass, and it is not promoted. But "the current rule" is no longer defensible as *the* trend rule —
if this construction is ever resumed, this is the variant, and that knowledge only exists because the grid included rules
chosen to beat it.

**Trading less did not cost less.** The ±2% hysteresis band cut switches from 24 to 14 and made the recent window *worse*:
−$257.88 against −$159.06. A pinned test asserts the pairing so nobody re-discovers it as a virtue. The lesson is the same
one the duty-cycle column keeps teaching — the cost of this construction is not the trades, it is the months spent out of
the market — and hysteresis buys fewer trades precisely by staying out longer after the first exit.

**Volatility targeting is the most expensive way to hold less.** `voltarget` lost $435.76/mo on the recent window with the
*second-highest* duty cycle in the family. It is not a hedge with a nice property; on a withdrawal-capacity measure it is a
permanent partial de-risking that charges the full shelter cost for a fraction of the exposure, and it switches 66 times
doing it. Faster averages agree: ma50 −$457.82 at 68 switches.

## What the tests hold down

The centrepiece is not a number, it is a **differential test for lookahead**: for every rule, each month's decision is
recomputed from a record truncated on that month's own reading day, and must match the decision the full archive produced.
Nine rules, seven months each, one identical answer — a rule that peeks would fail this and every number-looking test
below it. Alongside it: a synthetic record where every price is identical, so the *only* thing that can happen to a plan is
the switch charge, pinning a chatty plan to `(1 − 2 bps)^40` and a calm one to `(1 − 2 bps)^1`; a fully invested plan tied to
the comparator to the cent (any premium between two identical plans is the pricing, not the market); every rule held to the
history it actually needs (21 sessions for a volatility step, 200 for an MA200, 252 for momentum) rather than a blanket
warmup; and the pass flag recomputed from each row's own numbers so a verdict cannot be typed in. The finding itself is
pinned too — nine rows, none passing, all negative — as a fact about the archive rather than as prose.

## Where that leaves the objective

Not "stop". The constraint that has to change is visible now, and it is one of four: **more than one equity regime** (the
grid never tried rotating between US equity, non-US, commodities and Treasuries, where a *return* difference can exist
without leverage), **a different cadence** (weekly, charged real spreads, which the monthly engine cannot represent),
**leverage** (refuted at posted rates in rounds 29-30, and would need a desk quote better than 2.02%), or **the objective
itself** — trading capacity for a lower failure probability, which is what the incumbent does buy: 0.0% vs 4.1% over 169
windows, for about $160/mo per $100k on the last fifteen years. The ticket now says the alternatives have been priced and
points at this file, so the next reader does not restart the moving-average-length search that just finished.

## Checks

16 tests, 10 s, offline; whole suite **1944 passed** (collected first: 1928 + 16); ledger chain intact. The grid costs 9.2
s to run, which is cheap enough that it can be re-run on every new archive snapshot rather than remembered.
