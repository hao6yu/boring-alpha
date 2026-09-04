import contextlib
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
