"""Independent Decimal ledger replay and benchmark construction checks."""
from collections import defaultdict
from datetime import date,timedelta
from decimal import Decimal as D,ROUND_CEILING
import hashlib,json,math
import numpy as np
from followup import HERE,ROOT,RAW,OLD,read,write,sha,intact,load_inputs,scenario_inputs,schedule,portfolio,models

def before():
    spec,predictions,rows,frames,actions,references=load_inputs()
    candidates,keep,_=schedule(predictions,'fixed')
    replay=portfolio.simulate(calendar=models.SESSIONS,prices=frames,candidates=candidates,actions=actions,cost_case='base',rank_mode='matched',retention_by_day=keep)
    original=read(ROOT/'data/snapshots'/OLD.name/'fixed-base-account.json')
    assert replay==original,'Frozen predictions must exactly reproduce the original fixed account.'
    old_bar=frames['2022-03-01']['ZBH'].copy()
    p,a=scenario_inputs(frames,actions,25.53,'2022-04-01')
    assert frames['2022-03-01']['ZBH']==old_bar and p['2022-03-01']['ZBH'] is not frames['2022-03-01']['ZBH']
    original_action=next(a for a in actions if a['action_id']=='ZBH:2022-03-01:unresolved_distribution')
    changed=next(a for a in a if a['action_id']==original_action['action_id'])
    assert original_action['verified'] is False and original_action['type']=='stock_distribution'
    assert changed['qualification']=='HYPOTHETICAL_CASH_IN_LIEU_NOT_OBSERVED_BROKER_PAYMENT'
    assert D(changed['amount_per_share'])*6==D('15.318')
    assert changed['cash_available_date']=='2022-04-01'
    # Unranked controls cannot change when every prediction/label is changed.
    mutated=[dict(r,fixed=-r['fixed']+10,ridge=1000,label_excess=None) for r in predictions]
    for seed in spec['control_seeds']:
        assert schedule(predictions,f'unranked_{seed:02}',seed)==schedule(mutated,f'unranked_{seed:02}',seed)
    intact()
    write(HERE/'verification-before.json',dict(passed=True,checks=['Exact original fixed-base account reproduction from frozen predictions.',
         'Receipt scenario uses $15.318 for six ZBH shares at the ex-date reference; payment delay and source-input immutability checked.',
         'All 20 control schedules invariant to arbitrary score and label changes.','Original artifact and prediction hashes unchanged.']))
    print('Pre-run checks passed.')

def replay(name,account,frames,actions):
    slip=D('.001') if '-base' in name else D('.005')
    cents=lambda v:v.quantize(D('.01'),rounding=ROUND_CEILING)
    fills=defaultdict(list);events=defaultdict(list)
    for a in actions:events[a['effective_date']].append(a)
    for f in account['fills']:
        d,s=f['date'],f['security_id'];q=D(f['quantity']);close=D(frames[d][s]['close'])
        assert q>0 and q==q.to_integral_value() and close==D(f['raw_close'])
        value=q*close*(1+slip if f['side']=='buy' else 1-slip)
        fee=dict(commission=cents(min(D('.01')*value,max(D(1),D('.005')*q))),
                 sec=cents(D('.0000206')*value) if f['side']=='sell' else D(0),
                 taf=cents(min(D('9.79'),D('.000195')*q)) if f['side']=='sell' else D(0),cat=cents(D('.000003')*q))
        assert value==D(f['notional']) and fee=={k:D(v) for k,v in f['fees'].items()}
        assert sum(fee.values())==D(f['fee_total']) and q*close*slip==D(f['slippage_cost'])
        if f['side']=='buy':assert d==[x for x in models.SESSIONS if x[:7]==d[:7]][1]
        fills[d].append(f)
    cash=high=prior_nav=D(10000);holdings={};claims={};actual_claims={c['claim_id']:c for c in account['claims']};stop=None;checked=0
    for row in account['daily']:
        day=row['date']
        if row['nav'] is None:break
        for c in claims.values():
            if not c['paid'] and c['cash_available_date'] is not None and c['cash_available_date']<=day:
                cash+=D(c['amount']);c['paid']=True
        for action in sorted(events[day],key=lambda a:a['action_id']):
            s,key=action['security_id'],action['action_id']
            if s not in holdings:continue
            assert action['verified'];h=holdings[s]
            if action['type']=='split':
                h['quantity']*=D(action['factor']);assert h['quantity']==h['quantity'].to_integral_value()
            elif action['type'] in ['dividend','merger_cash']:
                c=dict(actual_claims[key],paid=False)
                assert D(c['amount'])==h['quantity']*D(action['amount_per_share'])
                assert c['cash_available_date']==action['cash_available_date']
                claims[key]=c
                if c['cash_available_date'] is not None and c['cash_available_date']<=day:cash+=D(c['amount']);c['paid']=True
                if key=='ZBH:2022-03-01:unresolved_distribution':assert 0<h['quantity']<10
                if action['type']=='merger_cash':del holdings[s]
            else:raise AssertionError('Unqualified held stock distribution cannot have complete NAV.')
        for f in fills[day]:
            s,q=f['security_id'],D(f['quantity']);value,fee=D(f['notional']),D(f['fee_total'])
            if f['side']=='buy':
                assert s not in holdings and stop is None
                assert value+fee<=min(D(800),D('.08')*prior_nav)
                cash-=value+fee;holdings[s]=dict(quantity=q,basis=value+fee)
                assert cash>=2000 and len(holdings)<=10
            else:
                assert holdings[s]['quantity']==q
                c=next(c for c in account['claims'] if c['type']=='sale' and c['event_id']==f['event_id'])
                assert D(c['amount'])==value-fee
                earliest=(date.fromisoformat(day)+timedelta(days=7)).isoformat()
                assert c['cash_available_date']==next((d for d in models.SESSIONS if d>=earliest),None)
                claims[c['claim_id']]=dict(c,paid=False);del holdings[s]
        equity=sum((h['quantity']*D(frames[day][s]['close']) for s,h in holdings.items()),D(0))
        unpaid=sum((D(c['amount']) for c in claims.values() if not c['paid']),D(0));nav=cash+equity+unpaid
        assert nav==D(row['nav']) and cash==D(row['settled_cash']) and unpaid==D(row['unpaid_claim_value'])
        assert set(holdings)==set(row['holdings'])
        high=max(high,nav)
        if high-nav>=2000 and stop is None:stop=day
        assert row['account_stopped']==(stop is not None);checked+=1;prior_nav=nav
    complete=checked==len(account['daily'])
    if complete:
        assert account['status']=='COMPLETE_ACCOUNTING' and not holdings and not account['open_holdings']
        assert nav==D(account['ending_nav']) and stop==account['stop_date']
        pnl=sum((D(c['net_sale_proceeds'])-D(c['cost_basis']) for c in account['completed_positions']),D(0))
        pnl+=sum((D(c['amount']) for c in account['claims'] if c['type']=='dividend'),D(0))
        pnl+=sum((D(c['amount'])-D(c['originating_position_basis']) for c in account['claims'] if c['type']=='merger_cash'),D(0))
        assert pnl==nav-10000
    else:assert account['status']=='UNRESOLVED' and account['ending_nav'] is None
    return dict(account=name,complete=complete,days_reconciled=checked,total_days=len(account['daily']),fills_checked=len(account['fills']))

def after():
    spec,predictions,rows,frames,actions,references=load_inputs();result=read(HERE/'results.json');freeze=read(HERE/'run-freeze.json')
    assert sha(HERE/'protocol.json')==freeze['protocol_sha256']
    for name,h in freeze['code'].items():assert sha(HERE/name)==h
    orders=read(HERE/'orders.json')
    for seed in spec['control_seeds']:
        for row in orders[f'unranked_{seed:02}']:
            rs=[r for r in predictions if r['month']==row['month']]
            rs=sorted(rs,key=lambda r:(hashlib.sha256(f'ba-ml-unranked-followup-v1|{seed}|{r["cik"]}'.encode()).hexdigest(),r['symbol']))
            assert row['all_symbols']==[r['symbol'] for r in rs]
            assert row['entry_count']==math.ceil(len(rs)*.1) and row['retention_count']==math.ceil(len(rs)*.2)
    checked={}
    for scenario,variant in [('strict',result['strict'])]+list(result['receipt_scenarios'].items()):
        if scenario=='strict':prices,events=frames,actions
        else:prices,events=scenario_inputs(frames,actions,variant['assumed_cash_per_ZIMV'],variant['cash_available_date'])
        for name,ref in variant['account_files'].items():
            p=ROOT/ref['file'];assert sha(p)==ref['sha256']
            if ref['file'] in checked:continue
            account=read(p);ranking={r['month']:r for r in orders[name.rsplit('-',1)[0]]}
            for fill in account['fills']:
                if fill['side']=='buy':
                    order=ranking[fill['date'][:7]]
                    assert fill['security_id'] in order['all_symbols'][:order['entry_count']]
            checked[ref['file']]=replay(name+'-'+scenario,account,prices,events)
    # Reconstruct reference P&L using the independently read original ledger.
    benchmark_checks=[]
    for cost in ['base','stress']:
        original=read(ROOT/result['strict']['account_files']['fixed-'+cost]['file'])
        reference=read(RAW/('fixed-'+cost+'-exposure-reference.json'))
        universe=read(RAW/'universe-reference.json');charges=defaultdict(float)
        for fill in original['fills']:charges[fill['date']]+=float(fill['fee_total'])+float(fill['slippage_cost'])
        prev_nav=10000.;stock=0.;bench=10000.;actual=10000.
        for row,ref,u in zip(original['daily'],reference['daily'],universe):
            expected=(stock*u['universe_return']-charges[row['date']])/prev_nav
            assert abs(expected-ref['reference_return'])<1e-12
            assert abs(stock/prev_nav-ref['lagged_stock_exposure'])<1e-12
            bench*=1+expected;actual*=1+ref['strategy_return']
            assert abs(bench-ref['reference_nav'])<1e-7 and abs(actual-float(row['nav']))<1e-7
            stock=sum(float(x['quantity'])*float(x['qualified_close']) for x in row['holdings'].values());prev_nav=float(row['nav'])
        assert abs(bench-reference['ending_reference_nav'])<1e-7
        benchmark_checks.append(dict(cost=cost,days_reconciled=len(reference['daily']),ending_reference_nav=bench))
    for scenario,group in result['control_ensembles'].items():
        v=result['strict'] if scenario=='strict' else result['receipt_scenarios'][scenario]
        for cost,ensemble in group.items():
            items=[(k,x) for k,x in v['metrics'].items() if k.startswith('unranked') and k.endswith('-'+cost)]
            assert len(items)==20
            if ensemble['all_complete']:
                assert all(x['final_nav'] is not None and x['status']=='COMPLETE_ACCOUNTING' for _,x in items)
                assert abs(np.mean([x['final_nav'] for _,x in items])-ensemble['mean_ending_nav'])<1e-8
            else:assert 'mean_ending_nav' not in ensemble
    intact()
    write(HERE/'verification-after.json',dict(passed=True,unique_accounts=len(checked),accounts=list(checked.values()),
         total_nav_days_reconciled=sum(x['days_reconciled'] for x in checked.values()),total_fills_recomputed=sum(x['fills_checked'] for x in checked.values()),
         exposure_references=benchmark_checks,control_hash_orders_checked=True,no_incomplete_control_deletion=True,original_artifacts_unchanged=True,followup_code_unchanged=True))
    print(json.dumps(dict(passed=True,unique_accounts=len(checked),complete=sum(x['complete'] for x in checked.values()),nav_days=sum(x['days_reconciled'] for x in checked.values()),fills=sum(x['fills_checked'] for x in checked.values())),indent=2))

if __name__=='__main__':
    import sys
    before() if '--before' in sys.argv else after()
