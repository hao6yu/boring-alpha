from datetime import date
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch

from boring_alpha.data.csv_loader import _csv_number, load_csv_market_data, load_csv_market_data_bytes

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
    def test_end_filter_skips_protected_numeric_values_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "p.csv").write_text(PRICES + "2024-01-04,SPY,PROTECTED,PROTECTED\n")
            (root / "c.csv").write_text(CASH + "2024-01-04,PROTECTED\n")
            bounded = load_csv_market_data(root / "p.csv", root / "c.csv", end=date(2024, 1, 3))
            self.assertEqual(bounded.fingerprint(), _load(PRICES, CASH).fingerprint())
            with self.assertRaisesRegex(ValueError, "invalid price row"):
                load_csv_market_data(root / "p.csv", root / "c.csv")

    def test_end_filter_still_rejects_invalid_numbers_inside_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "p.csv").write_text(PRICES.replace("101.0,102.0", "PROTECTED,102.0"))
            (root / "c.csv").write_text(CASH)
            with self.assertRaisesRegex(ValueError, "invalid price row 3"):
                load_csv_market_data(root / "p.csv", root / "c.csv", end=date(2024, 1, 3))

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


class SafeCsvDiagnosticsTests(unittest.TestCase):
    def _error(self, prices: bytes, cash: bytes, *, end: date | None = None) -> tuple[ValueError, str]:
        try:
            load_csv_market_data_bytes(prices, cash, end=end)
        except ValueError as error:
            return error, "".join(traceback.format_exception(error))
        self.fail("invalid input was accepted")

    def test_malformed_dates_never_print_the_row_or_original_exception(self) -> None:
        cases = (
            ("price", b"date,symbol,tr_open,tr_close\nSEALED-DATE,SEALED-SYMBOL,987654.321,123456.789\n", CASH.encode()),
            ("cash", PRICES.encode(), b"date,cash_factor\nSEALED-DATE,987654.321\n"),
        )
        for source, prices, cash in cases:
            with self.subTest(source=source):
                with patch("boring_alpha.data.csv_loader._csv_number", wraps=_csv_number) as numbers:
                    error, rendered = self._error(prices, cash, end=date(2023, 12, 31))
                self.assertEqual(str(error), f"invalid {source} row 2: field 'date'")
                self.assertFalse(any(call.args[2] == source for call in numbers.call_args_list))
                for protected in ("SEALED-DATE", "SEALED-SYMBOL", "987654.321", "123456.789"):
                    self.assertNotIn(protected, rendered)
                self.assertTrue(error.__suppress_context__)
                self.assertIsNone(error.__cause__)
                self.assertNotIn("During handling", rendered)

    def test_numeric_conversion_failures_expose_only_the_field(self) -> None:
        cases = (
            ("price", "tr_open", PRICES.replace("100.0", "PRIVATE-NUMBER").encode(), CASH.encode()),
            ("price", "tr_close", PRICES.replace("100.0,101.0", "100.0,PRIVATE-NUMBER").encode(), CASH.encode()),
            ("cash", "cash_factor", PRICES.encode(), CASH.replace("1.0001", "PRIVATE-NUMBER").encode()),
        )
        for source, field, prices, cash in cases:
            with self.subTest(source=source, field=field):
                error, rendered = self._error(prices, cash)
                self.assertEqual(str(error), f"invalid {source} row 2: field '{field}'")
                self.assertNotIn("PRIVATE-NUMBER", rendered)
                self.assertNotIn("could not convert string to float", rendered)
                self.assertTrue(error.__suppress_context__)

    def test_corrupt_headers_do_not_echo_possible_observations(self) -> None:
        for source, prices, cash in (
            ("price", b"SEALED-HEADER,987654.321\n", CASH.encode()),
            ("cash", PRICES.encode(), b"SEALED-HEADER,987654.321\n"),
        ):
            with self.subTest(source=source):
                error, rendered = self._error(prices, cash)
                self.assertIn(f"{source} CSV columns", str(error))
                self.assertNotIn("SEALED-HEADER", rendered)
                self.assertNotIn("987654.321", rendered)

    def test_duplicate_header_is_not_an_exact_schema(self) -> None:
        prices = PRICES.replace("date,symbol,tr_open,tr_close", "date,symbol,tr_open,tr_close,tr_close").encode()
        error, _ = self._error(prices, CASH.encode())
        self.assertIn("price CSV columns", str(error))

    def test_malformed_retained_rows_report_safe_fields(self) -> None:
        cases = (
            (b"date,symbol,tr_open,tr_close\n2024-01-02\n", "symbol"),
            (b"date,symbol,tr_open,tr_close\n2024-01-02,SPY,100\n", "tr_close"),
            (b"date,symbol,tr_open,tr_close\n2024-01-02,SPY,100,101,SEALED-EXTRA\n", "columns"),
        )
        for prices, field in cases:
            with self.subTest(field=field):
                error, rendered = self._error(prices, CASH.encode())
                self.assertEqual(str(error), f"invalid price row 2: field '{field}'")
                self.assertNotIn("SEALED-EXTRA", rendered)

    def test_future_rows_skip_symbol_shape_and_numeric_validation(self) -> None:
        prices = PRICES.encode() + b"2024-01-04,,PRIVATE-NUMBER,PRIVATE-NUMBER,SEALED-EXTRA\n"
        cash = CASH.encode() + b"2024-01-04,PRIVATE-NUMBER,SEALED-EXTRA\n"
        bounded = load_csv_market_data_bytes(prices, cash, end=date(2024, 1, 3))
        self.assertEqual(bounded.fingerprint(), _load(PRICES, CASH).fingerprint())

    def test_invalid_encoding_does_not_echo_bytes(self) -> None:
        error, rendered = self._error(PRICES.encode() + b"\xffPRIVATE-BYTES", CASH.encode())
        self.assertEqual(str(error), "invalid price CSV: field 'encoding' (UTF-8 required)")
        self.assertNotIn("PRIVATE-BYTES", rendered)
        self.assertNotIn("0xff", rendered)

    def test_finite_values_are_checked_even_for_cash_only_dates(self) -> None:
        error, _ = self._error(PRICES.encode(), CASH.encode() + b"2024-01-04,nan\n")
        self.assertEqual(str(error), "invalid cash row 4: field 'cash_factor' (not a finite number)")


if __name__ == "__main__":
    unittest.main()
