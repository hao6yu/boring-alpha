import contextlib
import csv
from datetime import date
import io
from pathlib import Path
import tempfile
import unittest

from boring_alpha.cli import run_backtest

REPO_ROOT = Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def test_checked_in_synthetic_config_runs_end_to_end(self) -> None:
        source = (REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            config_path = root / "configs" / "demo.toml"
            config_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = run_backtest(config_path)
            self.assertEqual(status, 0)
            runs = list((root / "experiments" / "BA-001").iterdir())
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0] / "manifest.json").exists())
            self.assertIn("SYNTHETIC DATA", output.getvalue())

    def test_run_backtest_honours_the_configured_benchmark(self) -> None:
        # `load_config` folds a `[benchmark]` table into strategy_spec_sha256,
        # so `run_backtest` must actually use it. With the table present the
        # gating benchmark is an annual target-exposure allocation, which
        # enters on the first session of 2018 and rebalances only every
        # following January; a fixed monthly benchmark would trade every
        # month instead.
        source = (REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            output_dir = root / "run-output"
            output_dir.mkdir()
            source = source.replace('output_dir = "../experiments"', f'output_dir = "{output_dir}"')
            source += '\n[benchmark]\nexposure = 0.6\nrebalance = "annual"\n'
            config_path = root / "configs" / "demo.toml"
            config_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = run_backtest(config_path)
            self.assertEqual(status, 0)
            runs = list((output_dir / "BA-001").iterdir())
            self.assertEqual(len(runs), 1)
            trades_text = (runs[0] / "benchmark_trades.csv").read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(trades_text)))
            fill_dates = [date.fromisoformat(row["date"]) for row in rows]
            self.assertTrue(fill_dates, "expected at least one benchmark fill")
            self.assertTrue(
                all(fill_date.month == 1 for fill_date in fill_dates),
                f"expected every fill in January, got months {sorted({d.month for d in fill_dates})}",
            )
            self.assertGreater(
                len({fill_date.year for fill_date in fill_dates}),
                1,
                "expected fills across more than one year",
            )

    def test_engine_warnings_are_printed(self) -> None:
        source = (REPO_ROOT / "configs" / "ba_001_multi_asset_trend.toml").read_text(encoding="utf-8")
        # Shorten the warm-up so the decisive pre-start month-end has no history.
        source = source.replace('start = "2016-12-01"', 'start = "2017-06-01"')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            config_path = root / "configs" / "demo.toml"
            config_path.write_text(source, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run_backtest(config_path)
        self.assertIn("no signal at month-end 2017-12-29", output.getvalue())


if __name__ == "__main__":
    unittest.main()
