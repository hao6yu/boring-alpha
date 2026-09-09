# The fifth file that guessed, and the footer that said it had not

Round 103. Changed: [`rotation_search.py`](../../tools/rotation_search.py) (fee lookup sourced, footer rewritten as derived prose),
[`test_rotation_search.py`](../../tests/test_rotation_search.py) 19→21, [`four-files-four-answers…`](2026-09-08-four-files-four-answers-one-fact-what-a-fund-charges.md)
(amended). Nothing in the forward books moved; this is research-side pricing.

## Round 94 sourced the ratios. It did not rewire the lookups.

`rotation_search.py` is the battery that ranks candidate rules — the page whose verdict is "2 of 7 pass, and the best of them is beaten
by a static 50/50 control". Its fee lookup, written before round 94 and never revisited, was:

```python
FLAT_FEE = paper.UNPOSTED_FEE                                    # 0.0035
def fee(sym): return wc.EXPENSE[sym] if sym in wc.EXPENSE else FLAT_FEE
```

`wc.EXPENSE` is `withdrawal_capacity`'s **graded-universe** list: five sleeves that file chose to publish withdrawal tables for. Using
it as the definition of "has a known expense ratio" means a scope decision in one file silently set the fees in another. Three of this
battery's five legs were on the wrong side of it, and the direction was not random:

| leg | charged | posted | error |
| --- | --- | --- | --- |
| IEF (the shelter) | 0.35% | 0.15% | **over-billed 20 bps** |
| GLD | 0.35% | 0.40% | under-billed 5 bps |
| EFA | 0.35% | 0.32% | over-billed 3 bps |

The worst error sat on the sleeve the rules hide in. A study whose job is to decide whether a shelter is worth it, charging the shelter
double its real cost, is biased against exactly the thing the objective would use — and the same study grades policies against a marginal
bill of a few bps, so 20 bps is not a rounding note. And the page's own footer was telling the reader the opposite: *"the rotation holds
GLD and EFA, whose real expense ratios are not in the archive"* — false since round 94, printed in prose, in the same eight-round
pattern as round 102's refusal (`sleeve_table`, `correction_table`, and now here).

## What the correction moved, in dollars

Printed, not asserted: the whole grid was captured before and after.

* Largest cell move on the page: **+$3.17/mo** (`dm6_sq`, long window, +186.21 → +189.37).
* `dm12_ief` +0.69/mo, `dm12_wide` −0.13/mo, `dm6_sq` recent +1.94/mo.
* Verdicts: unchanged. Passes: still **2 of 7**. The control gap that condemns the best rule ($94.35) unchanged, because the control
  holds only SPY and QQQ, which were priced correctly all along.
* Where the figure reaches the decision sheet: `.best_rule.vs_spy_recent` **88.29 → 88.34** a month, five cents.

So the correction was worth a few dollars a month and changed nobody's verdict. It was still worth doing, for two reasons that r95
already states and this round re-proves: the *size* of an error only means anything once you know its *direction*, and all three errors
ran against the safe leg; and a page that misprices three of its five legs cannot be the page that settles whether a trading rule works,
whatever the dollars turn out to be. The honest summary is published rather than smoothed: the fee fix moved the ranking's numbers by up
to 1.7% and its conclusions by nothing at all.

## The pattern, and the guard

Five files, one fact, four rounds of discovering that "one sourced table" was a claim about a module and not about the call graph:

1. `paper.FEES` — fixed in r94.
2. `withdrawal_capacity.EXPENSE` — sourced in r94 (its short list is a scope decision, and now says so).
3. `correction_table.measure` — the gate asked the table in r102.
4. `sleeve_table.UNPOSTED` — the refusal became `REFUSED`, with asset-class reasons, in r102.
5. `rotation_search.fee` — this round.

`power_horizon.simulate` still carries a `.get(s, paper.UNPOSTED_FEE)` default, and it is genuinely unreachable: the book it scores is
`BOOK + (WITNESS,)`, every symbol of which `fund_fees` prices — asserted now rather than assumed, because "unreachable" is the sort of
claim that outlives the condition that made it true. `cross_section.EXPENSE` is `dict(fund_fees.FEES)` ✓. The footer's remaining
assumption — the 2 bps charged to switch into a fund — is now printed from `wc.TURNOVER_COST` instead of a typed numeral, and labelled
as an assumption, which is all an assumption is entitled to.

## Checks

**2316 passed, 239 subtests.** `test_rotation_search.py` went 19→21 (counted before and after, per r94): the guess pins are inverted
(every leg on the page must equal its posted ratio), a leg the table has not priced now raises `SystemExit` naming `fund_fees`, and the
footer is required to print the legs it used to misprice. `test_fund_fees.py` went 17→19 with the generalisation of this round: every fee
accessor in the repository is called and compared to the table for every leg it can name (`paper.FEES`, `cross_section.EXPENSE`,
`withdrawal_capacity.EXPENSE`, `rotation_search.fee`, and the union of their legs must equal the priced universe — so a leg nobody checks
fails the test), and wherever a guess default survives, the symbols the tool scores must all be priced so it cannot fire. Neighbour suites green: `test_decision_sheet`, `test_runbook`, `test_fund_fees`
(56 tests). Live state unchanged: five books, one anchor entry each, sealed fees $0.00, first seal 2026-09-30.

*Round 103. 103 standing rules. The measured answer to "did the wrong fees change the answer" is no; the measured answer to "were they
biased against the hedge" is yes, systematically — and a rule set you cannot price is a rule set you cannot rank.*

---

**Corrected in round 104, one round later.** This note said *"the control gap that condemns the best rule ($94.35) unchanged"*. It was
wrong, and the way it was wrong is the lesson: the before/after diff was printed with a six-entry cap per rule (`moved[:6]`), the numeric
cells filled the cap, and the verdict strings — which carry the gap — never reached the screen. The grid's own line now reads
**$92.94**, so the fee fix moved the gap by **$1.41** and this note's claim of "unchanged" was an artifact of a truncated print, not of the
data. Restated with the full diff, uncapped: verdicts and the pass set unchanged; every dollar figure on the page moved by up to $3.17;
the control gap moved by $1.41. A diff with a cap is a diff with a cap, and nothing outside it is an all-clear.
