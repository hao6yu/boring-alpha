"""Synthetic source/price joins. No archived prices, documents, or labels read."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import sys

import pytest


PATH=Path(__file__).resolve().parents[1]/'research/equity-event-test-2026-09-10/panel.py'
sys.path.insert(0,str(PATH.parent))
spec=importlib.util.spec_from_file_location('equity_event_panel_audit',PATH)
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def setup_panel(tmp_path,monkeypatch,filing='2022-06-01'):
    sessions=[]; day=date(2019,10,1)
    while day<=date(2023,12,29):
        if day.weekday()<5: sessions.append(day.isoformat())
        day+=timedelta(days=1)
    # Entirely invented flat raw prices and matching adjusted prices.
    series={s:{'rows':{d:{'close':50.0,'adjClose':50.0,'volume':100000.0,
                           'splitFactor':1.0,'divCash':0.0} for d in sessions},
               'issues':{},'source_sha256':'synthetic'} for s in ('A','SPY')}
    current={'accession':'current','filing_date':filing,'acceptance_eastern':filing+'T16:01:00-04:00',
             'security':{'historical_symbol':'A','status':'VERIFIED_SINGLE_COMMON_CLASS'}}
    prior={'accession':'prior','filing_date':'2019-06-01','acceptance_eastern':'2019-06-01T16:01:00-04:00'}
    slot={'slot_id':'focus','cik':'0000000001','status':'READY','current':current,'prior':prior,
          'checks':{k:True for k in ('current_release','earliest_event','prior_release','period_identity','identity','timing')}}
    slots=[slot]+[{'slot_id':f'missing:{i}','cik':str(i),'status':'UNRESOLVED','current':None} for i in range(1599)]
    pair={'status':'SOURCE_PAIR_READ_NUMERIC_COVERAGE_EXPLICIT','missing_reasons':[],
          'flags':{'document_types_match':True,'scope':'quarter','fiscal_quarter_ordinal':1,
                   'unequal_duration':False,'accounting_transition':False,
                   'current_metric_currency':{'diluted_eps':['USD']}},
          'current':{'period_end':'2019-12-31','narrative_words':10,'documents':[],
                     'flags':{'source_document_types':['EARNINGS_RELEASE'],'split_mentioned':False,
                              'unstructured_financial_text_unresolved':False}},
          'original_prior':{'narrative_words':10,'documents':[],
                            'flags':{'source_document_types':['EARNINGS_RELEASE'],
                                     'unstructured_financial_text_unresolved':False}},
          'comparisons':{'revenue':{'same_current_release_comparison_eligible':True,
                                    'current_value':'100','current_release_comparable_prior_value':'80','missing_reasons':[]},
                         'diluted_eps':{'same_current_release_comparison_eligible':True,
                                        'current_value':'.2','current_release_comparable_prior_value':'.1','missing_reasons':[]}},
          'narrative':{'current':'Management reports customer demand and discusses operations.',
                       'original_prior':'Management discusses the earlier business and its outlook.'}}
    (tmp_path/'sec-cohort.json').write_text(json.dumps({'policy_sha256':p.POLICY_SHA,'issuers':[{}]*100}))
    (tmp_path/'price-manifest.json').write_text('{}')
    captured={}
    monkeypatch.setattr(p,'HERE',tmp_path); monkeypatch.setattr(p,'ROOT',tmp_path)
    monkeypatch.setattr(p,'RAW',tmp_path/'ignored')
    monkeypatch.setattr(p,'calendar',lambda:sessions)
    monkeypatch.setattr(p,'load_prices',lambda **kwargs:(series,{}))
    monkeypatch.setattr(p,'extract_pair',lambda _:deepcopy(pair))
    monkeypatch.setattr(p,'digest',lambda _:'synthetic')
    def write(path,value):
        captured[path.name]=deepcopy(value)
        return 'synthetic'
    monkeypatch.setattr(p,'write',write)
    def run():
        (tmp_path/'sec-events.json').write_text(json.dumps({'policy_sha256':p.POLICY_SHA,'status':'SYNTHETIC','slots':slots}))
        p.build()
        return next(r for r in captured['development-panel.json'] if r['event_id']=='focus')
    return run,series,sessions,slot,pair


def test_future_label_availability_cannot_change_ready_or_past_features(tmp_path,monkeypatch):
    run,series,sessions,slot,pair=setup_panel(tmp_path,monkeypatch,'2020-06-01')
    first=run()
    assert first['status']=='READY' and first['target_pp']==0
    assert first['entry_date']=='2020-06-02'
    del series['A']['rows'][first['exit_date']]
    second=run()
    assert second['status']=='READY' and second['target_pp'] is None
    assert first['features']==second['features']
    assert second['label_audit']['reason']=='UNRESOLVED_LABEL_PRICE_SPAN'


@pytest.mark.parametrize('filing',['2021-12-20','2022-06-01'])
def test_unmatured_development_and_evaluation_targets_are_not_calculated(tmp_path,monkeypatch,filing):
    run,_,_,_,_=setup_panel(tmp_path,monkeypatch,filing)
    def forbidden(*args): raise AssertionError('target calculation crossed the development cutoff')
    monkeypatch.setattr(p,'target',forbidden)
    result=run()
    assert result['status']=='READY' and result['target_pp'] is None


@pytest.mark.parametrize('defect',['empty','unstructured','corrupt','document_type'])
def test_unqualified_narrative_cannot_be_ready(tmp_path,monkeypatch,defect):
    run,_,_,_,pair=setup_panel(tmp_path,monkeypatch)
    if defect=='empty': pair['narrative']['original_prior']=' '
    if defect=='unstructured': pair['current']['flags']['unstructured_financial_text_unresolved']=True
    if defect=='corrupt': pair['current']['documents']=[{'encoding_artifact_word_count':30,'encoding_artifact_word_fraction':.1}]
    if defect=='document_type': pair['flags']['document_types_match']=False
    result=run()
    assert result['status']=='UNRESOLVED' and result['features']=={}


def test_old_action_gap_changes_only_eps_feature_and_preentry_split_is_seen(tmp_path,monkeypatch):
    run,series,sessions,slot,pair=setup_panel(tmp_path,monkeypatch)
    first=run(); assert first['features']['scaled_eps_change'] is not None
    # An old gap outside the61-close predictor window still blocks EPS/share basis.
    del series['A']['rows']['2020-02-03']
    missing=run()
    assert missing['status']=='READY' and missing['features']['scaled_eps_change'] is None
    assert not missing['eps_action_history_audit']['complete']
    series['A']['rows']['2020-02-03']={'close':50.0,'adjClose':50.0,'volume':100000.0,'splitFactor':2.0,'divCash':0.0}
    split=run()
    assert split['status']=='READY' and split['features']['scaled_eps_change'] is None
    assert split['eps_action_history_audit']['complete']
    assert 'EPS_EFFECTIVE_SHARE_BASIS_NEEDS_SOURCE_REVIEW' in split['feature_missing_reasons']['scaled_eps_change']


def test_late_original_prior_and_missing_required_source_block_ready(tmp_path,monkeypatch):
    run,_,_,slot,pair=setup_panel(tmp_path,monkeypatch)
    slot['prior']['filing_date']='2022-06-02'
    late=run()
    assert late['status']=='UNRESOLVED' and 'PRIOR_SOURCE_NOT_PUBLIC_BEFORE_ENTRY' in late['reasons']
    slot['prior']['filing_date']='2019-06-01'
    slot['checks']['prior_release']=False
    missing=run()
    assert missing['status']=='UNRESOLVED' and 'ORIGINAL_SOURCE_JOIN_UNRESOLVED' in missing['reasons']


def test_source_proven_action_conflict_blocks_only_its_bounded_history(tmp_path,monkeypatch):
    import csv
    import io
    import zipfile
    from price_data import FIELDS, parse
    assert parse(b"Error: Ticker 'OLD' not found") == ({}, {})
    output = io.StringIO()
    fields = sorted(FIELDS)
    writer = csv.DictWriter(output,fieldnames=fields); writer.writeheader()
    for day in ['2020-05-01','2020-05-04','2020-05-05']:
        row = {key:50 for key in fields}; row.update(date=day,volume=100000,adjVolume=100000,divCash=0,splitFactor=1)
        writer.writerow(row)
    (tmp_path/'A.csv').write_text(output.getvalue())
    with zipfile.ZipFile(tmp_path/'directory.zip','w') as z:
        z.writestr('supported_tickers.csv','ticker,exchange,assetType,priceCurrency,startDate,endDate\nA,NYSE,Stock,USD,2010-01-01,2023-12-29\n')
    (tmp_path/'tiingo-directory-source.json').write_text(json.dumps({'file':'directory.zip','sha256':p.digest(tmp_path/'directory.zip')}))
    (tmp_path/'price-source-exceptions.json').write_text(json.dumps({'policy_sha256':p.POLICY_SHA,'symbols':{'A':[{
        'start_date':'2020-05-04','end_date':'2020-05-04','reason':'Synthetic issuer action contradiction',
        'verified_source_conflict':True,'source_evidence':{'source':'synthetic original notice'}}]}}))
    manifest = {'policy_sha256':p.POLICY_SHA,'symbols':{'A':{'status':'DOWNLOADED','path':'A.csv','sha256':p.digest(tmp_path/'A.csv')}}}
    monkeypatch.setattr(p,'HERE',tmp_path); monkeypatch.setattr(p,'ROOT',tmp_path)
    series,_ = p.load_prices(manifest)
    assert not p.qualified_span('A',['2020-05-01','2020-05-04','2020-05-05'],series)[0]
    assert p.qualified_span('A',['2020-05-01','2020-05-05'],series)[0]
    assert 'ORIGINAL_SOURCE_CONFLICT' in series['A']['issues']['2020-05-04'][0]
