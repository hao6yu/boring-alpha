# The dollar that a re-pull moved, and the audit line that had to earn its seat

Round 105. Ran the published procedure for real on a fresh fetch; added
`cost_conventions.py` to the monthly block, with its seat pinned; corrected `corpus_diff.py`'s within-tolerance verdict and reprinted two
digits in [`docs/RUNBOOK.md`](../../docs/RUNBOOK.md); tests `test_runbook.py` 21→23, `test_corpus_diff.py` 16→17.

## The month, run for real

`20260904T192633Z → 20260908T123726Z`, and for the first time the fetch carried real split events — QQQ 2:1 (2000-03-20), VOO 1:2
(2013-10-24), VTI 2:1, ITOT 2:1 and 2:1 — so the split logic that had only ever been exercised on synthetic data met the archive's own
history. What it produced agreed with the series it replaced to **0.0002% at the worst cell**, which is what "the split handling agrees
with what it replaced" looks like from the outside. The archive still ends 2026-09-04 (a fetch re-pulls the range; it does not invent
sessions), the seals are still not due, and the whole block ran clean through `report` and `compare`: chain intact, five books clean,
sealed fees $0.00, `23 more monthly entries … before a skill claim`.

Two new commands were in the block for this. The first was `cost_conventions.py`, added at seat 11 of 13 — after `audit_entries.py`,
before the report:

```sh
.venv/bin/python tools/audit_entries.py               # every sealed entry against its own numbers (rule 4)
.venv/bin/python tools/cost_conventions.py            # what every cost on this page actually is, and whether the fork moves a verdict
.venv/bin/python tools/paper.py report --book tilt_band
```

The seat is the point, not the presence. Sealing is calendar-bound, so a pricing disagreement must never block a seal; and the report is
where figures get republished, so an audit that runs *after* it is decoration. `test_runbook.py` now pins both halves
(`test_the_cost_audit_runs_after_the_seals_and_immediately_before_the_report`), including the corollary that every command after the
audit is print-only. A second test pins that the ledger audit runs *before* the cost audit, because a cost failure that fires first would
hide a ledger failure — the two protect different things: a book that won't verify never happened; a cost constant with two answers leaves
the book intact and the recommendation wrong.

## The dollar

`corpus_diff.py` printed this, in this order, on the real fetch:

```
  revised closes: 11 of 12 symbols, worst single cell 0.00% (IEF)
  …
  within the 1.5% tolerance that tests/test_power_horizon.py::TheBarsHaveACommand pins
  Nothing has to be re-read. This is the expected output of a routine fetch: history added, old closes unmoved.
```

The last line contradicted the first. Nothing had to be re-read *at 1.5%*, which is not the tolerance the repository publishes at:
`tests/test_runbook.py::TheDecisionFiguresAreReprinted` pins the runbook's bar table to the dollar on purpose, and a 0.0001% revision on a
$9.8M closing is a dollar. The suite failed on exactly that:

| the obeyed document said | the archive now says |
| --- | --- |
| `$9,812,538 banded` | `$9,812,539 banded` |
| `sits $2,404,017 behind plain QQQ` | `sits $2,404,018 behind plain QQQ` |

Nothing else moved: paid in `$2,020,000`, T-bills `$2,447,542 (+21.2%)`, VOO `$7,853,675 (−22.0%)`, monthly `$9,778,202`, never
`$9,988,324`, the drift share `8.70%` — all reprinted identical. The two digits were reprinted from the command's own output, not by
hand, and the historical notes that quote `12,216,556` were left alone: a sealed record is not re-priced (r94), which is also why they
carry their stamp.

The tool's verdict line is conditional now — on a diff where an old close moved it says so and points at the cent-pinned document:

```
  within the 1.5% tolerance that tests/test_power_horizon.py::TheBarsHaveACommand pins
  11 of 12 symbols' old closes moved, and immaterial at the tolerance above is not the same word as unchanged:
  `docs/RUNBOOK.md` pins its bar table to the dollar and `tests/test_runbook.py` recomputes every digit of it, …
  Re-print the figure with the command that printed it, never by hand.
```

and keeps the old calm only where it is true — `No old close moved at all` — with the negative case pinned by
`test_a_revision_small_enough_to_be_noise_still_names_the_document_it_moved`, which fails if the sentence ever comes back.

## The news half, re-read rather than assumed

The objective says *trending and global news*, so this round also re-read the two tools that price that claim, and both still say no with
their controls attached. `attention_bar.py`: **no cell on the financial basket clears the bar stated before the join**, `6 of 6 directions
were refuted by the control basket at the same threshold on the same windows`, financial basket spans −479 to +28 /mo against a control
best of +51. `news_veto.py`: **every cell is negative** — the veto costs the plan money in every reading and at every threshold — and
attention does not even cluster where the rule turns (|z| 0.70 at a turn against 0.63 in general), so there is no switch-cost saving to
argue about; its boundary is stated too (the corpus starts 2015-07-01 because that is where Wikimedia's Analytics API starts). Nothing
here is a failure of trying: it is the same result the price series keeps producing, arriving through a different input.

## Checks

**2333 passed, 239 subtests** (2330 + 2 runbook seat tests + 1 corpus_diff test; collected count printed before the run). Corpus:
`20260908T123726Z`, 73,009 rows, 1993-01-29 to 2026-09-04. Ledger: five books, one anchor entry each, sealed fees $0.00, first seal
2026-09-30, 23 more entries before a skill claim.

*Round 105. 105 standing rules. The month ran, a dollar moved, a contradiction in a tool's own output got fixed, an audit got a seat a test can evict, and the news signal was measured again and is still dead — and the bar is still the Nasdaq-100 fund doing
nothing at all.*
