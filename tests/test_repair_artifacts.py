"""Lifecycle labels must not contaminate immutable economic identities."""

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from boring_alpha.ba002_artifacts import load_ba002_evidence
from boring_alpha.cli import _banners, run_backtest, run_sweep_command
from boring_alpha.config import load_config
from boring_alpha.data import load_market_data
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_commands import confirm_research_freeze
from boring_alpha.research_freeze import freeze_sha256, load_freeze
from boring_alpha.sweep import run_sweep, write_sweep_report


@pytest.mark.parametrize('command', [run_backtest, run_sweep_command])
def test_demo_confirmation_does_not_change_existing_run_artifacts(tmp_path, command, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("synthetic workflow located a real journal")
    monkeypatch.setattr("boring_alpha.research_family.canonical_journal_path", forbidden)
    paths = prepare_ba002_demo(tmp_path)
    config = load_config(paths['development'])
    command(paths['development'])
    manifests = list((tmp_path / 'experiments').rglob('manifest.json'))
    assert len(manifests) == 1
    manifest = manifests[0]
    before = manifest.read_bytes()
    frozen_bytes = manifest.with_name('freeze.json').read_bytes()
    draft = load_freeze(config.research.freeze_path)
    # Also pins that an unchanged freshly-generated demo can use the public
    # confirm command, from either period sharing its one freeze.
    confirm_research_freeze(paths['validation'], freeze_sha256(draft), 'Fictional review only')
    command(paths['development'])
    assert list((tmp_path / 'experiments').rglob('manifest.json')) == manifests
    assert manifest.read_bytes() == before
    assert manifest.with_name('freeze.json').read_bytes() == frozen_bytes
    records = [json.loads(line) for line in manifest.with_name('provenance.jsonl').read_text().splitlines()]
    assert [row['research_freeze']['status'] for row in records] == ['draft', 'confirmed']
    assert records[1]['research_freeze']['confirmation']['reason'] == 'Fictional review only'


def test_repair_is_labeled_and_cannot_become_eligibility_evidence(tmp_path):
    paths = prepare_ba002_demo(tmp_path)
    config = load_config(paths['development'])
    data = load_market_data(config)
    sweep = run_sweep(config, data)
    # Inject lifecycle metadata into fictional results, never grant or claim
    # historical access. Journal tests separately prove repair eligibility.
    context = replace(sweep.run_context, attempt=SimpleNamespace(
        repair_of='fictional-original', revealed_diagnostic=True))
    sweep = replace(sweep, run_context=context)
    _, root = write_sweep_report(config, data, sweep)
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['repair_of'] == 'fictional-original'
    assert manifest['revealed_diagnostic'] is True
    assert 'REVEALED-DATA REPAIR' in (root / 'summary.md').read_text()
    assert any('REVEALED-DATA REPAIR' in banner for banner in _banners(config, context))
    with pytest.raises(ValueError, match='diagnostic'):
        load_ba002_evidence(root)
