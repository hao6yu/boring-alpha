# The candidate on every sleeve in the archive: +$123 on SPY, +$3 on VOO, and a flag for rows that cannot rank anything

Measured 2026-09-06, round 21. Tool: [`income_frontier.py`](../../tools/income_frontier.py) (`--years 10`,
`--years 20`, `--floor 400`), tests [`test_income_frontier.py`](../../tests/test_income_frontier.py) (33).
This round is the audit of [`2026-09-06-candidate-frontier.md`](2026-09-06-candidate-frontier.md), which proved
one sleeve and — in the sentence before its checks section — let the proof stand as though it were general.

## Why

The goal is written as "beat voo, qqq". Round 20 proved the candidate on **SPY**, which is the same index as
VOO but a different fund, and said nothing about the other three sleeves sitting in the same archive. One
fund's result is one fund's result. So: same rule, same engine, same four spending rules, on every sleeve
`by_date` carries — SPY, VOO, QQQ, VTI, ITOT — each on its own calendar, at its own expense ratio, each with
the mirror image of **its own** weight path as the control. Nothing retuned; `SLEEVE_LEAGUE` is every symbol
in the archive, chosen by the loader rather than by me.

## What the audit found, at a $400/mo floor and the guardrail rule

| sleeve | starts | plain fund | candidate | gap vs its own fund | reversal control | flag |
|---|---|---|---|---|---|---|
| SPY, 20y | 83 | feasible, $597 | **$720** | **+$123** | dies 2000-04 | discriminating |
| VTI, 20y | 32 | feasible, $699 | $732 | +$33 | survives, $587: **−$146** vs it | timing yes, income inside band |
| QQQ, 20y | 46 | **dies 1999-04** | feasible, $653 | no comparator survives | dies 1999-04 ✓ | feasibility, not income |
| ITOT, 20y | 17 | feasible, $690 | $725 | +$35 | **−$18: cannot decide** | thin, control weak |
| SPY, 10y | 143 | $597 | $700 | +$103 | dies | discriminating |
| QQQ, 10y | 106 | **dies** | $762 | — | dies ✓ | feasibility |
| VTI, 10y | 92 | $793 | $790 | **−$3** | +$32 | REDUNDANT |
| ITOT, 10y | 77 | $794 | $797 | +$3 | −$3 | **at the ceiling** |
| **VOO, 10y** | 37 | $797 | $800 | **+$3** | +$23 | **at the ceiling** |

**Only one row in this table has an income gap bigger than the noise floor: SPY.** On the fund the goal
actually names, over the years its record contains, the rule is worth **$3 a month per $100,000**. Round 20's
+$123 is real, and it is a 2000–2002 phenomenon: the edge appears on records long enough to hold two crises
(SPY from 1993, QQQ from 1999) and shrinks to a rounding on records that begin after the last one (VOO from
2010-09) — with VTI and ITOT in between, where the timing is measurable against the reversal (+$146 on VTI)
while the income consequence at this floor stays inside the band.

## The measurement lesson, which is the reason this note exists

A guardrail keeps half its cheque when triggered, so its median is capped at **twice its floor**. On a mild
record no start is ever cut, so the median sits exactly on that cap — and *every* plan on that record sits
there with it. Rows at 1.98×, 1.99×, 2.00× are then not a ranking of plans; they are the number 2.00 repeated.
The tool now flags any guardrail row above 1.97× as `NOT DISCRIMINATING` in the table and in the verdict, and
prints how many ranking rows are pinned there.

This applies backwards. Round 19's table reported VOO's guardrail at **1.99×** and I called that a sizeable
result; it was the ceiling, and VOO's 37 benign starts had never once forced a cut. Same for round 19's
"VOO clears, SPY does not" framing of the same record.

## A control has to be able to fail, and this one's power depends on where the crises sit

The reversal control decided round 20 — the same weights, same mean, wrong months, dying outright. On ITOT it
does not bite, and the reason is mechanical rather than mysterious. Mean weight through the crises:

| sleeve | record | candidate in 2008-09 | reversed in 2008-09 | candidate in 2000-03 | reversed in 2000-03 |
|---|---|---|---|---|---|
| SPY | 1993-2026 | 0.53 | 1.02 | 0.60 | 1.15 |
| QQQ | 1999-2026 | 0.55 | 1.12 | 0.41 | 0.84 |
| VTI | 2001-2026 | 0.53 | 1.09 | 0.75 | 1.16 |
| ITOT | 2004-2026 | 0.53 | **0.90** | — | — |

ITOT holds **one** crisis, placed near the middle of its record, so the mirror image happens to sit underweight
through it too. Reading a path backwards destroys timing in proportion to how far the crises sit from the
middle. The honest sentence about ITOT is therefore *"the control cannot decide this sleeve"*, not *"the
candidate fails here"* — and its gap, −$18/mo on ~13 starts, is inside the $125 noise floor anyway. Tests pin
the ITOT gap as **inside the band** rather than as a win, so a future change has to argue with it.

## What survives the audit, stated narrowly

- **Income edge:** +$103 to +$123/mo per $100k (≈ $21 to $25/mo at a $20k account) on the one sleeve whose
  record holds two crises 25 years apart, charged its own monthly turnover at the posted borrow tier, against
  holding the fund. On VTI and ITOT the *timing* is measurable — their candidates beat their own mirror images
  by +$146 and, weakly, lose by −$18 — while the income gap against simply holding the fund is +$33 and +$35,
  inside the band.
- **On QQQ — one of the two funds the goal names — the value is not income, it is feasibility.** Plain QQQ
  cannot keep $400/mo for 20 years from a single start date in its record and dies at 1999-04; the candidate
  keeps it from all 46 starts and ends the worst one with 37% of the lump. A promise that can be made versus
  one that cannot is a real difference, and it is not "beating" QQQ's return by anything.
- **On VOO, nothing measurable.** If the account is VOO and the horizon is the last fifteen years, this rule
  buys about what a fund swap costs to think about. It is insurance against a decade that fund's record does
  not contain — which is the honest reason not to buy it *and* the reason a 30-year holder might still want it.
- The loan remains Redundant (−$17, −$20/mo) and disqualified at 20 years. Twenty-one rounds, and the only
  mechanisms that have ever beaten the cheap default did so by **not being fully invested in bad years**.

## Checks

33 tests, 7.6 s, all offline against the sealed archive: a saturated row is flagged and a pair of them prints
`NOT DISCRIMINATING`; the VOO gap stays inside the noise floor and is flagged; the ITOT reversal gap stays
inside the band *and* SPY's reversal still loses by a mile; the mirror image holds its subject's exact weight
multiset and mean on every sleeve; a sleeve too short for the plan builds zero windows rather than a failure;
and `NOISE_FLOOR` is asserted to be round 18's `attention_bar.NOISE_FLOOR` × the ratio of the two capitals —
provenance as a test, not a comment. Full suite: **1405 passed, 233 subtests**. `journalctl verify`: chain
intact (1 entry), comparator `100% SPY, fee 0.000945`, $0.00 paid in. The forward book could not be advanced:
the archive is sealed through Friday 2026-09-04 and there has been no session since, which is the calendar
refusing, not the tool.
