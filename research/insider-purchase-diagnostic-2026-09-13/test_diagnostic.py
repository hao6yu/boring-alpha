"""Causality and cash-account checks on synthetic data; no market returns."""
from decimal import Decimal as D
import exchange_calendars as xcals
import pytest

from insider_rules import transaction_day, classify
from portfolio import simulate, fees


def fixture():
    calendar = [d.date().isoformat() for d in xcals.get_calendar('XNYS').sessions_in_range('2021-09-01','2022-03-31')]
    prices = {d:{'S':{'close':10,'volume':1_000_000,'status':'listed','qualified':True,'divCash':0,'splitFactor':1}} for d in calendar}
    def event(month):
        return {'event_id':month,'security_id':'S','cik':'1','accession':month,
            'filing_date':month,'acceptance_date_et':month,'score':None,
            'eligibility_status':'READY','selection_key':'a'}
    return calendar, prices, [event('2021-12-31'),event('2022-01-31')]


def test_xml_date_preserves_local_calendar_day():
    assert transaction_day('2018-01-18-05:00')=='2018-01-18'
    assert transaction_day('2018-01-18Z')=='2018-01-18'
    with pytest.raises(ValueError): transaction_day('2018-02-30')


def test_future_history_does_not_change_classification():
    history=[{'transaction_date':f'{y}-{m:02}-02','disclosure_day':f'{y}-{m:02}-04'} for y,m in [(2019,1),(2020,2),(2021,3)]]
    assert classify(history,2022)=='NONROUTINE'
    history.append({'transaction_date':'2020-01-02','disclosure_day':'2022-02-01'})
    assert classify(history,2022)=='NONROUTINE'
    assert classify(history,2022,[2020])=='UNKNOWN_HISTORY'


def test_monthly_dates_whole_shares_costs_and_locked_sale_claim():
    cal, prices, events=fixture()
    result=simulate(calendar=cal,prices=prices,candidates=events,rank_mode='matched',start='2022-01-03',end='2022-02-28')
    assert result['status']=='COMPLETE_ACCOUNTING'
    buy,sell=result['fills'][:2]
    assert buy['date']=='2022-01-03' and sell['date']=='2022-01-31'
    assert buy['quantity']==198 and sell['quantity']==198
    expected=D(10000)
    for f in result['fills']:
        expected += (D(f['notional'])-D(f['fee_total'])) if f['side']=='sell' else -(D(f['notional'])+D(f['fee_total']))
    assert D(result['ending_nav'])==expected
    assert all(D(d['settled_cash'])>=2000 for d in result['daily'])
    claim=result['claims'][0]
    assert claim['cash_available_date']=='2022-02-07'
    jan31=next(x for x in result['daily'] if x['date']=='2022-01-31')
    assert D(jan31['unpaid_claim_value'])==D(claim['amount'])


def test_entry_day_price_cannot_resize_quantity():
    cal, prices, events=fixture()
    prices['2022-01-03']['S']['close']=20
    result=simulate(calendar=cal,prices=prices,candidates=events[:1],rank_mode='matched',start='2022-01-03',end='2022-02-28')
    assert result['decisions'][0]['committed_quantity']==198
    assert result['decisions'][0]['status']=='ENTRY_LIMIT_CANCELLED'
    assert not result['fills'] and D(result['ending_nav'])==10000


def test_dividend_is_claim_not_spendable_cash():
    cal, prices, events=fixture()
    prices['2022-01-14']['S']['divCash']=1
    actions=[{'action_id':'div','security_id':'S','effective_date':'2022-01-14','type':'dividend','verified':True,'amount_per_share':1,'cash_available_date':None}]
    result=simulate(calendar=cal,prices=prices,candidates=events[:1],actions=actions,rank_mode='matched',start='2022-01-03',end='2022-02-28')
    claim=next(c for c in result['claims'] if c['type']=='dividend')
    assert D(claim['amount'])==198 and claim['paid'] is False
    assert D(result['ending_nav'])-D(result['ending_settled_cash'])==198


def test_missing_held_price_remains_unresolved():
    cal, prices, events=fixture()
    del prices['2022-01-14']['S']
    result=simulate(calendar=cal,prices=prices,candidates=events[:1],rank_mode='matched',start='2022-01-03',end='2022-02-28')
    assert result['status']=='UNRESOLVED'
    assert next(d for d in result['daily'] if d['date']=='2022-01-14')['nav'] is None


def test_regulatory_fees_are_separate_rounded_components():
    assert fees(100,D(1000),'sell')=={'commission':D('1.00'),'sec':D('.03'),'taf':D('.02'),'cat':D('.01')}
