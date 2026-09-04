from datetime import date
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.metrics.performance import calculate_metrics
from boring_alpha.signals.trend import MultiAssetTrend


class BacktestTests(unittest.TestCase):
    def test_month_end_signal_executes_at_next_session_open(self) -> None:
        anchor = date(2024, 1, 31)
        signal_day = date(2025, 1, 31)
        execution_day = date(2025, 2, 3)
        bars = [
            PriceBar(anchor, "A", 100.0, 100.0),
            PriceBar(signal_day, "A", 110.0, 110.0),
            PriceBar(execution_day, "A", 200.0, 200.0),
        ]
        data = MarketData(
            bars, {anchor: 1.0, signal_day: 1.0, execution_day: 1.0}, source="test"
        )
        engine = Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=0.0,
            start=execution_day,
            end=execution_day,
        )
        result = engine.run(MultiAssetTrend(("A",), 12, 1.0))
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].date, execution_day)
        self.assertEqual(result.trades[0].price, 200.0)
        self.assertAlmostEqual(result.trades[0].quantity, 5.0)

    def test_costs_are_funded_without_negative_cash(self) -> None:
        anchor = date(2024, 1, 31)
        signal_day = date(2025, 1, 31)
        execution_day = date(2025, 2, 3)
        bars = [
            PriceBar(anchor, "A", 50.0, 50.0),
            PriceBar(signal_day, "A", 100.0, 100.0),
            PriceBar(execution_day, "A", 100.0, 100.0),
        ]
        data = MarketData(
            bars, {anchor: 1.0, signal_day: 1.0, execution_day: 1.0}, source="test"
        )
        result = Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=100.0,
            start=execution_day,
            end=execution_day,
        ).run(MultiAssetTrend(("A",), 12, 1.0))
        self.assertGreaterEqual(result.equity_curve[-1].cash, -1e-9)
        self.assertAlmostEqual(result.equity_curve[-1].equity, 1_000.0 / 1.01)

    def test_metrics_include_initial_execution_cost(self) -> None:
        anchor = date(2024, 1, 31)
        signal_day = date(2025, 1, 31)
        first = date(2025, 2, 3)
        second = date(2025, 2, 4)
        bars = [
            PriceBar(anchor, "A", 50.0, 50.0),
            PriceBar(signal_day, "A", 100.0, 100.0),
            PriceBar(first, "A", 100.0, 100.0),
            PriceBar(second, "A", 100.0, 100.0),
        ]
        data = MarketData(
            bars,
            {anchor: 1.0, signal_day: 1.0, first: 1.0, second: 1.0},
            source="test",
        )
        result = Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=100.0,
            start=first,
            end=second,
        ).run(MultiAssetTrend(("A",), 12, 1.0))
        metrics = calculate_metrics(result, data)
        self.assertAlmostEqual(metrics["total_return"], 1.0 / 1.01 - 1.0)


if __name__ == "__main__":
    unittest.main()
