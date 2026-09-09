# The candidate re-opened and cleared the bar: +$123/mo at an equal floor, and its own mirror image dies

Measured 2026-09-06, round 20. Tool: [`income_frontier.py`](../../tools/income_frontier.py) (`--years 20
--floor 400`, `--years 10`, `--floor 700`), tests [`test_income_frontier.py`](../../tests/test_income_frontier.py)
(26 tests). Engine: [`withdrawal_capacity.py`](../../tools/withdrawal_capacity.py). Candidate definition:
[`paper.py`](../../tools/paper.py), imported verbatim through
[`policy_withdrawal.py`](../../tools/policy_withdrawal.py) — nothing retuned.

## Why this was worth re-running

Round 19 concluded that no trading mechanism in this repository raises a monthly income, and priced
**constant** leverage to prove it. Round 8 had already scored the pre-registered candidate — 18% vol target,
30-day window, 200-day trend gate, 30% floor, 1.30× cap, 5-session review — in withdrawal units, and it
**raised the worst-start floor on SPY from $379 to $518**: the only mechanism here ever to beat the Dominance
Rule on an income statistic. Round 19 never priced it. That was the wrong generalisation, made while writing a
conclusion sentence, and this round fixes it in the stricter equal-floor frame with three things round 8 could
not do.

**The bar, fixed before the first cell was computed:** at an equal floor and the same spending rule, the
candidate must pay a larger median than (a) the same sleeve held flat and (b) a flat weight at its own
average; the mirror image of its own path must lose to it; and it must do so at both horizons.

What changed since round 8, beyond the equaliser:

- **the band is zero for a path plan**, so every monthly move the policy asks for is executed and charged.
  Round 8 ran the index plan's 10% band — which lets a policy that wants 0.30× sit at 1.10× for free and books
  the difference as expense-free;
- **the borrow is priced at the April 2026 posted Public tier of 4.90% on average**, by setting the spread
  against the archive's *record-mean* cash yield (2.53%) rather than today's (3.51%). Priced against today the
  backtest borrows at ~3.9% average, a point under what a desk posts, in exactly the years the promise is
  hardest to keep. The candidate is in a borrowing month 68% of the time (mean weight 1.023, range 0.30-1.30).
- **four controls**, one of which is the candidate's own weight path read backwards.

## 20 years, $400/month promised, every start date on a fine grid (83 starts, 1993-02 to 2006-10)

| plan | feasible | median cheque | ×floor | worst start ends with | $20k account |
|---|---|---|---|---|---|
| cash (T-bills), fixed | ✓ | $400 | 1.00× | 20% | $80 |
| cash, guardrail | ✗ died 2004-06 | — | — | — | — |
| SPY, fixed | ✓ | $400 | 1.00× | 26% | $80 |
| SPY, guardrail | ✓ | $597 | 1.49× | **12%** | $119 |
| **candidate, guardrail** | ✓ | **$720** | **1.80×** | **66%** | **$144** |
| gateless (same policy, no trend gate) | ✓ | $622 | 1.55× | 34% | $124 |
| reversed (same weights, wrong months) | ✗ died 2000-04 | — | — | 0% | — |
| flat at its own average weight | ✓ | $593 | 1.48× | 11% | $119 |
| SPY 1.25× / 1.50× | ✗ every rule | — | — | — | — |
| QQQ | ✗ died 1999-08 | — | — | — | — |

**The candidate clears all four accusations**: +$123/mo over the same sleeve held flat, +$127 over its own
average weight, +$320 over the mirror image of its own path, +$98 over the same policy with its trend gate
removed. On the fixed cheque — where the median is *identical by definition* and only capital can differ — it
ends the worst start with **136% of the lump left** where the index leaves 26%. That is the same claim with the
spending rule taken out of it, and it is the strongest version.

Order of importance: the **trend gate is worth $98** of the $123 (gateless still beats SPY, by $25, on
average leverage of 1.109); the **timing** is worth $127 over the average weight (which is why this is not
disguised leverage — and note the *reversed* path has the identical mean weight and identical set of weights,
and dies); and the **guardrail** on top adds nothing to the candidate's *edge* but multiplies its *floor*,
1.80× versus the index's 1.49×.

Ten years tells the same story at a different size: +$103 / +$107 / +$123 / +$77 against the same four
comparisons. The constant-leverage rows stay Redundant (−$17, −$20) and stay disqualified at 20 years. This
result does not reopen the loan.

## Where the edge stops, so nobody has to discover it

- **$700 a month for 20 years — 8.4% a year — kills every plan in the table, candidate included** (died at a
  1997-08 start, after five forced sales). The mechanism buys a floor at a *modest* promise, roughly 4.8% a
  year of the lump. It is not a machine for affording a rich one. Even so, at that floor the candidate's
  worst fraction-of-NAV cheque is $362 where the index's is $188.
- **Scale, honestly.** These are dollars per $100,000 of lump. At the round-18 funded frame — $20k now — the
  candidate's edge is **+$21 to +$25 a month**, and at $50k, +$52 to +$64. Round 18 set the noise floor at
  $25/mo, being the size of the SPY-versus-VOO decision. So at a small account this edge is about one
  fund-choice decision a month: real, repeatable, and not life-changing. At $100k it is a car payment.
- **Nothing here is out of sample.** Same archive the candidate was built on; the forward journal is still one
  entry and $0.00 paid in. The pre-registered bar says *worth building*, not *worth buying*.
- **Monthly cadence.** The live book reviews every five sessions; this reviews at the month boundary, which
  understates responsiveness in both directions.
- Not measured: VTI and ITOT (records too short for a 20-year plan — the tool now prints "not measured", not
  "cannot promise"), and the candidate on QQQ at 20 years.

## Two defects found in the round's own machinery

- **A control copied its subject.** `weight_path` used one variable for both "which policy to compute" and
  "which control to return", so `"avg"` rewrote itself to `"candidate"` before the flat path was built. The
  control that exists to say *you could have just held this* returned the candidate and matched it **to the
  dollar** — $720 against $720. The honest reading of that table would have been "the average weight is as
  good as the policy", which is the exact inverse of the truth. The tool now refuses a flat control that is
  not flat and refuses a path that never moves; a test refuses a control equal to its subject.
- **The financing was priced against the wrong year.** Using today's cash yield as the base made a 20-year
  backtest borrow below the posted rate on average. Correcting it costs the candidate $4/mo of its $127
  edge — immaterial, and worth having measured rather than assumed.

## Audited the same day, and it did not survive intact

[`2026-09-06-sleeve-league.md`](2026-09-06-sleeve-league.md) prices this same rule on all five sleeves in the
archive. The income edge is +$123 on SPY and **+$3 on VOO** — VOO's record begins 2010-09 and contains no
decade worth protecting against, and on such records the guardrail's median sits on its own 2.00x ceiling for
every plan, which is why round 19's celebrated 1.99x row was the ceiling rather than a result. On QQQ the rule
buys feasibility instead of income: plain QQQ cannot make a $400/mo twenty-year promise from any start, and
the rule can. Read that file before quoting any number above.

## What this does to the goal

Twenty rounds and one table. The first thing in this repository that clears the Dominance Rule **in the unit
the goal is written in** is not a news feed (round 18: refuted by its own control, every direction negative)
and not a loan (rounds 7, 17, 19: Redundant, and disqualified outright at 20 years). It is a **rule** —
volatility targeting with a trend gate, which is arithmetic on realised variance and a 200-day average, no
forecast in it — paying +$103 to +$127 a month per $100k over holding the same fund, and ending the worst
decade with 66% of the lump where the fund left 12%.

The goal guessed short-term trading on news and trend. This says: the trend half is worth pursuing, the news
half is not, and the thing that makes the trend half *pay* is that it protects the withdrawal, not that it
beats the index. Next: put this candidate under the forward journal — the only artefact here that can say
whether any of it transfers — and measure it on VTI/ITOT as their records allow.

## Checks

26 tests, 4.3 s: the flat control is flat and is not its subject; the reversed path holds the same weights on
the same calendar; on a zero-return window a monthly-churning path ends strictly smaller than the same mean
held flat, and a path plan's band is 0.0 while an index plan's is 10%; the candidate beats all four controls
and keeps its promise; the constant-leverage rows stay disqualified; $700/mo over 20 years stays impossible
for the candidate too; the closing sentence is chosen by candidate-versus-own-sleeve and not by who tops the
table. Full suite: **1398 passed, 233 subtests**. `journalctl verify`: chain intact (1 entry), comparator spec
`100% SPY, fee 0.000945` unchanged.

**Superseded in part on 2026-09-06 (round 25).** Every figure above is priced on the paper book's own financing
accounting, which accrues the borrow at the archive's bill curve plus its 3bp execution spread. Charged at the
posted desk rate instead, the candidate's excess over its own fund is **−0.00%/yr** rather than +0.34%/yr, and
the 20-year gap to SPY narrows from +$123 to +$113/mo. The plan *ordering* in this note survives; the claim that
the rule earns more than the index does not. See
[`2026-09-06-sweep-repricing.md`](2026-09-06-sweep-repricing.md).
