# The ticket that can say no

Measured 2026-09-07, round 71. New tool: [`shelter_ticket.py`](../../tools/shelter_ticket.py). Tests: 14 in
[`test_shelter_ticket.py`](../../tests/test_shelter_ticket.py), 1 in [`test_paper_shelter.py`](../../tests/test_paper_shelter.py).

The stalest file in this repository was the one a person would actually run. `monthly_ticket.py` opened — still opens, on
disk — with "the only mechanism in this repository that beats plain DCA", about a 1.25x book, written at round 12. Rounds
29 and 30 withdrew that by charging the loan; round 61 found no return alpha anywhere; round 68 fixed what actually
survives. The recommendation and the artifact had drifted apart by fifty rounds, which is what drift looks like when
nobody has to act on the conclusions. So this round produced the sheet the settled construction should have had: one page,
the month's decision, the numbers at the capital in front of you, and refusals.

```
  sheltered-trend ticket · long record from 2002-08-01 · start-of-month reading · 10-year promise at a 5% failure budget

  1. THIS MONTH  (2026-09-04, trend read 2026-08-03)
     HOLD the equity sleeve (SPY/VOO) at 100%
     no leverage, no borrowing, no second position
     one switch when it flips: about 0.02% of the account in costs, plus 0.09% a year while it sits there

  2. WHAT THE PLAN SUPPORTS  (capital 100,000)
     this plan pays      567.22/mo   and failed in 0.0% of 169 ten-year windows
     plain VOO pays       436.76/mo   and failed in 4.1%
     the difference      +130.46/mo   = +30% more income
     the ceiling           775.00/mo   (the withdrawal at which the plan first stops beating the index)
     the rule was sheltered 19.6% of the days on this record

  3. WHAT IT IS NOT   — not a return alpha (round 61, 0 of 26 configurations); not a balanced portfolio: the same
     weights held statically with the other half in IEF pays 498.97/mo, so it is the rule doing the work, not a
     second asset sitting next to it.
  4. WHAT WOULD MAKE THIS WRONG — a shelter fee above the 0.35% charged (~$29/mo per extra 35 bps, on the 20% of days
     the plan is sheltered); a rule that stops switching; and the fact that a failure budget is a distribution over
     windows while one account lives one path.
```

The whole table is scale-proportional and the sheet prints it at whatever capital it is given: **$50,000 → $283.61 vs
$218.38; $100,000 → $567.22 vs $436.76; $250,000 → $1,418.06 vs $1,091.90** — the same +30% at every size, with the
ceiling scaling too ($387.50, $775.00, $1,937.50). The duty cycle arrived at **19.6%** through a new code path (the mean
of the daily weight series rather than round 66's record function), which is the second time that number has
independently reproduced itself. Cash instead of IEF is a legal request and is worth **$73.12/mo less**, matching round
66's figure exactly, from a different code path.

## Four bugs, all of them mine, all of them now tests

**The default payout compared two different accounts.** With no `--payout` the sheet took the plan's safe withdrawal
measured per $100,000 and tested it against the ceiling *scaled to the requested capital*: at $50,000 it asked whether
$567.22 fit under $387.50 and refused itself out of existence. A default has to be in the same units as the thing it is
compared against — the oldest kind of bug here and the one most likely to survive review, because it only appears at
capital sizes nobody was testing that day.

**Double scaling.** `measure_all` was handed the caller's capital and the sheet then multiplied by `capital/100k`
anyway, so the $200,000 sheet printed four times the safe amount. The fix is to measure on a $100,000 basis everywhere
and scale once, in one function, with a comment saying why: these figures are *not* exactly linear in capital, because
the promise contains an absolute floor — so scaling is a claim being made, not arithmetic being done, and it must be
visible where it happens.

**The live rule's failure mode was "sell".** `paper.shelter_weights` looked up the previous month's reading and, when
none existed, used `0.0` — meaning a rule that cannot answer answers *shelter*, which is round 45's defect (a missing
moving average reported as a decision) installed in the forward book's own rule. It cannot fire on the live book, whose
SPY history starts in 1993 and which always asks about the present; it fires immediately on a truncated record, which is
how I found it while writing the refusal test. It now returns no weights at all, the sheet prints
`the 200-day average does not exist yet on this record; the rule declines rather than guessing`, and
`paper.py step` exits with "insufficient history". A rule's failure mode is part of the rule even when the failure is
unreachable.

**The sheet misdated its own decision.** It printed "trend read 2026-09-04" — the last date in the file — when the
reading is taken on the first trading day of the *previous* month: **2026-08-03**. `shelter_weights` now returns the real
reading date and the live book's `show` prints it (`MA200 read 2026-08-03 (first day of the prior month)`). A sheet that
cannot name the price it acted on cannot be audited against it, which is the entire purpose of a dated decision.

## Refusals, because a sheet without one is marketing

The old ticket's best feature was that it could say no, at a measurable rate (the borrow break-even). This one has four
refusals, each exercised by asking for the thing it refuses: no 200-day average (above); a withdrawal past the ceiling,
which prints the ceiling instead of the number it was given — `900.00/mo is past this plan's capacity of 775.00/mo`;
a plan that clears the index by less than round 60's $25 bar; and a shelter the file has no price for. It exits **3** when
it refuses, so a scheduled run can tell issued from refused without parsing prose.

## The old sheet, kept and labelled

`monthly_ticket.py` still runs and its 18 tests still pass — the posted-rate menu and the break-even table are the only
evidence in the repository about what leverage costs at named desks, and rounds 29 to 32's conclusion depends on them. It
now opens with a SUPERSEDED block telling the real history and prints a banner before every ticket, suppressed under
`--json` so machine readers get clean output. Deleting it would have destroyed the record of a wrong recommendation, which
is the opposite of what a repository like this is for.

## Checks

14 new tests plus 1 in the paper-book file; whole suite **1893 passed** (collected first: 1878 + 15). Every number on the
sheet is re-derived from `correction_table.measure` rather than restated — one test asserts the ticket's plan row equals
the table's to ten places, so the artifact a person acts on cannot drift from the measurement — and the sheet's decision is
`paper.shelter_weights`, the forward book's own function, not a third copy of the rule.
