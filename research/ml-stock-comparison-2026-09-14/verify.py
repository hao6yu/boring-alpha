#!/usr/bin/env python3
"""Source, causal-feature and account-regression checks before model fitting."""
from copy import deepcopy
from datetime import date
import json,math,sys
from pathlib import Path
import numpy as np
import pandas as pd
from fundamentals import HERE,ROOT,RAW,a,preferred,build_one
from panel import SESSIONS,FEATURES,product_window,label
from probe import sha,write
import portfolio


def main():
    checks=[];payloads=0
    for name,field,container in [('price-manifest.json','sha256','symbols'),('sec-manifest.json','filtered_sha256',None),('submissions-manifest.json','sha256',None)]:
        d=json.loads((HERE/name).read_text());d=d[container] if container else d
        for m in d.values():
            if not m.get('file'):continue
            assert sha((ROOT/m['file']).read_bytes())==m[field];payloads+=1
    checks.append('Retained provider/SEC payloads match source manifests; failed and rejected identity candidates remain recorded.')
    fm=json.loads((HERE/'fundamental-coverage.json').read_text());b=(ROOT/fm['source_file']).read_bytes();assert sha(b)==fm['sha256'];fr=json.loads(b)
    assert len(fr)==5500
    component_count=0
    def visit(x,cut):
        nonlocal component_count
        if isinstance(x,dict):
            if 'filed' in x and 'val' in x:
                assert x['filed']<=cut and x['end']<=cut and a.available(x['filed'])<=cut;component_count+=1
            for v in x.values():visit(v,cut)
        elif isinstance(x,list):
            for v in x:visit(v,cut)
    for r in fr:visit(r,r['cut'])
    checks.append('All saved financial components satisfy decision-date and two-session filing availability rules.')
    sm=json.loads((HERE/'sec-manifest.json').read_text());cof=json.loads((ROOT/sm['0000927628']['file']).read_text())
    assert preferred(cof,'2021-12-31','2021-09-30')['val']==5912000000
    assert a.instant(cof,'PreferredStockValue','2021-12-31','2021-09-30')['val']==0
    original=build_one('COF','0000927628',cof,'2022-01','2021-12-31');altered=deepcopy(cof)
    # A future restatement with an old period must not alter the old signal.
    altered['facts']['us-gaap']['Assets']['units']['USD'].append(dict(end='2021-09-30',val=999999999999999,accn='future',filed='2023-01-03',form='10-Q'))
    assert build_one('COF','0000927628',altered,'2022-01','2021-12-31')==original
    checks.append('COF preferred capital is $5.912B despite zero rounded par value; a synthetic later restatement cannot change the old feature.')
    identity=json.loads((HERE/'identity-map.json').read_text());assert len(identity['rows'])==100
    assert next(r for r in identity['rows'] if r['symbol']=='SEE')['cik']=='0001012100'
    assert next(r for r in identity['rows'] if r['symbol']=='FOXA')['cik']=='0001308161'
    coverage=json.loads((HERE/'panel-coverage.json').read_text());b=(ROOT/coverage['panel_file']).read_bytes();assert sha(b)==coverage['panel_sha256'];rows=json.loads(b)
    assert len(rows)==5500 and all(r['cut']<r['entry']<=r['end']<'2024-01-01' for r in rows)
    for r in rows:
        if 'momentum_start' in r:
            p=pd.Period(r['month'],freq='M');assert r['momentum_start'][:7]==str(p-13) and r['momentum_end'][:7]==str(p-2)
        if r['eligible']:
            assert r['market_cap_proxy']>0 and r['median_dollar_turnover_63']>=10_000_000
            assert r['features']['momentum'] is not None and r['features']['volatility'] is not None
    assert all(not r['eligible'] for r in rows if r['symbol']=='FOXA')
    checks.append('All original slots are retained; modern FOXA and rejected H&R Block financials cannot enter the cohort.')
    synthetic={d:dict(gross=1.0,qualified=True,close=100) for d in SESSIONS}
    synthetic['2019-05-31']['gross']=2
    assert product_window(synthetic,'2018-05-31','2019-04-30')==0
    assert product_window(synthetic,'2018-05-31','2019-05-31')==1
    june={d:dict(gross=1.0,qualified=True,close=94) for d in SESSIONS if '2022-06-01'<=d<='2022-06-07'}
    ret,status=label(june,'CERN','2022-06-02','2022-06-30');assert math.isclose(ret,95/94-1) and status=='CASH_MERGER_CLAIM_TO_MONTH_END'
    checks.append('Momentum skips the latest month; cash-merger labels use contractual proceeds even without later stock quotes.')
    # Independent dates, share counts and dollar results for a tiny account.
    cal=[d for d in SESSIONS if '2021-09-01'<=d<='2022-01-10']
    prices={d:{'X':dict(close='100',volume='1000000',qualified=True,status='listed',divCash='0',splitFactor='1')} for d in cal}
    event=dict(event_id='test',security_id='X',cik='test',signal_date='2021-12-31',score=0,eligibility_status='READY',selection_key='0')
    acct=portfolio.simulate(calendar=cal,prices=prices,candidates=[event],start='2022-01-03',end='2022-01-10')
    assert acct['fills'][0]['date']=='2022-01-04' and int(acct['fills'][0]['quantity'])==7
    assert acct['fills'][-1]['date']=='2022-01-10'
    fees=sum(float(f['fee_total']) for f in acct['fills']);slip=sum(float(f['slippage_cost']) for f in acct['fills'])
    assert math.isclose(float(acct['ending_nav']),10000-fees-slip,abs_tol=1e-8)
    assert all(float(d['settled_cash'])>=2000 for d in acct['daily'])
    # Unpaid dividends cannot become buying power; a held unresolved stock
    # distribution must invalidate full accounting rather than disappear.
    pp=deepcopy(prices);pp['2022-01-05']['X']['divCash']='1'
    dividend=dict(action_id='div',security_id='X',effective_date='2022-01-05',type='dividend',verified=True,amount_per_share='1',cash_available_date=None)
    other=portfolio.simulate(calendar=cal,prices=pp,candidates=[event],actions=[dividend],start='2022-01-03',end='2022-01-10')
    assert float(other['ending_nav'])==float(acct['ending_nav'])+7
    assert other['ending_settled_cash']==acct['ending_settled_cash']
    unknown=dict(action_id='spin',security_id='X',effective_date='2022-01-05',type='stock_distribution',verified=False,amount_per_share='0',cash_available_date=None)
    bad=portfolio.simulate(calendar=cal,prices=prices,candidates=[event],actions=[unknown],start='2022-01-03',end='2022-01-10')
    assert bad['status']=='UNRESOLVED' and bad['ending_nav'] is None
    checks.append('Second-session execution, independent constant-price fee loss, non-spendable dividend claims, and held-distribution failure behavior pass.')
    result=dict(passed=True,source_payloads_checked=payloads,financial_components_checked=component_count,checks=checks,
                current_coverage_allows_aggregate_comparison=coverage['aggregate_comparison_coverage_pass'],
                code={p.name:sha(p.read_bytes()) for p in HERE.glob('*.py')},no_real_model_fitted_in_tests=True)
    write(HERE/'verification.json',result);print(json.dumps({k:v for k,v in result.items() if k!='code'},indent=2))

if __name__=='__main__':main()
