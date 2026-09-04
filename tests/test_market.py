from datetime import date
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar


class LastSharedSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        d1, d2 = date(2018, 3, 29), date(2018, 3, 30)
        bars = [
            PriceBar(d1, "A", 1.0, 1.0),
            PriceBar(d2, "A", 1.0, 1.0),
            PriceBar(d1, "B", 1.0, 1.0),
        ]
        self.data = MarketData(bars, {d1: 1.0, d2: 1.0}, source="test")

    def test_returns_last_session_where_all_symbols_have_bars(self) -> None:
        self.assertEqual(
            self.data.last_shared_session_in_month(("A", "B"), 2018, 3), date(2018, 3, 29)
        )

    def test_single_symbol_uses_its_own_last_session(self) -> None:
        self.assertEqual(
            self.data.last_shared_session_in_month(("A",), 2018, 3), date(2018, 3, 30)
        )

    def test_returns_none_when_month_has_no_shared_session(self) -> None:
        self.assertIsNone(self.data.last_shared_session_in_month(("A", "B"), 2018, 4))


class MarketDataValidationTests(unittest.TestCase):
    def test_fingerprint_ignores_the_source_label(self) -> None:
        day = date(2025, 1, 2)
        bars = [PriceBar(day, "A", 1.0, 2.0)]
        first = MarketData(bars, {day: 1.0}, source="csv:/one/path")
        second = MarketData(bars, {day: 1.0}, source="csv:/another/path")
        self.assertEqual(first.fingerprint(), second.fingerprint())

    def test_fingerprint_changes_when_a_price_changes(self) -> None:
        day = date(2025, 1, 2)
        first = MarketData([PriceBar(day, "A", 1.0, 2.0)], {day: 1.0}, source="s")
        second = MarketData([PriceBar(day, "A", 1.0, 2.5)], {day: 1.0}, source="s")
        self.assertNotEqual(first.fingerprint(), second.fingerprint())

    def test_duplicate_bar_is_rejected(self) -> None:
        day = date(2025, 1, 2)
        with self.assertRaisesRegex(ValueError, "duplicate bar"):
            MarketData([PriceBar(day, "A", 1.0, 1.0), PriceBar(day, "A", 1.0, 1.0)], {day: 1.0}, source="s")

    def test_missing_cash_factor_is_rejected(self) -> None:
        day = date(2025, 1, 2)
        with self.assertRaisesRegex(ValueError, "missing cash factor"):
            MarketData([PriceBar(day, "A", 1.0, 1.0)], {}, source="s")

    def test_non_positive_price_is_rejected(self) -> None:
        day = date(2025, 1, 2)
        with self.assertRaisesRegex(ValueError, "non-positive price"):
            MarketData([PriceBar(day, "A", 0.0, 1.0)], {day: 1.0}, source="s")


if __name__ == "__main__":
    unittest.main()
