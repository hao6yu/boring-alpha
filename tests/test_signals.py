from datetime import date
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.signals.trend import MultiAssetTrend, subtract_months


class SignalTests(unittest.TestCase):
    def test_fixed_sleeves_compare_asset_return_with_cash(self) -> None:
        first = date(2024, 1, 31)
        last = date(2025, 1, 31)
        bars = [
            PriceBar(first, "UP", 100.0, 100.0),
            PriceBar(first, "DOWN", 100.0, 100.0),
            PriceBar(last, "UP", 200.0, 200.0),
            PriceBar(last, "DOWN", 80.0, 80.0),
        ]
        data = MarketData(bars, {first: 1.0, last: 1.05}, source="test")
        snapshot = MultiAssetTrend(("UP", "DOWN"), 12, 0.5).snapshot(data, last)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.target_weights, {"UP": 0.5, "DOWN": 0.0})
        self.assertAlmostEqual(snapshot.cash_return, 0.05)

    def test_calendar_month_subtraction_handles_leap_day(self) -> None:
        self.assertEqual(subtract_months(date(2024, 2, 29), 12), date(2023, 2, 28))


if __name__ == "__main__":
    unittest.main()
