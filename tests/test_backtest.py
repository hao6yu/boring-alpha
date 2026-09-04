from datetime import date
import unittest

from boring_alpha.backtest.engine import Backtester, month_end_dates
from boring_alpha.data.market import MarketData
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.domain import PriceBar
from boring_alpha.metrics.performance import calculate_metrics
from boring_alpha.signals.trend import MultiAssetTrend


def _flat_data(symbol: str, closes: dict[date, float]) -> MarketData:
    bars = [PriceBar(day, symbol, close, close) for day, close in closes.items()]
    return MarketData(bars, {day: 1.0 for day in closes}, source="test")


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
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].date, execution_day)
        self.assertEqual(result.fills[0].price, 200.0)
        self.assertAlmostEqual(result.fills[0].quantity, 5.0)

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

    def test_month_end_without_history_is_recorded_as_warning(self) -> None:
        data = _flat_data(
            "A",
            {
                date(2024, 12, 31): 100.0,
                date(2025, 1, 2): 100.0,
                date(2025, 1, 31): 100.0,
                date(2025, 2, 3): 100.0,
            },
        )
        result = Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=0.0,
            start=date(2025, 1, 2),
            end=date(2025, 2, 3),
        ).run(MultiAssetTrend(("A",), 12, 1.0))
        self.assertEqual(result.fills, ())
        self.assertTrue(any("2024-12-31" in warning for warning in result.warnings))
        self.assertTrue(any("2025-01-31" in warning for warning in result.warnings))

    def test_only_the_decisive_pre_start_absence_is_recorded(self) -> None:
        data = _flat_data(
            "A",
            {
                date(2024, 11, 29): 100.0,
                date(2024, 12, 2): 100.0,
                date(2024, 12, 31): 100.0,
                date(2025, 1, 2): 100.0,
            },
        )
        result = Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=0.0,
            start=date(2025, 1, 1),
            end=date(2025, 1, 2),
        ).run(MultiAssetTrend(("A",), 12, 1.0))
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("2024-12-31", result.warnings[0])

    def test_start_before_the_first_session_is_accepted(self) -> None:
        data = _flat_data("A", {date(2025, 1, 15): 1.0, date(2025, 1, 16): 1.0})
        Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=0.0,
            start=date(2025, 1, 1),
            end=date(2025, 1, 16),
        )

    def test_start_inside_a_month_is_rejected(self) -> None:
        data = _flat_data(
            "A", {date(2025, 1, 2): 1.0, date(2025, 1, 15): 1.0, date(2025, 1, 16): 1.0}
        )
        with self.assertRaisesRegex(ValueError, "first session of a month"):
            Backtester(
                data,
                ("A",),
                initial_cash=1_000.0,
                cost_bps=0.0,
                start=date(2025, 1, 16),
                end=date(2025, 1, 16),
            )

    def test_start_on_a_weekend_is_accepted_when_the_next_session_opens_a_month(self) -> None:
        data = _flat_data("A", {date(2025, 1, 31): 1.0, date(2025, 2, 3): 1.0})
        Backtester(
            data,
            ("A",),
            initial_cash=1_000.0,
            cost_bps=0.0,
            start=date(2025, 2, 1),
            end=date(2025, 2, 3),
        )

    def test_month_end_dates_exclude_the_final_dataset_date(self) -> None:
        dates = (date(2024, 12, 30), date(2024, 12, 31), date(2025, 1, 2), date(2025, 1, 15))
        self.assertEqual(month_end_dates(dates), {date(2024, 12, 31)})

    def test_month_end_dates_compare_year_and_month(self) -> None:
        dates = (date(2024, 1, 31), date(2025, 1, 2), date(2025, 1, 3))
        self.assertEqual(month_end_dates(dates), {date(2024, 1, 31)})

    def test_future_prices_do_not_change_past_results(self) -> None:
        symbols = ("A", "B")
        data = generate_synthetic_market_data(
            symbols, date(2020, 1, 1), date(2022, 12, 30), seed=3, annual_cash_rate=0.01
        )
        cutoff = date(2022, 6, 30)
        perturbed_bars = [
            PriceBar(bar.date, bar.symbol, bar.open * 0.5, bar.close * 0.5)
            if bar.date > cutoff
            else bar
            for day in data.dates
            for bar in data.by_date[day].values()
        ]
        perturbed = MarketData(perturbed_bars, data.cash_factors, source="perturbed")

        def run(market: MarketData):
            engine = Backtester(
                market,
                symbols,
                initial_cash=10_000.0,
                cost_bps=10.0,
                start=date(2021, 1, 1),
                end=date(2022, 12, 30),
            )
            return engine.run(MultiAssetTrend(symbols, 12, 0.5))

        base, other = run(data), run(perturbed)
        self.assertEqual(
            [d for d in base.decisions if d.as_of <= cutoff],
            [d for d in other.decisions if d.as_of <= cutoff],
        )
        self.assertEqual(
            [t for t in base.fills if t.date <= cutoff],
            [t for t in other.fills if t.date <= cutoff],
        )
        self.assertEqual(
            [e for e in base.equity_curve if e.date <= cutoff],
            [e for e in other.equity_curve if e.date <= cutoff],
        )
        self.assertNotEqual(base.equity_curve[-1], other.equity_curve[-1])


if __name__ == "__main__":
    unittest.main()
