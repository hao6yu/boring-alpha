"""Economic accounting/timing checks with synthetic prices, never a return fit."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import run_ba012_profitability as ledger


def synthetic():
    sigma=np.diag([100.**2]*5).tolist()
    symbols=['ESU2','TNU2','6EU2','GCQ2','ZCU2']
    prices=dict.fromkeys(symbols,'100')
    bundle={'seed':{'date_chicago':'2022-06-30','signs':[1]*5,'sigma_after_1630':sigma},'days':[]}
    for i,day in enumerate(['2022-07-01','2022-07-05']):
        bundle['days'].append({'date_chicago':day,'previous_joint_date_chicago':'2022-06-30' if i==0 else '2022-07-01',
            'first_joint_of_month':i==0,'last_joint_of_month':False,
            'monthly_signal_date':'2022-06-30','signs':[1]*5,'monthly_after_1630_signs':None,
            'sigma_before_1000':deepcopy(sigma),'sigma_after_1630':deepcopy(sigma),
            'markets':[{'is_roll':False,'active_parent_raw_symbol':s} for s in symbols],
            'reference_1000':dict(prices),'settlement_1630':dict(prices),
            'execution_bars':{s:{f'10:{minute:02d}':{'open':'100','close':'100'} for minute in range(6)} for s in symbols}})
    plan=json.loads((ledger.HERE/'plan.json').read_text())
    window={'start_inclusive':'2022-07-01','end_exclusive':'2022-07-06','joint_sessions':2,'boundary_liquidation_date':'2022-07-05'}
    return bundle,plan,window


def test_flat_prices_reconcile_all_costs_and_final_liquidation():
    b,p,w=synthetic();r=ledger.run_account(b,p,25000,'base',w)
    assert r['status']=='COMPLETE_DIAGNOSTIC'
    assert r['execution_events']>0 and r['gross_trading_pnl']==0
    assert r['ending_equity']==pytest.approx(25000-r['execution_costs']-4.65)
    assert r['daily_ledger'][-1]['quantities']==[0]*5
    assert not any(x['phase']=='10:03_entry' and x['date']=='2022-07-05' for x in r['executions'])
    assert sum(x['signed_quantity'] for x in r['executions'])==0


def test_unseen_entry_price_cannot_improve_committed_quantity():
    b,p,w=synthetic();other=deepcopy(b)
    other['days'][0]['execution_bars']['ESU2']['10:03']['open']='110'
    left=ledger.run_account(b,p,25000,'base',w);right=ledger.run_account(other,p,25000,'base',w)
    for field in ['committed_terminal_target_1000','committed_target_1002']:
        assert left['decisions'][0][field]==right['decisions'][0][field]
    assert left['ending_equity']!=right['ending_equity']


def test_missing_held_mark_prevents_performance_verdict():
    b,p,w=synthetic()
    # Every reference missing ensures a held mark is unavailable, whichever
    # portfolio wins; it must not be misclassified as a cash decision.
    b['days'][1]['reference_1000']=dict.fromkeys(b['days'][1]['reference_1000'],None)
    r=ledger.run_account(b,p,25000,'base',w)
    assert r['status']=='UNRESOLVED' and r['ending_equity'] is None and r['cagr'] is None
    assert 'missing held mark' in r['unresolved_reason']
    assert r['execution_events']>0


def test_futures_mark_to_market_and_trade_cost_are_counted_once():
    a=ledger.Account(25000,[.86,2.1225,1.65,.91,3.26],{})
    a.active_date='2022-07-01';a.fill([2,0,0,0,0],{'ESU2':100},['ESU2',None,None,None,None],'entry')
    a.mark({'ESU2':110},'settlement')
    a.mark({'ESU2':110},'repeat_same_mark')
    a.fill([0]*5,{'ESU2':120},[None]*5,'exit')
    assert a.gross[0]==20 and a.costs[0]==pytest.approx(3.44)
    assert a.equity==pytest.approx(25016.56)
    assert a.high>=a.equity


def test_settlement_protection_stays_committed_despite_morning_recovery():
    b,p,w=synthetic()
    # Add a third date so day2 liquidation cannot be attributed to boundary.
    third=deepcopy(b['days'][1]);third['date_chicago']='2022-07-06';third['previous_joint_date_chicago']='2022-07-05'
    b['days'].append(third);w.update(end_exclusive='2022-07-07',joint_sessions=3,boundary_liquidation_date='2022-07-06')
    b['days'][0]['sigma_after_1630']=np.diag([10000.**2]*5).tolist()
    b['days'][1]['sigma_before_1000']=deepcopy(b['days'][0]['sigma_after_1630'])
    r=ledger.run_account(b,p,25000,'base',w)
    assert r['status']=='COMPLETE_DIAGNOSTIC'
    assert r['decisions'][1]['reason']=='previous_settlement_constraint_breach'
    assert r['daily_ledger'][1]['quantities']==[0]*5


def test_roll_never_counts_different_contract_price_gap_as_profit():
    a=ledger.Account(25000,[.86,2.1225,1.65,.91,3.26],{})
    a.active_date='2022-07-01'
    a.fill([2,0,0,0,0],{'ESU2':100},['ESU2',None,None,None,None],'entry')
    a.fill([0]*5,{'ESU2':110},[None]*5,'roll_exit')
    a.fill([2,0,0,0,0],{'ESZ2':300},['ESZ2',None,None,None,None],'roll_entry')
    a.fill([0]*5,{'ESZ2':310},[None]*5,'final_exit')
    assert a.gross[0]==20
    assert a.costs[0]==pytest.approx(8*.86)
    assert len(a.executions)==4


def test_failed_valuation_is_atomic_and_does_not_fabricate_partial_mark():
    a=ledger.Account(25000,[.86,2.1225,1.65,.91,3.26],{})
    a.active_date='2022-07-01'
    a.fill([1,1,0,0,0],{'ESU2':100,'TNU2':100},['ESU2','TNU2',None,None,None],'entry')
    before=(a.equity,a.marks.copy(),a.gross.copy())
    with pytest.raises(ledger.Unresolved,match='missing held mark'):
        a.mark({'ESU2':110,'TNU2':None},'missing')
    assert a.equity==before[0] and a.marks==before[1] and np.array_equal(a.gross,before[2])


def test_concentration_only_violation_reduces_without_forced_full_flat(monkeypatch):
    b,p,w=synthetic()
    third=deepcopy(b['days'][1]);third['date_chicago']='2022-07-06';third['previous_joint_date_chicago']='2022-07-05'
    b['days'].append(third);w.update(end_exclusive='2022-07-07',joint_sessions=3,boundary_liquidation_date='2022-07-06')
    changed=np.diag([150.**2,100.**2,100.**2,100.**2,100.**2]).tolist()
    b['days'][0]['sigma_after_1630']=deepcopy(changed)
    for d in b['days'][1:]:d.update(sigma_before_1000=deepcopy(changed),sigma_after_1630=deepcopy(changed))
    monkeypatch.setattr(ledger,'monthly_plan',lambda *args:(np.array([2,1,1,0,0]),{'status':'SYNTHETIC_FIXED_PLAN'}))
    r=ledger.run_account(b,p,5000,'base',w)
    assert r['status']=='COMPLETE_DIAGNOSTIC'
    assert r['daily_ledger'][0]['quantities']==[2,1,1,0,0]
    assert r['daily_ledger'][0]['terminal']['violations']==['concentration']
    assert r['daily_ledger'][1]['quantities']==[1,1,1,0,0]
    morning=next(d for d in r['decisions'] if d['date']=='2022-07-05' and 'mandatory' in d)
    assert not morning['mandatory']


def test_complete_and_unresolved_artifacts_serialize_without_nan():
    b,p,w=synthetic()
    complete=ledger.run_account(b,p,25000,'base',w)
    json.dumps(complete,allow_nan=False)
    b['days'][1]['reference_1000']=dict.fromkeys(b['days'][1]['reference_1000'],None)
    incomplete=ledger.run_account(b,p,25000,'base',w)
    json.dumps(incomplete,allow_nan=False)
    assert incomplete['unresolved_category']=='held_valuation_data'
