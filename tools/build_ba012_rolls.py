#!/usr/bin/env python3
"""Freeze hypothetical child-to-parent BA-012 rolls without reading prices.

Only the independent calendar and protocol registration are read. There are no
network, credential, vendor, bar, position, return, or optimization inputs.
The output is an exchange-deadline parent-exposure diagnostic; current M6E
account-specific broker delivery applicability remains explicitly unverified.
"""

from __future__ import annotations

import hashlib
import json
import platform
from bisect import bisect_left
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "research/ba012-stage-a"
CALENDAR = DIR / "calendar-v1.json"
EXPECTED_CALENDAR_SHA256 = "b1034a5462f09723f297faba748291c304ee6597f02f0212e765b171226789b3"
PROTOCOL_SHA256 = "095fa832c82645a6f570668813b59b08afa4a21c93466980703ff78c46eec67f"
ORDER = ["NES", "MTN", "M6E", "1OZ", "MZC"]
MONTH_CODES = "FGHJKMNQUVXZ"
SPECS = {
    "NES": {"parent": "ES", "months": [3, 6, 9, 12], "listed_count": 2,
            "price_unit": "index points", "child_dollars_per_price_unit": 0.5},
    "MTN": {"parent": "TN", "months": [3, 6, 9, 12], "listed_count": 2,
            "price_unit": "decimal percent-of-par bond points", "child_dollars_per_price_unit": 100.0},
    "M6E": {"parent": "6E", "months": [3, 6, 9, 12], "listed_count": 6,
            "price_unit": "USD per EUR", "child_dollars_per_price_unit": 12500.0},
    "1OZ": {"parent": "GC", "months": [2, 4, 6, 8, 10, 12], "listed_count": 12,
            "price_unit": "USD per troy ounce", "child_dollars_per_price_unit": 1.0},
    "MZC": {"parent": "ZC", "months": [3, 5, 7, 9, 12], "listed_count": 9,
            "price_unit": "cents per bushel", "child_dollars_per_price_unit": 5.0},
}
SOURCES = {
    "nes_faq": "https://www.cmegroup.com/articles/faqs/faq-e-nano-equity-index-futures.html",
    "mtn_rule54": "https://www.cmegroup.com/rulebook/CBOT/III/54.pdf?redirect=/rulebook/CBOT/V/54.pdf",
    "mtn_calendar": "https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-10-year-us-treasury-note.calendar.html",
    "tn_calendar": "https://www.cmegroup.com/markets/interest-rates/us-treasury/ultra-10-year-us-treasury-note.calendar.html",
    "m6e_rule292": "https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/III/250/292/292.pdf",
    "gold_rule131": "https://www.cmegroup.com/rulebook/COMEX/1a/131.pdf",
    "gold_faq": "https://www.cmegroup.com/articles/faqs/faq-1-oz-gold-futures.html",
    "gold_calendar": "https://www.cmegroup.com/markets/metals/precious/1-ounce-gold.calendar.html",
    "mzc_rule_filing": "https://www.cmegroup.com/content/dam/cmegroup/market-regulation/rule-filings/2025/1/25-024.pdf",
    "ibkr_delivery_policy": "https://www.interactivebrokers.ca/en/trading/marginRequirements/physicalDeliveryLiquidationRules.php",
    "databento_units": "https://databento.com/docs/examples/instrument-definitions/contract-notional",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def nearest_weekday(day: date) -> date:
    return day + timedelta(days={5: -1, 6: 1}.get(day.weekday(), 0))


def easter(year: int) -> date:
    """Gregorian computus, calendar arithmetic only."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day0 = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day0 + 1)


def regular_holidays(year: int) -> set[date]:
    """Reviewed exchange settlement holidays; not every Globex open date.

    For the relevant child expiry months, this excludes Memorial Day and
    Thanksgiving in the manner demonstrated by current CME calendar examples.
    June 2023 FX additionally follows the explicit bank-holiday adjustment.
    Extension beyond 2023 is dates only, to identify already-listed Q1 2024
    replacement maturities used on 2023 reference dates.
    """
    jan1 = date(year, 1, 1)
    may31 = date(year, 5, 31)
    days = {
        jan1 + timedelta(days=int(jan1.weekday() == 6)),
        nth_weekday(year, 1, 0, 3), nth_weekday(year, 2, 0, 3),
        easter(year) - timedelta(days=2),
        may31 - timedelta(days=may31.weekday()),
        nearest_weekday(date(year, 7, 4)), nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4), nearest_weekday(date(year, 12, 25)),
    }
    if year >= 2022:
        days.add(nearest_weekday(date(year, 6, 19)))
    return days


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in regular_holidays(day.year)


def previous_business_days(day: date, count: int) -> date:
    for _ in range(count):
        day -= timedelta(days=1)
        while not is_business_day(day):
            day -= timedelta(days=1)
    return day


def last_trade(child: str, year: int, month: int) -> date:
    first = date(year, month, 1)
    if child == "NES":
        result = nth_weekday(year, month, 4, 3)
        # All quarterly third Fridays in the actual study interval are open;
        # keep the index-publication holiday rule explicit for verification.
        while not is_business_day(result):
            result -= timedelta(days=1)
        return result
    if child == "MTN":
        return previous_business_days(first, 2)
    if child == "1OZ":
        return previous_business_days(first, 3)
    if child == "M6E":
        delivery = nth_weekday(year, month, 2, 3)
        nominal = delivery - timedelta(days=2)
        # In the reviewed quarterly 2016-Q1 through 2024-Q1 dates, the sole
        # nominal LTD US-bank holiday is Juneteenth 2023. No relevant Tuesday
        # is TARGET-closed and no delivery Wednesday needs a holiday shift.
        if (year, month) == (2023, 6):
            assert nominal == date(2023, 6, 19)
            return date(2023, 6, 16)
        assert nominal.weekday() == 0 and is_business_day(nominal)
        return nominal
    if child == "MZC":
        last = previous_business_days(first, 1)
        friday = last - timedelta(days=1)
        while friday.weekday() != 4:
            friday -= timedelta(days=1)
        while sum(is_business_day(friday + timedelta(days=n))
                  for n in range(1, (last - friday).days + 1)) < 2:
            friday -= timedelta(days=7)
        return friday if is_business_day(friday) else previous_business_days(friday, 1)
    raise ValueError(child)


def calendar_examples() -> dict:
    """Manually transcribed non-price fields from official rendered calendars."""
    return {
        "review_date": "2026-09-10",
        "capture_method": "Read-only browser, calendar tables only; no API keys or market-data archive reads",
        "gold_rows": [
            {"contract": "1OZZ26", "last_trade": "2026-11-25", "settlement": "2026-11-25"},
            {"contract": "1OZM27", "last_trade": "2027-05-26", "settlement": "2027-05-26"},
        ],
        "gold_interpretation": "These exclude Thanksgiving 2026-11-26 and Memorial Day 2027-05-31 from the prior-month third-last-business-day count.",
        "mtn_rows": [
            {"contract": "MTNZ26", "last_trade": "2026-11-27"},
            {"contract": "MTNH27", "last_trade": "2027-02-25"},
        ],
        "tn_rows": [
            {"contract": "TNZ26", "first_holding": "2026-11-24", "first_position": "2026-11-27", "first_notice": "2026-11-30", "first_delivery": "2026-12-01"},
            {"contract": "TNM27", "first_holding": "2027-05-25", "first_position": "2027-05-27", "first_notice": "2027-05-28", "first_delivery": "2027-06-01"},
        ],
        "mtn_interpretation": "Rule54 uses two business days before the named month. Current MTN last-trade dates match TN first-position dates; TN June2027 month-start sequence explicitly excludes MemorialDay. This is documented support for the shared Treasury business-day interpretation, not observed prelaunch MTN expirations.",
        "sources": SOURCES,
    }


def build() -> dict:
    assert digest(CALENDAR) == EXPECTED_CALENDAR_SHA256, "Calendar changed: review before rebuilding"
    assert digest(ROOT / "docs/strategies/BA-012.md") == PROTOCOL_SHA256, "Protocol changed"
    calendar = json.loads(CALENDAR.read_text())
    study_sessions = [date.fromisoformat(s) for s in calendar["joint_sessions"]]
    # Check the expiry-calendar weekday/holiday reconstruction against the
    # pinned observation mask, with the documented rates/equity mourning day.
    for row in calendar["weekday_requests"]:
        day = date.fromisoformat(row["date_chicago"])
        assert row["scheduled_joint_session"] == (is_business_day(day) and day != date(2018, 12, 5))
    joint = list(study_sessions)
    day = date(2024, 1, 1)
    while day < date(2024, 4, 1):
        if is_business_day(day):
            joint.append(day)
        day += timedelta(days=1)

    # Official current examples resolve holiday interpretation, independent
    # of the date range or any observed prices in the research study.
    assert last_trade("1OZ", 2026, 12) == date(2026, 11, 25)
    assert last_trade("1OZ", 2027, 6) == date(2027, 5, 26)
    assert last_trade("MTN", 2026, 12) == date(2026, 11, 27)
    assert last_trade("MTN", 2027, 6) == date(2027, 5, 27)
    assert last_trade("M6E", 2023, 6) == date(2023, 6, 16)
    assert last_trade("MZC", 2023, 12) == date(2023, 11, 24)

    contracts: dict[str, list[dict]] = {}
    for child in ORDER:
        spec = SPECS[child]
        contracts[child] = []
        for year in range(2016, 2025):
            months = spec["months"] if year < 2024 else [spec["months"][0]]
            for month in months:
                ltd = last_trade(child, year, month)
                insertion = bisect_left(joint, ltd)
                assert insertion >= 5
                exit_day = joint[insertion - 5]
                assert len([d for d in joint if exit_day <= d < ltd]) == 5
                contracts[child].append({
                    "child_root": child, "parent_root": spec["parent"],
                    "contract_year": year, "contract_month": month,
                    "maturity": f"{year:04d}-{month:02d}",
                    "hypothetical_child_symbol": f"{child}{MONTH_CODES[month-1]}{year%10}",
                    "parent_raw_symbol": f"{spec['parent']}{MONTH_CODES[month-1]}{year%10}",
                    "exchange_last_trade_date": ltd.isoformat(),
                    "effective_deadline_date": ltd.isoformat(),
                    "exit_date_chicago": exit_day.isoformat(),
                    "broker_deadline_date": None,
                    "broker_basis": "M6E account applicability unverified; exchange-only parent diagnostic" if child == "M6E" else "Cash-settled child; no earlier broker deadline established",
                })

    rows = []
    previous = None
    prior_active: dict[str, str] = {}
    for day in study_sessions:
        markets = []
        for child in ORDER:
            # Current listing schedules contain at least the nearest two
            # listed eligible maturities. Five-session early exit never
            # requires skipping over an unexpired intermediate maturity.
            selected = next(c for c in contracts[child] if c["exit_date_chicago"] > day.isoformat())
            active = selected["parent_raw_symbol"]
            interval = prior_active.get(child)
            roll = interval is not None and active != interval
            required = [active] if interval in (None, active) else [interval, active]
            if roll:
                old = next(c for c in contracts[child] if c["parent_raw_symbol"] == interval)
                assert old["exit_date_chicago"] == day.isoformat()
            markets.append({
                "child_root": child, "parent_root": SPECS[child]["parent"],
                "active_parent_raw_symbol": active,
                "interval_parent_raw_symbol": interval,
                "is_roll": roll,
                "required_parent_raw_symbols": required,
                "active_maturity": selected["maturity"],
                "active_exchange_last_trade_date": selected["exchange_last_trade_date"],
                "active_exit_date_chicago": selected["exit_date_chicago"],
                "price_unit": SPECS[child]["price_unit"],
                "child_dollars_per_price_unit": SPECS[child]["child_dollars_per_price_unit"],
            })
            prior_active[child] = active
        rows.append({"date_chicago": day.isoformat(),
                     "previous_joint_date_chicago": previous,
                     "markets": markets})
        previous = day.isoformat()
    assert len(rows) == 2007
    assert [m["active_parent_raw_symbol"] for m in rows[0]["markets"]] == ["ESH6", "TNH6", "6EH6", "GCG6", "ZCH6"]
    assert [m["active_parent_raw_symbol"] for m in rows[-1]["markets"]] == ["ESH4", "TNH4", "6EH4", "GCG4", "ZCH4"]
    counts = Counter(m["child_root"] for r in rows for m in r["markets"] if m["is_roll"])
    assert dict(counts) == {"1OZ": 48, "MZC": 40, "MTN": 32, "M6E": 32, "NES": 32}
    return {
        "manifest_version": 1, "strategy_id": "BA-012", "stage": "A",
        "research_label": "Hypothetical current-child exposure and schedule on actual parent futures; not historical child executions",
        "frozen_before_archive_price_reads_by_generator": True,
        "calendar_sha256": EXPECTED_CALENDAR_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "generator_sha256": digest(Path(__file__)),
        "generator_python_version": platform.python_version(),
        "generator_path": "tools/build_ba012_rolls.py",
        "date_start": rows[0]["date_chicago"], "date_end": rows[-1]["date_chicago"],
        "sources": SOURCES,
        "rules": {
            "selection": "Nearest child maturity with exit_date strictly after current reference date",
            "exit_count": "Fifth joint session strictly before effective deadline; deadline itself is not counted",
            "roll_reference": "At t use previous active contract at both t-1 and t for interval; seed new active at t for the next interval; require both prices at t",
            "account_execution": "Not implemented here: old position exits10:01, replacements enter10:03 under frozen account rules",
            "NES": "Third Friday of March/June/September/December; earlier index publication day if needed",
            "MTN": "Second-last exchange settlement business day of prior month",
            "M6E": "Second exchange business day before third Wednesday, with explicit US banking and Eurosystem adjustments; June2023 LTD June16",
            "1OZ": "Third-last business day of prior month, relying on explicit Rule131102.E; final-floating-price discrepancy is irrelevant to early exit",
            "MZC": "Latest Friday at least two business days before prior month's final business day; move a closed Friday to preceding business day",
            "business_days": "Reviewed weekday exchange settlement calendar excludes normal exchange holidays, supported by current CME gold/Treasury contract calendar examples; observation mourning closure used only in joint-session backward count",
            "future_calendar_scope": "Date-only Q1 2024 extension identifies replacements held at2023-end; no2024 bars read",
        },
        "broker_status": {
            "M6E": "UNVERIFIED_ACCOUNT_APPLICABILITY",
            "diagnostic_basis": "Use exchange deadline because no applicable earlier account-specific M6E deadline is established. Public EUR delivery exception means an earlier cutoff cannot simply be assumed.",
            "native_or_account_specific_execution_validated": False,
            "formal_funded_feasibility_verdict_permitted": False,
            "parent_integer_risk_diagnostic_permitted": True,
        },
        "symbology_status": "Expected exact CME outright raw symbols; dated vendor raw_symbol-to-instrument_id confirmation required before joining prices; year reused across decades",
        "normalization": "Decode DBN fixed-point1e-9 exactly once. ZC cents/bu; Treasury numeric decimalpoints, not fractional display strings. Do not infer solely from min_price_increment_amount.",
        "joint_reference_count": len(rows),
        "roll_counts": dict(sorted(counts.items())),
        "contract_metadata": [c for child in ORDER for c in contracts[child]],
        "rows": rows,
    }


def write_json(name: str, value: dict) -> str:
    target = DIR / name
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    target.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    target.with_suffix(target.suffix + ".sha256").write_text(f"{sha}  {target.name}\n")
    return sha


if __name__ == "__main__":
    DIR.mkdir(parents=True, exist_ok=True)
    evidence_sha = write_json("rolls-calendar-evidence-v1.json", calendar_examples())
    result = build()
    result["calendar_evidence_sha256"] = evidence_sha
    sha = write_json("rolls-v1.json", result)
    print(json.dumps({"path": str(DIR / "rolls-v1.json"), "sha256": sha,
                      "rows": len(result["rows"]), "roll_counts": result["roll_counts"]}))
