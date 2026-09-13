"""Synthetic cache integrity and membership checks; no archived inputs read."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / 'research/equity-event-test-2026-09-10/panel.py'
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location('equity_event_feature_cache_test_panel', PATH)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return p.digest(path)


def install_cache(root, results, sec_sha='roster', extractor_sha='extractor', errors=None):
    snapshot = {'sec_events_sha256': sec_sha, 'extractor_sha256': extractor_sha,
                'results': results, 'errors': errors or []}
    snapshot_path = root / 'ignored/features.json'
    record = {'path': 'ignored/features.json', 'sha256': save(snapshot_path, snapshot)}
    report = {'sec_events_sha256': sec_sha, 'extractor_sha256': extractor_sha,
              'cohort_sha256': p.digest(root / 'sec-cohort.json'),
              'source_feature_snapshot': record}
    save(root / 'feature-source-audit.json', report)
    return snapshot, report


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'HERE', tmp_path)
    monkeypatch.setattr(p, 'ROOT', tmp_path)
    save(tmp_path / 'sec-cohort.json', {'issuers': ['synthetic']})
    (tmp_path / 'current.htm').write_text('Synthetic current original release')
    (tmp_path / 'prior.htm').write_text('Synthetic original prior release')
    current = {'file': 'current.htm', 'sha256': p.digest(tmp_path / 'current.htm')}
    prior = {'file': 'prior.htm', 'sha256': p.digest(tmp_path / 'prior.htm')}
    results = {'one': {'slot_id': 'one', 'current': {'documents': [current]},
                       'prior': {'documents': [prior]}, 'repeated_evidence': [current]}}
    snapshot, report = install_cache(tmp_path, results)
    return tmp_path, results, snapshot, report


@pytest.mark.parametrize('stale', ['sec_events_sha256', 'extractor_sha256'])
def test_stale_roster_or_extractor_falls_back_without_reading_snapshot(cache, stale):
    root, _, _, report = cache
    report[stale] = 'different'
    report['source_feature_snapshot']['path'] = 'does-not-exist.json'
    save(root / 'feature-source-audit.json', report)
    assert p.audited_feature_cache('roster', 'extractor') == ({}, None)


def test_missing_cache_falls_back(cache):
    root, *_ = cache
    (root / 'feature-source-audit.json').unlink()
    assert p.audited_feature_cache('roster', 'extractor') == ({}, None)


def test_snapshot_bytes_are_hash_checked(cache):
    root, *_ = cache
    with (root / 'ignored/features.json').open('a') as handle:
        handle.write(' ')
    with pytest.raises(AssertionError):
        p.audited_feature_cache('roster', 'extractor')


@pytest.mark.parametrize('defect', ['inner_roster', 'inner_extractor', 'errors', 'slot_id', 'cohort'])
def test_inconsistent_snapshot_and_cohort_are_rejected(cache, defect):
    root, _, snapshot, report = cache
    if defect == 'inner_roster': snapshot['sec_events_sha256'] = 'other'
    if defect == 'inner_extractor': snapshot['extractor_sha256'] = 'other'
    if defect == 'errors': snapshot['errors'] = [{'slot_id': 'one', 'error': 'synthetic exception'}]
    if defect == 'slot_id': snapshot['results']['one']['slot_id'] = 'different'
    if defect == 'cohort': save(root / 'sec-cohort.json', {'issuers': ['changed']})
    report['source_feature_snapshot']['sha256'] = save(root / 'ignored/features.json', snapshot)
    save(root / 'feature-source-audit.json', report)
    with pytest.raises(AssertionError):
        p.audited_feature_cache('roster', 'extractor')


@pytest.mark.parametrize('filename', ['current.htm', 'prior.htm'])
def test_raw_original_document_tampering_is_rejected(cache, filename):
    root, *_ = cache
    (root / filename).write_text('A changed source is not the cached source')
    with pytest.raises(AssertionError, match='Cached original document changed'):
        p.audited_feature_cache('roster', 'extractor')


def test_cache_preserves_features_and_deduplicates_raw_references(cache):
    _, expected, _, report = cache
    actual, provenance = p.audited_feature_cache('roster', 'extractor')
    assert actual == expected
    assert provenance['verified_original_documents'] == 2
    assert provenance['source_feature_snapshot'] == report['source_feature_snapshot']


@pytest.mark.parametrize('change', ['existing_binding', 'unrelated_append'])
def test_cover_source_ledger_is_bound_even_when_raw_document_is_unchanged(cache, change):
    root, results, _, _ = cache
    ledger = {'sources': {'https://synthetic.example/original.htm':
                         {'file': 'current.htm', 'sha256': p.digest(root / 'current.htm')}}}
    ledger_sha = save(root / 'sec-sources.json', ledger)
    proof = results['one']['current']['documents'][0]
    proof.update(source_manifest_path='sec-sources.json', source_manifest_snapshot_sha256=ledger_sha)
    install_cache(root, results)
    assert p.audited_feature_cache('roster', 'extractor')[0] == results
    if change == 'existing_binding':
        ledger['sources']['https://synthetic.example/original.htm']['file'] = 'wrong-document.htm'
    else:
        ledger['sources']['https://synthetic.example/unrelated.htm'] = {'file': 'unrelated.htm', 'sha256': 'new'}
    save(root / 'sec-sources.json', ledger)
    with pytest.raises(AssertionError, match='Cached original document changed'):
        p.audited_feature_cache('roster', 'extractor')


def test_cached_build_matches_fresh_build_and_preserves_all_registered_slots(tmp_path, monkeypatch):
    """Cache one READY pair and one source-rejected pair; extract the missing pair.

    A foreign cache key must not create a new event, and a cached successful
    extraction must not override the roster's failed original-source join.
    """
    monkeypatch.setattr(p, 'HERE', tmp_path)
    monkeypatch.setattr(p, 'ROOT', tmp_path)
    monkeypatch.setattr(p, 'RAW', tmp_path / 'ignored')
    (tmp_path / 'feature_extract.py').write_text('# Synthetic extractor identity only\n')
    save(tmp_path / 'sec-cohort.json', {'policy_sha256': p.POLICY_SHA, 'issuers': [{}] * 100})
    save(tmp_path / 'price-manifest.json', {'synthetic': True})
    sessions = []
    day = date(2019, 10, 1)
    while day <= date(2023, 12, 29):
        if day.weekday() < 5: sessions.append(day.isoformat())
        day += timedelta(days=1)
    bars = {day: {'close': 50., 'adjClose': 50., 'volume': 100000.,
                  'splitFactor': 1., 'divCash': 0.} for day in sessions}
    monkeypatch.setattr(p, 'calendar', lambda: sessions)
    monkeypatch.setattr(p, 'load_prices', lambda **kwargs: ({'A': {'rows': bars, 'issues': {}}}, {}))
    monkeypatch.setattr(p, 'numeric_features', lambda pair, *args, **kwargs:
                        ({'synthetic_source_value': pair['source_value']}, {}))
    def no_target(*args):
        raise AssertionError('An evaluation outcome must remain masked')
    monkeypatch.setattr(p, 'target', no_target)
    slots, pairs = [], {}
    for i, name in enumerate(['cached', 'fallback', 'blocked']):
        checks = {key: True for key in ['current_release', 'earliest_event', 'prior_release',
                                       'period_identity', 'identity', 'timing']}
        if name == 'blocked': checks['prior_release'] = False
        slots.append({'slot_id': name, 'cik': str(i), 'status': 'SYNTHETIC', 'checks': checks,
                      'current': {'accession': name, 'filing_date': '2022-06-01',
                                  'acceptance_eastern': '2022-06-01T16:01:00-04:00',
                                  'security': {'historical_symbol': 'A'}},
                      'prior': {'filing_date': '2021-06-01',
                                'acceptance_eastern': '2021-06-01T16:01:00-04:00'}})
        pairs[name] = {'slot_id': name, 'source_value': i + 1,
                       'status': 'SOURCE_PAIR_READ_NUMERIC_COVERAGE_EXPLICIT', 'missing_reasons': [],
                       'flags': {'document_types_match': True},
                       'current': {'period_end': '2022-03-31', 'documents': [], 'flags': {}},
                       'original_prior': {'documents': [], 'flags': {}},
                       'narrative': {'current': 'Synthetic current ' + name,
                                     'original_prior': 'Synthetic prior ' + name}}
    slots += [{'slot_id': f'missing:{i}', 'cik': str(i), 'status': 'UNRESOLVED', 'current': None}
              for i in range(1597)]
    sec_sha = save(tmp_path / 'sec-events.json', {'policy_sha256': p.POLICY_SHA,
                                                'status': 'SYNTHETIC', 'slots': slots})
    calls = []
    def extract(slot):
        calls.append(slot['slot_id'])
        return deepcopy(pairs[slot['slot_id']])
    monkeypatch.setattr(p, 'extract_pair', extract)
    fresh_inventory = p.build()
    fresh_panel = json.loads((tmp_path / 'ignored/development-panel.json').read_text())
    fresh_features = json.loads((tmp_path / 'ignored/source-features.json').read_text())
    assert calls == ['cached', 'fallback', 'blocked']
    cached_pairs = {key: pairs[key] for key in ['cached', 'blocked']}
    cached_pairs['foreign'] = {'slot_id': 'foreign', 'status': 'NOT_A_REGISTERED_SLOT'}
    install_cache(tmp_path, cached_pairs, sec_sha, p.digest(tmp_path / 'feature_extract.py'))
    calls.clear()
    cached_inventory = p.build()
    cached_panel = json.loads((tmp_path / 'ignored/development-panel.json').read_text())
    assert cached_panel == fresh_panel
    assert json.loads((tmp_path / 'ignored/source-features.json').read_text()) == fresh_features
    assert calls == ['fallback']
    assert len(cached_panel) == 1600
    assert {row['event_id'] for row in cached_panel} == {slot['slot_id'] for slot in slots}
    assert cached_panel[0]['status'] == cached_panel[1]['status'] == 'READY'
    assert cached_panel[0]['features']['synthetic_source_value'] == 1
    assert cached_panel[1]['features']['synthetic_source_value'] == 2
    assert cached_panel[2]['status'] == 'UNRESOLVED'
    assert 'ORIGINAL_SOURCE_JOIN_UNRESOLVED' in cached_panel[2]['reasons']
    assert fresh_inventory['audited_feature_cache'] is None
    assert cached_inventory['audited_feature_cache'] is not None
