from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.config import load_config
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.metrics.performance import calculate_metrics
from boring_alpha.report import write_report
from boring_alpha.signals.trend import CashAllocation, FixedAllocation, MultiAssetTrend

CONFIG = """
[strategy]
id = "T-001"
name = "Report Test"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 10000
[execution]
cost_bps = 10
[data]
source = "synthetic"
start = "2020-01-01"
end = "2021-12-31"
seed = 5
annual_cash_rate = 0.01
[backtest]
start = "2021-01-01"
end = "2021-12-31"
[report]
output_dir = "../experiments"
"""


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "configs").mkdir()
        (root / "configs" / "run.toml").write_text(CONFIG, encoding="utf-8")
        self.config = load_config(root / "configs" / "run.toml")
        self.data = generate_synthetic_market_data(
            self.config.strategy.symbols,
            date(2020, 1, 1),
            date(2021, 12, 31),
            seed=5,
            annual_cash_rate=0.01,
        )
        engine = Backtester(
            self.data,
            self.config.strategy.symbols,
            initial_cash=10_000.0,
            cost_bps=10.0,
            start=date(2021, 1, 1),
            end=date(2021, 12, 31),
        )
        symbols = self.config.strategy.symbols
        self.results = (
            engine.run(MultiAssetTrend(symbols, 12, 0.5)),
            engine.run(FixedAllocation(symbols, 12, 0.5)),
            engine.run(CashAllocation(symbols)),
        )
        self.metrics = tuple(calculate_metrics(r, self.data) for r in self.results)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self):
        return write_report(self.config, self.data, *self.results, *self.metrics)

    def test_manifest_records_schema_version_and_engine_warnings(self) -> None:
        run_id, run_dir = self._write()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_schema"], 2)
        self.assertTrue(any("no signal at month-end 2020-12-31" in w for w in manifest["warnings"]))
        self.assertEqual(run_dir, self.config.report.output_dir / "T-001" / run_id)

    def test_same_config_content_from_another_directory_reuses_the_run(self) -> None:
        first_id, first_dir = self._write()
        # Identical bytes in a sibling directory; "../experiments" resolves to the same place.
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        (other / "renamed.toml").write_text(CONFIG, encoding="utf-8")
        config = load_config(other / "renamed.toml")
        second_id, second_dir = write_report(config, self.data, *self.results, *self.metrics)
        self.assertEqual(first_id, second_id)
        self.assertEqual(first_dir, second_dir)

    def test_rerun_with_identical_inputs_is_a_no_op(self) -> None:
        first_id, _ = self._write()
        second_id, _ = self._write()
        self.assertEqual(first_id, second_id)

    def test_write_once_refuses_a_changed_artifact(self) -> None:
        _, run_dir = self._write()
        (run_dir / "metrics.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
            self._write()


if __name__ == "__main__":
    unittest.main()
