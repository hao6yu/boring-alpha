#!/usr/bin/env python3
"""Reconcile the frozen repair evidence offline, without calculating returns."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'equity-event-pilot-2026-09-10'
POLICY_SHA = '023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    policy = read(HERE / 'policy.json')
    assert digest(HERE / 'policy.json') == POLICY_SHA
    assert digest(BASE / 'result.json') == policy['original_result_sha256']
    original = read(BASE / 'result.json')
    for name, sha in original['inputs'].items():
        assert digest(BASE / name) == sha, name
    events = read(HERE / 'event-repair.json')
    prices = {s['slot_id']: s for s in read(BASE / 'price-joins.json')['slots']}
    alternative = read(HERE / 'ptn-qualification.json')
    alt_slots = {s['slot_id']: s for s in alternative['slots']}
    audit = read(HERE / 'repair-audit.json')
    audited = {s['slot_id']: s for s in audit['slot_audit']}
    inactive = read(HERE / 'inactive-repair.json')
    dtss = read(HERE / 'dtss-repair.json')
    assert not audit['global_validation_failures']
    assert not audit['slot_validation_failures']
    for name, sha in audit['inputs'].items():
        assert digest(HERE / name) == sha, name
    for packet in [events, alternative, inactive, dtss, audit]:
        assert packet['policy_sha256'] == POLICY_SHA
    original_slots = {s['slot_id']: s for s in original['slots']}
    slots = []
    required = ['current_release', 'earliest_event', 'identity', 'period_identity', 'prior_release', 'timing']
    for event in events['slots']:
        sid = event['slot_id']
        source_ok = (all(event['checks'].get(k, False) for k in required)
                     and event['daily_proxy_success'] and event['prior_pair_source_support']
                     and not event['remaining_original_audit_failures'])
        price_ok = prices[sid]['price_window_success'] or alt_slots.get(sid, {}).get('qualified_price_window_success', False)
        coverage_ok = prices[sid]['price_window_success'] or alt_slots.get(sid, {}).get('source_coverage_success', False)
        combined = bool(source_ok and price_ok)
        assert source_ok == audited[sid]['event_source_ready_under_v2'], sid
        assert price_ok == audited[sid]['qualified_price_window'], sid
        assert combined == audited[sid]['combined_qualified'], sid
        slots.append({
            'slot_id': sid, 'symbol': event['historical_symbol'],
            'current_accession': event['current_accession'],
            'event_source_ready': bool(source_ok), 'qualified_price_window': bool(price_ok),
            'price_source_coverage': bool(coverage_ok), 'combined_qualified': combined,
            'known_preliminary_information': event['known_preliminary_information'],
            'blocking_failures': audited[sid]['blocking_failures'],
            'alternative_price_unresolved_reasons': alt_slots.get(sid, {}).get('unresolved_reasons', []),
        })
    assert set(original_slots) == set(audited) == {s['slot_id'] for s in slots}
    counts = {
        'fixed_slots': len(slots),
        'original_combined_qualified': original['counts']['fully_joined'],
        'repaired_combined_qualified': sum(s['combined_qualified'] for s in slots),
        'event_source_ready': sum(s['event_source_ready'] for s in slots),
        'qualified_price_windows': sum(s['qualified_price_window'] for s in slots),
        'price_source_coverage_windows': sum(s['price_source_coverage'] for s in slots),
        'full_current_releases': sum(s['checks'].get('current_release', False) for s in events['slots']),
        'original_prior_release_matches': sum(s['checks'].get('prior_release', False) for s in events['slots']),
        'prior_policy_ambiguities_resolved': events['previous_policy_ambiguities_resolved'],
        'selected_event_changes': events['selected_event_changes'],
        'known_preliminary_information_slots': events['slots_with_known_preliminary_information'],
        'required_combined': 95,
        'remaining_failed_slots': sum(not s['combined_qualified'] for s in slots),
    }
    assert counts['repaired_combined_qualified'] == audit['counts']['combined_qualified']
    source_gate = counts['repaired_combined_qualified'] >= counts['required_combined']
    inactive_gate = inactive['decision']['defensible_inactive_treatment_gate'] == 'PASS_FOR_DECLARED_LEDGER_POLICY'
    finished = datetime.now(timezone.utc)
    started = datetime.fromisoformat(policy['started_at'].replace('Z', '+00:00'))
    deadline = datetime.fromisoformat(policy['deadline_utc'].replace('Z', '+00:00'))
    input_names = [
        'policy.json', 'event-repair.json', 'feature-contract.md', 'accounting-examples.json',
        'ptn-qualification.json', 'ptn-evidence.json', 'ptn-source-manifest.json',
        'dtss-repair.json', 'dtss-sources.json', 'inactive-repair.json',
        'source-backed-ledger-policy.md', 'repair-audit.json',
    ]
    result = {
        'policy_sha256': POLICY_SHA, 'created_utc': finished.isoformat(),
        'elapsed_minutes_at_synthesis': round((finished - started).total_seconds() / 60, 2),
        'completed_within_budget': finished <= deadline,
        'counts': counts, 'inputs': {n: digest(HERE / n) for n in input_names},
        'original_inputs_verified_unchanged': original['inputs'],
        'original_result_sha256': digest(BASE / 'result.json'),
        'source_and_price_threshold_passed': source_gate,
        'inactive_ledger_policy_passed': inactive_gate,
        'inactive_scope': inactive['decision']['scope'],
        'overall_data_gate': 'PASS' if source_gate and inactive_gate else 'FAIL_NOT_READY_FOR_TRAINING',
        'interpretation': 'Four admissions result from an explicit exploratory event-rule amendment. No source gap was repaired to qualification. This is a data-readiness failure, not evidence about strategy profitability.',
        'future_model_blockers': inactive['decision']['future_model_blockers'] + [
            'Point-in-time performance universe and chronological training/evaluation protocol remain unspecified.',
            'Feature contract and three illustrative source extractions do not certify full-sample numerical features.',
            'The original Q3-2023-selected availability cohort cannot be reused as a historical performance universe.',
        ],
        'next_decision': 'Stop free-source repair and model work here. Reopen the same fixed-cohort gate only for a demonstrably better raw-price/corporate-action source or independently recovered original DTSS releases. Do not replace issuers or lower95/100. A small PTN qualification sample is the concrete procurement target; no purchase or vendor coverage is assumed.',
        'requests': {
            'new_sec_index_requests': dtss['new_sec_requests'],
            'ptn_public_source_attempts': len(read(HERE / 'ptn-source-manifest.json')['requests']),
            'new_tiingo_requests': 0,
            'inactive_evidence': inactive['network_summary'],
            'note': 'Web research reads are separate from the three SEC index fetches and ten PTN source attempts; no combined billable-call count is asserted.',
        },
        'new_paid_data_usd': 0, 'model_training_performed': False,
        'strategy_returns_calculated': False, 'reserved_equity_strategy_prices_opened': False,
        'corporate_action_metadata_after_2023': 'PTN split announcement only; no 2024–2025 price history.',
        'global_validation_failures': [], 'slots': slots,
        'script_sha256': digest(Path(__file__)),
    }
    output = HERE / 'result.json'
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    (HERE / 'result.json.sha256').write_text(digest(output) + '  result.json\n')
    print(json.dumps({k: result[k] for k in ['counts', 'overall_data_gate', 'completed_within_budget', 'elapsed_minutes_at_synthesis']}))


if __name__ == '__main__':
    main()
