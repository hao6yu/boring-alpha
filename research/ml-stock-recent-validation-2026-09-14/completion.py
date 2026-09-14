"""Conditional stock-conversion completion, using frozen ranks and cached data."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal as D
import gzip
import json
import numpy as np
import recent as r
import evaluate as original
import completion_engine as engine
from acquire import HERE,ROOT,RAW,OLD,load,write,sha,scope

SPEC=load(HERE/'completion-protocol.json')
engine.frozen_policy=r.portfolio.frozen_policy


def cases():
    for multiplier in SPEC['cash_multipliers']:
        for delay in SPEC['whole_share_trade_delay_sessions']:
            for cost in SPEC['cost_cases']:
                yield dict(name=f'cash{multiplier}-delay{delay}-{cost}',cash_multiplier=multiplier,delay_sessions=delay,cost=cost)


def inputs(case):
    frames,actions,_=r.account_inputs()
    for child in ('XOM','VGNT','SGI'):
        for day,bar in r.child_rows(child).items():
            if day not in frames:continue
            assert bar['splitFactor']==1,'Child split requires explicit additional qualification'
            assert bar['divCash']<bar['close']*.04,'Child distribution requires explicit additional qualification'
            frames[day][child]=dict(close=str(bar['close']),volume=str(bar['volume']),qualified=True,status='listed',splitFactor='1',divCash=str(bar['divCash']))
            if day>=r.START and bar['divCash']:
                actions.append(dict(action_id=f'{child}:{day}:dividend',security_id=child,effective_date=day,type='dividend',verified=True,amount_per_share=str(bar['divCash']),cash_available_date=None))
    converted=[]
    for action in actions:
        symbol,day=action['security_id'],action['effective_date']
        if action['type']=='stock_distribution' and symbol in ('PXD','APTV','LEG'):
            terms=SPEC[symbol];child=terms['child']
            numerator=str(terms.get('ratio',terms.get('ratio_numerator')));denominator=str(terms.get('ratio_denominator',1))
            fixed_date=terms.get('publication_date',r.SESSIONS[r.INDEX[day]+5])
            quote=D(terms['published_cash_unit_price']) if 'published_cash_unit_price' in terms else D(str(r.child_rows(child)[day]['close']))
            action=dict(action,type='spinoff' if symbol=='APTV' else 'stock_merger',verified=True,
                        child_security_id=child,child_cik=terms['child_cik'],ratio_numerator=numerator,ratio_denominator=denominator,
                        fixed_unit_cash=str(quote*D(str(case['cash_multiplier']))),fixed_cash_date=fixed_date,
                        trade_available_date=r.SESSIONS[r.INDEX[day]+case['delay_sessions']],
                        qualification='CONDITIONAL_SETTLEMENT_SCENARIO_NOT_VERIFIED_BROKER_RECEIPT')
        converted.append(action)
    return frames,converted


def reference(account,universe):
    # Floating fractional entitlements have market exposure until their cash
    # amount is fixed. Include them in attribution without making tradable shares.
    proxy=deepcopy(account)
    for row in proxy['daily']:
        value=row['market_sensitive_claim_value']
        if D(value):row['holdings']['__floating_entitlement__']=dict(quantity=value,qualified_close='1')
    return original.exposure_reference(proxy,universe)


def save_account(name,account):
    path=RAW/f'completion-{name}.json.gz'
    path.write_bytes(gzip.compress(json.dumps(account,sort_keys=True,allow_nan=False).encode(),mtime=0))
    return dict(file=str(path.relative_to(ROOT)),sha256=sha(path))


def load_account(ref):
    path=ROOT/ref['file'];assert sha(path)==ref['sha256']
    return json.loads(gzip.decompress(path.read_bytes()))


def run():
    scope();assert load(HERE/'completion-verification-before.json')['passed']
    assert sha(RAW/'predictions.json')==SPEC['fixed_predictions_sha256']
    assert sha(HERE/'evaluation-result.json')==SPEC['strict_result_sha256']
    assert not (HERE/'completion-results.json').exists()
    _,candidates,keep,orders=original.predictions_and_schedule()
    assert orders==load(HERE/'orders.json')
    frozen=[HERE/n for n in ['completion.py','completion_engine.py','completion_verify.py','completion-protocol.json','completion-verification-before.json']]
    write(HERE/'completion-freeze.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),files={str(p.relative_to(ROOT)):sha(p) for p in frozen},cases=list(cases()),central_cases=['cash1-delay5-base','cash1-delay5-stress'],ranking_orders_unchanged=True))
    universe=load(RAW/'universe-returns.json');out=[]
    for case in cases():
        frames,actions=inputs(case)
        account=engine.simulate(calendar=r.SESSIONS,prices=frames,candidates=candidates,actions=actions,cost_case=case['cost'],rank_mode='matched',retention_by_day=keep)
        ref=save_account(case['name'],account);metric=r.m.metrics(account);metric['yearly']=original.yearly(account)
        metric['max_holdings']=max(len(d['holdings']) for d in account['daily'])
        metric['forced_extra_holding_days']=sum(len(d['holdings'])>10 for d in account['daily'])
        metric['mean_stock_exposure']=float(np.mean([(sum(float(h['quantity'])*float(h['qualified_close']) for h in d['holdings'].values())+float(d['market_sensitive_claim_value']))/float(d['nav']) for d in account['daily'] if d['nav'] is not None]))
        benchmark,paths=reference(account,universe)
        write(RAW/f'completion-{case["name"]}-reference.json',paths)
        result=dict(case,metrics=metric,account_file=ref,reference=benchmark,uncertainty=original.uncertainty(paths),held_stock_actions=[x for x in account['action_log'] if x['type'] in ('stock_merger','spinoff')])
        out.append(result)
        print(json.dumps(dict(case=case['name'],status=metric['status'],profit=metric['profit'],cagr=metric['cagr'],max_drawdown=metric['max_drawdown'],forced_extra_holding_days=metric['forced_extra_holding_days'])),flush=True)
    write(HERE/'completion-results.json',dict(status='CONDITIONAL_CORPORATE_ACTION_SETTLEMENT_SENSITIVITIES',cases=out,new_paid_data_usd=0,new_network_data_requests=0,model_fits=0,ranking_orders_unchanged=True,strict_result_unchanged=sha(HERE/'evaluation-result.json')==SPEC['strict_result_sha256']))
    scope()


if __name__=='__main__':run()
