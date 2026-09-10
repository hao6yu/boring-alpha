#!/usr/bin/env python3
"""Build BA-012 Stage A morning membership and weekday acquisition manifests.

Offline calendar construction only: no credentials, vendor calls, market data,
contract selection, strategy signals, or return calculations. Limited to the
reviewed 2016-01-11 through 2023-12-31 interval. See the interpretation note.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "research/ba012-stage-a/calendar-v1.json"
START = date(2016, 1, 11)
END = date(2024, 1, 1)  # exclusive
CHICAGO = ZoneInfo("America/Chicago")
PMC_COMMIT = "275890784073a3a3a347e4f05f4dc986456e6a75"
PMC_BASE = f"https://github.com/rsheftel/pandas_market_calendars/blob/{PMC_COMMIT}/pandas_market_calendars/"

SOURCES = {
    "pmc_grains": PMC_BASE + "calendars/cme_globex_agriculture.py",
    "pmc_us_holiday_definitions": PMC_BASE + "holidays/us.py",
    "pmc_grain_hours": PMC_BASE + "calendars/cme_market_times.py",
    "pmc_equity_early_closes": PMC_BASE + "calendars/cme_globex_equities.py",
    "pmc_cme_holiday_definitions": PMC_BASE + "holidays/cme.py",
    "cme_mourning_2018": "https://www.cmegroup.com/notices/ser/2018/12/SER-8289.pdf",
    "juneteenth_2022_broker_schedule": "https://www.nesvick.com/wp-content/uploads/2022/06/Juneteenth-2022-Holiday-Trading-Schedule.pdf",
    "juneteenth_2023_broker_schedule": "https://www.gtjai.com/upload/UploadFiles/2023/06/14/6d29478797914e268ad308406a278a91.pdf",
    "december_31_2021_broker_notice": "https://www.ampfutures.com/news/new-years-holiday-trading-schedule-2021",
    "december_31_2021_cme_clearing": "https://www.cmegroup.com/tools-information/holiday-calendar/files/2021-new-years-advisory.pdf",
    "tn_launch": "https://www.cmegroup.com/media-room/press-releases/2016/1/15/cme_group_announcessuccessfullaunchofultra10-yearfutures.html",
}

# Materialize Good Friday only for the reviewed years. The source rule is
# Western Easter minus two days, not a price-derived closure inference.
GOOD_FRIDAY = {
    2016: "2016-03-25", 2017: "2017-04-14", 2018: "2018-03-30",
    2019: "2019-04-19", 2020: "2020-04-10", 2021: "2021-04-02",
    2022: "2022-04-15", 2023: "2023-04-07",
}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def nearest_weekday(day: date) -> date:
    return day + timedelta(days={5: -1, 6: 1}.get(day.weekday(), 0))


def holiday_rules() -> dict[date, list[dict[str, str]]]:
    excluded: dict[date, list[dict[str, str]]] = {}

    def add(day: date, reason: str, source: str = "pmc_grains") -> None:
        excluded.setdefault(day, []).append({"reason": reason, "source_id": source})

    for year in range(2016, 2024):
        jan1 = date(year, 1, 1)
        # Saturday January 1 does NOT move to Friday December 31.
        add(jan1 + timedelta(days=int(jan1.weekday() == 6)), "New Year; Sunday observed Monday")
        add(nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day; grains closed")
        add(nth_weekday(year, 2, 0, 3), "Presidents Day; grains closed")
        add(date.fromisoformat(GOOD_FRIDAY[year]), "Good Friday; grains closed")
        may31 = date(year, 5, 31)
        add(may31 - timedelta(days=may31.weekday()), "Memorial Day; grains closed")
        add(nearest_weekday(date(year, 7, 4)), "Independence Day; grains closed")
        add(nth_weekday(year, 9, 0, 1), "Labor Day; grains closed")
        add(nth_weekday(year, 11, 3, 4), "Thanksgiving Day; grains closed")
        add(nearest_weekday(date(year, 12, 25)), "Christmas; nearest weekday observance")

    # The pinned grain class omits these holidays; do not inherit its omission.
    add(date(2022, 6, 20), "Juneteenth; grains day session closed", "juneteenth_2022_broker_schedule")
    add(date(2023, 6, 19), "Juneteenth; grains closed", "juneteenth_2023_broker_schedule")
    add(date(2018, 12, 5), "National day of mourning; rates closed, US equity indices close 08:30 CT", "cme_mourning_2018")
    return excluded


def early_close_markers(day: date) -> list[dict[str, str]]:
    """Known equity early closes after the required morning window.

    These annotations do not assert a complete five-product closing schedule.
    Holiday exclusions always take precedence. Rules are transcribed from the
    pinned equity calendar and CME holiday definitions, including July 3 only
    when July 4 is Tuesday through Friday.
    """
    reasons = []
    if day == nth_weekday(day.year, 11, 3, 4) + timedelta(days=1):
        reasons.append("Friday after Thanksgiving")
    if day.month == 12 and day.day == 24 and day.weekday() <= 3:
        reasons.append("Christmas Eve")
    july4 = date(day.year, 7, 4)
    if 1 <= july4.weekday() <= 4 and day == july4 - timedelta(days=1):
        reasons.append("Weekday before July 4 when July 4 is Tuesday through Friday")
    return [{"reason": reason, "product": "ES", "library_scheduled_close_ct": "12:15:00",
             "affects_required_window": False, "source_id": "pmc_equity_early_closes"}
            for reason in reasons]


def utc_reference(day: date, hour: int, minute: int) -> str:
    return datetime.combine(day, time(hour, minute), CHICAGO).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build() -> dict:
    exclusions = holiday_rules()
    rows = []
    day = START
    while day < END:
        if day.weekday() < 5:
            reasons = exclusions.get(day, [])
            rows.append({
                "date_chicago": day.isoformat(),
                "request_start_utc_inclusive": utc_reference(day, 9, 59),
                "request_end_utc_exclusive": utc_reference(day, 10, 0),
                "scheduled_joint_session": not reasons,
                "exclusions": reasons,
                "known_early_close_annotations": early_close_markers(day) if not reasons else [],
            })
        day += timedelta(days=1)
    sessions = [row["date_chicago"] for row in rows if row["scheduled_joint_session"]]
    # Narrow, material calendar checks; no observations or market data involved.
    assert len(rows) == 2080 and len(sessions) == 2007
    assert "2018-12-05" not in sessions
    assert "2022-06-20" not in sessions and "2023-06-19" not in sessions
    assert "2021-06-18" in sessions and "2021-12-31" in sessions
    assert "2022-01-03" in sessions and "2023-12-29" in sessions
    assert utc_reference(date(2018, 3, 9), 9, 59).endswith("15:59:00Z")
    assert utc_reference(date(2018, 3, 12), 9, 59).endswith("14:59:00Z")
    return {
        "manifest_version": 1,
        "strategy_id": "BA-012",
        "stage": "A",
        "review_date": "2026-09-10",
        "scope": "Scheduled joint morning membership and all-weekday acquisition superset only; not a child contract roll manifest",
        "construction": "Independent of prices, volumes, returned bars, and future returns",
        "calendar_basis": "Pinned maintainers' product rules plus explicit historical source exceptions; not an exchange-certified complete historical schedule",
        "range_start_inclusive": START.isoformat(),
        "range_end_exclusive": END.isoformat(),
        "required_open_window_chicago": ["09:59:00", "10:06:00"],
        "timezone": "America/Chicago",
        "generator": {
            "path": "tools/build_ba012_calendar.py",
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python_version": platform.python_version(),
            "dependencies": "Python standard library; system IANA America/Chicago timezone",
            "pandas_market_calendars_source_version": "5.4.0",
            "pandas_market_calendars_source_commit": PMC_COMMIT,
        },
        "sources": SOURCES,
        "regular_holiday_rule_note": "Grains closed on the listed weekday holidays. New Year is Sunday-to-Monday, unlike nearest-weekday July 4 and Christmas. Columbus and Veterans Days are not excluded.",
        "early_close_annotation_scope": "Known ES afternoon early-close markers are recorded but retained. Full product closing times are outside this minute-membership manifest.",
        "initial_availability_note": "TN first traded on Sunday 2016-01-10 after 17:00 CT; first common morning is 2016-01-11. Earlier January weekdays are prelaunch, not missing-bar failures.",
        "acquisition": {
            "dataset": "GLBX.MDP3", "schema": "ohlcv-1m", "stype_in": "parent",
            "symbols": ["ES.FUT", "TN.FUT", "6E.FUT", "GC.FUT", "ZC.FUT"],
            "each_weekday_requested_including_holidays": True,
            "parent_warning": "Parent expansion includes spreads and all maturities; retain archive, then resolve dated raw symbols and select actual outright contracts after independent roll mapping.",
            "missing_data_policy": "Do not change scheduled membership from returned records. Missing expected positive-volume bars stay missing; no filling or alternative time.",
        },
        "outstanding_before_roll_panel": [
            "Identify each child's exchange business-day basis for its hypothetical LTD; do not substitute this joint calendar for it.",
            "Resolve applicable known broker mandatory closeout dates; do not invent unknown dates or assert their absence.",
            "Freeze hypothetical listed maturities and exact parent matching independently of price/volume.",
            "This calendar does not certify historical instrument-specific unscheduled halts; unexpected missing bars remain unresolved pending independent evidence.",
        ],
        "weekday_request_count": len(rows),
        "joint_session_count": len(sessions),
        "excluded_weekday_count": len(rows) - len(sessions),
        "joint_session_counts_by_year": dict(sorted(Counter(day[:4] for day in sessions).items())),
        "joint_sessions": sessions,
        "weekday_requests": rows,
    }


if __name__ == "__main__":
    payload = (json.dumps(build(), indent=2, sort_keys=True) + "\n").encode()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    OUTPUT.with_suffix(".json.sha256").write_text(f"{digest}  {OUTPUT.name}\n")
    print(json.dumps({"path": str(OUTPUT), "sha256": digest,
                      "joint_sessions": 2007, "weekday_requests": 2080}))
