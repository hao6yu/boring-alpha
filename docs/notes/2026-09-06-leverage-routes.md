# The cheap way to lever is not the cheap way: at 1.25× a fund's own leverage loses at any interest rate

Priced 2026-09-06, round 33. Tool: [`leverage_routes.py`](../../tools/leverage_routes.py), tests
[`test_leverage_routes.py`](../../tests/test_leverage_routes.py) (10, 0.04 s, no data load).

## Why this round exists when the archive says everything already

Rounds 29 and 30 left one plan in the repository that beats the index under honest costs, and it needs a broker to
approve a margin agreement, maintain it, and reprice it at will. That is a problem the goal does not have to have.
A leveraged ETF delivers the identical exposure with no approval, no agreement, and no taxable-account position —
which matters at $20,000, and matters absolutely in an account where margin is not available at all. Every round
since 29 has described the surviving plan as "a loan, not a model," and not one of them checked whether the loan
is actually the cheap way to buy the thing. It is the right answer for the wrong reason until you price the
alternative, so this round priced it.

## The arithmetic is about what the rate is charged on

The intuition is that 0.95% is small and margin at 4.90% is large, so the fund wins. The accounting is:

| | charged on | all-in cost per $ of exposure | on a $25,000 book at 1.25× |
|---|---|---:|---:|
| margin at the broker | the borrowed part only | **0.98%/yr** | **$245/yr** |
| a fund's own leverage | the whole position, plus a dealer's funding | **1.63%/yr** | **$406/yr** |

**The loan is cheaper by 0.65% of exposure — 66% relative, $161/yr on a $25,000 book.** The reason is a
denominator, not a fee schedule: a borrower pays interest on `L − 1` per dollar of equity and nothing on the rest,
while a fund pays its management fee on the *entire* position and *also* pays a dealer to hold the leverage it uses.
The fund is paying for the same funding the loan is paying for, and adding a fee on top.

## The crossover, and the direction that surprises

Solving `(L−1)·b + L·er = (L−1)·posted` gives **b\* = posted − swap − L·er/(L−1)**, and the sign of that number is
the finding:

| leverage | dealer swap | the fund wins below | read |
|---:|---:|---:|---|
| 1.25× | 0.00% | **0.15%** | only in a zero-rate regime |
| 1.25× | 0.50% | **−0.35%** | **never, at any interest rate** |
| 2.00× | 0.50% | 2.50% | wins in about half the record |
| 3.00× | 0.50% | 2.98% | wins in 56% of months, and today |

At 3× the fund genuinely is cheaper — by 0.07% of exposure, a sliver, not a rout. So the crossover runs the wrong
way from intuition: **the fund is a better-value unit of leverage the more leverage it holds**, because the same
fee gets spread across more exposure while the loan's interest keeps growing linearly. That is an arithmetic
property of the two wrappers, not advice to lever harder — the same maths that makes 3× cheap per unit is what
makes it dangerous in a 60% drawdown, and round 30 measured that window directly.

## The line the cost table cannot print — and the number under it that was wrong

Volatility drag is not a fee and does not appear in an expense ratio. This note's first draft quoted the
textbook term `−(L−1)·L/2·σ²` as **−0.40%/yr at 1.25×** and moved on, which was the right instinct executed with
the wrong instrument: that formula is a local, continuous-time approximation, and the archive holds 8,458 daily
sessions, so the quantity can be *computed* rather than approximated. Round 34 did exactly that
([`daily_reset.py`](../../tools/daily_reset.py)) and the approximation turned out to be nearly useless outside
the aggregate:

| window | vol | 1× | 3× daily reset | actual path cost | formula said |
|---|---:|---:|---:|---:|---:|
| full record 1993-26 | 18.5% | +10.87% | +22.80% | −9.82%/yr | −10.31% |
| bear 2022 | 24.2% | −18.24% | **−54.24%** | −36.00%/yr | −18.05% |
| crisis 2007-09 | 29.8% | −5.66% | −35.83% | −18.85%/yr | −7.85% |
| **calm 2017** | 6.7% | +21.80% | **+78.18%** | **+12.77%/yr** | −1.36% |

The formula was within half a point on 33 years and wrong by **18 points in 2022 and 14 points in 2017** — and
the 2017 error is the one that indicts it, because the realised path cost there was **positive**: a 3× fund
returned 78% against an index's 22%. In a low-volatility uptrend the daily reset is a *tailwind*, since every up
day raises the base the next day's leverage applies to. A quantity that changes sign depending on the path is not
a cost to be quoted; the aggregate −9.82%/yr and the calm-market +12.77%/yr are the same mechanism measured in
two different regimes, and neither is the other's bound.

The correction does not overturn this note's conclusion — the loan-versus-fund cost gap is fees and funding,
which the path term is entirely separate from — but it moves the warning. The route gap is the one with a decision
attached: the same 3× exposure held with **monthly** rebalancing earned more than the daily reset, because a
margin account's fixed notional between rebalances lets realised leverage fall into a fall instead of buying more
of it.

> **Corrected in round 37, on two counts.** The figures this paragraph published — **+3.54%/yr over the record** and
> **+6.40%/yr in the corona year** — were each a *single* start day out of the 21 that cadence permits, selected by
> where a loop beginning at index zero happened to land. Averaged over all 21 start days the record gain is
> **+0.91%/yr**, and the corona figure reverses to **−17.96%**: the average monthly start loses 18 points to daily
> rebalancing in exactly the window that was meant to demonstrate the benefit under stress, and the worst start
> loses 110 points. Two of six regimes flip sign. See
> [`2026-09-06-cadence-luck.md`](2026-09-06-cadence-luck.md). The conclusion of this note — that a fund's own
> leverage is not the cheap route — is untouched, because it never depended on the cadence figure.

## What changes in the project's record

The ledger's 1.25× row stays as it is — it is priced on the margin route, which is the cheaper one and the one
whose drawdown has actually been measured. What changes is the sentence attached to it. "A loan, not a model" is
still true, but it was quietly also claiming *no alternative exists*, and now one does: the same exposure is
available without a margin agreement for roughly $161/yr more on a $25,000 book, plus a path cost that changes sign with the regime. At this account size that is about $13 a month to not need a margin agreement. Whether
that is a good trade is a question about the account, and the archive has now said everything it can about it.

## Checks

10 tests, 0.04 s, no data load, deliberately arithmetic-only so a wrong sign fails rather than a number drifting:
a loan charges `(L−1)/L` of the rate and **zero when unlevered**; a fund's fee per unit of exposure is `er` at every
leverage, which is the fact the crossover turns on; **the crossover must be negative at 1.25× with a paid dealer
and strictly increasing in leverage**; at 3× the fund must win but by less than 20bp; and the drag term must be zero
at 1.0×, superlinear in leverage, and beyond −2% at 3× and 30% vol. Full suite: **1495 passed, 233 subtests**.
`journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
