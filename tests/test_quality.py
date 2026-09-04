from datetime import date, timedelta
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.data.quality import QualityThresholds, enforce, inspect
from boring_alpha.domain import PriceBar

THRESHOLDS = QualityThresholds()


def _series(closes: list[float], *, opens: list[float] | None = None, factor: float = 1.0001,
            start: date = date(2024, 1, 1), symbol: str = "A") -> MarketData:
    days: list[date] = []
    day = start
    while len(days) < len(closes):
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    opens = opens if opens is not None else closes
    bars = [PriceBar(d, symbol, o, c) for d, o, c in zip(days, opens, closes)]
    return MarketData(bars, {d: factor for d in days}, source="test")


def _codes(data: MarketData, severity: str) -> set[str]:
    return {f.code for f in inspect(data, ("A",), THRESHOLDS) if f.severity == severity}


class QualityTests(unittest.TestCase):
    def test_clean_series_produces_no_findings(self) -> None:
        self.assertEqual(inspect(_series([100.0, 101.0, 100.5, 102.0]), ("A",), THRESHOLDS), [])

    def test_implausible_session_return_is_an_error(self) -> None:
        self.assertIn("session_return", _codes(_series([100.0, 45.0, 46.0]), "error"))

    def test_large_but_plausible_crisis_move_is_accepted(self) -> None:
        self.assertEqual(inspect(_series([100.0, 88.0, 95.0]), ("A",), THRESHOLDS), [])

    def test_implausible_open_gap_is_an_error(self) -> None:
        data = _series([100.0, 101.0, 102.0], opens=[100.0, 150.0, 102.0])
        self.assertIn("open_gap", _codes(data, "error"))

    def test_absurd_cash_factor_is_an_error(self) -> None:
        self.assertIn("cash_rate", _codes(_series([100.0, 101.0], factor=1.01), "error"))

    def test_stale_closes_are_a_warning(self) -> None:
        self.assertIn("stale_closes", _codes(_series([100.0] * 12), "warning"))

    def test_calendar_gap_is_a_warning(self) -> None:
        days = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 2, 1)]
        bars = [PriceBar(d, "A", 100.0, 100.0) for d in days]
        data = MarketData(bars, {d: 1.0001 for d in days}, source="test")
        self.assertIn("calendar_gap", _codes(data, "warning"))

    def test_gap_findings_name_the_symbol_and_date(self) -> None:
        findings = inspect(_series([100.0, 45.0]), ("A",), THRESHOLDS)
        self.assertIn("A", findings[0].message)
        self.assertIn("2024-01-02", findings[0].message)

    def test_checks_only_the_configured_symbols(self) -> None:
        days = [date(2024, 1, 1), date(2024, 1, 2)]
        bars = [PriceBar(days[0], "A", 100.0, 100.0), PriceBar(days[1], "A", 100.0, 100.0),
                PriceBar(days[0], "B", 100.0, 100.0), PriceBar(days[1], "B", 10.0, 10.0)]
        data = MarketData(bars, {d: 1.0001 for d in days}, source="test")
        self.assertEqual(inspect(data, ("A",), THRESHOLDS), [])
        self.assertTrue(inspect(data, ("A", "B"), THRESHOLDS))


class EnforceTests(unittest.TestCase):
    def test_errors_halt_and_name_every_problem(self) -> None:
        findings = inspect(_series([100.0, 45.0, 90.0]), ("A",), THRESHOLDS)
        with self.assertRaises(ValueError) as caught:
            enforce(findings)
        self.assertIn("session_return", str(caught.exception))

    def test_warnings_are_returned_rather_than_raised(self) -> None:
        warnings = enforce(inspect(_series([100.0] * 12), ("A",), THRESHOLDS))
        self.assertTrue(any("stale" in warning for warning in warnings))

    def test_thresholds_can_be_relaxed(self) -> None:
        relaxed = QualityThresholds(max_session_return=0.60, max_open_gap=0.60)
        self.assertEqual(inspect(_series([100.0, 45.0]), ("A",), relaxed), [])


if __name__ == "__main__":
    unittest.main()
