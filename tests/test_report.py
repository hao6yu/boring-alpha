from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.backtest.engine import Backtester
from boring_alpha.config import load_config
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.domain import BacktestResult, SignalSnapshot
from boring_alpha.metrics.performance import calculate_metrics
import boring_alpha.report as report
from boring_alpha.report import write_report
from boring_alpha.signals.trend import CashAllocation, FixedAllocation, MultiAssetTrend


def _result_with_decisions(*decisions: SignalSnapshot) -> BacktestResult:
    return BacktestResult(
        name="P",
        initial_equity=1.0,
        equity_curve=(),
        fills=(),
        decisions=tuple(decisions),
    )


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
[evaluation]
period = "exploratory"
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
        self.assertEqual(manifest["artifact_schema"], 6)
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


class ArtifactIdentityTests(ReportTests):
    """The manifest must be a pure function of config, data, code, and period."""

    def test_environment_changes_do_not_trip_the_write_once_guard(self) -> None:
        self._write()
        real = report.git_provenance
        report.git_provenance = lambda root: {"git_commit": "0" * 40, "git_dirty": False}
        try:
            self._write()
        finally:
            report.git_provenance = real

    def test_each_invocation_appends_a_provenance_record(self) -> None:
        _, run_dir = self._write()
        self._write()
        lines = (run_dir / "provenance.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        record = json.loads(lines[0])
        self.assertIn("recorded_at", record)
        self.assertIn("python_version", record)
        self.assertIn("git_commit", record)

    def test_manifest_holds_no_environment_fields(self) -> None:
        _, run_dir = self._write()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        for field in ("git_commit", "git_dirty", "python_version", "unseal_reason"):
            self.assertNotIn(field, manifest)

    def test_different_period_bounds_change_the_run_identity(self) -> None:
        first, _ = self._write()
        bounded = self.config.__class__(
            **{
                **{f: getattr(self.config, f) for f in self.config.__slots__},
                "evaluation": self.config.evaluation.__class__(
                    "development", date(2021, 1, 1), date(2021, 12, 31),
                    self.config.evaluation.review_dir,
                ),
            }
        )
        second, _ = write_report(bounded, self.data, *self.results, *self.metrics)
        self.assertNotEqual(first, second)


class GitProvenanceScopeTests(unittest.TestCase):
    def test_reports_nulls_when_the_repository_does_not_contain_the_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provenance = report.git_provenance(Path(directory), code_path=Path("/usr/lib/python"))
        self.assertIsNone(provenance["git_commit"])


from boring_alpha.report import snapshot_record


class DecisionRecordTests(unittest.TestCase):
    """Files written before `hold` existed must be reproduced byte for byte."""

    def _snapshot(self, **overrides) -> SignalSnapshot:
        fields = dict(
            as_of=date(2024, 1, 31),
            target_weights={"A": 0.5},
            asset_returns={"A": 0.1},
            cash_return=0.01,
            name="P",
        )
        fields.update(overrides)
        return SignalSnapshot(**fields)

    def test_a_false_hold_is_omitted_from_the_record(self) -> None:
        record = snapshot_record(self._snapshot())
        self.assertNotIn("hold", record)
        self.assertEqual(
            record,
            {
                "as_of": date(2024, 1, 31),
                "target_weights": {"A": 0.5},
                "asset_returns": {"A": 0.1},
                "cash_return": 0.01,
                "name": "P",
            },
        )

    def test_a_true_hold_is_recorded(self) -> None:
        self.assertIs(snapshot_record(self._snapshot(hold=True))["hold"], True)

    def test_ba_001_decision_json_bytes_are_unchanged(self) -> None:
        self.assertEqual(
            report.json_text(snapshot_record(self._snapshot())),
            '{\n  "as_of": "2024-01-31",\n  "asset_returns": {\n    "A": 0.1\n  },\n'
            '  "cash_return": 0.01,\n  "name": "P",\n  "target_weights": {\n'
            '    "A": 0.5\n  }\n}\n',
        )

    def test_decisions_json_uses_the_record(self) -> None:
        result = _result_with_decisions(self._snapshot(), self._snapshot(hold=True))
        text = report.decisions_json(result)
        self.assertEqual(text.count('"hold"'), 1)
