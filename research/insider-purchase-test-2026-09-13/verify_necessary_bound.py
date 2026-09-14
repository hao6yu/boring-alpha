"""Independent SQL/calendar reconstruction of the decisive history witnesses."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import sqlite3

from download_sources import HERE, RAW, POLICY_SHA, policy, atomic


def run():
    policy()
    db=sqlite3.connect('file:'+str(RAW/'submission-index.sqlite')+'?mode=ro',uri=True)
    final=json.loads((HERE/'opportunity-upper-bound-mandatory-witnesses.json').read_text())
    records=json.loads((HERE/'necessary-history-witnesses.json').read_text())['witnesses']
    ledger=json.loads((RAW/'candidate-ledger.json').read_text())['rows']
    ledger={(r['accession'],r['table_row']):r for r in ledger}
    sql="""SELECT DISTINCT o.owner_cik, s.filing_date, s.acceptance,
                  json_extract(t.payload,'$.transactionDate'),
                  date(json_extract(t.payload,'$.transactionDate'))
           FROM owners o JOIN transactions t ON o.accession=t.accession
           LEFT JOIN submissions s ON t.accession=s.accession
           WHERE json_extract(t.payload,'$.transactionType')='nonDerivativeTransaction'
             AND json_extract(t.payload,'$.transactionCode') IN ('P','S')"""
    history=defaultdict(list)
    for owner,filing,accepted,literal,sql_date in db.execute(sql):
        available=max(filing,accepted[:8]) if filing and accepted and accepted[:8].isdigit() else filing or '00000000'
        normalized=sql_date.replace('-','') if sql_date else None
        if normalized and normalized>available:
            normalized=None
        history[owner].append((available,normalized))
    checked, year_checks = [], {}
    for w in records:
        row=ledger[(w['accession'],w['table_row'])]
        owner=w['owner_cik']; year=int(row['disclosure_day'][:4])
        key=(owner,year)
        if key not in year_checks:
            sets={str(y):set() for y in range(year-3,year)}
            for available,day in history[owner]:
                if available>=f'{year}0101':
                    continue
                if day is None:
                    for s in sets.values():s.update(range(1,13))
                elif day[:4] in sets:
                    sets[day[:4]].add(int(day[4:6]))
            year_checks[key]={k:sorted(v) for k,v in sets.items()}
        assert year_checks[key]==w['maximal_history_months']
        sets=[set(v) for v in year_checks[key].values()]
        if 'NONROUTINE' in w['excluded_classes']:
            assert not all(sets)
        if 'ROUTINE' in w['excluded_classes']:
            assert not set.intersection(*sets)
        sub=json.loads(db.execute('SELECT payload FROM submissions WHERE accession=?',(w['accession'],)).fetchone()[0])
        txs=[json.loads(r[0]) for r in db.execute('SELECT payload FROM transactions WHERE accession=? AND table_row=?',(w['accession'],w['table_row']))]
        assert len(txs)==1
        tx=txs[0]
        assert sub['documentType']=='4' and tx['transactionCode']=='P'
        assert tx['transactionAcquiredDisposedCode']=='A'
        assert Decimal(tx['transactionShares'])>0 and Decimal(tx['transactionPricePerShare'])>0
        assert tx['securityTitle']==w['security_title']
        persons=[json.loads(r[0]) for r in db.execute('SELECT payload FROM owners WHERE accession=?',(w['accession'],))]
        assert len(persons)==1 and persons[0]['rptOwnerCik']==owner
        assert any(persons[0][k].strip().lower() in {'1','true'} for k in ['isOfficer','isDirector'])
        assert row['status']=='CANDIDATE'
        assert sub['issuerCik'].zfill(10)==w['issuer_cik']
        assert row['disclosure_month'].replace('-','')==w['month']
        amended=db.execute("SELECT COUNT(*) FROM submissions WHERE issuer_cik=? AND document_type='4/A' AND substr(MAX(filing_date,substr(acceptance,1,8)),1,6)=?",(w['issuer_cik'],w['month'])).fetchone()[0]
        assert amended==0
        checked.append((w['issuer_cik'],w['month'],w['security_title'],w['excluded_classes']))
    # Rebuild the potential pool from the prior (more permissive) run, preserving
    # every possible class. Its source selection is verified separately below.
    current=json.loads((RAW/'optimistic-event-slots-current-rules.json').read_text())
    assert all('security_title' in r for group in current.values() for r in group), 'Rebuild class-safe current-rules pool first'
    reconstructed={}
    for group,label in [('any_classifiable','NONROUTINE'),('routine','ROUTINE')]:
        possible={(r['issuer'],r['month'],r['security_title']) for r in current[group]}
        for cik,month,title,excluded in checked:
            if label in excluded:possible.discard((cik,month,title))
        pairs={(a,b) for a,b,c in possible}
        reconstructed[label]={'issuer_months':len(pairs),'issuers':len({a for a,b in pairs}),
                              'months':len({b for a,b in pairs})}
        assert reconstructed[label]==final['nonroutine_upper_bound' if label=='NONROUTINE' else 'routine_upper_bound']
    # Show six fixed witness examples, selected without outcomes.
    examples=sorted(records,key=lambda w:hashlib.sha256((w['accession']+'|'+w['table_row']).encode()).hexdigest())[:6]
    result={'policy_sha256':POLICY_SHA,'status':'NECESSARY_HISTORY_BOUND_VERIFIED',
            'method':'Separate SQLite date parsing and per-owner calendar reconstruction; verify every compulsory current purchase against source tables, check absence of same-month issuer amendments, and reconstruct final class-specific opportunity sets.',
            'witness_rows_verified':len(records),'unique_owner_years_verified':len(year_checks),
            'reconstructed_counts':reconstructed,'examples':examples,
            'scope':'Independent computation within this task, not an external replication or population data certification.',
            'source_selection':'Original sources/checksums and eight explicit footnote reviews are shared audited inputs.',
            'security_return_observations_read':0}
    atomic(HERE/'necessary-bound-verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='examples'}),flush=True)


if __name__=='__main__':run()
