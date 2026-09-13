"""Record reviewed issuer/exchange actions before model fitting; no returns."""
import csv
import json
from datetime import datetime, timezone

from sec_collect import HERE, ROOT, POLICY_SHA, atomic, digest


def main():
    assert not (HERE/'frozen-models.json').exists()
    evidence=json.loads((HERE/'corporate-action-evidence.json').read_text())
    exceptions=json.loads((HERE/'price-source-exceptions.json').read_text())
    manifest=json.loads((HERE/'price-manifest.json').read_text())
    owners={i['historical_symbol']:i['cik'] for i in json.loads((HERE/'sec-cohort.json').read_text())['issuers']}
    assert evidence['policy_sha256']==exceptions['policy_sha256']==POLICY_SHA
    copart='https://www.sec.gov/Archives/edgar/data/900075/000119312523263869/d571958dars.pdf'
    overrides={
        'CPRT:2022-11-04:split': {'verified':True,'action_kind':'stock_split','expected_provider_amount':'2',
            'unresolved_reason':None,'source_evidence':{'url':copart,'page_zero_based':67,
                'corroboration':'https://www.sec.gov/Archives/edgar/data/900075/000090007523000013/xslF345X03/wf-form4_167770692335011.xml',
                'interpretation':'Annual report confirms completed November3 two-for-one common dividend; original Form4 confirms November4 split basis.'}},
        'CPRT:2023-08-22:split': {'verified':True,'action_kind':'stock_split','expected_provider_amount':'2',
            'unresolved_reason':None,'source_evidence':{'url':copart,'page_zero_based':67,
                'corroboration':'https://www.copart.com/content/us/en/press-releases/copart-announces-two-for-one-stock-split',
                'interpretation':'Original August4 announcement specifies distribution after August21 close; annual report confirms completed two-for-one common dividend.'}},
        'RELV:2021-01-07:split': {'verified':False,'action_kind':'REVERSE_FORWARD_SPLIT_WITH_SMALL_HOLDER_CASHOUT',
            'expected_provider_amount':'2000','unresolved_reason':'Vendor forward factor is not a 2000-fold unit entitlement for prior holders. Original source describes paired reverse/forward transaction and holder-dependent cash-out, completed December2020. OTC continuity and component accounting are unresolved.',
            'source_evidence':{'url':'https://www.sec.gov/Archives/edgar/data/768710/000143774921000828/relv20210115_sc13e3a.htm'}},
        'WMC:2022-07-11:split': {'verified':True,'action_kind':'reverse_stock_split','expected_provider_amount':'0.1',
            'unresolved_reason':None,'source_evidence':{'url':'https://www.sec.gov/Archives/edgar/data/1465885/000162828022018296/wmc-pressreleasefinalsplit.htm',
                'interpretation':'One-for-ten common split, first adjusted session July11. Fractional shares sold by transfer agent; amount/date not inferred. Frozen simulator leaves fractional entitlements unresolved.'}},
        'WYY:2020-11-09:split': {'verified':True,'action_kind':'reverse_stock_split','expected_provider_amount':'0.1',
            'unresolved_reason':None,'source_evidence':{'url':'https://www.sec.gov/Archives/edgar/data/1034760/000165495420011582/wyy_ex992.htm',
                'interpretation':'One-for-ten common split effective November6 after close, first adjusted session November9. Issuer describes round-up, subject to broker processes; frozen simulator does not invent a fractional-share allocation.'}},
    }
    for key,value in overrides.items():
        previous=evidence['reviewed_action_overrides'].get(key)
        assert previous is None or previous==value
        evidence['reviewed_action_overrides'][key]=value
    records=[
        ('MJCO','2020-09-22','halted','https://www.sec.gov/Archives/edgar/data/1626853/000121390020027486/ea127128-8k_majesco.htm',
         'Original closing8-K: merger September21, suspension before September22 open. Do not move suspension backward to September21. Cash entitlement16dollars; no payment-date assumption.'),
        ('CLDB','2021-11-02','halted','https://www.sec.gov/Archives/edgar/data/774569/000119312521315416/d250362d8k.htm',
         'Original closing8-K requests suspension as of November1 close; use next session, not invented November1 pre-open halt. Mixed elective/prorated stock/cash merger remains unresolved.'),
        ('DNKN','2020-12-15','halted','https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-239',
         'Nasdaq confirms December14 last trading and8pm halt, merger before December15 open;106.50dollars cash per common share. No actual cash-credit date inferred.'),
        ('RELV','2020-12-22','halted','https://www.sec.gov/Archives/edgar/data/768710/000143774920025842/relv20201223_8k.htm',
         'Original8-K confirms Nasdaq suspension before December22 open and OTC commencement December23. Paired reverse/forward cash-out and OTC history need independent continuity qualification; no wealth or liquidation assumed.'),
        ('TEUM','2020-11-12','otc','https://www.sec.gov/Archives/edgar/data/1084384/000110465920123617/tm2035239d2_8k.htm',
         'Original8-K specifies Nasdaq suspension at November12 open;2020 original annual filing confirms subsequent Pink Sheets quotations. Subsequent provider rows do not establish listed-session eligibility; OTC continuity remains unqualified for this pass.'),
        ('WMC','2023-12-06','halted','https://www.nasdaq.com/press-release/ag-mortgage-investment-trust-inc.-completes-acquisition-of-western-asset-mortgage',
         'Original issuer December6 08:51EST completion announcement confirms December5 last trading and pre-open December6 suspension;1.498MITT shares plus0.92cash. No unsupported successor valuation.'),
    ]
    for ticker,day,status,url,facts in records:
        if ticker in exceptions['symbols']:continue
        rec=manifest['symbols'][ticker];assert digest(ROOT/rec['path'])==rec['sha256']
        dates=[r['date'][:10] for r in csv.DictReader((ROOT/rec['path']).read_text().splitlines())]
        proof={'url':url,'interpretation':facts,'raw_source_sha256':rec['sha256'],
               'observed_row_count_in_interval':sum(d>=day for d in dates),'row_date_metadata_only':True,
               'reviewed_utc':datetime.now(timezone.utc).isoformat()}
        exceptions['symbols'][ticker]=[{'start_date':day,'end_date':'2023-12-29','verified_source_conflict':True,
            'reason':'Original listed-common history has ceased. Subsequent vendor records require a separately qualified claim, successor or OTC continuity; no executable listed fill or liquidation value inferred.',
            'source_evidence':proof}]
        # Date offset follows the actual Eastern session; source knowledge is an
        # explicit effective-status convention, not a historical receipt clock.
        from zoneinfo import ZoneInfo
        stamp=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
        evidence['security_status_events'].append({'security_id':owners[ticker]+':single_common',
            'source_ticker':ticker,'status':status,'verified':True,'effective_at':stamp,'available_at':stamp,
            'source_evidence':{**proof,'timestamp_scope':'Effective market-status observability convention; not a predictive feature or proof of historical notice receipt.'}})
    atomic(HERE/'corporate-action-evidence.json',evidence)
    atomic(HERE/'price-source-exceptions.json',exceptions)
    print('Recorded second-batch action and market-status evidence; no returns calculated.')


if __name__=='__main__':main()
