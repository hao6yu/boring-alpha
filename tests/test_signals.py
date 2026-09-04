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


from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.signals.trend import TargetExposureAllocation


def _two_symbol_data(days: list[date]) -> MarketData:
    bars = [
        PriceBar(day, symbol, 100.0 + index, 100.0 + index)
        for index, day in enumerate(days)
        for symbol in ("A", "B")
    ]
    return MarketData(bars, {day: 1.0 for day in days}, source="test")


class TargetExposureTests(unittest.TestCase):
    DAYS = [date(2023, 11, 30), date(2023, 12, 29), date(2024, 11, 29), date(2024, 12, 31)]

    def test_weights_sum_to_the_target_exposure(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual")
        snapshot = policy.snapshot(_two_symbol_data(self.DAYS), date(2024, 12, 31))
        assert snapshot is not None
        self.assertAlmostEqual(sum(snapshot.target_weights.values()), 0.6)
        self.assertAlmostEqual(snapshot.target_weights["A"], 0.3)

    def test_annual_holds_except_at_the_december_month_end(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual")
        data = _two_symbol_data(self.DAYS)
        november = policy.snapshot(data, date(2024, 11, 29))
        december = policy.snapshot(data, date(2024, 12, 31))
        assert november is not None and december is not None
        self.assertTrue(november.hold)
        self.assertFalse(december.hold)
        # A hold still carries the targets: the engine uses them on an empty book.
        self.assertAlmostEqual(sum(november.target_weights.values()), 0.6)

    def test_monthly_never_holds(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "monthly")
        snapshot = policy.snapshot(_two_symbol_data(self.DAYS), date(2024, 11, 29))
        assert snapshot is not None
        self.assertFalse(snapshot.hold)

    def test_the_name_states_exposure_and_schedule(self) -> None:
        self.assertEqual(
            TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual").name,
            "Target-Exposure Benchmark (60%, annual)",
        )

    def test_an_unknown_schedule_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "rebalance"):
            TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "weekly")

    def test_insufficient_history_still_yields_no_signal(self) -> None:
        policy = TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, "annual")
        self.assertIsNone(policy.snapshot(_two_symbol_data(self.DAYS), date(2023, 11, 30)))

    def test_schedules_are_the_configuration_s_schedules(self) -> None:
        from boring_alpha.config import REBALANCE_SCHEDULES as configured
        from boring_alpha.domain import REBALANCE_SCHEDULES as shared

        self.assertIs(configured, shared)
        for schedule in shared:
            TargetExposureAllocation(("A", "B"), 12, 0.5, 0.6, schedule)


if __name__ == "__main__":
    unittest.main()
