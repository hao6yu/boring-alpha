#!/usr/bin/env python3
"""Evidence and financial timing checks for the completed feasibility sample."""
from copy import deepcopy
import json
from pathlib import Path
from analyze import available, instant, ttm
from probe import HERE, ROOT, RAW, sha, write


def verify():
    checked = 0
    for name in ['sec-manifest.json','databento-manifest.json']:
        manifest = json.loads((HERE/name).read_text())
        for rec in manifest.values():
            if rec.get('file'):
                b=(ROOT/rec['file']).read_bytes()
                assert sha(b)==rec.get('filtered_sha256',rec['response_sha256'])
                checked += 1
    f = json.loads((HERE/'fundamental-coverage.json').read_text())
    component_count = 0
    def inspect(obj,cut):
        nonlocal component_count
        if isinstance(obj,dict):
            if 'filed' in obj:
                assert obj['filed'] < '2024-01-01'
                assert obj['end'] <= cut
                assert available(obj['filed']) <= cut
                component_count += 1
            for val in obj.values(): inspect(val,cut)
        elif isinstance(obj,list):
            for val in obj: inspect(val,cut)
    for row in f: inspect(row,row['cut'])
    assert available('2023-07-03')=='2023-07-06', 'Independence Day must not count as a trading session'
    assert available('2023-06-30')=='2023-07-05', 'Weekend and Independence Day lag'
    data=json.loads((RAW/'AAPL-companyfacts-pre2024.json').read_text())
    cut='2023-06-30'; target='2023-04-01'
    old_assets=instant(data,'Assets',cut)
    old_net=ttm(data,'NetIncomeLoss',cut,target)
    assert old_net['value']==(99_803+54_158-59_640)*1_000_000
    changed=deepcopy(data)
    # Synthetic later restatements must not alter historical inputs.
    changed['facts']['us-gaap']['Assets']['units']['USD'].append(old_assets | dict(filed='2024-02-01', val=10**25))
    latest=old_net['components'][1]
    changed['facts']['us-gaap']['NetIncomeLoss']['units']['USD'].append(latest | dict(filed='2024-02-01',val=10**25))
    assert instant(changed,'Assets',cut)==old_assets
    assert ttm(changed,'NetIncomeLoss',cut,target)==old_net
    # Contradictory facts in one filing must remain unresolved, not selected by order.
    conflict=deepcopy(data)
    conflict['facts']['us-gaap']['Assets']['units']['USD'].append(old_assets | dict(val=old_assets['val']+1))
    assert instant(conflict,'Assets',cut) is None
    p=json.loads((HERE/'price-summary.json').read_text())
    c=json.loads((HERE/'price-coverage.json').read_text())
    j=json.loads((HERE/'sample-joins.json').read_text())
    assert not p['source_errors'] and not p['missing_active_price_sessions']
    assert all(not r['unexpected_dates'] for r in c)
    assert p['raw_rows']==p['retained_rows']+p['unrelated_ticker_rows_excluded']
    assert p['unrelated_ticker_rows_excluded']==148
    meta_2021=next(x for x in j if x['label']=='META' and x['cut']=='2021-12-31')
    assert meta_2021['symbol']=='FB', 'The earlier META fund must not join to Facebook fundamentals'
    assert all(not x['valid_raw_price'] for x in j if x['listing_status']=='REMOVED_FROM_NASDAQ_FEED')
    initial=json.loads((HERE/'first-download-206-client-rejection.json').read_text())
    recovery=json.loads((HERE/'databento-manifest.json').read_text())['sample-daily-bars']
    assert initial['http_status']==206 and recovery['http_status']==206
    # The first body was discarded by the client. Its hash is preserved, but
    # content equivalence cannot be established (response ordering may vary).
    quote=json.loads((HERE/'pre-download-quote.json').read_text())['quote_usd']
    result=dict(status='PASS_FOR_REPORTED_FEASIBILITY_SCOPE',archived_payload_hashes_checked=checked,
                historical_fact_components_checked=component_count,
                checks=['NYSE holiday filing lag','synthetic future-restatement exclusion','contradictory fact rejection',
                        'Apple TTM arithmetic','daily OHLCV and dated symbol map','expected listing-session coverage',
                        'unrelated META fund exclusion','no forward fill after listing removal','both streamed requests counted in cost'],
                successful_data_responses=2,download_credit_cost_estimate_usd=quote+initial['quote_usd'],
                no_profitability_result=True,full_feature_panel_qualified=False)
    write(HERE/'verification.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__': verify()
