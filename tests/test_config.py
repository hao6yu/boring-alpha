from pathlib import Path
import tempfile
import unittest

from boring_alpha.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID = """
[strategy]
id = "X"
name = "Valid"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 1000
[execution]
cost_bps = 0
[data]
source = "synthetic"
start = "2020-01-01"
end = "2022-01-01"
[backtest]
start = "2021-01-01"
end = "2022-01-01"
[evaluation]
period = "exploratory"
[report]
output_dir = "out"
"""


def _load(content: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "nested" / "config.toml"
        path.parent.mkdir()
        path.write_text(content, encoding="utf-8")
        return load_config(path), path


class ConfigTests(unittest.TestCase):
    def test_checked_in_config_is_valid_and_fixed_sleeves_sum_to_one(self) -> None:
        config = load_config(REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml")
        self.assertEqual(config.strategy.strategy_id, "BA-001")
        self.assertAlmostEqual(
            len(config.strategy.symbols) * config.strategy.sleeve_weight, 1.0
        )
        self.assertEqual(config.report.output_dir, REPO_ROOT / "experiments")

    def test_relative_paths_resolve_against_the_config_directory(self) -> None:
        config, path = _load(VALID)
        self.assertEqual(config.report.output_dir, path.resolve().parent / "out")

    def test_rejects_leveraged_sleeves(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceed 100%"):
            _load(VALID.replace("sleeve_weight = 0.5", "sleeve_weight = 0.6"))

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown.*lookback_month\\b"):
            _load(VALID.replace("lookback_months = 12", "lookback_month = 12"))

    def test_unknown_table_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown.*exectuion"):
            _load(VALID.replace("[execution]", "[exectuion]"))

    def test_keys_for_the_other_data_source_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "prices_path.*synthetic"):
            _load(VALID.replace('source = "synthetic"', 'source = "synthetic"\nprices_path = "x.csv"'))

    def test_datetime_values_are_rejected_for_date_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "backtest.start must be an ISO date"):
            _load(VALID.replace('start = "2021-01-01"', "start = 2021-01-01T00:00:00"))

    def test_missing_required_key_is_reported_as_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution.cost_bps.*required"):
            _load(VALID.replace("cost_bps = 0\n", ""))


if __name__ == "__main__":
    unittest.main()
