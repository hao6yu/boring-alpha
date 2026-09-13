"""Finish the preidentified remaining-symbol action review after data arrives."""
import csv
import json
from datetime import datetime, timezone
from sec_collect import HERE, ROOT, POLICY_SHA, atomic, digest


def main():
    assert not (HERE/'frozen-models.json').exists()
    m=json.loads((HERE/'price-manifest.json').read_text())
    if m.get('pending_symbols'):raise ValueError('Wait for the bounded remaining-symbol pass')
    evidence=json.loads((HERE/'corporate-action-evidence.json').read_text())
    exceptions=json.loads((HERE/'price-source-exceptions.json').read_text())
    qa=json.loads((HERE/'action-source-qualification.json').read_text())
    remaining=['PEGI','EPRT','LE','DNTH','ASXC','AYRO','META','ZVRA','TFIN']
    overrides=evidence['reviewed_action_overrides']
    reviewed=[];unknown=[]
    for ticker in remaining:
        record=qa['symbols'].get(ticker,{})
        for day,action in record.get('actions',{}).items():
            if action['splitFactor']==1:continue
            key=f'{ticker}:{day}:split'
            if key in overrides:continue
            if ticker=='AYRO' and day=='2023-09-18' and action['splitFactor']==.125:
                overrides[key]={'verified':True,'action_kind':'reverse_stock_split','expected_provider_amount':'0.125',
                    'unresolved_reason':None,'source_evidence':{
                        'url':'https://www.sec.gov/Archives/edgar/data/1086745/000149315223032766/ex99-1.htm',
                        'interpretation':'Original announcement:1-for8, September18 adjusted trading. Current filing independently maps AYRO. Frozen simulator leaves nonintegral allocation unresolved despite issuer round-up description; no cash or extra unit invented.'}}
            elif ticker=='DNTH' and day in ('2023-09-11','2023-09-12') and action['splitFactor']==.0625:
                overrides[key]={'verified':False,'action_kind':'REVERSE_MERGER_WITH_CVR_AND_FRACTIONAL_CASH',
                    'expected_provider_amount':'0.0625','unresolved_reason':'One-for16 is confirmed but simultaneous reverse merger, CVR and fractional cash accounting are unsupported. Provider factor alone does not value the complete old-holder entitlement.',
                    'source_evidence':{'url':'https://investor.dianthustx.com/news-releases/news-release-details/magenta-therapeutics-announces-completion-merger-dianthus',
                        'cvr_source':'https://investor.dianthustx.com/ir-resources/faqs',
                        'interpretation':'September11 11:13Eastern legal reverse split,11:15merger; September12 first DNTH regular trading.'}}
            else:
                unknown.append({'ticker':ticker,'date':day,'split_factor':action['splitFactor'],
                    'reason':'Not covered by the source reviews completed before price arrival; remains unverified.'})
            if key in overrides:reviewed.append(key)
    # Only dates are inspected. Cessation is proved by the original exchange
    # bulletin; a vendor terminal row is not an executable liquidation.
    ticker='PEGI';rec=m['symbols'].get(ticker,{})
    if 'path' in rec and ticker not in exceptions['symbols']:
        assert digest(ROOT/rec['path'])==rec['sha256']
        dates=[r['date'][:10] for r in csv.DictReader((ROOT/rec['path']).read_text().splitlines())]
        proof={'url':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-47',
            'interpretation':'Nasdaq confirms March13 last trading,8pm halt; merger before March16 open;26.75dollars cash. No actual cash-credit date inferred.',
            'raw_source_sha256':rec['sha256'],'observed_row_count_in_interval':sum(d>='2020-03-16' for d in dates),
            'row_date_metadata_only':True}
        exceptions['symbols'][ticker]=[{'start_date':'2020-03-16','end_date':'2023-12-29',
            'verified_source_conflict':True,'reason':'Old PEGI common ceased before March16open; vendor terminal rows cannot support listed fills or marks. Cash claim requires separate entitlement ledger, no liquidation assumed.',
            'source_evidence':proof}]
        evidence['security_status_events'].append({'security_id':'0001561660:single_common','source_ticker':ticker,
            'status':'halted','verified':True,'effective_at':'2020-03-16T09:30:00-04:00','available_at':'2020-03-16T09:30:00-04:00',
            'source_evidence':{**proof,'timestamp_scope':'Effective market-status observability convention, not notice receipt.'}})
    atomic(HERE/'corporate-action-evidence.json',evidence)
    atomic(HERE/'price-source-exceptions.json',exceptions)
    atomic(HERE/'remaining-price-review.json',{'policy_sha256':POLICY_SHA,'created_utc':datetime.now(timezone.utc).isoformat(),
        'price_manifest_sha256':digest(HERE/'price-manifest.json'),'reviewed_action_keys':reviewed,
        'new_unverified_action_fields':unknown,'scope':'Action metadata and original status sources only; no returns.'})
    print(json.dumps({'new_reviewed_actions':reviewed,'unverified_new_actions':unknown}))


if __name__=='__main__':main()
