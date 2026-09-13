#!/usr/bin/env python3
"""Reconcile final availability counts without computing financial returns."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(name):
    return json.loads((HERE / name).read_text())


def digest(name):
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def main():
    policy, selection, events = read('policy.json'), read('sec-selection.json'), read('sec-events.json')
    prices, audit, inactive = read('price-joins.json'), read('sample-audit.json'), read('inactive-results.json')
    manifest, sec_sources = read('price-manifest.json'), read('sec-sources.json')
    expected = {i['cik'] + '-W' + str(w) for i in selection['issuers'] for w in range(1, 5)}
    assert len(expected) == policy['denominator'] == 100
    assert {s['slot_id'] for s in events['slots']} == expected and len(events['slots']) == 100
    assert {s['slot_id'] for s in prices['slots']} == expected and len(prices['slots']) == 100
    assert prices['events_sha256'] == digest('sec-events.json')
    assert prices['manifest_sha256'] == digest('price-manifest.json')
    assert len(manifest['requests']) <= 35 and inactive['request_attempts'] <= 5
    audit_inputs = {r['path']: r['sha256'] for r in audit['inputs']}
    for name in ['sec-events.json', 'sec-selection.json', 'price-joins.json']:
        assert audit_inputs[str((HERE / name).relative_to(ROOT))] == digest(name)
    by_price = {s['slot_id']: s for s in prices['slots']}
    by_audit = {s['slot_id']: s for s in audit['slot_audit']}
    results, reason_counts = [], Counter()
    required = ['current_release', 'prior_release', 'identity', 'timing', 'period_identity', 'earliest_event']
    for event in events['slots']:
        slot_id = event['slot_id']
        price, verified = by_price[slot_id], by_audit[slot_id]
        missing = ['sec_' + key for key in required if not event['checks'].get(key, False)]
        missing += price['unresolved_reasons']
        missing += ['independent_' + f['check'] for f in verified['blocking_failures']]
        if not verified['daily_proxy_success']:
            missing.append('independent_daily_proxy_unresolved')
        if not verified['prior_pair_source_support']:
            missing.append('independent_prior_pair_unresolved')
        missing = sorted(set(missing))
        reason_counts.update(missing)
        mechanical = (all(event['checks'].get(k, False) for k in required if k != 'earliest_event')
                      and price['price_window_success'] and verified['daily_proxy_success']
                      and verified['prior_pair_source_support'])
        results.append({'slot_id': slot_id, 'historical_symbol': event['historical_symbol'],
                        'mechanical_source_price_join_before_event_definition_gate': mechanical,
                        'fully_joined_source_and_price_window': not missing,
                        'unresolved_reasons': missing})
    counts = {
        'fixed_slots': 100,
        'actual_earnings_events': sum(bool(s.get('current')) for s in events['slots']),
        'current_release_success': sum(s['checks'].get('current_release', False) for s in events['slots']),
        'prior_release_success': sum(s['checks'].get('prior_release', False) for s in events['slots']),
        'identity_success': sum(s['checks'].get('identity', False) for s in events['slots']),
        'timing_success': sum(s['daily_proxy_success'] for s in audit['slot_audit']),
        'exact_timestamp_mismatches': sum(s['exact_timestamp_match'] is False for s in audit['slot_audit']),
        'price_window_success': sum(s['price_window_success'] for s in prices['slots']),
        'mechanical_source_price_joins_before_event_definition_gate': sum(s['mechanical_source_price_join_before_event_definition_gate'] for s in results),
        'fully_joined': sum(s['fully_joined_source_and_price_window'] for s in results),
        'unresolved_by_reason': dict(reason_counts),
    }
    global_failures = audit['global_validation_failures'] + audit.get('global_pending_inputs', [])
    source_gate = counts['fully_joined'] >= 95 and not global_failures
    inactive_gate = inactive['inactive_controls_gate'] == 'PASS'
    result = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'policy_sha256': digest('policy.json'), 'counts': counts, 'slots': results,
        'cohort': 'Corrected implementation of the frozen historical rank; initial published issuer cohort preserved separately.',
        'original_selection_preserved': 'sec-selection-initial-published-v1.json',
        'original_cohort_preserved': 'sec-events-initial-published-cohort-v1.json',
        'selection_correction': 'sec-selection-correction.json',
        'source_and_price_threshold_passed': source_gate,
        'inactive_controls_gate': inactive['inactive_controls_gate'],
        'global_validation_failures': global_failures,
        'overall_gate': 'PASS' if source_gate and inactive_gate else 'NOT_PASSED',
        'accounting_feature_measure_definitions': 'NOT_FULLY_AUDITED; document joins do not certify GAAP/non-GAAP, 13/14-week, restatement or share-basis equivalence.',
        'price_action_scope': 'Required sessions, positive finite OHLC, volume, action fields, common adjustment factor and action transition review flags; no independent full action or execution certification.',
        'requests': {'sec_attempts': len(sec_sources['attempts']), 'sec_unique_urls': len(sec_sources['sources']),
                     'tiingo_main': len(manifest['requests']), 'tiingo_inactive': inactive['request_attempts']},
        'new_paid_data_usd': 0, 'strategy_returns_calculated': False, 'model_training_performed': False,
        'inputs': {name: digest(name) for name in ['policy.json', 'sec-selection.json', 'sec-events.json',
                   'sec-sources.json', 'price-manifest.json', 'price-joins.json', 'sample-audit.json',
                   'inactive-results.json', 'price-aliases.json', 'price-validation.json',
                   'manual-period-review.json', 'root-document-review.json', 'sec-selection-correction.json']},
    }
    (HERE / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'counts': counts, 'overall_gate': result['overall_gate'], 'requests': result['requests']}, indent=2))


if __name__ == '__main__':
    main()
