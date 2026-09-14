"""Offline frozen-prediction attribution, unranked controls and receipt scenarios."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D
import gzip, hashlib, json, math, sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=HERE.parent/'ml-stock-comparison-2026-09-14'
RAW=ROOT/'data/snapshots'/HERE.name
sys.path.insert(0,str(OLD))
import models, panel, portfolio

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj): p.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def save_account(name,a):
    p=RAW/(name+'.json.gz')
    p.write_bytes(gzip.compress(json.dumps(a,sort_keys=True,allow_nan=False).encode(),mtime=0))
    return dict(file=str(p.relative_to(ROOT)),sha256=sha(p))

def intact():
    spec=read(HERE/'protocol.json')
    for collection in ['original_artifacts','input_hashes']:
        for name,value in spec[collection].items(): assert sha(ROOT/name)==value,name
    return spec

def load_inputs():
    spec=intact()
    coverage=read(OLD/'panel-coverage.json')
    rows=read(ROOT/coverage['panel_file'])
    predictions=read(ROOT/'data/snapshots'/OLD.name/'predictions.json')
    assert len(predictions)==2115 and all('2022-01'<=r['month']<='2023-12' for r in predictions)
    # The frozen adapter also renders identity reports. Suppress that output
    # while reusing its unchanged price/action calculations in this follow-up.
    previous=panel.write
    try:
        panel.write=lambda *args,**kwargs:None
        frames,actions=models.account_frames()
        references,_,_=panel.price_features()
    finally: panel.write=previous
    for frame in frames: assert frame<'2024-01-01'
    intact()
    return spec,predictions,rows,frames,actions,references

def schedule(predictions,name,seed=None):
    candidates=[];keep={};orders=[]
    for month in sorted({r['month'] for r in predictions}):
        rs=[r for r in predictions if r['month']==month]
        if seed is None:rs.sort(key=lambda r:(-r[name],r['symbol']))
        else:rs.sort(key=lambda r:(hashlib.sha256(f'ba-ml-unranked-followup-v1|{seed}|{r["cik"]}'.encode()).hexdigest(),r['symbol']))
        n=len(rs);day=rs[0]['entry'];keep[day]=[r['symbol'] for r in rs[:math.ceil(.2*n)]]
        orders.append(dict(month=month,all_symbols=[r['symbol'] for r in rs],entry_count=math.ceil(.1*n),retention_count=math.ceil(.2*n)))
        for rank,r in enumerate(rs[:math.ceil(.1*n)]):
            candidates.append(dict(event_id=f'{name}:{month}:{r["symbol"]}',security_id=r['symbol'],cik=r['cik'],signal_date=r['cut'],score=r[name] if seed is None else None,eligibility_status='READY',selection_key=f'{rank:04}:{r["symbol"]}'))
    return candidates,keep,orders

def scenario_inputs(frames,actions,value,payment):
    # Qualified solely under this disclosed hypothetical cash-in-lieu receipt.
    # The original action, source payload and strict account are not modified.
    prices=frames.copy();day='2022-03-01';prices[day]=frames[day].copy()
    prices[day]['ZBH']=dict(frames[day]['ZBH'],divCash=str(D(str(value))/10))
    out=[];found=0
    for source in actions:
        action=deepcopy(source)
        if action['action_id']=='ZBH:2022-03-01:unresolved_distribution':
            found+=1
            action.update(type='dividend',verified=True,amount_per_share=str(D(str(value))/10),cash_available_date=payment,
                          qualification='HYPOTHETICAL_CASH_IN_LIEU_NOT_OBSERVED_BROKER_PAYMENT',assumed_cash_per_ZIMV_share=str(value))
        out.append(action)
    assert found==1
    return prices,out

def scenarios(spec):
    yield 'zero_withheld',0,None
    for value in spec['ridge_and_control_spinoff_scenarios']['child_cash_values'][1:]:
        for payment in spec['ridge_and_control_spinoff_scenarios']['payment_dates']:
            yield f'cash_{value}_{payment or "withheld"}',value,payment

def extras(a):
    metric=models.metrics(a)
    ds=a['daily'];valid=[r for r in ds if r['nav'] is not None]
    exposures=[sum(float(h['quantity'])*float(h['qualified_close']) for h in r['holdings'].values())/float(r['nav']) for r in valid]
    metric.update(mean_stock_exposure=float(np.mean(exposures)) if exposures else None,
                  fills=len(a['fills']),traded_notional=sum(float(f['notional']) for f in a['fills']),
                  mean_settled_cash=float(np.mean([float(r['settled_cash']) for r in valid])) if valid else None)
    march=[r for r in ds if r['date']=='2022-02-28'][0]
    q=float(march['holdings'].get('ZBH',{}).get('quantity',0));assert 0<=q<10
    metric['ZBH_shares_before_spinoff']=q
    return metric

def daily_universe_returns(predictions,references):
    monthly={m:sorted(r['symbol'] for r in predictions if r['month']==m) for m in sorted({r['month'] for r in predictions})}
    output=[]
    sessions=models.SESSIONS;index={d:i for i,d in enumerate(sessions)}
    for day in [d for d in sessions if '2022-01-03'<=d<='2023-12-29']:
        returns=[];missing=[]
        for s in monthly[day[:7]]:
            life=models.LIFECYCLE.get(s,{})
            if life.get('event_date','9999')<=day:
                if life['outcome']=='CASH_MERGER':
                    r=life['cash']/references[s][life['end']]['close']-1 if day==life['event_date'] else 0.
                else:missing.append(s);continue
            else:
                gross=references.get(s,{}).get(day,{}).get('gross')
                if gross is None:missing.append(s);continue
                r=gross-1
            returns.append(r)
        assert not missing,(day,missing)
        output.append(dict(date=day,universe_return=float(np.mean(returns)),names=len(returns)))
    return output

def exposure_reference(account,universe):
    assert account['status']=='COMPLETE_ACCOUNTING'
    costs=defaultdict(float)
    for f in account['fills']: costs[f['date']]+=float(f['fee_total'])+float(f['slippage_cost'])
    prior_nav=reference_nav=10000.;prior_stock=0.;rows=[]
    for row,u in zip(account['daily'],universe):
        assert row['date']==u['date']
        nav=float(row['nav']);w=prior_stock/prior_nav;cost=costs[row['date']]/prior_nav
        reference_return=w*u['universe_return']-cost
        actual_return=nav/prior_nav-1
        reference_nav*=1+reference_return
        rows.append(dict(date=row['date'],strategy_nav=nav,reference_nav=reference_nav,lagged_stock_exposure=w,
                         strategy_return=actual_return,reference_return=reference_return,universe_return=u['universe_return'],cost_return=cost))
        prior_stock=sum(float(h['quantity'])*float(h['qualified_close']) for h in row['holdings'].values());prior_nav=nav
    monthly=[]
    for month in sorted({r['date'][:7] for r in rows}):
        rs=[r for r in rows if r['date'].startswith(month)]
        actual=float(np.prod([1+r['strategy_return'] for r in rs])-1);reference=float(np.prod([1+r['reference_return'] for r in rs])-1)
        monthly.append(dict(month=month,strategy_return=actual,reference_return=reference,difference=actual-reference))
    assert len(monthly)==24
    return dict(ending_reference_nav=reference_nav,ending_strategy_nav=nav,difference_dollars=nav-reference_nav,
                monthly=monthly,paired_month_interval=models.block_interval([r['difference'] for r in monthly]),
                yearly_mean_month_difference={y:float(np.mean([r['difference'] for r in monthly if r['month'].startswith(y)])) for y in ['2022','2023']},daily=rows)

def summarize_ensemble(refs,metrics,fixed,load=True):
    bad=[name for name,r in metrics.items() if r['status']!='COMPLETE_ACCOUNTING' or r['final_nav'] is None]
    out=dict(count=len(metrics),incomplete=bad,all_complete=not bad)
    if bad:return out
    vals=np.array([r['final_nav'] for r in metrics.values()]);out.update(mean_ending_nav=float(vals.mean()),median_ending_nav=float(np.median(vals)),min_ending_nav=float(vals.min()),max_ending_nav=float(vals.max()),
        controls_below_fixed=int(sum(vals<fixed)),fixed_minus_mean_dollars=float(fixed-vals.mean()),
        mean_stock_exposure=float(np.mean([r['mean_stock_exposure'] for r in metrics.values()])),
        mean_buys=float(np.mean([r['buys'] for r in metrics.values()])),mean_traded_notional=float(np.mean([r['traded_notional'] for r in metrics.values()])),
        halted_controls=sum(r['stopped'] for r in metrics.values()))
    if load:
        paths=np.array([[float(d['nav']) for d in read(ROOT/ref['file'])['daily']] for ref in refs.values()])
        avg=paths.mean(axis=0);out['mean_account_nav_path']=avg.tolist()
    return out

def run():
    assert not (HERE/'results.json').exists(),'Preserve recorded outcomes.'
    assert read(HERE/'verification-before.json')['passed']
    spec,predictions,rows,frames,actions,references=load_inputs()
    assert datetime.now(timezone.utc)<datetime.fromisoformat(spec['deadline_utc'])
    write(HERE/'run-freeze.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),code={p.name:sha(p) for p in HERE.glob('*.py')},protocol_sha256=sha(HERE/'protocol.json')))
    cached=read(OLD/'evaluation-result.json');schedules={};orders={};accounts={};refs={};metrics={}
    for name in ['fixed','ridge']+[f'unranked_{s:02}' for s in spec['control_seeds']]:
        seed=int(name[-2:]) if name.startswith('unranked') else None
        candidates,keep,order=schedule(predictions,name,seed);schedules[name]=(candidates,keep);orders[name]=order
        for cost in ['base','stress']:
            key=name+'-'+cost
            if seed is None:
                ref=cached['account_files'][key];a=read(ROOT/ref['file']);assert sha(ROOT/ref['file'])==ref['sha256']
            else:
                a=portfolio.simulate(calendar=models.SESSIONS,prices=frames,candidates=candidates,actions=actions,cost_case=cost,rank_mode='matched',retention_by_day=keep)
                ref=save_account(key,a)
            accounts[key]=a;refs[key]=ref;metrics[key]=extras(a)
        print(name,'strict accounts recorded',flush=True)
    write(HERE/'orders.json',orders)
    variants={}
    for scenario,value,payment in scenarios(spec):
        prices,events=scenario_inputs(frames,actions,value,payment);vr={};vm={}
        for key,original in accounts.items():
            if metrics[key]['ZBH_shares_before_spinoff']==0:
                vr[key]=refs[key];vm[key]=metrics[key];continue
            name,cost=key.rsplit('-',1);candidates,keep=schedules[name]
            a=portfolio.simulate(calendar=models.SESSIONS,prices=prices,candidates=candidates,actions=events,cost_case=cost,rank_mode='matched',retention_by_day=keep)
            vr[key]=save_account(key+'-'+scenario,a);vm[key]=extras(a)
        variants[scenario]=dict(assumed_cash_per_ZIMV=value,cash_available_date=payment,account_files=vr,metrics=vm)
        print('Receipt scenario recorded:',scenario,flush=True)
    universe=daily_universe_returns(predictions,references);write(RAW/'universe-reference.json',universe)
    exposure={cost:exposure_reference(accounts['fixed-'+cost],universe) for cost in ['base','stress']}
    for cost,result in exposure.items():
        write(RAW/('fixed-'+cost+'-exposure-reference.json'),result)
    ensembles={}
    for scenario,variant in [('strict',dict(account_files=refs,metrics=metrics))]+list(variants.items()):
        ensembles[scenario]={}
        for cost in ['base','stress']:
            cr={k:v for k,v in variant['account_files'].items() if k.startswith('unranked') and k.endswith('-'+cost)}
            cm={k:variant['metrics'][k] for k in cr}
            ensembles[scenario][cost]=summarize_ensemble(cr,cm,metrics['fixed-'+cost]['final_nav'])
    # The old forecasts and all source artifacts must survive untouched.
    intact()
    write(HERE/'results.json',dict(status='EXPLORATORY_CACHED_DATA_FOLLOWUP',strict=dict(account_files=refs,metrics=metrics),receipt_scenarios=variants,
          control_ensembles=ensembles,exposure_reference={k:{n:v for n,v in r.items() if n!='daily'} for k,r in exposure.items()},
          new_model_fits=0,new_paid_data_usd=0,new_network_data_requests=0,reserved_strategy_prices_opened=False,finished_utc=datetime.now(timezone.utc).isoformat()))
    print('Follow-up outcomes saved.',flush=True)

if __name__=='__main__':run()
