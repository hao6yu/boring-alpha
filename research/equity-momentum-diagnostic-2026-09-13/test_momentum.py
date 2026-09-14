"""Synthetic checks of signal timing, retention, execution and loss controls."""
from copy import deepcopy
from decimal import Decimal as D

import exchange_calendars as xcals

from portfolio import simulate
from run_momentum import feature,bands,rank_hash


def data():
    days=[d.date().isoformat() for d in xcals.get_calendar('XNYS').sessions_in_range('2020-12-01','2022-03-31')]
    prices={d:{'1:single_common':{'close':10,'adjClose':10,'volume':1_000_000,'qualified':True,
        'status':'listed','source_ticker':'S','divCash':0,'splitFactor':1}} for d in days}
    return days,prices


def event(cutoff='2021-12-31',cik='1'):
    return {'event_id':cutoff+':'+cik,'security_id':cik+':single_common','cik':cik,'accession':'ranking',
        'filing_date':cutoff,'acceptance_date_et':cutoff,'score':0,'eligibility_status':'READY','selection_key':cik.zfill(6)}


def test_momentum_uses_eleven_months_and_skips_latest():
    days,prices=data()
    prices['2021-11-30']['1:single_common']['adjClose']=15
    for d in days:
        if d[:7]=='2021-12': prices[d]['1:single_common']['adjClose']=100
    f=feature('1','2022-01-03',days,prices)
    assert f['momentum_start']=='2020-12-31' and f['momentum_end']=='2021-11-30'
    assert f['momentum']==.5
    prices['2022-01-03']['1:single_common']['adjClose']=100000
    assert feature('1','2022-01-03',days,prices)==f


def test_missing_history_is_not_zero_return():
    days,prices=data(); del prices['2021-05-03']['1:single_common']
    assert feature('1','2022-01-03',days,prices)['status']=='MOMENTUM_PRICE_UNRESOLVED'


def test_qualification_and_bands_use_same_population():
    ordered=list(range(101)); enter,keep=bands(ordered)
    assert enter==ordered[:11] and keep==ordered[:21]
    assert len({rank_hash('1',seed) for seed in range(20)})==20


def test_retention_does_not_force_month_end_roundtrip():
    days,prices=data(); candidates=[event(),event('2022-01-31'),event('2022-02-28')]
    keep={d:['1:single_common'] for d in ['2022-01-03','2022-02-01','2022-03-01']}
    a=simulate(calendar=days,prices=prices,candidates=candidates,retention_by_day=keep,start='2022-01-03',end='2022-03-31')
    assert [(f['date'],f['side']) for f in a['fills']]==[('2022-01-03','buy'),('2022-03-31','sell')]
    assert a['fills'][0]['quantity']==79
    assert all(x['status']=='RETAINED' for x in a['held_exit_decisions'])


def test_leaving_retention_band_sells_next_monthly_session():
    days,prices=data()
    a=simulate(calendar=days,prices=prices,candidates=[event()],retention_by_day={'2022-02-01':[]},start='2022-01-03',end='2022-03-31')
    assert a['fills'][1]['date']=='2022-02-01'
    assert a['completed_positions'][0]['exit_reason']=='RANK_OR_DATA_EXIT'
    assert a['claims'][0]['cash_available_date']=='2022-02-08'


def test_entry_close_cannot_resize_morning_commitment():
    days,prices=data(); prices['2022-01-03']['1:single_common']['close']=30
    a=simulate(calendar=days,prices=prices,candidates=[event()],start='2022-01-03',end='2022-03-31')
    assert a['decisions'][0]['committed_quantity']==79
    assert a['decisions'][0]['status']=='ENTRY_LIMIT_CANCELLED' and not a['fills']


def test_ten_slots_cash_floor_and_next_session_halt_liquidation():
    days,prices=data()
    for d in days:
        template=prices[d]['1:single_common']
        prices[d]={f'{i}:single_common':deepcopy(template) for i in range(1,12)}
        if d=='2022-01-14':
            for b in prices[d].values(): b['close']=5
    a=simulate(calendar=days,prices=prices,candidates=[event(cik=str(i)) for i in range(1,12)],start='2022-01-03',end='2022-03-31')
    assert sum(f['side']=='buy' for f in a['fills'])==10
    assert all(D(d['settled_cash'])>=2000 for d in a['daily'])
    assert a['stop_date']=='2022-01-14'
    assert {f['date'] for f in a['fills'] if f['side']=='sell'}=={'2022-01-18'}
    assert a['stopped'] and not a['open_holdings']


def test_fractional_split_cannot_disappear_from_nav():
    days,prices=data(); prices['2022-01-14']['1:single_common'].update(splitFactor=.5,close=20)
    action={'action_id':'split','security_id':'1:single_common','effective_date':'2022-01-14','type':'split','verified':True,'factor':.5}
    a=simulate(calendar=days,prices=prices,candidates=[event()],actions=[action],start='2022-01-03',end='2022-03-31')
    assert a['status']=='UNRESOLVED'
    assert a['daily'][-1]['nav'] is None and a['open_holdings']
