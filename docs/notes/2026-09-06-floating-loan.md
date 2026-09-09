# The loan, repriced the way a broker bills it: the headline survives, the binding window does not

Measured 2026-09-06, round 30. Tool: [`floating_loan.py`](../../tools/floating_loan.py), tests
[`test_floating_loan.py`](../../tests/test_floating_loan.py) (6).

Round 29 left exactly one plan standing: a constant 1.25× book, **+1.63%/yr over the index** under sweep cash and
a posted 4.90% desk rate. That number and every cousin of it came from round 11, which priced the loan at a
**fixed** posted rate — and margin is not billed as a fixed rate. A desk quote is a spread over an index, and this
archive contains the index: the same DGS3MO curve every backtest here credits the cash leg with. So the surviving
plan's single most load-bearing input had never been varied, and a leveraged long-equity book *is* short a rate,
which is the kind of thing a plan should not discover in year four.

## The calibration, so the comparison is honest

Today's posted menu rate minus today's bill curve: **4.90% − 2.88% = 202bp**. Both models therefore agree in the
month the account is being priced in and differ only across history. The check that this worked is visible in the
table: the floating-minus-fixed column is the **same number in every window**, +0.69% at 202bp, +0.44% at 302bp,
−0.06% at 502bp. It is constant because the difference is a spread arithmetic on a constant borrowed fraction
(0.25 of the book), not a market outcome — so any window where that column moved would be a bug, and the test
suite asserts it holds.

## Constant 1.25×, sweep cash, $20,000

| window | months | fixed 4.90% | floating curve+202bp | $/mo floating | max drawdown |
|---|---:|---:|---:|---:|---:|
| full record | 404 | +1.63% | **+2.32%** | +$38.70 | −59.7% |
| rate fall 2007-09 | 36 | −2.18% | **−1.49%** | −$24.87 | **−59.7%** |
| zero-rate 2012-19 | 96 | +2.39% | +3.08% | +$51.29 | −16.9% |
| covid 2020-21 | 24 | +4.54% | +5.23% | +$87.12 | −24.1% |
| rate shock 2022-26 | 57 | +1.96% | +2.65% | +$44.13 | −29.8% |

**The floating model looks better, and that is the trap rather than the finding.** The archive's rate history is
6%+ before 2007, essentially nothing from 2012 to 2021, and 5%+ from 2023 — so a floating loan was cheap for most
of the sample and expensive only in the part that matters to anyone starting today. Averaging those two regimes
into +2.32%/yr is the same category of error as a thirty-year backtest that spent thirty years in a bull market,
except here the variable is the cost of the money, which is the one thing the plan cannot diversify away.

The number that decides is the **binding window**: 2007-09, where the same book is **−1.49%/yr into a 60%
drawdown**. That is the row to underwrite, and it is not a bad row — a leveraged long-equity book was always going
to lose in a leveraged equity crash — but it is the row that says how big the position may be, not the 404-month
average.

## Stressing the spread, which a desk can do unilaterally

A desk can widen its own spread with the index unmoved, so the spread is the risk the plan does not control:

| spread over the curve | full record | 2007-09 window |
|---|---:|---:|
| 202bp (calibrated to today) | +2.32%/yr | −1.49%/yr |
| 302bp (+100bp) | +2.07%/yr | −1.74%/yr |
| 502bp (+300bp) | **+1.57%/yr** | **−2.24%/yr** |

At +300bp the floating model falls **below** the fixed one on the full record — the floating plan's entire
advantage over round 11's number is the decade of cheap money, and one desk decision erases it. At that spread the
full record (+1.57%) is worth less than the fixed-rate figure has been claiming, which is the sharpest way to put
the round's conclusion: **the loan's edge over the fixed-rate model is a regime gift, not a property of the plan.**

The drawdown column deserves a note of its own. Measured on this tool's own basis — monthly, net of costs, from
the sequence a constant 1.25× book actually lived through — 2007-09 is **−59.7%**, against **−50.8%** for the
unlevered comparator in round 26's identical measurement. Earlier notes quote −52.7% and −52.8% for the same index
from the funded simulator, which compounds a deposit schedule rather than a balance, so the figures are not
interchangeable; what they agree on is that 0.25 borrowed dollars adds roughly seven points of peak-to-trough
against a benchmark that already takes a fifty-point drawdown.

## What changes in the project's record

Nothing was disproved and one label was wrong. `action_ledger.py`'s 1.25× row cites round 29's fixed-rate figure,
which remains the honest *conservative* number — floating prices higher on average and lower in the window that
matters, so the fixed model is the right one to sign against. The row's caveat now has to be read as "priced at a
fixed posted rate", and the drawdown printed beside it belongs to the *window*, not the average: **−59.7%** is the
2007-09 path, against −50.8% for the unlevered index. That is the cost of 0.25 borrowed dollars, and it is the
first number in this project larger than the index's own worst fall.

The goal asks for a model that earns more each month than the index. This plan does that in four of five windows,
by borrowing, and loses in the one where everyone is already losing. Whether that is a plan or a leverage decision
wearing a costume is a question about the account, not about the archive.

## Checks

6 tests, 0.5 s, offline. The calibration must be positive and under 600bp; an **unlevered book must earn exactly
zero excess under both financing models** (the identity that proves the financing model touches only financing,
and the same class of control that caught the comparator-expense bug in round 26); the two models must agree inside
1.2%/yr in the window they were calibrated to; a wider spread must always hurt a borrower, monotonically at 202,
402 and 602bp; the penalty must grow with leverage; and the full record must be positive while 2007-09 is negative
with a drawdown beyond −50%, which is the file's whole claim held to account. Full suite: **1468 passed, 233
subtests**. `journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
