"""Calendar tests use only public session dates and fabricated CSV rows."""

from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.data.calendar import SessionCalendar
from tools.build_nyse_calendar import (
    DEFAULT_OUTPUT, END, ROOT, SPECIAL_CLOSURES, START, build_calendar,
    canonical_sha256, compare_date_csv, encode_calendar, main, regular_closures,
)


class NyseCalendarTests(unittest.TestCase):
    def setUp(self):
        self.record = build_calendar()
        self.calendar = SessionCalendar.from_dict(self.record)

    def test_checked_in_bytes_regenerate_exactly(self):
        self.assertEqual(DEFAULT_OUTPUT.read_bytes(), encode_calendar(self.record))
        self.assertEqual(self.calendar.sha256, canonical_sha256(self.record))
        self.assertEqual(self.calendar.sha256, "6bc0cf5a01d73e50e216560e20988e982366f1436b95688c3b9cf78c02c3106a")

    def test_fixed_bounds_and_independent_warmup(self):
        self.assertEqual((self.calendar.coverage_start, self.calendar.coverage_end), (START, END))
        self.assertFalse(self.calendar.synthetic)
        req = self.calendar.requirements(date(2007, 6, 1), date(2017, 12, 31), (9, 12, 15))
        self.assertEqual(req.decision_date, date(2007, 5, 31))
        self.assertEqual(req.warmup_start, date(2006, 2, 28))

    def test_year_counts_pin_complete_date_set(self):
        counts = Counter(day.year for day in self.calendar.sessions)
        self.assertEqual(dict(counts), {
            2006: 251, 2007: 251, 2008: 253, 2009: 252, 2010: 252,
            2011: 252, 2012: 250, 2013: 252, 2014: 252, 2015: 252,
            2016: 252, 2017: 251, 2018: 251, 2019: 252, 2020: 253,
            2021: 252, 2022: 251, 2023: 250, 2024: 252, 2025: 250, 2026: 166,
        })
        self.assertEqual(len(self.calendar.sessions), 5197)
        self.assertEqual(len(self.calendar.closures), 194)
        self.assertEqual(len(self.calendar.half_days), 44)

    def test_every_exception_has_independent_primary_source_fact(self):
        facts = json.loads((ROOT / "data/calendars/nyse-source-facts-v1.json").read_text())
        sourced = {date.fromisoformat(day) for item in facts["sources"] for day in item["facts"].get("full_closures", [])}
        self.assertEqual(sourced, set(SPECIAL_CLOSURES))
        self.assertEqual(sourced, {date(2007, 1, 2), date(2012, 10, 29), date(2012, 10, 30), date(2018, 12, 5), date(2025, 1, 9)})
        self.assertTrue(sourced <= set(self.calendar.closures))
        self.assertFalse(sourced & set(self.calendar.sessions))

    def test_historical_new_year_and_juneteenth_rules(self):
        sessions = set(self.calendar.sessions)
        for day in (date(2010, 12, 31), date(2021, 12, 31), date(2021, 6, 18), date(2021, 6, 21)):
            self.assertIn(day, sessions)
        for day in (date(2006, 1, 2), date(2022, 6, 20), date(2023, 6, 19)):
            self.assertNotIn(day, sessions)

    def test_early_closes_and_intraday_halts_are_still_daily_sessions(self):
        half_days = set(self.calendar.half_days)
        self.assertTrue(half_days <= set(self.calendar.sessions))
        self.assertIn(date(2013, 7, 3), half_days)
        self.assertNotIn(date(2013, 7, 5), half_days)
        self.assertIn(date(2024, 12, 24), half_days)
        self.assertIn(date(2015, 7, 8), self.calendar.sessions)  # NYSE intraday halt was not a full closure.
        self.assertIn(date(2020, 3, 9), self.calendar.sessions)

    def test_rules_match_transcribed_published_year_tables(self):
        facts = json.loads((ROOT / "data/calendars/nyse-source-facts-v1.json").read_text())
        for item in facts["sources"]:
            for key, values in item["facts"].items():
                if key.endswith("_regular_closures"):
                    year = int(key[:4])
                    self.assertEqual(sorted(day.isoformat() for day in regular_closures(year)), values)
                if key.endswith("_early_closes"):
                    self.assertEqual([day for day in self.record["half_days"] if day[:4] == key[:4]], values)
                if key == "2026_regular_closures_through_august":
                    self.assertEqual([day for day in self.record["closures"] if day[:4] == "2026"], values)

    def test_regeneration_refuses_unreviewed_years(self):
        with self.assertRaisesRegex(ValueError, "reviewed only"):
            regular_closures(2027)

    def test_date_comparison_never_interprets_market_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fabricated.csv"
            path.write_text("date,symbol,close\n2025-01-08,SPY,not-a-number\n2025-01-10,SPY,SECRET\n2025-01-09,OTHER,0\n")
            result = compare_date_csv(self.record, path, date(2025, 1, 8), date(2025, 1, 10))
            self.assertTrue(result["match"])
            self.assertEqual(result["observed_sessions"], 2)
            self.assertNotIn("SECRET", json.dumps(result))

    def test_date_comparison_reports_missing_extra_and_duplicate_without_repair(self):
        before = encode_calendar(self.record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fabricated.csv"
            path.write_text("date,symbol\n2025-01-08,SPY\n2025-01-08,SPY\n2025-01-09,SPY\n")
            result = compare_date_csv(self.record, path, date(2025, 1, 8), date(2025, 1, 10))
            self.assertFalse(result["match"])
            self.assertEqual(result["missing"], ["2025-01-10"])
            self.assertEqual(result["unexpected"], ["2025-01-09"])
            self.assertEqual(result["duplicates"], ["2025-01-08"])
        self.assertEqual(encode_calendar(self.record), before)

    def test_cli_date_comparison_requires_explicit_bounds(self):
        with self.assertRaises(SystemExit):
            main(["--dates-csv", "NOT_READ.csv"])

    def test_provenance_checksums_cover_archived_calendar_and_source_facts(self):
        path = ROOT / "data/calendars/nyse-provenance-v1.json"
        provenance = json.loads(path.read_text())
        for name, sha in provenance["file_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), sha)
        self.assertEqual(provenance["calendar_canonical_sha256"], self.calendar.sha256)
        self.assertEqual(provenance["spy_date_cross_check"]["status"], "deferred; not performed")
