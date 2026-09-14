"""Project public ownership tables for the fixed cohort and its owners' history."""
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import zipfile

import pandas as pd

from download_sources import HERE, ROOT, RAW, POLICY_SHA, policy, atomic


def run():
    p = policy()
    m = json.loads((HERE / 'download-manifest.json').read_text())
    assert m['status'] == 'ALL_FIXED_ARCHIVES_VERIFIED'
    sources = {x['name'].removesuffix('.zip'): x for x in m['files']}
    db = sqlite3.connect(RAW / 'submission-index.sqlite')
    audit = {'policy_sha256': POLICY_SHA, 'passes': {}, 'security_return_observations_read': 0}
    existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {'owners', 'transactions', 'footnotes'} & existing, 'No implicit overwrite'

    def stream(name, columns, accept, write):
        rec = {'source_sha256': sources[name]['sha256'], 'scanned_rows': 0, 'retained_source_rows': 0}
        with zipfile.ZipFile(ROOT / sources[name]['file']) as z:
            info = z.getinfo(name + '.csv')
            assert info.file_size <= p['max_uncompressed_bytes_streamed_per_pass']
            with z.open(info) as f:
                for chunk in pd.read_csv(f, dtype=str, keep_default_na=False,
                                         usecols=columns, chunksize=100_000):
                    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['deadline_utc']):
                        raise RuntimeError('Study deadline reached')
                    rec['scanned_rows'] += len(chunk)
                    keep = accept(chunk)
                    rec['retained_source_rows'] += len(keep)
                    write(keep)
                    db.commit()
                    if rec['scanned_rows'] % 1_000_000 == 0:
                        print(json.dumps({'table': name, **rec}), flush=True)
            with z.open(name + '_errors.csv') as f:
                rec['upstream_errors'] = pd.read_csv(f, dtype=str, keep_default_na=False).to_dict('records')
        rec['status'] = 'COMPLETE_PASS'
        audit['passes'][name] = rec
        atomic(HERE / 'table-projection-audit.json', audit)

    owner_cols = ['accessionNumber', 'filingDate', 'rptOwnerCik', 'rptOwnerName',
                  'isDirector', 'isOfficer', 'isTenPercentOwner', 'isOther', 'officerTitle', 'otherText']
    db.execute('CREATE TABLE owners(accession TEXT, owner_cik TEXT, signature TEXT, payload TEXT, copies INTEGER, PRIMARY KEY(accession,owner_cik,signature))')

    def write_owners(chunk):
        records = []
        for row in chunk[owner_cols].itertuples(index=False, name=None):
            v = dict(zip(owner_cols, row))
            v.pop('filingDate')
            v['rptOwnerCik'] = v['rptOwnerCik'].strip().zfill(10)
            payload = json.dumps(v, sort_keys=True, separators=(',', ':'))
            records.append((v['accessionNumber'], v['rptOwnerCik'],
                            hashlib.sha256(payload.encode()).hexdigest(), payload, 1))
        db.executemany('INSERT INTO owners VALUES (?,?,?,?,?) ON CONFLICT(accession,owner_cik,signature) DO UPDATE SET copies=copies+1', records)

    stream('lit_reportingowner', owner_cols,
           lambda c: c[c['filingDate'].between('20180101', '20231231')], write_owners)
    db.execute('CREATE INDEX owner_cik_index ON owners(owner_cik)')
    db.execute('CREATE TABLE relevant_owners(owner_cik TEXT PRIMARY KEY)')
    # Owner candidates are selected from filings, without inspecting purchases or returns.
    db.execute('INSERT INTO relevant_owners SELECT DISTINCT o.owner_cik FROM owners o JOIN submissions s ON o.accession=s.accession WHERE s.issuer_cik IN (SELECT cik FROM cohort) AND substr(s.acceptance,1,6) BETWEEN ? AND ?', ('202112', '202311'))
    db.execute('CREATE TABLE work_accessions(accession TEXT PRIMARY KEY)')
    db.execute('INSERT OR IGNORE INTO work_accessions SELECT accession FROM owners WHERE owner_cik IN (SELECT owner_cik FROM relevant_owners)')
    db.execute('INSERT OR IGNORE INTO work_accessions SELECT accession FROM submissions WHERE issuer_cik IN (SELECT cik FROM cohort)')
    controls = json.loads((ROOT / 'research/insider-purchase-audit-2026-09-13/field-audit.json').read_text())['filings']
    db.executemany('INSERT OR IGNORE INTO work_accessions VALUES (?)', [(x['accession'],) for x in controls])
    db.commit()
    work = {r[0] for r in db.execute('SELECT accession FROM work_accessions')}
    audit['relevant_owner_count'] = db.execute('SELECT COUNT(*) FROM relevant_owners').fetchone()[0]
    audit['work_accession_count'] = len(work)
    print(json.dumps({'relevant_owners': audit['relevant_owner_count'], 'work_accessions': len(work)}), flush=True)

    db.execute('CREATE TABLE transactions(accession TEXT, row_type TEXT, table_row TEXT, signature TEXT, payload TEXT, copies INTEGER, PRIMARY KEY(accession,row_type,table_row,signature))')

    def write_transactions(chunk):
        records = []
        columns = list(chunk.columns)
        for row in chunk.itertuples(index=False, name=None):
            v = dict(zip(columns, row))
            payload = json.dumps(v, sort_keys=True, separators=(',', ':'))
            records.append((v['accessionNumber'], v['transactionType'], v['tableRow'],
                            hashlib.sha256(payload.encode()).hexdigest(), payload, 1))
        db.executemany('INSERT INTO transactions VALUES (?,?,?,?,?,?) ON CONFLICT(accession,row_type,table_row,signature) DO UPDATE SET copies=copies+1', records)

    stream('lit_nonderiv', lambda c: c not in {'URL', 'filingDate', 'filerCik'},
           lambda c: c[c['accessionNumber'].isin(work)], write_transactions)
    db.execute('CREATE TABLE footnotes(accession TEXT, note_id TEXT, signature TEXT, content TEXT, copies INTEGER, PRIMARY KEY(accession,note_id,signature))')

    def write_notes(chunk):
        records = [(a, i, hashlib.sha256(t.encode()).hexdigest(), t, 1)
                   for a,i,t in chunk[['accessionNumber','id','content']].itertuples(index=False,name=None)]
        db.executemany('INSERT INTO footnotes VALUES (?,?,?,?,?) ON CONFLICT(accession,note_id,signature) DO UPDATE SET copies=copies+1', records)

    stream('lit_footnotes', ['accessionNumber', 'id', 'content'],
           lambda c: c[c['accessionNumber'].isin(work)], write_notes)
    audit['unique_owner_records'] = db.execute('SELECT COUNT(*) FROM owners').fetchone()[0]
    audit['unique_transaction_versions'] = db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    audit['unique_footnote_versions'] = db.execute('SELECT COUNT(*) FROM footnotes').fetchone()[0]
    audit['transaction_row_conflicts'] = db.execute('SELECT COUNT(*) FROM (SELECT accession,row_type,table_row FROM transactions GROUP BY accession,row_type,table_row HAVING COUNT(*)>1)').fetchone()[0]
    audit['footnote_id_conflicts'] = db.execute('SELECT COUNT(*) FROM (SELECT accession,note_id FROM footnotes GROUP BY accession,note_id HAVING COUNT(*)>1)').fetchone()[0]
    audit['owner_role_conflicts'] = db.execute('SELECT COUNT(*) FROM (SELECT accession,owner_cik FROM owners GROUP BY accession,owner_cik HAVING COUNT(*)>1)').fetchone()[0]
    audit['status'] = 'ALL_PROJECTION_PASSES_COMPLETE'
    audit['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    db.commit()
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.close()
    atomic(HERE / 'table-projection-audit.json', audit)
    print(json.dumps({k:v for k,v in audit.items() if k != 'passes'}), flush=True)


if __name__ == '__main__':
    run()
