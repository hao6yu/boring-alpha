"""Compare the acquired bulk tables to captured SEC originals and known indexes."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
import json
import re
import sqlite3

from download_sources import HERE, ROOT, RAW, POLICY_SHA, policy, atomic


def normalize(text):
    return ' '.join(html.unescape(text or '').split())


def num(value):
    return None if value in ('', None) else format(Decimal(value).normalize(), 'f')


def run():
    policy()
    db = sqlite3.connect('file:' + str(RAW / 'submission-index.sqlite') + '?mode=ro', uri=True)
    original_path = ROOT / 'research/insider-purchase-audit-2026-09-13/field-audit.json'
    originals = json.loads(original_path.read_text())['filings']
    checks = []
    for original in originals:
        acc = original['accession']
        sub = [json.loads(x[0]) for x in db.execute('SELECT payload FROM submissions WHERE accession=?', (acc,))]
        ts = [json.loads(x[0]) for x in db.execute("SELECT payload FROM transactions WHERE accession=? AND row_type='nonDerivativeTransaction' ORDER BY CAST(table_row AS INTEGER)", (acc,))]
        owners = {x[0] for x in db.execute('SELECT DISTINCT owner_cik FROM owners WHERE accession=?', (acc,))}
        notes = {i: normalize(t) for i,t in db.execute('SELECT note_id,content FROM footnotes WHERE accession=?', (acc,))}
        extracted = [{'transaction_date': t['transactionDate'], 'code': t['transactionCode'],
                      'shares': num(t['transactionShares']), 'price': num(t['transactionPricePerShare']),
                      'acquired_disposed': t['transactionAcquiredDisposedCode'],
                      'owned_after': num(t['sharesOwnedFollowingTransaction']),
                      'ownership': t['directOrIndirectOwnership']} for t in ts]
        expected = [{k:t[k] for k in extracted[0]} for t in original['non_derivative_transactions']] if extracted else []
        checks.append({'accession': acc, 'metadata_versions': len(sub),
                       'acceptance_matches_original_index': len(sub)==1 and sub[0]['acceptanceDatetime']==datetime.fromisoformat(original['accepted_eastern']).strftime('%Y%m%d%H%M%S'),
                       'issuer_matches': len(sub)==1 and sub[0]['issuerCik'].zfill(10)==original['issuer_cik'],
                       'transaction_rows_match': extracted==expected and len(ts)==len(original['non_derivative_transactions']),
                       'owner_ids_match': owners=={o['cik'] for o in original['owners']},
                       'footnotes_match': notes=={k:normalize(v) for k,v in original['footnotes'].items()},
                       'transaction_row_count':len(ts),
                       'prior_api_timestamp_conflict_preserved':original['cached_acceptance_matches_index'] is False})
    cohort = {r[0] for r in db.execute('SELECT cik FROM cohort')}
    known = {}
    source_records, seen = [], set()
    for folder in ['equity-event-expansion-2026-09-13','equity-event-test-2026-09-10','equity-event-pilot-2026-09-10']:
        mp = ROOT / 'research' / folder / 'sec-sources.json'
        manifest = json.loads(mp.read_text())
        for url, rec in manifest['sources'].items():
            match = re.search(r'data\.sec\.gov/submissions/CIK(\d{10})', url)
            if not match or match[1] not in cohort or rec.get('status') != 200 or rec.get('file') in seen:
                continue
            path = ROOT / rec['file']; raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==rec['sha256']
            seen.add(rec['file'])
            data = json.loads(raw)
            table = data.get('filings', {}).get('recent', data)
            if 'accessionNumber' not in table:
                continue
            source_records.append({'file':rec['file'],'sha256':rec['sha256'],'url':url})
            for i, acc in enumerate(table['accessionNumber']):
                if table['form'][i] not in {'4','4/A'} or not '2018-01-01' <= table['filingDate'][i] <= '2023-12-31':
                    continue
                known[acc] = {'issuer_index_cik':match[1], 'filing_date':table['filingDate'][i], 'form':table['form'][i]}
    absent, other_issuer = [], []
    for acc,row in known.items():
        found = db.execute('SELECT issuer_cik FROM submissions WHERE accession=?',(acc,)).fetchall()
        if not found:
            absent.append({'accession':acc,**row})
        elif row['issuer_index_cik'] not in {x[0] for x in found}:
            other_issuer.append({'accession':acc,**row,'actual_bulk_issuer_ciks':[x[0] for x in found]})
    result = {'policy_sha256': POLICY_SHA, 'original_checks': checks,
              'all_original_checks_pass': all(all(r[k] for k in ['acceptance_matches_original_index','issuer_matches','transaction_rows_match','owner_ids_match','footnotes_match']) for r in checks),
              'known_cached_index_accessions': len(known), 'missing_from_bulk': absent,
              'index_cik_differs_from_actual_issuer': other_issuer, 'cached_index_sources': source_records,
              'coverage_scope':'Comparison with available historical SEC index caches, not a complete market census.',
              'security_return_observations_read': 0,
              'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    atomic(HERE / 'original-source-audit.json', result)
    print(json.dumps({'all_original_checks_pass': result['all_original_checks_pass'],
                      'original_controls':len(checks),'known_index_accessions':len(known),
                      'missing_from_bulk':len(absent),'index_issuer_differences':len(other_issuer),
                      'failed_checks':[x for x in checks if not all(x[k] for k in ['acceptance_matches_original_index','issuer_matches','transaction_rows_match','owner_ids_match','footnotes_match'])]}),flush=True)


if __name__ == '__main__':
    run()
