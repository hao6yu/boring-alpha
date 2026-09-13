"""Source and synthetic extraction checks. No price data or strategy returns."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

PATH = Path(__file__).resolve().parents[1] / 'research/equity-event-test-2026-09-10/feature_extract.py'
SPEC = importlib.util.spec_from_file_location('equity_event_feature_extract', PATH)
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)


def slot(symbol, window):
    source = PATH.parents[1] / 'equity-event-pilot-2026-09-10/sec-events.json'
    slots = json.loads(source.read_text())['slots']
    selected = next(s for s in slots if s['historical_symbol'] == symbol and s['slot_id'].endswith('W'+str(window)))
    for record in (selected['current'], selected['prior']):
        files = [record['exhibit_file']] + [c['file'] for c in record.get('accounting_companions', [])]
        if any(not (PATH.parents[2] / filename).exists() for filename in files):
            pytest.skip('Ignored archived SEC fixture documents unavailable in this checkout')
    return selected


def test_team_transition_uses_current_gaap_comparatives_not_prior_ifrs():
    r = f.extract_pair(slot('TEAM', 1))
    assert r['flags']['accounting_transition']
    assert r['comparisons']['revenue']['current_value'] == '807392000'
    eps = r['comparisons']['diluted_eps']
    assert eps['current_value'] == '-0.05'
    assert eps['current_release_comparable_prior_value'] == '-1.63'
    assert eps['original_prior_value'] is None
    assert eps['original_prior_reported_value_before_basis_gate'] == '-1.59'
    assert eps['same_current_release_comparison_eligible']
    assert r['current']['flags']['text_encoding_artifact']


def test_snap_one_unequal_duration_is_not_normalized_or_invented():
    r = f.extract_pair(slot('SNPO', 2))
    assert r['flags']['unequal_duration']
    for comparison in r['comparisons'].values():
        assert not comparison['same_current_release_comparison_eligible']
        assert 'UNEQUAL_FISCAL_DURATION' in comparison['missing_reasons']
    assert r['current']['documents'][0]['explicit_financial_section_marker_applied']
    assert 'Consolidated Statements of Operations' not in r['narrative']['current']


def test_nextcure_annual_column_no_revenue_invented():
    r = f.extract_pair(slot('NXTC', 2))
    assert r['flags']['scope'] == 'year'
    assert r['comparisons']['diluted_eps']['current_value'] == '-2.69'
    assert r['comparisons']['diluted_eps']['current_release_comparable_prior_value'] == '-2.51'
    assert r['comparisons']['revenue']['current_value'] is None


def test_straightforward_original_values_have_hashed_cell_evidence():
    expected = [('NRIX', '10791000', '10252000', '-0.90'), ('EGRX', '65901000', '39853000', '-0.27')]
    for symbol, current, prior, eps in expected:
        r = f.extract_pair(slot(symbol, 1))
        assert r['comparisons']['revenue']['current_value'] == current
        assert r['comparisons']['revenue']['current_release_comparable_prior_value'] == prior
        assert r['comparisons']['diluted_eps']['current_value'] == eps
        evidence = r['current']['metrics']['revenue']['current']['evidence'][0]
        assert len(evidence['sha256']) == 64 and evidence['row_label']
        assert evidence['scope'] == 'quarter' and evidence['period_end'].startswith('2022')


TABLE = '''<table><tr><th colspan="5">Consolidated Statements of Operations (in thousands, except per share) U.S. $</th></tr>
<tr><th></th><th colspan="2">Three Months Ended September 30,</th><th colspan="2">Nine Months Ended September 30,</th></tr>
<tr><th></th><th>2022</th><th>2021</th><th>2022</th><th>2021</th></tr>
<tr><td>Total revenue</td><td>100</td><td>80</td><td>900</td><td>700</td></tr>
<tr><td>Diluted earnings per share</td><td>(0.20)</td><td>0.10</td><td>8.00</td><td>7.00</td></tr></table>'''


def test_aligned_spans_do_not_select_ytd_and_layout_prose_is_preserved():
    raw = '<table><tr><td>Management explains customer demand and our future plans.</td></tr></table>' + TABLE
    doc = f.Document(raw)
    values, financial, _ = f.extract_tables(doc, {'file': 'synthetic', 'sha256': 'x'}, '2022-09-30', '2021-09-30', 'quarter')
    assert values['revenue']['current']['value'] == '100000'
    assert values['diluted_eps']['current']['value'] == '-0.20'
    narrative = f.narrative(doc.root, financial)
    assert 'Management explains customer demand' in narrative
    assert 'Total revenue' not in narrative and '900' not in narrative


def test_non_gaap_and_ambiguous_units_stay_missing():
    for raw in (TABLE.replace('Consolidated Statements of Operations', 'Non-GAAP Reconciliation'), TABLE.replace('in thousands, except per share', 'amounts')):
        doc = f.Document(raw)
        result, _, _ = f.extract_tables(doc, {'file': 'synthetic', 'sha256': 'x'}, '2022-09-30', '2021-09-30', 'quarter')
        assert result['revenue']['current']['value'] is None


def test_named_currency_can_come_from_original_release_presentation_note():
    raw = '<p>All amounts are expressed in U.S. dollars.</p>'+TABLE.replace('U.S. $', '$')
    result, _, _ = f.extract_tables(f.Document(raw), {'file': 'synthetic', 'sha256': 'x'}, '2022-09-30', '2021-09-30', 'quarter')
    evidence = result['revenue']['current']['evidence'][0]
    assert evidence['currency'] == 'USD'
    assert 'U.S. dollars' in evidence['currency_source_evidence']['excerpt']
    raw = '<p>Foreign sales are translated to U.S. dollars for financial reporting purposes.</p>'+TABLE.replace('U.S. $', '$')
    result, _, _ = f.extract_tables(f.Document(raw), {'file': 'synthetic', 'sha256': 'x'}, '2022-09-30', '2021-09-30', 'quarter')
    assert result['diluted_eps']['current']['evidence'][0]['currency'] == 'USD'
    assert f.explicit_currency('We translated an illustrative balance to U.S. dollars for a sensitivity exercise.') is None


def test_explicit_sales_and_service_fees_row_is_revenue_not_sales_expense():
    raw = TABLE.replace('Total revenue', 'Sales and service fees')
    result, _, _ = f.extract_tables(f.Document(raw), {'file': 'synthetic', 'sha256': 'x'}, '2022-09-30', '2021-09-30', 'quarter')
    assert result['revenue']['current']['value'] == '100000'
    assert result['revenue']['comparable_prior']['value'] == '80000'
    assert result['revenue']['current']['evidence'][0]['row_label'] == 'Sales and service fees'
    assert not f.REVENUE.fullmatch('Sales and marketing expenses')


def test_hash_mismatch_and_missing_prior_do_not_claim_source_readiness():
    s = slot('NRIX', 1)
    s['current']['exhibit_sha256'] = '0'*64
    r = f.extract_pair(s)
    assert r['status'] == 'SOURCE_PAIR_UNRESOLVED'
    assert 'DOCUMENT_HASH_MISMATCH' in r['missing_reasons']
    s = slot('NRIX', 1)
    s['prior'] = None
    s['prior_match'] = None
    r = f.extract_pair(s)
    assert r['status'] == 'SOURCE_PAIR_UNRESOLVED'
    assert 'ORIGINAL_DOCUMENT_MISSING' in r['missing_reasons']


def test_domestic_regulatory_currency_is_separate_from_literal_currency():
    raw = TABLE.replace('U.S. $', '$')
    metrics, _, _ = f.extract_tables(f.Document(raw), {'file': 'synthetic', 'sha256': 'x'}, '2022-09-30', '2021-09-30', 'quarter')
    original = json.dumps(metrics, sort_keys=True)
    for cover_raw in (
        '<ix:nonNumeric name="dei:EntityIncorporationStateCountryCode" contextRef="c">Delaware</ix:nonNumeric>',
        '<table><tr><td>Maryland</td><td>001-1234</td></tr><tr><td>(State or other jurisdiction of incorporation)</td><td>(Commission File Number)</td></tr></table>',
    ):
        cover = f.cover_incorporation(f.Document(cover_raw))
        resolved = f.resolve_currency(metrics, 'Consolidated statements of operations', cover)
        assert resolved['currency'] == 'USD'
        assert resolved['method'] == 'REGULATORY_USD_INFERENCE'
        assert resolved['literal_metric_currencies']['diluted_eps'] == ['DOLLAR_SYMBOL']
        assert json.dumps(metrics, sort_keys=True) == original
    foreign = f.cover_incorporation(f.Document('<ix:nonNumeric name="dei:EntityIncorporationStateCountryCode">Cayman Islands</ix:nonNumeric>'))
    assert f.resolve_currency(metrics, '', foreign)['currency'] is None
    assert f.resolve_currency(metrics, 'We report in Canadian dollars.', cover)['currency'] is None
    assert f.resolve_currency(metrics, 'The issuer is a foreign private issuer.', cover)['currency'] is None
    assert f.resolve_currency(metrics, '', {})['currency'] is None


def test_actual_original_cover_currency_requires_accession_hash_and_cik():
    source = PATH.parent/'sec-checkpoints/events-dd4391ac635b8682d5cd688a89c41c400a090305c48176efde2ccec7d788ecf3.json'
    if not source.exists():
        source = PATH.parent/'sec-events-current-roster.json'
    if not source.exists():
        pytest.skip('Ignored/current source checkpoint unavailable')
    s = next(x for x in json.loads(source.read_text())['slots'] if x['slot_id']=='0001511337-2020Q1')
    if not s.get('current') or not (PATH.parents[2]/s['current']['primary_file']).exists():
        pytest.skip('Archived original cover unavailable')
    resolved = f.extract_pair(s)
    assert resolved['current']['currency_resolution']['method'] == 'REGULATORY_USD_INFERENCE'
    assert resolved['current']['currency_resolution']['cover_evidence']['state'] == 'Maryland'
    assert resolved['flags']['current_metric_currency']['revenue'] == ['DOLLAR_SYMBOL']
    assert f.original_cover_evidence(s['current'], '0000000001')['status'] == 'ORIGINAL_COVER_UNRESOLVED'


def test_cached_table_prefix_matches_original_prefix_parse_semantics():
    raw = '<div>'+('word '*500)+'<style>hidden</style><p>visible &amp; quoted</p><div style="display:none">ignored<table><tr><td>x</td></tr></table></div><table><tr><td>nested<table><tr><td>data</td></tr></table>tail</td></tr></table></div>'
    doc = f.Document(raw)
    for table in doc.root.walk('table'):
        assert f.clean(doc.table_prefixes[table.offset]) == f.clean(f.Document(raw[:table.offset]).root.text()[-1000:])
