"""Apply original issuer/exchange action evidence, without reading returns."""
import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from sec_collect import HERE, ROOT, POLICY_SHA, atomic, digest

def main():
    p=HERE/'corporate-action-evidence.json'
    evidence=json.loads(p.read_text())
    exceptions=json.loads((HERE/'price-source-exceptions.json').read_text())
    manifest=json.loads((HERE/'price-manifest.json').read_text())
    owners={i['historical_symbol']:i['cik'] for i in json.loads((HERE/'sec-cohort.json').read_text())['issuers']}
    assert evidence['policy_sha256']==exceptions['policy_sha256']==POLICY_SHA
    overrides={
        'FTNT:2022-06-23:split': {'verified':True,'action_kind':'stock_split','expected_provider_amount':'5',
            'unresolved_reason':None,'source_evidence':{
                'url':'https://investor.fortinet.com/news-releases/news-release-details/fortinet-announces-five-one-stock-split/',
                'completion_corroboration':'https://investor.fortinet.com/news-releases/news-release-details/fortinet-reports-second-quarter-2022-financial-results/',
                'new_common_shares_per_old_share':'5','effective_date':'2022-06-22','first_split_adjusted_session':'2022-06-23',
                'scope':'Original June9 announcement plus issuer Q2 report confirming effective June22 split; no fractional cash assumption.'}},
        'BWA:2023-07-05:split': {'verified':False,'action_kind':'SPIN_OFF_OTHER_SECURITY','expected_provider_amount':'1.136',
            'unresolved_reason':'PHINIA distribution is a different security, not 1.136 BorgWarner common shares. No successor valuation or fractional cash inferred.',
            'source_evidence':{'url':'https://www.borgwarner.com/newsroom/press-releases/2023/07/03/borgwarner-announces-completion-of-phinia-spin-off',
                'trading_date_corroboration':'https://investors.phinia.com/news/news-details/2023/PHINIA-Inc--Completes-Separation-from-BorgWarner-Starts-Trading-on-New-York-Stock-Exchange/default.aspx',
                'distribution_date':'2023-07-03','successor_first_regular_session':'2023-07-05'}},
        'SNX:2020-12-01:split': {'verified':False,'action_kind':'SPIN_OFF_OTHER_SECURITY','expected_provider_amount':'2',
            'unresolved_reason':'One Concentrix share is distributed per Synnex share; this is not a doubling of Synnex common shares. No unsupported successor mark inferred.',
            'source_evidence':{'url':'https://www.sec.gov/Archives/edgar/data/1177394/000156459020055926/snx-ex991_1064.htm',
                'distribution_date':'2020-12-01','new_other_security_shares_per_old_share':'1'}},
        'DCAR:2020-05-29:split': {'verified':False,'action_kind':'REVERSE_RECAPITALIZATION_AND_STOCK_DIVIDEND','expected_provider_amount':'0.2',
            'unresolved_reason':'Original source specifies a 1:10 reverse split followed by a 1:1 stock dividend, name/CUSIP change and reverse recapitalization. Net factor is 0.2, but component/fraction accounting is unsupported; do not silently treat the merger as one routine action.',
            'source_evidence':{'url':'https://www.sec.gov/Archives/edgar/data/1086745/000149315220010091/form8-k.htm',
                'first_successor_ticker_session':'2020-05-29','successor_ticker':'AYRO'}},
        'DCAR:2023-09-18:split': {'verified':False,'action_kind':'SUCCESSOR_TICKER_SOURCE_REQUIRES_IDENTITY_JOIN','expected_provider_amount':'0.125',
            'unresolved_reason':'Issuer AYRO confirms1:8 split, but action is carried in provider legacy DCAR history. No source-ticker aliasing without a qualified contemporaneous AYRO join.',
            'source_evidence':{'url':'https://www.sec.gov/Archives/edgar/data/1086745/000149315223032766/ex99-1.htm',
                'actual_ticker':'AYRO','first_split_adjusted_session':'2023-09-18','new_common_shares_per_old_share':'0.125'}},
    }
    for key,record in overrides.items():
        previous=evidence['reviewed_action_overrides'].get(key)
        assert previous is None or previous==record
        evidence['reviewed_action_overrides'][key]=record
    for ticker,day,url,facts in [
        ('DSSI','2021-07-16','https://infomemo.theocc.com/infomemos?number=48993',
         'OCC assigns July16 effective adjusted stock deliverable; original issuer July16 completion release corroborates merger. Old DSSI common converts to INSW common plus fractional cash, not a cash-only liquidation.'),
        ('VSLR','2020-10-09','https://www.sec.gov/Archives/edgar/data/1469367/000119312520265967/d21282d8k.htm',
         'Original Sunrun closing8-K confirms October8 completed conversion of old VSLR common into0.55 RUN shares plus fractional cash. Next-session old VSLR rows cannot represent unchanged listed common. No exact intraday October8 halt is inferred.'),
        ('AGFS','2023-03-31','https://infomemo.theocc.com/infomemos?number=52205',
         'OCC confirms merger consummated before March31 open; each common share converts to3dollars cash. Issuer completion notice separately confirms March31 suspension.'),
        ('WIFI','2021-06-02','https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2021-89',
         'Nasdaq confirms June1 last trading, halt8pm June1, merger before June2 open, suspensionJune3;14dollars cash per common share.'),
    ]:
        if ticker in exceptions['symbols']: continue
        rec=manifest['symbols'][ticker];assert digest(ROOT/rec['path'])==rec['sha256']
        dates=[r['date'][:10] for r in csv.DictReader((ROOT/rec['path']).read_text().splitlines())]
        proof={'url':url,'interpretation':facts,'raw_source_sha256':rec['sha256'],
               'observed_row_count_in_interval':sum(d>=day for d in dates),'row_date_metadata_only':True,
               'reviewed_utc':datetime.now(timezone.utc).isoformat()}
        exceptions['symbols'][ticker]=[{'start_date':day,'end_date':'2023-12-29','verified_source_conflict':True,
            'reason':'Old listed-common price records after independently established market cessation are unqualified; no liquidation fill or replacement value imputed.',
            'source_evidence':proof}]
        evidence['security_status_events'].append({'security_id':owners[ticker]+':single_common','source_ticker':ticker,
            'status':'halted','verified':True,'effective_at':day+'T09:30:00-04:00','available_at':day+'T09:30:00-04:00',
            'source_evidence':{**proof,'timestamp_scope':'Effective market-status observability convention, not historical notice receipt or predictive feature.'}})
    atomic(p,evidence);atomic(HERE/'price-source-exceptions.json',exceptions)
    print('Reviewed FTNT, BWA, SNX, AGFS and WIFI action evidence; no returns calculated.')

if __name__=='__main__': main()
