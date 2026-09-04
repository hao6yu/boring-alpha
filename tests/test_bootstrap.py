from datetime import date
import unittest

from boring_alpha.data.market import MarketData
from boring_alpha.domain import BacktestResult, EquityPoint, PriceBar
from boring_alpha.metrics.bootstrap import sharpe_difference_interval
from boring_alpha.metrics.performance import excess_return_series


def _alternating(n: int, high: float, low: float) -> list[float]:
    return [high if index % 2 else low for index in range(n)]


class BootstrapTests(unittest.TestCase):
    def test_identical_series_give_a_zero_difference_and_a_zero_interval(self) -> None:
        series = _alternating(500, 0.004, -0.002)
        result = sharpe_difference_interval(series, list(series), seed=1, resamples=120)
        self.assertAlmostEqual(result["point"], 0.0)
        self.assertAlmostEqual(result["low"], 0.0)
        self.assertAlmostEqual(result["high"], 0.0)

    def test_the_interval_is_reproducible_for_a_seed(self) -> None:
        first = _alternating(400, 0.006, -0.003)
        second = _alternating(400, 0.004, -0.003)
        a = sharpe_difference_interval(first, second, seed=7, resamples=120)
        b = sharpe_difference_interval(first, second, seed=7, resamples=120)
        self.assertEqual(a, b)
        self.assertNotEqual(a, sharpe_difference_interval(first, second, seed=8, resamples=120))

    def test_the_interval_brackets_the_point_estimate(self) -> None:
        first = _alternating(400, 0.006, -0.003)
        second = _alternating(400, 0.004, -0.003)
        result = sharpe_difference_interval(first, second, seed=3, resamples=120)
        self.assertLessEqual(result["low"], result["point"])
        self.assertLessEqual(result["point"], result["high"])

    def test_mismatched_series_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "same length"):
            sharpe_difference_interval([0.1, 0.2], [0.1], seed=1, resamples=120)


class ExcessReturnTests(unittest.TestCase):
    def test_excess_returns_subtract_the_session_cash_rate(self) -> None:
        days = [date(2024, 1, 2), date(2024, 1, 3)]
        curve = (EquityPoint(days[0], 100.0, 0.0, 0.0), EquityPoint(days[1], 110.0, 0.0, 0.0))
        result = BacktestResult("t", 100.0, curve, (), ())
        data = MarketData(
            [PriceBar(day, "A", 1.0, 1.0) for day in days],
            {days[0]: 1.0, days[1]: 1.01},
            source="test",
        )
        series = excess_return_series(result, data)
        self.assertAlmostEqual(series[0], 0.0)
        self.assertAlmostEqual(series[1], 0.1 - 0.01)


if __name__ == "__main__":
    unittest.main()
