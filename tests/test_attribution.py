"""Per-sleeve contribution must account for the whole change in equity."""

from datetime import date
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.signals.trend import MultiAssetTrend

ANCHOR, SIGNAL = date(2023, 12, 29), date(2024, 12, 31)
FIRST, SECOND = date(2025, 1, 2), date(2025, 1, 3)


def _data(factor: float = 1.0) -> MarketData:
    bars = [
        PriceBar(ANCHOR, "A", 100.0, 100.0), PriceBar(ANCHOR, "B", 100.0, 100.0),
        PriceBar(SIGNAL, "A", 120.0, 120.0), PriceBar(SIGNAL, "B", 90.0, 90.0),
        PriceBar(FIRST, "A", 120.0, 132.0), PriceBar(FIRST, "B", 90.0, 90.0),
        PriceBar(SECOND, "A", 132.0, 121.0), PriceBar(SECOND, "B", 90.0, 90.0),
    ]
    days = [ANCHOR, SIGNAL, FIRST, SECOND]
    return MarketData(bars, {day: factor for day in days}, source="test")


def _run(factor: float = 1.0):
    data = _data(factor)
    return data, Backtester(
        data, ("A", "B"), initial_cash=1_000.0, cost_bps=0.0,
        start=FIRST, end=SECOND,
    ).run(MultiAssetTrend(("A", "B"), 12, 0.5))


class AttributionTests(unittest.TestCase):
    def test_only_the_active_sleeve_contributes(self) -> None:
        _, result = _run()
        # A beat cash and was bought at 120; B did not and stayed in cash.
        self.assertEqual(result.contributions["B"], 0.0)
        self.assertGreater(result.contributions["A"], 0.0)

    def test_contribution_equals_the_position_times_the_price_change(self) -> None:
        _, result = _run()
        # 500 of equity buys 4.1667 shares at 120; the close ends at 121.
        self.assertAlmostEqual(result.contributions["A"], 500.0 / 120.0 * (121.0 - 120.0))

    def test_contributions_and_cash_interest_explain_the_whole_equity_change(self) -> None:
        _, result = _run(factor=1.0001)
        change = result.equity_curve[-1].equity - result.initial_equity
        sleeves = sum(result.contributions.values())
        self.assertAlmostEqual(change, sleeves + result.cash_interest, places=9)

    def test_costs_are_charged_to_the_sleeve_that_traded(self) -> None:
        data = _data()
        result = Backtester(
            data, ("A", "B"), initial_cash=1_000.0, cost_bps=100.0,
            start=FIRST, end=SECOND,
        ).run(MultiAssetTrend(("A", "B"), 12, 0.5))
        without_cost = 500.0 / 120.0 * (121.0 - 120.0)
        self.assertLess(result.contributions["A"], without_cost)


if __name__ == "__main__":
    unittest.main()
