"""Adapt the preserved signal/account code to a new date window, without fitting."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
import math
import sys
import numpy as np
import pandas as pd
import exchange_calendars as xc
from acquire import HERE, ROOT, RAW, OLD, load, write, sha, scope

sys.path.insert(0,str(OLD))
import fundamentals as f
import panel as p
import models as m
import portfolio
from reviewed_sources import SPLITS, SPINS, CASH_OVERRIDES, LIFECYCLE, ALIASES
from recent_sources import NEW_SPLITS, NEW_SPINS, NEW_LIFECYCLE, REGISTRANT_BRIDGES

SPEC=scope()
START,END=SPEC['new_evaluation']
CAL=xc.get_calendar('XNYS',start='2008-01-01',end='2027-01-31')
SESSIONS=[x.date().isoformat() for x in CAL.sessions_in_range('2018-05-01',END)]
INDEX={d:i for i,d in enumerate(SESSIONS)}
COHORT=load(OLD/'identity-candidates.json')['rows'][:100]


def months():
    for month in pd.period_range(START[:7],END[:7],freq='M'):
        cut=CAL.date_to_session((month-1).end_time.normalize(),direction='previous').date().isoformat()
        yield str(month),cut


def configure():
    f.a.CAL=CAL;f.a.SESSIONS=CAL.sessions
    f.a.available.cache_clear()
    p.HERE=HERE;p.RAW=RAW;p.SESSIONS=SESSIONS;p.INDEX=INDEX
    p.SPLITS={**SPLITS,**NEW_SPLITS};p.SPINS={**SPINS,**NEW_SPINS};p.LIFECYCLE={**LIFECYCLE,**NEW_LIFECYCLE}
    p.load_sources=load_sources;p.child_rows=child_rows
    # Only the evaluation dates change. No source file or original policy is edited.
    policy=load(OLD/'account-policy.json')
    policy.update(evaluation_start=START,evaluation_end=END)
    portfolio.frozen_policy=lambda:deepcopy(policy)
    m.SESSIONS=SESSIONS
    return policy


@lru_cache(None)
def all_prices():
    old=load(OLD/'price-manifest.json')['symbols'];new=load(HERE/'price-manifest.json')['symbols']
    out={};audit={}
    for symbol in sorted(set(old)|set(new)):
        rows={};refs=[]
        for origin,record in [('old',old.get(symbol,{})),('recent',new.get(symbol,{}))]:
            if not record.get('file'):continue
            source=ROOT/record['file'];assert sha(source)==record['sha256']
            data=load(source);assert len(data)==len({r['date'][:10] for r in data})
            assert all('2018-05-01'<=r['date'][:10]<=END for r in data)
            if symbol in load(HERE/'extra-price-requests.json',{}).get('symbols',[]):
                for bar in data:
                    assert all(isinstance(bar[k],(float,int)) and math.isfinite(bar[k]) for k in ['open','high','low','close','adjClose','volume','splitFactor','divCash'])
                    assert 0<bar['low']<=min(bar['open'],bar['close'])<=max(bar['open'],bar['close'])<=bar['high']
                    assert bar['volume']>0 and bar['adjClose']>0 and bar['splitFactor']>0 and bar['divCash']>=0
            refs.append(dict(origin=origin,file=record['file'],sha256=record['sha256'],rows=len(data)))
            rows.update({r['date'][:10]:r for r in data})
        out[symbol]=rows;audit[symbol]=refs
    write(HERE/'joined-price-sources.json',audit)
    return out


def load_sources():
    series=all_prices();issuer={};audit={}
    for c in COHORT:
        symbol=c['Symbol'];provider=ALIASES.get(symbol,{}).get('provider',symbol)
        source=series.get(provider,{});end=p.LIFECYCLE.get(symbol,{}).get('end',END)
        kept={d:r for d,r in source.items() if d<=end} if symbol!='FOXA' else {}
        issuer[symbol]=kept
        audit[symbol]=dict(provider_symbol=provider,source_rows=len(source),retained_rows=len(kept),
                           excluded_after_lifecycle=[d for d in source if d>end],
                           missing_expected_sessions=[d for d in SESSIONS if d<=end and d not in kept],issues=[])
    return COHORT,series,issuer,audit


@lru_cache(None)
def child_rows(symbol):
    return all_prices().get(symbol,{})


def source_facts(cik):
    recent=load(HERE/'sec-manifest.json');old=load(OLD/'sec-manifest.json')
    record=recent.get(cik,old.get(cik,{}))
    assert record.get('file'),cik
    path=ROOT/record['file'];assert sha(path)==record['filtered_sha256']
    return load(path)


def combined_facts(first,second):
    result=deepcopy(first)
    for ns,tags in second['facts'].items():
        for tag,concept in tags.items():
            target=result['facts'].setdefault(ns,{}).setdefault(tag,{'units':{}})['units']
            for unit,rs in concept['units'].items():
                rows=target.setdefault(unit,[]);seen={json.dumps(r,sort_keys=True) for r in rows}
                rows.extend(r for r in rs if json.dumps(r,sort_keys=True) not in seen)
    return result


def fundamentals():
    output=[];inventory=[]
    for c in COHORT:
        symbol,cik=c['Symbol'],c['cik'];data=source_facts(cik)
        bridge=REGISTRANT_BRIDGES.get(symbol);successor=None
        if bridge:
            successor=source_facts(bridge['new'])
            combined=combined_facts(data,successor)
        group=[]
        for month,cut in months():
            used=combined if bridge and cut>=bridge['effective'] else data
            used_cik=bridge['new'] if bridge and cut>=bridge['effective'] else cik
            row=f.build_one(symbol,used_cik,used,month,cut)
            # The stable issuer slot is unchanged by a holding-company handover.
            row['source_cik']=used_cik;row['cik']=cik
            group.append(row)
        output.extend(group)
        inventory.append(dict(symbol=symbol,cik=cik,filing_eligible=sum(r['filing_eligible'] for r in group),shares_available=sum(bool(r['shares']) for r in group)))
    path=RAW/'monthly-fundamentals.json';write(path,output)
    write(HERE/'fundamental-coverage.json',dict(rows=len(output),months=len(list(months())),source_file=str(path.relative_to(ROOT)),sha256=sha(path),issuers=inventory,registrant_bridges=REGISTRANT_BRIDGES))
    print(json.dumps(dict(fundamental_rows=len(output),months=len(list(months())))),flush=True)


def build_panel():
    fm=load(HERE/'fundamental-coverage.json');assert sha(ROOT/fm['source_file'])==fm['sha256']
    fs=load(ROOT/fm['source_file']);prices,audit,actions=p.price_features();rows=[]
    for frow in fs:
        s,cut,month=frow['symbol'],frow['cut'],frow['month'];rs=prices[s];period=pd.Period(month,freq='M')
        days=[d for d in SESSIONS if d[:7]==month];entry,end=days[1],days[-1]
        r=dict(symbol=s,cik=frow['cik'],month=month,cut=cut,entry=entry,end=end,features={k:None for k in p.FEATURES},eligible=False,eligibility_reasons=[],label_return=None,label_status='NOT_EVALUATED',market_cap_proxy=None)
        if cut>p.LIFECYCLE.get(s,{}).get('end','9999'):
            r['eligibility_reasons'].append('ORIGINAL_SECURITY_NO_LONGER_ENTRY_ELIGIBLE');rows.append(r);continue
        if not frow['filing_eligible']:r['eligibility_reasons'].append('FILING_UNAVAILABLE_OR_STALE')
        if not frow['shares']:r['eligibility_reasons'].append('REPORTED_COMMON_SHARES_UNAVAILABLE_OR_STALE')
        q=rs.get(cut);look=SESSIONS[max(0,INDEX[cut]-251):INDEX[cut]+1]
        if len(look)!=252 or any(d not in rs or not rs[d]['qualified'] for d in look):r['eligibility_reasons'].append('252_SESSION_HISTORY_UNQUALIFIED')
        liqdays=SESSIONS[max(0,INDEX[cut]-62):INDEX[cut]+1]
        liq=[rs[d]['close']*rs[d]['volume'] for d in liqdays if d in rs and rs[d]['qualified']]
        r['median_dollar_turnover_63']=float(np.median(liq)) if len(liq)==63 else None
        if q is None or not q['qualified']:r['eligibility_reasons'].append('CUT_PRICE_UNAVAILABLE')
        elif q['close']<5:r['eligibility_reasons'].append('PRICE_BELOW_5')
        if len(liq)!=63:r['eligibility_reasons'].append('LIQUIDITY_HISTORY_UNAVAILABLE')
        elif r['median_dollar_turnover_63']<10_000_000:r['eligibility_reasons'].append('TURNOVER_BELOW_10M')
        start=CAL.date_to_session((period-13).end_time.normalize(),direction='previous').date().isoformat()
        stop=CAL.date_to_session((period-2).end_time.normalize(),direction='previous').date().isoformat()
        momentum=p.product_window(rs,start,stop);r.update(momentum_start=start,momentum_end=stop)
        vg=[rs.get(d,{}).get('gross') for d in liqdays]
        vol=float(np.std(np.array(vg)-1,ddof=1)*np.sqrt(252)) if len(vg)==63 and all(v is not None for v in vg) else None
        if momentum is None:r['eligibility_reasons'].append('MOMENTUM_PRICE_OR_ACTION_GAP')
        if vol is None:r['eligibility_reasons'].append('VOLATILITY_PRICE_OR_ACTION_GAP')
        r['features'].update(momentum=momentum,volatility=vol,roa=frow['roa'],cfo_assets=frow['cfo_assets'])
        if q and frow['shares']:
            shares=frow['shares'];subsequent=[v['actual_units_factor'] for d,v in rs.items() if shares['end']<d<=cut]
            unknown=[d for d,v in rs.items() if shares['end']<d<=cut and 'UNCLASSIFIED_SHARE_OR_PRICE_FACTOR' in v['issues']]
            cap=shares['val']*math.prod(subsequent)*q['close']
            if cap>0 and not unknown:
                r['market_cap_proxy']=cap
                if frow['common_equity'] is not None:r['features']['book_price']=frow['common_equity']/cap
                if frow['common_income_ttm'] is not None:r['features']['earnings_price']=frow['common_income_ttm']['value']/cap
            else:r['eligibility_reasons'].append('CURRENT_SHARE_BASIS_UNRESOLVED')
        r['eligible']=not r['eligibility_reasons']
        if r['eligible']:
            if month==END[:7]:r['label_status']='UNFINISHED_MONTH_NOT_A_FULL_MONTH_LABEL'
            else:r['label_return'],r['label_status']=p.label(rs,s,entry,end)
        rows.append(r)
    assert len(rows)==100*len(list(months())) and len({(r['symbol'],r['month']) for r in rows})==len(rows)
    summaries=[]
    for month,_ in months():
        rr=[r for r in rows if r['month']==month];eligible=[r for r in rr if r['eligible']]
        summaries.append(dict(month=month,slots=100,eligible=len(eligible),known_labels=sum(r['label_return'] is not None for r in eligible),
                              financial_feature_available={k:sum(r['features'][k] is not None for r in eligible) for k in p.FEATURES[:4]},
                              reasons=dict(Counter(x for r in rr for x in r['eligibility_reasons']))))
    path=RAW/'monthly-panel.json';write(path,rows)
    write(HERE/'panel-coverage.json',dict(rows=len(rows),months=len(summaries),panel_file=str(path.relative_to(ROOT)),panel_sha256=sha(path),monthly=summaries,
                                        all_original_slots_retained=True,full_months_only_for_labels=True))
    write(HERE/'price-audit.json',audit);write(HERE/'action-inventory.json',actions)
    print(json.dumps(dict(rows=len(rows),minimum_eligible=min(r['eligible'] for r in summaries),maximum_eligible=max(r['eligible'] for r in summaries))),flush=True)


def account_inputs():
    prices,audit,inventory=p.price_features();frames={d:{} for d in SESSIONS};actions=[]
    for s,rs in prices.items():
        for d,r in rs.items():
            frames[d][s]=dict(close=str(r['close']),volume=str(r['volume']),qualified=r['qualified'],status='listed',splitFactor=str(r['actual_units_factor']),divCash=str(r['cash_dividend']))
            if d<START:continue
            if r['cash_dividend']:
                actions.append(dict(action_id=f'{s}:{d}:dividend',security_id=s,effective_date=d,type='dividend',verified=not r['issues'],amount_per_share=str(r['cash_dividend']),cash_available_date=CASH_OVERRIDES.get((s,d),{}).get('payment_date')))
            if r['actual_units_factor']!=1:
                actions.append(dict(action_id=f'{s}:{d}:split',security_id=s,effective_date=d,type='split',verified=not r['issues'],factor=str(r['actual_units_factor'])))
            if (s,d) in p.SPINS or any('UNCLASSIFIED' in x or 'LARGE_DISTRIBUTION' in x for x in r['issues']):
                actions.append(dict(action_id=f'{s}:{d}:unresolved_distribution',security_id=s,effective_date=d,type='stock_distribution',verified=False,amount_per_share='0',cash_available_date=None,entitlement_source=p.SPINS.get((s,d))))
    for s,event in p.LIFECYCLE.items():
        d=event.get('event_date')
        if not d or not START<=d<=END:continue
        if event['outcome']=='CASH_MERGER':
            actions.append(dict(action_id=f'{s}:{d}:merger_cash',security_id=s,effective_date=d,type='merger_cash',verified=True,amount_per_share=str(event['cash']),cash_available_date=None,source=event['source']))
        else:
            actions.append(dict(action_id=f'{s}:{d}:unresolved_merger',security_id=s,effective_date=d,type='stock_distribution',verified=False,amount_per_share='0',cash_available_date=None,entitlement_source=event))
        for day in SESSIONS:
            if day>event['end']:frames[day][s]=dict(status='halted',qualified=False,missing_provider_row=True)
    return frames,actions,prices


configure()
if __name__=='__main__':
    if sys.argv[1]=='fundamentals':fundamentals()
    elif sys.argv[1]=='panel':build_panel()
