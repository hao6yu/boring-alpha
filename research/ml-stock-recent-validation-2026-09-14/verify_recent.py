"""Information-cutoff checks and independent account replay for the recent window."""
from collections import defaultdict
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal as D, ROUND_CEILING
import json
import math
import sys
import recent as r
from acquire import HERE,ROOT,RAW,OLD,load,write,sha,scope


def financial_checks():
    scope();fm=load(HERE/'fundamental-coverage.json')
    assert sha(ROOT/fm['source_file'])==fm['sha256']
    rows=load(ROOT/fm['source_file']);count=0
    def visit(value,cut):
        nonlocal count
        if isinstance(value,dict):
            if 'filed' in value and 'val' in value:
                assert value['filed']<=cut and value['end']<=cut and r.f.a.available(value['filed'])<=cut
                count+=1
            for x in value.values():visit(x,cut)
        elif isinstance(value,list):
            for x in value:visit(x,cut)
    for row in rows:visit(row,row['cut'])
    assert len(rows)==3300 and len({(x['symbol'],x['month']) for x in rows})==3300
    data=r.source_facts('0000927628');cut='2024-01-31'
    before=r.f.build_one('COF','0000927628',data,'2024-02',cut)
    altered=deepcopy(data)
    altered['facts']['us-gaap']['Assets']['units']['USD'].append(dict(end='2023-12-31',val=99999999999999,accn='future',filed='2026-01-02',form='10-K'))
    assert r.f.build_one('COF','0000927628',altered,'2024-02',cut)==before
    # The next two NYSE sessions after a filing, including the Jan 2025 closure.
    assert r.f.a.available('2025-01-08')=='2025-01-13'
    return dict(rows=len(rows),components=count,later_restatement_cannot_change_earlier_features=True)


def synthetic_accounts():
    cal=[d for d in r.SESSIONS if '2023-09-01'<=d<='2024-01-12']
    frames={d:{'X':dict(close='100',volume='1000000',qualified=True,status='listed',divCash='0',splitFactor='1')} for d in cal}
    event=dict(event_id='constant',security_id='X',cik='test',signal_date='2023-12-29',score=0,eligibility_status='READY',selection_key='0')
    kwargs=dict(calendar=cal,prices=frames,candidates=[event],start='2024-01-02',end='2024-01-12')
    account=r.portfolio.simulate(**kwargs)
    assert account['status']=='COMPLETE_ACCOUNTING'
    assert account['fills'][0]['date']=='2024-01-03' and int(account['fills'][0]['quantity'])==7
    assert math.isclose(float(account['ending_nav']),10000-sum(float(f['fee_total'])+float(f['slippage_cost']) for f in account['fills']),abs_tol=1e-8)
    # Same economic path through a 2:1 split must preserve account equity.
    split=deepcopy(frames)
    for d in cal:
        if d>='2024-01-05':split[d]['X']['close']='50'
    split['2024-01-05']['X']['splitFactor']='2'
    action=dict(action_id='split',security_id='X',effective_date='2024-01-05',type='split',verified=True,factor='2')
    second=r.portfolio.simulate(**dict(kwargs,prices=split,actions=[action]))
    assert second['status']=='COMPLETE_ACCOUNTING'
    assert int(second['fills'][-1]['quantity'])==14
    assert math.isclose(float(second['ending_nav']),10000-sum(float(f['fee_total'])+float(f['slippage_cost']) for f in second['fills']),abs_tol=1e-8)
    bad=dict(action_id='unknown',security_id='X',effective_date='2024-01-05',type='stock_distribution',verified=False,amount_per_share='0',cash_available_date=None)
    unresolved=r.portfolio.simulate(**dict(kwargs,actions=[bad]))
    assert unresolved['status']=='UNRESOLVED' and unresolved['ending_nav'] is None
    return dict(second_session_execution=True,constant_price_cost_loss=True,whole_split_units_and_value=True,unqualified_held_distribution_fails_closed=True)


def before():
    financial=financial_checks();synthetic=synthetic_accounts();coverage=load(HERE/'panel-coverage.json')
    assert sha(ROOT/coverage['panel_file'])==coverage['panel_sha256']
    rows=load(ROOT/coverage['panel_file'])
    assert len(rows)==3300 and all(x['cut']<x['entry']<=x['end']<=r.END for x in rows)
    requests=load(HERE/'price-manifest.json')
    expected=load(HERE/'bulk-acquisition-plan.json')['initial_symbols']+load(HERE/'extra-price-requests.json')['symbols']
    assert set(expected)<=set(requests['symbols']),'Price acquisition still pending'
    payloads=0
    for record in requests['symbols'].values():
        if record.get('file'):assert sha(ROOT/record['file'])==record['sha256'];payloads+=1
    for record in load(HERE/'sec-manifest.json').values():
        assert record.get('file') and sha(ROOT/record['file'])==record['filtered_sha256'];payloads+=1
    prior_prices=load(OLD/'price-manifest.json')['symbols'];overlap_rows=0;overlap_differences=[]
    for symbol,new in requests['symbols'].items():
        old=prior_prices.get(symbol,{})
        if not old.get('file') or not new.get('file'):continue
        previous={x['date'][:10]:x for x in load(ROOT/old['file'])}
        for row in load(ROOT/new['file']):
            day=row['date'][:10]
            if day not in previous:continue
            overlap_rows+=1
            changed=[k for k in ['open','high','low','close','volume','splitFactor','divCash'] if abs(row[k]-previous[day][k])>max(1e-8,abs(previous[day][k])*1e-8)]
            if changed:overlap_differences.append(dict(symbol=symbol,date=day,fields=changed))
    write(HERE/'overlap-audit.json',dict(rows_checked=overlap_rows,differences=overlap_differences,adjusted_prices_not_compared='Future corporate actions can rescale adjusted levels; raw bars/actions must agree or receive explicit source review.'))
    assert not overlap_differences,'Raw history revisions need review before evaluating'
    scores_checked=0
    for month in sorted({x['month'] for x in rows}):
        eligible=[x for x in rows if x['month']==month and x['eligible']]
        features=r.m.transformed(eligible)
        scores=(features[:,0]+features[:,1]+features[:,2]+features[:,3]+features[:,4]-features[:,5])/6
        for row,score in zip(eligible,scores):
            independent=0.
            for key in r.p.FEATURES:
                value=row['features'][key]
                if value is None:continue
                values=[x['features'][key] for x in eligible if x['features'][key] is not None]
                rank=(sum(x<value for x in values)+(sum(x==value for x in values)+1)/2)/len(values)-.5
                independent+=rank*(-1 if key=='volatility' else 1)/6
            assert math.isclose(float(score),independent,abs_tol=1e-12)
            scores_checked+=1
        altered=deepcopy(eligible)
        for x in altered:x['label_return']=123456.
        assert (r.m.transformed(altered)==features).all()
    out=dict(passed=True,financial=financial,synthetic=synthetic,source_payloads=payloads,independent_scores=scores_checked,overlap_rows_identical=overlap_rows,labels_cannot_change_scores=True,original_artifacts_unchanged=True)
    write(HERE/'verification-before.json',out);print(json.dumps(out,indent=2))


def replay(account,frames,actions,cost):
    byday=defaultdict(list)
    for action in actions:byday[action['effective_date']].append(action)
    cents=lambda v:v.quantize(D('.01'),rounding=ROUND_CEILING)
    slip=D('.001') if cost=='base' else D('.005');fills=defaultdict(list)
    for f in account['fills']:
        d,s=f['date'],f['security_id'];q=D(f['quantity']);close=D(frames[d][s]['close'])
        assert q>0 and q==q.to_integral_value() and close==D(f['raw_close'])
        notional=q*close*(1+slip if f['side']=='buy' else 1-slip)
        fee=dict(commission=cents(min(D('.01')*notional,max(D(1),D('.005')*q))),sec=cents(D('.0000206')*notional) if f['side']=='sell' else D(0),taf=cents(min(D('9.79'),D('.000195')*q)) if f['side']=='sell' else D(0),cat=cents(D('.000003')*q))
        assert fee=={k:D(v) for k,v in f['fees'].items()} and notional==D(f['notional'])
        assert sum(fee.values())==D(f['fee_total']) and q*close*slip==D(f['slippage_cost'])
        if f['side']=='buy':assert d==[day for day in r.SESSIONS if day[:7]==d[:7]][1]
        fills[d].append(f)
    cash=high=D(10000);holdings={};claims={};claimed={c['claim_id']:c for c in account['claims']};stop=None;checked=0
    for row in account['daily']:
        day=row['date']
        if row['nav'] is None:break
        for c in claims.values():
            if not c['paid'] and c['cash_available_date'] is not None and c['cash_available_date']<=day:cash+=D(c['amount']);c['paid']=True
        for action in sorted(byday[day],key=lambda x:x['action_id']):
            s,key=action['security_id'],action['action_id']
            if s not in holdings:continue
            assert action['verified'];h=holdings[s]
            if action['type']=='split':h['quantity']*=D(action['factor']);assert h['quantity']==h['quantity'].to_integral_value()
            elif action['type'] in ['dividend','merger_cash']:
                c=dict(claimed[key],paid=False);assert D(c['amount'])==h['quantity']*D(action['amount_per_share']);claims[key]=c
                assert c['cash_available_date']==action['cash_available_date']
                if c['cash_available_date'] is not None and c['cash_available_date']<=day:cash+=D(c['amount']);c['paid']=True
                if action['type']=='merger_cash':del holdings[s]
            else:raise AssertionError('Unqualified distribution cannot have complete NAV')
        for f in fills[day]:
            s,q=f['security_id'],D(f['quantity']);value,fee=D(f['notional']),D(f['fee_total'])
            if f['side']=='buy':
                assert s not in holdings and stop is None;cash-=value+fee;holdings[s]=dict(quantity=q,basis=value+fee)
                assert cash>=2000 and len(holdings)<=10
            else:
                assert holdings[s]['quantity']==q
                c=next(c for c in account['claims'] if c['type']=='sale' and c['event_id']==f['event_id'])
                assert D(c['amount'])==value-fee
                earliest=(date.fromisoformat(day)+timedelta(days=7)).isoformat()
                assert c['cash_available_date']==next((d for d in r.SESSIONS if d>=earliest),None)
                claims[c['claim_id']]=dict(c,paid=False);del holdings[s]
        equity=sum((h['quantity']*D(frames[day][s]['close']) for s,h in holdings.items()),D(0));unpaid=sum((D(c['amount']) for c in claims.values() if not c['paid']),D(0));nav=cash+equity+unpaid
        assert nav==D(row['nav']) and cash==D(row['settled_cash']) and unpaid==D(row['unpaid_claim_value'])
        assert set(holdings)==set(row['holdings'])
        for s,h in holdings.items():assert h['quantity']==D(row['holdings'][s]['quantity'])
        high=max(high,nav)
        if high-nav>=2000 and stop is None:stop=day
        assert row['account_stopped']==(stop is not None);checked+=1
    complete=checked==len(account['daily'])
    if complete:
        assert account['status']=='COMPLETE_ACCOUNTING' and not holdings and not account['open_holdings']
        assert nav==D(account['ending_nav']) and stop==account['stop_date']
        pnl=sum((D(x['net_sale_proceeds'])-D(x['cost_basis']) for x in account['completed_positions']),D(0))
        pnl+=sum((D(c['amount']) for c in account['claims'] if c['type']=='dividend'),D(0))
        pnl+=sum((D(c['amount'])-D(c['originating_position_basis']) for c in account['claims'] if c['type']=='merger_cash'),D(0))
        assert pnl==nav-10000
    else:assert account['status']=='UNRESOLVED' and account['ending_nav'] is None
    return dict(complete=complete,nav_days=checked,total_days=len(account['daily']),fills=len(account['fills']),stop_date=stop)


def after():
    frozen=load(HERE/'evaluation-freeze.json')
    for name,h in frozen['files'].items():assert sha(ROOT/name)==h,name
    frames,actions,_=r.account_inputs();result=load(HERE/'evaluation-result.json');reports={};reference_checks={}
    for cost,ref in result['account_files'].items():
        assert sha(ROOT/ref['file'])==ref['sha256']
        account=load(ROOT/ref['file']);reports[cost]=replay(account,frames,actions,cost)
        paths=load(RAW/f'{cost}-reference-path.json');universe=load(RAW/'universe-returns.json')
        expenses=defaultdict(lambda:D(0))
        for fill in account['fills']:expenses[fill['date']]+=D(fill['fee_total'])+D(fill['slippage_cost'])
        previous_nav=reference_nav=D(10000);stock=D(0)
        for actual,benchmark,source in zip(account['daily'],paths,universe):
            assert actual['date']==benchmark['date']==source['date']
            day=actual['date'];weight=stock/previous_nav
            rr=weight*D(str(source['universe_return']))-expenses[day]/previous_nav
            reference_nav*=1+rr
            assert abs(reference_nav-D(str(benchmark['reference_nav'])))<D('.0000001')
            assert abs(weight-D(str(benchmark['lagged_stock_exposure'])))<D('.0000000001')
            previous_nav=D(actual['nav'])
            stock=sum((D(h['quantity'])*D(h['qualified_close']) for h in actual['holdings'].values()),D(0))
        if result['exposure_references'][cost]['complete']:
            assert len(paths)==len(account['daily'])
            assert abs(reference_nav-D(str(result['exposure_references'][cost]['ending_nav'])))<D('.0000001')
        reference_checks[cost]=dict(days=len(paths),decimal_arithmetic_reconciled=True,complete=result['exposure_references'][cost]['complete'])
    scope();write(HERE/'verification-after.json',dict(passed=True,accounts=reports,reference_checks=reference_checks,frozen_files_unchanged=True,original_artifacts_unchanged=True))
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    if sys.argv[1]=='financial':print(json.dumps(dict(financial=financial_checks(),synthetic=synthetic_accounts()),indent=2))
    elif sys.argv[1]=='before':before()
    elif sys.argv[1]=='after':after()
