from datetime import date
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.signals.trend import FixedAllocation, MultiAssetTrend, month_offset


def _single_symbol_data(closes: dict[date, float]) -> MarketData:
    bars = [PriceBar(day, "A", close, close) for day, close in closes.items()]
    return MarketData(bars, {day: 1.0 for day in closes}, source="test")


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

    def test_anchor_is_prior_year_month_end_not_same_calendar_date(self) -> None:
        # 2019-03-29 is the March 2019 month-end. The same calendar date a year
        # earlier (2018-03-29) was one session before the March 2018 month-end.
        data = _single_symbol_data(
            {date(2018, 3, 29): 100.0, date(2018, 3, 30): 110.0, date(2019, 3, 29): 121.0}
        )
        snapshot = MultiAssetTrend(("A",), 12, 1.0).snapshot(data, date(2019, 3, 29))
        assert snapshot is not None
        self.assertAlmostEqual(snapshot.asset_returns["A"], 121.0 / 110.0 - 1.0)

    def test_no_signal_when_anchor_month_has_no_session(self) -> None:
        data = _single_symbol_data({date(2019, 2, 28): 100.0, date(2019, 3, 29): 110.0})
        self.assertIsNone(MultiAssetTrend(("A",), 12, 1.0).snapshot(data, date(2019, 3, 29)))

    def test_month_offset_crosses_year_boundaries(self) -> None:
        self.assertEqual(month_offset(2019, 1, -12), (2018, 1))
        self.assertEqual(month_offset(2019, 1, -15), (2017, 10))
        self.assertEqual(month_offset(2019, 1, -13), (2017, 12))

    def test_static_benchmark_waits_for_the_same_warm_up(self) -> None:
        short = _single_symbol_data({date(2019, 2, 28): 100.0, date(2019, 3, 29): 110.0})
        self.assertIsNone(FixedAllocation(("A",), 12, 0.5).snapshot(short, date(2019, 3, 29)))
        full = _single_symbol_data({date(2018, 3, 30): 100.0, date(2019, 3, 29): 110.0})
        snapshot = FixedAllocation(("A",), 12, 0.5).snapshot(full, date(2019, 3, 29))
        assert snapshot is not None
        self.assertEqual(snapshot.target_weights, {"A": 0.5})


if __name__ == "__main__":
    unittest.main()
