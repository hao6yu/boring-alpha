"""Replay both frozen variants under every previously declared account case."""
from datetime import datetime,timezone
import importlib.util,json,socket,sys
from prepare import HERE,ROOT,RAW,OLD,RECENT,FOLLOW,load,sha,write
from compare_support import (verify_freezes,saved,save,augment_metrics,selection_checks,
                             reference,months,interval,paired)


def no_network(*args,**kwargs):raise RuntimeError('This comparison is cache-only; network disabled.')
socket.socket.connect=no_network
socket.create_connection=no_network


def import_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def process(window,name,cost,frames,actions,simulate,sessions,metrics,ledger,expected,universe,original_reference):
    variants={}
    for variant in ('before','after'):
        schedule=load(RAW/f'{window}-{variant}-schedule.json')
        account=simulate(calendar=sessions,prices=frames,candidates=schedule['candidates'],actions=actions,
                         cost_case=cost,rank_mode='matched',retention_by_day=schedule['keep'])
        if variant=='before':assert account==saved(expected),(window,name,'baseline account differs')
        check=ledger(account,frames,actions,cost)
        check.update(selection_checks(account,schedule))
        benchmark,paths,refcheck=reference(account,universe)
        original_reference(account,universe,benchmark,paths)
        monthly=months(paths,sessions)
        variants[variant]=dict(metrics=augment_metrics(account,metrics(account)),reference=benchmark,monthly=monthly,
            selection_interval=interval(tuple(r['difference'] for r in monthly)),
            account_file=save(f'{window}-{name}-{variant}-account',account),
            reference_file=save(f'{window}-{name}-{variant}-reference',paths),
            verification=dict(ledger=check,reference=refcheck,baseline_exactly_reproduced=True if variant=='before' else None),
            held_stock_actions=[x for x in account.get('action_log',[]) if x['type'] in ('stock_merger','spinoff','stock_distribution')])
    out=dict(name=name,cost=cost,variants=variants,comparison=paired(variants['before'],variants['after']))
    print(json.dumps(dict(window=window,case=name,before=variants['before']['metrics']['profit'],after=variants['after']['metrics']['profit'],
        after_status=variants['after']['metrics']['status'],selection_after=variants['after']['reference']['selection_difference'])),flush=True)
    return out


def old():
    sys.path.insert(0,str(FOLLOW));import followup as f
    v=import_file('prior_old_ledger_verifier',FOLLOW/'verify.py')
    spec,_,_,frames,actions,_=f.load_inputs();prior=load(FOLLOW/'results.json')
    universe=load(ROOT/'data/snapshots'/FOLLOW.name/'universe-reference.json')
    def ledger(a,p,e,cost):return v.replay('fixed-'+cost,a,p,e)
    def original_reference(a,u,b,paths):
        if a['status']=='COMPLETE_ACCOUNTING':
            original=f.exposure_reference(a,u)
            assert paths==original['daily']
            assert abs(b['selection_difference']-original['difference_dollars'])<1e-8
    out=[]
    for case in load(HERE/'evaluation-freeze.json')['cases']['old']:
        if case['scenario']=='strict':p,e=frames,actions;group=prior['strict']
        else:p,e=f.scenario_inputs(frames,actions,case['value'],case['payment']);group=prior['receipt_scenarios'][case['scenario']]
        out.append(process('old',case['name'],case['cost'],p,e,f.portfolio.simulate,f.models.SESSIONS,f.models.metrics,
                   ledger,group['account_files']['fixed-'+case['cost']],universe,original_reference))
    return out


def recent():
    sys.path.insert(0,str(RECENT));import completion as c;import completion_verify as cv;import verify_recent as vr
    r=c.r;r.write=lambda *args,**kwargs:None;r.p.write=lambda *args,**kwargs:None
    prior=load(RECENT/'evaluation-result.json');completed={x['name']:x for x in load(RECENT/'completion-results.json')['cases']}
    universe=load(ROOT/'data/snapshots'/RECENT.name/'universe-returns.json')
    frames,actions,_=r.account_inputs();out=[]
    def original_reference(a,u,b,paths):
        original,op=(c.reference(a,u) if 'market_sensitive_claim_value' in a['daily'][0] else c.original.exposure_reference(a,u))
        assert op==paths
        assert original['complete']==b['complete'] and original['selection_difference']==b['selection_difference']
    for case in load(HERE/'evaluation-freeze.json')['cases']['recent']:
        strict=case['name'].startswith('strict-')
        if strict:p,e=frames,actions;engine=r.portfolio.simulate;ledger=vr.replay;expected=prior['account_files'][case['cost']]
        else:p,e=c.inputs(case);engine=c.engine.simulate;ledger=cv.replay;expected=completed[case['name']]['account_file']
        out.append(process('recent',case['name'],case['cost'],p,e,engine,r.SESSIONS,r.m.metrics,ledger,expected,universe,original_reference))
    return out


def main():
    window=sys.argv[1];assert window in ('old','recent');path=HERE/f'{window}-results.json';assert not path.exists()
    verify_freezes();out=old() if window=='old' else recent();verify_freezes()
    write(path,dict(window=window,status='CONTROLLED_VERIFIED_INPUT_COMPARISON',cases=out,finished_utc=datetime.now(timezone.utc).isoformat(),
                    new_network_requests=0,new_paid_data_usd=0,new_model_fits=0,parameter_searches=0))
    print(window,'comparison complete',flush=True)

if __name__=='__main__':main()
