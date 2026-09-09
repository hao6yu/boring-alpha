# The second implementation disagreed with itself first

Round 108. Added [`test_nyse_rules_independently.py`](../../tests/test_nyse_rules_independently.py) (5 tests), two tests to
[`test_corpus_diff.py`](../../tests/test_corpus_diff.py) (22→24), corrected [`corpus_diff.py`](../../tools/corpus_diff.py)'s coverage
branch, and corrected last round's own runbook paragraph
([`docs/RUNBOOK.md`](../../docs/RUNBOOK.md)).

## The check the repository could not run

`docs/data/nyse-calendar.md` says the calendar artifact's rules were verified against `exchange_calendars==4.13`, in a disposable
environment, with wheel and source hashes in the provenance record. That is a real verification — of a file this lab cannot re-verify: the
package is not in the venv and the project keeps no third-party dependency in it. Round 106 found the practical edge of that: the artifact
covers 2006-01-01 to **2026-08-31**, the archive ends 2026-09-04, the first forward seal is 2026-09-30, and so `corpus_diff.py` had to
refuse a question about a single weekday in September.

So round 108 wrote the second implementation rather than inheriting the claim: a Gregorian computus typed out from the algorithm, nth-weekday
rules found by scanning the month, and one observance convention per fixed holiday — deliberately not the builder's helpers, deliberately
re-derived — in a test file. The comparison is the whole artifact: every session, every closure.

## It was wrong twice, both times about something worth knowing

The first run disagreed on exactly two dates inside the covered window:

```
mine closed, artifact traded:  2010-12-24, 2021-12-24
```

- **Thanksgiving is the fourth Thursday, not the fourth Monday.** My first pass had `nth_weekday(y, 11, 0, 4)`. It did not show up
  immediately, because the wrong Monday lands on a date the coverage window never reaches for 2026 — the kind of bug that waits for an
  extension.
- **A Christmas on a Saturday closes the Friday before; a New Year on a Saturday closes nothing.** I had assumed the two fixed winter
  holidays behaved alike. They do not: 2010-12-24 and 2021-12-24 are closures, while 2011-01-10 (the Monday after New Year's Saturday)
  traded. The referee was not the artifact's authority but the archive's own bar data — `data/current/market_daily.csv` has no SPY bar on
  either December Friday, and has one on 2011-01-10. Market data is a witness to which days traded and it costs one dictionary lookup to ask.
- Juneteenth behaves like New Year's (Saturday 2021-06-19: the Friday traded), so three of the fixed holidays answer "Saturday" three ways.

After fixing my rules, the two implementations agree on all **5,197 sessions** and all **194 closures**, and the re-derived rules extend to
the rest of 2026 without touching the sealed artifact:

```
2026-09-07  Labor Day          first Monday of September
2026-11-26  Thanksgiving       fourth Thursday
2026-12-25  Christmas          a Friday
```

## What the tool is allowed to say now

`corpus_diff.py` still prints the coverage end it is refusing against, and then — when the gap falls inside the interval the rules were
reviewed for (2006-2026) — answers from the rules and *names that it is doing so*:

```
  no new sessions: 1 weekday between them (2026-09-07) and the calendar's coverage ends 2026-08-31, before the gap — the
  checked artifact cannot vouch for them, and `tools/build_nyse_calendar.py` is what would extend it; the rule set transcribed
  in `build_nyse_calendar.py` (re-derived in `tests/test_nyse_rules_independently.py`) says it was a closure — the archive is
  current, not stalled.
```

Past the reviewed window it refuses outright (`rule_closures(2031)` is `None`; the test checks 2031 and 1999 rather than fabricating a stamp
that would contradict its own directory), and `tests/test_corpus_diff.py` now pins the admission and the answer together, because an answer
without its provenance is the artifact claiming to have covered dates it never saw.

Last round's runbook paragraph is corrected in place, in the open: it said the live case was "the calendar cannot say" and that the tool had
no answer. It has one now, and the correction is the point — the paragraph was true for one round and stale the next, which is exactly why
round 100 put classes under the obeyed document's figures.

## Checks

**2357 passed, 239 subtests** (2350 + 5 rule re-derivations + 2 corpus_diff cases; collected count printed before the run). Corpus
`20260908T123726Z`, five books at the anchor, sealed fees $0.00, first seal 2026-09-30, 23 more entries before a skill claim.

*Round 108. 108 standing rules. September's weekday is known, the rules behind a sealed artifact can now be checked by anyone with the repo
and no network, and the second implementation earned its keep by being wrong before the artifact was.*
