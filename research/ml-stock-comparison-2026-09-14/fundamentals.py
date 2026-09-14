#!/usr/bin/env python3
"""As-of monthly source features; missing concepts remain explicit."""
from datetime import date
from functools import lru_cache
import json,sys
from pathlib import Path
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];RAW=ROOT/'data/snapshots'/HERE.name
OLD=HERE.parent/'ml-free-data-feasibility-2026-09-13'
sys.path.insert(0,str(OLD));import analyze as a
from probe import sha,write
a.available=lru_cache(None)(a.available)

def months():
    for m in pd.period_range('2019-06','2023-12',freq='M'):
        cut=a.CAL.date_to_session((m-1).end_time.normalize(),direction='previous').date().isoformat()
        yield str(m),cut

def prior_assets(data,cut,end):
    rs=[r for r in a.rows(data,'Assets',cut) if 'start' not in r and 350<=(date.fromisoformat(end)-date.fromisoformat(r['end'])).days<=378]
    if not rs:return None
    distance=min(abs((date.fromisoformat(end)-date.fromisoformat(r['end'])).days-365) for r in rs)
    rs=[r for r in rs if abs((date.fromisoformat(end)-date.fromisoformat(r['end'])).days-365)==distance]
    return a.choose(rs)

def equity(data,cut,end,symbol):
    eq=a.instant(data,'StockholdersEquity',cut,end)
    if not eq:
        total=a.instant(data,'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',cut,end)
        nci=a.instant(data,'MinorityInterest',cut,end)
        if total and nci:eq=dict(val=total['val']-nci['val'],end=end,method='total_minus_NCI',components=[total,nci])
    if not eq and symbol=='JNJ':
        common=a.instant(data,'CommonStockValue',cut,end);ret=a.instant(data,'RetainedEarningsAccumulatedDeficit',cut,end);oci=a.instant(data,'AccumulatedOtherComprehensiveIncomeLossNetOfTax',cut,end)
        treasury=a.instant(data,'TreasuryStockValue',cut,end) or a.instant(data,'TreasuryStockCommonValue',cut,end)
        parts=[common,ret,oci,treasury]
        if all(parts) and len({p['accn'] for p in parts})==1:
            value=common['val']+ret['val']+oci['val']-treasury['val']
            total=a.instant(data,'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',cut,end)
            if total and value==total['val']:eq=dict(val=value,end=end,method='JNJ_reconciled_common_equity',components=parts)
    return eq

def preferred(data,cut,end):
    # Par value alone can round to zero despite billions in preferred capital.
    # Never treat an absent preferred tag, or a zero par value, as proof of no
    # outstanding preferred stock.
    capital=a.instant(data,'PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount',cut,end)
    outstanding=a.instant(data,'PreferredStockSharesOutstanding',cut,end,unit='shares')
    issued=a.instant(data,'PreferredStockSharesIssued',cut,end,unit='shares')
    if capital and capital['val']>0:return dict(val=capital['val'],method='reported_preferred_capital',components=[capital])
    if outstanding and outstanding['val']==0:return dict(val=0,method='reported_zero_preferred_outstanding',components=[outstanding])
    if issued and issued['val']==0:return dict(val=0,method='reported_zero_preferred_issued',components=[issued])
    return None

def build_one(symbol,cik,data,month,cut):
    assets=a.instant(data,'Assets',cut);end=assets['end'] if assets else None
    rec=dict(symbol=symbol,cik=cik,month=month,cut=cut,assets=assets,report_end=end,
             shares=None,parent_equity=None,preferred_capital=None,common_equity=None,
             common_income_ttm=None,net_income_ttm=None,operating_cashflow_ttm=None,
             average_assets=None,roa=None,cfo_assets=None,filing_eligible=False,missing_reasons=[])
    if not assets:rec['missing_reasons'].append('NO_AVAILABLE_ASSETS_USD');return rec
    rec['filing_eligible']=(date.fromisoformat(cut)-date.fromisoformat(end)).days<=550 and (date.fromisoformat(cut)-date.fromisoformat(assets['filed'])).days<=365
    if not rec['filing_eligible']:rec['missing_reasons'].append('STALE_FILING_OR_REPORT')
    shares=a.instant(data,'EntityCommonStockSharesOutstanding',cut,unit='shares',namespace='dei') or a.instant(data,'CommonStockSharesOutstanding',cut,unit='shares')
    if shares and shares['val']>0 and (date.fromisoformat(cut)-date.fromisoformat(shares['end'])).days<=180:rec['shares']=shares
    else:rec['missing_reasons'].append('MISSING_OR_OLDER_THAN_180_DAY_SHARE_COUNT')
    eq=equity(data,cut,end,symbol);pref=preferred(data,cut,end)
    rec['parent_equity']=eq;rec['preferred_capital']=pref
    if eq and pref:rec['common_equity']=eq['val']-pref['val']
    else:rec['missing_reasons'].append('COMMON_BOOK_CAPITAL_NOT_IDENTIFIED')
    income=a.ttm(data,'NetIncomeLoss',cut,end)
    common=a.ttm(data,'NetIncomeLossAvailableToCommonStockholdersBasic',cut,end)
    if not common and income:
        pdv=a.ttm(data,'PreferredStockDividendsAndOtherAdjustments',cut,end)
        if pdv:common=dict(value=income['value']-pdv['value'],method='parent_income_less_preferred_and_other_adjustments',components=income['components']+pdv['components'])
    cash=a.ttm(data,'NetCashProvidedByUsedInOperatingActivities',cut,end)
    rec.update(common_income_ttm=common,net_income_ttm=income,operating_cashflow_ttm=cash)
    prior=prior_assets(data,cut,end)
    if prior and prior['val']>0 and assets['val']>0:
        avg=(assets['val']+prior['val'])/2
        rec['average_assets']=dict(value=avg,method='current_and_prior_year_end_mean',components=[assets,prior])
        if income:rec['roa']=income['value']/avg
        if cash:rec['cfo_assets']=cash['value']/avg
    for k in ['common_income_ttm','roa','cfo_assets']:
        if rec[k] is None:rec['missing_reasons'].append('MISSING_'+k.upper())
    return rec

def main():
    manifest=json.loads((HERE/'sec-manifest.json').read_text());co=json.loads((HERE/'identity-candidates.json').read_text())['rows']
    output=[];inventory=[]
    for c in co[:100]:
        symbol=c['Symbol'];cik=c['cik'];record=manifest.get(cik,{})
        if not record.get('file'):raise RuntimeError('Required SEC acquisition missing: '+symbol)
        b=(ROOT/record['file']).read_bytes();assert sha(b)==record['filtered_sha256'];data=json.loads(b)
        for ns in data['facts'].values():
            for tag in ns.values():
                for rs in tag['units'].values():
                    assert all(r['filed']<'2024-01-01' and r['end']<'2024-01-01' for r in rs)
        predecessor=None
        if symbol=='XRX':
            old=manifest['0000108772'];bb=(ROOT/old['file']).read_bytes();assert sha(bb)==old['filtered_sha256'];predecessor=json.loads(bb)
        for month,cut in months():
            # Explicit original/successor registrant handover is checked in the
            # issuer map; old source remains available until new reporting.
            use=data;used_cik=cik
            if symbol=='XRX' and cut<'2019-11-08':use=predecessor;used_cik='0000108772'
            output.append(build_one(symbol,used_cik,use,month,cut))
        subset=output[-55:]
        inventory.append(dict(symbol=symbol,cik=cik,source_entity=data['entityName'],
                              filing_eligible=sum(r['filing_eligible'] for r in subset),shares_available=sum(bool(r['shares']) for r in subset),
                              book_available=sum(r['common_equity'] is not None for r in subset),common_income_available=sum(r['common_income_ttm'] is not None for r in subset)))
        print(symbol,inventory[-1]['filing_eligible'],inventory[-1]['shares_available'],flush=True)
    path=RAW/'monthly-fundamentals.json';write(path,output)
    write(HERE/'fundamental-coverage.json',dict(rows=len(output),months=55,issuer_slots=100,source_file=str(path.relative_to(ROOT)),sha256=sha(path.read_bytes()),issuers=inventory,
                                               note='Raw as-of extraction. Security/price identity and the final feature eligibility join are separate.'))

if __name__=='__main__':main()
