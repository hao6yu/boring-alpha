#!/usr/bin/env python3
"""Offline audit of the currently resolved fixed-rank SEC cohort prefix."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
EXPECTED='3bda0898cd02318535333636b2416deb035d2adc1bf401f67f5c5655daea19a3'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    policy=json.loads((HERE/'experiment-policy.json').read_text())
    selection=json.loads((HERE/'sec-selection.json').read_text())
    ranked=json.loads((HERE/'sec-ranked-seed.json').read_text())
    sources=json.loads((HERE/'sec-sources.json').read_text())
    checks=[]
    def check(name,ok,detail=None):checks.append({'check':name,'pass':bool(ok),'detail':detail})
    check('frozen_policy',digest(HERE/'experiment-policy.json')==EXPECTED)
    check('rank_binding',selection['ranked_seed_sha256']==digest(HERE/'sec-ranked-seed.json'))
    master=ROOT/ranked['master_file'];check('master_hash',digest(master)==ranked['master_sha256'])
    ciks={r.split('|')[0].zfill(10) for r in master.read_text(encoding='latin-1').splitlines() if len(r.split('|'))==5 and r.split('|')[2]=='8-K' and r.split('|')[0].isdigit()}
    order=sorted(ciks,key=lambda c:hashlib.sha256((policy['cohort_seed']+'|'+c).encode()).hexdigest())
    check('original_master_rank',order==[r['cik'] for r in ranked['rows']])
    screened=selection['screened'];check('contiguous_screened_ranks',[r['seed_rank'] for r in screened]==list(range(1,len(screened)+1)))
    selected=[r for r in screened if r['decision']=='SELECTED']
    check('exact_selected_prefix',[r['cik'] for r in selected]==[i['cik'] for i in selection['issuers']])
    check('unresolved_only_final',all(r['decision']!='UNRESOLVED' for r in screened[:-1]))
    for row,issuer in zip(selected,selection['issuers']):
        e=row['selected_event']; key=issuer['cik']
        check(key+':rank',order[row['seed_rank']-1]==key)
        check(key+':original_full_release',e['form']=='8-K' and '2.02' in e['items'] and e['classification']=='EARNINGS_RELEASE')
        check(key+':cutoff',bool(e.get('acceptance_eastern')) and e['acceptance_eastern'][:10]<'2019-09-30')
        check(key+':common_class',e['security']['status']=='VERIFIED_SINGLE_COMMON_CLASS' and e['security']['historical_symbol']==issuer['historical_symbol'])
        check(key+':identity_source_hash',digest(ROOT/issuer['source']['file'])==issuer['source']['sha256'])
    for row in screened:
        check(str(row['seed_rank'])+':master_metadata_complete',not row.get('missing_master_accessions',[]))
        if row['decision']=='EXCLUDED' and not row.get('candidates'):
            check(str(row['seed_rank'])+':excluded_without_candidates',row.get('candidate_accessions')==[])
    for kind,rows in json.loads((HERE/'sec-manual-decisions.json').read_text()).items():
        for key,r in rows.items():check('manual:'+key+':source_hash',digest(ROOT/r['source_file'])==r['source_sha256'])
    journal=[json.loads(l) for l in (HERE/'sec-source-log.jsonl').read_text().splitlines()]
    starts=[r for r in journal if r['type']=='attempt_started'];ends={r['attempt_id']:r for r in journal if r['type']=='attempt_finished'}
    check('aggregate_attempts',len(starts)==sources['attempt_count'] and len(starts)<=policy['sec_max_requests'])
    denied=[r for r in ends.values() if r.get('status') in (401,403,429)]
    recovery_path=HERE/'sec-endpoint-recovery.json'
    recovery=json.loads(recovery_path.read_text()) if recovery_path.exists() else None
    allowed=bool(recovery and recovery['policy_sha256']==EXPECTED and recovery['status']=='RECOVERED_LINKED_HTML')
    restriction=json.loads((HERE/'sec-format-restriction.json').read_text())
    check('denial_resume_explicitly_authorized',restriction['policy_sha256']==EXPECTED and set(d['url'] for d in denied)==set(restriction['denied_urls']) and restriction['status']=='AUTHORIZED_HTML_INDEX_SUBMISSIONS_ONLY')
    check('no_TXT_after_format_restriction',all(not r['url'].split('?')[0].endswith('.txt') for r in starts if r['attempt_id']>restriction['prior_attempt_count']))
    check('denied_endpoint_never_retried',all(sum(r['url']==d['url'] for r in starts)==1 for d in denied))
    if allowed:
        check('recovery_source_hash',digest(ROOT/recovery['file'])==recovery['sha256'])
        check('recovery_first_request',sum(r['url']==recovery['url'] for r in starts)==1)

    for url,r in sources['sources'].items():check('source:'+str(r['attempt_id']),digest(ROOT/r['file'])==r['sha256'])
    result={'policy_sha256':EXPECTED,'selection_sha256':digest(HERE/'sec-selection.json'),'sources_sha256':digest(HERE/'sec-sources.json'),
        'status':'PASS_PREFIX_ONLY' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,'checks_count':len(checks),
        'selected_count':len(selected),'screened_count':len(screened),'network_stop':sources['stop_reason'],
        'cohort_complete':selection['selection_status']=='COMPLETE_100','first_unresolved_rank':next((r['seed_rank'] for r in screened if r['decision']=='UNRESOLVED'),None),
        'limitations':['Code/data consistency audit plus hashed source provenance; full100-issuer independent semantic audit is not implied.','An unresolved higher rank blocks final cohort admission; later price availability is not a replacement criterion.']}
    (HERE/'sec-prefix-audit.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
if __name__=='__main__':run()
