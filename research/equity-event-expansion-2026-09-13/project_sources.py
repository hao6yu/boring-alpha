"""Publish all 3,200 slots, retaining the original 1,600 exactly."""
from datetime import datetime, date, timedelta
from collections import Counter
import json
import sec_collect as s
from sec_annotate_predecessors import annotate
from sec_apply_identity import apply

def main():
    p=s.HERE;roster=json.loads((p/'sec-cohort.json').read_text())
    assert roster['selection_status']=='COMPLETE_200'
    original=json.loads((p/'inherited-evidence.json').read_text())['original_slots']
    original_path=s.ROOT/original['path'];assert s.digest(original_path)==original['sha256']
    oldslots={x['slot_id']:x for x in json.loads(original_path.read_text())['slots']}
    identity_path=p/'sec-identity-overrides.json'
    overrides=json.loads(identity_path.read_text()) if identity_path.exists() else {'events':{}}
    if identity_path.exists():assert overrides['policy_sha256']==s.POLICY_SHA
    slots=[];sources=[];completed=0
    for issuer in roster['issuers']:
        path=p/'sec-issuers'/(issuer['cik']+'.json')
        if not path.exists():
            slots.extend({'slot_id':f'{issuer["cik"]}-{year}Q{quarter}','cik':issuer['cik'],
                'seed_symbol':issuer['historical_symbol'],'status':'PENDING_COLLECTION',
                'current':None,'prior':None,'checks':{}}
                for year in range(2020,2024) for quarter in range(1,5))
            continue
        block=json.loads(path.read_text());assert block['policy_sha256']==s.POLICY_SHA
        assert len(block['slots'])==16 and all(x['cik']==issuer['cik'] for x in block['slots'])
        completed+=int(block['status']=='INITIAL_ITEM_202_PASS_COMPLETE')
        sources.append({'file':str(path.relative_to(s.ROOT)),'sha256':s.digest(path)})
        candidates={e['accession']:e for row in block['slots'] for e in row.get('candidate_events',[])}
        for row in block['slots']:
            if row['slot_id'] in oldslots:
                assert row==oldslots[row['slot_id']], 'Inherited slot changed'
                slots.append(row);continue
            current=row.get('current')
            if current:
                cutoff=(date.fromisoformat(current.get('release_date') or current['filing_date'])-timedelta(days=90)).isoformat()
                nearby={e['accession']:e for e in row.get('information_predecessors',[])}
                for e in candidates.values():
                    if e.get('classification') not in {'PRELIMINARY','GUIDANCE_UPDATE','ACCOUNTING_TRANSITION_PRESENTATION','SELECTED_METRICS_UPDATE'}:continue
                    if e['accession']==current['accession'] or not cutoff<=e['filing_date']<=current['filing_date']:continue
                    before=e['filing_date']<current['filing_date']
                    if e.get('acceptance_eastern') and current.get('acceptance_eastern'):
                        before=datetime.fromisoformat(e['acceptance_eastern'])<datetime.fromisoformat(current['acceptance_eastern'])
                    if before:nearby[e['accession']]=e
                row['nearby_information_disclosures']=list(nearby.values())
            slots.append(annotate(apply(row,overrides)))
    assert len(slots)==3200 and len({r['slot_id'] for r in slots})==3200
    state=json.loads((p/'sec-sources.json').read_text())
    out={'policy_sha256':s.POLICY_SHA,'selection_sha256':s.digest(p/'sec-cohort.json'),
        'fixed_slots':3200,'slots':slots,'issuers_completed':completed,'issuer_sources':sources,
        'updated_at':s.now(),'status':'INITIAL_SOURCE_PASS_PENDING_AUDIT' if completed==200 else 'IN_PROGRESS',
        'network_stop':state.get('stop_reason'),'original_1600_slots_exactly_preserved':True,
        'original_slots':original,'identity_overrides_sha256':s.digest(identity_path) if identity_path.exists() else None}
    checksum=s.atomic(p/'sec-events-current-roster.json',out)
    years={str(y):Counter() for y in range(2020,2024)}
    for row in slots:
        c=years[row['slot_id'].split('-')[-1][:4]];c['slots']+=1
        c['current']+=int(bool(row.get('current')));c['prior']+=int(bool(row.get('prior')))
        c['source_joins']+=int(bool(row.get('checks')) and all(row['checks'].values()))
    report={'policy_sha256':s.POLICY_SHA,'sec_events_sha256':checksum,'completed_issuers':completed,
        'years':{k:dict(v) for k,v in years.items()},'original_slots_preserved':True,
        'scope':'Source coverage only; no price, model or profitability claim.'}
    s.atomic(p/'sec-coverage.json',report);print(json.dumps(report))

if __name__=='__main__':main()
