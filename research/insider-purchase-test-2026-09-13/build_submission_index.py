"""Index only filing metadata, retaining conflicting source copies; no prices."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import zipfile

import pandas as pd

from download_sources import HERE, ROOT, RAW, POLICY_SHA, policy, atomic


def run():
    p = policy()
    manifest = json.loads((HERE / 'download-manifest.json').read_text())
    source = next(x for x in manifest['files'] if x['name'] == 'lit_submission.zip')
    assert source['status'] == 'VERIFIED'
    database = RAW / 'submission-index.sqlite'
    assert not database.exists(), 'Preserve prior index; no implicit overwrite'
    db = sqlite3.connect(database)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE submissions (accession TEXT, signature TEXT, issuer_cik TEXT, '
               'acceptance TEXT, filing_date TEXT, document_type TEXT, payload TEXT, copies INTEGER, '
               'PRIMARY KEY(accession, signature))')
    columns = ['accessionNumber', 'acceptanceDatetime', 'filingDate', 'type',
               'documentType', 'issuerCIK', 'issuerCik', 'issuerTradingSymbol',
               'dateOfOriginalSubmission', 'remarks']
    total, retained = 0, 0
    bounds, types = Counter(), Counter()
    with zipfile.ZipFile(ROOT / source['file']) as z:
        member = z.getinfo('lit_submission.csv')
        assert member.file_size <= p['max_uncompressed_bytes_streamed_per_pass']
        with z.open(member) as handle:
            for chunk in pd.read_csv(handle, usecols=columns, dtype=str, keep_default_na=False,
                                     chunksize=100_000):
                if datetime.now(timezone.utc) >= datetime.fromisoformat(p['deadline_utc']):
                    raise RuntimeError('Study deadline reached')
                total += len(chunk)
                bounds.update(chunk['filingDate'].str[:4])
                chunk = chunk[chunk['filingDate'].between('20180101', '20231231')]
                chunk = chunk[chunk['documentType'].isin(['4', '4/A']) |
                              chunk['type'].isin(['4', '4/A'])]
                retained += len(chunk)
                types.update(chunk['documentType'])
                records = []
                for row in chunk[columns].itertuples(index=False, name=None):
                    item = dict(zip(columns, row))
                    payload = json.dumps(item, sort_keys=True, separators=(',', ':'))
                    sig = hashlib.sha256(payload.encode()).hexdigest()
                    cik = item['issuerCik'].strip().zfill(10)
                    records.append((item['accessionNumber'], sig, cik, item['acceptanceDatetime'],
                                    item['filingDate'], item['documentType'], payload, 1))
                db.executemany('INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?) '
                               'ON CONFLICT(accession,signature) DO UPDATE SET copies=copies+1', records)
                db.commit()
                if total % 400_000 == 0:
                    print(json.dumps({'source_rows_scanned': total, 'in_period_rows': retained}), flush=True)
        # Preserve upstream download/parser errors rather than treating silence as coverage.
        with z.open('lit_submission_errors.csv') as handle:
            errors = pd.read_csv(handle, dtype=str, keep_default_na=False).to_dict('records')
    db.execute('CREATE INDEX submissions_issuer ON submissions(issuer_cik)')
    db.commit()
    unique = db.execute('SELECT COUNT(DISTINCT accession) FROM submissions').fetchone()[0]
    conflicts = db.execute('SELECT COUNT(*) FROM (SELECT accession FROM submissions GROUP BY accession HAVING COUNT(*)>1)').fetchone()[0]
    cohort = json.loads((HERE / 'cohort.json').read_text())['issuers']
    db.execute('CREATE TABLE cohort(cik TEXT PRIMARY KEY)')
    db.executemany('INSERT INTO cohort VALUES (?)', [(r['cik'],) for r in cohort])
    selected = db.execute('SELECT payload,copies,signature FROM submissions WHERE issuer_cik IN (SELECT cik FROM cohort)').fetchall()
    rows = [{'fields': json.loads(x), 'source_copies': n, 'signature': sig} for x,n,sig in selected]
    atomic(RAW / 'cohort-submissions.json', {'policy_sha256': POLICY_SHA, 'rows': rows})
    db.commit()
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.close()
    result = {'policy_sha256': POLICY_SHA, 'source_archive_sha256': source['sha256'],
              'status': 'COMPLETE_METADATA_PASS', 'source_rows_scanned': total,
              'in_period_source_rows': retained, 'unique_accessions': unique,
              'accessions_with_distinct_source_payloads': conflicts,
              'source_year_row_counts': dict(bounds), 'in_period_form_counts': dict(types),
              'cohort_submission_versions': len(rows), 'upstream_source_errors': errors,
              'database': str(database.relative_to(ROOT)),
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'security_return_observations_read': 0}
    atomic(HERE / 'submission-index-audit.json', result)
    print(json.dumps({k:v for k,v in result.items() if k != 'upstream_source_errors'}), flush=True)


if __name__ == '__main__':
    run()
