#!/usr/bin/env python3
"""Offline sample repairs and action-aware reference prices, not strategy P&L."""
from copy import deepcopy
from decimal import Decimal as D
import hashlib
import json
import math
from pathlib import Path
import sys
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=HERE.parent/'ml-free-data-feasibility-2026-09-13'
RAW=ROOT/'data/snapshots'/HERE.name
sys.path.insert(0,str(OLD))
from analyze import instant, available, CAL
from probe import write, sha

FILINGS=json.loads((HERE/'selected-filings.json').read_text())
META=[
 ('2019-12-31','0001326801-19-000069','2019-10-25',2406468226,445278305),
 ('2021-12-31','0001326801-21-000065','2021-10-20',2366277848,415481668),
 ('2023-06-30','0001326801-23-000067','2023-04-21',2212153203,350578831),
 ('2023-11-30','0001326801-23-000103','2023-10-20',2219607026,350255706),
]
SOURCES={
 'AAPL':'https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/',
 'AMZN':'https://www.miaxglobal.com/sites/default/files/alert-files/AMZN_split__50496.pdf',
 'GE':'https://www.ge.com/news/press-releases/ge-completes-one-for-eight-reverse-stock-split',
 'WAB':'https://www.ge.com/investor-relations/shareholder-services',
 'GEHC':'https://investor.gehealthcare.com/static-files/94bb183f-27f5-425a-adce-bb71fc9c0216',
 'ATVI':'https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b',
 'BBBY':'https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010d8k.htm',
 'BBBY_time':'https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/0001193125-23-247428-index.htm',
 'BBBY_suspend':'https://www.sec.gov/Archives/edgar/data/886158/000119312523115523/d89202dex991.htm',
 'JNJ':'https://www.jnj.com/media-center/press-releases/johnson-johnson-announces-final-results-of-exchange-offer-and-finalizes-separation-of-kenvue-inc',
}
SPLITS={('AAPL','2020-08-31'):4,('AMZN','2022-06-06'):20,('GE','2021-08-02'):.125}
SPINS={('GE','2019-02-26'):('WAB',.005371),('GE','2023-01-04'):('GEHC',1/3)}


def read_verified(manifest, name, field='sha256'):
    m=manifest[name]; b=(ROOT/m['file']).read_bytes(); assert sha(b)==m[field]
    return json.loads(b)


def accounting():
    original=json.loads((OLD/'fundamental-coverage.json').read_text())
    out=deepcopy(original); repairs=[]
    sm=json.loads((OLD/'sec-manifest.json').read_text())
    jnj=read_verified(sm,'JNJ','filtered_sha256')
    for cut,acc,end,a,b in META:
        f=FILINGS[acc]; r=next(x for x in out if x['label']=='META' and x['cut']==cut)
        assert r['reported_common_shares'] is None and r['assets']['accn']==acc
        assert end <= f['filingDate'] and available(f['filingDate']) <= cut
        repair=dict(label='META',cut=cut,field='reported_common_shares',val=a+b,
                    class_a=a,class_b=b,end=end,accn=acc,filed=f['filingDate'],
                    available=available(f['filingDate']),unit='shares',source=f['url'],
                    method='reviewed_original_filing_cover_sum_A_and_B',
                    evidence='Numerical cover facts transcribed from web-readable SEC filings; no raw HTML retained because SEC curl downloads returned 403.',
                    economic_value_note='A-price times total A+B shares is an explicit economic-equity proxy, not an observed B market quotation or a current fully diluted market cap.')
        r['reported_common_shares']=repair
        r['flags'].remove('NO_ENTITY_WIDE_COMMON_SHARE_COUNT_IN_COMPANYFACTS')
        repairs.append(repair)
    expected={'2019-12-31':58210000000,'2021-12-31':70272000000,'2023-06-30':70869000000}
    for r in out:
        if r['label']!='JNJ' or r['cut'] not in expected: continue
        cut,end=r['cut'],r['report_end'];acc=r['assets']['accn']
        tags=['CommonStockValue','RetainedEarningsAccumulatedDeficit','AccumulatedOtherComprehensiveIncomeLossNetOfTax',
              'TreasuryStockCommonValue' if cut=='2023-06-30' else 'TreasuryStockValue']
        parts=[instant(jnj,t,cut,end) for t in tags]
        assert all(p and p['accn']==acc for p in parts)
        v=parts[0]['val']+parts[1]['val']+parts[2]['val']-parts[3]['val']
        total=instant(jnj,'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',cut,end)
        assert v==expected[cut]==total['val'] and r['parent_equity'] is None
        repair=dict(label='JNJ',cut=cut,field='parent_equity',val=v,end=end,accn=acc,
                    method='issuer_specific_common_capital_plus_retained_and_AOCI_minus_treasury',
                    components=parts,reconciles_to_reported_total=total,source=FILINGS[acc]['url'],
                    evidence='Retained Company Facts components; 2021 and 2023 displayed balance sheets independently reviewed via web. 2019 original web page exceeded size limit; component reconciliation used.',
                    warning='This issuer-specific equation is not a generic assumption that untagged minority interest equals zero.')
        r['parent_equity']=repair;r['equity_method']=repair['method'];repairs.append(repair)
    for r in out:
        r['required_raw_accounting_fields_available']=bool(r['assets'] and r['parent_equity'] and (r['net_income_ttm'] or r['common_income_ttm']) and r['operating_cashflow_ttm'])
    write(HERE/'accounting-repairs.json',repairs)
    write(HERE/'fundamental-coverage-repaired.json',out)
    joins=json.loads((OLD/'sample-joins.json').read_text())
    for j in joins:
        f=next(r for r in out if r['label']==j['label'] and r['cut']==j['cut'])
        j['raw_accounting_available']=f['required_raw_accounting_fields_available']
        j['reported_shares_available']=bool(f['reported_common_shares'])
    write(HERE/'sample-joins-repaired.json',joins)
    return dict(repairs=len(repairs),raw_accounting_complete=sum(r['required_raw_accounting_fields_available'] for r in out),
                reported_share_count_available=sum(bool(r['reported_common_shares']) for r in out),
                total_checks=len(out),nasdaq_active_accounting_price_shares_joins=sum(j['valid_raw_price'] and j['raw_accounting_available'] and j['reported_shares_available'] for j in joins),
                exact_original_six_features_qualified=False)


def prices():
    manifest=json.loads((HERE/'tiingo-manifest.json').read_text())
    data={k.removeprefix('tiingo-'):read_verified(manifest,k) for k in manifest if manifest[k].get('file')}
    assert data.pop('BBBY')==[]
    data['BBBY']=data.pop('BBBYQ')
    by={s:{r['date'][:10]:r for r in rs} for s,rs in data.items()}
    assert all(len(by[s])==len(rs) for s,rs in data.items())
    errors=[];coverage=[];events=[];normalized=[];checks=0;routine_dividends=0
    observed_splits=set();observed_spins=set()
    for symbol,rs in data.items():
        rs=sorted(rs,key=lambda r:r['date'])
        start={'GEHC':'2023-01-04','WAB':'2019-02-25'}.get(symbol,'2018-05-01')
        end={'ATVI':'2023-10-12','BBBY':'2023-09-29'}.get(symbol,'2023-12-29')
        kept=[r for r in rs if r['date'][:10] <= end]
        excluded=[r['date'][:10] for r in rs if r['date'][:10] > end]
        assert excluded==(['2023-10-13'] if symbol=='ATVI' else [])
        actual={r['date'][:10] for r in kept}
        expected={s.date().isoformat() for s in CAL.sessions_in_range(start,end)}
        coverage.append(dict(symbol=symbol,provider_symbol='BBBYQ' if symbol=='BBBY' else symbol,
                             first=kept[0]['date'][:10],last=kept[-1]['date'][:10],rows=len(kept),
                             missing=sorted(expected-actual),unexpected=sorted(actual-expected),excluded_stale_rows=excluded))
        level=100.;previous=None
        for r in kept:
            day=r['date'][:10]
            assert start<=day<'2024-01-01'
            assert all(math.isfinite(r[k]) and r[k]>0 for k in ('open','high','low','close','adjClose'))
            assert r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high']
            assert r['volume']>=0 and r['splitFactor']>0 and r['divCash']>=0
            key=(symbol,day);factor=SPLITS.get(key,1);div=r['divCash'];child_value=0.;distribution=None
            if previous:
                actual_adj=(r['adjClose']/r['close'])/(previous['adjClose']/previous['close'])
                expected_adj=r['splitFactor']*(r['close']+r['divCash'])/r['close']
                checks+=1
                if abs(actual_adj/expected_adj-1)>1e-5:
                    errors.append(dict(symbol=symbol,date=day,type='VENDOR_ADJUSTMENT_INCONSISTENT',relative_error=actual_adj/expected_adj-1))
            if key in SPINS:
                child,ratio=SPINS[key];observed_spins.add(key)
                child_close=by[child][day]['close'];child_value=ratio*child_close
                distribution=dict(security=child,units_per_parent=ratio,reference_close=child_close,reference_value=child_value)
                events.append(dict(symbol=symbol,date=day,kind='stock_distribution',distribution=distribution,
                                   parent_units_factor=1,vendor_split_factor=r['splitFactor'],vendor_divCash=r['divCash'],
                                   cash_dividend_override=0,source=SOURCES[child],cash_payment_date=None,
                                   date_semantics='First ex-distribution price session. GE/WAB transaction completed Feb 25; GEHC distributed Jan 3. Do not infer earlier public announcement time.'))
                div=0
            elif key in SPLITS:
                observed_splits.add(key);assert r['splitFactor']==factor
                events.append(dict(symbol=symbol,date=day,kind='stock_split',units_factor=factor,source=SOURCES[symbol],
                                   fractional_units='Cash-in-lieu claim; no assumed cash availability before supported payment.'))
            else:
                assert r['splitFactor']==1, (symbol,day,'UNCLASSIFIED_FACTOR')
            if div:
                routine_dividends+=1
                events.append(dict(symbol=symbol,date=day,kind='routine_dividend_receivable',usd_per_post_split_share=div,
                                   payment_date=None,spendable_cash_on_ex_date=0,source='tiingo-manifest.json',
                                   independently_issuer_confirmed=False))
            if previous:
                gross=(factor*(r['close']+div)+child_value)/previous['close'];level*=gross
            else:gross=None
            normalized.append(dict(symbol=symbol,date=day,raw_close=r['close'],actual_units_factor=factor,
                                   cash_dividend_entitlement_per_post_split_share=div,stock_distribution=distribution,
                                   reference_gross=gross,reference_total_return_index=level,
                                   convention='Frictionless fractional distribution reinvestment at same-session close for return features only; not an executable account.',
                                   spendable_distribution_cash=0,market='OTC' if symbol=='BBBY' and day>='2023-05-03' else 'listed'))
            previous=r
    assert observed_splits==set(SPLITS) and observed_spins==set(SPINS)
    terminals=[dict(symbol='ATVI',date='2023-10-13',kind='cash_merger',cash_claim_per_share=95,
                    last_trade_date='2023-10-12',last_trade_price=by['ATVI']['2023-10-12']['close'],
                    source=SOURCES['ATVI'],payment_date=None,spendable_cash_on_event=0),
               dict(symbol='BBBY',date='2023-09-29',kind='equity_cancellation',terminal_value_per_share=0,
                    last_trade_price=by['BBBY']['2023-09-29']['close'],known_by_et='2023-09-29T16:23:06-04:00',
                    source=SOURCES['BBBY'],timestamp_source=SOURCES['BBBY_time'],
                    execution='After-close corporate outcome, never a sale at the final quoted price.')]
    events.extend(terminals)
    events.extend([dict(symbol='BBBY',date='2023-05-03',kind='nasdaq_suspension_otc_continuation',
                        provider_symbol='BBBYQ',new_listed_universe_purchases=False,source=SOURCES['BBBY_suspend']),
                   dict(symbol='JNJ',date='2023-08-23',kind='voluntary_exchange_default_no_election',
                        default_automatic_KVUE_units=0,source=SOURCES['JNJ'])])
    price_rows=len(normalized)
    # Preserve the quote while ensuring a daily economic-return consumer sees
    # the cancellation. The outcome became public after the last quoted close.
    last_bbby=next(r for r in normalized if r['symbol']=='BBBY' and r['date']=='2023-09-29')
    last_bbby['quoted_reference_gross']=last_bbby['reference_gross']
    last_bbby.update(reference_gross=0,reference_total_return_index=0,
                     terminal_value_per_share=0,reference_observation='after_close_cancellation',
                     known_by_et=terminals[1]['known_by_et'])
    last_atvi=next(r for r in normalized if r['symbol']=='ATVI' and r['date']=='2023-10-12')
    normalized.append(dict(symbol='ATVI',date='2023-10-13',raw_close=None,
                           reference_gross=95/last_atvi['raw_close'],
                           reference_total_return_index=last_atvi['reference_total_return_index']*95/last_atvi['raw_close'],
                           terminal_cash_claim_per_share=95,spendable_distribution_cash=0,
                           reference_observation='cash_merger_claim_not_a_trade',source=SOURCES['ATVI']))
    normalized.sort(key=lambda r:(r['symbol'],r['date']))
    output=RAW/'reference-prices.jsonl'
    output.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in normalized))
    write(HERE/'corporate-actions.json',sorted(events,key=lambda x:(x['date'],x['symbol'],x['kind'])))
    write(HERE/'price-coverage.json',coverage)
    write(HERE/'terminal-outcomes.json',terminals)
    return dict(symbol_series=len(data),retained_price_rows=price_rows,economic_reference_rows=len(normalized),ordinary_dividend_records=routine_dividends,
                documented_splits=len(SPLITS),documented_stock_distributions=len(SPINS),
                provider_adjustment_checks=checks,provider_adjustment_errors=errors,
                missing_expected_sessions=sum(len(x['missing']) for x in coverage),
                unexpected_sessions=sum(len(x['unexpected']) for x in coverage),
                stale_ATVI_rows_excluded=1,reference_file=str(output.relative_to(ROOT)),reference_sha256=sha(output.read_bytes()),
                features_reference_only=True,executable_account_qualified=False)


def main():
    result=dict(accounting=accounting(),prices=prices(),strategy_fitted=False,strategy_profitability_tested=False,
                new_subscription=False,new_paid_data_usd=0,reserved_2024_2025_prices_opened=False)
    write(HERE/'summary.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
