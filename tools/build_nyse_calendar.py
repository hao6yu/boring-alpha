"""Regenerate the bounded, date-only NYSE session artifact without market data.

This is a deliberately small transcription of the documented 2006–2026 rules,
not a general exchange calendar. See docs/data/nyse-calendar.md for provenance,
the independent library check, and the checks still required before research.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path


START = date(2006, 1, 1)
END = date(2026, 8, 31)
VERSION = "nyse-rules-2006-2026-v1"
SOURCE = "NYSE published equity-market holidays and special closures; see docs/data/nyse-calendar.md"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/calendars/nyse-2006-2026-v1.json"
SPECIAL_CLOSURES = {
    date(2007, 1, 2): "Gerald Ford national day of mourning",
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "George H. W. Bush national day of mourning",
    date(2025, 1, 9): "Jimmy Carter national day of mourning",
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _nearest_weekday(day: date) -> date:
    return day + timedelta(days={5: -1, 6: 1}.get(day.weekday(), 0))


def _easter(year: int) -> date:
    # Gregorian computus; integer arithmetic only, with Good Friday two days earlier.
    century, remainder = divmod(year, 100)
    cycle = year % 19
    correction = (century - (century + 8) // 25 + 1) // 3
    epact = (19 * cycle + century - century // 4 - correction + 15) % 30
    shift = (32 + 2 * (century % 4) + 2 * (remainder // 4) - epact - remainder % 4) % 7
    adjust = (cycle + 11 * epact + 22 * shift) // 451
    month, zero_day = divmod(epact + shift - 7 * adjust + 114, 31)
    return date(year, month, zero_day + 1)


def regular_closures(year: int) -> set[date]:
    """Applicable rules only; Saturday New Year does NOT close the prior Friday."""
    if not START.year <= year <= END.year:
        raise ValueError("calendar rules are reviewed only for 2006 through 2026")
    new_year = date(year, 1, 1)
    if new_year.weekday() == 6:
        new_year += timedelta(days=1)
    memorial = date(year, 5, 31)
    memorial -= timedelta(days=memorial.weekday())
    closed = {
        new_year, _nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3),
        _easter(year) - timedelta(days=2), memorial,
        _nearest_weekday(date(year, 7, 4)), _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4), _nearest_weekday(date(year, 12, 25)),
    }
    if year >= 2022:
        closed.add(_nearest_weekday(date(year, 6, 19)))
    return {day for day in closed if day.weekday() < 5}


def early_closes(year: int) -> set[date]:
    """Informational early-close dates; every one remains an open daily session.

    Historical Independence Day early-close convention changed in 2013.
    The regular-session date set does not depend on this annotation.
    """
    days = {_nth_weekday(year, 11, 3, 4) + timedelta(days=1)}
    christmas_eve, july3, july5 = date(year, 12, 24), date(year, 7, 3), date(year, 7, 5)
    if christmas_eve.weekday() < 4:
        days.add(christmas_eve)
    if july3.weekday() in (0, 1, 3) or (year >= 2013 and july3.weekday() == 2):
        days.add(july3)
    if year < 2013 and july5.weekday() == 4:
        days.add(july5)
    return days


def build_calendar() -> dict:
    """Return a SessionCalendar-compatible record for the fixed reviewed bounds."""
    weekdays = {
        START + timedelta(days=offset) for offset in range((END - START).days + 1)
        if (START + timedelta(days=offset)).weekday() < 5
    }
    closed = set(SPECIAL_CLOSURES)
    half_days: set[date] = set()
    for year in range(START.year, END.year + 1):
        closed.update(regular_closures(year))
        half_days.update(early_closes(year))
    closed &= weekdays
    sessions = weekdays - closed
    return {
        "schema_version": 1, "source": SOURCE, "version": VERSION,
        "coverage_start": START.isoformat(), "coverage_end": END.isoformat(),
        "sessions": [day.isoformat() for day in sorted(sessions)], "synthetic": False,
        "closures": [day.isoformat() for day in sorted(closed)],
        "half_days": [day.isoformat() for day in sorted(half_days & sessions)],
    }


def encode_calendar(record: dict) -> bytes:
    return (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def canonical_sha256(record: dict) -> str:
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cross_check_library(record: dict) -> dict:
    """Optional independent implementation check; no library needed at runtime."""
    import exchange_calendars

    if exchange_calendars.__version__ != "4.13":
        raise ValueError("the audited comparison requires exchange_calendars==4.13")
    calendar = exchange_calendars.get_calendar("XNYS", start=START.isoformat(), end=END.isoformat())
    sessions = [stamp.date().isoformat() for stamp in calendar.sessions]
    half_days = [stamp.date().isoformat() for stamp in calendar.early_closes]
    if record["sessions"] != sessions or record["half_days"] != half_days:
        raise ValueError("calendar differs from pinned XNYS sessions or early closes")
    return {"implementation": "exchange_calendars", "version": "4.13", "calendar": "XNYS", "match": True}


def compare_date_csv(record: dict, path: Path, start: date, end: date, symbol: str = "SPY") -> dict:
    """Read date/symbol fields only, never parse or report a numeric market value.

    Explicit bounds are required. Rows outside them are discarded immediately.
    This diagnostic never changes the authoritative calendar to fit the feed.
    Caller must obtain any required permission for date-only holdout inspection.
    """
    if not START <= start <= end <= END:
        raise ValueError("date comparison must be bounded within the archived calendar")
    expected = {day for day in record["sessions"] if start.isoformat() <= day <= end.isoformat()}
    observed: list[str] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"date", "symbol"} <= set(reader.fieldnames or ()):
            raise ValueError("date comparison requires date and symbol columns")
        for row in reader:
            if row["symbol"] != symbol:
                continue
            value = row["date"]
            day = date.fromisoformat(value)
            if value != day.isoformat():
                raise ValueError("date comparison requires canonical ISO dates")
            if start <= day <= end:
                observed.append(value)
    duplicates = sorted(day for day, count in Counter(observed).items() if count > 1)
    missing, unexpected = sorted(expected - set(observed)), sorted(set(observed) - expected)
    return {
        "symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
        "expected_sessions": len(expected), "observed_sessions": len(observed),
        "missing": missing, "unexpected": unexpected, "duplicates": duplicates,
        "match": not (missing or unexpected or duplicates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="verify checked-in bytes; do not write")
    parser.add_argument("--cross-check-library", action="store_true")
    parser.add_argument("--dates-csv", type=Path, help="explicit date-only feed comparison; never automatic")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--symbol", default="SPY")
    args = parser.parse_args(argv)
    record = build_calendar()
    checks = {}
    if args.cross_check_library:
        checks["library"] = cross_check_library(record)
    if args.dates_csv:
        if args.start is None or args.end is None:
            parser.error("--dates-csv requires explicit --start and --end")
        checks["date_comparison"] = compare_date_csv(record, args.dates_csv, args.start, args.end, args.symbol)
    elif args.start is not None or args.end is not None:
        parser.error("--start/--end apply only to --dates-csv, not calendar generation")
    payload = encode_calendar(record)
    if args.check:
        if args.output.read_bytes() != payload:
            raise ValueError("checked-in calendar differs from deterministic regeneration")
    elif not args.dates_csv:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists() and args.output.read_bytes() != payload:
            raise ValueError("refusing to replace a different calendar; use a new version/path")
        if not args.output.exists():
            args.output.write_bytes(payload)
    print(json.dumps({"calendar": str(args.output), "sessions": len(record["sessions"]),
                      "sha256": canonical_sha256(record), "checks": checks}, indent=2))
    return 0 if all(value["match"] for value in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
