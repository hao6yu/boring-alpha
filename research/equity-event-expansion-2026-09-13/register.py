"""One-time registration and provenance-preserving reuse; no network or fits."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / 'equity-event-test-2026-09-10'
OLD_SHA = '3bda0898cd02318535333636b2416deb035d2adc1bf401f67f5c5655daea19a3'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
    return digest(path)

def main():
    assert not (HERE/'experiment-policy.json').exists(), 'Already registered'
    assert digest(OLD/'experiment-policy.json') == OLD_SHA
    original = json.loads((OLD/'experiment-policy.json').read_text())
    spec = dict(original)
    stamp = datetime.now(timezone.utc)
    spec.update(
        name='Earnings-language incremental-value exploratory test: 200-company expansion',
        created_utc=stamp.isoformat(),
        authorization='User: commit all pending changes, then continue with the suggested larger predefined cohort.',
        cohort_count=200, event_slots=3200,
        cohort_rule=original['cohort_rule'].replace('First100', 'First200'),
        notes='New exploratory expansion after the original study failed coverage; only cohort breadth changes statistically. First100 original issuers preserved; no evaluation returns observed.',
        sec_collection_deadline_utc=(stamp+timedelta(hours=3)).isoformat(),
        sec_network_owner='root', sec_max_requests=9000,
        databento_scope='No new paid requests in this expansion; reuse existing qualified data only.',
        expansion_price_max_requests=110,
        expansion_price_order='New seed members in fixed rank order, then missing original seed symbols, then contemporaneous filing identifiers; no source-success replacements.',
        parent_policy_sha256=OLD_SHA,
        parent_commit='b579208',
    )
    policy_sha = write(HERE/'experiment-policy.json', spec)
    (HERE/'experiment-policy.json.sha256').write_text(policy_sha+'\n')
    changes={k:{'before':original.get(k),'after':v} for k,v in spec.items() if original.get(k)!=v}
    write(HERE/'registration.json', {'policy_sha256':policy_sha,'created_utc':stamp.isoformat(),
        'changed_policy_fields':changes,'model_fitted':False,'evaluation_returns_examined':False,
        'reason':'Coverage-driven expansion only; fixed new total200 before selecting new issuers.',
        'parent_policy':{'path':str((OLD/'experiment-policy.json').relative_to(ROOT)),'sha256':OLD_SHA}})

    # Copy executable implementations with only path/policy/cohort-size binding changes.
    files=['sec_collect.py','sec_period_annotations.py','model.py','panel.py','price_data.py',
           'feature_extract.py','portfolio.py','evaluation_metrics.py','run_experiment.py',
           'audit_feature_sources.py','audit_price_actions.py','action_inventory.py']
    code=[]
    for name in files:
        source=OLD/name
        body=source.read_text().replace(OLD_SHA,policy_sha)
        body=body.replace('data/snapshots/equity-event-test-2026-09-10',
                          'data/snapshots/equity-event-expansion-2026-09-13')
        if name=='sec_collect.py':
            body=body.replace("HERE.parent / 'equity-event-repair-2026-09-10/dtss-sources.json'",
                "HERE.parent / 'equity-event-repair-2026-09-10/dtss-sources.json', HERE.parent / 'equity-event-test-2026-09-10/sec-sources.json'")
            body=body.replace("len(out['issuers']) < 100", "len(out['issuers']) < 200")
            body=body.replace("len(out['issuers']) == 100", "len(out['issuers']) == 200")
            body=body.replace('COMPLETE_100','COMPLETE_200').replace("'fixed_slots': 1600","'fixed_slots': 3200")
            body=body.replace("cohort_id='fixed-2019Q3-incumbents-v1'","cohort_id='fixed-2019Q3-incumbents-expanded200'")
        elif name=='price_data.py':
            body=body.replace("len(issuers) <= 100","len(issuers) <= 200")
            body=body.replace("requests = ['SPY'] + [symbol(x['historical_symbol']) for x in issuers]",
                "requests = ['SPY'] + [symbol(x['historical_symbol']) for x in issuers[100:] + issuers[:100]]")
            body=body.replace("if made >= args.limit:",
                "if len(manifest['requests']) - manifest.get('inherited_request_count', 0) >= policy['expansion_price_max_requests']:\n            break\n        if made >= args.limit:")
            body=body.replace("if len(recent) >= 50:",
                "daily = [r for r in manifest['requests'] if datetime.fromisoformat(r['requested_utc']) > now() - timedelta(days=1)]\n        monthly = {r['symbol'] for r in manifest['requests'] if r['requested_utc'][:7] == now().isoformat()[:7]}\n        if len(daily) >= 1000 or (ticker not in monthly and len(monthly) >= 500):\n            break\n        if now() >= datetime.fromisoformat(policy['sec_collection_deadline_utc']):\n            break\n        if len(recent) >= 50:")
        elif name=='panel.py':
            body=body.replace("len(sec['slots']) == 1600 and len(cohort['issuers']) == 100",
                              "len(sec['slots']) == spec['event_slots'] and len(cohort['issuers']) == spec['cohort_count']")
        elif name=='run_experiment.py':
            body=body.replace('len(rows) != 1600', "len(rows) != spec['event_slots']")
            body=body.replace('registered 1600 slots','registered 3200 slots')
        (HERE/name).write_text(body)
        code.append({'name':name,'parent_sha256':digest(source),'expansion_sha256':digest(HERE/name)})
    write(HERE/'implementation-reuse.json',{'policy_sha256':policy_sha,'files':code,
        'scope':'Path/policy bindings, cohort size and deterministic bounded acquisition; no model/feature/trading-parameter changes.'})

    reused=[]
    def clone_json(name):
        source=OLD/name
        obj=json.loads(source.read_text())
        if 'policy_sha256' in obj: obj['policy_sha256']=policy_sha
        write(HERE/name,obj)
        reused.append({'name':name,'parent_path':str(source.relative_to(ROOT)),
            'parent_sha256':digest(source),'initial_expansion_sha256':digest(HERE/name),
            'scope':'Existing source evidence retained; top-level policy binding updated, original evidence and nested hashes unchanged.'})
        return obj
    for name in ['sec-manual-decisions.json','price-source-exceptions.json','corporate-action-evidence.json',
                 'tiingo-directory-source.json','data-expense.json','execution-plan.md',
                 'corporate-action-convention.json','feature-currency-interpretation.json',
                 'panel-source-clarifications.json','simulation-pool-convention.json']:
        if name.endswith('.json'):clone_json(name)
        else:(HERE/name).write_bytes((OLD/name).read_bytes())
    ranked=clone_json('sec-ranked-seed.json')
    selection=clone_json('sec-selection.json')
    selection.update(ranked_seed_sha256=digest(HERE/'sec-ranked-seed.json'),selection_status='IN_PROGRESS',
        cohort_id='fixed-2019Q3-incumbents-expanded200',updated_at=stamp.isoformat())
    write(HERE/'sec-selection.json',selection);write(HERE/'sec-cohort.json',selection)
    manifest=clone_json('price-manifest.json')
    manifest.update(inherited_request_count=len(manifest['requests']), expansion_started_utc=stamp.isoformat(),
        pending_symbols=[],cohort_snapshots=[])
    write(HERE/'price-manifest.json',manifest)

    # Carry final annotated slots, not earlier issuer snapshots that predate source repairs.
    inventory=json.loads((OLD/'panel-inventory.json').read_text())
    source=ROOT/inventory['sec_events_path'];assert digest(source)==inventory['sec_events_sha256']
    frozen=json.loads(source.read_text());by_cik=defaultdict(list)
    for row in frozen['slots']:by_cik[row['cik']].append(row)
    for issuer in selection['issuers']:
        oldpath=OLD/'sec-issuers'/(issuer['cik']+'.json')
        obj=json.loads(oldpath.read_text())
        obj.update(policy_sha256=policy_sha,issuer=issuer,slots=by_cik[issuer['cik']],
            inherited_frozen_roster_path=str(source.relative_to(ROOT)),inherited_frozen_roster_sha256=digest(source))
        assert len(obj['slots'])==16
        write(HERE/'sec-issuers'/oldpath.name,obj)
    write(HERE/'inherited-evidence.json',{'policy_sha256':policy_sha,'reused':reused,
        'original_ciks':[i['cik'] for i in selection['issuers']],
        'original_rank_prefix':len(selection['screened']),
        'original_slots':{'path':str(source.relative_to(ROOT)),'sha256':digest(source),'count':1600},
        'original_feature_audit':{'path':str((OLD/'feature-source-audit.json').relative_to(ROOT)),
            'sha256':digest(OLD/'feature-source-audit.json')}})
    write(HERE/'source-readiness.json',{'policy_sha256':policy_sha,'ready':False,'status':'EXPANSION_COLLECTION_PENDING'})
    print(json.dumps({'policy_sha256':policy_sha,'deadline_utc':spec['sec_collection_deadline_utc'],
        'cohort_target':200,'inherited_issuers':100,'slots_target':3200}))

if __name__=='__main__':main()
