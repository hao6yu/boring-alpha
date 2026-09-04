"""The fetcher decides what counts as data, so its rules need pinning."""

from datetime import date
import importlib.util
from pathlib import Path
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "fetch_market_data", Path(__file__).resolve().parent.parent / "tools" / "fetch_market_data.py"
)
fetcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetcher)


def _chart(stamps, opens, closes, adjcloses, offset=0):
    return {
        "meta": {"gmtoffset": offset},
        "timestamp": list(stamps),
        "indicators": {
            "quote": [{"open": list(opens), "close": list(closes)}],
            "adjclose": [{"adjclose": list(adjcloses)}],
        },
    }


DAY1, DAY2 = 1_700_000_000, 1_700_086_400   # 2023-11-14, 2023-11-15 UTC


class AdjustmentTests(unittest.TestCase):
    def test_the_open_is_put_on_the_close_s_adjusted_basis(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1], [100.0], [110.0], [55.0]), date(2030, 1, 1)
        )
        # factor = 55/110 = 0.5, so the open adjusts to 50.
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0][1], 50.0)
        self.assertAlmostEqual(rows[0][2], 55.0)

    def test_an_unadjusted_series_passes_through_unchanged(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1], [100.0], [110.0], [110.0]), date(2030, 1, 1)
        )
        self.assertAlmostEqual(rows[0][1], 100.0)


class IncompleteSessionTests(unittest.TestCase):
    def test_a_session_dated_today_is_dropped(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1, DAY2], [1.0, 2.0], [1.0, 2.0], [1.0, 2.0]), date(2023, 11, 15)
        )
        self.assertEqual([row[0] for row in rows], [date(2023, 11, 14)])

    def test_completed_sessions_are_kept(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1, DAY2], [1.0, 2.0], [1.0, 2.0], [1.0, 2.0]), date(2023, 11, 16)
        )
        self.assertEqual(len(rows), 2)


class BadRowTests(unittest.TestCase):
    def test_missing_values_are_dropped(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1, DAY2], [None, 2.0], [1.0, 2.0], [1.0, 2.0]), date(2030, 1, 1)
        )
        self.assertEqual(len(rows), 1)

    def test_non_finite_values_are_dropped(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1, DAY2], [float("nan"), 2.0], [1.0, 2.0], [1.0, 2.0]), date(2030, 1, 1)
        )
        self.assertEqual(len(rows), 1)

    def test_non_positive_prices_are_dropped(self) -> None:
        rows = fetcher.rows_from_chart(
            _chart([DAY1, DAY2], [1.0, 2.0], [0.0, 2.0], [1.0, 2.0]), date(2030, 1, 1)
        )
        self.assertEqual(len(rows), 1)


class CashFactorTests(unittest.TestCase):
    RATES = [(date(2020, 1, 6), 1.50), (date(2020, 1, 7), 3.00)]

    def test_a_session_uses_the_last_rate_known_before_it(self) -> None:
        factors = fetcher.cash_factors([date(2020, 1, 8)], self.RATES)
        self.assertAlmostEqual(factors[date(2020, 1, 8)], 1.03 ** (1 / 252))

    def test_the_same_day_rate_is_not_used(self) -> None:
        # On the 7th only the 6th's rate is known, so 1.50 must be used, not 3.00.
        factors = fetcher.cash_factors([date(2020, 1, 7)], self.RATES)
        self.assertAlmostEqual(factors[date(2020, 1, 7)], 1.015 ** (1 / 252))

    def test_sessions_before_the_first_observation_fall_back_to_it(self) -> None:
        factors = fetcher.cash_factors([date(2019, 12, 31)], self.RATES)
        self.assertAlmostEqual(factors[date(2019, 12, 31)], 1.015 ** (1 / 252))

    def test_a_zero_rate_leaves_cash_flat(self) -> None:
        factors = fetcher.cash_factors([date(2021, 1, 4)], [(date(2020, 1, 1), 0.0)])
        self.assertEqual(factors[date(2021, 1, 4)], 1.0)


class ProvenanceTests(unittest.TestCase):
    def test_the_cash_series_is_quoted_on_an_investment_basis(self) -> None:
        # DTB3 is a bank-discount quote and is not a return on money invested;
        # using it would understate cash and flatter a rule that must beat it.
        self.assertEqual(fetcher.FRED_SERIES, "DGS3MO")
        self.assertIn("DGS3MO", fetcher.FRED_URL)


if __name__ == "__main__":
    unittest.main()


class SnapshotTests(unittest.TestCase):
    """Prices and cash must move together, or they can be read as a mismatched pair."""

    PRICES = [["date", "symbol", "tr_open", "tr_close"], ["2024-01-02", "A", "1", "1"]]
    CASH = [["date", "cash_factor"], ["2024-01-02", "1.0001"]]
    COVERAGE = {"A": {"first": "2024-01-02", "last": "2024-01-02", "rows": "1"}}

    def _write(self, out):
        return fetcher.write_snapshot(out, self.PRICES, self.CASH, self.COVERAGE)

    def test_a_snapshot_holds_both_files_and_a_manifest(self) -> None:
        import tempfile

        out = Path(tempfile.mkdtemp())
        snapshot = self._write(out)
        for name in ("market_daily.csv", "cash_daily.csv", "manifest.json"):
            self.assertTrue((snapshot / name).is_file(), name)

    def test_the_manifest_records_the_methodology_a_config_must_repeat(self) -> None:
        import json, tempfile

        snapshot = self._write(Path(tempfile.mkdtemp()))
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["methodology"], fetcher.METHODOLOGY)
        self.assertEqual(manifest["cash_series"], "DGS3MO")
        self.assertIn("investment", manifest["cash_basis"])

    def test_current_points_at_the_finished_snapshot(self) -> None:
        import tempfile

        out = Path(tempfile.mkdtemp())
        snapshot = self._write(out)
        self.assertTrue((out / "current").is_symlink())
        self.assertEqual((out / "current").resolve(), snapshot.resolve())

    def test_a_second_snapshot_repoints_current_without_touching_the_first(self) -> None:
        import tempfile, time

        out = Path(tempfile.mkdtemp())
        first = self._write(out)
        time.sleep(1.1)   # snapshot names are second-resolution
        second = self._write(out)
        self.assertNotEqual(first, second)
        self.assertTrue((first / "manifest.json").is_file())
        self.assertEqual((out / "current").resolve(), second.resolve())

    def test_an_existing_snapshot_directory_is_never_overwritten(self) -> None:
        import tempfile

        out = Path(tempfile.mkdtemp())
        self._write(out)
        with self.assertRaises(FileExistsError):
            self._write(out)   # same second, so the same directory name
