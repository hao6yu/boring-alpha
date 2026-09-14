#!/usr/bin/env python3
"""One frozen annual-refit linear/tree comparison, plus fixed-score reference."""
from datetime import datetime, timezone
import hashlib,json,math,sys
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from scipy.stats import spearmanr
from panel import HERE,ROOT,RAW,FEATURES,SESSIONS,price_features
from reviewed_sources import LIFECYCLE,CASH_OVERRIDES,SPINS
from probe import sha,write
import portfolio


def transformed(rows):
    data=pd.DataFrame([r['features'] for r in rows],columns=FEATURES,dtype=float)
    ranks=data.rank(pct=True,method='average')-.5
    return np.c_[ranks.fillna(0).to_numpy(),data.isna().to_numpy().astype(float)]

def train_weights(months):
    _,inverse,counts=np.unique(months,return_inverse=True,return_counts=True)
    w=1/counts[inverse];return w/w.mean()

def block_interval(values):
    v=np.asarray(values,dtype=float);n=len(v);rng=np.random.default_rng(20260914);means=[]
    for _ in range(2000):
        indices=[rng.integers(n)]
        for i in range(1,n):indices.append(rng.integers(n) if rng.random()<1/12 else (indices[-1]+1)%n)
        means.append(float(v[indices].mean()))
    return dict(mean=float(v.mean()),ci95=list(map(float,np.quantile(means,[.025,.975]))),months=n,expected_block_months=12,
                caveat='Twenty-four seen months give weak regime evidence. This resamples months, not independent stocks.')

def account_frames():
    series,audit,inventory=price_features();frames={d:{} for d in SESSIONS};actions=[]
    for s,rs in series.items():
        for d,r in rs.items():
            # Raw action fields are replaced only by source-reviewed ordinary
            # units/cash. Unknown corporate events remain explicit held gaps.
            frames[d][s]=dict(close=str(r['close']),volume=str(r['volume']),qualified=r['qualified'],status='listed',
                              splitFactor=str(r['actual_units_factor']),divCash=str(r['cash_dividend']))
            if d<'2022-01-01':continue
            if r['cash_dividend']:
                actions.append(dict(action_id=f'{s}:{d}:dividend',security_id=s,effective_date=d,type='dividend',verified=not r['issues'],
                                    amount_per_share=str(r['cash_dividend']),cash_available_date=CASH_OVERRIDES.get((s,d),{}).get('payment_date')))
            if r['actual_units_factor']!=1:
                actions.append(dict(action_id=f'{s}:{d}:split',security_id=s,effective_date=d,type='split',verified=not r['issues'],factor=str(r['actual_units_factor'])))
            if (s,d) in SPINS or any('UNCLASSIFIED' in x or 'LARGE_DISTRIBUTION' in x for x in r['issues']):
                actions.append(dict(action_id=f'{s}:{d}:unresolved_distribution',security_id=s,effective_date=d,type='stock_distribution',verified=False,
                                    amount_per_share='0',cash_available_date=None,entitlement_source=SPINS.get((s,d)),reason='Delivery and any fractional cash not qualified for whole-share account.'))
    for s,event in LIFECYCLE.items():
        d=event.get('event_date')
        if not d or not '2022-01-01'<=d<'2024-01-01':continue
        if event['outcome']=='CASH_MERGER':
            actions.append(dict(action_id=f'{s}:{d}:merger_cash',security_id=s,effective_date=d,type='merger_cash',verified=True,
                                amount_per_share=str(event['cash']),cash_available_date=None,source=event['source']))
        for day in SESSIONS:
            if day>event['end']:frames[day][s]=dict(status='halted',qualified=False,missing_provider_row=True)
    return frames,actions

def metrics(acct):
    days=acct['daily'];nav=[float(d['nav']) if d['nav'] is not None else None for d in days]
    out=dict(status=acct['status'],stopped=acct['stopped'],stop_date=acct['stop_date'],buys=sum(f['side']=='buy' for f in acct['fills']),
             unpriced_days=sum(x is None for x in nav),final_nav=None,profit=None,cagr=None,max_drawdown=None,
             fees=sum(float(f['fee_total']) for f in acct['fills']),slippage=sum(float(f['slippage_cost']) for f in acct['fills']))
    if any(x is None for x in nav):return out
    arr=np.array(nav);peaks=np.maximum.accumulate(np.r_[10000,arr])[1:];elapsed=(pd.Timestamp(days[-1]['date'])-pd.Timestamp(days[0]['date'])).days+1
    out.update(final_nav=nav[-1],profit=nav[-1]-10000,cagr=(nav[-1]/10000)**(365/elapsed)-1,max_drawdown=float(np.max(1-arr/peaks)),
               ending_cash=float(acct['ending_settled_cash']),unpaid_claims=sum(float(c['amount']) for c in acct['claims'] if not c['paid']),
               gross_same_fills_profit=nav[-1]-10000+out['fees']+out['slippage'],
               cash_reference_end_values={str(rate):10000*(1+rate)**(elapsed/365) for rate in [.04,.06]})
    return out

def run():
    start=json.loads((HERE/'experiment-start.json').read_text());assert datetime.now(timezone.utc)<datetime.fromisoformat(start['deadline_utc'])
    assert not (HERE/'evaluation-result.json').exists(),'Do not overwrite outcomes or silently retune.'
    coverage=json.loads((HERE/'panel-coverage.json').read_text())
    conditional='--conditional' in sys.argv
    assert coverage['aggregate_comparison_coverage_pass'] or conditional
    pm=json.loads((HERE/'price-manifest.json').read_text())
    cohort=json.loads((HERE.parent/'ml-free-data-preparation-2026-09-13/next-cohort.json').read_text())['rows']
    assert all(r['Symbol'] in pm['symbols'] for r in cohort), 'Do not fit while original stock requests are still pending.'
    verify=json.loads((HERE/'verification.json').read_text());assert verify['passed']
    b=(ROOT/coverage['panel_file']).read_bytes();assert sha(b)==coverage['panel_sha256'];all_rows=json.loads(b)
    before=dict(at_utc=datetime.now(timezone.utc).isoformat(),panel_sha256=sha(b),code={p.name:sha(p.read_bytes()) for p in HERE.glob('*.py')},
                scope_sha256=start['scope_sha256'],manifests={n:sha((HERE/n).read_bytes()) for n in ['price-manifest.json','sec-manifest.json','identity-map.json','account-policy.json']},
                models_fitted_before_freeze=False,eligible_universe='Known eligible subset of frozen 100 original slots; see coverage.',
                label_benchmark='Equal mean of known eligible labels within month; any unavailable label means the benchmark is conditional.')
    write(HERE/'evaluation-start.json',before)
    eligible=[r for r in all_rows if r['eligible']];by_month={};xy={}
    for month in sorted({r['month'] for r in eligible}):
        rs=[r for r in eligible if r['month']==month];X=transformed(rs)
        known=[r['label_return'] for r in rs if r['label_return'] is not None];mean=np.mean(known) if known else np.nan
        y=np.array([r['label_return']-mean if r['label_return'] is not None else np.nan for r in rs]);by_month[month]=rs;xy[month]=(X,y)
    predictions=[];fit_audit=[]
    for year in [2022,2023]:
        training=[m for m in xy if m<f'{year}-01'];X=np.concatenate([xy[m][0] for m in training]);y=np.concatenate([xy[m][1] for m in training]);ms=np.concatenate([[m]*len(xy[m][1]) for m in training]);mask=np.isfinite(y)
        X,y,ms=X[mask],y[mask],ms[mask];weights=train_weights(ms)
        linear=Ridge(alpha=100,fit_intercept=True)
        tree=HistGradientBoostingRegressor(loss='squared_error',learning_rate=.05,max_iter=150,max_leaf_nodes=15,min_samples_leaf=100,l2_regularization=10,early_stopping=False,random_state=20260914)
        linear.fit(X,y,sample_weight=weights);tree.fit(X,y,sample_weight=weights)
        fit_audit.append(dict(year=year,training_last_month=max(ms),training_rows=len(y),training_months=len(set(ms)),monthly_weight_sums={m:float(weights[ms==m].sum()) for m in sorted(set(ms))}))
        for month in [m for m in xy if m.startswith(str(year))]:
            X,y=xy[month];lp=linear.predict(X);tp=tree.predict(X);fp=(X[:,0]+X[:,1]+X[:,2]+X[:,3]+X[:,4]-X[:,5])/6
            for r,target,l,t,f in zip(by_month[month],y,lp,tp,fp):
                predictions.append(dict(symbol=r['symbol'],cik=r['cik'],month=month,cut=r['cut'],entry=r['entry'],label_excess=float(target) if np.isfinite(target) else None,
                                        ridge=float(l),tree=float(t),fixed=float(f)))
    monthly=[]
    for month in sorted({r['month'] for r in predictions}):
        rs=[r for r in predictions if r['month']==month and r['label_excess'] is not None]
        item=dict(month=month,known_labels=len(rs))
        for name in ['ridge','tree','fixed']:item[name]=float(spearmanr([r[name] for r in rs],[r['label_excess'] for r in rs]).statistic)
        item['tree_minus_ridge']=item['tree']-item['ridge'];monthly.append(item)
    write(RAW/'predictions.json',predictions);write(HERE/'fit-audit.json',fit_audit)
    frames,actions=account_frames();accounts={};refs={}
    for name in ['ridge','tree','fixed']:
        candidates=[];keep={}
        for month in sorted({r['month'] for r in predictions}):
            rs=sorted([r for r in predictions if r['month']==month],key=lambda r:(-r[name],r['symbol']));n=len(rs);day=rs[0]['entry'];keep[day]=[r['symbol'] for r in rs[:math.ceil(.2*n)]]
            for rank,r in enumerate(rs[:math.ceil(.1*n)]):
                candidates.append(dict(event_id=f'{name}:{month}:{r["symbol"]}',security_id=r['symbol'],cik=r['cik'],signal_date=r['cut'],score=r[name],eligibility_status='READY',selection_key=f'{rank:04}:{r["symbol"]}'))
        for cost in ['base','stress']:
            acct=portfolio.simulate(calendar=SESSIONS,prices=frames,candidates=candidates,actions=actions,cost_case=cost,rank_mode='matched',retention_by_day=keep)
            key=f'{name}-{cost}';path=RAW/(key+'-account.json');write(path,acct);accounts[key]=metrics(acct);refs[key]=dict(file=str(path.relative_to(ROOT)),sha256=sha(path.read_bytes()))
    result=dict(status='EXPLORATORY_MODEL_COMPARISON_NO_VALIDATION_OR_LIVE_APPROVAL',
                aggregate_coverage_pass=coverage['aggregate_comparison_coverage_pass'],
                conditional_identified_subset_only=not coverage['aggregate_comparison_coverage_pass'],monthly_rank_correlations=monthly,
                rank_correlation_intervals={k:block_interval([m[k] for m in monthly]) for k in ['ridge','tree','fixed','tree_minus_ridge']},
                yearly_mean_rank_correlations={y:{k:float(np.mean([m[k] for m in monthly if m['month'].startswith(y)])) for k in ['ridge','tree','fixed','tree_minus_ridge']} for y in ['2022','2023']},
                accounts=accounts,account_files=refs,new_paid_data_usd=0,reserved_prices_opened=False)
    write(HERE/'evaluation-result.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':run()
