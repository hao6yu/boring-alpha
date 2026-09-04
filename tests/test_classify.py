"""A verdict must refuse inputs it cannot legitimately combine."""

import json
from pathlib import Path
import tempfile
import unittest

from boring_alpha.cli import run_classify

BASE = {
    "strategy": {"max_drawdown": -0.10, "sharpe_vs_cash": 0.50},
    "static": {"max_drawdown": -0.20, "sharpe_vs_cash": 0.55},
}
VARIANTS = {
    name: dict(BASE)
    for name in ("base", "double_cost", "lookback_9", "lookback_15", "drop_top_sleeve")
}


def _criteria(period: str, **overrides) -> dict:
    payload = {
        "artifact_schema": 5,
        "strategy_id": "X-001",
        "code_sha256": "a" * 64,
        "evaluation_period": period,
        "passed": True,
        "criteria": [],
        "variants": VARIANTS,
    }
    payload.update(overrides)
    return payload


class ClassifyGuardTests(unittest.TestCase):
    def _dirs(self, development: dict, validation: dict) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp())
        paths = []
        for name, payload in (("dev", development), ("val", validation)):
            directory = root / name
            directory.mkdir()
            (directory / "criteria.json").write_text(json.dumps(payload), encoding="utf-8")
            paths.append(directory)
        return paths[0], paths[1]

    def test_matched_sweeps_classify(self) -> None:
        development, validation = self._dirs(_criteria("development"), _criteria("validation"))
        self.assertEqual(run_classify(development, validation), 0)

    def test_a_period_mismatch_is_refused(self) -> None:
        development, validation = self._dirs(_criteria("validation"), _criteria("validation"))
        with self.assertRaisesRegex(ValueError, "expected development"):
            run_classify(development, validation)

    def test_a_different_strategy_is_refused(self) -> None:
        development, validation = self._dirs(
            _criteria("development"), _criteria("validation", strategy_id="Y-002")
        )
        with self.assertRaisesRegex(ValueError, "different strategies"):
            run_classify(development, validation)

    def test_a_different_code_revision_is_refused(self) -> None:
        development, validation = self._dirs(
            _criteria("development"), _criteria("validation", code_sha256="b" * 64)
        )
        with self.assertRaisesRegex(ValueError, "different code"):
            run_classify(development, validation)

    def test_a_malformed_file_reports_an_error_rather_than_crashing(self) -> None:
        development, validation = self._dirs(
            _criteria("development", variants={}), _criteria("validation")
        )
        with self.assertRaises(ValueError):
            run_classify(development, validation)


if __name__ == "__main__":
    unittest.main()
