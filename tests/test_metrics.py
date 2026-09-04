from datetime import date
import math
import statistics
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, PriceBar, Trade
from boring_alpha.metrics.performance import calculate_metrics


def _result_and_data(start_equity: float, equities: dict[date, float]):
    curve = tuple(EquityPoint(day, equity, equity, 0.0) for day, equity in equities.items())
    result = BacktestResult("t", start_equity, curve, (), ())
    bars = [PriceBar(day, "A", 1.0, 1.0) for day in equities]
    data = MarketData(bars, {day: 1.0 for day in equities}, source="test")
    return result, data


class MetricsTests(unittest.TestCase):
    def test_max_drawdown_and_total_return_on_a_known_curve(self) -> None:
        result, data = _result_and_data(
            100.0,
            {date(2024, 1, 2): 110.0, date(2024, 1, 3): 99.0, date(2024, 1, 4): 120.0},
        )
        metrics = calculate_metrics(result, data)
        self.assertAlmostEqual(metrics["max_drawdown"], 99.0 / 110.0 - 1.0)
        self.assertAlmostEqual(metrics["total_return"], 0.2)

    def test_cagr_uses_calendar_days_inclusive(self) -> None:
        result, data = _result_and_data(
            100.0, {date(2020, 1, 1): 100.0, date(2020, 12, 31): 110.0}
        )
        metrics = calculate_metrics(result, data)
        self.assertAlmostEqual(metrics["cagr"], 1.1 ** (365.2425 / 366) - 1.0)

    def test_sharpe_versus_cash_annualizes_daily_excess_returns(self) -> None:
        result, data = _result_and_data(
            100.0,
            {
                date(2024, 1, 2): 102.0,
                date(2024, 1, 3): 102.0,
                date(2024, 1, 4): 104.04,
                date(2024, 1, 5): 104.04,
            },
        )
        returns = [0.02, 0.0, 0.02, 0.0]
        expected = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252.0)
        self.assertAlmostEqual(calculate_metrics(result, data)["sharpe_vs_cash"], expected)


if __name__ == "__main__":
    unittest.main()


class ReportedDiagnosticsTests(unittest.TestCase):
    def test_worst_month_finds_the_worst_calendar_month(self) -> None:
        result, data = _result_and_data(
            100.0,
            {
                date(2024, 1, 31): 110.0,
                date(2024, 2, 29): 99.0,
                date(2024, 3, 28): 105.0,
            },
        )
        metrics = calculate_metrics(result, data)
        self.assertAlmostEqual(metrics["worst_month"], 99.0 / 110.0 - 1.0)

    def test_first_month_is_measured_from_the_initial_equity(self) -> None:
        result, data = _result_and_data(
            100.0, {date(2024, 1, 31): 80.0, date(2024, 2, 29): 82.0}
        )
        self.assertAlmostEqual(calculate_metrics(result, data)["worst_month"], -0.2)

    def test_time_in_market_is_the_fraction_of_sessions_holding_anything(self) -> None:
        curve = tuple(
            EquityPoint(day, 100.0, 100.0, exposure)
            for day, exposure in {
                date(2024, 1, 2): 0.0,
                date(2024, 1, 3): 50.0,
                date(2024, 1, 4): 50.0,
                date(2024, 1, 5): 0.0,
            }.items()
        )
        result = BacktestResult("t", 100.0, curve, (), ())
        bars = [PriceBar(point.date, "A", 1.0, 1.0) for point in curve]
        data = MarketData(bars, {point.date: 1.0 for point in curve}, source="test")
        self.assertAlmostEqual(calculate_metrics(result, data)["time_in_market"], 0.5)

    def test_turnover_annualizes_against_average_equity_and_elapsed_years(self) -> None:
        days = {date(2024, 1, 2): 100.0, date(2025, 1, 1): 100.0}
        result, data = _result_and_data(100.0, days)
        trades = (Trade(date(2024, 1, 2), "A", "BUY", 1.0, 50.0, 50.0, 0.0),)
        with_trades = BacktestResult("t", 100.0, result.equity_curve, trades, ())
        metrics = calculate_metrics(with_trades, data)
        self.assertAlmostEqual(metrics["one_way_turnover"], 0.25, places=2)


class TurnoverConventionTests(unittest.TestCase):
    def test_one_way_turnover_counts_one_side_of_a_round_trip(self) -> None:
        days = {date(2024, 1, 2): 100.0, date(2025, 1, 1): 100.0}
        result, data = _result_and_data(100.0, days)
        # A full round trip of 100 of notional is one unit of one-way turnover
        # against 100 of average equity, not two.
        trades = (
            Trade(date(2024, 1, 2), "A", "BUY", 1.0, 100.0, 100.0, 0.0),
            Trade(date(2024, 12, 31), "A", "SELL", 1.0, 100.0, 100.0, 0.0),
        )
        metrics = calculate_metrics(
            BacktestResult("t", 100.0, result.equity_curve, trades, ()), data
        )
        self.assertAlmostEqual(metrics["one_way_turnover"], 1.0, places=2)
