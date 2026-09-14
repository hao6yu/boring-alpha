"""Pure account metrics; unchanged economics from the prior diagnostic."""
from collections import Counter, defaultdict
from datetime import date
import numpy as np

def bootstrap(values):
    if any(v is None for v in values):
        return {'status':'UNRESOLVED_PAIRED_DAILY_RETURNS'}
    x=np.asarray(values,dtype=float); rng=np.random.Generator(np.random.PCG64(20260914))
    idx=rng.integers(0,len(x),size=2000); total=x[idx].copy()
    for _ in range(1,len(x)):
        restart=rng.random(2000)<.05; fresh=rng.integers(0,len(x),size=2000)
        idx=np.where(restart,fresh,(idx+1)%len(x)); total+=x[idx]
    draws=252*total/len(x); low,high=np.quantile(draws,[.025,.975],method='linear')
    return {'status':'DESCRIPTIVE_ONLY','estimand':'annualized arithmetic mean daily account return difference',
        'estimate':float(252*x.mean()),'lower_95':float(low),'upper_95':float(high),
        'seed':20260914,'replicates':2000,'expected_block_sessions':20,'observations':len(x),
        'limitations':'Short, sparse, already-explored history; no issuer-cluster or multiple-search correction. Not an independent validation.'}


def metrics(account):
    initial=float(account['initial_capital']); daily=account['daily']
    valid=all(d['nav'] is not None for d in daily)
    out={'accounting_status':account['status'],'daily_nav_complete':valid,'completed_positions':len(account['completed_positions']),
         'buy_fills':sum(f['side']=='buy' for f in account['fills']),'decision_states':dict(Counter(d['status'] for d in account['decisions'])),
         'stopped':account['stopped'],'stop_date':account['stop_date'],'unresolved_candidate_ids':account['unresolved_candidate_ids'],
         'unpriced_days':len(account['unpriced_days']),'open_stock_lots':len(account['open_holdings']),
         'initial_capital_usd':initial,'ending_nav_usd':None,'net_profit_usd':None,'cagr':None,'max_drawdown_fraction':None}
    if not valid: return out
    nav=np.array([float(d['nav']) for d in daily]); days=(date.fromisoformat(daily[-1]['date'])-date.fromisoformat(daily[0]['date'])).days+1
    peaks=np.maximum.accumulate(np.r_[initial,nav])[1:]
    fees=sum(float(f['fee_total']) for f in account['fills']); slip=sum(float(f['slippage_cost']) for f in account['fills'])
    active={f['date'][:7] for f in account['fills']}|{d['date'][:7] for d in daily if d['holdings']}
    equity=[sum(float(h['quantity'])*float(h['qualified_close']) for h in d['holdings'].values()) for d in daily]
    out.update(ending_nav_usd=float(nav[-1]),net_profit_usd=float(nav[-1]-initial),cagr=float((nav[-1]/initial)**(365/days)-1),
        total_return=float(nav[-1]/initial-1),max_drawdown_fraction=float(np.max(1-nav/peaks)),max_drawdown_usd=float(np.max(peaks-nav)),
        commissions_and_regulatory_usd=fees,slippage_usd=slip,gross_same_fills_profit_usd=float(nav[-1]-initial+fees+slip),
        gross_same_fills_cagr=float(((nav[-1]+fees+slip)/initial)**(365/days)-1),
        active_months=len(active),average_stock_exposure_fraction=float(np.mean(np.array(equity)/nav)),
        average_settled_cash_fraction=float(np.mean([float(d['settled_cash'])/float(d['nav']) for d in daily])),
        ending_settled_cash_usd=float(account['ending_settled_cash']),
        ending_unpaid_claims_usd=sum(float(c['amount']) for c in account['claims'] if not c['paid']),
        ending_locked_dividend_claims_usd=sum(float(c['amount']) for c in account['claims'] if not c['paid'] and c['type']=='dividend'),
        calendar_days=days)
    last=initial; monthly=[]
    for month in sorted({d['date'][:7] for d in daily}):
        end=next(d for d in reversed(daily) if d['date'][:7]==month); current=float(end['nav'])
        monthly.append({'month':month,'net_profit_usd':current-last,'return':current/last-1,'ending_nav_usd':current})
        last=current
    out['monthly']=monthly
    by_issuer=defaultdict(float); position_returns=[]
    for h in account['completed_positions']:
        dividend=sum(float(c['amount']) for c in account['claims'] if c['event_id']==h['event_id'] and c['type']=='dividend')
        pnl=float(h['net_sale_proceeds'])+dividend-float(h['cost_basis'])
        by_issuer[h['cik']]+=pnl
        position_returns.append({'event_id':h['event_id'],'cik':h['cik'],'net_profit_usd':pnl,'return':pnl/float(h['cost_basis'])})
    out['issuer_net_profit_usd']=dict(sorted(by_issuer.items(),key=lambda kv:-kv[1]))
    out['position_results']=position_returns
    out['positive_position_fraction']=sum(p['net_profit_usd']>0 for p in position_returns)/len(position_returns) if position_returns else None
    out['cash_reference_scenarios']=[{'annual_rate':rate,'ending_value_usd':initial*(1+rate)**(days/365),
        'strategy_minus_cash_usd':float(nav[-1])-initial*(1+rate)**(days/365)} for rate in (.04,.06)]
    return out

