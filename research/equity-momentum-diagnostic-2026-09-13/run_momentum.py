"""Offline, fixed-rule momentum experiment and all predeclared controls."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import sys

import numpy as np

from momentum_io import HERE, ROOT, RAW, SOURCE_HERE, POLICY_SHA, atomic, digest, policy, check_budget
import portfolio as account_engine
from metrics import metrics, bootstrap


def month_label(index):
    year,month=divmod(index,12)
    return f'{year:04}-{month+1:02}'


def month_number(day):
    return int(day[:4])*12+int(day[5:7])-1


def rank_hash(cik, seed=None):
    text=f'BA-stock-momentum-buffer-v1|{cik}' if seed is None else f'BA-stock-unranked-v1|{seed}|{cik}'
    return hashlib.sha256(text.encode()).hexdigest()


def qualified(b):
    return bool(b and b.get('qualified') is True and b.get('status')=='listed' and b.get('close',0)>0 and b.get('volume',0)>0)


def feature(cik, entry, sessions, prices):
    """Read only dates strictly preceding entry; skip the most recent month."""
    sec=cik+':single_common'; index=sessions.index(entry)
    liq_days=sessions[max(0,index-60):index]
    bars=[prices.get(d,{}).get(sec) for d in liq_days]
    if any(b and b.get('status') in ('otc','halted') for b in bars):
        return {'status':'KNOWN_LISTING_INELIGIBLE'}
    if len(bars)!=60 or any(not qualified(b) for b in bars):
        return {'status':'LIQUIDITY_PRICE_UNRESOLVED'}
    volume=float(np.median([b['close']*b['volume'] for b in bars]))
    if bars[-1]['close']<5 or volume<2_000_000:
        return {'status':'LIQUIDITY_INELIGIBLE'}
    start_month=month_label(month_number(entry)-13)
    end_month=month_label(month_number(entry)-2)
    starts=[d for d in sessions if d[:7]==start_month]
    ends=[d for d in sessions if d[:7]==end_month]
    if not starts or not ends:
        return {'status':'MOMENTUM_CALENDAR_UNRESOLVED'}
    first,last=max(starts),max(ends)
    history=sessions[sessions.index(first):sessions.index(last)+1]
    rows=[prices.get(d,{}).get(sec) for d in history]
    if any(not qualified(b) for b in rows):
        return {'status':'MOMENTUM_PRICE_UNRESOLVED','momentum_start':first,'momentum_end':last}
    if len({b['source_ticker'] for b in rows})!=1:
        return {'status':'MOMENTUM_IDENTITY_BRIDGE_UNRESOLVED','momentum_start':first,'momentum_end':last}
    ratio=rows[-1]['adjClose']/rows[0]['adjClose']
    assert math.isfinite(ratio) and ratio>0 and last<entry
    return {'status':'READY','momentum':ratio-1,'momentum_start':first,'momentum_end':last,
            'prior_close':bars[-1]['close'],'median_dollar_volume_60':volume,
            'source_ticker':rows[-1]['source_ticker'],'momentum_sessions':len(rows)}


def bands(ordered):
    n=len(ordered)
    return ordered[:math.ceil(.10*n)],ordered[:math.ceil(.20*n)]


def construct_inputs(ciks,sessions,prices):
    models={'momentum':None}|{f'unranked_{i:02}':i for i in range(20)}
    candidates={m:[] for m in models}; retention={m:{} for m in models}
    slots=[]; monthly=[]
    for month in sorted({d[:7] for d in sessions if '2022-01-03'<=d<='2023-12-29'}):
        entry=min(d for d in sessions if d[:7]==month)
        cutoff=(date.fromisoformat(month+'-01')-timedelta(days=1)).isoformat()
        features={c:feature(c,entry,sessions,prices) for c in ciks}
        for c,f in features.items(): slots.append({'cik':c,'entry_date':entry,'entry_month':month,**f})
        ready=[c for c in ciks if features[c]['status']=='READY']
        orders={}
        for name,seed in models.items():
            order=sorted(ready,key=lambda c:(-features[c]['momentum'],rank_hash(c))) if seed is None else sorted(ready,key=lambda c:rank_hash(c,seed))
            enter,keep=bands(order); orders[name]={'entry_ciks':enter,'retention_ciks':keep,'all_ranked_ciks':order}
            retention[name][entry]=[c+':single_common' for c in keep]
            for rank,c in enumerate(enter,1):
                candidates[name].append({'event_id':f'{name}:{month}:{c}','security_id':c+':single_common','cik':c,
                    'accession':f'ranking:{month}:{c}','filing_date':cutoff,'acceptance_date_et':cutoff,
                    'score':features[c]['momentum'] if seed is None else None,'eligibility_status':'READY',
                    'selection_key':f'{rank:06}:{c}'})
        monthly.append({'entry_month':month,'information_cutoff':cutoff,'ready_issuers':len(ready),
            'status_counts':dict(Counter(f['status'] for f in features.values())),'orders':orders})
    assert len(slots)==4800
    return {'slots':slots,'monthly':monthly,'candidates':candidates,'retention_by_day':retention}


def mean_control(controls):
    """Mean initial-capital-matched account path; no deletion of failed seeds."""
    incomplete=[name for name,a in controls.items() if a['status']!='COMPLETE_ACCOUNTING' or any(d['nav'] is None for d in a['daily']) or a['open_holdings']]
    if incomplete:
        return {'status':'UNRESOLVED_CONTROL_ENSEMBLE','incomplete_accounts':incomplete},None
    values=np.array([[float(d['nav']) for d in a['daily']] for a in controls.values()])
    average=values.mean(axis=0); prev=np.r_[10000,average[:-1]]; returns=average/prev-1
    days=(date(2023,12,29)-date(2022,1,3)).days+1
    peaks=np.maximum.accumulate(np.r_[10000,average])[1:]
    ends=values[:,-1]
    return {'status':'COMPLETE_PREDECLARED_CONTROL_ENSEMBLE','count':len(controls),
        'initial_capital_per_account':10000,'mean_ending_nav_usd':float(average[-1]),
        'mean_net_profit_usd':float(average[-1]-10000),'mean_path_cagr':float((average[-1]/10000)**(365/days)-1),
        'mean_path_max_drawdown_fraction':float(np.max(1-average/peaks)),
        'ending_nav_min_median_max':list(map(float,[ends.min(),np.median(ends),ends.max()])),
        'ending_nav_25_75_percentiles':list(map(float,np.quantile(ends,[.25,.75]))),
        'halted_controls':sum(a['stopped'] for a in controls.values()),
        'interpretation':'Average of 20 separately funded hypothetical $10k accounts, used only as a comparison reference; not a directly tradable $10k pooled allocation.'},list(map(float,returns))


def run():
    check_budget(); spec=policy()
    assert not (HERE/'evaluation-result.json').exists(), 'Refuse to overwrite completed results'
    assert digest(ROOT/spec['cohort_path'])==spec['cohort_sha256']
    assert digest(ROOT/spec['qualified_identity_snapshot'])==spec['qualified_identity_snapshot_sha256']
    before={'policy_sha256':POLICY_SHA,'at_utc':datetime.now(timezone.utc).isoformat(),
        'code':{n:digest(HERE/n) for n in ['run_momentum.py','portfolio.py','metrics.py','momentum_io.py']},
        'source_adapter_code':{n:digest(SOURCE_HERE/n) for n in ['panel.py','price_data.py','run_experiment.py']},
        'sources':{n:digest(SOURCE_HERE/n) for n in ['price-manifest.json','price-source-exceptions.json','corporate-action-evidence.json','sec-cohort.json']},
        'identity_source':spec['qualified_identity_snapshot'],'identity_source_sha256':spec['qualified_identity_snapshot_sha256'],
        'strategy_outcomes_computed':False,'control_seeds':spec['control_seeds']}
    atomic(HERE/'evaluation-start.json',before)
    sys.path.insert(0,str(SOURCE_HERE))
    from panel import calendar,load_prices
    from run_experiment import source_frames
    sessions=calendar(); assert sessions[0]=='2019-10-01' and sessions[-1]=='2023-12-29'
    series,audit=load_prices()
    cohort=json.loads((ROOT/spec['cohort_path']).read_text())
    sec=json.loads((ROOT/spec['qualified_identity_snapshot']).read_text())
    prices,actions,identities=source_frames(series,sessions,sec,cohort)
    for day,rows in prices.items():
        for b in rows.values():
            if not b.get('missing_provider_row'):
                b['adjClose']=series[b['source_ticker']]['rows'][day]['adjClose']
    inputs=construct_inputs([i['cik'] for i in cohort['issuers']],sessions,prices)
    sha=atomic(RAW/'frozen-inputs.json',inputs)
    freeze={'policy_sha256':POLICY_SHA,'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'input_file':str((RAW/'frozen-inputs.json').relative_to(ROOT)),'sha256':sha,'issuer_months':4800,
        'monthly_coverage':[{k:v for k,v in m.items() if k!='orders'} for m in inputs['monthly']],
        'slot_status_counts':dict(Counter(s['status'] for s in inputs['slots'])),
        'future_price_endpoint_availability_used_for_selection':False,
        'note':'Price files contain the fixed 2019-2023 window; ranking/eligibility functions access strictly pre-entry dates. Source availability itself may correlate with survival.'}
    atomic(HERE/'input-freeze.json',freeze)
    atomic(RAW/'source-audit.json',{'identities':identities,'prices':audit})
    summaries={}; comparisons={}; ledgers={}
    for cost in ['base','stress']:
        accounts={}; summaries[cost]={}; ledgers[cost]={}
        for name,candidates in inputs['candidates'].items():
            check_budget()
            a=account_engine.simulate(calendar=sessions,prices=prices,candidates=candidates,actions=actions,cost_case=cost,
                rank_mode='matched',retention_by_day=inputs['retention_by_day'][name])
            accounts[name]=a; summary=metrics(a)
            summary['held_review_states']=dict(Counter(r['status'] for r in a['held_exit_decisions']))
            if summary['daily_nav_complete']:
                peakweights=[max([float(h['quantity'])*float(h['qualified_close'])/float(d['nav']) for h in d['holdings'].values()],default=0) for d in a['daily']]
                summary['largest_observed_position_weight']=max(peakweights)
                summary['round_trip_equivalent_turnover_per_year']=sum(float(f['notional']) for f in a['fills'])/(2*10000)/(summary['calendar_days']/365)
            summaries[cost][name]=summary
            path=RAW/f'{cost}-{name}.json'; checksum=atomic(path,a)
            ledgers[cost][name]={'path':str(path.relative_to(ROOT)),'sha256':checksum}
        controls={n:a for n,a in accounts.items() if n!='momentum'}
        ensemble,control_returns=mean_control(controls)
        if control_returns is not None:
            target=accounts['momentum']; deltas=[float(d['daily_return'])-r if d['daily_return'] is not None else None for d,r in zip(target['daily'],control_returns)]
            ensemble['momentum_minus_mean_control_uncertainty']=bootstrap(deltas)
            if target['ending_nav'] is not None:
                ensemble['momentum_minus_mean_control_ending_usd']=float(target['ending_nav'])-ensemble['mean_ending_nav_usd']
                ensemble['controls_with_lower_ending_nav_than_momentum']=sum(float(a['ending_nav'])<float(target['ending_nav']) for a in controls.values())
        comparisons[cost]=ensemble
        print(json.dumps({'cost_case':cost,'momentum':{k:v for k,v in summaries[cost]['momentum'].items() if k in ['accounting_status','ending_nav_usd','cagr','max_drawdown_fraction','completed_positions','stopped']},'control_status':ensemble['status']}),flush=True)
    result={'policy_sha256':POLICY_SHA,'status':'FIXED_EXPLORATORY_DIAGNOSTIC_COMPLETE_NO_VALIDATION_PASS',
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_paid_data_usd':0,
        'accounts':summaries,'unranked_comparison':comparisons,'ledgers':ledgers,
        'coverage':freeze['slot_status_counts'],'input_freeze_sha256':digest(HERE/'input-freeze.json'),
        'limitations':['Fixed 2019 incumbent cohort and existing cached-source gaps; conditional on qualified inputs, not all US equities.',
            'Already-explored2022-2023 market history, long-only adaptation, no parameter search or external code execution.',
            'No cash interest/taxes, conservative seven-day cash lock and whole-share closing-limit proxies; not actual fills.',
            'Any unresolved required account/held mark blocks a complete comparison; never omit a failed control seed.']}
    atomic(HERE/'evaluation-result.json',result)


if __name__=='__main__': run()
