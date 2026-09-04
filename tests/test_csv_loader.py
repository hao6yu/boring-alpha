from datetime import date
from pathlib import Path
import tempfile
import unittest

from boring_alpha.data.csv_loader import load_csv_market_data

PRICES = "date,symbol,tr_open,tr_close\n2024-01-02,SPY,100.0,101.0\n2024-01-03,spy,101.0,102.0\n"
CASH = "date,cash_factor\n2024-01-02,1.0001\n2024-01-03,1.0001\n"


def _load(prices: str, cash: str):
    with tempfile.TemporaryDirectory() as directory:
        prices_path = Path(directory) / "p.csv"
        cash_path = Path(directory) / "c.csv"
        prices_path.write_text(prices, encoding="utf-8")
        cash_path.write_text(cash, encoding="utf-8")
        return load_csv_market_data(prices_path, cash_path)


class CsvLoaderTests(unittest.TestCase):
    def test_loads_bars_and_uppercases_symbols(self) -> None:
        data = _load(PRICES, CASH)
        self.assertEqual(data.symbols, ("SPY",))
        self.assertEqual(data.bar(date(2024, 1, 3), "SPY").close, 102.0)
        self.assertAlmostEqual(data.cash_factors[date(2024, 1, 2)], 1.0001)

    def test_source_label_does_not_depend_on_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("p1", "p2"):
                (root / f"{name}.csv").write_text(PRICES, encoding="utf-8")
            (root / "c.csv").write_text(CASH, encoding="utf-8")
            first = load_csv_market_data(root / "p1.csv", root / "c.csv")
            second = load_csv_market_data(root / "p2.csv", root / "c.csv")
        self.assertEqual(first.source, second.source)

    def test_rejects_unexpected_price_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "price CSV columns"):
            _load(PRICES.replace("tr_open", "open"), CASH)

    def test_rejects_malformed_price_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid price row 3"):
            _load(PRICES.replace("101.0,102.0", "101.0,abc"), CASH)

    def test_rejects_duplicate_cash_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid cash row 3"):
            _load(PRICES, "date,cash_factor\n2024-01-02,1.0\n2024-01-02,1.0\n")

    def test_rejects_price_date_without_cash_factor(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing cash factor"):
            _load(PRICES, "date,cash_factor\n2024-01-02,1.0\n")


if __name__ == "__main__":
    unittest.main()
