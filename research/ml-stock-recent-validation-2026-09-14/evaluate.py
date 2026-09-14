"""One fixed-score evaluation after the new source/implementation freeze."""
from collections import defaultdict
from datetime import datetime,timezone
import json
import math
import numpy as np
import pandas as pd
import recent as r
from acquire import HERE,ROOT,RAW,OLD,load,write,sha,scope


def predictions_and_schedule():
    coverage=load(HERE/'panel-coverage.json');rows=load(ROOT/coverage['panel_file'])
    predictions=[];candidates=[];keep={};orders=[]
    for month in sorted({x['month'] for x in rows}):
        eligible=[x for x in rows if x['month']==month and x['eligible']]
        if not eligible:raise RuntimeError('No qualified eligible universe: '+month)
        x=r.m.transformed(eligible);score=(x[:,0]+x[:,1]+x[:,2]+x[:,3]+x[:,4]-x[:,5])/6
        group=[dict(symbol=row['symbol'],cik=row['cik'],month=month,cut=row['cut'],entry=row['entry'],fixed=float(value)) for row,value in zip(eligible,score)]
        predictions.extend(group);group.sort(key=lambda x:(-x['fixed'],x['symbol']))
        n=len(group);day=group[0]['entry'];keep[day]=[x['symbol'] for x in group[:math.ceil(.2*n)]]
        orders.append(dict(month=month,entry_date=day,all_symbols=[x['symbol'] for x in group],entry_count=math.ceil(.1*n),retention_count=math.ceil(.2*n)))
        for rank,row in enumerate(group[:math.ceil(.1*n)]):
            candidates.append(dict(event_id=f'fixed:{month}:{row["symbol"]}',security_id=row['symbol'],cik=row['cik'],signal_date=row['cut'],score=row['fixed'],eligibility_status='READY',selection_key=f'{rank:04}:{row["symbol"]}'))
    return predictions,candidates,keep,orders


def universe_returns(predictions,references):
    monthly={month:sorted(x['symbol'] for x in predictions if x['month']==month) for month in sorted({x['month'] for x in predictions})}
    out=[]
    for day in [d for d in r.SESSIONS if r.START<=d<=r.END]:
        values=[];missing=[]
        previous_day=r.SESSIONS[r.INDEX[day]-1]
        for symbol in monthly[day[:7]]:
            life=r.p.LIFECYCLE.get(symbol,{})
            if life.get('event_date','9999')<=day:
                if life['outcome']=='CASH_MERGER':
                    value=life['cash']/references[symbol][life['end']]['close']-1 if day==life['event_date'] else 0.
                elif life['outcome'] in ('STOCK_MERGER','CASH_AND_STOCK_MERGER'):
                    child=r.child_rows(life['child']);current=child.get(day);previous=child.get(previous_day)
                    if current is None or (day!=life['event_date'] and previous is None) or current['splitFactor']!=1:
                        missing.append(symbol);continue
                    cash=life.get('cash',0);ratio=life['ratio']
                    if day==life['event_date']:value=(cash+ratio*current['close'])/references[symbol][life['end']]['close']-1
                    else:value=(cash+ratio*(current['close']+current['divCash']))/(cash+ratio*previous['close'])-1
                else:missing.append(symbol);continue
            else:
                gross=references.get(symbol,{}).get(day,{}).get('gross')
                if gross is None:missing.append(symbol);continue
                value=gross-1
            values.append(value)
        out.append(dict(date=day,eligible_names=len(monthly[day[:7]]),known_names=len(values),missing=missing,universe_return=None if missing or not values else float(np.mean(values))))
    return out


def exposure_reference(account,universe):
    costs=defaultdict(float)
    for f in account['fills']:costs[f['date']]+=float(f['fee_total'])+float(f['slippage_cost'])
    prior_nav=reference_nav=10000.;prior_stock=0.;rows=[];gap=None
    for day,u in zip(account['daily'],universe):
        assert day['date']==u['date']
        if day['nav'] is None or u['universe_return'] is None:
            gap=dict(date=day['date'],account_nav_missing=day['nav'] is None,reference_missing=u['missing']);break
        weight=prior_stock/prior_nav;cost=costs[day['date']]/prior_nav
        reference_return=weight*u['universe_return']-cost
        nav=float(day['nav']);actual_return=nav/prior_nav-1;reference_nav*=1+reference_return
        rows.append(dict(date=day['date'],strategy_nav=nav,reference_nav=reference_nav,lagged_stock_exposure=weight,strategy_return=actual_return,reference_return=reference_return,universe_return=u['universe_return'],cost_return=cost))
        prior_stock=sum(float(h['quantity'])*float(h['qualified_close']) for h in day['holdings'].values());prior_nav=nav
    complete=len(rows)==len(account['daily'])
    out=dict(complete=complete,days=len(rows),first_gap=gap,ending_nav=reference_nav if complete else None,selection_difference=prior_nav-reference_nav if complete else None,
             qualification='Fractional equal-eligible-universe daily return at actual lagged stock exposure, subtracting actual dated fee/slippage rate. Not executable, not sector/beta adjusted, no cash interest.')
    return out,rows


def yearly(account):
    previous=10000.;out={}
    for year in ('2024','2025','2026'):
        rows=[d for d in account['daily'] if d['date'].startswith(year)]
        if not rows:continue
        ending=float(rows[-1]['nav']) if rows[-1]['nav'] is not None else None
        complete=all(d['nav'] is not None for d in rows) and previous is not None
        out[year]=dict(first_date=rows[0]['date'],last_date=rows[-1]['date'],start_nav=previous,ending_nav=ending,return_fraction=ending/previous-1 if complete else None,profit=ending-previous if complete else None,year_to_date=year=='2026')
        previous=ending if complete else None
    return out


def uncertainty(paths):
    monthly=[]
    for month in sorted({x['date'][:7] for x in paths}):
        if month==r.END[:7]:continue
        rows=[x for x in paths if x['date'].startswith(month)]
        expected=[d for d in r.SESSIONS if d[:7]==month]
        if [x['date'] for x in rows]!=expected:continue
        strategy=math.prod(1+x['strategy_return'] for x in rows)-1
        reference=math.prod(1+x['reference_return'] for x in rows)-1
        monthly.append(dict(month=month,strategy_return=strategy,reference_return=reference,difference=strategy-reference))
    if not monthly:return dict(monthly=[],interval=None)
    v=np.array([x['difference'] for x in monthly]);rng=np.random.default_rng(20260914);means=[]
    for _ in range(2000):
        indices=[int(rng.integers(len(v)))]
        for i in range(1,len(v)):indices.append(int(rng.integers(len(v))) if rng.random()<1/12 else (indices[-1]+1)%len(v))
        means.append(float(v[indices].mean()))
    return dict(monthly=monthly,interval=dict(mean=float(v.mean()),ci95=list(map(float,np.quantile(means,[.025,.975]))),months=len(v),resamples=2000,expected_block_months=12,seed=20260914,limitation='Few calendar years, selection after the earlier experiment, and dependence across months limit inference; this is not a probability of profitable trading.'))


def main():
    scope();assert load(HERE/'verification-before.json')['passed']
    assert not (HERE/'evaluation-result.json').exists(),'Completed result must not be overwritten or retuned'
    files=list(HERE.glob('*.py'))+[HERE/name for name in ['protocol.json','account-policy.json','panel-coverage.json','fundamental-coverage.json','price-manifest.json','sec-manifest.json','verification-before.json']]
    files+=[ROOT/load(HERE/'panel-coverage.json')['panel_file'],ROOT/load(HERE/'fundamental-coverage.json')['source_file']]
    freeze=HERE/'evaluation-freeze.json'
    snapshot=dict(at_utc=datetime.now(timezone.utc).isoformat(),files={str(p.relative_to(ROOT)):sha(p) for p in files},model_fits=0,parameter_searches=0)
    if freeze.exists():
        for name,h in load(freeze)['files'].items():assert sha(ROOT/name)==h,name
    else:write(freeze,snapshot)
    predictions,candidates,keep,orders=predictions_and_schedule()
    write(RAW/'predictions.json',predictions);write(HERE/'orders.json',orders)
    frames,actions,reference_prices=r.account_inputs();universe=universe_returns(predictions,reference_prices)
    write(RAW/'universe-returns.json',universe)
    results={};refs={};benchmarks={};intervals={}
    for cost in ('base','stress'):
        account=r.portfolio.simulate(calendar=r.SESSIONS,prices=frames,candidates=candidates,actions=actions,cost_case=cost,rank_mode='matched',retention_by_day=keep)
        path=RAW/f'fixed-{cost}-account.json';write(path,account);refs[cost]=dict(file=str(path.relative_to(ROOT)),sha256=sha(path))
        metric=r.m.metrics(account);metric['yearly']=yearly(account)
        valid=[x for x in account['daily'] if x['nav'] is not None]
        metric['mean_stock_exposure']=float(np.mean([sum(float(h['quantity'])*float(h['qualified_close']) for h in x['holdings'].values())/float(x['nav']) for x in valid])) if valid else None
        results[cost]=metric;benchmark,paths=exposure_reference(account,universe);benchmarks[cost]=benchmark
        write(RAW/f'{cost}-reference-path.json',paths);intervals[cost]=uncertainty(paths)
    output=dict(status='FROZEN_RECENT_WINDOW_HISTORICAL_EVALUATION',evaluation_start=r.START,evaluation_end=r.END,accounts=results,account_files=refs,exposure_references=benchmarks,selection_uncertainty=intervals,
                seen_2022_2023_source=str(OLD/'evaluation-result.json'),new_paid_data_usd=0,model_fits=0,parameter_searches=0)
    write(HERE/'evaluation-result.json',output);scope()
    print(json.dumps(dict(accounts=results,exposure_references=benchmarks),indent=2))


if __name__=='__main__':main()
