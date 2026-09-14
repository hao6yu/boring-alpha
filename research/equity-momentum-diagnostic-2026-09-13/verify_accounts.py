"""Independent raw-price, fee, and Decimal ledger reconciliation; no simulation."""
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, ROUND_CEILING
import hashlib
import json
import math

from momentum_io import HERE, ROOT, RAW, SOURCE_HERE, POLICY_SHA, atomic, digest, policy


def run():
    policy()
    result = json.loads((HERE / 'evaluation-result.json').read_text())
    start = json.loads((HERE / 'evaluation-start.json').read_text())
    assert result['policy_sha256'] == start['policy_sha256'] == POLICY_SHA
    for group, directory in [('code', HERE), ('source_adapter_code', SOURCE_HERE), ('sources', SOURCE_HERE)]:
        assert all(digest(directory / name) == sha for name, sha in start[group].items())
    assert digest(ROOT / start['identity_source']) == start['identity_source_sha256']
    freeze = json.loads((HERE / 'input-freeze.json').read_text())
    assert digest(HERE / 'input-freeze.json') == result['input_freeze_sha256']
    assert digest(ROOT / freeze['input_file']) == freeze['sha256']
    inputs = json.loads((ROOT / freeze['input_file']).read_text())
    identity = json.loads((RAW / 'source-audit.json').read_text())['identities']
    manifest = json.loads((SOURCE_HERE / 'price-manifest.json').read_text())
    evidence = json.loads((SOURCE_HERE / 'corporate-action-evidence.json').read_text())
    actions = defaultdict(list)
    for key, action in evidence['actions'].items():
        actions[action['effective_date']].append(dict(action, action_id=key))
    cache = {}

    def source(cik, day):
        ticker = max((t, s) for t, s in identity[cik] if t < day)[1]
        if ticker not in cache:
            meta = manifest['symbols'][ticker]
            path = ROOT / meta['path']
            assert digest(path) == meta['sha256']
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            assert all('2019-10-01' <= r['date'][:10] <= '2023-12-29' for r in rows)
            cache[ticker] = {r['date'][:10]: r for r in rows}
        return cache[ticker][day]

    # Recompute every admitted score from raw adjusted closes and check all
    # predeclared rank/retention sets. Qualification gaps remain explicit.
    ready = defaultdict(dict)
    for row in inputs['slots']:
        if row['status'] != 'READY':
            continue
        cik, first, last = row['cik'], row['momentum_start'], row['momentum_end']
        assert first < last < row['entry_date']
        entry_index = int(row['entry_date'][:4]) * 12 + int(row['entry_date'][5:7]) - 1
        for day, offset in [(first, 13), (last, 2)]:
            assert int(day[:4]) * 12 + int(day[5:7]) - 1 == entry_index - offset
        score = D(source(cik, last)['adjClose']) / D(source(cik, first)['adjClose']) - 1
        assert abs(score - D(str(row['momentum']))) < D('1e-12')
        ready[row['entry_month']][cik] = float(score)
    for month in inputs['monthly']:
        scores = ready[month['entry_month']]
        for name, bands in month['orders'].items():
            if name == 'momentum':
                ordered = sorted(scores, key=lambda c: (-scores[c], hashlib.sha256(f'BA-stock-momentum-buffer-v1|{c}'.encode()).hexdigest()))
            else:
                seed = int(name.rsplit('_', 1)[1])
                ordered = sorted(scores, key=lambda c: hashlib.sha256(f'BA-stock-unranked-v1|{seed}|{c}'.encode()).hexdigest())
            assert bands['all_ranked_ciks'] == ordered
            assert bands['entry_ciks'] == ordered[:math.ceil(len(ordered) * .10)]
            assert bands['retention_ciks'] == ordered[:math.ceil(len(ordered) * .20)]

    cent = lambda x: x.quantize(D('.01'), rounding=ROUND_CEILING)
    reports = []
    for cost, references in result['ledgers'].items():
        slip = D('.001') if cost == 'base' else D('.005')
        for name, reference in references.items():
            path = ROOT / reference['path']
            assert digest(path) == reference['sha256']
            account = json.loads(path.read_text())
            events = {r['event_id']: r for r in inputs['candidates'][name]}
            fills = defaultdict(list)
            for fill in account['fills']:
                fills[fill['date']].append(fill)
                q, close = D(fill['quantity']), D(source(fill['cik'], fill['date'])['close'])
                assert q > 0 and q == q.to_integral_value() and close == D(fill['raw_close'])
                notional = q * close * (1 + slip if fill['side'] == 'buy' else 1 - slip)
                fees = {
                    'commission': cent(min(D('.01') * notional, max(D(1), D('.005') * q))),
                    'sec': cent(D('.0000206') * notional) if fill['side'] == 'sell' else D(0),
                    'taf': cent(min(D('9.79'), D('.000195') * q)) if fill['side'] == 'sell' else D(0),
                    'cat': cent(D('.000003') * q),
                }
                assert fees == {k: D(v) for k, v in fill['fees'].items()}
                assert notional == D(fill['notional']) and sum(fees.values()) == D(fill['fee_total'])
                assert q * close * slip == D(fill['slippage_cost'])
                if fill['side'] == 'buy':
                    event = events[fill['event_id']]
                    assert max(event['filing_date'], event['acceptance_date_et']) < fill['date']

            cash = high = D(10000)
            holdings, claims, seen_actions = {}, {}, []
            navs, first_stop, missing_day = [], None, None
            source_claims = {c['claim_id']: c for c in account['claims']}
            for row in account['daily']:
                day = row['date']
                if row['nav'] is None:
                    missing_day = day
                    break  # Never manufacture a post-exchange price or complete NAV.
                for claim in claims.values():
                    if not claim['paid'] and claim['cash_available_date'] is not None and claim['cash_available_date'] <= day:
                        cash += D(claim['amount'])
                        claim['paid'] = True
                for action in sorted(actions[day], key=lambda a: a['action_id']):
                    sec, key = action['security_id'], action['action_id']
                    if sec not in holdings:
                        continue
                    assert action['verified'] is True
                    holding = holdings[sec]
                    if action['type'] == 'split':
                        factor = D(action['factor'])
                        assert factor == D(source(holding['cik'], day)['splitFactor'])
                        holding['quantity'] *= factor
                        assert holding['quantity'] == holding['quantity'].to_integral_value()
                    else:
                        claim = dict(source_claims[key], paid=False)
                        per_share = D(action['amount_per_share'])
                        if action['type'] == 'dividend':
                            assert per_share == D(source(holding['cik'], day)['divCash'])
                        assert D(claim['amount']) == holding['quantity'] * per_share
                        assert D(claim['entitled_quantity']) == holding['quantity']
                        assert D(claim['originating_position_basis']) == holding['basis']
                        assert claim['cash_available_date'] == action['cash_available_date']
                        claims[key] = claim
                        if claim['cash_available_date'] is not None and claim['cash_available_date'] <= day:
                            cash += D(claim['amount'])
                            claim['paid'] = True
                        if action['type'] == 'merger_cash':
                            del holdings[sec]
                    seen_actions.append(key)
                for fill in fills[day]:
                    sec, q = fill['security_id'], D(fill['quantity'])
                    value, fee = D(fill['notional']), D(fill['fee_total'])
                    if fill['side'] == 'buy':
                        assert sec not in holdings and first_stop is None
                        cash -= value + fee
                        holdings[sec] = {'quantity': q, 'cik': fill['cik'], 'basis': value + fee}
                        assert cash >= 2000 and len(holdings) <= 10
                    else:
                        assert holdings[sec]['quantity'] == q
                        claim = next(c for c in account['claims'] if c['type'] == 'sale' and c['event_id'] == fill['event_id'])
                        assert D(claim['amount']) == value - fee
                        earliest = (date.fromisoformat(day) + timedelta(days=7)).isoformat()
                        available = next((d['date'] for d in account['daily'] if d['date'] >= earliest), None)
                        assert claim['cash_available_date'] == available
                        claims[claim['claim_id']] = dict(claim, paid=False)
                        del holdings[sec]
                equity = sum((h['quantity'] * D(source(h['cik'], day)['close']) for h in holdings.values()), D(0))
                unpaid = sum((D(c['amount']) for c in claims.values() if not c['paid']), D(0))
                nav = cash + unpaid + equity
                assert nav == D(row['nav']) and cash == D(row['settled_cash']) and unpaid == D(row['unpaid_claim_value'])
                assert set(holdings) == set(row['holdings'])
                for sec, holding in holdings.items():
                    assert holding['quantity'] == D(row['holdings'][sec]['quantity'])
                high = max(high, nav)
                assert high == D(row['high_water_observed']) and high - nav == D(row['drawdown_observed'])
                if high - nav >= 2000 and first_stop is None:
                    first_stop = day
                assert row['account_stopped'] == (first_stop is not None)
                navs.append(nav)
            last_checked = account['daily'][len(navs) - 1]['date']
            assert sorted(seen_actions) == sorted(a['action_id'] for a in account['action_log'] if a['date'] <= last_checked)
            if missing_day is None:
                assert account['status'] == 'COMPLETE_ACCOUNTING' and not holdings and not account['open_holdings']
                assert navs[-1] == D(account['ending_nav']) and cash == D(account['ending_settled_cash'])
                assert first_stop == account['stop_date']
                assert set(claims) == set(source_claims)
                assert all(c['paid'] == source_claims[k]['paid'] for k, c in claims.items())
                # Include merger-terminated positions, absent from the inherited
                # sell-fill-only completed_positions convenience list.
                pnl = sum((D(p['net_sale_proceeds']) - D(p['cost_basis']) for p in account['completed_positions']), D(0))
                pnl += sum((D(c['amount']) for c in account['claims'] if c['type'] == 'dividend'), D(0))
                pnl += sum((D(c['amount']) - D(c['originating_position_basis']) for c in account['claims'] if c['type'] == 'merger_cash'), D(0))
                assert pnl == navs[-1] - 10000
            else:
                assert account['status'] == 'UNRESOLVED' and account['ending_nav'] is None
                assert name in ('unranked_00', 'unranked_10') and missing_day == '2023-09-12'
            reports.append({'cost_case': cost, 'account': name,
                'status': 'RECONCILED' if missing_day is None else 'VALID_PREFIX_RECONCILED_REMAINDER_UNRESOLVED',
                'daily_NAVs_reconciled': len(navs), 'last_reconciled_date': last_checked,
                'fills_recomputed_from_raw_source': len(account['fills']),
                'cash_claims_checked_in_replayed_period': len(claims),
                'corporate_actions_checked_in_replayed_period': len(seen_actions),
                'ending_nav': account['ending_nav'], 'first_unpriced_date': missing_day,
                'first_halt_recomputed': first_stop})
    record = {'status': '38_COMPLETE_ACCOUNTS_AND_4_INCOMPLETE_PREFIXES_RECONCILED',
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'policy_sha256': POLICY_SHA, 'result_sha256': digest(HERE / 'evaluation-result.json'),
        'verifier_sha256': digest(HERE / 'verify_accounts.py'),
        'accounts': reports, 'raw_price_files_rechecked': len(cache),
        'ready_scores_recomputed': sum(len(v) for v in ready.values()),
        'monthly_model_rankings_checked': 24 * 21, 'source_and_strategy_code_unchanged': True,
        'qualification': 'Independent Decimal cash/claim/share replay, raw-file fill checks and ranking recalculation. Same cached evidence, not external replication. Full comparison remains unresolved; no averaging of only complete controls.'}
    atomic(HERE / 'account-verification.json', record)
    print(json.dumps({k: v for k, v in record.items() if k != 'accounts'}))


if __name__ == '__main__':
    run()
