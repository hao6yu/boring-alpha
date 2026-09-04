"""A verdict must refuse inputs it cannot legitimately combine."""

import contextlib
import io
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
        "strategy_id": "BA-001",
        "strategy_spec_sha256": "e" * 64,
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
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_classify(development, validation), 0)

    def test_a_period_mismatch_is_refused(self) -> None:
        development, validation = self._dirs(_criteria("validation"), _criteria("validation"))
        with self.assertRaisesRegex(ValueError, "expected development"):
            with contextlib.redirect_stdout(io.StringIO()):
                run_classify(development, validation)

    def test_a_different_strategy_is_refused(self) -> None:
        development, validation = self._dirs(
            _criteria("development"), _criteria("validation", strategy_id="Y-002")
        )
        with self.assertRaisesRegex(ValueError, "different strategies"):
            with contextlib.redirect_stdout(io.StringIO()):
                run_classify(development, validation)

    def test_a_different_code_revision_is_refused(self) -> None:
        development, validation = self._dirs(
            _criteria("development"), _criteria("validation", code_sha256="b" * 64)
        )
        with self.assertRaisesRegex(ValueError, "different code"):
            with contextlib.redirect_stdout(io.StringIO()):
                run_classify(development, validation)

    def test_a_malformed_file_reports_an_error_rather_than_crashing(self) -> None:
        development, validation = self._dirs(
            _criteria("development", variants={}), _criteria("validation")
        )
        with self.assertRaises(ValueError):
            with contextlib.redirect_stdout(io.StringIO()):
                run_classify(development, validation)


if __name__ == "__main__":
    unittest.main()


class VerdictInputGuardTests(unittest.TestCase):
    """Absence proves nothing, so a missing identity field is refused too."""

    _dirs = ClassifyGuardTests._dirs

    def test_a_missing_strategy_spec_hash_is_refused(self) -> None:
        development = _criteria("development")
        del development["strategy_spec_sha256"]
        dev_dir, val_dir = self._dirs(development, _criteria("validation"))
        with self.assertRaisesRegex(ValueError, "records no strategy_spec_sha256"):
            run_classify(dev_dir, val_dir)

    def test_a_different_strategy_definition_is_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development"), _criteria("validation", strategy_spec_sha256="f" * 64)
        )
        with self.assertRaisesRegex(ValueError, "different strategy definitions"):
            run_classify(dev_dir, val_dir)

    def test_a_stale_artifact_schema_is_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", artifact_schema=4), _criteria("validation", artifact_schema=4)
        )
        with self.assertRaisesRegex(ValueError, "artifact schema 4"):
            run_classify(dev_dir, val_dir)

    def test_a_missing_artifact_schema_is_refused(self) -> None:
        development = _criteria("development")
        del development["artifact_schema"]
        dev_dir, val_dir = self._dirs(development, _criteria("validation"))
        with self.assertRaisesRegex(ValueError, "records no artifact_schema"):
            run_classify(dev_dir, val_dir)


class TaxPolicyAgreementTests(unittest.TestCase):
    """Two sweeps scored under different tax policies cannot share a verdict."""

    _dirs = ClassifyGuardTests._dirs

    def test_identical_tax_policies_classify(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256="c" * 64),
            _criteria("validation", tax_policy_sha256="c" * 64),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_classify(dev_dir, val_dir), 0)

    def test_different_tax_policies_are_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256="c" * 64),
            _criteria("validation", tax_policy_sha256="d" * 64),
        )
        with self.assertRaisesRegex(ValueError, "different tax policies"):
            run_classify(dev_dir, val_dir)

    def test_a_policy_on_one_side_only_is_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256="c" * 64), _criteria("validation")
        )
        with self.assertRaisesRegex(ValueError, "different tax policies"):
            run_classify(dev_dir, val_dir)

    def test_an_empty_string_policy_on_one_side_only_is_refused(self) -> None:
        # An empty string and an absent field are both falsy, but they are not
        # the same value: `any(...)` over the pair would miss this, since it
        # only asks whether either side is truthy.
        dev_dir, val_dir = self._dirs(
            _criteria("development", tax_policy_sha256=""), _criteria("validation")
        )
        with self.assertRaisesRegex(ValueError, "different tax policies"):
            run_classify(dev_dir, val_dir)


class ProfileLookupTests(unittest.TestCase):
    _dirs = ClassifyGuardTests._dirs

    def test_an_unregistered_strategy_is_refused(self) -> None:
        dev_dir, val_dir = self._dirs(
            _criteria("development", strategy_id="X-001"),
            _criteria("validation", strategy_id="X-001"),
        )
        with self.assertRaisesRegex(ValueError, "no evaluation profile.*X-001"):
            run_classify(dev_dir, val_dir)

    def test_the_verdict_names_the_strategy(self) -> None:
        dev_dir, val_dir = self._dirs(_criteria("development"), _criteria("validation"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run_classify(dev_dir, val_dir)
        self.assertIn("BA-001 classification:", out.getvalue())


class SchemaCompatibilityTests(unittest.TestCase):
    _dirs = ClassifyGuardTests._dirs

    def test_every_readable_schema_classifies(self) -> None:
        from boring_alpha.report import READABLE_SCHEMAS

        for schema in READABLE_SCHEMAS:
            dev_dir, val_dir = self._dirs(
                _criteria("development", artifact_schema=schema),
                _criteria("validation", artifact_schema=schema),
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_classify(dev_dir, val_dir), 0)
