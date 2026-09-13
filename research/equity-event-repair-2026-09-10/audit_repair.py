#!/usr/bin/env python3
"""Independent offline audit of the separate v2 cohort/event repair.

Original raw SEC hashes and prior audit bindings are rechecked. Prices are not
recalculated; qualified-price flags are reported from their source-specific audit.
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / 'equity-event-pilot-2026-09-10'
POLICY_SHA = '023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05'
ORIGINAL_AUDIT_SHA = '494df2c895b2ee2f1e1e0b4934c74af1eef9627cd587c3a234965203375275e7'
FOUR = {'0001701114-W1', '0001600422-W2', '0000827187-W2', '0001169561-W2'}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def main():
    checks = []
    def check(name, ok, slot_id=None, details=None):
        row = {'check': name, 'status': 'PASS' if ok else 'FAIL'}
        if slot_id: row['slot_id'] = slot_id
        if details is not None: row['details'] = details
        checks.append(row)
        return ok

    policy = read(HERE / 'policy.json')
    check('v2_policy_hash', digest(HERE / 'policy.json') == POLICY_SHA)
    check('original_policy_immutable', digest(OLD / 'policy.json') == policy['original_policy_sha256'])
    check('original_result_immutable', digest(OLD / 'result.json') == policy['original_result_sha256'])
    check('original_cohort_immutable', digest(OLD / 'sec-selection.json') == policy['cohort_selection_sha256'])
    check('original_audit_immutable', digest(OLD / 'sample-audit.json') == ORIGINAL_AUDIT_SHA)
    original_audit = read(OLD / 'sample-audit.json')
    original_result = read(OLD / 'result.json')
    check('original_89_result_preserved', original_result['counts']['fully_joined'] == 89 and original_result['overall_gate'] == 'NOT_PASSED')
    for rec in original_audit['inputs']:
        check('original_audit_input_immutable', digest(ROOT / rec['path']) == rec['sha256'], details=rec['path'])
    for name, sha in original_result['inputs'].items():
        check('original_result_input_immutable', digest(OLD / name) == sha, details=name)
    check('original_audit_globals_clear', not original_audit['global_validation_failures'] and not original_audit['global_pending_inputs'])
    sources = read(OLD / 'sec-sources.json')['sources']
    for url, rec in sources.items():
        if rec.get('status') == 200:
            check('original_raw_sec_immutable', digest(ROOT / rec['file']) == rec['sha256'], details=url)
    new_sources = read(HERE / 'dtss-sources.json')
    for url, rec in new_sources['sources'].items():
        check('new_raw_sec_integrity', digest(ROOT / rec['file']) == rec['sha256'], details=url)

    old_slots = {r['slot_id']: r for r in read(OLD / 'sec-events.json')['slots']}
    prior_checks = {r['slot_id']: r for r in original_audit['slot_audit']}
    earliest_checks = {r['slot_id']: r for r in original_audit['checks'] if r['check'] == 'earliest_under_collector_full_release_convention'}
    repair = read(HERE / 'event-repair.json')
    new_slots = {r['slot_id']: r for r in repair['slots']}
    check('exact_fixed_100_slots', len(repair['slots']) == len(new_slots) == 100 and set(new_slots) == set(old_slots))
    check('25_issuers_four_slots', len(Counter(r['cik'] for r in repair['slots'])) == 25 and set(Counter(r['cik'] for r in repair['slots']).values()) == {4})
    check('event_repair_policy_binding', repair['policy_sha256'] == POLICY_SHA)
    check('event_repair_original_binding', repair['original_events_sha256'] == digest(OLD / 'sec-events.json') and repair['original_audit_sha256'] == ORIGINAL_AUDIT_SHA)
    check('no_training_or_returns', repair['model_training_performed'] is False and repair['strategy_returns_calculated'] is False)
    check('no_reported_event_changes', repair['selected_event_changes'] == 0)
    check('four_explicit_definition_repairs', repair['previous_policy_ambiguities_resolved'] == 4)

    original_prices = {r['slot_id']: r for r in read(OLD / 'price-joins.json')['slots']}
    ptn = read(HERE / 'ptn-qualification.json')
    ptn_slots = {r['slot_id']: r for r in ptn['slots']}
    check('PTN_exact_four_fixed_slots', set(ptn_slots) == {f'0000911216-W{i}' for i in range(1, 5)})
    check('PTN_policy_binding', ptn['policy_sha256'] == POLICY_SHA)
    for key in ['evidence', 'observations', 'source_manifest']:
        rec = ptn[key]
        check('PTN_artifact_binding', digest(ROOT / rec['file']) == rec['sha256'], details=key)
    ptn_manifest = read(ROOT / ptn['source_manifest']['file'])
    check('PTN_no_paid_or_reserved_prices', ptn_manifest['new_paid_cost_usd'] == 0 and ptn_manifest['no_reserved_period_prices'] is True)
    for rec in ptn_manifest['requests']:
        if rec.get('file') and rec.get('sha256'):
            check('PTN_archived_response_integrity', digest(ROOT / rec['file']) == rec['sha256'], details=rec['file'])
    check('PTN_coverage_not_reclassified_raw', not any(r['qualified_price_window_success'] for r in ptn_slots.values()) and ptn['volume_basis_verified'] is False and ptn['complete_subsequent_actions_verified'] is False)
    dtss = read(HERE / 'dtss-repair.json')
    check('DTSS_policy_binding', dtss['policy_sha256'] == POLICY_SHA)
    check('DTSS_original_source_binding', dtss['original_events_sha256'] == digest(OLD / 'sec-events.json') and dtss['original_source_manifest_sha256'] == digest(OLD / 'sec-sources.json'))
    check('DTSS_failure_preserved', {r['slot_id'] for r in dtss['slots']} == {'0001631282-W1', '0001631282-W2'} and all(r['prior_release'] is None and not r['repaired'] for r in dtss['slots']))
    check('DTSS_W3_preserved', dtss['preserved_no_current_slot']['slot_id'] == '0001631282-W3' and old_slots['0001631282-W3'].get('current') is None)

    slot_audit = []
    for sid, row in new_slots.items():
        old = old_slots[sid]
        verified = prior_checks[sid]
        current = old.get('current')
        current_acc = current['accession'] if current else None
        check('identity_and_window_unchanged', all(row[k] == old[k] for k in ['cik', 'historical_symbol', 'window_start', 'window_end']), sid)
        check('selected_original_accession_unchanged', row['current_accession'] == current_acc, sid)
        if current:
            first = earliest_checks[sid]
            check('independently_verified_first_full_release', first['status'] == 'PASS' and first['details']['qualifying_in_order'][0] == current_acc and not first['details']['unresolved_candidates'], sid)
        check('only_earliest_gate_may_change', all(row['checks'].get(k) == v for k, v in old['checks'].items() if k != 'earliest_event'), sid)
        check('full_release_gate_matches_evidence', row['checks'].get('earliest_event') == bool(current and old['checks'].get('full_nonpreliminary_release_selection')), sid)
        check('timing_and_prior_support_unchanged', row['daily_proxy_success'] == verified['daily_proxy_success'] and row['prior_pair_source_support'] == verified['prior_pair_source_support'], sid)
        expected_failures = [r for r in verified['blocking_failures'] if not (r['check'] == 'event_definition_resolved' and sid in FOUR)]
        check('no_other_original_block_removed', row['remaining_original_audit_failures'] == expected_failures, sid)
        check('old_preliminary_ambiguities_retained', row['preliminary_predecessors'] == verified.get('preliminary_event_ambiguities', []), sid)
        check('no_first_information_or_absence_claim', row['first_public_earnings_information_verified'] is False and row['absence_of_other_preliminary_information_verified'] is False, sid)
        check('bounded_preliminary_state', row['known_preliminary_information'] in {'KNOWN_YES', 'NONE_FOUND_IN_LIMITED_AUDITED_CANDIDATES', 'UNKNOWN'}, sid)
        reviews = {r['accession']: r for r in row['reviewed_information_predecessors']}
        check('all_audited_predecessors_preserved', set(reviews) == {r['accession'] for r in verified.get('earlier_rejection_reviews', [])}, sid)
        for review in verified.get('earlier_rejection_reviews', []):
            candidate = next(c for c in old['candidate_events'] if c['accession'] == review['accession'])
            got = reviews.get(review['accession'], {})
            check('predecessor_provenance_unchanged', all(got.get(k) == candidate.get(k) for k in ['filing_date', 'acceptance_eastern', 'release_date', 'primary_file']) and got.get('source_supported') == review['source_supported'], sid, review['accession'])
            check('predecessor_raw_hash_and_url', got.get('primary_url') == candidate.get('primary_url') and got.get('primary_sha256') == digest(ROOT / candidate['primary_file']), sid, review['accession'])
        if sid in FOUR or sid == '0000101382-W3':
            check('known_preliminary_information_not_absent', row['known_preliminary_information'] == 'KNOWN_YES', sid)
        if sid == '0001631282-W3':
            check('missing_current_not_admitted', not row['checks'].get('earliest_event') and not row['daily_proxy_success'], sid)
        blockers = []
        for key in ['current_release', 'prior_release', 'identity', 'timing', 'period_identity', 'earliest_event']:
            if not row['checks'].get(key): blockers.append('sec_' + key)
        blockers.extend('independent_' + r['check'] for r in expected_failures)
        if not row['daily_proxy_success']: blockers.append('independent_daily_proxy_unresolved')
        if not row['prior_pair_source_support']: blockers.append('independent_prior_pair_unresolved')
        event_ready = not blockers
        price = original_prices[sid]['price_window_success']
        coverage = price
        if sid in ptn_slots:
            price = ptn_slots[sid]['qualified_price_window_success']
            coverage = ptn_slots[sid]['source_coverage_success']
        if not price: blockers.append('qualified_price_window_unavailable')
        independent_failures = [r['check'] for r in checks if r.get('slot_id') == sid and r['status'] == 'FAIL']
        blockers.extend(independent_failures)
        slot_audit.append({'slot_id': sid, 'current_accession': current_acc,
                           'current_release_date': current.get('release_date') if current else None,
                           'current_filing_date': current.get('filing_date') if current else None,
                           'entry_session': verified.get('expected_entry_session'),
                           'daily_proxy_success': verified['daily_proxy_success'],
                           'exact_timestamp_match_warning': verified.get('exact_timestamp_match') is False,
                           'event_source_ready_under_v2': event_ready,
                           'price_source_coverage': coverage, 'qualified_price_window': price,
                           'blocking_failures': sorted(set(blockers)), 'combined_qualified': not blockers})

    failures = [r for r in checks if r['status'] == 'FAIL']
    inputs = {name: digest(HERE / name) for name in ['policy.json', 'event-repair.json', 'feature-contract.md', 'dtss-repair.json', 'dtss-sources.json', 'ptn-qualification.json', 'inactive-repair.json']}
    result = {
        'schema': 'independent-equity-event-repair-audit-v2', 'policy_sha256': POLICY_SHA,
        'created_utc': datetime.now(timezone.utc).isoformat(), 'audit_script_sha256': digest(Path(__file__)),
        'inputs': inputs, 'checks': checks, 'check_counts': dict(Counter(r['status'] for r in checks)),
        'global_validation_failures': [r for r in failures if not r.get('slot_id')],
        'slot_validation_failures': [r for r in failures if r.get('slot_id')],
        'counts': {'fixed_slots': 100, 'unchanged_selected_originals': sum(r['current_accession'] is not None for r in slot_audit),
                   'event_source_ready_under_v2': sum(r['event_source_ready_under_v2'] for r in slot_audit),
                   'qualified_price_windows': sum(r['qualified_price_window'] for r in slot_audit),
                   'source_price_coverage_windows': sum(r['price_source_coverage'] for r in slot_audit),
                   'combined_qualified': sum(r['combined_qualified'] for r in slot_audit),
                   'original_combined_qualified_unchanged': 89},
        'status': 'VALIDATION_FAILED' if failures else 'REPAIR_AUDIT_VALID',
        'slot_audit': slot_audit,
        'feature_contract_review': {'reviewed_sha256': inputs['feature-contract.md'],
                                    'result': 'No concrete causal or source-basis blocker found in the extraction specification. Actual numerical fields are not extracted or certified.',
                                    'limits': 'Historical cohort is an availability audit, not a performance universe; any later model experiment still needs a registered point-in-time universe and execution/evaluation rules.'},
        'scope_limits': ['Qualified-price states are inherited from the existing source-specific audits; this script does not independently reconstruct OHLC or calculate investment returns.',
                         'Inactive treatment is separately reviewed; this cohort/event audit does not turn declared cash-lock or OTC marking conventions into observed execution.',
                         'The four original policy failures remain in the unchanged original report; v2 defines a separate exploratory target.',
                         'Known predecessor review has limited archived coverage and never establishes the first public earnings information.'],
        'network_requests': 0, 'prices_recalculated': False, 'strategy_returns_calculated': False,
    }
    path = HERE / 'repair-audit.json'
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    (HERE / 'repair-audit.json.sha256').write_text(digest(path) + '  repair-audit.json\n')
    print(json.dumps({k: result[k] for k in ['status', 'counts', 'check_counts', 'global_validation_failures', 'slot_validation_failures']}, indent=2))

if __name__ == '__main__':
    main()
