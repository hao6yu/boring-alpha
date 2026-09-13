#!/usr/bin/env python3
"""Apply the explicit full-release convention without resampling events."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'equity-event-pilot-2026-09-10'
SHA = '023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05'
# These are source-reviewed classifications, not inferences from filing dates.
PREDECESSOR_TYPES = {
    '0001104659-22-104870': 'PRELIMINARY_RESULTS',
    '0001493152-22-028213': 'GUIDANCE_UPDATE',
    '0001493152-23-005370': 'PRELIMINARY_RESULTS',
    '0000827187-23-000005': 'PRELIMINARY_RESULTS',
    '0001564590-23-005223': 'PRELIMINARY_SELECTED_METRICS',
    '0001650372-22-000071': 'ACCOUNTING_TRANSITION_PRESENTATION',
    '0001169561-23-000005': 'PRELIMINARY_RESULTS',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(HERE / 'policy.json') == SHA
    policy = json.loads((HERE / 'policy.json').read_text())
    assert digest(BASE / 'policy.json') == policy['original_policy_sha256']
    assert digest(BASE / 'result.json') == policy['original_result_sha256']
    assert digest(BASE / 'sec-selection.json') == policy['cohort_selection_sha256']
    original = json.loads((BASE / 'sec-events.json').read_text())
    audit = {s['slot_id']: s for s in json.loads((BASE / 'sample-audit.json').read_text())['slot_audit']}
    slots = []
    for old in original['slots']:
        current = old.get('current')
        verified = audit[old['slot_id']]
        is_full = bool(current and old['checks'].get('full_nonpreliminary_release_selection'))
        ambiguities = verified.get('preliminary_event_ambiguities', [])
        predecessors = []
        for review in verified.get('earlier_rejection_reviews', []):
            record = next((c for c in old.get('candidate_events', []) if c.get('accession') == review['accession']), {})
            kind = PREDECESSOR_TYPES[review['accession']]
            assert review.get('source_supported') is True and record
            primary = Path(record['primary_file'])
            assert primary.exists()
            predecessors.append({
                'accession': review['accession'], 'finding': review.get('finding'),
                'source_supported': review.get('source_supported'),
                'filing_date': record.get('filing_date'), 'acceptance_eastern': record.get('acceptance_eastern'),
                'release_date': record.get('release_date'), 'primary_file': record.get('primary_file'),
                'primary_url': record.get('primary_url'), 'primary_sha256': digest(primary),
                'information_type': kind,
                'explicit_preliminary_results': kind == 'PRELIMINARY_RESULTS',
                'explicit_preliminary_selected_metrics': kind == 'PRELIMINARY_SELECTED_METRICS',
                'earlier_preliminary_information': kind in {'PRELIMINARY_RESULTS', 'PRELIMINARY_SELECTED_METRICS'},
            })
        remaining_audit_failures = [f for f in verified.get('blocking_failures', [])
                                    if not (f['check'] == 'event_definition_resolved' and is_full)]
        checks = dict(old['checks'])
        checks['earliest_event'] = is_full
        slots.append({
            'slot_id': old['slot_id'], 'cik': old['cik'], 'historical_symbol': old['historical_symbol'],
            'window_start': old['window_start'], 'window_end': old['window_end'],
            'current_accession': current['accession'] if current else None,
            'selected_event_unchanged': True,
            'original_event_definition_status': verified.get('event_definition_status'),
            'event_definition_status': 'RESOLVED_UNDER_EXPLICIT_V2_FULL_RELEASE_RULE' if is_full else 'NO_VERIFIED_FULL_RELEASE',
            'checks': checks, 'preliminary_predecessors': ambiguities,
            'reviewed_information_predecessors': predecessors,
            'known_preliminary_information': 'KNOWN_YES' if any(p['earlier_preliminary_information'] for p in predecessors) else 'NONE_FOUND_IN_LIMITED_AUDITED_CANDIDATES',
            'absence_of_other_preliminary_information_verified': False,
            'first_public_earnings_information_verified': False,
            'prior_pair_source_support': verified['prior_pair_source_support'],
            'daily_proxy_success': verified['daily_proxy_success'],
            'remaining_original_audit_failures': remaining_audit_failures,
            'original_unresolved_reasons': old['unresolved_reasons'],
        })
    assert len(slots) == len({s['slot_id'] for s in slots}) == 100
    assert sum(s['checks']['earliest_event'] for s in slots) == 99
    result = {
        'policy_sha256': SHA, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'original_events_sha256': digest(BASE / 'sec-events.json'),
        'original_audit_sha256': digest(BASE / 'sample-audit.json'),
        'fixed_slots': 100, 'selected_event_changes': 0,
        'full_release_definition_resolved': sum(s['checks']['earliest_event'] for s in slots),
        'previous_policy_ambiguities_resolved': sum(bool(s['preliminary_predecessors']) and s['checks']['earliest_event'] for s in slots),
        'slots_with_known_preliminary_information': sum(s['known_preliminary_information'] == 'KNOWN_YES' for s in slots),
        'change_classification': 'Explicit exploratory policy amendment, before any strategy-return inspection. Original89/100 result remains unchanged.',
        'predecessor_search_scope': 'Original audited SEC candidates only. No claim of complete issuer-publication coverage or absence of preliminary results. Future datasets must retain coverage status.',
        'slots': slots, 'model_training_performed': False, 'strategy_returns_calculated': False,
    }
    (HERE / 'event-repair.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: result[k] for k in ['fixed_slots', 'selected_event_changes', 'full_release_definition_resolved', 'previous_policy_ambiguities_resolved']}))


if __name__ == '__main__':
    main()
