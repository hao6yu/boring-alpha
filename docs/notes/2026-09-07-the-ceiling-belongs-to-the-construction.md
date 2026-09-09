# The ceiling belongs to the construction, not the signal: bills → IEF moves the trend plan's capacity from $725 to $775 a month

Measured 2026-09-07, round 65. Tool: [`shelter_test.py`](../../tools/shelter_test.py) (round 64's, extended). Tests:
24 in [`test_shelter_test.py`](../../tests/test_shelter_test.py), 6 of them new.

Round 63 found that the trend rule's protection has a ceiling — the withdrawal at which it stops being the safer pair
and becomes the riskier one — and quoted it at $750–825/mo per $100,000. Round 64 found the shelter was leaving income
on the table. Those are the same plan measured twice, so the capacity was re-measured under the better shelter, on the
same 246 complete months and the same 127 window starts, against the index on the same panel.

| shelter | safe $/mo at 5% failure | capacity ($/mo per $100k) | Δ vs bills | failure rates at that rung | crossings |
|---|---:|---:|---:|---|---:|
| cash (bills) | 593.13 | **$725** | — | plan 27.6% vs index 24.4% | 1 |
| IEF | 657.16 | **$775** | **+$50** | plan 25.2% vs index 24.4% | 1 |
| TLT | 683.33 | $775 | +$50 | plan 26.8% vs index 24.4% | **3** |
| IEF+TLT | 675.38 | $775 | +$50 | plan 26.8% vs index 24.4% | **3** |
| GLD | 816.63 | **$925** | **+$175** | plan 35.4% vs index 31.5% | 1 |
| DBC | 353.93 | **$225** | **−$500** | plan 0.8% vs index 0.0% | 1 |

The DBC row is the odd one: its first crossing sits at $225/mo, where neither plan is failing to speak of, so its
"capacity" is a statement about a drag rather than a risk turn — it is the riskier pair almost as soon as anything is
withdrawn, which is the same fact its −$239/mo of income and 22.8% failure rate said last round, told from the other
end.

The bond shelter buys **two grid rungs** of protection capacity — a 7% lift — on top of its +$64/mo of income. Gold
buys seven rungs (+24%) and is the same second bet it was last round. Commodities take away twenty rungs. So a capacity
is not a property of a trading rule that can be quoted once and reused: it belongs to the construction, signal and
shelter together, and any change to either end of the account moves it.

**The combined figure, for the record:** $100,000 in, trend rule, shelter in short Treasuries at a pessimal 0.60% fee
— **$657/mo** of withdrawal inside a 5% failure budget (round 58's bills figure was $593.13), and the plan stops being
the safer pair above **$775/mo**. Scaled to $250,000: **$1,643/mo** safe, ceiling **$1,938**. Homogeneity is the same
argument round 63 tested, and the same test applies to it.

## Two honesty notes about the numbers above

**The $25 discrepancy with round 63 is a convention, not a model change.** Round 63 measured $750 on 129 window starts
selected by start-year from the long record; this is $725 on 127 starts from the panel, which begins 2006-02-07 and so
misses the 2006 starts round 63 included. Nothing about the rule or the costs differs. If the two figures had agreed
exactly across different samples, that would have been the thing to worry about (round 58's rule).

**A ceiling this high is not a comfort zone.** At the bills capacity of $725/mo, the plan already fails in **27.6%** of
ten-year windows and the index in 24.4% — the capacity is the point where the *relative* ordering turns over, deep in
the steep part of the failure curve, not a level at which the plan is safe. What the capacity is good for is knowing
where the argument stops: below it, the trend leg is the risk-buyer's choice; above it, it is the thing that breaks.

## The oscillation, which was nearly a crash

The first version of this scan raised an exception when the failure-rate ordering flipped back. It should not have:
P(fail) over 127 windows is a step function moving in rungs of 1/127, and two steep curves can step over each other more
than once. **TLT and IEF+TLT each flip three times**, and the row now carries that count instead of smoothing it — a
reader quoting "+$50 of capacity" for TLT should know the ordering is not stable near the crossover, whereas for bills
and gold it is. The scan also stops rather than inventing a ceiling once the benchmark fails in every window (there is
nothing left to be safer than), and reports `None` — not zero — when no rung in the grid crosses.

## Checks

24 tests, 9.0 s, offline. Six new: a plan cannot be riskier than itself (`None`, zero crossings); the capacity lands on
a grid rung and inside the grid; IEF and GLD lift it and DBC cuts it; the crossings count is reported for what it is
(bills exactly 1, TLT more than 1, and the sweep never truncates below 40 rungs); `None` is exercised against a
benchmark fabricated to lose everywhere without dying, so it cannot mean "the loop never ran"; and the benchmark's
failure rate at the last rung quoted is under 100% while the plan's is over 10% — the ceiling must sit in the steep
region, or it is not the thing round 63 described. All of round 64's eighteen still pass, including the cash row's
$593.13. Full suite **1811 passed** (collected first: 1805 + 6). `journalctl verify`: chain intact, comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
