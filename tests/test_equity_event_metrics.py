"""Synthetic account arithmetic and gate checks; no market or strategy inputs."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
from pathlib import Path

import numpy as np
import pytest


PATH=Path(__file__).resolve().parents[1]/'research/equity-event-test-2026-09-10/evaluation_metrics.py'
spec=importlib.util.spec_from_file_location('equity_event_metrics_audit',PATH)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def account(dates, navs, cost='base', rank='score', expense=0):
    previous=5000; daily=[]
    for d,nav in zip(dates,navs):
        daily.append({'date':d,'nav':None if nav is None else str(nav),
                      'settled_cash':None if nav is None else str(nav),
                      'unpaid_claim_value':'0','holdings':{},
                      'daily_return':None if nav is None or previous is None else str(nav/previous-1)})
        previous=nav
    return {'status':'COMPLETE_ACCOUNTING','policy_sha256':m.POLICY_SHA,
            'start':dates[0],'end':dates[-1],'initial_capital':'5000',
            'initial_expense':str(expense),'cost_case':cost,'rank_mode':rank,
            'ending_nav':daily[-1]['nav'],'daily':daily,'fills':[], 'claims':[],
            'completed_positions':[],'open_holdings':{},'stopped':False}


def test_cagr_cash_drawdown_and_year_boundary_are_one_continuous_account():
    dates=['2022-12-29','2022-12-30','2023-01-03']
    r=m.account_metrics(account(dates,[5500,4400,5000]),expected_dates=dates)
    assert r['status']=='COMPLETE' and r['cagr']==0
    assert r['max_drawdown_dollars']==1100
    assert r['max_drawdown_fraction']==pytest.approx(.2)
    assert r['annual_returns']['2023']['opening_nav']==4400
    assert r['annual_returns']['2023']['net_return']==pytest.approx(5000/4400-1)
    assert r['annual_returns']['2022']['net_return']==pytest.approx(-.12)
    assert r['elapsed_calendar_days_inclusive']==6
    for row in r['cash_comparisons']:
        assert row['ending_value']==pytest.approx(5000*(1+row['effective_annual_rate'])**(6/365))


def test_missing_nav_or_entire_day_is_never_forward_filled_or_deleted():
    dates=['2022-01-03','2022-01-04','2022-01-05']
    r=m.account_metrics(account(dates,[5000,None,6000]),expected_dates=dates)
    assert r['status']=='UNRESOLVED' and r['cagr'] is None and r['max_drawdown_fraction'] is None
    assert all(x['account_minus_cash'] is None for x in r['cash_comparisons'])
    source=account(dates,[5000,5100,6000]); del source['daily'][1]
    r=m.account_metrics(source,expected_dates=dates)
    assert r['status']=='UNRESOLVED' and r['cagr'] is None


def test_stock_claim_exposure_beta_and_two_sided_turnover_are_distinct():
    dates=['2022-01-03','2022-01-04','2022-01-05']
    benchmark=[.01,-.02,.015]; returns=[2*x for x in benchmark]
    navs=5000*np.cumprod(1+np.array(returns)); source=account(dates,navs)
    for row,nav in zip(source['daily'],navs):
        row.update(settled_cash=str(nav-1500),unpaid_claim_value='500',
                   holdings={'A':{'quantity':'10','qualified_close':'100'}})
    source['fills']=[{'date':dates[0],'quantity':10,'raw_close':'100','fee_total':'1','slippage_cost':'1'},
                     {'date':dates[-1],'quantity':10,'raw_close':'110','fee_total':'1','slippage_cost':'1.1'}]
    r=m.account_metrics(source,expected_dates=dates,benchmark_returns=dict(zip(dates,benchmark)))
    assert r['diagnostics']['beta']==pytest.approx(2)
    assert r['diagnostics']['stock_exposure']['mean']==pytest.approx(np.mean(1000/navs))
    assert r['diagnostics']['claim_exposure']['mean']==pytest.approx(np.mean(500/navs))
    assert r['diagnostics']['turnover']['two_sided_reference_notional']==2100
    assert r['diagnostics']['turnover']['ratio_to_mean_daily_nav']==pytest.approx(2100/np.mean(navs))
    assert r['active_months']==1
    bad=m.account_metrics(source,expected_dates=dates,benchmark_returns={dates[0]:.01})
    assert bad['diagnostics']['beta'] is None and bad['status']=='COMPLETE'


def test_stationary_bootstrap_constant_difference_estimates_mean_not_cagr():
    result=m.stationary_bootstrap([.0001]*50)
    assert result['estimate']==pytest.approx(.0252)
    assert result['lower']==pytest.approx(.0252) and result['upper']==pytest.approx(.0252)
    assert result['expected_block_sessions']==20 and result['replicates']==2000
    assert result['seed']==20260910 and result['percentile_method']=='linear'
    assert m.stationary_bootstrap([0,None,.1])['lower'] is None
    varied=[-.001,.002,.001,-.002]*20
    left=m.stationary_bootstrap(varied); right=m.stationary_bootstrap(varied)
    assert left==right and left['lower']<0<left['upper']


def full_suite():
    dates=[]; d=date(2022,1,3)
    while d<=date(2023,12,29):
        if d.weekday()<5: dates.append(d.isoformat())
        d+=timedelta(days=1)
    # Explicit synthetic weekday calendar, not a historical NYSE authority.
    result={}
    for cost in m.COSTS:
        result[cost]={}
        for name,r in [('numeric',.00005),('text',.0005),('matched_event',.0001)]:
            source=account(dates,5000*np.cumprod(np.repeat(1+r,len(dates))),cost,
                           'matched' if name=='matched_event' else 'score')
            source['completed_positions']=[{'event_id':str(i),'delay_sessions':0} for i in range(40)]
            # One stock holding each month makes active-month eligibility explicit.
            for row in source['daily']:
                row['settled_cash']=str(float(row['nav'])-100)
                row['holdings']={'A':{'quantity':'1','qualified_close':'100'}}
            result[cost][name]=source
    return dates,result


def test_gate_requires_both_costs_baselines_counts_and_separate_expense_account():
    dates,suite=full_suite()
    kwargs={'expected_dates':dates,'sample_counts':{'fit_2020':200,'validation_2021':100,'evaluation':200,'evaluation_issuers':40},
            'upstream_ready':{'ready':True,'reasons':[]},
            'data_expense':{'amount_usd':0,'basis':'no_charge','source':'synthetic'}}
    report=m.evaluate(suite,**kwargs)
    assert report['status']=='PASS'
    assert report['trading_only']['comparisons']['base']['annualized_net_text_minus_numeric_cagr']>.01
    assert report['trading_only']['bootstrap']['lower']>0
    # A paid study cannot silently become a terminal-value subtraction.
    kwargs['data_expense']={'amount_usd':5,'basis':'quote','source':'synthetic quote'}
    report=m.evaluate(suite,**kwargs)
    assert report['status']=='UNRESOLVED' and report['after_data_expense']['status']=='UNRESOLVED'
    paid=deepcopy(suite)
    for cost in m.COSTS:
        for name in m.MODELS:
            r=paid[cost][name]; r['initial_expense']='5'
            previous=5000
            for row in r['daily']:
                nav=float(row['nav'])-5
                row.update(nav=str(nav),settled_cash=str(nav-100),daily_return=str(nav/previous-1))
                previous=nav
            r['ending_nav']=r['daily'][-1]['nav']
    report=m.evaluate(suite,expense_accounts=paid,**kwargs)
    assert report['status']=='PASS'
    assert report['after_data_expense']['accounts']['base']['text']['cagr']<report['trading_only']['accounts']['base']['text']['cagr']
    # The fixture supplies separate outcomes; the evaluator cannot certify that
    # an upstream caller genuinely reran a simulator. Provenance remains required.
    suite['stress']['text']['daily'][20]['nav']=None
    report=m.evaluate(suite,expense_accounts=paid,**kwargs)
    assert report['status']=='UNRESOLVED'
    assert report['trading_only']['accounts']['stress']['text']['cagr'] is None
