"""Offline accounting and paired comparison helpers; no strategy choices."""
from collections import defaultdict
from decimal import Decimal as D
from functools import lru_cache
import gzip,json,math
import numpy as np
from prepare import HERE,ROOT,RAW,load,sha,write,intact


def verify_freezes():
    intact()
    for name in ('input-freeze.json','evaluation-freeze.json'):
        for path,digest in load(HERE/name)['files'].items():assert sha(ROOT/path)==digest,path


def saved(ref):
    path=ROOT/ref['file'];assert sha(path)==ref['sha256'],str(path)
    return load(path)


def save(name,obj):
    path=RAW/(name+'.json.gz')
    assert not path.exists(),str(path)
    path.write_bytes(gzip.compress(json.dumps(obj,sort_keys=True,allow_nan=False).encode(),mtime=0))
    return dict(file=str(path.relative_to(ROOT)),sha256=sha(path))


def augment_metrics(account,metric):
    valid=[r for r in account['daily'] if r['nav'] is not None]
    exposures=[(sum(float(h['quantity'])*float(h['qualified_close']) for h in r['holdings'].values())+float(r.get('market_sensitive_claim_value',0)))/float(r['nav']) for r in valid]
    notional=sum(float(f['notional']) for f in account['fills'])
    metric.update(fills=len(account['fills']),traded_notional=notional,
        one_way_turnover_over_initial_equity=notional/20000,
        mean_stock_exposure=float(np.mean(exposures)) if valid else None,
        mean_settled_cash=float(np.mean([float(r['settled_cash']) for r in valid])) if valid else None,
        exposure_basis='All days' if len(valid)==len(account['daily']) else 'Only priced prefix; not full-period exposure',
        max_holdings=max(len(r['holdings']) for r in account['daily']),
        forced_extra_holding_days=sum(len(r['holdings'])>10 for r in account['daily']))
    return metric


def selection_checks(account,schedule):
    orders={r['month']:r for r in schedule['orders']};prior=D(10000);count=0
    byday=defaultdict(list)
    for f in account['fills']:byday[f['date']].append(f)
    for row in account['daily']:
        for f in byday[row['date']]:
            if f['side']=='buy':
                order=orders[f['date'][:7]]
                assert f['security_id'] in order['all_symbols'][:order['entry_count']]
                assert prior is not None
                assert D(f['notional'])+D(f['fee_total'])<=min(D(800),D('.08')*prior)
                count+=1
        prior=D(row['nav']) if row['nav'] is not None else None
    return dict(buys_in_frozen_top_decile=count,buy_size_limits_checked=True)


def reference(account,universe):
    """Same original exposure/cost recurrence, retaining any unresolved prefix."""
    assert len(account['daily'])==len(universe)
    costs=defaultdict(float)
    for f in account['fills']:costs[f['date']]+=float(f['fee_total'])+float(f['slippage_cost'])
    prior=bench=10000.;stock=0.;paths=[];gap=None
    for row,u in zip(account['daily'],universe):
        assert row['date']==u['date']
        if row['nav'] is None or u['universe_return'] is None:
            gap=dict(date=row['date'],account_nav_missing=row['nav'] is None,reference_missing=u.get('missing',[]));break
        weight=stock/prior;cost=costs[row['date']]/prior;rr=weight*u['universe_return']-cost
        nav=float(row['nav']);sr=nav/prior-1;bench*=1+rr
        paths.append(dict(date=row['date'],strategy_nav=nav,reference_nav=bench,lagged_stock_exposure=weight,
                          strategy_return=sr,reference_return=rr,universe_return=u['universe_return'],cost_return=cost))
        stock=sum(float(h['quantity'])*float(h['qualified_close']) for h in row['holdings'].values())+float(row.get('market_sensitive_claim_value',0));prior=nav
    complete=len(paths)==len(account['daily'])
    result=dict(complete=complete,days=len(paths),first_gap=gap,ending_nav=bench if complete else None,
                selection_difference=prior-bench if complete else None,
                qualification='Non-executable equal-eligible-universe attribution at each strategy\'s own lagged stock exposure and actual dated costs; no sector/beta adjustment or cash interest.')
    # Independent Decimal reconstruction, including the initial day and any
    # floating fractional-stock entitlement. An incomplete prefix stays partial.
    charges=defaultdict(lambda:D(0))
    for f in account['fills']:charges[f['date']]+=D(f['fee_total'])+D(f['slippage_cost'])
    prev=target=D(10000);equity=D(0)
    for row,p,u in zip(account['daily'],paths,universe):
        rr=equity/prev*D(str(u['universe_return']))-charges[row['date']]/prev
        target*=1+rr
        assert abs(target-D(str(p['reference_nav'])))<D('.0000001')
        assert abs(equity/prev-D(str(p['lagged_stock_exposure'])))<D('.0000000001')
        prev=D(row['nav']);equity=sum((D(h['quantity'])*D(h['qualified_close']) for h in row['holdings'].values()),D(0))+D(row.get('market_sensitive_claim_value','0'))
    if complete:assert abs(prev-target-D(str(result['selection_difference'])))<D('.0000001')
    return result,paths,dict(days=len(paths),complete=complete,decimal_reference_reconciled=True)


@lru_cache(maxsize=None)
def interval(values):
    if not values:return None
    values=np.asarray(values,dtype=float);rng=np.random.default_rng(20260914);n=len(values);means=[]
    for _ in range(2000):
        indices=[int(rng.integers(n))]
        for i in range(1,n):indices.append(int(rng.integers(n)) if rng.random()<1/12 else (indices[-1]+1)%n)
        means.append(float(values[indices].mean()))
    return dict(mean=float(values.mean()),ci95=list(map(float,np.quantile(means,[.025,.975]))),months=n,
                resamples=2000,expected_block_months=12,seed=20260914,
                limitation='Exploratory resampling of already-seen months; few independent regimes, no correction for the project\'s earlier searches, not a probability of future profitability.')


def months(paths,sessions):
    out=[]
    for month in sorted({r['date'][:7] for r in paths}):
        if month=='2026-09':continue
        rows=[r for r in paths if r['date'].startswith(month)]
        if [r['date'] for r in rows]!=[d for d in sessions if d[:7]==month]:continue
        strategy=math.prod(1+r['strategy_return'] for r in rows)-1
        benchmark=math.prod(1+r['reference_return'] for r in rows)-1
        out.append(dict(month=month,strategy_return=strategy,reference_return=benchmark,difference=strategy-benchmark))
    return out


def paired(before,after):
    complete=before['metrics']['status']==after['metrics']['status']=='COMPLETE_ACCOUNTING' and before['reference']['complete'] and after['reference']['complete']
    if not complete:return dict(complete=False,full_period_comparison=None,reason='At least one account/reference remains unresolved; no full-period return is inferred from its priced prefix.')
    keys=['profit','cagr','max_drawdown','fees','slippage','fills','traded_notional','one_way_turnover_over_initial_equity','mean_stock_exposure']
    delta={k:after['metrics'][k]-before['metrics'][k] for k in keys}
    delta['selection_difference']=after['reference']['selection_difference']-before['reference']['selection_difference']
    bm={r['month']:r for r in before['monthly']};am={r['month']:r for r in after['monthly']};assert bm.keys()==am.keys()
    rows=[dict(month=m,strategy_return_change=am[m]['strategy_return']-bm[m]['strategy_return'],selection_return_change=am[m]['difference']-bm[m]['difference']) for m in sorted(bm)]
    return dict(complete=True,after_minus_before=delta,monthly=rows,
                strategy_return_change_interval=interval(tuple(r['strategy_return_change'] for r in rows)),
                selection_return_change_interval=interval(tuple(r['selection_return_change'] for r in rows)))
