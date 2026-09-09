# The bot-shaped artefact is a runner, and the honest part is what it refuses to hold

Round 95. Changed: [`monthly.py`](../../tools/monthly.py) (new), [`test_monthly_runner.py`](../../tests/test_monthly_runner.py)
(16 tests), [`RUNBOOK.md`](../RUNBOOK.md) gains a paragraph naming it.

## The objective asks for a bot; the archive has produced a refusal with a schedule

The standing goal is a model that earns monthly and beats VOO or QQQ. Ninety-four rounds of measurement have produced a specific
answer to "what should it decide": nothing, on a schedule, with the decision made once at an anchoring and graded by a calendar. So
the bot-shaped thing worth building is the mechanical half of the month — fetch, seal every book, verify, audit, report, compare —
in the published order, stopping at the first failure. Which is `tools/monthly.py`: eleven commands, and this week's live run:

```
   1. tools/forward_p0.py --status --commission 0
   2. tools/fetch_market_data.py
   3. tools/paper.py step                        — not due: corpus ends 2026-09-04, book `root` already closed at 2026-09-04
   4. tools/paper.py step --book tilt_band       — not due: …
   5–7. … constant, tilt, tilt_qqq               — not due: …
   8. tools/journalctl.py verify
   9. tools/audit_entries.py
  10. tools/paper.py report --book tilt_band
  11. tools/paper.py compare
EXIT 0
```

## Three decisions, all of them refusals

**It reads its orders from the document.** `plan()` parses the first ```sh block of `docs/RUNBOOK.md` — the published procedure is
the authority, and the runner holds no copy of it. The one thing the block cannot say is a list of books, so the runner adds one seal
per book found on disk and labels each with why it is there (`book \`tilt\` found on disk`). A test re-parses the block independently
and fails if the two readings diverge, so the document and the tool are one artefact or a red suite.

**Skipping is not continuing.** A seal whose condition the engine would refuse — corpus's last session is at or before the book's head
— is reported `not due` and skipped, in the engine's own words, computed from the same two numbers `command_step` compares (its
`max(data.dates)` and the head's `asof`), read through `paper.load_data()` rather than re-derived, because r82's lesson is that a
subtle rule written twice arrives twice. Mid-month, that turns five refusals into five honest skip lines and a clean exit 0. A
*failure* is different: it stops the run, and a stopped run prints no summary, because a month that stopped halfway is not a month.
Those two look similar on screen and must not be confused — a skip is a fact about the calendar, a stop is a fact about the record.

**No knobs.** `--dry-run` and `--json`. There is no `--force`, no `--yes`, no `--asof`, no `--tilt`, no `--band`, and there is a test
that asserts the help text contains none of them — the same reason `paper.py` refuses `--tilt`: a rebalancing band is a measured
property of a model, not something an operator may want more this month. A runner that could overrule a refusal would undo every
refusal the tools around it were built to make, and the runner is the one file in this tree that gets run when nobody is reading.

It is also worth stating what the runner is *not*: it does not fetch news, rank signals, or size a position, because the archive
cannot price a news veto (`decision_sheet.py` refuses one), and r90 measured what a "signal" that fires on luck looks like — the
skill verdict prints `beat` 18.8% of the time at the protocol's own floor on paths where no skill exists anywhere. Automating a
decision this repository has not been able to grade would be the fastest way ever built in this project to lose money with
confidence.

## The first live fetch broke a pin two days later, and the pin was the thing that was wrong

The runner ran for real, so `data/current` was repointed at a new snapshot (`20260908T072408Z`): same 5,177 sessions, same last date
2026-09-04, one close revised by about a hundredth of a basis point — what a re-pull of someone else's adjusted series looks like.
`tests/test_shelter_long_record.py` then failed, and it failed on an `assertEqual` between two *computed* figures: the `end`
convention's warmed and cold readings, which round 58 found to be identical because the month-end hole is immaterial under that
convention.

They were identical to 1.4e-11 on a $527 cheque and no longer bit-identical. The finding had not moved; the assertion had been
claiming something about the archive's bytes rather than about the finding — and a monthly fetch exists precisely to change those
bytes, so the suite carried a hidden lock forbidding the procedure from running. Fixed to a half-cent tolerance *plus* a relative
bound of 1e-9, so it still catches a real change of substance and no longer catches float noise. Swept the rest of the suite for the
same class: no other exact pin compares computed floats against live data (the remaining exact pins are dates, tuples and fixture
arithmetic, where bit equality is the right demand).

What I got wrong was the order of operations: running the runner live was right, and checking which pins assume a frozen corpus
should have come first. That is r87's rehearsal discipline applied to a new kind of change — a fetch is not just a new file, it is a
new input to every number the suite repeats.

## Checks

**2256 passed, 239 subtests** (after the pin above was moved from bits to cents; the first run of this round's suite read 2255 passed, 1 failed, and the failure was the real find of the round) — the runner's sixteen tests, including the one that stubs `audit_entries.py` to fail and asserts the
four commands after it never ran, the one that makes a dry run assert it executed nothing, and the one that asserts the fetch precedes
every seal and the checks follow them. Live state unchanged: five books, one anchor entry each, `all chains verify, and every entry
accounts for itself`, sealed fees to date $0.00. The first real seal is still 2026-09-30, and the first deposit 2026-10-30 — the
runner cannot make the calendar arrive sooner, which is the whole point of it.

*Round 95. 95 standing rules. The month is now one command, and the command's most important feature is that it cannot be talked
out of stopping.*
