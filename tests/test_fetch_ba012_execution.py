"""Offline checks for the narrow execution-bar acquisition."""
import gzip
import importlib.util
import io
import json
from decimal import Decimal
from pathlib import Path
import urllib.request
import pytest

SPEC = importlib.util.spec_from_file_location('execution_archive', Path(__file__).parents[1] / 'tools/fetch_ba012_execution.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

@pytest.fixture
def setup(tmp_path, monkeypatch):
    old, settlements = tmp_path / 'old', tmp_path / 'settlements'
    old.mkdir(); settlements.mkdir()
    monkeypatch.setattr(m, 'SETTLEMENT_ROOT', settlements)
    monkeypatch.setattr(m.a, 'prior_state', lambda root: (Decimal('.2'), set()))
    monkeypatch.setattr(m.settlement_archive, 'statistics_prior', lambda root: (Decimal('.41'), set()))
    def forbidden(*args, **kwargs):
        pytest.fail('External requests forbidden')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', forbidden)
    queries = [{'dataset':'GLBX.MDP3','schema':'ohlcv-1m','stype_in':'parent',
        'symbols':'ES.FUT,TN.FUT,6E.FUT,GC.FUT,ZC.FUT', 'start':f'2022-07-0{d}T15:00:00+00:00',
        'end':f'2022-07-0{d}T15:06:00+00:00'} for d in (1,5)]
    return old, tmp_path / 'execution', {'queries': queries}

class Response(io.BytesIO):
    code=200
    headers={}

def rawbar(query, offset=0, price=10):
    return (json.dumps({'hd':{'ts_event':str(m.a.stamp_ns(query['start'])+offset*60*10**9),
        'rtype':33,'publisher_id':1,'instrument_id':123}, 'open':str(price),'high':str(price),
        'low':str(price),'close':str(price),'volume':1})+'\n').encode()

class Fake(m.Client):
    def __init__(self, plan, cost='.1', fail=False, body=None):
        super().__init__('db-synthetic-no-network-key', plan['queries'])
        self.cost,self.fail,self.body=Decimal(cost),fail,body
    def quote(self, query):
        self.requests.append({'method':'metadata.get_cost','query':query,'result':'ok'})
        return self.cost
    def open(self, method, params):
        assert self.allowed(method,params)
        meta={'method':method,'query':params,'result':'attempting'}
        self.requests.append(meta)
        if self.fail:
            meta['result']='transport_error'
            raise m.a.ArchiveError('transport_error')
        return meta,Response(self.body if self.body is not None else rawbar(params))

def test_both_prior_ledgers_and_incremental_cap(setup):
    old,root,plan=setup
    for index,cost in enumerate(('.19','.19000000000000000000000000001')):
        client=Fake(plan,cost)
        _,report=m.run(client,plan,False,root/str(index),old)
        assert report['status']==('quoted_affordable' if index==0 else 'quote_over_budget')
        assert Decimal(report['aggregate_prior_estimate_usd'])==Decimal('.61')
        assert Decimal(report['estimate_ceiling_usd'])==Decimal('.99')
        assert not any(r['method']=='timeseries.get_range'for r in client.requests)

def test_failed_reservation_counts_and_complete_archive_skips(setup):
    old,root,plan=setup
    one={'queries':plan['queries'][:1]}
    _,first=m.run(Fake(one,fail=True),one,True,root,old)
    assert first['status']=='failed'
    folder,second=m.run(Fake(one),one,True,root,old)
    assert second['status']=='complete'
    assert m.execution_prior(root)[0]==Decimal('.2')
    client=Fake(one)
    _,third=m.run(client,one,True,root,old)
    assert third['status']=='complete' and client.requests==[]
    part=second['partitions'][0]
    assert gzip.decompress((folder/part['file']).read_bytes())==rawbar(one['queries'][0])

def test_window_bound_duplicates_and_signed_parent_spreads(setup,tmp_path):
    _,_,plan=setup;q=plan['queries'][0]
    body=rawbar(q,0,0)+rawbar(q,5,-1)
    saved=m.download(Fake(plan,body=body),q,tmp_path/'valid.gz')
    assert saved['records']==2
    for name,invalid in [('late',rawbar(q,6)),('duplicate',rawbar(q)*2)]:
        with pytest.raises(m.a.ArchiveError):
            m.download(Fake(plan,body=invalid),q,tmp_path/(name+'.gz'))
        assert not (tmp_path/(name+'.gz')).exists()

def test_exact_plan_calendar_mapping_and_no_holdout():
    design=m.load_design(m.STAGE/'rolls-v2.json')
    mapping=m.a.load_json((m.STAGE/'symbology/20260910T130820097627Z/mapping.json').read_bytes())
    plan=m.make_plan(design,mapping)
    assert len(plan['queries'])==377
    assert plan['queries'][0]['start']=='2022-07-01T15:00:00+00:00'
    assert plan['queries'][-1]['end']=='2023-12-29T16:06:00+00:00'
    assert all(q['end']<'2024-01-01' for q in plan['queries'])
    assert all('GCV' not in c['raw_symbol'] for r in plan['required_contracts'] for c in r['contracts'])
    client=m.Client('db-synthetic-no-network-key',plan['queries'])
    assert not client.allowed('account.list',plan['queries'][0])
    assert not client.allowed('timeseries.get_range',plan['queries'][0]|m.a.ENCODING|{'end':'2025-01-01'})
