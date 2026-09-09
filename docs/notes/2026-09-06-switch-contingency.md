# The only income in this project that needs no borrowing pays $5.77 a month in a crisis

Measured 2026-09-06, round 44. Tool: [`cash_yield_gap.py`](../../tools/cash_yield_gap.py) (`contingency`,
`REGIMES`, `section_contingency`); tests [`test_cash_yield_gap.py`](../../tests/test_cash_yield_gap.py) (22, of which
7 new).

## Why this round went after the switch instead of another signal

Forty-three rounds have eliminated every price-based and news-based forecast the repository could build, and exactly
two actions are still standing:

- **borrow 25% and own the index** — beats the index on the mean, and r41/r43 measured that it *lowers* the monthly
  amount the account can guarantee;
- **move idle cash into a bill-fund ladder** — bounded, positive, no borrowing, worth **$39.85/mo** averaged across
  the archive and $46.12 at today's bill.

So the second one is the only candidate that satisfies "extra money each month" without a loan, and every figure ever
quoted for it has been **unconditional**: the mean, the median, the quartiles of the bill curve. r31 and r32
established the distribution. Nobody asked the conditional question, which for an income is the one that matters —
an income that arrives when the account is also being hurt is worth more per dollar than one that arrives while the
account is winning, and a plan whose stated purpose is a monthly amount should know which one it has.

## The answer, at $20,000 over 404 months

| | switch pays |
|---|---:|
| unconditional mean | **+$39.85/mo** |
| worst decile of market months | +$33.39 |
| best decile of market months | +$42.64 |
| months SPY fell > 5% | +$32.13 |
| months SPY rose > 5% | +$41.33 |
| correlation with SPY's monthly return | **+0.037** |

It is not a hedge. Its pay is *lower* in the worst market months than in the best, by about a fifth.

| episode | months | mean | worst month | vs the record mean |
|---|---:|---:|---:|---:|
| dot-com bear 2000-09…2002-10 | 26 | +$50.34 | +$24.39 | 126% |
| **GFC 2008-08…2009-06** | 11 | **+$5.77** | **−$1.32** | **14%** |
| **march 2020** | 5 | **+$5.46** | +$0.15 | **14%** |
| rate-raising 2022 | 12 | +$32.24 | +$0.35 | 81% |
| **QE bull 2010-2021** | **144** | **+$6.66** | −$1.65 | **17%** |
| VOO's whole record | 193 | +$23.90 | −$1.65 | 60% |

And in the five months the market did the most damage in 33 years:

| month | SPY | the switch paid |
|---|---:|---:|
| 2008-10 | −16.52% | **+$10.66** |
| 1998-08 | −14.12% | +$80.41 |
| 2020-03 | −12.49% | +$4.22 |
| 2009-02 | −10.74% | +$2.60 |
| 2002-09 | −10.49% | +$24.39 |

## What the mechanism is, and why the direction was knowable in advance

A bill-fund ladder earns the front end of the Treasury curve, which is the policy rate with a spread on it. The
policy rate is cut when an equity account is being damaged — that is the entire job description. So the one income
in this repository that requires no borrowing is a **standing claim on the central bank's normal, and crises are the
suspension of that normal.** It paid 14% of its own average through the GFC and through March 2020, and one of those
crises saw it pay *negative* money (−$1.32 in a month, when the ladder's roll yield went below the SGOV expense and
sweep drag).

The 1998 row is the honest counterexample and it is printed rather than dropped: the worst-but-one month in the
record paid **$80.41**, more than double the average, because in 1998 rates were high and the crisis was a long-term
capital problem, not a policy-rate cut. Conditionality runs through the *rate regime*, not through the market
direction, which is why the monthly correlation is +0.037 — essentially nothing — while the decile means still run
the wrong way. A hedge can be uncorrelated and still pay in crises; this one is uncorrelated *and* pays less in
crises, and the correlation alone would not have distinguished the two.

> **Amended in round 45: the six episode windows above were dated by the author, and that is a choice the archive
> can punish.** Round 34's cadence answer moved 11 points on a start offset, round 38's guarantee moved $26/mo on a
> stride; a hand-drawn `2008-08…2009-06` is the same species of input. Re-run with **no date chosen at all** — a
> bear month is one where the index sits more than D% below its own trailing peak, enumerated at D = 10/20/30%
> (`bear_sweep`) — the conclusion **strengthens**: pay falls monotonically with depth at every threshold
> (**+$27.19 / +$15.68 / +$12.87** against calm months' +$45.07 / +$44.48 / +$41.86), with nothing tuned. But a
> second thing surfaced that the hand-drawn table could not: the **month-weighted** and **episode-weighted**
> answers disagree ($27.19 vs $32.54 at 10% depth), because a 2-month episode paying $95.71 counts as one crisis
> and a 32-month episode paying $3.95 counts as one crisis. "What a crisis pays" has no fact of the matter behind
> it; only "what the months inside these episodes paid" does, and the weighting is a choice that belongs in the
> open. See [`2026-09-06-crises-enumerated.md`](2026-09-06-crises-enumerated.md).

## The number that should replace the headline

Over **144 of the last 404 months — a third of the record, and 2010 to 2021 in its entirety — the switch paid
$6.66 a month.** The $46.12 quoted at the top of `cash_yield_gap.py` is not wrong, it is a **regime price**: rates
went to zero for twelve years, came back for a two-year spike, and the archive's mean is mostly the years in between.
For scale, the whole window in which VOO exists — 193 months — paid the switch $23.90, 60% of the record mean, which
is the same era r39 found flatters levered equity. The two facts are the same years wearing different clothes.

So the honest statement of the goal's surviving non-borrowing income is:

> **$6.66/mo if the rate regime repeats 2010-2021. $5.77/mo if the next crisis repeats 2008. $32.24/mo in a
> rate-raising year. $46.12/mo today. $39.85/mo if the next 404 months resemble the last 404.**

That is a real, bounded, verified income stream, and it is a *rate view*, not a paycheck. Anyone who wants the second
one still has to borrow, and r41 measured that borrowing makes the guaranteed monthly amount smaller.

## Checks

22 tests in this file, 7 of them new, 0.9 s, offline: the conditional mean in the worst decile must sit **below** the
unconditional mean and below the best decile; the crash-month mean must sit below the surge-month mean; the
correlation must be pinned as **small** rather than negative, because the claim being refuted is about conditional
level and a test that asserted a negative correlation would be testing the wrong thing; both crisis episodes must pay
under a quarter of the record mean with the GFC pinned at $5.77 to the cent and its worst month negative; the QE-bull
row must cover ≥ 120 months and pay under 20% of the mean; the worst market month must still be October 2008 and must
still have paid $10.66; **every named episode must actually have found months** — a typo in a window silently deletes
the evidence, so the label sets are compared rather than counted; the "whole archive" row must reproduce the
unconditional mean to nine decimals, or the conditional and unconditional figures are not the same quantity; and
doubling the balance must double the dollars and leave the correlation bit-identical. Full suite: **1562 passed, 233
subtests** (collected before the run; my arithmetic predicted 1561 and the collection was right, the class has seven
tests). `journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.

> **Restated in round 47.** The spot bill yield quoted in this note (**2.88%**, and the **+$46.12/mo** built from
> it, and the "55th percentile of the record") was computed by annualising the last three monthly buckets of the
> cash curve — and the last of those was a **four-day stub**: the archive seals after a session, and the September
> 2026 bucket held trading days 1-4 only. Compounding a four-day accrual as a month pulled the spot down **103bp**.
> On complete months the archive's own last full month is **3.81%**, the three-month spot is **3.91%**, the switch
> is worth **+$63.34/mo** at $20,000, and today sits at the **65th** percentile — *above* the record median, not
> below it. Every distribution figure in these notes (mean $39.85, median $33.72, quartiles) moved by pennies;
> only the spot and the percentile it was compared against were wrong. See
> [`2026-09-06-the-seal-is-not-a-month.md`](2026-09-06-the-seal-is-not-a-month.md).
