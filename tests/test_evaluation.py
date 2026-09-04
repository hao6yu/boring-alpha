from datetime import date, timedelta
from pathlib import Path
import tempfile
import tomllib
import unittest

from boring_alpha.config import load_config

PERIODS = """
[BA-001.development]
start = 2007-01-01
end = 2017-12-31

[BA-001.validation]
start = 2018-01-01
end = 2021-12-31

[BA-001.sealed]
start = 2022-01-01
end = 2025-12-31
"""

CONFIG = """
[strategy]
id = "BA-001"
name = "Multi-Asset Trend"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 1000
[execution]
cost_bps = 10
[data]
source = "synthetic"
start = "2006-01-01"
end = "2030-12-31"
[backtest]
start = "2007-01-01"
end = "2017-12-31"
[evaluation]
period = "development"
[report]
output_dir = "../experiments"
"""


def _load(config: str = CONFIG, periods: str | None = PERIODS):
    directory = tempfile.mkdtemp()
    configs = Path(directory) / "configs"
    configs.mkdir()
    if periods is not None:
        (configs / "evaluation_periods.toml").write_text(periods, encoding="utf-8")
    path = configs / "run.toml"
    path.write_text(config, encoding="utf-8")
    return load_config(path)


class EvaluationPeriodTests(unittest.TestCase):
    def test_period_bounds_are_resolved_from_the_registry(self) -> None:
        config = _load()
        self.assertEqual(config.evaluation.period, "development")
        self.assertEqual(config.evaluation.start, date(2007, 1, 1))
        self.assertEqual(config.evaluation.end, date(2017, 12, 31))

    def test_exploratory_period_is_unbounded(self) -> None:
        config = _load(CONFIG.replace('period = "development"', 'period = "exploratory"'), periods=None)
        self.assertIsNone(config.evaluation.end)

    def test_backtest_window_outside_the_period_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the development period"):
            _load(CONFIG.replace('end = "2017-12-31"\n[evaluation]', 'end = "2018-06-30"\n[evaluation]'))

    def test_unknown_period_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "evaluation.period must be one of"):
            _load(CONFIG.replace('period = "development"', 'period = "dev"'))

    def test_period_missing_from_the_registry_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no development period for BA-001"):
            _load(periods="[BA-002.development]\nstart = 2007-01-01\nend = 2017-12-31\n")

    def test_missing_registry_file_is_reported(self) -> None:
        with self.assertRaisesRegex(ValueError, "evaluation_periods.toml"):
            _load(periods=None)

    def test_evaluation_table_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "evaluation.period is required"):
            _load(CONFIG.replace('[evaluation]\nperiod = "development"\n', ""))


if __name__ == "__main__":
    unittest.main()


class CheckedInRegistryTests(unittest.TestCase):
    """The registry and the example configuration must agree with the charter."""

    REPO_ROOT = Path(__file__).resolve().parent.parent

    def test_example_csv_config_covers_exactly_the_development_period(self) -> None:
        config = load_config(self.REPO_ROOT / "configs" / "ba_001_real_csv.example.toml")
        self.assertEqual(config.evaluation.period, "development")
        self.assertEqual(config.backtest.start, config.evaluation.start)
        self.assertEqual(config.backtest.end, config.evaluation.end)

    def test_registry_periods_are_contiguous_and_ordered(self) -> None:
        registry = self.REPO_ROOT / "configs" / "evaluation_periods.toml"
        bounds = tomllib.loads(registry.read_text(encoding="utf-8"))["BA-001"]
        development, validation, sealed = (
            bounds["development"], bounds["validation"], bounds["sealed"]
        )
        self.assertEqual(development["end"], validation["start"] - timedelta(days=1))
        self.assertEqual(validation["end"], sealed["start"] - timedelta(days=1))
