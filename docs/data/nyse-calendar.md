# Bounded NYSE equity-session calendar

The lab now has an independent, checked-in list of **5,197 daily sessions** from
2006-01-01 through 2026-08-31, including BA-002's common 15-month warmup. It is
date-only metadata, not market history, a historical run, or permission to open a
holdout. No SPY file or other market-data file was inspected to build it.

## What is included for review

- `data/calendars/nyse-2006-2026-v1.json`: the `SessionCalendar` input; 194
  weekday closures and 44 informational early-close dates accompany the sessions.
- `data/calendars/nyse-source-facts-v1.json`: short attributed primary-source
  excerpts, reviewed dates, URLs, and researcher-transcribed calendar facts.
- `data/calendars/nyse-provenance-v1.json`: checksums of those files and the
  generator, plus the actual independent-library comparison result.
- `tools/build_nyse_calendar.py`: a bounded standard-library implementation of
  the applicable weekday, holiday and exceptional-closure rules. It does not
  fetch data, infer missing sessions from prices, or extrapolate beyond its
  reviewed bounds.

The calendar's canonical SHA-256 is
`6bc0cf5a01d73e50e216560e20988e982366f1436b95688c3b9cf78c02c3106a`.
The pretty-printed file has a different byte checksum, recorded in provenance.

## Authority and checks performed

The full generated session and early-close sets were compared with
[`exchange_calendars` 4.13 XNYS](https://pypi.org/project/exchange_calendars/4.13/).
Both match exactly. That package was installed in a temporary environment for
this check, not added to the lab's runtime or test dependencies. Its version,
published wheel digest, and inspected rule-file digests are recorded. It is a
community-maintained implementation, **corroboration rather than exchange
authority**. Agreement between implementations is useful, not proof of accuracy.

The exceptional full closures in this interval have primary-source support:

| Date | Reason | Primary record |
| --- | --- | --- |
| 2007-01-02 | Gerald Ford national mourning | [NYSE Information Memo 06-88, December 29, 2006](https://www.nyse.com/publicdocs/nyse/regulation/nyse/NYSE_Rules.pdf) |
| 2012-10-29 and 2012-10-30 | Hurricane Sandy | [NYSE filing published by SEC, Release 34-70099, pages 5–6](https://www.sec.gov/rules/sro/nyse/2013/34-70099.pdf) |
| 2018-12-05 | George H. W. Bush national mourning | [NYSE/ICE announcement, December 1, 2018](https://ir.theice.com/press/news-details/2018/New-York-Stock-Exchange-to-Honor-President-George-H-W-Bush/default.aspx) |
| 2025-01-09 | Jimmy Carter national mourning | [NYSE/ICE announcement, December 30, 2024](https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx) |

The Ford memo was verified from indexed primary-source text. Opening the entire
aggregate rulebook PDF failed; it is not described as downloaded or archived.

Recurring closures are New Year's Day, the third January Monday, the third
February Monday, Good Friday, the last May Monday, Independence Day, the first
September Monday, the fourth November Thursday, Christmas, and—**only from
2022**—Juneteenth. Weekend observation is deliberately not a generic federal
holiday calendar: Saturday New Year's Day does not close the preceding Friday.
Thus 2010-12-31 and 2021-12-31 remain sessions.

The [2019 announcement's 2021 table](https://ir.theice.com/press/news-details/2019/NYSE-Group-Announces-2020-2021-and-2022-Holiday-and-Early-Closings-Calendar/default.aspx)
has no Juneteenth closure. The subsequent
[2022–2024 announcement](https://ir.theice.com/press/news-details/2021/NYSE-Group-Announces-2022-2023-and-2024-Holiday-and-Early-Closings-Calendar/default.aspx)
includes Juneteenth and expressly records no observed New Year's holiday in
2022. These tables were transcribed and tested. Its early-close dates are still
open sessions. The [NYSE 2026 calendar](https://www.nyse.com/trade/hours-calendars)
was checked through this artifact's August endpoint.

Historical Independence Day early-close annotations follow the pinned library's
pre-/post-2013 convention. These annotations are informative: daily coverage
does not depend on exact intraday closing times. Intraday interruptions are not
treated as full-day closures. This calendar covers U.S. equities' regular-session
dates, not bonds, futures, bank holidays, or extended-hours executions. NYSE Group
announcements explicitly cover NYSE Arca Equities; do not generalize the dates to
an unrelated venue or asset class.

This is **not an exhaustive manual audit of every annual NYSE circular from
2006–2026**. The full date set is supported by explicit recurring rules, the
identified special closures, selected primary annual tables and the pinned
library check. Short excerpts and factual transcriptions—not full original
documents—are the archived primary evidence. URLs and package hashes do not
magically archive the documents or the package.

## Reproduction without market data

From the repository root:

```sh
.venv/bin/python tools/build_nyse_calendar.py --check
.venv/bin/python -m pytest -q tests/test_nyse_calendar.py
```

Optional repeat of the independent implementation check, in a disposable
environment where `exchange_calendars==4.13` is installed:

```sh
python tools/build_nyse_calendar.py --check --cross-check-library
```

The ordinary suite needs no third-party calendar dependency or network. It pins
the complete artifact, annual counts, all five unusual closures, historical
holiday boundaries, published year tables, warmup coverage, and early closes.
Never silently replace the artifact after a research freeze. A corrected date or
new interval requires a reviewed new version and provenance record.

## Deferred SPY date-only cross-check

This remains **not performed**. Before a historical run, explicitly approve the
date-only inspection and select the bounded snapshot/window. The tool below reads
only `date` and `symbol` fields for comparison, never interprets prices, never
returns numeric market values, and does not modify the calendar. It cannot
grant its own holdout permission. The CSV reader necessarily reads raw rows;
the promise is no interpretation/output of price values, not zero-byte access.

Example for already-seen history, **not run during implementation**:

```sh
.venv/bin/python tools/build_nyse_calendar.py --check \
  --dates-csv PATH_TO_REVIEWED_SNAPSHOT/prices_daily.csv \
  --start 2006-02-28 --end 2021-12-31 --symbol SPY
```

Missing dates, extra dates and duplicate SPY dates are reported, with a nonzero
exit status on mismatch. Investigate and record the cause; do not intersect the
calendar with Yahoo's dates to make a failing feed pass. Extending this diagnostic
into the holdout requires its own explicit decision; this implementation did not
do so.

## Rights and limitations

The generator and factual dates are researcher-written project material.
Attribution is retained for short NYSE/ICE excerpts; the project's MIT license
does not grant rights to their original publications, trademarks, or market
data. The optional comparison library is Apache-2.0 and is not vendored here.
This sourcing record is neither legal advice nor permission to redistribute full
source publications. A public holiday date list is also not a guarantee that an
ETF traded or had a valid price on every expected session: that is what the
separate completeness checks test.
