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


class ClusterValidationTests(unittest.TestCase):
    def _with_clusters(self, table: str):
        return _load(VALID + table)

    def test_a_bare_string_is_rejected_rather_than_split_into_letters(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a list of symbols"):
            self._with_clusters('\n[clusters]\ngrowth = "A"\n')

    def test_overlapping_clusters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            self._with_clusters('\n[clusters]\none = ["A"]\ntwo = ["A", "B"]\n')

    def test_a_symbol_outside_the_universe_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the universe"):
            self._with_clusters('\n[clusters]\none = ["Z"]\n')

    def test_valid_clusters_are_normalised(self) -> None:
        config, _ = self._with_clusters('\n[clusters]\none = ["a"]\ntwo = ["b"]\n')
        self.assertEqual(config.clusters, {"one": ("A",), "two": ("B",)})


BENCHMARK = VALID + """
[benchmark]
exposure = 0.6
rebalance = "annual"
"""

BA001_SPEC_HASH = "595a25e57ed68d4e863eeb69b40248345840b809b0f213609ddd14b4cd952110"


class BenchmarkConfigTests(unittest.TestCase):
    def test_an_absent_table_means_no_override(self) -> None:
        config, _ = _load(VALID)
        self.assertIsNone(config.benchmark)

    def test_the_table_is_parsed(self) -> None:
        config, _ = _load(BENCHMARK)
        assert config.benchmark is not None
        self.assertAlmostEqual(config.benchmark.exposure, 0.6)
        self.assertEqual(config.benchmark.rebalance, "annual")

    def test_the_table_enters_the_spec_hash_only_when_present(self) -> None:
        without, _ = _load(VALID)
        annual, _ = _load(BENCHMARK)
        monthly, _ = _load(BENCHMARK.replace('"annual"', '"monthly"'))
        half, _ = _load(BENCHMARK.replace("0.6", "0.5"))
        hashes = {without.strategy_spec_sha256, annual.strategy_spec_sha256,
                  monthly.strategy_spec_sha256, half.strategy_spec_sha256}
        self.assertEqual(len(hashes), 4)

    def test_ba_001_development_spec_hash_is_unchanged(self) -> None:
        # The value recorded in both real BA-001 sweeps. Adding an optional table
        # must not move it, or the archived record would no longer describe the
        # checked-in configuration.
        config = load_config(REPO_ROOT / "configs" / "ba_001_development.toml")
        self.assertEqual(config.strategy_spec_sha256, BA001_SPEC_HASH)

    def test_exposure_outside_the_unit_interval_is_refused(self) -> None:
        for bad in ("0.0", "1.5", "-0.2"):
            with self.assertRaisesRegex(ValueError, "benchmark.exposure"):
                _load(BENCHMARK.replace("0.6", bad))

    def test_an_unknown_schedule_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark.rebalance"):
            _load(BENCHMARK.replace('"annual"', '"weekly"'))

    def test_an_incomplete_table_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark.rebalance is required"):
            _load(VALID + "\n[benchmark]\nexposure = 0.6\n")
        with self.assertRaisesRegex(ValueError, "benchmark.exposure is required"):
            _load(VALID + '\n[benchmark]\nrebalance = "annual"\n')

    def test_an_unknown_key_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown key"):
            _load(BENCHMARK + "band = 0.02\n")
