#!/usr/bin/env python3
"""Offline refresh of completed blocks with named reviewed source decisions."""
import json,re
import sec_collect as s
from sec_period_annotations import annotate
p=s.HERE
class Offline:
 def __init__(self):
  self.policy=json.loads((p/'experiment-policy.json').read_text());self.sources=json.loads((p/'sec-sources.json').read_text())['sources'];self.old=json.loads((s.OLD/'sec-sources.json').read_text())['sources']
  for line in (p/'sec-source-log.jsonl').read_text().splitlines():
   r=json.loads(line)
   if r.get('type')=='attempt_finished' and r.get('status')==200:self.sources[r['url']]=r
 def get(self,u):
  r=self.sources.get(u) or self.old.get(u)
  if not r:raise s.SourceFailure('offline_source_missing')
  b=(s.ROOT/r['file']).read_bytes()
  if s.sha(b)!=r['sha256']:raise s.StopCollection('raw_hash')
  return b,r['file']
base=s.Client
class Client(base):
 def event(self,cik,row):return annotate(s.event_override(super().event(cik,row)))
s.Client=Client;manual=json.loads((p/'sec-manual-decisions.json').read_text());targets=set()
for acc in manual['events']:
 f=p/'sec-parsed'/(acc+'.json')
 if f.exists():
  e=json.loads(f.read_text())['event'];m=re.search(r'/edgar/data/(\d+)/',e.get('primary_url',''))
  if m:targets.add(m[1].zfill(10))
changes=[];fetcher=Offline()
for issuer in json.loads((p/'sec-selection.json').read_text())['issuers']:
 if issuer['cik'] not in targets:continue
 f=p/'sec-issuers'/(issuer['cik']+'.json')
 if not f.exists():continue
 before=f.read_bytes();old=json.loads(before)
 if old.get('status')!='INITIAL_ITEM_202_PASS_COMPLETE':continue
 h=s.sha(before);copy=p/'sec-checkpoints'/('issuer-'+issuer['cik']+'-'+h+'.json');copy.parent.mkdir(exist_ok=True)
 if not copy.exists():copy.write_bytes(before)
 new=s.collect_issuer(fetcher,issuer)
 oldfailed={r['accession'] for r in old.get('source_failures',[])};newfailed={r['accession'] for r in new.get('source_failures',[])}
 if not newfailed.issubset(oldfailed):
  f.write_bytes(before);changes.append({'cik':issuer['cik'],'status':'SKIPPED_NEW_OFFLINE_CACHE_GAP'});continue
 changes.append({'cik':issuer['cik'],'before_sha256':h,'after_sha256':s.digest(f),'before_current':sum(bool(x['current']) for x in old['slots']),'after_current':sum(bool(x['current']) for x in new['slots']),'before_base_checks':sum(all(x['checks'].values()) for x in old['slots']),'after_base_checks':sum(all(x['checks'].values()) for x in new['slots'])})
out={'policy_sha256':s.POLICY_SHA,'network_requests':0,'manual_decisions_sha256':s.digest(p/'sec-manual-decisions.json'),'updated_at':s.now(),'changes':changes}
s.atomic(p/'sec-reviewed-frame-refresh.json',out);print(json.dumps(changes))
