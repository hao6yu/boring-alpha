"""Public sensitivity workflow uses fictional archives, never research history."""
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from boring_alpha import cli
from boring_alpha.tax.policy import SCENARIOS
import test_cli as fixture_module


@pytest.fixture(scope='module')
def archive():
    # Reuse construction only, not unittest inheritance (which reruns methods).
    fixture = fixture_module.AfterTaxCommandTests()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.tearDown()


def assumptions(root, capacity=0, destination='outside_account'):
    path = root / f'loss-{capacity}-{destination}.toml'
    path.write_text(f'''[loss_sensitivity]
annual_capacity = {capacity}
outside_ordinary_income = 50000
savings_destination = "{destination}"
''')
    return path


def execute(archive, policy, *, output=None):
    with contextlib.redirect_stdout(output or io.StringIO()):
        assert cli.run_aftertax(archive.taxed_dir, archive.policy,
                               loss_sensitivity_path=policy) == 0
    return sorted(archive.taxed_dir.glob('tax-loss-sensitivity-*.json'))


def test_zero_capacity_separates_baseline_and_preserves_frozen_artifacts(archive):
    immutable = {name: (archive.taxed_dir / name).read_bytes()
                 for name in ('manifest.json', 'criteria.json', 'tax.json')}
    output = io.StringIO()
    paths = execute(archive, assumptions(archive.root), output=output)
    payload = next(json.loads(path.read_text()) for path in paths
                   if json.loads(path.read_text())['loss_sensitivity']['annual_capacity'] == 0)
    baseline = json.loads(immutable['tax.json'])
    assert payload['baseline_runs'] == baseline['runs']
    assert payload['non_gating'] is True
    assert payload['source'] == 'aftertax-loss-sensitivity'
    assert payload['initial_account_size'] == 10000
    assert payload['loss_sensitivity']['ordinary_rate'] == .35
    assert 'runs' not in payload  # Cannot impersonate the ordinary tax envelope.
    for account, scenarios in payload['sensitivity_runs'].items():
        assert set(scenarios) == {scenario.key for scenario in SCENARIOS}
        for key, record in scenarios.items():
            original = payload['baseline_runs'][account][key]
            assert record['wealth']['after_tax_post_liquidation'] == original['wealth']['after_tax_post_liquidation']
            assert record['wealth']['household_terminal_wealth'] == original['wealth']['after_tax_post_liquidation']
            assert record['loss_sensitivity']['non_gating'] is True
    assert 'NON-GATING HOUSEHOLD-WEALTH' in output.getvalue()
    assert 'CAGR' not in output.getvalue()
    assert {name: (archive.taxed_dir / name).read_bytes() for name in immutable} == immutable


def test_identical_sensitivity_is_idempotent_and_changed_assumptions_get_new_identity(archive):
    policy = assumptions(archive.root, 3000)
    paths = execute(archive, policy)
    before = {path: path.read_bytes() for path in paths}
    assert execute(archive, policy) == paths
    assert {path: path.read_bytes() for path in paths} == before
    later = execute(archive, assumptions(archive.root, 1500))
    assert len(later) == len(paths) + 1
    assert len({json.loads(path.read_text())['loss_sensitivity_sha256'] for path in later}) == len(later)


def test_contribution_mode_reports_deposits_without_self_financing_cagr(archive):
    paths = execute(archive, assumptions(archive.root, 3000, 'contribute_to_account'))
    payload = next(json.loads(path.read_text()) for path in paths
                   if json.loads(path.read_text())['loss_sensitivity']['savings_destination'] == 'contribute_to_account')
    for scenarios in payload['sensitivity_runs'].values():
        for record in scenarios.values():
            assert record['metrics']['after_tax_cagr'] is None
            assert record['metrics']['tax_drag_bps'] is None
            assert record['metrics']['effective_tax_rate'] is None
            assert 'contributed_tax_savings_post_liquidation' in record['wealth']


def test_sensitivity_keeps_failed_identity_notices_visible(archive):
    from boring_alpha.tax.overlay import apply_overlay
    def invalid_identity(*args, **kwargs):
        result = apply_overlay(*args, **kwargs)
        result['identity_checks']['income_plus_gain_passed'] = False
        return result
    output = io.StringIO()
    # Unique assumptions keep this intentionally invalid diagnostic separate
    # from other fixture artifacts. Production source bytes are not changed.
    with patch('boring_alpha.tax.overlay.apply_overlay', side_effect=invalid_identity):
        execute(archive, assumptions(archive.root, 2500), output=output)
    assert 'identity checks failed for strategy /' in output.getvalue()
    assert 'income_plus_gain_passed' in output.getvalue()


def test_bad_sensitivity_refused_before_archive_is_opened(tmp_path):
    policy = tmp_path / 'bad.json'
    policy.write_text('{"annual_capacity":3000}')
    with patch('boring_alpha.cli.read_manifest', side_effect=AssertionError('archive opened')):
        with pytest.raises(ValueError, match='requires'):
            cli.run_aftertax(tmp_path / 'NO_ARCHIVE', tmp_path / 'NO_TAX', loss_sensitivity_path=policy)


def test_cli_routes_explicit_policy_and_default_stays_off():
    args = ['boring-alpha', 'aftertax', 'ARCHIVE', '--policy', 'TAX.toml']
    for suffix, expected in (([], None), (['--loss-sensitivity', 'LOSS.toml'], Path('LOSS.toml'))):
        with patch('sys.argv', args + suffix), patch('boring_alpha.cli.run_aftertax', return_value=0) as run:
            with pytest.raises(SystemExit) as result:
                cli.main()
            assert result.value.code == 0
            run.assert_called_once_with(Path('ARCHIVE'), Path('TAX.toml'), None, loss_sensitivity_path=expected)
