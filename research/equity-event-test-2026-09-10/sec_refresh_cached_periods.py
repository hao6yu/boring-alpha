#!/usr/bin/env python3
"""Rebuild only completed issuer blocks whose cached original periods gain annotations."""
import json
import sec_collect as s
from sec_period_annotations import annotate
p=s.HERE
class Offline:
 def __init__(self):
  self.policy=json.loads((p/'experiment-policy.json').read_text());self.sources=json.loads((p/'sec-sources.json').read_text())['sources'];self.old=json.loads((s.OLD/'sec-sources.json').read_text())['sources']
 def get(self,u):
  r=self.sources.get(u) or self.old.get(u)
  if not r:raise s.SourceFailure('offline_source_missing')
  b=(s.ROOT/r['file']).read_bytes()
  if s.sha(b)!=r['sha256']:raise s.StopCollection('raw_hash')
  return b,r['file']
base=s.Client
class Client(base):
 def event(self,cik,row):return annotate(s.event_override(super().event(cik,row)))
s.Client=Client
roster=json.loads((p/'sec-selection.json').read_text());changes=[]
for issuer in roster['issuers']:
 f=p/'sec-issuers'/(issuer['cik']+'.json')
 if not f.exists():continue
 old=json.loads(f.read_text())
 if old.get('status')!='INITIAL_ITEM_202_PASS_COMPLETE':continue
 candidates=[e for row in old['slots'] for e in [row.get('current'),row.get('prior')]+row.get('candidate_events',[]) if e]
 needs=any(not e.get('week_period_annotation_status') and annotate(e).get('week_period_annotation_status') for e in candidates)
 if not needs:continue
 before=s.digest(f);copy=p/'sec-checkpoints'/('issuer-'+issuer['cik']+'-'+before+'.json');copy.parent.mkdir(exist_ok=True)
 if not copy.exists():copy.write_bytes(f.read_bytes())
 new=s.collect_issuer(Offline(),issuer)
 changes.append({'cik':issuer['cik'],'before_sha256':before,'before_file':str(copy.relative_to(s.ROOT)),'after_sha256':s.digest(f),'before_priors':sum(bool(x['prior']) for x in old['slots']),'after_priors':sum(bool(x['prior']) for x in new['slots'])})
s.atomic(p/'sec-period-annotation-review.json',{'policy_sha256':s.POLICY_SHA,'network_requests':0,'script_sha256':s.digest(p/'sec_period_annotations.py'),'changes':changes,'scope':'Original fiscalperiod parserrepair only; no prices/model outcomes read. Explicit13/14-week periods never certify equal-duration numericalgrowth.'});print(json.dumps(changes))
