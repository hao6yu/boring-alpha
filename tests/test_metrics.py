from datetime import date
import math
import statistics
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, PriceBar
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
