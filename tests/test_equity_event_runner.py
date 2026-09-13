"""Runner integration tests using invented records only; no historical data."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


PATH = Path(__file__).resolve().parents[1]/'research/equity-event-test-2026-09-10/run_experiment.py'
sys.path.insert(0,str(PATH.parent))
spec = importlib.util.spec_from_file_location('equity_event_runner_audit',PATH)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
SECURITY = '0000000001:single_common'
DAYS = ['2022-01-03','2022-01-04','2022-01-05']


def setup_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(r,'HERE',tmp_path)
    monkeypatch.setattr(r,'session_schedule',lambda days: {
        d:{'open':d+'T14:30:00+00:00','close':d+'T21:00:00+00:00'} for d in days})
    raw = {'close':50.0,'volume':100000.0,'divCash':0.0,'splitFactor':1.0}
    series = {s:{'rows':{d:deepcopy(raw) for d in DAYS},'issues':{},'source_sha256':s+'-synthetic'}
              for s in ['OLD','NEW']}
    cohort = {'issuers':[{'cik':'0000000001','seed_acceptance_eastern':'2021-12-01T16:01:00-05:00',
                          'historical_symbol':'OLD'}]}
    sec = {'slots':[]}
    envelope = {'policy_sha256':r.POLICY_SHA,'actions':{},'security_status_events':[]}
    def run():
        (tmp_path/'corporate-action-evidence.json').write_text(json.dumps(envelope))
        return r.source_frames(series,DAYS,sec,cohort)
    return run,series,sec,envelope


def test_identity_uses_previous_known_cover_and_rejects_same_day_conflict(tmp_path,monkeypatch):
    run,_,sec,_ = setup_sources(tmp_path,monkeypatch)
    rec = {'filing_date':'2022-01-04','acceptance_eastern':'2022-01-04T10:00:00-05:00',
           'security':{'status':'VERIFIED_SINGLE_COMMON_CLASS','historical_symbol':'NEW'}}
    sec['slots'] = [{'cik':'0000000001','current':rec}]
    prices,_,_ = run()
    assert prices['2022-01-04'][SECURITY]['source_ticker']=='OLD'
    assert prices['2022-01-05'][SECURITY]['source_ticker']=='NEW'
    conflict = deepcopy(rec)
    conflict['security']['historical_symbol']='OLD'
    sec['slots'].append({'cik':'0000000001','current':conflict})
    with pytest.raises(ValueError,match='Conflicting historical tickers'):
        run()


def test_status_distinguishes_actual_close_and_preopen_knowledge(tmp_path,monkeypatch):
    run,series,_,evidence = setup_sources(tmp_path,monkeypatch)
    evidence['security_status_events'] = [{'security_id':SECURITY,'status':'halted',
        'effective_at':'2022-01-03T17:00:00Z','available_at':'2022-01-03T17:01:00Z',
        'verified':True,'source_evidence':{'url':'synthetic-official'}}]
    prices,_,_ = run()
    assert prices[DAYS[0]][SECURITY]['status']=='halted'
    assert prices[DAYS[0]][SECURITY]['status_before_open']=='listed'
    assert prices[DAYS[1]][SECURITY]['status_before_open']=='halted'
    evidence['security_status_events'][0]['effective_at']='2022-01-03T22:00:00Z'
    evidence['security_status_events'][0]['available_at']='2022-01-03T22:01:00Z'
    prices,_,_ = run()
    assert prices[DAYS[0]][SECURITY]['status']=='listed'
    del series['OLD']['rows'][DAYS[1]]
    prices,_,_ = run()
    assert prices[DAYS[1]][SECURITY]['status_before_open']=='halted'
    assert prices[DAYS[1]][SECURITY]['qualified'] is False
    assert 'close' not in prices[DAYS[1]][SECURITY]
    other = dict(evidence['security_status_events'][0],status='otc')
    evidence['security_status_events'].append(other)
    assert run()[0][DAYS[1]][SECURITY]['status']=='unknown'


def test_action_amount_kind_and_payment_evidence_are_distinct(tmp_path,monkeypatch):
    run,series,_,evidence = setup_sources(tmp_path,monkeypatch)
    series['OLD']['rows'][DAYS[0]]['divCash']=.25
    dividend_id=SECURITY+':'+DAYS[0]+':dividend'
    proof={'security_id':SECURITY,'effective_date':DAYS[0],'type':'dividend','verified':True,
           'source_price_sha256':'OLD-synthetic','amount_per_share':'.25','cash_available_date':None}
    evidence['actions'][dividend_id]=proof
    actions=run()[1]
    assert actions[0]['verified'] and actions[0]['cash_available_date'] is None
    proof['amount_per_share']='.26'
    with pytest.raises(ValueError,match='dividend source conflicts'):
        run()
    proof['amount_per_share']='.25'; proof['cash_available_date']=DAYS[2]
    with pytest.raises(ValueError,match='separate availability evidence'):
        run()
    proof.update(cash_availability_verified=True,cash_availability_evidence={'url':'synthetic-payment'})
    assert run()[1][0]['cash_available_date']==DAYS[2]
    proof['cash_available_date']=None
    series['OLD']['rows'][DAYS[1]]['splitFactor']=2.0
    split_id=SECURITY+':'+DAYS[1]+':split'
    split={'security_id':SECURITY,'effective_date':DAYS[1],'type':'split','verified':True,
           'source_price_sha256':'OLD-synthetic','factor':'2','action_kind':'distribution'}
    evidence['actions'][split_id]=split
    assert run()[1][1]['verified'] is False
    split['action_kind']='stock_split'
    assert run()[1][1]['verified'] is True
    split['factor']='3'
    with pytest.raises(ValueError,match='split source conflicts'):
        run()


def test_merger_claim_does_not_require_dividend_column_or_terminal_price(tmp_path,monkeypatch):
    run,series,_,evidence = setup_sources(tmp_path,monkeypatch)
    del series['OLD']['rows'][DAYS[1]]
    evidence['actions']['merger-synthetic']={'security_id':SECURITY,'effective_date':DAYS[1],
        'type':'merger_cash','amount_per_share':'95','cash_available_date':None,
        'verified':True,'source_evidence':{'url':'synthetic-merger'}}
    actions=run()[1]
    assert len(actions)==1 and actions[0]['type']=='merger_cash'
    assert actions[0]['verified'] is True and actions[0]['cash_available_date'] is None


def test_forecasts_reject_duplicates_identity_changes_and_nonfinite_scores():
    pool=[{'event_id':'a','cik':'1','entry_date':DAYS[0],'exit_date':DAYS[2]}]
    forecast=[{**pool[0],'numeric':-2,'text':3}]
    assert r.checked_forecasts(pool,forecast)['a']['text']==3
    with pytest.raises(ValueError,match='duplicate'):
        r.checked_forecasts(pool,forecast*2)
    with pytest.raises(ValueError,match='timing or issuer'):
        r.checked_forecasts(pool,[{**forecast[0],'entry_date':DAYS[1]}])
    with pytest.raises(ValueError,match='Non-finite'):
        r.checked_forecasts(pool,[{**forecast[0],'text':float('nan')}])


def test_panel_dates_must_equal_the_simulator_source_date_horizon():
    start=date(2022,1,3)
    sessions=[(start+timedelta(days=i)).isoformat() for i in range(31)
              if (start+timedelta(days=i)).weekday()<5]
    row={'filing_date':'2021-12-30','acceptance_date_et':'2021-12-31',
         'entry_date':sessions[0],'exit_date':sessions[20]}
    r.checked_pool_timing([row],sessions)
    with pytest.raises(ValueError,match='source-date execution horizon'):
        r.checked_pool_timing([{**row,'entry_date':sessions[1]}],sessions)


def setup_evaluation(tmp_path,monkeypatch):
    here=tmp_path/'research'; raw=tmp_path/'ignored'
    here.mkdir(); raw.mkdir()
    monkeypatch.setattr(r,'ROOT',tmp_path); monkeypatch.setattr(r,'HERE',here); monkeypatch.setattr(r,'RAW',raw)
    monkeypatch.setattr(r,'private_path',lambda path:path.resolve())
    monkeypatch.setattr(r,'code_hashes',lambda:{'runner':'synthetic-code'})
    monkeypatch.setattr(r,'runtime_provenance',lambda days:{'synthetic_schedule':days})
    start=date(2022,1,3)
    sessions=['2021-12-31']+[(start+timedelta(days=i)).isoformat() for i in range(31)
                            if (start+timedelta(days=i)).weekday()<5]
    monkeypatch.setattr(r,'calendar',lambda:sessions)
    monkeypatch.setattr(r,'policy',lambda:{'evaluation_start':DAYS[0],'evaluation_end':sessions[-1],
                                        'last_entry_date':DAYS[2]})
    for name in r.BOUND_INPUTS:
        r.write(here/name,{})
    r.write(here/'source-readiness.json',{'ready':True,'reasons':[]})
    r.write(here/'data-expense.json',{'amount_usd':'25','basis':'quote','source':'synthetic'})
    r.write(here/'sec-events.json',{'slots':[]})
    r.write(here/'sec-cohort.json',{'issuers':[]})
    r.write(here/'price-manifest.json',{})
    r.write(here/'panel-inventory.json',{'sec_events_path':'research/sec-events.json'})
    pool=[{'event_id':str(i),'cik':str(i),'security_id':str(i)+':single_common','accession':str(i),
           'filing_date':'2021-12-31','acceptance_date_et':'2021-12-31','entry_date':DAYS[0],
           'exit_date':sessions[21],'status':'READY','target_pp':None} for i in range(2)]
    pool_sha=r.write(raw/'pool.json',pool)
    forecasts=[{k:row[k] for k in ['event_id','cik','entry_date','exit_date']} |
               {'numeric':-.5 if i==0 else 2,'text':2 if i==0 else -.5} for i,row in enumerate(pool)]
    forecast_sha=r.write(raw/'forecasts.json',forecasts)
    (raw/'model.bin').write_bytes(b'synthetic-model')
    frozen={'policy_sha256':r.POLICY_SHA,'code_sha256':r.code_hashes(),
        'price_manifest_sha256':r.digest(here/'price-manifest.json'),
        'bound_execution_inputs_sha256':r.bound_inputs(),'runtime':r.runtime_provenance(sessions),
        'sec_events_sha256':r.digest(here/'sec-events.json'),'cohort_sha256':r.digest(here/'sec-cohort.json'),
        'model_artifact':{'path':'ignored/model.bin','sha256':r.digest(raw/'model.bin')},
        'evaluation_pool':{'path':'ignored/pool.json','sha256':pool_sha,'observations':2,'issuers':2},
        'forecasts':{'path':'ignored/forecasts.json','sha256':forecast_sha},'sample_counts':{}}
    r.write(here/'frozen-models.json',frozen)
    calls=[]
    monkeypatch.setattr(r,'load_prices',lambda:({},{}))
    monkeypatch.setattr(r,'source_frames',lambda *args:({},[],{}))
    monkeypatch.setattr(r,'target',lambda *args:(None,{'reason':'SYNTHETIC_FUTURE_PRICE_GAP'}))
    def simulate(**kw):
        calls.append(deepcopy(kw))
        return {'initial_expense':kw.get('initial_expense',0)}
    monkeypatch.setattr(r,'simulate',simulate)
    def evaluate(accounts,**kw):
        assert all(kw['expense_accounts'][cost][model]['initial_expense']==25
                   for cost in ['base','stress'] for model in ['numeric','text','matched_event'])
        return {'status':'SYNTHETIC_ONLY'}
    monkeypatch.setattr(r,'evaluate',evaluate)
    return here,calls


def test_all_models_keep_same_preentry_pool_despite_scores_and_missing_future_labels(tmp_path,monkeypatch):
    here,calls=setup_evaluation(tmp_path,monkeypatch)
    report=r.run_evaluation()
    assert len(calls)==12
    assert all([e['event_id'] for e in call['candidates']]==['0','1'] for call in calls)
    assert sum(call.get('initial_expense',0)==25 for call in calls)==6
    assert report['label_coverage']['unresolved_outcomes']==2
    assert report['label_coverage']['frozen_pool']==2
    assert all(e['eligibility_status']=='READY' for c in calls for e in c['candidates'])
    assert (here/'evaluation-result.json').exists()


def test_changed_execution_evidence_aborts_before_prices_or_simulation(tmp_path,monkeypatch):
    here,calls=setup_evaluation(tmp_path,monkeypatch)
    r.write(here/'corporate-action-evidence.json',{'changed':True})
    def forbidden():
        raise AssertionError('price input read before provenance gate')
    monkeypatch.setattr(r,'load_prices',forbidden)
    with pytest.raises(ValueError,match='input changed after model freeze'):
        r.run_evaluation()
    assert calls==[]


def test_private_output_must_be_within_raw_and_gitignored(tmp_path,monkeypatch):
    monkeypatch.setattr(r,'ROOT',tmp_path); monkeypatch.setattr(r,'RAW',tmp_path/'ignored')
    monkeypatch.setattr(r.subprocess,'run',lambda *args,**kw:SimpleNamespace(returncode=0))
    assert r.private_path(tmp_path/'ignored'/'output.json')==tmp_path/'ignored'/'output.json'
    with pytest.raises(ValueError,match='registered raw directory'):
        r.private_path(tmp_path/'public.json')
    monkeypatch.setattr(r.subprocess,'run',lambda *args,**kw:SimpleNamespace(returncode=1))
    with pytest.raises(ValueError,match='not git-ignored'):
        r.private_path(tmp_path/'ignored'/'output.json')
