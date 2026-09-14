"""Independent settlement-scenario ledger and frozen-signal checks."""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_UP
import json
import sys
import completion as c
from acquire import HERE, ROOT, RAW, load, write, sha, scope

r = c.r


def unchanged():
    scope()
    for path, digest in load(HERE/'evaluation-freeze.json')['files'].items():
        assert sha(ROOT/path) == digest, path
    assert sha(RAW/'predictions.json') == c.SPEC['fixed_predictions_sha256']
    assert sha(HERE/'evaluation-result.json') == c.SPEC['strict_result_sha256']
    assert c.original.predictions_and_schedule()[3] == load(HERE/'orders.json')


def synthetic():
    cal = [d for d in r.SESSIONS if '2023-09-01' <= d <= '2024-01-12']
    bar = lambda price: dict(close=str(price), volume='1000000', qualified=True,
                             status='listed', divCash='0', splitFactor='1')
    frames = {d: {'X': bar(100), 'Y': bar(200)} for d in cal}
    event = dict(event_id='constant', security_id='X', cik='test',
                 signal_date='2023-12-29', score=0, eligibility_status='READY', selection_key='0')
    kwargs = dict(calendar=cal, prices=frames, candidates=[event],
                  start='2024-01-02', end='2024-01-12')
    baseline = r.portfolio.simulate(**kwargs)
    revised = c.engine.simulate(**kwargs)
    for row in revised['daily']:
        assert row.pop('market_sensitive_claim_value') == '0'
    assert revised == baseline
    action = dict(action_id='conversion', security_id='X', effective_date='2024-01-05',
                  type='stock_merger', verified=True, amount_per_share='0', cash_available_date=None,
                  child_security_id='Y', child_cik='child', ratio_numerator='1', ratio_denominator='2',
                  fixed_cash_date='2024-01-08', fixed_unit_cash='190', trade_available_date='2024-01-10')
    args = dict(kwargs, actions=[action], retention_by_day={'2024-01-08': []})
    merged = c.engine.simulate(**args)
    assert merged['status'] == 'COMPLETE_ACCOUNTING'
    assert [(f['security_id'], f['quantity'], f['date']) for f in merged['fills']] == [
        ('X', 7, '2024-01-03'), ('Y', 3, '2024-01-10')]
    claim = next(x for x in merged['claims'] if x['type'] == 'fractional_cash')
    assert D(claim['amount']) == 95 and D(claim['fractional_quantity']) == D('.5')
    assert claim['cash_available_date'] is None and claim['paid'] is False
    costs = sum((D(f['fee_total']) + D(f['slippage_cost']) for f in merged['fills']), D(0))
    assert D(merged['ending_nav']) == 10000-costs-5
    alternate = c.engine.simulate(**dict(args, actions=[dict(action, fixed_unit_cash='0')]))
    for a, b in zip(merged['daily'], alternate['daily']):
        if a['date'] < '2024-01-08': assert a == b
    spinframes = deepcopy(frames)
    for day in cal:
        spinframes[day]['Y'] = bar(40)
        if day >= '2024-01-05': spinframes[day]['X'] = bar(80)
    spun = c.engine.simulate(**dict(kwargs, prices=spinframes,
        actions=[dict(action, type='spinoff', fixed_unit_cash='40')]))
    assert spun['status'] == 'COMPLETE_ACCOUNTING'
    costs = sum((D(f['fee_total']) + D(f['slippage_cost']) for f in spun['fills']), D(0))
    assert D(spun['ending_nav']) == 10000-costs
    assert max(len(d['holdings']) for d in spun['daily']) == 2
    missing = deepcopy(frames); del missing['2024-01-05']['Y']
    failed = c.engine.simulate(**dict(args, prices=missing))
    assert failed['status'] == 'UNRESOLVED' and failed['ending_nav'] is None
    return dict(no_action_exact_regression=True, merger_value_and_whole_units=True,
                spinoff_value_conserved=True, child_sale_waits_for_availability=True,
                future_cash_quote_cannot_change_earlier_NAV=True,
                fractional_cash_never_spendable=True, missing_child_price_fails_closed=True)


def replay(account, frames, actions, cost):
    byday = defaultdict(list)
    for action in actions:
        byday[action['effective_date']].append(action)
    cents = lambda v: v.quantize(D('.01'), rounding=ROUND_CEILING)
    slip = D('.001') if cost == 'base' else D('.005')
    fills = defaultdict(list)
    for f in account['fills']:
        day, sec = f['date'], f['security_id']
        q, close = D(f['quantity']), D(frames[day][sec]['close'])
        assert q > 0 and q == q.to_integral_value() and close == D(f['raw_close'])
        executed = close*(1+slip if f['side'] == 'buy' else 1-slip)
        notional = q*executed
        fee = dict(commission=cents(min(D('.01')*notional, max(D(1), D('.005')*q))),
                   sec=cents(D('.0000206')*notional) if f['side'] == 'sell' else D(0),
                   taf=cents(min(D('9.79'), D('.000195')*q)) if f['side'] == 'sell' else D(0),
                   cat=cents(D('.000003')*q))
        assert fee == {k:D(v) for k,v in f['fees'].items()}
        assert executed == D(f['executed_price']) and notional == D(f['notional'])
        assert sum(fee.values()) == D(f['fee_total']) and q*close*slip == D(f['slippage_cost'])
        if f['side'] == 'buy': assert day == [d for d in r.SESSIONS if d[:7] == day[:7]][1]
        fills[day].append(f)
    cash = high = previous = D(10000)
    holdings, claims = {}, {}
    stop = None
    reported = {x['claim_id']:x for x in account['claims']}
    assert len(reported) == len(account['claims'])

    def claim(key, sec, kind, amount, day, available, **extra):
        assert key not in claims
        claims[key] = dict(security_id=sec, type=kind, amount=amount, created_date=day,
                           cash_available_date=available, paid=False, **extra)

    for row in account['daily']:
        day = row['date']
        assert row['nav'] is not None, (cost, day, row['unpriced_security_ids'])
        for v in claims.values():
            if v['type'] == 'fractional_cash':
                v['amount'] = ((v['fraction']*v['unit']).quantize(D('.01'), rounding=ROUND_HALF_UP)
                               if day >= v['fixed'] else v['fraction']*D(frames[day][v['child']]['close']))
            if not v['paid'] and v['cash_available_date'] is not None and v['cash_available_date'] <= day:
                cash += v['amount']; v['paid'] = True
        for action in sorted(byday[day], key=lambda a:a['action_id']):
            sec, key, kind = action['security_id'], action['action_id'], action['type']
            if sec not in holdings: continue
            assert action['verified'], (day, sec)
            h = holdings[sec]
            if kind == 'split':
                h['quantity'] *= D(action['factor'])
                assert h['quantity'] == h['quantity'].to_integral_value()
            elif kind in ('dividend', 'merger_cash'):
                value = h['quantity']*D(action['amount_per_share'])
                claim(key, sec, kind, value, day, action['cash_available_date'])
                if action['cash_available_date'] is not None and action['cash_available_date'] <= day:
                    cash += value; claims[key]['paid'] = True
                if kind == 'merger_cash': del holdings[sec]
            elif kind in ('stock_merger', 'spinoff'):
                child = action['child_security_id']
                assert child not in holdings
                quantity = h['quantity']*D(action['ratio_numerator'])/D(action['ratio_denominator'])
                whole = D(int(quantity)); fraction = quantity-whole
                if fraction:
                    amount = (fraction*D(action['fixed_unit_cash'])).quantize(D('.01'), rounding=ROUND_HALF_UP) if day >= action['fixed_cash_date'] else fraction*D(frames[day][child]['close'])
                    claim(key+':fraction', sec, 'fractional_cash', amount, day, None,
                          fraction=fraction, child=child, fixed=action['fixed_cash_date'], unit=D(action['fixed_unit_cash']))
                if whole:
                    holdings[child] = dict(quantity=whole,
                        event_id=h['event_id']+':received:'+child+':'+day, available=action['trade_available_date'])
                if kind == 'stock_merger': del holdings[sec]
            else: raise AssertionError(('unsupported held action', action))
        for f in fills[day]:
            sec, q, value, fee = f['security_id'], D(f['quantity']), D(f['notional']), D(f['fee_total'])
            if f['side'] == 'buy':
                assert sec not in holdings and stop is None
                cash -= value+fee
                holdings[sec] = dict(quantity=q, event_id=f['event_id'], available=day)
                assert cash >= 2000 and len(holdings) <= 10
            else:
                assert holdings[sec]['quantity'] == q and day >= holdings[sec]['available']
                assert holdings[sec]['event_id'] == f['event_id']
                earliest = (date.fromisoformat(day)+timedelta(days=7)).isoformat()
                available = next((d for d in r.SESSIONS if d >= earliest), None)
                claim(f['event_id']+':sale', sec, 'sale', value-fee, day, available)
                del holdings[sec]
        equity = sum((h['quantity']*D(frames[day][s]['close']) for s,h in holdings.items()), D(0))
        unpaid = sum((v['amount'] for v in claims.values() if not v['paid']), D(0))
        floating = sum((v['amount'] for v in claims.values() if v['type'] == 'fractional_cash' and day < v['fixed']), D(0))
        nav = cash+equity+unpaid
        assert nav == D(row['nav']) and cash == D(row['settled_cash']) and unpaid == D(row['unpaid_claim_value']), day
        assert floating == D(row['market_sensitive_claim_value'])
        assert set(holdings) == set(row['holdings'])
        for sec,h in holdings.items():
            assert h['quantity'] == D(row['holdings'][sec]['quantity'])
            assert h['event_id'] == row['holdings'][sec]['event_id']
        high = max(high, nav)
        if high-nav >= 2000 and stop is None: stop = day
        assert row['account_stopped'] == (stop is not None)
        assert high == D(row['high_water_observed']) and high-nav == D(row['drawdown_observed'])
        assert nav/previous-1 == D(row['daily_return']); previous = nav
    assert account['status'] == 'COMPLETE_ACCOUNTING' and not holdings and not account['open_holdings']
    assert nav == D(account['ending_nav']) and stop == account['stop_date']
    assert set(claims) == set(reported)
    for key, value in claims.items():
        other = reported[key]
        for field in ('security_id', 'type', 'created_date', 'cash_available_date', 'paid'):
            assert value[field] == other[field], (key, field)
        assert value['amount'] == D(other['amount'])
    # Entire-account cashflow reconciliation, independent of allocated tax bases.
    outgoing = sum((D(f['notional'])+D(f['fee_total']) for f in account['fills'] if f['side'] == 'buy'), D(0))
    incoming = sum((v['amount'] for v in claims.values()), D(0))
    assert nav-10000 == incoming-outgoing
    return dict(nav_days=len(account['daily']), fills=len(account['fills']), claims=len(claims),
                stop_date=stop, complete=True, independent_cashflow_reconciled=True)


def reference_check(account, paths, universe, result):
    expenses = defaultdict(lambda:D(0))
    for f in account['fills']: expenses[f['date']] += D(f['fee_total'])+D(f['slippage_cost'])
    previous = reference = D(10000); stock = D(0)
    assert len(paths) == len(universe) == len(account['daily'])
    for actual, target, source in zip(account['daily'], paths, universe):
        assert actual['date'] == target['date'] == source['date']
        weight = stock/previous
        rr = weight*D(str(source['universe_return']))-expenses[actual['date']]/previous
        reference *= 1+rr
        assert abs(reference-D(str(target['reference_nav']))) < D('.0000001')
        assert abs(weight-D(str(target['lagged_stock_exposure']))) < D('.0000000001')
        previous = D(actual['nav'])
        stock = sum((D(h['quantity'])*D(h['qualified_close']) for h in actual['holdings'].values()), D(0))
        stock += D(actual['market_sensitive_claim_value'])
    assert result['complete'] and abs(reference-D(str(result['ending_nav']))) < D('.0000001')
    assert abs(previous-reference-D(str(result['selection_difference']))) < D('.0000001')
    return dict(days=len(paths), decimal_arithmetic_reconciled=True)


def before():
    unchanged()
    out = dict(passed=True, synthetic=synthetic(), strict_freeze_preserved=True,
               original_artifacts_unchanged=True, fixed_scores_and_orders_unchanged=True)
    write(HERE/'completion-verification-before.json', out)
    print(json.dumps(out, indent=2))


def after():
    unchanged()
    for path,digest in load(HERE/'completion-freeze.json')['files'].items():
        assert sha(ROOT/path) == digest, path
    strict = load(HERE/'evaluation-result.json')
    universe = load(RAW/'universe-returns.json'); reports = {}
    for case in load(HERE/'completion-results.json')['cases']:
        account = c.load_account(case['account_file'])
        oldref = strict['account_files'][case['cost']]
        assert sha(ROOT/oldref['file']) == oldref['sha256']
        old = load(ROOT/oldref['file'])
        for a,b in zip(account['daily'][:85], old['daily'][:85]):
            assert {k:a[k] for k in b} == b and D(a['market_sensitive_claim_value']) == 0
        assert [f for f in account['fills'] if f['date'] < '2024-05-03'] == [f for f in old['fills'] if f['date'] < '2024-05-03']
        frames,actions = c.inputs(case)
        report = replay(account, frames, actions, case['cost'])
        paths = load(RAW/f'completion-{case["name"]}-reference.json')
        report['reference'] = reference_check(account, paths, universe, case['reference'])
        report['strict_prefix_days_identical'] = 85
        reports[case['name']] = report
        print(json.dumps(dict(case=case['name'], **report)), flush=True)
    unchanged()
    write(HERE/'completion-verification-after.json', dict(passed=True, scenarios=reports,
        completion_freeze_preserved=True, strict_freeze_preserved=True, original_artifacts_unchanged=True))


if __name__ == '__main__':
    {'before':before, 'after':after}[sys.argv[1]]()
