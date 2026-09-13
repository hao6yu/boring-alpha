"""Synthetic cash and chronology checks; no historical prices or model fitting."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal as D
import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1]/'research/equity-event-test-2026-09-10/portfolio.py'
spec = importlib.util.spec_from_file_location('equity_event_portfolio', PATH)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def fixture(symbols=('A',), price='50'):
    # Explicit synthetic weekday calendar. It is not used as a historical calendar.
    calendar = []
    day = date(2021, 10, 1)
    while day <= date(2022, 4, 15):
        if day.weekday() < 5:
            calendar.append(day.isoformat())
        day += timedelta(days=1)
    prices = {d: {s: {'close': price, 'volume': '100000', 'qualified': True,
                      'status': 'listed', 'divCash': '0', 'splitFactor': '1'}
                  for s in symbols} for d in calendar}
    return {'calendar': calendar, 'prices': prices, 'candidates': [],
            'start': '2022-01-03', 'end': '2022-03-31'}


def event(b, symbol='A', entry='2022-01-03', score='2', suffix=''):
    available = b['calendar'][b['calendar'].index(entry)-1]
    return {'event_id': symbol+suffix, 'security_id': symbol, 'cik': symbol,
            'accession': symbol+suffix, 'filing_date': available,
            'acceptance_date_et': available, 'score': score, 'eligibility_status': 'READY'}


def dayrow(r, day):
    return next(d for d in r['daily'] if d['date'] == day)


def test_posted_fee_components_and_cost_examples():
    for q, expected in [(10, ('3.05', '7.05')), (20, ('4.06', '12.06'))]:
        for slip, value in zip((D('.001'), D('.005')), expected):
            buy, sell = q*D(50)*(1+slip), q*D(50)*(1-slip)
            charges = sum(p.fees(q, buy, 'buy').values())+sum(p.fees(q, sell, 'sell').values())
            assert buy-sell+charges == D(value)
    assert p.fees(1, '.1', 'buy')['commission'] == D('.01')
    with pytest.raises(ValueError):
        p.fees(1.5, 10, 'buy')


def test_half_cent_rounded_stress_cost_is_reserved():
    # 201 shares at $1: nominal reserve is 203.020, actual rounded cost 203.025.
    assert p.stress_budget(201, D(1)) == D('203.020')
    assert not p.fits_stressed(201, D(1), D('203.022'))
    assert p.whole_quantity(D('203.022'), D(1)) == 200


def test_quantity_is_prior_close_and_upward_gap_cancels_without_resizing():
    b = fixture(); b['candidates'] = [event(b)]
    baseline = p.simulate(**b)
    changed = deepcopy(b); changed['prices']['2022-01-03']['A']['close'] = '100'
    result = p.simulate(**changed)
    assert baseline['decisions'][0]['committed_quantity'] == result['decisions'][0]['committed_quantity'] == 19
    assert result['decisions'][0]['status'] == 'ENTRY_LIMIT_CANCELLED'
    assert not result['fills'] and D(result['ending_nav']) == 5000
    assert baseline['fills'][0]['date'] == '2022-01-03'


def test_twenty_intervals_and_seven_calendar_day_sale_cash_lock():
    b = fixture(); b['candidates'] = [event(b)]
    r = p.simulate(**b)
    entry_index = b['calendar'].index('2022-01-03')
    due = b['calendar'][entry_index+20]
    assert [x['side'] for x in r['fills']] == ['buy', 'sell']
    assert r['fills'][1]['date'] == due
    sale = next(c for c in r['claims'] if c['type'] == 'sale')
    release = (date.fromisoformat(due)+timedelta(days=7)).isoformat()
    assert sale['cash_available_date'] == release
    assert D(dayrow(r, due)['settled_cash']) == D(dayrow(r, '2022-01-03')['settled_cash'])
    assert D(dayrow(r, release)['settled_cash']) > D(dayrow(r, due)['settled_cash'])
    assert r['completed_positions'][0]['delay_sessions'] == 0


def test_concurrent_reservations_preserve_cash_and_issuer_slots():
    b = fixture(tuple('ABCDE')); b['candidates'] = [event(b, s) for s in 'ABCDE']
    r = p.simulate(**b)
    buys = [x for x in r['fills'] if x['side'] == 'buy']
    assert len(buys) == 4
    assert all(x['quantity'] == 19 for x in buys)
    assert r['decisions'][4]['status'] == 'SLOTS_FULL'
    assert D(r['daily'][0]['settled_cash']) >= 1000
    assert sum(D(x['notional'])+D(x['fee_total']) for x in buys) == 5000-D(r['daily'][0]['settled_cash'])


def test_split_then_dividend_preserve_value_without_double_count_or_cash_credit():
    b = fixture(); b['candidates'] = [event(b)]
    for d in b['calendar']:
        if d >= '2022-01-04': b['prices'][d]['A']['close'] = '25'
        if d >= '2022-01-05': b['prices'][d]['A']['close'] = '24'
    b['prices']['2022-01-04']['A']['splitFactor'] = '2'
    b['prices']['2022-01-05']['A']['divCash'] = '1'
    b['actions'] = [
        {'action_id': 'split', 'security_id': 'A', 'effective_date': '2022-01-04',
         'type': 'split', 'verified': True, 'factor': '2'},
        {'action_id': 'div', 'security_id': 'A', 'effective_date': '2022-01-05',
         'type': 'dividend', 'verified': True, 'amount_per_share': '1', 'cash_available_date': None}]
    r = p.simulate(**b)
    a, split, div = [dayrow(r, d) for d in ('2022-01-03', '2022-01-04', '2022-01-05')]
    assert D(split['holdings']['A']['quantity']) == 38
    assert D(a['nav']) == D(split['nav']) == D(div['nav'])
    assert a['settled_cash'] == split['settled_cash'] == div['settled_cash']
    assert D(div['unpaid_claim_value']) == 38
    assert not next(c for c in r['claims'] if c['type'] == 'dividend')['paid']


def test_missing_held_mark_nulls_nav_and_next_session_entry_then_delays_exit():
    b = fixture(('A', 'B')); b['candidates'] = [event(b)]
    due = b['calendar'][b['calendar'].index('2022-01-03')+20]
    nextday = b['calendar'][b['calendar'].index(due)+1]
    third = b['calendar'][b['calendar'].index(due)+2]
    b['candidates'].append(event(b, 'B', nextday))
    b['prices'][due]['A']['status'] = 'halted'
    b['prices'][nextday]['A']['status'] = 'otc'
    r = p.simulate(**b)
    assert dayrow(r, due)['nav'] is None
    assert dayrow(r, due)['holdings']['A']['exit_pending']
    assert dayrow(r, nextday)['nav'] is not None
    assert dayrow(r, nextday)['daily_return'] is None
    assert r['decisions'][1]['status'] == 'UNPRICED_ENTRY_FREEZE'
    assert r['fills'][1]['date'] == third
    assert r['completed_positions'][0]['delay_sessions'] == 2
    assert r['status'] == 'UNRESOLVED' and r['max_drawdown'] is None


def test_merger_replaces_shares_with_locked_claim_and_never_fills_halt_row():
    b = fixture(); b['candidates'] = [event(b)]
    b['prices']['2022-01-04']['A']['status'] = 'halted'
    b['actions'] = [{'action_id': 'merger', 'security_id': 'A', 'effective_date': '2022-01-04',
                     'type': 'merger_cash', 'verified': True, 'amount_per_share': '95',
                     'cash_available_date': None}]
    r = p.simulate(**b)
    assert len(r['fills']) == 1 and not r['open_holdings']
    claim = r['claims'][0]
    assert D(claim['amount']) == 19*95 and not claim['paid']
    assert D(r['ending_nav']) == D(r['ending_settled_cash'])+D(claim['amount'])
    assert not r['completed_positions']


def test_stop_latches_after_close_and_executes_next_close_even_after_recovery():
    b = fixture(tuple('ABCD'), '80'); b['candidates'] = [event(b, s) for s in 'ABCD']
    for s in 'ABCD':
        b['prices']['2022-01-04'][s]['close'] = '40'
        b['prices']['2022-01-05'][s]['close'] = '90'
    r = p.simulate(**b)
    assert r['stopped'] and r['stop_date'] == '2022-01-04'
    sells = [f for f in r['fills'] if f['side'] == 'sell']
    assert len(sells) == 4 and {s['date'] for s in sells} == {'2022-01-05'}
    assert all(D(s['raw_close']) == 90 for s in sells)
    assert D(r['max_drawdown']) > 1000


def test_unverified_dividend_and_fractional_split_are_not_magic_cash():
    b = fixture(); b['candidates'] = [event(b)]
    b['prices']['2022-01-04']['A']['divCash'] = '1'
    r = p.simulate(**b)
    assert r['status'] == 'UNRESOLVED' and not r['claims']
    assert dayrow(r, '2022-01-04')['nav'] is None
    b['prices']['2022-01-04']['A']['divCash'] = '0'
    b['prices']['2022-01-04']['A']['splitFactor'] = '.1'
    b['actions'] = [{'action_id': 'reverse', 'security_id': 'A', 'effective_date': '2022-01-04',
                     'type': 'split', 'verified': True, 'factor': '.1'}]
    r = p.simulate(**b)
    assert D(r['open_holdings']['A']['quantity']) == D('1.9')
    assert dayrow(r, '2022-01-04')['nav'] is None and len(r['fills']) == 1


def test_initial_expense_and_matched_baseline_have_explicit_account_effects():
    b = fixture(); b['candidates'] = [event(b, score='0')]
    score = p.simulate(**b, initial_expense='5')
    matched = p.simulate(**b, rank_mode='matched', initial_expense='5')
    assert not score['fills'] and D(score['ending_nav']) == 4995
    assert D(score['daily'][0]['daily_return']) == D('-.001')
    assert matched['fills'] and D(matched['daily'][0]['high_water_observed']) == 5000


def test_later_intraday_halt_cannot_cancel_other_morning_commitment():
    b = fixture(('A', 'B')); b['candidates'] = [event(b), event(b, 'B', '2022-01-04')]
    b['prices']['2022-01-04']['A']['status'] = 'halted'
    r = p.simulate(**b)
    assert r['decisions'][1]['status'] == 'FILLED'
    assert dayrow(r, '2022-01-04')['nav'] is None
    b['prices']['2022-01-04']['A']['status_before_open'] = 'halted'
    r = p.simulate(**b)
    assert r['decisions'][1]['status'] == 'UNPRICED_ENTRY_FREEZE'


def test_known_halted_entry_is_no_fill_not_missing_account_data():
    b = fixture(); b['candidates'] = [event(b)]
    b['prices']['2022-01-03']['A']['status'] = 'halted'
    r = p.simulate(**b)
    assert r['decisions'][0]['status'] == 'ENTRY_HALTED'
    # Closing status alone was not known in the morning: quantity was committed.
    assert r['decisions'][0]['committed_quantity'] == 19
    assert r['status'] == 'COMPLETE_ACCOUNTING' and not r['fills']


@pytest.mark.parametrize('status,decision,unresolved',[
    ('halted','ENTRY_HALTED',False),('otc','ENTRY_NONLISTED',False),
    ('unknown','ENTRY_STATUS_UNRESOLVED',True)])
def test_preopen_nonrouteable_candidate_is_retained_without_commitment(status,decision,unresolved):
    b = fixture(); b['candidates'] = [event(b)]
    # A later listed closing bar does not erase the morning's known constraint.
    b['prices']['2022-01-03']['A']['status_before_open'] = status
    r = p.simulate(**b)
    assert len(r['decisions']) == 1 and r['decisions'][0]['status'] == decision
    assert 'committed_quantity' not in r['decisions'][0] and not r['fills']
    assert (r['status'] == 'UNRESOLVED') is unresolved


def test_status_without_quote_preserves_missing_nav_without_inventing_action_failure():
    b = fixture(); b['candidates'] = [event(b)]
    b['prices']['2022-01-04']['A'] = {'qualified':False,'status':'halted',
        'status_before_open':'halted','missing_provider_row':True}
    b['prices']['2022-01-05']['A']['status'] = 'otc'
    r = p.simulate(**b)
    assert dayrow(r,'2022-01-04')['nav'] is None
    assert dayrow(r,'2022-01-05')['nav'] is not None
    assert 'unresolved_action' not in dayrow(r,'2022-01-05')['holdings']['A']
    assert r['status']=='UNRESOLVED' and len(r['completed_positions'])==1


def test_split_factor_must_exist_and_match_provider_action_fields():
    b = fixture(); b['candidates'] = [event(b)]
    action = {'action_id': 'split', 'security_id': 'A', 'effective_date': '2022-01-04',
              'type': 'split', 'verified': True}
    b['actions'] = [action]
    with pytest.raises(ValueError, match='factor/amount'):
        p.simulate(**b)
    action['factor'] = '2'
    b['prices']['2022-01-04']['A']['splitFactor'] = '3'
    r = p.simulate(**b)
    assert r['status'] == 'UNRESOLVED' and dayrow(r, '2022-01-04')['nav'] is None
    assert D(r['open_holdings']['A']['quantity']) == 19


def test_unresolved_action_cannot_disappear_into_later_merger_cash():
    b = fixture(); b['candidates'] = [event(b)]
    b['prices']['2022-01-04']['A']['divCash'] = '1'
    b['actions'] = [{'action_id': 'merger', 'security_id': 'A', 'effective_date': '2022-01-05',
                     'type': 'merger_cash', 'verified': True, 'amount_per_share': '95',
                     'cash_available_date': None}]
    r = p.simulate(**b)
    assert r['ending_nav'] is None and not r['claims']
    assert len(r['open_holdings']) == 1
