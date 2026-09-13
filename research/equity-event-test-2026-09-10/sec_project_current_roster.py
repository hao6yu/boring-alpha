#!/usr/bin/env python3
"""Offline checkpoint from immutable issuer blocks and the corrected fixed roster."""
import json
from datetime import date,datetime,timedelta
import sec_collect as s
from sec_annotate_predecessors import annotate
from sec_apply_identity import apply as apply_identity
p=s.HERE
identity_path=p/'sec-identity-overrides.json'
identity=json.loads(identity_path.read_text()) if identity_path.exists() else {'events':{}}
if identity_path.exists():assert identity['policy_sha256']==s.POLICY_SHA
roster=json.loads((p/'sec-selection.json').read_text())
assert roster['policy_sha256']==s.POLICY_SHA and roster['selection_status']=='COMPLETE_100'
rows=[];sources=[];completed=0;complete_passes=0
for issuer in roster['issuers']:
 f=p/'sec-issuers'/(issuer['cik']+'.json')
 if f.exists():
  obj=json.loads(f.read_text());assert obj['policy_sha256']==s.POLICY_SHA
  assert len(obj['slots'])==16 and all(x['cik']==issuer['cik'] for x in obj['slots'])
  all_candidates={e['accession']:e for slot in obj['slots'] for e in slot.get('candidate_events',[])}
  for slot in obj['slots']:
   current=slot.get('current')
   if current:
    cutoff=(date.fromisoformat(current.get('release_date') or current['filing_date'])-timedelta(days=90)).isoformat()
    nearby={e['accession']:e for e in slot.get('information_predecessors',[])}
    for e in all_candidates.values():
     if e.get('classification') not in {'PRELIMINARY','GUIDANCE_UPDATE','ACCOUNTING_TRANSITION_PRESENTATION','SELECTED_METRICS_UPDATE'}:continue
     if e['accession']==current['accession'] or not cutoff<=e['filing_date']<=current['filing_date']:continue
     before=e['filing_date']<current['filing_date']
     if e.get('acceptance_eastern') and current.get('acceptance_eastern'):
      before=datetime.fromisoformat(e['acceptance_eastern'])<datetime.fromisoformat(current['acceptance_eastern'])
     if before:nearby[e['accession']]=e
    slot['nearby_information_disclosures']=list(nearby.values())
   rows.append(annotate(apply_identity(slot,identity)))
  completed+=1;complete_passes+=int(obj.get('status')=='INITIAL_ITEM_202_PASS_COMPLETE');sources.append({'file':str(f.relative_to(s.ROOT)),'sha256':s.digest(f)})
 else:
  for y in range(2020,2024):
   for q in range(1,5):rows.append({'slot_id':f'{issuer["cik"]}-{y}Q{q}','cik':issuer['cik'],'seed_symbol':issuer['historical_symbol'],'status':'PENDING_COLLECTION','current':None,'prior':None,'checks':{}})
assert len(rows)==1600 and len({r['slot_id'] for r in rows})==1600
out={'policy_sha256':s.POLICY_SHA,'selection_sha256':s.digest(p/'sec-selection.json'),'fixed_slots':1600,'issuer_blocks_present':completed,'issuers_completed':complete_passes,'status':'INITIAL_SOURCE_PASS_PENDING_AUDIT' if complete_passes==100 else 'IN_PROGRESS','updated_at':s.now(),'slots':rows,'issuer_sources':sources,'roster_scope':'Corrected original fixedCIK rule; no stale subsidiaryHE slots. Before/after proof sec-parent-identity-correction.json.'}
out['identity_overrides_sha256']=s.digest(identity_path) if identity_path.exists() else None
state=json.loads((p/'sec-sources.json').read_text())
if state.get('stop_reason'):
 out['status']='STOPPED_SOURCE_COLLECTION_INCOMPLETE';out['network_stop']=state['stop_reason']
h=s.atomic(p/'sec-events-current-roster.json',out)
checkpoint=p/'sec-checkpoints'/('events-'+h+'.json')
checkpoint.parent.mkdir(exist_ok=True)
if not checkpoint.exists():checkpoint.write_bytes((p/'sec-events-current-roster.json').read_bytes())
assert s.digest(checkpoint)==h
from collections import Counter
counts=Counter();years={str(y):Counter() for y in range(2020,2024)}
for row in rows:
 year=row['slot_id'].split('-')[-1][:4];stats=years[year]
 for key,ok in [('slots',True),('current',bool(row.get('current'))),('prior',bool(row.get('prior'))),('base_SEC_checks',bool(row.get('checks')) and all(row['checks'].values()))]:
  if ok:counts[key]+=1;stats[key]+=1
 for reason in row.get('unresolved_reasons',[]):counts['reason:'+reason]+=1
s.atomic(p/'sec-coverage.json',{'policy_sha256':s.POLICY_SHA,'selection_sha256':out['selection_sha256'],'events_sha256':h,'status':out['status'],'network_stop':out.get('network_stop'),'issuer_blocks_present':completed,'initial_pass_issuers':complete_passes,'counts':dict(counts),'years':{y:dict(c) for y,c in years.items()},'note':'Source joins only; not liquidity, label, feature, or performance qualification.'})
print(json.dumps({'issuers_completed':completed,'slots':1600,'sha256':h}))
