#!/usr/bin/env python3
"""Record the bounded DTSS source-search result; offline, no values or prices."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / 'equity-event-pilot-2026-09-10'
POLICY_SHA = '023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert digest(HERE / 'policy.json') == POLICY_SHA
    sources = json.loads((OLD / 'sec-sources.json').read_text())
    url = 'https://data.sec.gov/submissions/CIK0001631282.json'
    source = sources['sources'][url]
    assert digest(ROOT / source['file']) == source['sha256']
    data = json.loads((ROOT / source['file']).read_text())
    recent = data['filings']['recent']
    assert data['filings']['files'] == [], 'Unexamined historical metadata pages'
    filings = []
    for i, date in enumerate(recent['filingDate']):
        if '2021-10-01' <= date <= '2022-03-31':
            filings.append({key: recent[key][i] for key in
                            ('accessionNumber', 'filingDate', 'reportDate', 'form', 'items', 'primaryDocument')})
    assert not any(r['form'] in ('8-K', '6-K') for r in filings)
    inspection = json.loads((HERE / 'dtss-index-inspection.json').read_text())
    assert inspection['policy_sha256'] == POLICY_SHA
    assert inspection['plan_sha256'] == digest(HERE / 'dtss-inspection-plan.json')
    for index in inspection['indices']:
        assert digest(ROOT / index['file']) == index['sha256']
        types = [r[3] for r in index['document_rows'] if len(r) >= 4]
        assert not any(t.startswith('EX-99') for t in types)
    originals = {s['slot_id']: s for s in json.loads((OLD / 'sec-events.json').read_text())['slots']}
    slots = []
    for w, end in [(1, '2021-09-30'), (2, '2021-12-31')]:
        slot_id = f'0001631282-W{w}'
        current = originals[slot_id]['current']
        assert not originals[slot_id].get('prior')
        slots.append({'slot_id': slot_id, 'current_accession': current['accession'],
                      'current_filing_date': current['filing_date'],
                      'current_release_date': current['release_date'],
                      'required_prior_period_end': end, 'prior_release': None,
                      'repaired': False, 'blocking': True,
                      'status': 'UNRESOLVED_ORIGINAL_PRIOR_RELEASE_NOT_RECOVERED'})
    assert not originals['0001631282-W3'].get('current')
    result = {
        'policy_sha256': POLICY_SHA, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'original_events_sha256': digest(OLD / 'sec-events.json'),
        'original_result_sha256': digest(OLD / 'result.json'),
        'original_source_manifest_sha256': digest(OLD / 'sec-sources.json'),
        'source_manifest_sha256': digest(HERE / 'dtss-sources.json'),
        'inspection_sha256': digest(HERE / 'dtss-index-inspection.json'),
        'status': 'NO_QUALIFIED_REPAIR_WITHIN_TARGETED_SOURCE_SEARCH',
        'submissions_source': source, 'submissions_url': url,
        'submissions_historical_pages': data['filings']['files'],
        'inspected_metadata_window': ['2021-10-01', '2022-03-31'],
        'filings_in_window': filings,
        'original_8k_6k_count_in_window': 0,
        'inspected_index_findings': [dict(accession=r['accession'], url=r['url'], file=r['file'],
                                        sha256=r['sha256'], finding='No separate press-release exhibit listed; reports/certifications/XBRL or registration amendment and graphics only.')
                                      for r in inspection['indices']],
        'slots': slots,
        'preserved_no_current_slot': {'slot_id': '0001631282-W3', 'status': 'NO_CURRENT_ORIGINAL', 'blocking': True},
        'original_result_unchanged': True,
        'limitations': [
            'A bounded unsuccessful recovery does not establish that no public prior release ever existed.',
            'Only the specified original filing indexes were newly fetched; financial statement values were not substituted for an original earnings release.',
            'The complete cached submission listing supplies filing metadata; it is not an exhaustive text search of every historical attachment.',
            'Two SEC-domain search-engine queries returned unrelated issuers and supplied no probative DTSS evidence; no result was accepted.',
            'A later website copy without verified original availability was not used.',
        ],
        'new_sec_requests': len(json.loads((HERE / 'dtss-sources.json').read_text())['attempts']),
        'paid_requests': 0, 'prices_read': False, 'strategy_returns_calculated': False,
    }
    path = HERE / 'dtss-repair.json'
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    (HERE / 'dtss-repair.json.sha256').write_text(digest(path) + '  dtss-repair.json\n')
    print(json.dumps({'status': result['status'], 'unrepaired_prior_slots': len(slots), 'sha256': digest(path)}))

if __name__ == '__main__':
    main()
