"""Synthetic-only acceptance tests for the BA-002 command/evidence pipeline."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from boring_alpha.cli import run_aftertax, run_backtest, run_classify, run_sweep_command
from boring_alpha.ba002_artifacts import load_ba002_evidence
from boring_alpha.config import load_config
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.profiles import profile_for
from boring_alpha.criteria_ba002 import evaluate_period


class BA002ProfileIntegrationTests(unittest.TestCase):
    def test_profile_grid_and_independent_common_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = prepare_ba002_demo(Path(directory))
            config = load_config(paths['development'])
            grid = profile_for('BA-002').grid(config)
            self.assertEqual(list(grid), ['base', 'double_cost', 'without_9', 'without_12', 'without_15'])
            self.assertEqual(grid['without_15'].strategy(config, None).horizons, (9, 12))
            self.assertEqual(grid['without_15'].strategy(config, None).warmup_months, 15)
            self.assertEqual(grid['double_cost'].cost_bps, 20)
            self.assertEqual(grid['double_cost'].benchmark(config).rebalance, 'annual')

    def test_unknown_profile_refused_before_market_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = prepare_ba002_demo(Path(directory))
            path = paths['development']
            path.write_text(path.read_text().replace('id = "BA-002"', 'id = "RENAMED"')
                            .replace('period = "development"', 'period = "exploratory"'))
            with patch('boring_alpha.cli.load_market_data', side_effect=AssertionError('loaded')):
                with self.assertRaisesRegex(ValueError, 'profile'):
                    run_backtest(path)


class BA002EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.paths = prepare_ba002_demo(cls.root)
        with contextlib.redirect_stdout(io.StringIO()):
            run_sweep_command(cls.paths['development'])
            run_sweep_command(cls.paths['validation'])
        cls.sweeps = {}
        for path in (cls.root / 'experiments/BA-002/sweeps').iterdir():
            if not path.is_dir():
                continue
            manifest = json.loads((path / 'manifest.json').read_text())
            cls.sweeps[manifest['evaluation_period']] = path

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_archives_include_paired_benchmarks_and_evidence_checksums(self):
        root = self.sweeps['development']
        manifest = json.loads((root / 'manifest.json').read_text())
        tax = json.loads((root / 'tax.json').read_text())
        self.assertEqual(manifest['artifact_schema'], 7)
        self.assertIn('criteria.json', manifest['artifacts_sha256'])
        self.assertIn('tax.json', manifest['artifacts_sha256'])
        self.assertIn('research_contract.json', manifest['artifacts_sha256'])
        self.assertIn('calendar.json', manifest['artifacts_sha256'])
        self.assertEqual(len(manifest['account_map']), 5)
        for row, accounts in manifest['account_map'].items():
            for account in accounts.values():
                self.assertEqual(len(tax['runs'][account]), 8)
        self.assertNotEqual(tax['runs']['benchmark'], tax['runs']['benchmark:double_cost'])
        self.assertIn('reference_12', tax['runs'])
        self.assertNotIn('reference_12', manifest['grid'])

    def test_posthoc_replay_includes_every_paired_account(self):
        root = self.sweeps['development']
        with contextlib.redirect_stdout(io.StringIO()):
            run_aftertax(root, self.paths['policy'])
        original = json.loads((root / 'tax.json').read_text())
        outputs = list(root.glob('tax-*.json'))
        self.assertEqual(len(outputs), 1)
        replay = json.loads(outputs[0].read_text())
        self.assertEqual(original['runs'], replay['runs'])

    def test_classification_is_research_eligibility_with_synthetic_banner(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(run_classify(self.sweeps['development'], self.sweeps['validation']), 0)
        self.assertIn('SYNTHETIC', output.getvalue())
        self.assertIn('eligib', output.getvalue().lower())
        self.assertNotIn('ADVANCE', output.getvalue())

    def test_tampered_tax_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sweep'
            shutil.copytree(self.sweeps['development'], root)
            tax = json.loads((root / 'tax.json').read_text())
            tax['runs'].pop('benchmark:without_12')
            (root / 'tax.json').write_text(json.dumps(tax))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                run_classify(root, self.sweeps['validation'])

    @staticmethod
    def _rewrite_payload(root, name, payload):
        """Keep byte checksums consistent to exercise semantic guards too."""
        content = json.dumps(payload).encode()
        (root / name).write_bytes(content)
        manifest = json.loads((root / 'manifest.json').read_text())
        manifest['artifacts_sha256'][name] = hashlib.sha256(content).hexdigest()
        (root / 'manifest.json').write_text(json.dumps(manifest))

    def test_saved_pass_flags_cannot_change_classification(self):
        expected = evaluate_period(load_ba002_evidence(self.sweeps['development']))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sweep'
            shutil.copytree(self.sweeps['development'], root)
            criteria = json.loads((root / 'criteria.json').read_text())
            criteria['passed'] = not expected.passed
            for criterion in criteria['criteria']:
                criterion['passed'] = not criterion['passed']
            # Even internally consistent byte hashes cannot make saved verdicts
            # authoritative. The underlying account/scenario evidence decides.
            self._rewrite_payload(root, 'criteria.json', criteria)
            actual = evaluate_period(load_ba002_evidence(root))
            self.assertEqual(actual, expected)

    def test_cli_classification_ignores_both_saved_period_verdicts(self):
        expected_output = io.StringIO()
        with contextlib.redirect_stdout(expected_output):
            run_classify(self.sweeps['development'], self.sweeps['validation'])
        actual_pass = all(evaluate_period(load_ba002_evidence(path)).passed for path in self.sweeps.values())
        with tempfile.TemporaryDirectory() as directory:
            copies = {}
            for period, original in self.sweeps.items():
                root = Path(directory) / period
                shutil.copytree(original, root)
                criteria = json.loads((root / 'criteria.json').read_text())
                criteria['passed'] = not actual_pass
                for criterion in criteria['criteria']:
                    criterion['passed'] = not actual_pass
                self._rewrite_payload(root, 'criteria.json', criteria)
                copies[period] = root
            actual_output = io.StringIO()
            with contextlib.redirect_stdout(actual_output):
                run_classify(copies['development'], copies['validation'])
            self.assertEqual(actual_output.getvalue(), expected_output.getvalue())

    def test_future_distribution_changes_preserve_identical_bounded_rerun(self):
        path = self.root / 'data/distributions_daily.csv'
        original = path.read_text()
        changed = []
        for row in original.splitlines():
            fields = row.split(',')
            if fields[0].startswith('2019-'):
                fields[2:] = ['FUTURE_NUMERIC_PARSE_TRAP', 'FUTURE_NUMERIC_PARSE_TRAP']
            changed.append(','.join(fields))
        self.assertNotEqual('\n'.join(changed) + '\n', original)
        root = self.sweeps['development']
        manifest_before = (root / 'manifest.json').read_bytes()
        provenance_before = len((root / 'provenance.jsonl').read_text().splitlines())
        try:
            path.write_text('\n'.join(changed) + '\n')
            with contextlib.redirect_stdout(io.StringIO()):
                run_sweep_command(self.paths['development'])
            self.assertEqual((root / 'manifest.json').read_bytes(), manifest_before)
            self.assertEqual(len((root / 'provenance.jsonl').read_text().splitlines()), provenance_before + 1)
        finally:
            path.write_text(original)

    def test_embedded_behavior_changes_are_refused_without_live_config_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sweep'
            shutil.copytree(self.sweeps['development'], root)
            path = root / 'manifest.json'
            manifest = json.loads(path.read_text())
            self.assertIn('exposure = 0.6', manifest['config_toml'])
            manifest['config_toml'] = manifest['config_toml'].replace('exposure = 0.6', 'exposure = 0.9')
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'benchmark'):
                load_ba002_evidence(root)

    def test_missing_diagnostic_tax_account_is_incomplete_even_with_valid_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sweep'
            shutil.copytree(self.sweeps['development'], root)
            tax = json.loads((root / 'tax.json').read_text())
            tax['runs'].pop('reference_12')
            self._rewrite_payload(root, 'tax.json', tax)
            with self.assertRaisesRegex(ValueError, 'complete archived account map'):
                load_ba002_evidence(root)

    def test_noninteger_schema_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sweep'
            shutil.copytree(self.sweeps['development'], root)
            path = root / 'manifest.json'
            manifest = json.loads(path.read_text())
            manifest['artifact_schema'] = 7.0
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'artifact_schema'):
                load_ba002_evidence(root)

    def test_incomplete_publication_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sweep'
            shutil.copytree(self.sweeps['development'], root)
            (root / 'manifest.json').unlink()
            with self.assertRaises(ValueError):
                run_classify(root, self.sweeps['validation'])

    def test_single_backtest_uses_ensemble_decisions(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_backtest(self.paths['development'])
        roots = [path for path in (self.root / 'experiments/BA-002').iterdir()
                 if path.name != 'sweeps']
        self.assertEqual(len(roots), 1)
        decisions = json.loads((roots[0] / 'decisions.json').read_text())
        self.assertTrue(decisions)
        self.assertTrue(all(len(row['horizon_evidence']) == 3 for row in decisions))
        self.assertTrue(all(row['cash_return'] is None for row in decisions))


if __name__ == '__main__':
    unittest.main()
