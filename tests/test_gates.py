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

    def _write_reviews(self, *names: str) -> None:
        reviews = self.root / "docs" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        for name in names:
            (reviews / name).write_text("reviewed", encoding="utf-8")

    def _provenance(self) -> list[dict]:
        runs = list((self.root / "experiments" / "T-001").iterdir())
        lines = (runs[0] / "provenance.jsonl").read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines]

    def _manifest(self) -> dict:
        runs = list((self.root / "experiments" / "T-001").iterdir())
        self.assertEqual(len(runs), 1)
        return json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))

    def test_sealed_run_without_unseal_is_refused(self) -> None:
        with self.assertRaises(SealedRunError):
            self._run()
        self.assertFalse((self.root / "experiments").exists())

    def test_sealed_run_records_the_unseal_reason_and_warns(self) -> None:
        self._write_reviews("T-001-development.md", "T-001-validation.md")
        output = self._run(unseal_reason="development and validation review complete")
        self.assertEqual(self._manifest()["evaluation_period"], "sealed")
        self.assertEqual(
            self._provenance()[0]["unseal_reason"],
            "development and validation review complete",
        )
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
        self._write_reviews("T-001-development.md", "T-001-validation.md")
        self._run(unseal_reason="review complete")
        manifest = self._manifest()
        self.assertEqual(manifest["data_end"], "2023-12-29")
        self.assertEqual(manifest["evaluation_end"], "2023-12-31")

    def test_invocation_provenance_is_recorded_beside_the_manifest(self) -> None:
        self._write_reviews("T-001-development.md", "T-001-validation.md")
        self._run(unseal_reason="review complete")
        self.assertEqual(self._manifest()["artifact_schema"], 4)
        record = self._provenance()[0]
        for field in ("python_version", "git_commit", "git_dirty", "recorded_at"):
            self.assertIn(field, record)


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
            code = root / "a.txt"
            clean = git_provenance(root, code_path=code)
            self.assertRegex(clean["git_commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(clean["git_dirty"])
            (root / "a.txt").write_text("two", encoding="utf-8")
            self.assertTrue(git_provenance(root, code_path=code)["git_dirty"])

    def test_reports_nulls_outside_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provenance = git_provenance(Path(directory))
        self.assertIsNone(provenance["git_commit"])
        self.assertIsNone(provenance["git_dirty"])


if __name__ == "__main__":
    unittest.main()


class SealedReviewGateTests(GateTests):
    def test_sealed_run_requires_both_written_reviews(self) -> None:
        self._write_reviews("T-001-development.md")
        with self.assertRaisesRegex(ValueError, "validation review"):
            self._run(unseal_reason="ready")

    def test_sealed_run_proceeds_once_both_reviews_exist(self) -> None:
        self._write_reviews("T-001-development.md", "T-001-validation.md")
        self._run(unseal_reason="ready")
        self.assertEqual(self._manifest()["evaluation_period"], "sealed")

    def test_empty_unseal_on_a_non_sealed_period_is_rejected(self) -> None:
        self.config_path.write_text(
            CONFIG.replace('period = "sealed"', 'period = "exploratory"'), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "only to the sealed period"):
            self._run(unseal_reason="")

    def test_validation_gate_survives_a_missing_review_directory(self) -> None:
        self.config_path.write_text(
            CONFIG.replace('period = "sealed"', 'period = "validation"')
            .replace('start = "2022-01-01"\nend = "2023-12-31"', 'start = "2018-01-01"\nend = "2021-12-31"'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "development review"):
            self._run()

    def test_backtest_starting_before_the_period_is_rejected(self) -> None:
        self.config_path.write_text(
            CONFIG.replace('start = "2022-01-01"\nend = "2023-12-31"', 'start = "2021-01-01"\nend = "2023-12-31"'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "outside the sealed period"):
            self._run(unseal_reason="ready")

    def test_exploratory_run_is_announced_on_the_console(self) -> None:
        self.config_path.write_text(
            CONFIG.replace('period = "sealed"', 'period = "exploratory"'), encoding="utf-8"
        )
        output = self._run()
        self.assertGreaterEqual(output.count("EXPLORATORY RUN"), 2)
        self.assertIn("NOT EVIDENCE ABOUT T-001", output)
