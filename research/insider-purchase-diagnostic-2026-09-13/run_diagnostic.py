"""One fixed, offline account diagnostic after source-only signal freezing."""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

from diagnostic_io import HERE, ROOT, RAW, POLICY_SHA, atomic, digest, policy, check_budget
import portfolio as diagnostic_account

PARENT = HERE.with_name('equity-event-expansion-2026-09-13')


def key(month, cik):
    return hashlib.sha256(f"{policy()['selection_seed']}|{month}|{cik}".encode()).hexdigest()


def prior_features(cik, day, sessions, prices):
    i = sessions.index(day)
    lookback = sessions[i-61:i]
    sec = cik+':single_common'
    bars = [prices.get(d,{}).get(sec) for d in lookback]
    if any(b and b.get('status') in ('halted','otc') for b in bars[-60:]):
        return {'status':'LIQUIDITY_INELIGIBLE_KNOWN_STATUS'}
    if len(bars)!=61 or any(not b or b.get('qualified') is not True or b.get('status')!='listed' or
                           b.get('close',0)<=0 or b.get('volume',0)<=0 for b in bars):
        return {'status':'PRIOR_PRICE_OR_IDENTITY_UNRESOLVED',
                'missing_or_invalid_days':[d for d,b in zip(lookback,bars) if not b or b.get('qualified') is not True or b.get('status')!='listed' or b.get('close',0)<=0 or b.get('volume',0)<=0]}
    px = bars[-1]['close']
    vol = float(np.median([b['close']*b['volume'] for b in bars[-60:]]))
    if px<5 or vol<2_000_000:
        return {'status':'LIQUIDITY_INELIGIBLE','prior_close':px,'median_dollar_volume_60':vol}
    # The adjustment ratio is only compared within a continuous source ticker.
    # A changed ticker requires a qualified continuity bridge; do not guess one.
    if len({b['source_ticker'] for b in bars})!=1:
        return {'status':'PRIOR_RETURN_TICKER_BRIDGE_UNRESOLVED'}
    return {'status':'READY','prior_close':px,'median_dollar_volume_60':vol,
            'past_60_session_total_return':bars[-1]['adjClose']/bars[0]['adjClose']-1}


def build_candidates(frozen, sessions, prices):
    slots = {(s['issuer_cik'],s['disclosure_month']):s for s in frozen['slots']}
    ciks = sorted({s['issuer_cik'] for s in frozen['slots']})
    candidates = {name:[] for name in ('nonroutine','routine','matched')}
    coverage, matched_rows, ranked = [], [], []
    for month in sorted({d[:7] for d in sessions if '2022-01-03'<=d<='2023-12-29'}):
        day = min(d for d in sessions if d[:7]==month)
        prior_month = sessions[sessions.index(day)-1][:7]
        # Previous calendar month-end, even when it is not a trading day.
        from datetime import timedelta
        cutoff = (date.fromisoformat(month+'-01')-timedelta(days=1)).isoformat()
        features = {c:prior_features(c,day,sessions,prices) for c in ciks}
        for c,f in features.items():
            coverage.append({'issuer_cik':c,'entry_month':month,**f})
        ready = [c for c in ciks if features[c]['status']=='READY']
        boundaries = {name:np.quantile([features[c][name] for c in ready],np.arange(1,10)/10,method='linear')
                      for name in ('prior_close','median_dollar_volume_60')} if ready else {}
        deciles = {c:tuple(int(np.searchsorted(boundaries[n],features[c][n],side='right'))
                          for n in boundaries) for c in ready}
        selected = {}
        for category,name in [('NONROUTINE','nonroutine'),('ROUTINE','routine')]:
            pool = sorted([s for s in frozen['signals'] if s['disclosure_month']==prior_month and s['classification']==category],
                          key=lambda s:key(month,s['issuer_cik']))
            qualifying = [s for s in pool if features[s['issuer_cik']]['status']=='READY']
            selected[name] = qualifying[:4]
            for s in pool:
                cik=s['issuer_cik']; f=features[cik]
                status = 'SELECTED' if s in qualifying[:4] else 'OUTSIDE_FOUR_SLOTS' if f['status']=='READY' else f['status']
                ranked.append({'issuer_cik':cik,'entry_month':month,'category':name,'selection_status':status,'selection_key':key(month,cik)})
            for s in selected[name]:
                cik=s['issuer_cik']
                candidates[name].append({'event_id':f'{name}:{month}:{cik}','security_id':cik+':single_common',
                    'cik':cik,'accession':s['source_rows'][0]['accession'],'filing_date':cutoff,'acceptance_date_et':cutoff,
                    'score':None,'eligibility_status':'READY','selection_key':key(month,cik)})
        available = {c for c in ready if not slots[(c,prior_month)]['any_p_disclosure']}
        for s in selected['nonroutine']:
            cik=s['issuer_cik']
            possible = [c for c in available if deciles[c]==deciles[cik]]
            chosen = min(possible,key=lambda c:(abs(features[c]['past_60_session_total_return']-features[cik]['past_60_session_total_return']),key(month,c))) if possible else None
            matched_rows.append({'entry_month':month,'signal_cik':cik,'control_cik':chosen,'deciles':deciles[cik],
                'status':'MATCHED' if chosen else 'NO_SAME_DECILE_CONTROL','available_same_decile':len(possible)})
            if chosen is None:
                continue
            available.remove(chosen)
            candidates['matched'].append({'event_id':f'matched:{month}:{chosen}','security_id':chosen+':single_common',
                'cik':chosen,'accession':f'match:{cik}','filing_date':cutoff,'acceptance_date_et':cutoff,
                'score':None,'eligibility_status':'READY','selection_key':key(month,cik),'matched_signal_cik':cik})
    return candidates, {'all_cohort_prior_price_checks':coverage,'ranked_signals':ranked,'matches':matched_rows}


def bootstrap(values):
    if any(v is None for v in values):
        return {'status':'UNRESOLVED_PAIRED_DAILY_RETURNS'}
    x=np.asarray(values,dtype=float); rng=np.random.Generator(np.random.PCG64(20260913))
    idx=rng.integers(0,len(x),size=2000); total=x[idx].copy()
    for _ in range(1,len(x)):
        restart=rng.random(2000)<.05; fresh=rng.integers(0,len(x),size=2000)
        idx=np.where(restart,fresh,(idx+1)%len(x)); total+=x[idx]
    draws=252*total/len(x); low,high=np.quantile(draws,[.025,.975],method='linear')
    return {'status':'DESCRIPTIVE_ONLY','estimand':'annualized arithmetic mean daily account return difference',
        'estimate':float(252*x.mean()),'lower_95':float(low),'upper_95':float(high),
        'seed':20260913,'replicates':2000,'expected_block_sessions':20,'observations':len(x),
        'limitations':'Short, sparse, already-explored history; no issuer-cluster or multiple-search correction. Not an independent validation.'}


def metrics(account):
    initial=float(account['initial_capital']); daily=account['daily']
    valid=all(d['nav'] is not None for d in daily)
    out={'accounting_status':account['status'],'daily_nav_complete':valid,'completed_positions':len(account['completed_positions']),
         'buy_fills':sum(f['side']=='buy' for f in account['fills']),'decision_states':dict(Counter(d['status'] for d in account['decisions'])),
         'stopped':account['stopped'],'stop_date':account['stop_date'],'unresolved_candidate_ids':account['unresolved_candidate_ids'],
         'unpriced_days':len(account['unpriced_days']),'open_stock_lots':len(account['open_holdings']),
         'initial_capital_usd':initial,'ending_nav_usd':None,'net_profit_usd':None,'cagr':None,'max_drawdown_fraction':None}
    if not valid: return out
    nav=np.array([float(d['nav']) for d in daily]); days=(date.fromisoformat(daily[-1]['date'])-date.fromisoformat(daily[0]['date'])).days+1
    peaks=np.maximum.accumulate(np.r_[initial,nav])[1:]
    fees=sum(float(f['fee_total']) for f in account['fills']); slip=sum(float(f['slippage_cost']) for f in account['fills'])
    active={f['date'][:7] for f in account['fills']}|{d['date'][:7] for d in daily if d['holdings']}
    equity=[sum(float(h['quantity'])*float(h['qualified_close']) for h in d['holdings'].values()) for d in daily]
    out.update(ending_nav_usd=float(nav[-1]),net_profit_usd=float(nav[-1]-initial),cagr=float((nav[-1]/initial)**(365/days)-1),
        total_return=float(nav[-1]/initial-1),max_drawdown_fraction=float(np.max(1-nav/peaks)),max_drawdown_usd=float(np.max(peaks-nav)),
        commissions_and_regulatory_usd=fees,slippage_usd=slip,gross_same_fills_profit_usd=float(nav[-1]-initial+fees+slip),
        gross_same_fills_cagr=float(((nav[-1]+fees+slip)/initial)**(365/days)-1),
        active_months=len(active),average_stock_exposure_fraction=float(np.mean(np.array(equity)/nav)),
        average_settled_cash_fraction=float(np.mean([float(d['settled_cash'])/float(d['nav']) for d in daily])),
        ending_settled_cash_usd=float(account['ending_settled_cash']),
        ending_unpaid_claims_usd=sum(float(c['amount']) for c in account['claims'] if not c['paid']),
        ending_locked_dividend_claims_usd=sum(float(c['amount']) for c in account['claims'] if not c['paid'] and c['type']=='dividend'),
        calendar_days=days)
    last=initial; monthly=[]
    for month in sorted({d['date'][:7] for d in daily}):
        end=next(d for d in reversed(daily) if d['date'][:7]==month); current=float(end['nav'])
        monthly.append({'month':month,'net_profit_usd':current-last,'return':current/last-1,'ending_nav_usd':current})
        last=current
    out['monthly']=monthly
    by_issuer=defaultdict(float); position_returns=[]
    for h in account['completed_positions']:
        dividend=sum(float(c['amount']) for c in account['claims'] if c['event_id']==h['event_id'] and c['type']=='dividend')
        pnl=float(h['net_sale_proceeds'])+dividend-float(h['cost_basis'])
        by_issuer[h['cik']]+=pnl
        position_returns.append({'event_id':h['event_id'],'cik':h['cik'],'net_profit_usd':pnl,'return':pnl/float(h['cost_basis'])})
    out['issuer_net_profit_usd']=dict(sorted(by_issuer.items(),key=lambda kv:-kv[1]))
    out['position_results']=position_returns
    out['positive_position_fraction']=sum(p['net_profit_usd']>0 for p in position_returns)/len(position_returns) if position_returns else None
    out['cash_reference_scenarios']=[{'annual_rate':rate,'ending_value_usd':initial*(1+rate)**(days/365),
        'strategy_minus_cash_usd':float(nav[-1])-initial*(1+rate)**(days/365)} for rate in (.04,.06)]
    return out


def run():
    check_budget()
    assert not (HERE/'evaluation-result.json').exists(), 'Preserve prior evaluation; no silent rerun'
    freeze=json.loads((HERE/'signal-freeze.json').read_text())
    assert freeze['policy_sha256']==POLICY_SHA and digest(ROOT/freeze['signals']['path'])==freeze['signals']['sha256']
    assert all(digest(HERE/name)==sha for name,sha in freeze['source_files'].items())
    frozen=json.loads((ROOT/freeze['signals']['path']).read_text())
    registration={'policy_sha256':POLICY_SHA,'started_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_signal_freeze_sha256':digest(HERE/'signal-freeze.json'),
        'code_sha256':{n:digest(HERE/n) for n in ['run_diagnostic.py','portfolio.py','diagnostic_io.py']},
        'reuse_code_sha256':{n:digest(PARENT/n) for n in ['run_experiment.py','panel.py','price_data.py']},
        'source_inputs':{n:digest(PARENT/n) for n in ['sec-cohort.json','sec-events.json','corporate-action-evidence.json','price-manifest.json','price-source-exceptions.json']},
        'matching_convention':'Linear empirical decile cutoffs over all qualified past-only cohort features each month; right-side bin for ties; exact price/volume decile match, nearest past60 total return, fixed hash tie-break; no replacement and no relaxed matching.',
        'selection_convention':'Past-only liquidity eligibility precedes fixed hash top-four selection; no replacement after no-fill or cash rejection.',
        'no_price_outcome_optimized_parameters':True}
    atomic(HERE/'evaluation-start.json',registration)
    # Import the unchanged cached-data adapter. Its network collection entrypoint
    # is not called, and no provider key is read by these functions.
    sys.path.insert(0,str(PARENT))
    from panel import load_prices, calendar
    from run_experiment import source_frames
    sessions=calendar(); assert min(sessions)>='2019-10-01' and max(sessions)<='2023-12-29'
    series, price_audit=load_prices()
    sec=json.loads((PARENT/'sec-events.json').read_text()); cohort=json.loads((PARENT/'sec-cohort.json').read_text())
    prices,actions,identities=source_frames(series,sessions,sec,cohort)
    for day, daily in prices.items():
        for b in daily.values():
            if not b.get('missing_provider_row'):
                b['adjClose']=series[b['source_ticker']]['rows'][day]['adjClose']
    candidates,coverage=build_candidates(frozen,sessions,prices)
    candidate_sha=atomic(RAW/'frozen-account-candidates.json',{'candidates':candidates,'coverage':coverage})
    atomic(HERE/'account-candidate-freeze.json',{'policy_sha256':POLICY_SHA,'at_utc':datetime.now(timezone.utc).isoformat(),
        'sha256':candidate_sha,'candidates':{k:len(v) for k,v in candidates.items()},
        'ranked_signal_states':dict(Counter(r['selection_status'] for r in coverage['ranked_signals'])),
        'match_states':dict(Counter(r['status'] for r in coverage['matches'])),
        'all_cohort_prior_price_states':dict(Counter(r['status'] for r in coverage['all_cohort_prior_price_checks'])),
        'account_returns_computed':False,'price_files_loaded_but_candidate_functions_access_preentry_dates_only':True})
    accounts={}; summaries={}; comparisons={}
    for cost in ('base','stress'):
        accounts[cost]={}; summaries[cost]={}
        for name in candidates:
            a=diagnostic_account.simulate(calendar=sessions,prices=prices,candidates=candidates[name],actions=actions,cost_case=cost,rank_mode='matched')
            accounts[cost][name]=a; summaries[cost][name]=metrics(a)
        comparisons[cost]={}
        for control in ('routine','matched'):
            a=accounts[cost]['nonroutine']['daily']; b=accounts[cost][control]['daily']
            assert [d['date'] for d in a]==[d['date'] for d in b]
            diffs=[float(x['daily_return'])-float(y['daily_return']) if x['daily_return'] is not None and y['daily_return'] is not None else None for x,y in zip(a,b)]
            comparisons[cost][control]=bootstrap(diffs)
    ledger_sha=atomic(RAW/'account-ledgers.json',accounts)
    atomic(RAW/'price-identity-audit.json',{'price_audit':price_audit,'identities':identities})
    result={'policy_sha256':POLICY_SHA,'status':'EXPLORATORY_DIAGNOSTIC_COMPLETE_NO_VALIDATION_PASS',
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_paid_data_usd':0,'capital_usd':10000,
        'evaluation_start':'2022-01-03','evaluation_end':'2023-12-29','candidate_freeze_sha256':digest(HERE/'account-candidate-freeze.json'),
        'accounts':summaries,'paired_descriptive_uncertainty':comparisons,
        'ledger':{'path':str((RAW/'account-ledgers.json').relative_to(ROOT)),'sha256':ledger_sha},
        'limitations':['Source-identified subset with explicit abstention; original sample thresholds remain unmet.',
            'Past-price/identity gaps are reported before outcomes; missing potential signals or controls limit full-universe claims.',
            'Close-based conservative fill proxies are modeled executions, not historical order-book fills.',
            '2022-2023 is already-explored market history; 2024-2025 strategy prices were not opened.',
            'No cash interest or taxes; cash benchmarks are stated constant-rate scenarios, not historical yields.',
            'Fixed current-rate IBKR Pro counterfactual; actual user account tariff unverified.']}
    atomic(HERE/'evaluation-result.json',result)
    print(json.dumps({'status':result['status'],'accounts':{c:{n:{k:v for k,v in m.items() if k in ['accounting_status','ending_nav_usd','net_profit_usd','cagr','completed_positions','buy_fills','unpriced_days','active_months','max_drawdown_fraction']} for n,m in models.items()} for c,models in summaries.items()}}))


if __name__=='__main__':
    run()
