# The premium on stepping aside: $21 a month on the median decade, $109 on the worst one, and $0 if you are brave at the bottom

Measured 2026-09-06, round 22. Tool: [`de_risk_premium.py`](../../tools/de_risk_premium.py) (10-year and 20-year
windows, disjoint chains), tests [`test_de_risk_premium.py`](../../tests/test_de_risk_premium.py) (10).
Twenty-one notes have quoted what the trend-gated vol target *pays*. This one prices what it costs.

## Why this was the next number to compute

Rounds 20 and 21 established the rule beats holding SPY at an equal floor by $103–123/mo per $100k, and that
the result is a 2000–2002 phenomenon that does not transfer to VOO's record. Both notes quoted the payout of
the protection. Nobody priced the **premium** — and a protection with an unpriced premium is not a decision,
it is a recommendation.

The premium has to be measured in ending capital, because the equal-floor frame fixes each rule's median cheque
by construction (round 19): once the cheque is equalised, capital is the only place a rule can show up.

    difference(start) = what's left under the rule − what's left holding the fund
                        same cheque, same horizon, same expense, same turnover charge, same posted borrow rate

## Two things fixed before any number was computed

1. **Overlapping windows are not independent bets** (standing rule r15). 143 ten-year starts on a 33-year
   archive re-use 2008 forty-five times. The headline is a **non-overlapping chain**; the grid is detail.
2. **The buy test is against the cheapest competing decision, not against zero**: round 18's noise floor —
   $25/mo at a $20k account, the value of choosing SPY over VOO. A premium bigger than that is a worse use of
   the account than a spreadsheet cell.

## The premium, at a $400/mo promise per $100k, restated at the $20k account that exists

| sleeve | horizon | independent bets | rule cost money on | median | p10 | worst start |
|---|---|---|---|---|---|---|
| SPY | 10y | **3** | 1 of 3 | **+$21/mo** | −$17/mo | −$17/mo |
| SPY | 20y | 1 | 0 of 1 | +$31/mo | +$31/mo | +$31/mo |
| VTI | 10y | 2 | 1 of 2 | +$8/mo | −$24/mo | −$24/mo |
| VTI | 20y | 1 | 0 of 1 | +$43/mo | +$43/mo | +$43/mo |
| QQQ | 10y | **2** | 1 of 2 | **−$68/mo** | −$193/mo | −$193/mo |
| QQQ | 20y | **1** | 0 of 1 | +$78/mo | +$78/mo | +$78/mo |

The same windows on the dense grid, where a decade is counted many times — kept here because it is the number
that reads like a sample and isn't: SPY 10y median +$22, p10 −$37, worst −$109 (143 starts); SPY 20y median
+$33, p10 +$20, **worst +$10, on every one of 83 starts**; VTI 10y median +$15, worst −$134; QQQ 10y median
−$59, worst −$200, with the fund itself dying on 5 of them.

## Where the premium actually sits, which is the finding

The six most expensive ten-year starts on SPY: **2009-04 (−94%), 2009-02, 2011-10, 2009-06, 2008-12, 2009-08**.
The six most profitable: 1994-10, 2001-06, 2001-02, 1995-02, 1994-12 (+46% to +57%). Same on VTI — worst
2009-03, best 2008-09.

So the premium is heaviest for **whoever puts the money in at the bottom and holds through the bull that
follows** — the person who invested in 2009 was rewarded for exactly the reflex the rule asks for, and then
paid for it for a decade. And the protection pays off for whoever invested *before* a crash and stayed. The
rule is worth most to the person who already had the money in, and costs most to the person who timed it
well by hand. That is not a flaw to fix; it is the shape of the product, and any version of it that removes
this asymmetry would be removing the mechanism.

## What it decides

- **On a 20-year horizon the premium clears the bar in the archive's worst case, at the size that exists.**
  Median +$31/mo at $20k, and the *worst* of 83 overlapping starts is still +$10/mo. The rule never cost money
  on any 20-year start in the record, on SPY or VTI. It is not a 10-year product pretending to be safe; on
  10 years the p10 is −$17/mo on three bets, one of which it lost.
- **On a 10-year horizon it is inside the noise band on SPY (+$21 against a $25 floor) and outside it on QQQ
  (−$68, and −$193 on its unlucky start).** At the funded size and a decade, running this rule on QQQ would
  have cost more than twice what switching index funds is worth.
- **QQQ points two ways at once, and blending the two readings is the mistake to avoid.** Its archive holds
  exactly one 20-year window that can hold the promise (from 1999-04, the dot-com peak), and there the rule
  ends two lumps ahead of a fund that could not have paid $400/mo at all. Every later start lands in the 2010s
  bull, and the median over 46 of those is a shortfall of more than two lumps. One window is a fact about a
  protection working once; 46 overlapping starts are a fact about the premium. Publish both.
- **Three bets, not 143.** The honest headline for the whole file series is now: on a 33-year archive, the
  rule won two of three independent decades on SPY and one of two on VTI, and the loser cost $17 a month on
  $20,000. That is the size of the evidence, and it is why the forward book matters more than any further
  backtest.

## Consequence for the build, which was the opposite of what this note first said

The paragraph written here claimed the rule could not go into the forward book because the book's comparator
is a pinned 100% SPY spec and the rule needs its own. **That was wrong, and checking cost one command.**
`data/paper/model.json` already reads `model_key: "voltarget"`, which is this rule — vol-target 18%, 200-day
gate, 30%-1.30x, five-session review — pinned against the comparator `100% SPY, fee 0.000945`, which *is* the
P0 benchmark, on identical cash. There is no blocker. The book has been running the priced rule since the
afternoon of this very date, and on the last sealed session (Friday 2026-09-04) the rule's answer is
**128% SPY**: it wants a fifth more than the account, today, with the trend gate open and volatility low.

What the book lacks is not plumbing, it is months: one entry, $5,000 paid in, and its own report says
`underpowered — 23 more monthly entries, $5,000 more paid in required`. That is the honest state of the whole
file series, and the premium measured above is what to expect while waiting: a 20-year product whose worst
decade in the archive cost $17 a month on the account that exists.

## Checks

10 tests, 1.2 s, all offline against the sealed archive: the disjoint chain is provably disjoint and much
sparser than the grid; a fund that died can never score as a negative difference; misaligned windows raise
rather than producing a plausible number; the same terminal gap restates smaller over a longer horizon (the
$/mo belongs to its horizon); the distribution is ordered; and the shape findings are pinned as bands — four
of the six most expensive starts in 2008-09 and none after 2012, QQQ's grid median worse than SPY's, QQQ's
20-year chain still exactly one window. Full suite: **1415 passed, 233 subtests**. `journalctl verify`: chain
intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.

**Priced again on 2026-09-06 (round 25).** The premium above is what de-risking costs when the rule's borrowings
accrue at the archive's bill curve, which is how this engine has always charged them. At the posted rate the
rule's expected return over its own fund is zero rather than positive, so the premium is better read as what
protection costs against **not** holding the index, since holding the index is now the honest baseline. See
[`2026-09-06-sweep-repricing.md`](2026-09-06-sweep-repricing.md).
