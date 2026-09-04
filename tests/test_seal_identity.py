"""The seal's headline claim: appending later data must not change a sealed run."""

import contextlib
from datetime import date, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.cli import run_backtest

PERIODS = """
[S-001.development]
start = 2020-01-01
end = 2021-12-31
"""

CONFIG = """
[strategy]
id = "S-001"
name = "Seal Identity"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 10000
[execution]
cost_bps = 10
[data]
source = "csv"
prices_path = "../data/prices.csv"
cash_path = "../data/cash.csv"
[backtest]
start = "2020-01-01"
end = "2021-12-31"
[evaluation]
period = "development"
[report]
output_dir = "../experiments"
"""


def _sessions(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _write_csvs(directory: Path, end: date) -> None:
    """A deterministic zigzag: reproducible, and extending it never rewrites history."""

    prices = ["date,symbol,tr_open,tr_close"]
    cash = ["date,cash_factor"]
    for index, day in enumerate(_sessions(date(2019, 1, 1), end)):
        cash.append(f"{day},1.00004")
        for offset, symbol in enumerate(("A", "B")):
            close = 100.0 + index * 0.02 + offset * 5.0 + (index % 7) * 0.3
            prices.append(f"{day},{symbol},{close - 0.05:.4f},{close:.4f}")
    (directory / "prices.csv").write_text("\n".join(prices) + "\n", encoding="utf-8")
    (directory / "cash.csv").write_text("\n".join(cash) + "\n", encoding="utf-8")


class SealIdentityTests(unittest.TestCase):
    def test_appending_later_data_leaves_a_development_run_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "data").mkdir()
            (root / "configs" / "evaluation_periods.toml").write_text(PERIODS, encoding="utf-8")
            config_path = root / "configs" / "run.toml"
            config_path.write_text(CONFIG, encoding="utf-8")

            _write_csvs(root / "data", date(2021, 12, 31))
            with contextlib.redirect_stdout(io.StringIO()):
                run_backtest(config_path)
            runs = list((root / "experiments" / "S-001").iterdir())
            self.assertEqual(len(runs), 1)
            first = json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))

            # Three more years arrive. The config bytes do not change.
            _write_csvs(root / "data", date(2024, 12, 31))
            with contextlib.redirect_stdout(io.StringIO()):
                run_backtest(config_path)

            runs = list((root / "experiments" / "S-001").iterdir())
            self.assertEqual(len(runs), 1, "appended data created a second run directory")
            second = json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first, second)
            self.assertEqual(first["data_end"], "2021-12-31")
            self.assertEqual(
                len((runs[0] / "provenance.jsonl").read_text(encoding="utf-8").strip().splitlines()),
                2,
            )


if __name__ == "__main__":
    unittest.main()
