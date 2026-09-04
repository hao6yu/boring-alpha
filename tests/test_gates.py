import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from boring_alpha.cli import SealedRunError, run_backtest
from boring_alpha.report import git_provenance

PERIODS = """
[T-001.validation]
start = 2018-01-01
end = 2021-12-31

[T-001.sealed]
start = 2022-01-01
end = 2023-12-31
"""

CONFIG = """
[strategy]
id = "T-001"
name = "Gate Test"
symbols = ["A", "B"]
lookback_months = 12
sleeve_weight = 0.5
[portfolio]
initial_cash = 10000
[execution]
cost_bps = 10
[data]
source = "synthetic"
start = "2016-01-01"
end = "2025-12-31"
seed = 11
annual_cash_rate = 0.01
[backtest]
start = "2022-01-01"
end = "2023-12-31"
[evaluation]
period = "sealed"
[report]
output_dir = "../experiments"
"""


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "configs").mkdir()
        (self.root / "configs" / "evaluation_periods.toml").write_text(PERIODS, encoding="utf-8")
        self.config_path = self.root / "configs" / "run.toml"
        self.config_path.write_text(CONFIG, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, **kwargs) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_backtest(self.config_path, **kwargs)
        return output.getvalue()

    def _manifest(self) -> dict:
        runs = list((self.root / "experiments" / "T-001").iterdir())
        self.assertEqual(len(runs), 1)
        return json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))

    def test_sealed_run_without_unseal_is_refused(self) -> None:
        with self.assertRaises(SealedRunError):
            self._run()
        self.assertFalse((self.root / "experiments").exists())

    def test_sealed_run_records_the_unseal_reason_and_warns(self) -> None:
        output = self._run(unseal_reason="development and validation review complete")
        manifest = self._manifest()
        self.assertEqual(manifest["unseal_reason"], "development and validation review complete")
        self.assertEqual(manifest["evaluation_period"], "sealed")
        self.assertIn("change log", output)

    def test_validation_run_without_a_development_review_is_refused(self) -> None:
        self.config_path.write_text(
            CONFIG.replace('period = "sealed"', 'period = "validation"')
            .replace('start = "2022-01-01"\nend = "2023-12-31"', 'start = "2018-01-01"\nend = "2021-12-31"'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "development review"):
            self._run()

    def test_validation_run_proceeds_once_a_review_exists(self) -> None:
        (self.root / "docs" / "reviews").mkdir(parents=True)
        (self.root / "docs" / "reviews" / "T-001-development.md").write_text("reviewed", encoding="utf-8")
        self.config_path.write_text(
            CONFIG.replace('period = "sealed"', 'period = "validation"')
            .replace('start = "2022-01-01"\nend = "2023-12-31"', 'start = "2018-01-01"\nend = "2021-12-31"'),
            encoding="utf-8",
        )
        self._run()
        self.assertEqual(self._manifest()["evaluation_period"], "validation")

    def test_data_after_the_period_end_is_never_loaded(self) -> None:
        self._run(unseal_reason="review complete")
        manifest = self._manifest()
        self.assertEqual(manifest["data_end"], "2023-12-29")
        self.assertEqual(manifest["evaluation_end"], "2023-12-31")

    def test_manifest_records_code_provenance(self) -> None:
        self._run(unseal_reason="review complete")
        manifest = self._manifest()
        self.assertEqual(manifest["artifact_schema"], 3)
        self.assertIn("python_version", manifest)
        self.assertIn("git_commit", manifest)
        self.assertIn("git_dirty", manifest)


class GitProvenanceTests(unittest.TestCase):
    def test_reports_commit_and_dirty_state_of_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e", "PATH": "/usr/bin:/bin"}
            run = lambda *args: subprocess.run(("git", "-C", str(root)) + args, check=True, capture_output=True, env=env)
            run("init", "-q")
            (root / "a.txt").write_text("one", encoding="utf-8")
            run("add", "a.txt")
            run("commit", "-qm", "first")
            clean = git_provenance(root)
            self.assertRegex(clean["git_commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(clean["git_dirty"])
            (root / "a.txt").write_text("two", encoding="utf-8")
            self.assertTrue(git_provenance(root)["git_dirty"])

    def test_reports_nulls_outside_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provenance = git_provenance(Path(directory))
        self.assertIsNone(provenance["git_commit"])
        self.assertIsNone(provenance["git_dirty"])


if __name__ == "__main__":
    unittest.main()
