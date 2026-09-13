"""Snapshot actual SEC-only extraction coverage; never imports price/model code."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from feature_extract import extract_pair

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 'BA-SEC-feature-cell-audit-v1'


def inherited_features(events):
    """Reuse exact old slots and byte-identical extraction, with raw hash checks."""
    old = HERE.parent/'equity-event-test-2026-09-10'
    assert digest((HERE/'feature_extract.py').read_bytes()) == digest((old/'feature_extract.py').read_bytes())
    inheritance = json.loads((HERE/'inherited-evidence.json').read_text())
    audit_record = inheritance['original_feature_audit']
    audit_raw = (ROOT/audit_record['path']).read_bytes()
    assert digest(audit_raw) == audit_record['sha256']
    audit = json.loads(audit_raw)
    snapshot_record = audit['source_feature_snapshot']
    snapshot_raw = (ROOT/snapshot_record['path']).read_bytes()
    assert digest(snapshot_raw) == snapshot_record['sha256']
    snapshot = json.loads(snapshot_raw)
    assert not snapshot['errors'] and snapshot['extractor_sha256'] == digest((HERE/'feature_extract.py').read_bytes())
    original = inheritance['original_slots']
    original_raw = (ROOT/original['path']).read_bytes()
    assert digest(original_raw) == original['sha256'] == snapshot['sec_events_sha256']
    oldslots = {r['slot_id']:r for r in json.loads(original_raw)['slots']}
    current = {r['slot_id']:r for r in events['slots']}
    assert all(current[k] == row for k,row in oldslots.items())
    references = set()
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('file'), str) and isinstance(value.get('sha256'), str):
                references.add((value['file'],value['sha256']))
            if isinstance(value.get('source_manifest_path'), str) and isinstance(value.get('source_manifest_snapshot_sha256'), str):
                references.add((value['source_manifest_path'],value['source_manifest_snapshot_sha256']))
            for child in value.values():visit(child)
        elif isinstance(value, list):
            for child in value:visit(child)
    visit(snapshot['results'])
    for filename, checksum in references:
        assert digest((ROOT/filename).read_bytes()) == checksum, 'Inherited feature source changed'
    assert all(k in oldslots and value['slot_id']==k for k,value in snapshot['results'].items())
    return snapshot['results'], {'original_audit':audit_record,'original_snapshot':snapshot_record,
        'raw_references_verified':len(references),'unchanged_slots_verified':len(oldslots),
        'scope':'Identical source records and identical extractor; prior reviewed financial cells remain prior evidence.'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(obj, indent=2, sort_keys=True) + '\n').encode()
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_bytes(raw)
    tmp.replace(path)
    return digest(raw)


def main():
    source_path = HERE/'sec-events-current-roster.json'
    if not source_path.exists():
        source_path = HERE/'sec-events.json'
    raw = source_path.read_bytes()
    events = json.loads(raw)
    cohort_raw = (HERE/'sec-cohort.json').read_bytes()
    cohort = json.loads(cohort_raw)
    assert events['selection_sha256'] == digest(cohort_raw), 'Current SEC roster checksum mismatch'
    assert len(cohort['issuers']) == 200 and len(events['slots']) == 3200
    assert {s['cik'] for s in events['slots']} == {i['cik'] for i in cohort['issuers']}
    if events.get('issuers_completed', 0) < 4:
        raise SystemExit('Wait for at least4 completed issuer blocks; no sampling of a trivial checkpoint.')
    extractor_hash = digest((HERE/'feature_extract.py').read_bytes())
    # The producer updates its projection atomically; preserve the exact bytes
    # read for this audit as well as the derived feature evidence snapshot.
    event_snapshot_path = ROOT/'data/snapshots/equity-event-expansion-2026-09-13/feature-audit-snapshots'/f'{digest(raw)}-sec-events.json'
    event_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if event_snapshot_path.exists():
        assert event_snapshot_path.read_bytes() == raw
    else:
        temporary = event_snapshot_path.with_suffix('.json.tmp')
        temporary.write_bytes(raw)
        temporary.replace(event_snapshot_path)
    results, inheritance = inherited_features(events)
    inherited_ids = set(results)
    errors = []
    statuses = Counter()
    for slot in events['slots']:
        statuses[slot['status']] += 1
        if slot.get('status') == 'PENDING_COLLECTION' or not slot.get('current'):
            continue
        assert slot['current']['filing_date'] < '2024-01-01'
        if slot.get('prior'):
            assert slot['prior']['filing_date'] < '2024-01-01'
        if slot['slot_id'] in inherited_ids:
            continue
        try:
            results[slot['slot_id']] = extract_pair(slot)
        except Exception as exc:
            errors.append({'slot_id': slot['slot_id'], 'error': type(exc).__name__, 'message': str(exc)})
    assert digest((HERE/'feature_extract.py').read_bytes()) == extractor_hash
    counts = {}
    for year in range(2020, 2024):
        slots = [s for s in events['slots'] if f'-{year}Q' in s['slot_id']]
        extracted = [results[s['slot_id']] for s in slots if s['slot_id'] in results]
        counts[str(year)] = {
            'registered_slots': len(slots), 'pending_collection_slots': sum(s['status']=='PENDING_COLLECTION' for s in slots),
            'current_releases_available': sum(bool(s.get('current')) for s in slots),
            'original_prior_releases_available': sum(bool(s.get('prior')) for s in slots),
            'source_pairs_read': sum(r['status']=='SOURCE_PAIR_READ_NUMERIC_COVERAGE_EXPLICIT' for r in extracted),
            'gaap_revenue_comparisons_parsed': sum(r['comparisons']['revenue']['same_current_release_comparison_eligible'] for r in extracted),
            'gaap_eps_comparisons_parsed_before_currency_and_share_price_gate': sum(r['comparisons']['diluted_eps']['same_current_release_comparison_eligible'] for r in extracted),
            'named_usd_eps_comparisons_before_share_price_gate': sum(r['comparisons']['diluted_eps']['same_current_release_comparison_eligible'] and r['flags']['current_metric_currency']['diluted_eps']==['USD'] for r in extracted),
            'regulatory_inferred_usd_eps_comparisons_before_share_price_gate': sum(r['comparisons']['diluted_eps']['same_current_release_comparison_eligible'] and r['current'].get('currency_resolution', {}).get('method')=='REGULATORY_USD_INFERENCE' for r in extracted),
            'total_resolved_usd_eps_comparisons_before_share_price_gate': sum(r['comparisons']['diluted_eps']['same_current_release_comparison_eligible'] and r['current'].get('currency_resolution', {}).get('currency')=='USD' for r in extracted),
            'document_type_mismatches': sum(not r['flags']['document_types_match'] for r in extracted),
            'unstructured_financial_text_flags': sum(any(r[k].get('flags',{}).get('unstructured_financial_text_unresolved',False) for k in ('current','original_prior')) for r in extracted),
            'material_encoding_flags_under_root_rule': sum(any(d['encoding_artifact_word_count'] >=20 and d['encoding_artifact_word_fraction'] >=.01 for k in ('current','original_prior') for d in r[k].get('documents',[])) for r in extracted),
            'numeric_missing_reasons': dict(Counter(reason for r in extracted for c in r['comparisons'].values() for reason in c['missing_reasons']))}
    samples = []
    for year in range(2020, 2024):
        ranked = sorted((r for sid,r in results.items() if f'-{year}Q' in sid and sid not in inherited_ids),
                        key=lambda r:digest((SEED+'|'+r['slot_id']).encode()))
        for metric in ('revenue','diluted_eps'):
            eligible = [r for r in ranked if r['comparisons'][metric]['same_current_release_comparison_eligible']][:2]
            for r in eligible:
                current = r['current']['metrics'][metric]['current']
                prior = r['current']['metrics'][metric]['comparable_prior']
                samples.append({'slot_id':r['slot_id'],'metric':metric,'scope':r['flags']['scope'],
                                'current_value':current['value'],'current_release_comparable_prior_value':prior['value'],
                                'current_evidence':current['evidence'], 'comparable_prior_evidence':prior['evidence'],
                                'review_status':'SELECTED_FOR_SOURCE_CELL_REVIEW'})
    snapshot_path = ROOT/'data/snapshots/equity-event-expansion-2026-09-13/feature-audit-snapshots'/f'{digest(raw)}.json'
    snapshot_sha = save(snapshot_path, {'sec_events_sha256':digest(raw),'extractor_sha256':extractor_hash,'results':results,'errors':errors})
    report = {'schema':'earnings-new-source-audit-v1','created_at':datetime.now(timezone.utc).isoformat(),
              'status':'PARTIAL_SOURCE_ONLY_EXTRACTION_AUDIT' if any(s['status']=='PENDING_COLLECTION' for s in events['slots']) else 'SOURCE_ONLY_EXTRACTION_AUDIT',
              'sec_events_path':str(source_path.relative_to(ROOT)), 'sec_events_sha256':digest(raw),
              'sec_events_snapshot_path':str(event_snapshot_path.relative_to(ROOT)),
              'cohort_sha256':digest(cohort_raw),'sec_collection_status':events['status'],'issuers_completed':events.get('issuers_completed'),
              'registered_slot_count':len(events['slots']),'source_slot_statuses':dict(statuses),
              'new_extraction_coverage_by_year':counts,'extractor_sha256':extractor_hash,
              'audit_script_sha256':digest(Path(__file__).read_bytes()),'extraction_errors':errors,
              'sample_selection_rule':f'Per calendar-slot year and metric, first2 successfully parsed NEW-company comparisons in SHA256({SEED}|slot_id) order; independent of prices/outcomes. This partial snapshot sample is not a population accuracy estimate.',
              'inherited_feature_cache':inheritance,'inherited_extracted_slots':len(inherited_ids),'new_extracted_slots':len(results)-len(inherited_ids),
              'source_cell_samples':samples,'source_feature_snapshot':{'path':str(snapshot_path.relative_to(ROOT)),'sha256':snapshot_sha},
              'scope':'SEC originals only. Source loading, numerical extraction, clean narrative, predecessor coverage and final admission are separate checks. Missing numerical values are not filled with zeros.',
              'no_prices_or_outcomes_read':True}
    path=HERE/'feature-source-audit.json'
    checksum=save(path,report)
    save(HERE/'feature-audit-history'/f'{digest(raw)}-{extractor_hash}.json',report)
    print(json.dumps({'report':str(path.relative_to(ROOT)),'sha256':checksum,'completed_issuers':events.get('issuers_completed'),
                      'extracted_slots':len(results),'errors':errors,'samples':len(samples),'by_year':counts}))


if __name__=='__main__':
    main()
