"""Sleeves may begin on different dates; gaps after the common start may not."""

from datetime import date, timedelta
import unittest

from boring_alpha.backtest.engine import Backtester, month_end_dates
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.signals.trend import MultiAssetTrend


def _sessions(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _ragged(late_start: date, end: date = date(2022, 6, 30)) -> MarketData:
    """A starts 2020-01-01; B starts later. Prices rise steadily."""

    bars = []
    for index, day in enumerate(_sessions(date(2020, 1, 1), end)):
        bars.append(PriceBar(day, "A", 100.0 + index * 0.05, 100.0 + index * 0.05))
        if day >= late_start:
            bars.append(PriceBar(day, "B", 50.0 + index * 0.02, 50.0 + index * 0.02))
    days = _sessions(date(2020, 1, 1), end)
    return MarketData(bars, {day: 1.00002 for day in days}, source="test")


class SharedCalendarTests(unittest.TestCase):
    def test_shared_sessions_exclude_days_a_symbol_is_missing(self) -> None:
        data = _ragged(date(2020, 7, 1))
        self.assertEqual(data.shared_sessions(("A", "B"))[0], date(2020, 7, 1))
        self.assertEqual(data.shared_sessions(("A",))[0], date(2020, 1, 1))

    def test_month_ends_during_warm_up_are_not_portfolio_month_ends(self) -> None:
        data = _ragged(date(2020, 7, 1))
        shared_month_ends = month_end_dates(data.shared_sessions(("A", "B")))
        self.assertNotIn(date(2020, 1, 31), shared_month_ends)
        self.assertIn(date(2020, 7, 31), shared_month_ends)


class RaggedStartTests(unittest.TestCase):
    def test_a_late_starting_sleeve_does_not_abort_the_run(self) -> None:
        data = _ragged(date(2020, 7, 1))
        result = Backtester(
            data,
            ("A", "B"),
            initial_cash=10_000.0,
            cost_bps=10.0,
            start=date(2021, 8, 1),
            end=date(2022, 6, 30),
        ).run(MultiAssetTrend(("A", "B"), 12, 0.5))
        self.assertTrue(result.trades)
        self.assertGreaterEqual(min(trade.date for trade in result.trades), date(2021, 8, 1))

    def test_the_portfolio_waits_until_every_sleeve_has_a_full_lookback(self) -> None:
        data = _ragged(date(2020, 7, 1))
        result = Backtester(
            data,
            ("A", "B"),
            initial_cash=10_000.0,
            cost_bps=10.0,
            start=date(2021, 1, 1),
            end=date(2022, 6, 30),
        ).run(MultiAssetTrend(("A", "B"), 12, 0.5))
        # B's anchor month (July 2020) is the first with a shared session, so
        # the first decision is the July 2021 month-end.
        self.assertEqual(result.decisions[0].as_of, date(2021, 7, 30))

    def test_a_gap_after_the_common_start_is_a_data_error(self) -> None:
        data = _ragged(date(2020, 7, 1))
        bars = [
            bar
            for day in data.dates
            for bar in data.by_date[day].values()
            if not (bar.symbol == "B" and bar.date == date(2021, 3, 10))
        ]
        holed = MarketData(bars, data.cash_factors, source="test")
        with self.assertRaisesRegex(ValueError, "2021-03-10"):
            Backtester(
                holed,
                ("A", "B"),
                initial_cash=10_000.0,
                cost_bps=10.0,
                start=date(2021, 8, 1),
                end=date(2022, 6, 30),
            )

    def test_a_symbol_absent_entirely_is_still_rejected(self) -> None:
        data = _ragged(date(2020, 7, 1))
        with self.assertRaisesRegex(ValueError, "missing symbols"):
            Backtester(
                data,
                ("A", "B", "C"),
                initial_cash=10_000.0,
                cost_bps=10.0,
                start=date(2021, 8, 1),
                end=date(2022, 6, 30),
            )


if __name__ == "__main__":
    unittest.main()
