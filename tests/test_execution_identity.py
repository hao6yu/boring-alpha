"""Disk-identity drift checks use fictional inputs and no approval records."""

from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from boring_alpha.config import load_config
from boring_alpha.data.loader import load_market_data
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_access import ResearchContext, RunContext, open_run, prepare_run


class ExecutionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.code = patch("boring_alpha.report.code_fingerprint", return_value="a" * 64).start()
        self.evaluator = patch("boring_alpha.research_access.evaluator_fingerprint", return_value="b" * 64).start()
        self.addCleanup(patch.stopall)

    def test_verification_detects_code_or_evaluator_drift_without_resetting_baseline(self):
        for field in ("code", "evaluator"):
            with self.subTest(field=field):
                self.code.return_value, self.evaluator.return_value = "a" * 64, "b" * 64
                context = RunContext(None, ("a" * 64, "b" * 64))
                self.assertEqual(context.verify(), ("a" * 64, "b" * 64))
                before = context.execution_identity
                getattr(self, field).return_value = "c" * 64
                with self.assertRaisesRegex(ValueError, "changed during execution"):
                    context.verify()
                self.assertEqual(context.execution_identity, before)

    def test_missing_baseline_is_not_silently_initialized_by_verify(self):
        with self.assertRaises(TypeError):
            RunContext(None)
        with self.assertRaisesRegex(ValueError, "changed during execution"):
            RunContext(None, None).verify()

    def test_frozen_code_evaluator_and_inputs_must_match_before_journal_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            base = load_config(prepare_ba002_demo(Path(directory))["development"])
            config = replace(base, data=replace(base.data, source="csv"))
            for field in ("code_sha256", "evaluator_sha256", "input_manifest_sha256"):
                identity = {"code_sha256": "a" * 64, "evaluator_sha256": "b" * 64, "input_manifest_sha256": "0" * 64}
                identity[field] = "c" * 64
                selected = ResearchContext({}, Mock(), {"identity": identity})
                with self.subTest(field=field), patch("boring_alpha.research_access.research_context", return_value=selected), patch(
                    "boring_alpha.research_access.capture_inputs", return_value=SimpleNamespace(sha256="0" * 64, sources={})
                ), patch("boring_alpha.research_state.RunJournal") as journal:
                    with self.assertRaisesRegex(ValueError, "differs from the confirmed freeze"):
                        prepare_run(config)
                    journal.assert_not_called()

    def test_legacy_attempt_evaluator_identity_remains_its_complete_code_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            base = load_config(prepare_ba002_demo(Path(directory))["development"])
            config = replace(base, strategy=replace(base.strategy, strategy_id="BA-001"),
                data=replace(base.data, source="csv"),
                backtest=replace(base.backtest, start=date(2030, 1, 1), end=date(2030, 12, 31)),
                evaluation=replace(base.evaluation, period="exploratory", start=None, end=None))
            selected = ResearchContext({}, Mock(sha256="f" * 64), {"identity": {
                "code_sha256": "a" * 64, "evaluator_sha256": "a" * 64, "input_manifest_sha256": "0" * 64}})
            with patch("boring_alpha.research_access.legacy_research_context", return_value=selected), patch(
                "boring_alpha.research_access.capture_inputs", return_value=SimpleNamespace(sha256="0" * 64, sources={})
            ), patch("boring_alpha.research_state.RunJournal") as journal:
                context = prepare_run(config)
            self.assertEqual(context.verify(), ("a" * 64, "b" * 64))
            self.assertEqual(journal.return_value.begin.call_args.args[0].evaluator_sha256, "a" * 64)

    def test_loader_refuses_changes_during_input_loading_before_returning_data(self):
        from boring_alpha.data.synthetic import generate_synthetic_market_data

        def generate(*args, **kwargs):
            self.code.return_value = "c" * 64
            return generate_synthetic_market_data(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            paths = prepare_ba002_demo(Path(directory))
            config = load_config(paths["development"])
            with patch("boring_alpha.data.loader.generate_synthetic_market_data", side_effect=generate):
                with self.assertRaisesRegex(ValueError, "changed during execution"):
                    load_market_data(config)

    def test_known_drift_before_access_does_not_start_or_parse_an_attempt(self):
        attempt = Mock()
        def changed_before_access(*args):
            self.code.return_value = "c" * 64
            return RunContext(None, ("a" * 64, "b" * 64), attempt=attempt)

        with tempfile.TemporaryDirectory() as directory:
            config = load_config(prepare_ba002_demo(Path(directory))["development"])
            with patch("boring_alpha.research_access.prepare_run", side_effect=changed_before_access), patch(
                "boring_alpha.data.loader._load_market_data"
            ) as reader:
                with self.assertRaisesRegex(ValueError, "changed during execution"):
                    with open_run(config):
                        self.fail("known drift yielded data")
            attempt.start_access.assert_not_called()
            reader.assert_not_called()
            attempt.fail.assert_called_once()

    def test_drift_while_starting_access_is_caught_before_numeric_loading(self):
        attempt = Mock()
        attempt.start_access.side_effect = lambda: setattr(self.code, "return_value", "c" * 64)
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(prepare_ba002_demo(Path(directory))["development"])
            context = RunContext(None, ("a" * 64, "b" * 64), attempt=attempt)
            with patch("boring_alpha.research_access.prepare_run", return_value=context), patch(
                "boring_alpha.data.loader._load_market_data"
            ) as reader:
                with self.assertRaisesRegex(ValueError, "changed during execution"):
                    with open_run(config):
                        self.fail("access drift yielded data")
            attempt.start_access.assert_called_once()
            reader.assert_not_called()
            attempt.fail.assert_called_once()

    def test_early_engine_drift_is_refused_before_tax_scoring(self):
        from boring_alpha.backtest import Backtester
        from boring_alpha.sweep import run_sweep

        original = Backtester.run
        def drift(engine, signal):
            result = original(engine, signal)
            self.code.return_value = "c" * 64
            return result

        with tempfile.TemporaryDirectory() as directory:
            paths = prepare_ba002_demo(Path(directory))
            config = load_config(paths["development"])
            with open_run(config) as run:
                with patch.object(Backtester, "run", drift), patch("boring_alpha.sweep.run_scenarios") as tax:
                    with self.assertRaisesRegex(ValueError, "changed during execution"):
                        run_sweep(config, run.data, run_context=run.context)
                    tax.assert_not_called()

    def test_sweep_publication_rechecks_the_baseline_before_writing_anything(self):
        from boring_alpha.ba002_artifacts import write_ba002_sweep

        data = SimpleNamespace()
        context = RunContext(None, ("a" * 64, "b" * 64))
        sweep = SimpleNamespace(run_context=context, evidence=SimpleNamespace(identity={
            "code_sha256": "a" * 64, "evaluator_sha256": "b" * 64,
        }))
        self.evaluator.return_value = "c" * 64
        with self.assertRaisesRegex(ValueError, "changed during execution"):
            write_ba002_sweep(None, data, sweep)

    def test_single_backtest_drift_refuses_before_a_completion_manifest_exists(self):
        from boring_alpha.backtest import Backtester
        from boring_alpha.cli import run_backtest

        original = Backtester.run
        def drift(engine, signal):
            result = original(engine, signal)
            self.code.return_value = "c" * 64
            return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = prepare_ba002_demo(root)
            with patch.object(Backtester, "run", drift):
                with self.assertRaisesRegex(ValueError, "changed during execution"):
                    run_backtest(paths["development"])
            self.assertFalse((root / "experiments").exists())
