# A figure wrong by ten times, in the document that gets obeyed, invisible to 2299 tests

Round 100. Changed: [`RUNBOOK.md`](../RUNBOOK.md) (correction), [`decision_sheet.py`](../../tools/decision_sheet.py) (friction line
derived, not typed), [`test_runbook.py`](../../tests/test_runbook.py) 13→16, [`test_decision_sheet.py`](../../tests/test_decision_sheet.py)
16→18, and the two places that repeated the wrong number ([`r97 note`](2026-09-08-a-cost-with-no-transaction-in-it.md), rule r97).

## What round 97 published, and what the arithmetic says

Round 97's finding was right and its headline figure was off by an order of magnitude. The sentence, in the runbook, in a note, and in
the standing rule list:

> the $175,786 (**0.87%** of paid in) between the band and the drift control contains no transaction at all

Paid in over the 193 month-ends is $2,020,000. `175,786 / 2,020,000` is **8.70%**, not 0.87% — the division was done against a paid-in
figure ten times its size, and printed three times. The dollars were always right, because they came out of the tool; the share was
mental arithmetic, and it landed in the one direction that makes a rebalancing policy look harmless: a tenth of the truth, in a paragraph
whose whole purpose was to argue that a policy's cost is bigger than its invoice. The corrected comparison, both halves from
`rebalance_cost.py` on the same window:

| cost of rebalancing the 50/50 tilt, over the record | as a share of paid in |
|---|---|
| the tickets, i.e. the spread the never-rebalanced book did not pay | **0.054%** ($1,091) |
| the policy — the same two funds with the band honoured instead of never traded again | **8.70%** ($175,786) |

**The policy cost 161 times the invoice for it.** Round 97's own rule says a ledger that itemises transactions prices the activity and
not the policy; this round found the repository doing the same thing to itself in prose, and the correction makes the rule's own point
161 times sharper.

`decision_sheet.py` had the same fact stated worse. Its friction line read:

> the bill for rebalancing monthly is 0.003-0.054% of paid-in and the *policy* is worth **10.4% of it**

Both numbers exist — 0.054% is the marginal bill, 10.4% is the *monthly* policy gap as a share of paid in — but the sentence attached the
second to the first as a fraction of it, which is inverted by two orders of magnitude, and it was untraceable to any function. The line is
now derived at print time and says which denominator is which:

```
     rebalance only past 5 points of drift, and know which cost is which. Over the record the bill for the tickets is 0.054% of paid in
     (0.003% over the last five years); what the *policy* of rebalancing cost — the same two funds with the band honoured instead of never
     traded again — is 8.70% of paid in, or 161 times the bill. Both recomputed from rebalance_cost.py when the sheet was built, and
     neither contains a transaction
```

## Why 2299 tests did not catch it, and what now can

Because prose is not a fixture. Every test in this repository checks a tool against data, or a tool against itself; the runbook is read by
a human and trusted by that human, and it had one hand-typed percentage in it whose generator no test ran. The fix is not to trust prose
less — it is to stop letting prose carry figures that have no command underneath them:

- `decision_sheet.py` computes the two shares from `rebalance_cost` each time it renders (memoised; the sheet gained no measurable time).
- `tests/test_runbook.py::TheProseReprintsItsOwnFigures` recomputes all four quoted friction figures from `rebalance_cost` and asserts the
  runbook prints each one **at its own rounding** — `f"{drift:.2f}%"`, so the test fails if the paragraph and the engine disagree by a
  digit, and passes on formatting rather than on tolerance.
- It carries its own negative test, built from this round's actual slip: put the old 0.87% back *as a share of paid in* and the scan
  rejects it, while still finding the true 8.70%. (It first tripped on the correction sentence, which mentions the old figure to record
  the correction — the scan is on the phrase, not on the digits, which is also the more precise claim.)
- `tests/test_decision_sheet.py` now fails if a `% of paid in` with a typed number in front of it appears anywhere in the renderer's
  source. Interpolated figures are fine; typed ones are the class of bug this round found.

The correction is disclosed rather than silently applied: the runbook paragraph says what it used to say and which way the error ran, and
rule r97 was amended in place with its own correction, because a rule that carries a wrong number is a wrong rule an operator will quote.

## Checks

**2304 passed, 239 subtests** — five new tests, of which one exists purely to prove the other three fire. Reconciliation worth recording,
because the two engines agree where the prose had not: `idealisation_tax` gives the marginal bill at 0.0540% and `secondary_bars` gives the
drift gap at 8.7023% — the runbook's 0.054% and 8.70% are those numbers at their printed rounding, and the five-year bill recomputes to
0.0026%, which the runbook's "0.003% ($18)" rounds correctly. Live state unchanged: five books, one anchor each, all chains verify, sealed
fees $0.00, first seal 2026-09-30.

*Round 100. 100 standing rules. A claim in prose is a claim with no command under it, and the runbook is the one document in this
repository that a person actually obeys — so it gets tested like code from here, starting with the numbers in it.*
