"""Replay general extraction across all cohort slots, before any return test."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import date
import json
import sys
import exchange_calendars as xc
import pandas as pd
from prepare import HERE,ROOT,RAW,OLD,RECENT,AUDIT,load,write,sha
from extract import Filing

CAL=xc.get_calendar('XNYS',start='2008-01-01',end='2027-01-01')
def available(filed):
    i=CAL.sessions.searchsorted(pd.Timestamp(filed),side='right')
    return CAL.sessions[i+1].date().isoformat()

def intact():
    protocol=load(HERE/'protocol.json')
    for group in ['baseline_files','source_files']:
        for name,digest in protocol[group].items():assert sha(ROOT/name)==digest,name
    assert sha(HERE/'filing-plan.json')==protocol['filing_plan_sha256']
    return protocol

def load_documents():
    plan={j['id']:j for j in load(HERE/'filing-plan.json')};docs={}
    for record in load(HERE/'retrieval-manifest.json')['requests']:
        if record['status']!='COMPLETE':continue
        p=ROOT/record['file'];assert sha(p)==record['sha256']
        markup=p.read_text();assert len(markup)==record['document_characters']
        result=Filing(markup,plan[record['id']]).extract()
        result['source_file']=record['file'];result['source_sha256']=record['sha256']
        docs[plan[record['id']]['cik'],record['accn']]=result
    write(RAW/'extracted-documents.json',list(docs.values()))
    return docs

def lookup(docs,cik,accn,cut):
    doc=docs.get((cik,accn))
    if doc and available(doc['metadata']['filed'])<=cut:return doc
    return None

def recover(row,docs):
    revised=deepcopy(row);recovered={};reasons=[]
    if not row['assets'] or not row['filing_eligible']:return revised,recovered,['INELIGIBLE_FILING']
    cik=row.get('source_cik',row['cik']);cut=row['cut'];end=row['report_end']
    if row['common_equity'] is None:
        doc=lookup(docs,cik,row['assets']['accn'],cut)
        cert=doc['book'].get(end) if doc else None
        if cert:
            revised['common_equity']=cert['value'];recovered['book']=cert
        else:reasons.append('BOOK_DOCUMENT_UNAVAILABLE' if doc is None else 'BOOK_STRUCTURE_UNQUALIFIED')
    if row['common_income_ttm'] is None:
        net=row['net_income_ttm'];parts=net['components'] if net else []
        qualified=[]
        if len(parts)==3 and net['method']=='prior_full_year_plus_current_ytd_minus_prior_ytd':
            annual,current,prior=parts;d=date.fromisoformat
            aligned=(annual['start']==prior['start'] and annual['end']>prior['end'] and current['end']==end
                and 350<=(d(annual['end'])-d(annual['start'])).days<=378
                and (d(current['start'])-d(annual['end'])).days==1
                and abs((d(current['end'])-d(current['start'])).days-(d(prior['end'])-d(prior['start'])).days)<=7)
            if aligned:
                for part in parts:
                    doc=lookup(docs,cik,part['accn'],cut)
                    cert=doc['income'].get(part['start']+'|'+part['end']) if doc else None
                    if cert:qualified.append(cert)
        elif len(parts)==1 and parts[0].get('start'):
            part=parts[0];d=date.fromisoformat
            if 350<=(d(part['end'])-d(part['start'])).days<=378:
                doc=lookup(docs,cik,part['accn'],cut)
                cert=doc['income'].get(part['start']+'|'+part['end']) if doc else None
                if cert:qualified.append(cert)
        if qualified and len(qualified)==len(parts):
            value=sum(cert['value']*sign for cert,sign in zip(qualified,[1,1,-1]))
            revised['common_income_ttm']=dict(value=value,method='qualified_original_basic_common_eps',components=qualified)
            recovered['income']=revised['common_income_ttm']
        else:reasons.append('INCOMPLETE_QUALIFIED_COMMON_EARNINGS')
    # Deliberately leave ROA, CFO, share counts and all other original fields intact.
    return revised,recovered,reasons

def main():
    protocol=intact();docs=load_documents();original=[]
    for folder in [OLD,RECENT]:
        original.extend(r for r in load(ROOT/'data/snapshots'/folder.name/'monthly-fundamentals.json')
                        if '2022-01'<=r['month']<='2026-09')
    assert len(original)==5700 and len({(r['symbol'],r['month']) for r in original})==5700
    revised=[];changes=[];reasons=Counter();byissuer=defaultdict(Counter);bymonth=defaultdict(Counter)
    for row in original:
        after,proof,why=recover(row,docs);revised.append(after);reasons.update(why)
        assert {k:v for k,v in row.items() if k not in ('common_equity','common_income_ttm')}=={k:v for k,v in after.items() if k not in ('common_equity','common_income_ttm')}
        for field in ('common_equity','common_income_ttm'):
            if row[field] is not None:assert row[field]==after[field]
        if proof:
            changes.append(dict(symbol=row['symbol'],month=row['month'],cut=row['cut'],proof=proof))
            for target in proof:byissuer[row['symbol']][target]+=1;bymonth[row['month']][target]+=1
    baseline={(r['symbol'],r['month']):r for r in original};new={(r['symbol'],r['month']):r for r in revised}
    fixture_results=[]
    for fixture in load(AUDIT/'audit-results.json')['rows']:
        key=fixture['symbol'],fixture['month']
        for field,short in [('common_equity','common_equity'),('common_income_ttm','common_income')]:
            if baseline[key][field] is not None:continue
            got=new[key][field];got=got['value'] if isinstance(got,dict) else got
            fixture_results.append(dict(symbol=key[0],month=key[1],field=field,expected=fixture[short+'_after'],actual=got,passed=got==fixture[short+'_after']))
    passed=all(r['passed'] for r in fixture_results)
    counts={f:{'before':sum(r[f] is not None for r in original),'after':sum(r[f] is not None for r in revised)} for f in ('common_equity','common_income_ttm')}
    write(RAW/'revised-monthly-fundamentals.json',revised)
    write(RAW/'change-provenance.json',changes)
    write(HERE/'coverage.json',dict(slots=len(original),counts=counts,changed_company_dates=len(changes),
        changed_issuers=len(byissuer),by_issuer={k:dict(v) for k,v in sorted(byissuer.items())},
        by_month={k:dict(v) for k,v in sorted(bymonth.items())},unresolved_reasons=dict(reasons),
        documents=len(docs),fixture_results=fixture_results,fixtures_passed=sum(r['passed'] for r in fixture_results),fixture_targets=len(fixture_results),
        data_gate_passed=passed,baseline_files_unchanged=len(protocol['baseline_files']),
        revised_payload_sha256=sha(RAW/'revised-monthly-fundamentals.json'),new_fits=0,profitability_runs=0))
    print(json.dumps(dict(counts=counts,documents=len(docs),changed_issuers=len(byissuer),fixture_passed=sum(r['passed'] for r in fixture_results),fixture_targets=len(fixture_results),failures=[r for r in fixture_results if not r['passed']]),indent=2))
    intact()

if __name__=='__main__':main()
