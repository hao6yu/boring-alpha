# Where the stub reaches: it moved the spot 103bp and the guarantee exactly nothing

Measured 2026-09-07, round 48. Tool: [`withdrawal_capacity.py`](../../tools/withdrawal_capacity.py)
(`last_business_day`, `monthly_complete`); tests
[`test_partial_month_blast_radius.py`](../../tests/test_partial_month_blast_radius.py) (10).

## The question round 47 left open

The partial-month defect lives in `withdrawal_capacity.monthly`, which **eight tools** call. Round 47 fixed it
where it happened to be noticed — `cash_yield_gap.py` — and left the other seven reading a series whose last row is
four trading days of September dressed as a month. Either those numbers are wrong too, or something about the
statistics protects them, and "probably fine" is not a thing this repository is allowed to say after being wrong
about its own headline action by 37%.

So the blast radius was measured at each consumer, by forcing every tool back onto the raw series and diffing.

## Measured, at the numbers that carry the recommendations

| statistic | with the stub | dropped | movement |
|---|---:|---:|---:|
| guaranteed cheque, SPY 1.00× | $364.45 | $364.45 | **$0.00** |
| guaranteed cheque, SPY 1.25× | $317.58 | $317.58 | **$0.00** |
| full-history excess, 1.25× @4.90% | +1.1171pp | +1.1201pp | +0.003pp |
| benchmark CAGR, full history | 10.733% | 10.748% | +0.015pp |
| negative-month share at 1.25× | 39.1% | 39.1% | denominator only |
| switch, median month | $33.72 | $33.72 | <$0.01 |
| **switch, today** | **$46.12** | **$63.34** | **+$17.22 (37%)** |
| **spot bill yield** | **2.88%** | **3.91%** | **+103bp** |
| 16-year excess, 1.25× @4.90% | +2.180pp | +2.333pp | +0.153pp |

The pattern is clean and it is a rule, not a coincidence:

- **A minimum over windows cannot see the tail.** The guarantee is bound by the April-2000 window, which ends in
  2020 — six years before the stub exists. Its indifference is structural, and it is now pinned at exact equality
  (`assertEqual`, not a tolerance) so that if the binding window ever moves near the end of the record, this file
  fails and the reason is investigated.
- **Compounding over the full history dilutes one partial month to nothing:** 0.003pp of a 1.12pp edge, 1 part in
  370.
- **Anything anchored at the spot is the casualty**, because a spot is by definition the shortest window you can
  build, and the shortest window is the one that runs off the end of the data.
- **A truncated window is its own category.** The 16-year excess moved 0.153pp — fifty times the full-history
  movement — not because the stub is big but because dropping it **slides the whole 192-month window by one
  month**. That is round 39's era effect arriving sideways through a calendar artefact, and it is the reason the
  leverage recommendation is stated as a range rather than a point.

## The structural fix

`withdrawal_capacity.last_business_day` and `monthly_complete(series, factors, last_date)` now own the rule, in the
module all eight consumers already import, with one definition (`cash_yield_gap.last_business_day` is now an alias,
so the tests that name it still name it). `cash_yield_gap.cash_months` delegates. The rule is a rule, not a reflex:
`monthly_complete` keeps the final bucket when the seal lands on its last weekday, and there is a test for exactly
that, because a fix that always drops the last month is wrong in the opposite direction and would cost a month of
history at every month-end seal.

Two of the new tests could not be written the obvious way. Patching `monthly` can no longer reproduce the
contaminated spot — the fix removed the formula, not just the call — so the comparison is **formula against
formula**: the old three-month annualisation computed on the raw series, against `bill()` as it stands. A test that
reproduced the defect by patching the helper would have been testing the patch.

## Checks

10 tests, 1.0 s, offline: the sealed archive must end on a stub (asserting the seal is still 2026-09-04, so the
expectation retires itself the first time a month-end seal happens) and exactly one bucket must be dropped;
`monthly_complete` must keep everything on a month-end seal; the guarantee must be **identical**, not approximately
identical, at 1.00× and 1.25×; full-history excess within 0.05pp; the negative-month share within a point of 39.1%;
the spot must move by more than 50bp **and in the direction a four-day accrual can only move it — down**; the
16-year edge shift must be between 0.05 and 0.25pp, pinned on both sides so it cannot quietly become either nothing
or everything. Full suite: **1595 passed** (collected first: 1585 + 10). `journalctl verify`: chain intact,
comparator `100% SPY, fee 0.000945`, $0.00 paid in.
