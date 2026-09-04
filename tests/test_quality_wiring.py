"""Quality findings must reach the operator: errors halt, warnings are recorded."""

import contextlib
from datetime import date, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.cli import run_backtest

CONFIG = """
[strategy]
id = "Q-001"
name = "Quality Wiring"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 10000
[execution]
cost_bps = 10
[data]
source = "csv"
methodology = "test-v1"
prices_path = "../data/prices.csv"
cash_path = "../data/cash.csv"
[backtest]
start = "2021-01-01"
end = "2021-12-31"
[evaluation]
period = "exploratory"
[report]
output_dir = "../experiments"
"""


def _sessions() -> list[date]:
    days, day = [], date(2019, 1, 1)
    while day <= date(2021, 12, 31):
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class QualityWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "configs").mkdir()
        (self.root / "data").mkdir()
        self.config_path = self.root / "configs" / "run.toml"
        self.config_path.write_text(CONFIG, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_prices(self, crash_on: date | None = None) -> None:
        rows = ["date,symbol,tr_open,tr_close"]
        cash = ["date,cash_factor"]
        for day in _sessions():
            cash.append(f"{day},1.00002")
            for symbol in ("A", "B"):
                price = 40.0 if (crash_on and symbol == "A" and day >= crash_on) else 100.0
                rows.append(f"{day},{symbol},{price:.4f},{price:.4f}")
        (self.root / "data" / "prices.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        (self.root / "data" / "cash.csv").write_text("\n".join(cash) + "\n", encoding="utf-8")

    def _run(self) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_backtest(self.config_path)
        return output.getvalue()

    def _manifest(self) -> dict:
        run = next((self.root / "experiments" / "Q-001").iterdir())
        return json.loads((run / "manifest.json").read_text(encoding="utf-8"))

    def test_implausible_move_halts_the_run_before_any_artifact_is_written(self) -> None:
        self._write_prices(crash_on=date(2021, 6, 1))
        with self.assertRaisesRegex(ValueError, "session_return"):
            self._run()
        self.assertFalse((self.root / "experiments").exists())

    def test_stale_prices_are_recorded_as_a_manifest_warning(self) -> None:
        self._write_prices()
        self._run()
        self.assertTrue(
            any("stale" in warning for warning in self._manifest()["warnings"]),
            self._manifest()["warnings"],
        )

    def test_warnings_reach_the_console(self) -> None:
        self._write_prices()
        self.assertIn("data quality", self._run())

    def test_thresholds_can_be_relaxed_in_the_configuration(self) -> None:
        self._write_prices(crash_on=date(2021, 6, 1))
        self.config_path.write_text(
            CONFIG + '\n[quality]\nmax_session_return = 0.8\nmax_open_gap = 0.8\n',
            encoding="utf-8",
        )
        self._run()
        self.assertTrue(self._manifest()["run_id"])


if __name__ == "__main__":
    unittest.main()
