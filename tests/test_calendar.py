"""Calendar dates are a separately enumerated fictional exchange, not price-derived."""

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.distributions import DistributionTable
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar


ARTIFACT = {
    "schema_version": 1,
    "source": "synthetic:fictional-two-session-exchange",
    "version": "fixture-1",
    "synthetic": True,
    "coverage_start": "2006-02-01",
    "coverage_end": "2007-06-30",
    "sessions": [
        "2006-02-27", "2006-02-28", "2006-03-31", "2006-04-28",
        "2006-05-31", "2006-06-30", "2006-07-31", "2006-08-31",
        "2006-09-29", "2006-10-31", "2006-11-30", "2006-12-29",
        "2007-01-31", "2007-02-28", "2007-03-30", "2007-04-30",
        "2007-05-30", "2007-05-31", "2007-06-01", "2007-06-04", "2007-06-29",
    ],
    "closures": ["2007-06-02"],
    "half_days": ["2007-06-29"],
}
START, END = date(2007, 6, 1), date(2007, 6, 30)


def inputs(days):
    market = MarketData(
        [PriceBar(day, symbol, 100.0, 100.0) for day in days for symbol in ("A", "B")],
        {day: 1.0 for day in days}, source="synthetic:test",
    )
    distributions = DistributionTable(
        [(day, symbol, 100.0, 0.0) for day in days for symbol in ("A", "B")],
        splits={}, sha256="fixture", source="synthetic:test",
    )
    return market, distributions


class SessionCalendarTests(unittest.TestCase):
    def setUp(self):
        self.calendar = SessionCalendar.from_dict(ARTIFACT)

    def test_common_readiness_and_each_anchor_use_expected_sessions(self):
        req = self.calendar.requirements(START, END, (9, 12, 15))
        self.assertEqual(req.decision_date, date(2007, 5, 31))
        self.assertEqual(req.warmup_start, date(2006, 2, 28))
        self.assertEqual(dict(req.anchors[req.decision_date]), {
            9: date(2006, 8, 31), 12: date(2006, 5, 31), 15: date(2006, 2, 28),
        })
        self.assertEqual(req.evaluation_sessions, (START, date(2007, 6, 4), date(2007, 6, 29)))
        pair = self.calendar.requirements(START, END, (9, 12))
        self.assertEqual(pair.warmup_start, req.warmup_start)
        self.assertEqual(pair.required_sessions, req.required_sessions)

    def test_removing_same_date_from_every_series_does_not_hide_missing_sessions(self):
        for removed in ("2007-06-01", "2007-06-04", "2007-06-29", "2006-02-28", "2007-05-31"):
            with self.subTest(removed=removed):
                days = tuple(date.fromisoformat(value) for value in ARTIFACT["sessions"] if value != removed)
                market, distributions = inputs(days)
                with self.assertRaisesRegex(ValueError, "calendar.*coverage"):
                    self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))

    def test_declared_closure_is_not_required_but_half_day_is(self):
        market, distributions = inputs(self.calendar.sessions)
        req = self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))
        self.assertNotIn(date(2007, 6, 2), req.required_sessions)
        self.assertIn(date(2007, 6, 29), req.required_sessions)

    def test_every_input_is_checked_against_calendar_not_one_another(self):
        market, distributions = inputs(self.calendar.sessions)
        missing = date(2007, 6, 4)
        del market.by_date[missing]["B"]
        with self.assertRaisesRegex(ValueError, "price.*coverage"):
            self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))
        market, distributions = inputs(self.calendar.sessions)
        del market.cash_factors[missing]
        with self.assertRaisesRegex(ValueError, "cash.*coverage"):
            self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))
        market, _ = inputs(self.calendar.sessions)
        _, distributions = inputs(tuple(day for day in self.calendar.sessions if day != missing))
        with self.assertRaisesRegex(ValueError, "distribution.*coverage"):
            self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))

    def test_unexpected_price_cash_or_distribution_dates_refused(self):
        extra = date(2007, 6, 2)
        market, distributions = inputs(tuple(sorted((*self.calendar.sessions, extra))))
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))
        market, distributions = inputs(self.calendar.sessions)
        market.cash_factors[extra] = 1.0
        with self.assertRaisesRegex(ValueError, "cash.*unexpected"):
            self.calendar.validate_inputs(market, distributions, ("A", "B"), START, END, (9, 12, 15))

    def test_calendar_must_cover_whole_earliest_anchor_month_and_endpoint(self):
        for changes in ({"coverage_start": "2006-02-27"}, {"coverage_end": "2007-06-29"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "calendar coverage"):
                SessionCalendar.from_dict({**ARTIFACT, **changes}).requirements(START, END, (9, 12, 15))

    def test_missing_anchor_month_is_not_a_fallback_to_another_date(self):
        artifact = {**ARTIFACT, "sessions": [value for value in ARTIFACT["sessions"] if not value.startswith("2006-08")]}
        with self.assertRaisesRegex(ValueError, "no expected session"):
            SessionCalendar.from_dict(artifact).requirements(START, END, (9, 12, 15))

    def test_output_curve_must_match_exact_sequence(self):
        expected = (START, date(2007, 6, 4), date(2007, 6, 29))
        self.calendar.validate_output_sessions(expected, START, END)
        for changed in (expected[1:], expected[:-1], expected[::2], expected[::-1], (*expected, expected[-1])):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "output.*sessions"):
                self.calendar.validate_output_sessions(changed, START, END)

    def test_identity_is_canonical_and_includes_authority_and_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.json"
            path.write_text(json.dumps({**ARTIFACT, "sha256": self.calendar.sha256}, indent=4))
            self.assertEqual(SessionCalendar.load(path).sha256, self.calendar.sha256)
            path.write_text(json.dumps({**ARTIFACT, "sha256": "0" * 64}))
            with self.assertRaisesRegex(ValueError, "hash"):
                SessionCalendar.load(path)
        other = SessionCalendar.from_dict({**ARTIFACT, "version": "fixture-2"})
        self.assertNotEqual(other.sha256, self.calendar.sha256)
        self.assertNotEqual(other.authority_sha256, self.calendar.authority_sha256)

    def test_artifact_structure_is_strict(self):
        for changes in (
            {"sessions": list(reversed(ARTIFACT["sessions"]))},
            {"sessions": [*ARTIFACT["sessions"], ARTIFACT["sessions"][-1]]},
            {"source": ""}, {"synthetic": "yes"}, {"schema_version": True},
            {"closures": ["2007-06-01"]}, {"half_days": ["2007-06-02"]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SessionCalendar.from_dict({**ARTIFACT, **changes})
