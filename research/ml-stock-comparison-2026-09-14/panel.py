#!/usr/bin/env python3
"""Build every frozen cohort/month slot; no scores or fitted model here."""
from collections import Counter
from functools import lru_cache
import json,math,sys
from pathlib import Path
import numpy as np
import pandas as pd
from fundamentals import HERE,ROOT,RAW,a,months
from reviewed_sources import SPLITS,SPINS,CASH_OVERRIDES,LIFECYCLE,ALIASES
sys.path.insert(0,str(HERE.parent/'ml-free-data-feasibility-2026-09-13'))
from probe import sha,write
FEATURES=['book_price','earnings_price','roa','cfo_assets','momentum','volatility']
SESSIONS=[x.date().isoformat() for x in a.CAL.sessions_in_range('2018-05-01','2023-12-29')]
INDEX={d:i for i,d in enumerate(SESSIONS)}

def load_sources():
    pm=json.loads((HERE/'price-manifest.json').read_text());co=json.loads((HERE/'identity-candidates.json').read_text())['rows'][:100]
    sm=json.loads((HERE/'submissions-manifest.json').read_text());series={};source_audit={};identities=[]
    for symbol,m in pm['symbols'].items():
        if not m.get('file'):continue
        b=(ROOT/m['file']).read_bytes();assert sha(b)==m['sha256'];rs=json.loads(b)
        assert all('2018-05-01'<=r['date'][:10]<'2024-01-01' for r in rs)
        assert len({r['date'][:10] for r in rs})==len(rs)
        series[symbol]={r['date'][:10]:r for r in rs}
    for c in co:
        m=sm.get(c['cik'],{});assert m.get('file')
        assert sha((ROOT/m['file']).read_bytes())==m['sha256']
        assert c['Symbol']!='SEE' or m['name']=='SEALED AIR CORP/DE'
        identities.append(dict(symbol=c['Symbol'],historical_roster_name=c['Name'],cik=c['cik'],sec_name=m['name'],
                               sec_tickers=m.get('tickers'),sec_former_names=m.get('former_names'),source=m['url'],source_sha256=m['sha256'],
                               qualification='2018 roster name reviewed against SEC registrant/current and former names; explicit lifecycle and registrant changes retained. Current membership not used.',
                               lifecycle=LIFECYCLE.get(c['Symbol']),alias=ALIASES.get(c['Symbol'])))
    # Provider aliases are accepted only after separately documented issuer
    # continuity. Never use the modern FOXA series for Twenty-First Century Fox.
    issuer_series={}
    for c in co:
        s=c['Symbol'];provider=ALIASES.get(s,{}).get('provider',s)
        rs=series.get(provider,series.get(s,{}))
        if s=='FOXA':rs={}
        end=LIFECYCLE.get(s,{}).get('end','2023-12-29')
        kept={d:r for d,r in rs.items() if d<=end};issuer_series[s]=kept
        excluded=[d for d in rs if d>end]
        source_audit[s]=dict(provider_symbol=provider,source_rows=len(rs),retained_rows=len(kept),excluded_after_lifecycle=excluded,
                             missing_expected_sessions=[d for d in SESSIONS if d<=end and d not in kept],issues=[])
    write(HERE/'identity-map.json',dict(rows=identities,unused_rejected_cik='0000012659',
         registrant_bridges={'XRX':{'old':'0000108772','new':'0001770450','effective':'2019-07-31','ratio':1,'source':'https://www.sec.gov/Archives/edgar/data/1770450/000119312519208837/d767474d8k12b.htm'},
                             'CI':{'old':'0000701221','new':'0001739940','effective':'2018-12-21','source':'https://www.sec.gov/Archives/edgar/data/1532063/000114036118045477/form8k.htm'}}))
    return co,series,issuer_series,source_audit

def price_features():
    co,all_series,series,audit=load_sources();out={};action_rows=[]
    for c in co:
        s=c['Symbol'];rs=series[s];processed={};previous=None
        for day,r in sorted(rs.items()):
            issues=[];k=(s,day)
            values=[r[x] for x in ['open','high','low','close','adjClose','volume','splitFactor','divCash']]
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):issues.append('NONFINITE')
            elif not (0<r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] and r['volume']>0 and r['adjClose']>0 and r['splitFactor']>0 and r['divCash']>=0):issues.append('INVALID_BAR')
            unit_factor=1.;cash=r['divCash'];distribution=0.;event=None
            if k in SPLITS:unit_factor=SPLITS[k]['ratio'];assert r['splitFactor']==unit_factor
            elif k in SPINS:
                event=SPINS[k];child=all_series.get(event['child'],{}).get(day)
                cash=0
                if child:distribution=event['ratio']*child['close']
                else:issues.append('DISTRIBUTED_SECURITY_MARK_MISSING')
            elif previous and r['splitFactor']!=1:issues.append('UNCLASSIFIED_SHARE_OR_PRICE_FACTOR')
            if k in CASH_OVERRIDES:cash=CASH_OVERRIDES[k]['amount']
            elif cash>r['close']*.04 and k not in SPINS:issues.append('LARGE_DISTRIBUTION_NEEDS_SOURCE')
            if previous:
                prior,pr=previous
                if INDEX.get(day,-10)!=INDEX.get(prior,-20)+1:issues.append('MISSING_PREVIOUS_SESSION')
                actual=(r['adjClose']/r['close'])/(pr['adjClose']/pr['close'])
                expected=r['splitFactor']*(r['close']+r['divCash'])/r['close']
                if abs(actual/expected-1)>1e-5:issues.append('PROVIDER_ADJUSTMENT_INCONSISTENT')
                gross=(unit_factor*(r['close']+cash)+distribution)/pr['close'] if not issues else None
            else:gross=None
            processed[day]=dict(close=r['close'],volume=r['volume'],gross=gross,qualified=not any(x in issues for x in ['NONFINITE','INVALID_BAR']),
                                 actual_units_factor=unit_factor,cash_dividend=cash,issues=issues,splitFactor=r['splitFactor'],divCash=r['divCash'])
            if issues:audit[s]['issues'].append(dict(date=day,issues=issues))
            if r['divCash'] or r['splitFactor']!=1 or k in CASH_OVERRIDES:
                action_rows.append(dict(symbol=s,date=day,vendor_split=r['splitFactor'],vendor_dividend=r['divCash'],actual_units_factor=unit_factor,
                                        cash_entitlement=cash,stock_distribution=event,source_override=CASH_OVERRIDES.get(k) or SPLITS.get(k),issues=issues))
            previous=(day,r)
        out[s]=processed
    return out,audit,action_rows

def product_window(rs,start,end):
    if start not in INDEX or end not in INDEX or start not in rs or not rs[start]['qualified']:return None
    vals=[rs.get(d,{}).get('gross') for d in SESSIONS[INDEX[start]+1:INDEX[end]+1]]
    if not vals or any(x is None or not math.isfinite(x) or x<=0 for x in vals):return None
    return float(np.prod(vals)-1)

@lru_cache(None)
def child_rows(symbol):
    m=json.loads((HERE/'price-manifest.json').read_text())['symbols'].get(symbol,{})
    if not m.get('file'):return {}
    b=(ROOT/m['file']).read_bytes();assert sha(b)==m['sha256']
    data=json.loads(b)
    assert all('2018-05-01'<=r['date'][:10]<'2024-01-01' for r in data)
    return {r['date'][:10]:r for r in data}

def label(rs,symbol,entry,end):
    life=LIFECYCLE.get(symbol,{})
    if entry>life.get('end','9999'):return None,'ENTRY_AFTER_ORIGINAL_SECURITY_REMOVED'
    if life.get('event_date','9999')<=end:
        last=life['end']
        before=product_window(rs,entry,last) if last!=entry else 0
        if before is None or last not in rs:return None,'MISSING_PREMERGER_LABEL_PATH'
        if life.get('outcome')=='CASH_MERGER':
            return (1+before)*life['cash']/rs[last]['close']-1,'CASH_MERGER_CLAIM_TO_MONTH_END'
        if life.get('outcome') not in ['STOCK_MERGER','CASH_AND_STOCK_MERGER']:
            return None,'STOCK_CONVERSION_LABEL_NOT_YET_RECONCILED'
        child=child_rows(life['child']);day=life['event_date']
        if day not in child:return None,'MERGER_CHILD_PRICE_MISSING'
        value=child[day]['close'];previous=child[day]
        for d in SESSIONS[INDEX[day]+1:INDEX[end]+1]:
            current=child.get(d)
            if not current or current['splitFactor']!=1 or current['divCash']>current['close']*.04 or current['close']<=0:
                return None,'MERGER_CHILD_PATH_OR_ACTION_UNQUALIFIED'
            transition=(current['adjClose']/current['close'])/(previous['adjClose']/previous['close'])
            if abs(transition/((current['close']+current['divCash'])/current['close'])-1)>1e-5:
                return None,'MERGER_CHILD_ADJUSTMENT_INCONSISTENT'
            value*=(current['close']+current['divCash'])/previous['close'];previous=current
        terminal=life.get('cash',0)+life['ratio']*value
        return (1+before)*terminal/rs[last]['close']-1,'DOCUMENTED_STOCK_CONVERSION_REFERENCE'
    value=product_window(rs,entry,end)
    return value,'KNOWN_REFERENCE_TOTAL_RETURN' if value is not None else 'LABEL_PRICE_OR_ACTION_GAP'

def main():
    fundamental=json.loads((HERE/'fundamental-coverage.json').read_text());b=(ROOT/fundamental['source_file']).read_bytes();assert sha(b)==fundamental['sha256'];fs=json.loads(b)
    prices,audit,actions=price_features();rows=[];monthly=[]
    for f in fs:
        s,cut,month=f['symbol'],f['cut'],f['month'];rs=prices[s];p=pd.Period(month,freq='M');days=[d for d in SESSIONS if d[:7]==month];entry,end=days[1],days[-1]
        r=dict(symbol=s,cik=f['cik'],month=month,cut=cut,entry=entry,end=end,features={k:None for k in FEATURES},eligible=False,eligibility_reasons=[],label_return=None,label_status='NOT_EVALUATED',market_cap_proxy=None)
        if cut>LIFECYCLE.get(s,{}).get('end','9999'):
            r['eligibility_reasons'].append('ORIGINAL_SECURITY_NO_LONGER_ENTRY_ELIGIBLE');rows.append(r);continue
        if not f['filing_eligible']:r['eligibility_reasons'].append('FILING_UNAVAILABLE_OR_STALE')
        if not f['shares']:r['eligibility_reasons'].append('REPORTED_COMMON_SHARES_UNAVAILABLE_OR_STALE')
        q=rs.get(cut)
        look=SESSIONS[max(0,INDEX[cut]-251):INDEX[cut]+1]
        if len(look)!=252 or any(d not in rs or not rs[d]['qualified'] for d in look):r['eligibility_reasons'].append('252_SESSION_HISTORY_UNQUALIFIED')
        liqdays=SESSIONS[max(0,INDEX[cut]-62):INDEX[cut]+1]
        liq=[rs[d]['close']*rs[d]['volume'] for d in liqdays if d in rs and rs[d]['qualified']]
        r['median_dollar_turnover_63']=float(np.median(liq)) if len(liq)==63 else None
        if q is None or not q['qualified']:r['eligibility_reasons'].append('CUT_PRICE_UNAVAILABLE')
        elif q['close']<5:r['eligibility_reasons'].append('PRICE_BELOW_5')
        if len(liq)!=63:r['eligibility_reasons'].append('LIQUIDITY_HISTORY_UNAVAILABLE')
        elif r['median_dollar_turnover_63']<10_000_000:r['eligibility_reasons'].append('TURNOVER_BELOW_10M')
        start=a.CAL.date_to_session((p-13).end_time.normalize(),direction='previous').date().isoformat()
        stop=a.CAL.date_to_session((p-2).end_time.normalize(),direction='previous').date().isoformat()
        momentum=product_window(rs,start,stop);r.update(momentum_start=start,momentum_end=stop)
        vol_gross=[rs.get(d,{}).get('gross') for d in liqdays]
        vol=float(np.std(np.array(vol_gross)-1,ddof=1)*np.sqrt(252)) if len(vol_gross)==63 and all(v is not None for v in vol_gross) else None
        if momentum is None:r['eligibility_reasons'].append('MOMENTUM_PRICE_OR_ACTION_GAP')
        if vol is None:r['eligibility_reasons'].append('VOLATILITY_PRICE_OR_ACTION_GAP')
        r['features'].update(momentum=momentum,volatility=vol,roa=f['roa'],cfo_assets=f['cfo_assets'])
        if q and f['shares']:
            shares=f['shares'];subsequent=[v['actual_units_factor'] for d,v in rs.items() if shares['end']<d<=cut]
            # A share-count transition cannot be imputed from a vendor's
            # unidentified factor. An identified spinoff leaves parent units 1.
            unknown=[d for d,v in rs.items() if shares['end']<d<=cut and 'UNCLASSIFIED_SHARE_OR_PRICE_FACTOR' in v['issues']]
            cap=shares['val']*math.prod(subsequent)*q['close']
            if cap>0 and not unknown:
                r['market_cap_proxy']=cap
                if f['common_equity'] is not None:r['features']['book_price']=f['common_equity']/cap
                if f['common_income_ttm'] is not None:r['features']['earnings_price']=f['common_income_ttm']['value']/cap
            else:r['eligibility_reasons'].append('CURRENT_SHARE_BASIS_UNRESOLVED')
        r['eligible']=not r['eligibility_reasons']
        if r['eligible']:r['label_return'],r['label_status']=label(rs,s,entry,end)
        rows.append(r)
    assert len(rows)==5500 and len({(r['symbol'],r['month']) for r in rows})==5500
    for month in sorted({r['month'] for r in rows}):
        rr=[r for r in rows if r['month']==month];eligible=[r for r in rr if r['eligible']];known=[r for r in eligible if r['label_return'] is not None]
        monthly.append(dict(month=month,slots=100,eligible=len(eligible),known_labels=len(known),eligible_label_coverage=len(known)/len(eligible) if eligible else None,
                            financial_feature_available={k:sum(r['features'][k] is not None for r in eligible) for k in FEATURES[:4]},
                            reasons=dict(Counter(x for r in rr for x in r['eligibility_reasons']))))
    diagnostic=[m for m in monthly if m['month']>='2022-01'];yearly={}
    for year in ['2022','2023']:
        ms=[m for m in diagnostic if m['month'].startswith(year)];e=sum(m['eligible'] for m in ms);n=sum(m['known_labels'] for m in ms);yearly[year]=dict(eligible=e,known=n,coverage=n/e if e else 0)
    passes=all(m['eligible']>=80 for m in diagnostic) and all(y['coverage']>=.95 for y in yearly.values())
    path=RAW/'monthly-panel.json';write(path,rows)
    pm=json.loads((HERE/'price-manifest.json').read_text())
    original={r['symbol'] for r in rows}
    requested=original|set(json.loads((HERE/'extra-price-requests.json').read_text())['symbols'])
    missing=sorted(requested-set(pm['symbols']))
    data_gaps={s:len(v['missing_expected_sessions']) for s,v in audit.items() if v['missing_expected_sessions']}
    write(HERE/'panel-coverage.json',dict(rows=len(rows),months=55,cohort_slots=100,aggregate_comparison_coverage_pass=passes,monthly=monthly,diagnostic_years=yearly,
                                        panel_file=str(path.relative_to(ROOT)),panel_sha256=sha(path.read_bytes()),
                                        all_original_requests_attempted=original<=set(pm['symbols']),all_planned_requests_attempted=not missing,
                                        pending_price_symbols=missing,source_complete=not missing and not data_gaps,
                                        historical_price_gap_counts=data_gaps,
                                        source_completeness_note='Attempted requests are distinct from full history and action qualification. Removed or missing securities remain in cohort slots.'))
    write(HERE/'price-audit.json',audit);write(HERE/'action-inventory.json',actions)
    print(json.dumps(dict(panel_rows=len(rows),eligible_min_diagnostic=min(m['eligible'] for m in diagnostic),yearly=yearly,coverage_pass=passes),indent=2))

if __name__=='__main__':main()
