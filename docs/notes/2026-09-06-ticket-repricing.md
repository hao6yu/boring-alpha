# Re-pricing the ticket against its own accounting: the one plan still standing is a loan, and it is not the one the ledger was scoring

Measured 2026-09-06, round 29. Edits to [`monthly_ticket.py`](../../tools/monthly_ticket.py) (a printed caveat)
and [`action_ledger.py`](../../tools/action_ledger.py) (a missing row), tests in
[`test_action_ledger.py`](../../tests/test_action_ledger.py).

## How this round happened

Round 28 published a ledger whose second row was the cheap share class and whose verdict was that only the
idle-cash switch was actionable. `monthly_ticket.py` — the repository's only *executable* artifact, the thing
that prints an order sheet — was simultaneously printing **+136 bps of NAV a year, +$23 a month at $20,000**,
for a leveraged plan the ledger did not contain. Two files in one repository, one claim each, no note explaining
the difference. That is exactly the failure a summary table is supposed to prevent, so the table was checked
against the thing it summarised.

The two claims were **not in conflict, and neither was wrong.** They score different portfolios:

| book | mean weight | what it holds | excess vs index, sweep cash + posted 4.90% borrow |
|---|---:|---|---|
| the paper book's vol-target rule, cap 1.3× | **1.023** | mostly equity, idle cash ~27% of the time, occasional borrowing | **−0.25%/yr  −$4.10/mo** |
| the ticket's constant 1.25× book | **1.250** | always 1.25×, never idle, always borrowing | **+1.63%/yr  +$27.24/mo** |

The vol-target rule spends roughly a quarter of its life in cash that the sweep under-credits, which is where
round 25's ~0.79%/yr financing subsidy came from and where the −$4.10 comes from. A *constant* leverage book has
no cash leg at all to be under-credited: it pays interest on a fixed loan and is simply long 1.25× the equity
premium, which on this archive's realised returns is worth +1.63%/yr after paying 4.90% for the money. The
ledger had a row labelled "the rule as configured" that a reader could easily take for the ticket's policy. It
now has both rows, with the distinction in the caveat text.

## The corrected order of things, at $20,000

| action | $/mo | variance | is it a bet? |
|---|---:|---|---|
| move idle cash out of the default sweep | +46.12 | none | no — a rate and an arithmetic difference |
| **a constant 1.25× book at a posted desk rate** | **+27.24** | substantial | **no — it is a loan** |
| hold the cheapest share class | +1.07 (r38: 25.00 was the noise floor, not this) | none | no — it is the fee, certain and tiny |
| reinvest distributions promptly | +0.01 | none | no, and nothing to do |
| the vol-target rule, cap 1.3× | −4.10 | substantial | yes |
| the same rule unlevered, cap 1.0× | −21.15 | substantial | yes |
| nine-sleeve momentum rotation | −231.00 | substantial | yes |

Two conclusions, and the second one is the goal talking.

**The positive rows are all the same kind of thing.** The idle-cash switch is a rate you are not being paid. The
1.25× plan is a spread you are capturing by borrowing at 4.90% to hold an asset that returned 10.78% on this
archive's money-weighted basis. The share class is a fee you are overpaying. None of them is a forecast, and the
two biggest are the two that require no view whatsoever. That is what 29 rounds of this repository have
distilled to: **the edge is in the balance sheet, not the signal** — which is r25's rule ("a levered strategy is
a loan application") turned from a warning into the ranking.

**The ticket's caveat had to be rewritten before it could be published, because the first version of it was the
same conflation.** The warning first went in reading "this assumes the cash leg earns the bill curve, and under
honest financing the same book is −$4/mo." For a constant-1.25× book that is false: the −$4 was measured on the
*vol-target* rule. Writing it would have contradicted round 25 from inside round 11's own tool. What is actually
true is narrower and is what now prints: the cash-leg assumption is irrelevant to this policy (+1.63%/yr under
both cash legs, identical to the cent, because there is no cash leg), and the number that matters is the borrow
spread, which the ticket already solves against every posted desk and which fails on four of the eight.

## Checks

`test_action_ledger.py` gains the row-count and shape assertions it already made — the positive rows are asserted
to be exactly three and all cost-shaped, and adding the 1.25× row deliberately broke that test so it had to be
argued with rather than edited, which is the mechanism working: it is now four positive rows, and the new one is
allowed because it is a financing decision rather than a signal. `--verify` re-derives the vol-target row from
`unlevered_timing.run()["mo"]`; the 1.25× row is re-derived by the same call with `static=1.25`, which is why the
row cites round 29 and not round 11. **7 tests, 0.2 s** — one fewer than round 28's seven, because two of
round 28's assertions died this round and were replaced rather than padded back: `idle cash beats every positive
stochastic row combined` is no longer true once a loan is priced honestly, and it now asserts the narrower claim
that survives (`idle cash beats the largest row that asks you to hold a view`). The row-count assertion was raised
from 3 positive rows to 4, and its docstring says why a fifth would have to be argued in. Full suite: **1462
passed, 233 subtests**, collected as 1462 — 1469 is what a round that had added one row and deleted one test
*while editing nothing else* would have produced, and the runner says 1462, so 1462 is what is written.
`journalctl verify`: chain intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in.
