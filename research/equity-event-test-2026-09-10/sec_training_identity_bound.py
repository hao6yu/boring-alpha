#!/usr/bin/env python3
"""Scoped remaining-query ceiling plus identity-only count diagnostic; no returns."""
import json,statistics
from pathlib import Path
from collections import Counter
import panel
p=Path(__file__).resolve().parent
base_path=p/'sec-training-feasibility.json';base=json.loads(base_path.read_text());manifest=json.loads((p/'price-manifest.json').read_text())
assert panel.digest(p/'price-manifest.json')==base['price_manifest_sha256']
series,_=panel.load_prices(manifest);sessions=panel.calendar();identity_flag='MULTIPLE_PROVIDER_SECURITY_HISTORIES_SHARE_TICKER_NEEDS_IDENTITY_RESOLUTION';cases=[]
for row in base['source_valid_slot_checks']:
 ticker=row['historical_symbol']
 if ticker not in ['CADE','FSBC']:continue
 i=sessions.index(row['entry_date']);past=sessions[max(0,i-61):i];span=sessions[i:i+21];src=series.get(ticker,{'rows':{},'issues':{}});required=past+span
 missing=[d for d in required if d not in src['rows']];other={d:[x for x in src['issues'].get(d,[]) if x!=identity_flag] for d in required};other={d:x for d,x in other.items() if x};identity_days=[d for d in required if identity_flag in src['issues'].get(d,[])]
 complete=len(past)==61 and len(span)==21 and not missing and not other
 price_ok=liquidity_ok=None
 if all(d in src['rows'] for d in past) and len(past)==61:
  price_ok=src['rows'][past[-1]]['close']>=5
  liquidity_ok=statistics.median(src['rows'][d]['close']*src['rows'][d]['volume'] for d in past[-60:])>=2_000_000
 spy_good,_=panel.qualified_span('SPY',span,series)
 sole=bool(complete and identity_days and price_ok and liquidity_ok and spy_good)
 cases.append({'slot_id':row['slot_id'],'cik':row['cik'],'historical_symbol':ticker,'entry_date':row['entry_date'],'exit_date':row['exit_date'],'source_valid':True,'missing_required_dates':missing,'other_price_issues':other,'identity_flagged_dates':len(identity_days),'all_required_dates_present_without_other_issues':complete,'raw_preentry_price_ge5':price_ok,'median60_dollarvolume_ge2m':liquidity_ok,'benchmark_label_dates_qualified':spy_good,'excluded_solely_by_identity_if_existing_observations_verified':sole})
pegi=next(r for r in base['eligible_source_pending_rescue_slots'] if r['historical_symbol']=='PEGI');assert pegi['slot_id']=='0001561660-2020Q1' and pegi['entry_date']=='2020-03-03' and pegi['exit_date']=='2020-03-31'
remaining=[r for r in base['eligible_source_pending_rescue_slots'] if r['slot_id']!=pegi['slot_id']]
ceiling=base['currently_counted']+len(remaining);assert ceiling==199
out={'status':'SCOPED_PENDING_QUERY_CEILING_WITH_IDENTITY_DIAGNOSTIC_NO_RETURNS','policy_sha256':base['policy_sha256'],'base_feasibility_sha256':panel.digest(base_path),'price_manifest_sha256':base['price_manifest_sha256'],'sec_events_sha256':base['sec_events_sha256'],'script_sha256':panel.digest(Path(__file__)),'current_count':base['currently_counted'],'remaining_planned_queries':['PEGI','EPRT','LE','DNTH','ASXC','AD','FLNA','OSG','SER'],'maximum_additional_from_planned_queries':len(remaining),'optimistic_ceiling_for_these_queries_only':ceiling,'minimum200_reachable_from_these_queries_only':False,'eligible_pending_rescue_slots':remaining,'observed_MGTA_liquidity_failures_unchanged':base['measured_pending_failures_held_fixed'],'pegi_nonrescuable_label':{'slot_id':pegi['slot_id'],'entry_date':pegi['entry_date'],'exit_date':pegi['exit_date'],'required_stock_sessions':21,'last_trading_date':'2020-03-13','halt_eastern':'2020-03-13 20:00:00','merger_completed_before_open':'2020-03-16','suspension_date':'2020-03-17','source_urls':['https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-47','https://patternenergy.com/pattern-energy-and-canada-pension-plan-investment-board-complete-transaction/'],'source_verification':'Root independently verified Nasdaq notice and issuercompletion; research_volatility corroborated. No newnetworkrequest by this diagnostic.','reason':'A pricequery cannot create continuingordinary-commonstock observations after cancellation. No mergercashclaim or syntheticlabel is substituted under the frozen target.'},'identity_only_cases':cases,'identity_only_counts':{t:sum(r['historical_symbol']==t and r['excluded_solely_by_identity_if_existing_observations_verified'] for r in cases) for t in ['CADE','FSBC']},'limitations':['199 is a ceiling only for the nine specified remainingqueries with currentlyqualifiedMGTAobservations heldfixed. It is not a ceiling after arbitrary newsource/identityrepairs.','CADE/FSBC counterfactual diagnostics do not resolve identity: removing a flag is insufficient. Originalhistoricalsecurity and exactshare/pricebasis must be proven separately before admission.','All narrative/documenttype gates are still optimistically assumed to pass; extractednumericalfeatures are not required. No returnvalues, forecasts, fits or profitability conclusions were computed.']}
panel.write(p/'sec-training-feasibility-refined.json',out)
print(json.dumps({'current':out['current_count'],'pending_additional':len(remaining),'scoped_ceiling':ceiling,'identity_only_counts':out['identity_only_counts'],'cases':[{k:r[k] for k in ['slot_id','entry_date','exit_date','all_required_dates_present_without_other_issues','raw_preentry_price_ge5','median60_dollarvolume_ge2m','excluded_solely_by_identity_if_existing_observations_verified']} for r in cases],'output_sha256':panel.digest(p/'sec-training-feasibility-refined.json')}))
