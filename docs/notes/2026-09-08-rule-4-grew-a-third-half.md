# Rule 4 grew a third half: the corpus is an input, and inputs get revised

Round 98. Changed: [`corpus_diff.py`](../../tools/corpus_diff.py) (new), [`test_corpus_diff.py`](../../tests/test_corpus_diff.py)
(16 tests), [`RUNBOOK.md`](../RUNBOOK.md) (the diff joins the monthly block, rule 4 becomes three halves),
[`test_power_horizon.py`](../../tests/test_power_horizon.py) (the replay pin now imports the tolerance instead of restating it).

## What rounds 95 and 97 had in common, which nobody had said

Round 95: the runner fetched, the pointer moved, two days later a bit-level assertion failed with the finding entirely intact. Round
97: a sixteen-year replay re-ran and every one of its four totals had drifted 0.4–0.8%, paid-in and month count unchanged. Same cause,
twice, discovered by being surprised rather than by looking. Every figure in this repository is a function of a file somebody else is
allowed to revise — and the project verified the *ledger* twice over (`journalctl.py`, `audit_entries.py`) and never once the *corpus*.

`tools/corpus_diff.py` is that missing half. Two newest snapshots, and it answers what moved:

```
# corpus diff · 20260906T203953Z → 20260908T072408Z
  sessions 8,458 → 8,458
  symbols 12 → 12
  revised closes: 11 of 12 symbols, worst single cell 0.00% (IEF)
  distributions: 0 amounts differ (worst $0.0000 a share), 0 rows new, 0 rows gone
  cash rate: 0 sessions differ, worst 0.00%
    IEF   6,065 sessions   worst revision 0.0002% on 2003-03-13 (43.6509857178 → 43.6510772705)
    TLT   6,065 sessions   worst revision 0.0002% on 2005-08-08 (46.2119674683 → 46.2118797302)
    SPY   8,458 sessions   worst revision 0.0002% on 1994-07-07 (25.586561203 → 25.5866012573)

  within the 1.5% tolerance that tests/test_power_horizon.py::TheBarsHaveACommand pins
```

**Eleven of twelve funds had historical closes revised**, the worst single cell by two hundredths of a basis point, in a fetch that
added no sessions and restated no dividends. That is the exact magnitude that broke round 95's assertion — which is to say the
tolerance is not the interesting number; *knowing that it moved* is. The tool reports everything and only stops the month on a
revision outside tolerance, a removed session, a lost fund, or a dividend restated by more than half a cent.

## Four refusals it has to keep making

- **A missing column is named, not measured as zero.** The first version of the cash reader looked for `rate` in a file whose column is
  `cash_factor`, found nothing, and printed `0 sessions differ` — a fabricated verdict of "unchanged", which is exactly r92's failure
  mode wearing a numeric disguise. Both readers now `SystemExit` naming the columns they did find, and a test asserts the message names
  the actual column (`whatever`) rather than swallowing it.
- **One snapshot is not a failure.** With fewer than two snapshots it prints `nothing to compare yet` and exits 0 — the r92 discipline
  that a monthly check must be allowed to admit ignorance and still let the month through.
- **A snapshot cannot be diffed against itself** (`the zero would be a lie`), and an unknown `--against` stamp is refused with the list
  of stamps that do exist.
- **The tolerance is one constant.** `corpus_diff.TOLERANCE = 0.015`, imported by the replay pin that uses it; a test greps the pin for
  `0.015` and fails if it finds it, and another asserts the runbook quotes `1.5%`, which is the runbook sentence that keeps the
  document from drifting away from the tool.

## Live, as a step rather than a manual chore

`corpus_diff.py` is line 3 of the runbook's block — immediately after the fetch, before any seal — so `tools/monthly.py` picked it up
without being edited (that was the point of r95's design: the runner parses the document). The procedure now runs twelve commands and
exits 0, with the diff printing its verdict between the fetch and the seals:

```
  [2/12] fetch_market_data.py
  [3/12] corpus_diff.py        within the 1.5% tolerance …
  [4-8/12] paper.py step ×5    SKIPPED — not due: corpus ends 2026-09-04
  [9/12] journalctl.py verify   [10/12] audit_entries.py   [11/12] report   [12/12] compare
```

## What the new step found on its first month: a solver that reported the search, not the answer

The suite run that followed this change failed one test, in a file this round never touched
(`tests/test_financing_break_even.py`): the break-even borrow spread's *reported residual* disagreed with a fresh re-price at the
spread returned, by $5.97. The cause was latent and the trigger was round 98's own fetch — the revised closes moved the levered path,
which moved where the discontinuity fell, which exposed a reporting fault that had been sitting there. The bisection exits early when
the gap is inside its dollar tolerance, and that path re-prices by construction; the twenty-iteration fall-through returned the narrowed
midpoint while reporting the residual from the *previous probe*, a different spread. On a step-discontinuous function those two spreads
can be dollars apart.

The promise in the docstring — "what the gap actually was at the spread returned" — was the thing that was false, so the fix is in the
tool, not the assertion: the fall-through path re-prices at the answer it hands back. A negative test now forces that path with a
tolerance the loop can never satisfy (`1e-9`), which is the r93 discipline: a fix without a test that would have failed before it is a
story about a fix. And the test that caught it is worth keeping an eye on as a pattern — it does not ask the solver whether it converged,
it re-prices independently and compares. That is the same shape as `audit_entries.py` meeting the engine's own output, and it is the
second time this week a fresh-repricing check has caught something a self-reported figure passed.

## Checks

**2289 passed, 239 subtests** — sixteen new tests for the diff, one for the solver's fall-through path: a fabricated snapshot pair per case (an added session, a 0.0990% revision that must
be printed but must not stop, a 3% revision that must stop and name the cell, a removed session, a lost fund, a $0.02 dividend
restatement, `--json` parity, two missing-column refusals, the one-snapshot shrug, two bad-`--against` refusals, the anti-copy scans on
the tolerance, and the block-order assertion). The real snapshots are only ever asked to *run* and to parse fully (8,458 cash rows,
73,009 dividend rows) — never asserted to be within tolerance, because that is the vendor's behaviour and a suite that fails on it is
r95's accident turned into policy. Live state: five books, one anchor each, `all chains verify`, sealed fees $0.00, first seal
2026-09-30.

*Round 98. 98 standing rules. The archive now checks the ground it stands on as often as it checks its own bookkeeping.*
