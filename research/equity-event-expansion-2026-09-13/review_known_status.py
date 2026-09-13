"""Apply reviewed exchange/issuer cessation dates, never infer tradable prices."""
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import hashlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    policy_sha=hashlib.sha256((HERE/'experiment-policy.json').read_bytes()).hexdigest()
    manifest=json.loads((HERE/'price-manifest.json').read_text())
    roster=json.loads((HERE/'sec-cohort.json').read_text())
    owners={i['historical_symbol']:i['cik'] for i in roster['issuers']}
    exceptions=json.loads((HERE/'price-source-exceptions.json').read_text())
    evidence=json.loads((HERE/'corporate-action-evidence.json').read_text())
    records=[
        {'ticker':'MYL','start':'2020-11-17','available_at':'2020-11-17T09:30:00-05:00',
         'url':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-208',
         'facts':'Nasdaq identifies November16 as MYL last trading day and November17 as suspension and VTRS regular-way start. Stock consideration is one Viatris share per Mylan share; no continuous old-MYL prices are inferred.',
         'source_type':'EXCHANGE_CORPORATE_ACTION_NOTICE','status':'halted'},
        {'ticker':'TYPE','start':'2019-10-11','available_at':'2019-10-11T08:26:00-04:00',
         'url':'https://www.sec.gov/Archives/edgar/data/1385292/000119312519266384/d805632dex991.htm',
         'facts':'Original issuer completion release published October11 at08:26ET says trading ceased at October10 close. Common shares converted to19.85dollars cash; the provider October11 row cannot be an ordinary listed-stock close.',
         'source_type':'ISSUER_ORIGINAL_MERGER_COMPLETION_RELEASE','status':'halted'},
    ]
    for r in records:
        ticker=r['ticker'];rec=manifest['symbols'][ticker]
        raw=(ROOT/rec['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==rec['sha256']
        dates=[x['date'][:10] for x in csv.DictReader(raw.decode().splitlines())]
        conflict={'start_date':r['start'],'end_date':'2023-12-29',
            'verified_source_conflict':True,
            'reason':'Old listed-common price record after independently established suspension/cessation; no replacement security or cash value substituted.',
            'source_evidence':{'url':r['url'],'source_type':r['source_type'],'interpretation':r['facts'],
                'raw_source_sha256':rec['sha256'],'observed_row_count_in_interval':sum(d>=r['start'] for d in dates),
                'row_date_metadata_only':True,'reviewed_utc':datetime.now(timezone.utc).isoformat()}}
        assert ticker not in exceptions['symbols'], 'Already recorded; do not overwrite review'
        exceptions['symbols'][ticker]=[conflict]
        evidence['security_status_events'].append({'security_id':owners[ticker]+':single_common',
            'source_ticker':ticker,'status':r['status'],'verified':True,
            'effective_at':r['start']+'T09:30:00'+r['available_at'][-6:],
            'available_at':r['available_at'],'source_evidence':{
                **conflict['source_evidence'],
                'timestamp_scope':'Exchange effective status observability convention, except TYPE issuer timestamp explicitly supplied; not historical notice receipt or predictive text.'}})
    for name,obj in [('price-source-exceptions.json',exceptions),('corporate-action-evidence.json',evidence)]:
        assert obj['policy_sha256']==policy_sha
        (HERE/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'reviewed':[r['ticker'] for r in records],'prices_or_returns_examined':False}))

if __name__=='__main__':main()
