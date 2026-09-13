#!/usr/bin/env python3
"""Offline source consistency audit; no prices, labels, model results, or networking."""
import json,hashlib,re
from collections import Counter
from datetime import datetime
import sec_collect as s
from sec_annotate_predecessors import scopes
p=s.HERE;checks=[]
def check(name,ok,detail=None):checks.append({'check':name,'pass':bool(ok),'detail':detail})
def load(name):return json.loads((p/name).read_text())
policy=load('experiment-policy.json');selection=load('sec-selection.json');events=load('sec-events-current-roster.json');sources=load('sec-sources.json');manual=load('sec-manual-decisions.json')
check('frozen_policy',s.digest(p/'experiment-policy.json')==s.POLICY_SHA)
check('corrected_cohort',s.digest(p/'sec-selection.json')=='48e8b9692bf255dfb2578c17b43932e018063bab5df5ed359d0e9ba290fc84a0')
check('projection_cohort_binding',events['selection_sha256']==s.digest(p/'sec-selection.json'))
expected=[f'{i["cik"]}-{y}Q{q}' for i in selection['issuers'] for y in range(2020,2024) for q in range(1,5)]
check('exact_fixed_1600_slots',[r['slot_id'] for r in events['slots']]==expected and len(set(expected))==1600)
check('no_displaced_subsidiary',all(r['cik']!='0000046207' for r in events['slots']))
check('corrected_LE_present',sum(r['cik']=='0000799288' for r in events['slots'])==16)
check('all_initial_issuer_passes',events['issuers_completed']==100)
known={r['file']:r['sha256'] for r in sources['sources'].values()}
for r in json.loads((s.OLD/'sec-sources.json').read_text())['sources'].values():known.setdefault(r['file'],r['sha256'])
verified_files={};event_seen={};slot_blocks=[];base_counts=Counter()
def rawfile(f,h=None):
 if not f:return False
 expected_hash=h or known.get(f)
 if not expected_hash:return False
 if f not in verified_files:verified_files[f]=s.digest(s.ROOT/f)
 return verified_files[f]==expected_hash
for row in events['slots']:
 key=row['slot_id'];cur=row.get('current');old=row.get('prior');blocking=list(row.get('unresolved_reasons',[]))
 if not cur:
  check(key+':missing_retained',not row.get('checks',{}).get('current_release'))
  slot_blocks.append({'slot_id':key,'blocking':blocking or ['PENDING_COLLECTION']});continue
 check(key+':current_window',row['window_start']<=cur['filing_date']<=row['window_end'] and row['window_basis']=='ORIGINAL_FILING_DATE')
 check(key+':original_current',cur['form']=='8-K' and '2.02' in cur['items'] and cur['classification']=='EARNINGS_RELEASE')
 qualifying=sorted([e for e in row['candidate_events'] if e.get('classification')=='EARNINGS_RELEASE' and e.get('release_date')],key=lambda e:(e.get('acceptance_eastern') or '',e['accession']))
 check(key+':earliest_recorded_full',bool(qualifying) and qualifying[0]['accession']==cur['accession'])
 if row['checks']['earliest_event']:
  check(key+':no_unresolved_earlier',not row.get('candidate_failures') and not any(e['classification']=='UNRESOLVED' and e['filing_date']<=cur['filing_date'] for e in row['candidate_events']))
 check(key+':daily_timing_consistent',row['checks']['timing']==bool(cur['daily_entry_invariant']))
 check(key+':identity_consistent',row['checks']['identity']==(cur['security']['status']=='VERIFIED_SINGLE_COMMON_CLASS'))
 if cur.get('identity_source_at_decision'):
  proof=cur['identity_source_at_decision'];check(key+':dated_identity',max(proof['filing_date'],proof['acceptance_eastern_wallclock'][:10])<=cur['daily_entry_anchor_index'] and proof['index_ciks']==[row['cik']] and rawfile(proof['file'],proof['sha256']) and rawfile(proof['index_file'],proof['index_sha256']))
 if old:
  match=s.parser.period_match(cur,old)
  check(key+':prior_original_and_causal',old['classification']=='EARNINGS_RELEASE' and old['filing_date']<cur['filing_date'])
  check(key+':original_period_match',match['verified'] and row['prior_match']['verified'] and match['matched_scope']==row['prior_match']['matched_scope'])
 for e in [cur,old]+row.get('candidate_events',[])+row.get('information_predecessors',[])+row.get('unresolved_predecessor_scope',[]):
  if not e:continue
  event_seen[e['accession']]=e
 if row.get('predecessor_coverage'):
  check(key+':no_absence_claim',row['predecessor_coverage']['absence_verified'] is False)
 for e in row.get('information_predecessors',[]):
  target=(row.get('prior_match') or {}).get('matched_scope')
  if target is None and len(scopes(cur))==1:target=next(iter(scopes(cur)))
  before=e['filing_date']<cur['filing_date']
  if e.get('acceptance_eastern') and cur.get('acceptance_eastern'):before=datetime.fromisoformat(e['acceptance_eastern'])<datetime.fromisoformat(cur['acceptance_eastern'])
  check(key+':predecessor:'+e['accession'],e['period_end']==cur['period_end'] and target in scopes(e) and before)
 check(key+':known_prelim_exact', (row.get('known_preliminary_information')=='KNOWN_YES')==any(e['classification']=='PRELIMINARY' for e in row.get('information_predecessors',[])))
 if all(row['checks'].values()):base_counts[key.split('-')[-1][:4]]+=1
 slot_blocks.append({'slot_id':key,'base_SEC_checks':all(row['checks'].values()),'blocking':blocking})
for acc,e in event_seen.items():
 check(acc+':index_source',rawfile(e['index_file']))
 check(acc+':primary_source',rawfile(e.get('primary_file')) or bool(e.get('primary_document_unavailable') and e.get('cohort_identity_source')))
 if e.get('exhibit_file'):check(acc+':exhibit_hash',rawfile(e['exhibit_file'],e.get('exhibit_sha256')))
 if e.get('period_end'):
  proof=e.get('period_evidence')
  check(acc+':period_original_excerpt',bool(proof and proof.get('excerpt') and proof.get('period_end')==e['period_end']))
 for c in e.get('accounting_companions',[]):check(acc+':companion:'+c['file'],rawfile(c['file'],c['sha256']) and bool(c.get('source_evidence')))
for acc,r in manual['events'].items():check('manual:'+acc,rawfile(r['source_file'],r['source_sha256']))
journal=[json.loads(l) for l in (p/'sec-source-log.jsonl').read_text().splitlines()];starts=[r for r in journal if r['type']=='attempt_started'];ends={r['attempt_id']:r for r in journal if r['type']=='attempt_finished'}
check('attempt_count_bound',len(starts)==sources['attempt_count']<=policy['sec_max_requests'])
check('all_started_attempts_finished',set(r['attempt_id'] for r in starts)==set(ends))
counts=Counter(r['url'] for r in starts);check('per_url_two_attempt_bound',max(counts.values())<=2)
check('start_deadline',all(datetime.fromisoformat(r['started_at'])<datetime.fromisoformat(policy['sec_collection_deadline_utc']) for r in starts))
ordered=sorted(datetime.fromisoformat(r['started_at']).timestamp() for r in starts);check('request_start_rate',all(ordered[i+4]-ordered[i]>=0.99 for i in range(len(ordered)-4)))
restriction=load('sec-format-restriction.json');denied=[r for r in ends.values() if r.get('status') in [401,403,429]]
check('only_preserved_TXT_denials',{r['url'] for r in denied}==set(restriction['denied_urls']))
check('no_denied_retry',all(counts[r['url']]==1 for r in denied))
check('no_new_TXT_after_restriction',all(not r['url'].split('?')[0].endswith('.txt') for r in starts if r['attempt_id']>restriction['prior_attempt_count']))
for name,expected_hash in {'sec-events.json':'fe508fddb17c35957a89c57fcc21ed99b1f2d6d11c5bd579870614c342604452','sec-selection.json':'026159b5a7054be7ed61941f6785de318442e37e05d6ae5509d092b335efac94','sec-sources.json':'13931953589ea2b421c5aaf532f757b5ddf4f4d565bd6ce1ff119c888aab820c'}.items():check('old_pilot_unchanged:'+name,s.digest(s.OLD/name)==expected_hash)
out={'policy_sha256':s.POLICY_SHA,'created_utc':s.now(),'status':'PASS_INTERNAL_SOURCE_CONSISTENCY_WITH_RECORDED_GAPS' if all(c['pass'] for c in checks) else 'FAIL','checks_count':len(checks),'failures':[c for c in checks if not c['pass']],'source_files_checked':len(verified_files),'unique_events_checked':len(event_seen),'base_SEC_checks_by_year':dict(base_counts),'slot_blocking':slot_blocks,'reviewed_files':{name:s.digest(p/name) for name in ['sec-selection.json','sec-events-current-roster.json','sec-sources.json','sec-manual-decisions.json','sec-cohort-ownership-audit.json']},'limitations':['Internal consistency and original-source provenance audit, not independent semantic verification of every extracted value.','Recorded missing original/current/identity sources remain missing; source joins alone do not qualify prices, features, labels, fills or P&L.','Item2.02 predecessor frame does not prove comprehensive absence of earlier earnings information.']}
s.atomic(p/'sec-event-source-audit.json',out);print(json.dumps({k:v for k,v in out.items() if k not in ['slot_blocking','limitations','reviewed_files']}))
