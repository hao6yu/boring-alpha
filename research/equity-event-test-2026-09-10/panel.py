"""Join original earnings sources to past prices; mask evaluation outcomes.

All detailed source features and provider-derived rows are stored under the
ignored data directory. The public inventory contains coverage and provenance.
No source/price gap removes a registered slot. READY uses only pre-entry facts.
"""
from bisect import bisect_right
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
import csv
import io
import zipfile

import exchange_calendars as xcals
from feature_extract import extract_pair
from model import policy, POLICY_SHA
from price_data import parse, symbol

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = ROOT / 'data/snapshots/equity-event-test-2026-09-10'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(raw)
    tmp.replace(path)
    return hashlib.sha256(raw).hexdigest()


def calendar():
    p = policy()
    return [d.date().isoformat() for d in xcals.get_calendar('XNYS').sessions_in_range(
        p['price_start'], p['price_end_inclusive'])]


def audited_feature_cache(sec_sha, extractor_sha):
    """Reuse identical audited source extraction, verifying its raw documents.

    This avoids parsing the same archived tables again when only price data
    arrives. A different roster or extractor cannot use the cached features.
    """
    path = HERE / 'feature-source-audit.json'
    if not path.exists():
        return {}, None
    report_raw = path.read_bytes()
    report = json.loads(report_raw)
    if (report.get('sec_events_sha256') != sec_sha or
            report.get('extractor_sha256') != extractor_sha):
        return {}, None
    assert report['cohort_sha256'] == digest(HERE / 'sec-cohort.json')
    record = report['source_feature_snapshot']
    snapshot_path = ROOT / record['path']
    assert digest(snapshot_path) == record['sha256']
    snapshot = json.loads(snapshot_path.read_text())
    assert snapshot['sec_events_sha256'] == sec_sha and snapshot['extractor_sha256'] == extractor_sha
    assert not snapshot['errors'], 'Audited source extraction has unresolved exceptions'
    references = set()
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('file'), str) and isinstance(value.get('sha256'), str):
                references.add((value['file'], value['sha256']))
            if (isinstance(value.get('source_manifest_path'), str) and
                    isinstance(value.get('source_manifest_snapshot_sha256'), str)):
                references.add((value['source_manifest_path'], value['source_manifest_snapshot_sha256']))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(snapshot['results'])
    for filename, checksum in references:
        assert digest(ROOT / filename) == checksum, 'Cached original document changed'
    for slot_id, pair in snapshot['results'].items():
        assert pair['slot_id'] == slot_id
    return snapshot['results'], {
        'source_audit_sha256': hashlib.sha256(report_raw).hexdigest(),
        'source_feature_snapshot': record, 'verified_original_documents': len(references),
        'qualification': 'Exact frozen roster and extractor match; every referenced original document hash rechecked.',
    }


def load_prices(manifest=None, source_exceptions=None):
    """Provider raw/adjusted fields plus explicit distribution arithmetic audit.

    The adjusted factor change must equal splitFactor*(close+divCash)/close.
    This verifies internal total-return/share-unit consistency, not independently
    certified issuer cash payment availability or realized execution.
    """
    manifest = manifest if manifest is not None else json.loads((HERE / 'price-manifest.json').read_text())
    assert manifest['policy_sha256'] == POLICY_SHA
    directory_source = json.loads((HERE / 'tiingo-directory-source.json').read_text())
    directory_path = ROOT / directory_source['file']
    assert digest(directory_path) == directory_source['sha256']
    with zipfile.ZipFile(directory_path) as archive:
        directory = list(csv.DictReader(io.StringIO(archive.read('supported_tickers.csv').decode('utf-8-sig'))))
    identities = {}
    for record in directory:
        identities.setdefault(record['ticker'].upper(), set()).add(tuple(sorted(record.items())))
    exceptions_path = HERE / 'price-source-exceptions.json'
    exceptions = (source_exceptions if source_exceptions is not None else
                  json.loads(exceptions_path.read_text()) if exceptions_path.exists() else {})
    if exceptions:
        assert exceptions['policy_sha256'] == POLICY_SHA
    series, audit = {}, {}
    for ticker, rec in manifest['symbols'].items():
        if 'path' not in rec:
            audit[ticker] = {'status': rec['status'], 'rows': 0}
            continue
        path = ROOT / rec['path']
        assert digest(path) == rec['sha256']
        rows, issues = parse(path.read_bytes())
        identity_ambiguous = len(identities.get(ticker, ())) > 1
        if identity_ambiguous:
            for day in rows:
                issues.setdefault(day, []).append('MULTIPLE_PROVIDER_SECURITY_HISTORIES_SHARE_TICKER_NEEDS_IDENTITY_RESOLUTION')
        for conflict in exceptions.get('symbols', {}).get(ticker, []):
            assert conflict.get('verified_source_conflict') is True and conflict.get('source_evidence')
            assert conflict['start_date'] <= conflict['end_date']
            for day in rows:
                if conflict['start_date'] <= day <= conflict['end_date']:
                    issues.setdefault(day, []).append('ORIGINAL_SOURCE_CONFLICT: ' + conflict['reason'])
        history = sorted(rows)
        transitions = []
        for before, day in zip(history, history[1:]):
            previous, current = rows[before], rows[day]
            if min(previous['close'], previous['adjClose'], current['close'], current['adjClose']) <= 0:
                continue
            actual = (current['adjClose'] / current['close']) / (previous['adjClose'] / previous['close'])
            expected = current['splitFactor'] * (current['close'] + current['divCash']) / current['close']
            if abs(actual / expected - 1) > 1e-5:
                issues.setdefault(day, []).append('distribution_adjustment_arithmetic_mismatch')
                transitions.append(day)
        series[ticker] = {'rows': rows, 'issues': issues, 'source_sha256': rec['sha256']}
        audit[ticker] = {'status': rec['status'], 'rows': len(rows),
                         'provider_identity_ambiguous': identity_ambiguous,
                         'structurally_qualified_rows': len(rows) - len(issues),
                         'invalid_sessions': issues, 'distribution_transition_mismatches': transitions,
                         'source_sha256': rec['sha256']}
    return series, audit


def qualified_span(ticker, days, series):
    source = series.get(ticker, {'rows': {}, 'issues': {}})
    missing = [d for d in days if d not in source['rows']]
    invalid = [d for d in days if d in source['issues']]
    return not missing and not invalid, {'missing_sessions': missing, 'invalid_sessions': invalid}


def target(row, series, sessions):
    """Call for development now; evaluate frozen predictions only in a later step."""
    if not row.get('entry_date') or not row.get('exit_date'):
        return None, {'reason': 'RIGHT_CENSORED_CALENDAR'}
    i = sessions.index(row['entry_date'])
    span = sessions[i:i+21]
    assert len(span) == 21 and span[-1] == row['exit_date']
    for ticker in [row['ticker'], 'SPY']:
        good, details = qualified_span(ticker, span, series)
        if not good:
            return None, {'reason': 'UNRESOLVED_LABEL_PRICE_SPAN', 'ticker': ticker, **details}
    changes = []
    for ticker in [row['ticker'], 'SPY']:
        prices = series[ticker]['rows']
        changes.append(prices[span[-1]]['adjClose'] / prices[span[0]]['adjClose'] - 1)
    return 100 * (changes[0] - changes[1]), {'status': 'PROVIDER_TOTAL_RETURN_ARITHMETIC_QUALIFIED', 'sessions': 21}


def numeric_features(pair, previous, prior_rows, *, action_history_complete=None):
    flags = pair['flags']
    current = pair['current']
    old = pair['original_prior']
    rev = pair['comparisons']['revenue']
    eps = pair['comparisons']['diluted_eps']
    missing = {}
    growth = None
    if rev['same_current_release_comparison_eligible']:
        a, b = float(rev['current_value']), float(rev['current_release_comparable_prior_value'])
        if b > 0:
            growth = a / b - 1
        else:
            missing['revenue_yoy'] = ['NONPOSITIVE_PRIOR_REVENUE']
    else:
        missing['revenue_yoy'] = rev['missing_reasons']
    scaled_eps = None
    # Current release comparative columns share a table/basis. A detected split
    # in that statement or since period end needs a separately verified basis
    # transformation; this first pass records missing instead of guessing it.
    split_since_period = [d for d, p in prior_rows.items()
                          if d > current['period_end'] and p['splitFactor'] != 1]
    if not eps['same_current_release_comparison_eligible']:
        missing['scaled_eps_change'] = eps['missing_reasons']
    elif (flags['current_metric_currency']['diluted_eps'] != ['USD'] and
          current.get('currency_resolution', {}).get('currency') != 'USD'):
        missing['scaled_eps_change'] = ['US_DOLLAR_DENOMINATION_UNRESOLVED']
    elif action_history_complete is not True:
        missing['scaled_eps_change'] = ['PERIOD_TO_PREENTRY_ACTION_HISTORY_UNCOVERED']
    elif current['flags']['split_mentioned'] or split_since_period:
        missing['scaled_eps_change'] = ['EPS_EFFECTIVE_SHARE_BASIS_NEEDS_SOURCE_REVIEW']
    else:
        scaled_eps = (float(eps['current_value']) - float(eps['current_release_comparable_prior_value'])) / previous['close']
    return {'revenue_yoy': growth, 'scaled_eps_change': scaled_eps,
            'scope': flags.get('scope') or 'UNKNOWN',
            'fiscal_quarter': str(flags.get('fiscal_quarter_ordinal') or 'UNKNOWN'),
            'unequal_duration': float(flags['unequal_duration']),
            'accounting_transition': float(flags['accounting_transition']),
            'document_type_current': '|'.join(current['flags']['source_document_types']),
            'document_type_prior': '|'.join(old['flags']['source_document_types']),
            'log_current_document_words': math.log1p(current['narrative_words']),
            'log_prior_document_words': math.log1p(old['narrative_words']),
            'predecessor_search_coverage': str(flags.get('predecessor_search_coverage') or 'UNKNOWN')}, missing


def build():
    spec = policy()
    implementation_sha = digest(Path(__file__))
    extractor_sha = digest(HERE / 'feature_extract.py')
    cohort = json.loads((HERE / 'sec-cohort.json').read_text())
    candidates = []
    for name in ['sec-events.json', 'sec-events-current-roster.json']:
        path = HERE / name
        if path.exists():
            raw = path.read_bytes()
            content = json.loads(raw)
            if content.get('selection_sha256', digest(HERE / 'sec-cohort.json')) == digest(HERE / 'sec-cohort.json'):
                candidates.append((content.get('updated_at', ''), path, content, raw))
    if not candidates:
        raise ValueError('No SEC event checkpoint matches the current independently corrected cohort')
    _, original_sec_path, sec, sec_raw = max(candidates, key=lambda x: x[0])
    sec_sha = hashlib.sha256(sec_raw).hexdigest()
    sec_path = RAW / 'panel-source-snapshots' / ('sec-' + sec_sha + '.json')
    sec_path.parent.mkdir(parents=True, exist_ok=True)
    if sec_path.exists():
        assert sec_path.read_bytes() == sec_raw
    else:
        sec_path.write_bytes(sec_raw)
    assert sec['policy_sha256'] == cohort['policy_sha256'] == POLICY_SHA
    assert len(sec['slots']) == 1600 and len(cohort['issuers']) == 100
    sessions = calendar()
    manifest_raw = (HERE / 'price-manifest.json').read_bytes()
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    exceptions_path = HERE / 'price-source-exceptions.json'
    exceptions_raw = exceptions_path.read_bytes() if exceptions_path.exists() else b'{}'
    exceptions_sha = hashlib.sha256(exceptions_raw).hexdigest() if exceptions_path.exists() else None
    series, price_audit = load_prices(manifest=json.loads(manifest_raw), source_exceptions=json.loads(exceptions_raw))
    cached_features, cache_provenance = audited_feature_cache(sec_sha, extractor_sha)
    output, source_features = [], {}
    for slot in sec['slots']:
        row = {'event_id': slot['slot_id'], 'cik': slot['cik'], 'status': 'UNRESOLVED',
               'entry_date': None, 'exit_date': None, 'target_pp': None, 'features': {},
               'current_text': '', 'prior_text': '', 'reasons': [], 'source_status': slot['status']}
        current, prior = slot.get('current'), slot.get('prior')
        if not current:
            row['reasons'].append('NO_ORIGINAL_CURRENT_RELEASE')
            output.append(row)
            continue
        row.update(ticker=symbol(current['security']['historical_symbol']) if current['security'].get('historical_symbol') else None,
                   accession=current['accession'], filing_date=current['filing_date'],
                   acceptance_date_et=current['acceptance_eastern'][:10] if current.get('acceptance_eastern') else None,
                   security_id=slot['cik'] + ':single_common')
        if not row['acceptance_date_et']:
            row['reasons'].append('ACCEPTANCE_TIME_MISSING')
            output.append(row)
            continue
        available = max(row['filing_date'], row['acceptance_date_et'])
        index = bisect_right(sessions, available)
        if index >= len(sessions):
            row['reasons'].append('RIGHT_CENSORED_CALENDAR')
            output.append(row)
            continue
        row['entry_date'] = sessions[index]
        row['exit_date'] = sessions[index+20] if index+20 < len(sessions) else None
        if not all(slot.get('checks', {}).get(k) for k in ['current_release', 'earliest_event', 'prior_release', 'period_identity', 'identity', 'timing']):
            row['reasons'].append('ORIGINAL_SOURCE_JOIN_UNRESOLVED')
        if prior and max(prior['filing_date'], (prior.get('acceptance_eastern') or '9999')[:10]) >= row['entry_date']:
            row['reasons'].append('PRIOR_SOURCE_NOT_PUBLIC_BEFORE_ENTRY')
        pair = cached_features.get(slot['slot_id'])
        if pair is None:
            pair = extract_pair(slot)
        source_features[slot['slot_id']] = pair
        if pair['status'] != 'SOURCE_PAIR_READ_NUMERIC_COVERAGE_EXPLICIT':
            row['reasons'].extend(pair['missing_reasons'])
        if not pair['flags']['document_types_match']:
            row['reasons'].append('SOURCE_DOCUMENT_TYPE_SUBSTITUTION_UNRESOLVED')
        for role, text_role in [('current', 'current'), ('original_prior', 'original_prior')]:
            if not pair['narrative'][text_role].strip():
                row['reasons'].append(role.upper() + '_NARRATIVE_EMPTY')
            if pair[role].get('flags', {}).get('unstructured_financial_text_unresolved'):
                row['reasons'].append(role.upper() + '_FINANCIAL_TABLE_NARRATIVE_UNRESOLVED')
            if any(d.get('encoding_artifact_word_count', 0) >= 20 and
                   d.get('encoding_artifact_word_fraction', 0) >= .01
                   for d in pair[role].get('documents', [])):
                row['reasons'].append(role.upper() + '_MATERIAL_ENCODING_CORRUPTION_UNRESOLVED')
        if row['reasons']:
            output.append(row)
            continue
        # Sixty return intervals need 61 closes; liquidity uses the last 60.
        past = sessions[max(0, index-61):index]
        good, details = qualified_span(row['ticker'], past, series)
        if len(past) < 61 or not good:
            row['reasons'].append('PAST_PRICE_BASIS_OR_LOOKBACK_UNRESOLVED')
            row['past_price_audit'] = details
            output.append(row)
            continue
        bars = series[row['ticker']]['rows']
        previous = bars[past[-1]]
        median_volume = statistics.median(bars[d]['close'] * bars[d]['volume'] for d in past[-60:])
        if previous['close'] < 5 or median_volume < 2_000_000:
            row['status'] = 'INELIGIBLE'
            row['reasons'].append('PREENTRY_PRICE_OR_LIQUIDITY_BELOW_FROZEN_LIMIT')
            output.append(row)
            continue
        action_days = [d for d in sessions if pair['current']['period_end'] < d < row['entry_date']]
        action_good, action_details = qualified_span(row['ticker'], action_days, series)
        action_complete = pair['current']['period_end'] >= '2019-09-30' and action_good
        features, missing = numeric_features(pair, previous,
            {d: p for d, p in bars.items() if d < row['entry_date']},
            action_history_complete=action_complete)
        row['eps_action_history_audit'] = {'complete': action_complete, **action_details}
        returns = [bars[b]['adjClose'] / bars[a]['adjClose'] - 1 for a, b in zip(past[-21:], past[-20:])]
        features.update(prior20_total_return=previous['adjClose']/bars[past[-21]]['adjClose']-1,
                        prior60_total_return=previous['adjClose']/bars[past[0]]['adjClose']-1,
                        prior20_daily_volatility=statistics.stdev(returns),
                        log_preentry_raw_price=math.log(previous['close']),
                        log_median60_dollar_volume=math.log(median_volume),
                        known_preliminary_information=slot.get('known_preliminary_information', 'UNKNOWN'),
                        known_guidance_predecessor=float(any(e['classification']=='GUIDANCE_UPDATE' for e in slot.get('information_predecessors', []))),
                        known_accounting_predecessor=float(any(e['classification']=='ACCOUNTING_TRANSITION_PRESENTATION' for e in slot.get('information_predecessors', []))))
        row.update(status='READY', features=features, feature_missing_reasons=missing,
                   current_text=pair['narrative']['current'], prior_text=pair['narrative']['original_prior'])
        if row['entry_date'] < '2022-01-01' and row['exit_date'] and row['exit_date'] <= '2021-12-31':
            row['target_pp'], row['label_audit'] = target(row, series, sessions)
        output.append(row)
    # All evaluation target values remain masked in this development artifact.
    assert not any(r['target_pp'] is not None for r in output if (r['entry_date'] or '') >= '2022-01-01')
    panel_path = RAW / 'development-panel.json'
    feature_path = RAW / 'source-features.json'
    panel_sha = write(panel_path, output)
    feature_sha = write(feature_path, source_features)
    counts = {str(y): dict(Counter(r['status'] for r in output if (r['entry_date'] or '')[:4] == str(y))) for y in range(2020, 2024)}
    fit = [r for r in output if r['status']=='READY' and r['target_pp'] is not None and r['entry_date'][:4]=='2020' and r['exit_date'] <= '2020-12-31']
    validation = [r for r in output if r['status']=='READY' and r['target_pp'] is not None and r['entry_date'][:4]=='2021' and r['exit_date'] <= '2021-12-31']
    evaluation = [r for r in output if r['status']=='READY' and '2022-01-01' <= r['entry_date'] <= spec['last_entry_date']]
    if digest(Path(__file__)) != implementation_sha or digest(HERE / 'feature_extract.py') != extractor_sha:
        raise ValueError('Implementation changed during panel construction; rebuild the snapshot')
    report = {'policy_sha256': POLICY_SHA, 'sec_source_status': sec['status'], 'fixed_slots': len(output),
        'sec_events_path': str(sec_path.relative_to(ROOT)), 'sec_events_sha256': sec_sha,
        'sec_snapshot_copied_from': str(original_sec_path.relative_to(ROOT)), 'cohort_sha256': digest(HERE / 'sec-cohort.json'),
        'price_manifest_sha256': manifest_sha, 'panel_code_sha256': implementation_sha,
        'price_source_exceptions_sha256': exceptions_sha,
        'feature_code_sha256': extractor_sha, 'calendar_sessions': len(sessions),
        'audited_feature_cache': cache_provenance,
        'status_counts_by_entry_year': counts, 'all_slot_status_counts': dict(Counter(r['status'] for r in output)),
        'slot_reasons': dict(Counter(reason for r in output for reason in r['reasons'])),
        'fit_observations': len(fit), 'validation_observations': len(validation),
        'evaluation_preentry_observations': len(evaluation), 'evaluation_preentry_issuers': len({r['cik'] for r in evaluation}),
        'numeric_coverage_by_year': {str(y): {key: sum(r['features'].get(key) is not None for r in output if r['status']=='READY' and r['entry_date'][:4]==str(y)) for key in ['revenue_yoy','scaled_eps_change']} for y in range(2020,2024)},
        'price_sources': price_audit, 'evaluation_targets_masked': True,
        'panel': {'path': str(panel_path.relative_to(ROOT)), 'sha256': panel_sha},
        'source_features': {'path': str(feature_path.relative_to(ROOT)), 'sha256': feature_sha},
        'minimum_development_pass': len(fit)>=200 and len(validation)>=100,
        'minimum_evaluation_preentry_pass': len(evaluation)>=200 and len({r['cik'] for r in evaluation})>=40,
        'qualification': 'Coverage checkpoint only. Original-source extraction audit, action/identity review and frozen model manifest required before strategy evaluation.'}
    write(HERE / 'panel-inventory.json', report)
    return report


if __name__ == '__main__':
    result = build()
    print(json.dumps({k: result[k] for k in ['fixed_slots','fit_observations','validation_observations','evaluation_preentry_observations','evaluation_preentry_issuers','numeric_coverage_by_year']}))
