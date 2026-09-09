# A calendar is an input, and it ages

Round 106. [`corpus_diff.py`](../../tools/corpus_diff.py) can now explain an empty fetch;
[`test_corpus_diff.py`](../../tests/test_corpus_diff.py) 17→22; one paragraph added to [`docs/RUNBOOK.md`](../../docs/RUNBOOK.md).

## The fetch that added nothing, and what was actually true

Round 105's fetch left the archive ending 2026-09-04 while the clock said 2026-09-08, and the diff tool printed *"history added, old
closes unmoved"* over a diff that added nothing. Two questions, both answerable from the files:

1. **Did the filter eat a session?** No. The raw chart payload was pulled and inspected: its last four sessions are
   `2026-09-01, 02, 03, 04` and `exchange_today(gmtoffset)` is 2026-09-08, so the fetcher dropped exactly the session still in progress and
   nothing else. The source's own edge is 2026-09-04.
2. **Was the archive then two days stale?** One day, and the day was **2026-09-07 — US Labor Day**, the first Monday of September. The
   archive is complete through the last completed session; nothing was missing.

So nothing was wrong, and the report still misled. That is the same fault as round 105's *"nothing has to be re-read"*: a calm sentence
sitting over a gap the tool never looked at.

## The calendar is dated, and the forward test is not

The answer above came from `data/calendars/nyse-2006-2026-v1.json` — real NYSE closures, built from `exchange_calendars` 4.13 with
provenance beside it. Its `coverage_end` is **2026-08-31**. The archive's newest session is 2026-09-04 and the first forward seal is
2026-09-30, so the calendar cannot speak about a single date the forward test now needs. It is not a broken input, it is a dated one —
exactly like the price file, which also stops somewhere and says so in its own name.

`corpus_diff.py` now says which of four things is true when a fetch adds no sessions:

| case | what it prints |
| --- | --- |
| no completed day was skipped | *the archive ends on the last completed session; the exchange has not finished another one since the fetch ran* |
| every gap weekday was a closure | *all N weekdays in between (…) were exchange closures — the archive is current, not stalled* |
| the source fell short | names the open days missed, exits 0 (the next fetch should fill them), and forbids quoting figures for a period the corpus does not cover |
| the calendar cannot say — **the live case** | *1 weekday between them (2026-09-07) and the calendar's coverage ends 2026-08-31, before the gap … rebuild it with `tools/build_nyse_calendar.py` before anything leans on the month's dates* |

An off-by-one surfaced while writing it: the gap initially included the fetch day itself, which the fetcher deliberately excludes, so every
weekday fetch would have read as short by one session. Fixed, and the fix carries a comment because the wrong version was *plausible*.

## Checks

**2338 passed, 239 subtests** (2333 + 4 scratch cases + 1 live admission; collected count printed before the run). Neighbours green:
`test_corpus_diff` 22, `test_runbook` 23. Corpus `20260908T123726Z`, 73,009 rows, 1993-01-29 to 2026-09-04. Ledger unchanged: five books,
one anchor entry each, sealed fees $0.00, first seal 2026-09-30, `23 more monthly entries … before a skill claim`.

*Round 106. 106 standing rules. The month is not stalled and the news signal is still dead and the bar is still plain QQQ — but the tool
that reports the frontier can now say why it cannot read the calendar, which is the difference between an instrument and a reassurance.*
