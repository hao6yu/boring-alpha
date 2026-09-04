"""The ledger must record what was intended, not only what happened."""

from datetime import date
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar
from boring_alpha.report import ARTIFACT_SCHEMA, _trades_csv
from boring_alpha.signals.trend import MultiAssetTrend

ANCHOR, SIGNAL, FILL = date(2023, 12, 29), date(2024, 12, 31), date(2025, 1, 2)


def _run():
    bars = [
        PriceBar(ANCHOR, "A", 100.0, 100.0),
        PriceBar(SIGNAL, "A", 120.0, 120.0),
        # The open gaps up from the month-end close: that gap is the slippage.
        PriceBar(FILL, "A", 132.0, 132.0),
    ]
    days = [ANCHOR, SIGNAL, FILL]
    data = MarketData(bars, {day: 1.0 for day in days}, source="test")
    return Backtester(
        data, ("A",), initial_cash=1_000.0, cost_bps=0.0, start=FILL, end=FILL
    ).run(MultiAssetTrend(("A",), 12, 1.0))


class SlippageTests(unittest.TestCase):
    def test_the_schema_records_the_wider_ledger(self) -> None:
        self.assertEqual(ARTIFACT_SCHEMA, 5)

    def test_the_ledger_header_names_intent_and_reference(self) -> None:
        header = _trades_csv(_run()).splitlines()[0]
        self.assertEqual(
            header,
            "date,symbol,side,quantity,price,notional,cost,intended_notional,reference_price",
        )

    def test_the_reference_price_differs_from_the_fill_price(self) -> None:
        row = _trades_csv(_run()).splitlines()[1].split(",")
        self.assertEqual(float(row[4]), 132.0)   # filled at the next open
        self.assertEqual(float(row[8]), 120.0)   # decided at the month-end close

    def test_a_fully_filled_order_reports_equal_notionals(self) -> None:
        row = _trades_csv(_run()).splitlines()[1].split(",")
        self.assertAlmostEqual(float(row[5]), float(row[7]))


if __name__ == "__main__":
    unittest.main()
