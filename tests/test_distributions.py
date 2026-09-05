"""The distributions file is read by the tax overlay alone; it must be strict."""

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.data.distributions import DistributionTable, load_distributions, split_records
from boring_alpha.data.market import MarketData
from boring_alpha.domain import PriceBar

CSV = """date,symbol,close,dividend
2024-01-02,A,100.0,0.0
2024-01-02,B,50.0,0.0
2024-01-03,A,101.0,0.5
2024-01-03,B,51.0,0.0
2024-01-04,A,102.0,0.0
2024-01-04,B,52.0,0.25
"""
MANIFEST = {"splits": {"A": [{"date": "2005-06-09", "ratio": "2:1"}], "B": []}}


def _write(root: Path, csv_text: str = CSV, manifest: dict | None = MANIFEST) -> tuple[Path, Path | None]:
    csv_path = root / "distributions_daily.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    manifest_path = None
    if manifest is not None:
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return csv_path, manifest_path


class ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_loads_close_and_dividend_by_session_and_symbol(self) -> None:
        csv_path, manifest_path = _write(self.root)
        table = load_distributions(csv_path, manifest_path=manifest_path)
        self.assertEqual(table.close(date(2024, 1, 3), "A"), 101.0)
        self.assertEqual(table.dividend(date(2024, 1, 3), "A"), 0.5)
        self.assertEqual(table.dividend(date(2024, 1, 3), "B"), 0.0)
        self.assertEqual(table.symbols, ("A", "B"))
        self.assertEqual(table.dates, (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)))
        self.assertEqual(table.splits, MANIFEST["splits"])
        self.assertEqual(len(table.sha256), 64)

    def test_ex_dates_list_only_sessions_with_a_dividend(self) -> None:
        csv_path, manifest_path = _write(self.root)
        table = load_distributions(csv_path, manifest_path=manifest_path)
        self.assertEqual(table.ex_dates("A"), (date(2024, 1, 3),))
        self.assertEqual(table.ex_dates("B"), (date(2024, 1, 4),))
        self.assertEqual(table.ex_dates("Z"), ())

    def test_exact_columns_are_required(self) -> None:
        csv_path, manifest_path = _write(self.root, "date,symbol,close\n2024-01-02,A,1\n")
        with self.assertRaisesRegex(ValueError, "columns must be exactly"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_negative_dividend_is_refused(self) -> None:
        csv_path, manifest_path = _write(
            self.root, "date,symbol,close,dividend\n2024-01-02,A,1,-0.1\n"
        )
        with self.assertRaisesRegex(ValueError, "negative dividend"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_non_positive_close_is_refused(self) -> None:
        csv_path, manifest_path = _write(self.root, "date,symbol,close,dividend\n2024-01-02,A,0,0\n")
        with self.assertRaisesRegex(ValueError, "non-positive close"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_duplicate_row_is_refused(self) -> None:
        csv_path, manifest_path = _write(
            self.root, "date,symbol,close,dividend\n2024-01-02,A,1,0\n2024-01-02,A,1,0\n"
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_distributions(csv_path, manifest_path=manifest_path)

    def test_a_missing_lookup_is_a_value_error(self) -> None:
        csv_path, manifest_path = _write(self.root)
        table = load_distributions(csv_path, manifest_path=manifest_path)
        with self.assertRaisesRegex(ValueError, "no distribution row"):
            table.close(date(2024, 1, 5), "A")


class SplitRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_split_records_may_come_from_an_embedded_block(self) -> None:
        csv_path, _ = _write(self.root, manifest=None)
        table = load_distributions(csv_path, manifest_block=MANIFEST)
        self.assertEqual(table.splits, MANIFEST["splits"])

    def test_a_manifest_without_splits_is_refused(self) -> None:
        csv_path, manifest_path = _write(self.root, manifest={"methodology": "x"})
        with self.assertRaisesRegex(ValueError, "no 'splits' key"):
            load_distributions(csv_path, manifest_path=manifest_path)
        with self.assertRaisesRegex(ValueError, "no 'splits' key"):
            split_records({"methodology": "x"})

    def test_exactly_one_manifest_source_is_required(self) -> None:
        csv_path, manifest_path = _write(self.root)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            load_distributions(csv_path)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            load_distributions(csv_path, manifest_path=manifest_path, manifest_block=MANIFEST)


class TruncationAndCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp())
        csv_path, manifest_path = _write(root)
        self.table = load_distributions(csv_path, manifest_path=manifest_path)

    def _market(self, days) -> MarketData:
        bars = [PriceBar(day, symbol, 1.0, 1.0) for day in days for symbol in ("A", "B")]
        return MarketData(bars, {day: 1.0 for day in days}, source="test")

    def test_through_rehashes_the_input_and_preserves_source_provenance(self) -> None:
        truncated = self.table.through(date(2024, 1, 3))
        self.assertEqual(truncated.dates, (date(2024, 1, 2), date(2024, 1, 3)))
        self.assertNotEqual(truncated.sha256, self.table.sha256)
        self.assertNotEqual(truncated.csv_sha256, self.table.csv_sha256)
        self.assertEqual(truncated.source_sha256, self.table.source_sha256)
        self.assertEqual(truncated.splits, self.table.splits)
        self.assertIn("truncated=2024-01-03", truncated.source)
        with self.assertRaisesRegex(ValueError, "leaves no rows"):
            self.table.through(date(2023, 1, 1))

    def test_future_rows_and_splits_do_not_enter_the_truncated_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = CSV.replace("2024-01-04,A,102.0,0.0", "2024-01-04,A,999.0,50.0")
            changed += "2024-01-04,NEW,100.0,0.0\n"
            manifest = {"splits": {"A": MANIFEST["splits"]["A"] + [
                {"date": "2024-01-04", "ratio": "3:1"}
            ], "B": [], "NEW": []}}
            path, manifest_path = _write(root, changed, manifest)
            future = load_distributions(path, manifest_path=manifest_path)
            boundary = date(2024, 1, 3)
            self.assertNotEqual(future.source_sha256, self.table.source_sha256)
            self.assertEqual(future.through(boundary).sha256, self.table.through(boundary).sha256)
            self.assertEqual(future.through(boundary).splits, self.table.splits)

    def test_semantic_identity_ignores_csv_formatting_but_includes_methodology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, manifest_path = _write(root, CSV.replace("100.0", "100.0000"))
            formatted = load_distributions(path, manifest_path=manifest_path)
            self.assertEqual(formatted.sha256, self.table.sha256)
            self.assertNotEqual(formatted.source_sha256, self.table.source_sha256)
            revised = load_distributions(path, manifest_block={**MANIFEST, "methodology": "revised"})
            self.assertEqual(revised.csv_sha256, formatted.csv_sha256)
            self.assertNotEqual(revised.sha256, formatted.sha256)

    def test_coverage_passes_when_every_priced_session_has_a_row(self) -> None:
        self.table.require_coverage(self._market([date(2024, 1, 2), date(2024, 1, 3)]), ("A", "B"))

    def test_coverage_fails_on_a_priced_session_without_a_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "no distribution row for A on 2024-01-05"):
            self.table.require_coverage(self._market([date(2024, 1, 5)]), ("A", "B"))

    def test_coverage_ignores_symbols_not_asked_about(self) -> None:
        bars = [PriceBar(date(2024, 1, 2), "C", 1.0, 1.0)]
        data = MarketData(bars, {date(2024, 1, 2): 1.0}, source="test")
        self.table.require_coverage(data, ("A", "B"))


if __name__ == "__main__":
    unittest.main()
