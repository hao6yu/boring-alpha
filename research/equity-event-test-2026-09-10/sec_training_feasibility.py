#!/usr/bin/env python3
"""Source/price count upper bound only. No return, target or forecast computation."""
import json,hashlib,statistics
from bisect import bisect_right
from collections import Counter
from pathlib import Path
import panel
p=Path(__file__).resolve().parent
sec_raw=(p/'sec-events-current-roster.json').read_bytes();assert hashlib.sha256(sec_raw).hexdigest()=='f931061fdbfe0a44d6598c5dcdc8fe9f2a185321a897cf88b387f2cc2a329ca1'
sec=json.loads(sec_raw);manifest_raw=(p/'price-manifest.json').read_bytes();manifest=json.loads(manifest_raw);series,_=panel.load_prices(manifest);sessions=panel.calendar()
cohort=json.loads((p/'sec-cohort.json').read_text());aliases=json.loads((p/'price-alias-candidates.json').read_text());symbol_history=json.loads((p/'sec-symbol-history.json').read_text());pending={'PEGI','EPRT','LE','DNTH','ASXC','AD','FLNA','OSG','SER'};pending_ciks={}
for i in cohort['issuers']:
 if i['historical_symbol'] in pending:pending_ciks.setdefault(i['cik'],set()).add(i['historical_symbol'])
for a in aliases['aliases']:
 if a['provider_query_symbol'] in pending:pending_ciks.setdefault(a['cik'],set()).add(a['provider_query_symbol'])
for i in symbol_history['issuers']:
 for symbol in i['original_cover_symbols']:
  if symbol in pending:pending_ciks.setdefault(i['cik'],set()).add(symbol)
assert set().union(*pending_ciks.values())==pending
counts=Counter();rows=[]
for slot in sec['slots']:
 cur=slot.get('current');prior=slot.get('prior')
 if not cur or not cur.get('acceptance_eastern'):continue
 available=max(cur['filing_date'],cur['acceptance_eastern'][:10]);index=bisect_right(sessions,available)
 if index>=len(sessions) or not sessions[index].startswith('2020-'):continue
 counts['2020_entry_current_slots']+=1
 exit_day=sessions[index+20] if index+20<len(sessions) else None
 if not exit_day or exit_day>'2020-12-31':counts['right_censored_after_fit_cutoff']+=1;continue
 if not all(slot.get('checks',{}).get(k) for k in ['current_release','earliest_event','prior_release','period_identity','identity','timing']):counts['source_join_invalid']+=1;continue
 if not prior or max(prior['filing_date'],(prior.get('acceptance_eastern') or '9999')[:10])>=sessions[index]:counts['prior_not_available']+=1;continue
 counts['matured_source_valid']+=1;ticker=panel.symbol(cur['security']['historical_symbol']);past=sessions[max(0,index-61):index]
 past_good,details=panel.qualified_span(ticker,past,series);past_good=past_good and len(past)==61
 price_ok=liquidity_ok=False
 if past_good:
  bars=series[ticker]['rows'];price_ok=bars[past[-1]]['close']>=5;liquidity_ok=statistics.median(bars[d]['close']*bars[d]['volume'] for d in past[-60:])>=2_000_000
 span=sessions[index:index+21];label_checks={symbol:panel.qualified_span(symbol,span,series)[0] for symbol in [ticker,'SPY']};label_good=all(label_checks.values())
 preentry=past_good and price_ok and liquidity_ok;ready=preentry and label_good
 reason='COUNTED' if ready else 'PAST_HISTORY_UNQUALIFIED' if not past_good else 'PRICE_OR_LIQUIDITY_FAIL' if not preentry else 'LABEL_DATE_COVERAGE_UNQUALIFIED'
 counts[reason]+=1
 if preentry:counts['preentry_price_liquidity_qualified']+=1
 affected=sorted(pending_ciks.get(slot['cik'],set()))
 row={'slot_id':slot['slot_id'],'cik':slot['cik'],'historical_symbol':ticker,'entry_date':sessions[index],'exit_date':exit_day,'source_valid':True,'qualified61_close_history':past_good,'preentry_price_ge5':price_ok if past_good else None,'median60_dollarvolume_ge2m':liquidity_ok if past_good else None,'label_dates_qualified':label_good,'benchmark_label_dates_qualified':label_checks['SPY'],'current_counted':ready,'reason':reason,'pending_queries':affected}
 rows.append(row)
current=[r for r in rows if r['current_counted']];affected=[r for r in rows if r['pending_queries']];unconstrained_rescue=[r for r in affected if not r['current_counted']]
measured_failures=[r for r in unconstrained_rescue if r['qualified61_close_history'] and not (r['preentry_price_ge5'] and r['median60_dollarvolume_ge2m'])]
rescued=[r for r in unconstrained_rescue if r not in measured_failures]
# Existing qualified pre-entry observations cannot be rewritten by a successor
# identifier query. DNTH serves2023 history only, not a new2020 MGTA series.
upper=len(current)+len(rescued)
out={'status':'COUNT_UPPER_BOUND_NO_RETURNS','policy_sha256':panel.POLICY_SHA,'sec_events_sha256':hashlib.sha256(sec_raw).hexdigest(),'price_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'pending_alias_manifest_sha256':panel.digest(p/'price-alias-candidates.json'),'script_sha256':panel.digest(Path(__file__)),'counts':dict(counts),'currently_counted':len(current),'pending_source_valid_slots':len(affected),'already_counted_pending_slots':sum(r['current_counted'] for r in affected),'maximum_additional_pending_rescue':len(rescued),'optimistic_maximum':upper,'unconstrained_ceiling_overturning_measured_liquidity':len(current)+len(unconstrained_rescue),'measured_pending_failures_held_fixed':[r['slot_id'] for r in measured_failures],'eligible_source_pending_rescue_slots':rescued,'frozen_fit_minimum':200,'minimum_possible':upper>=200,'pending_affected_slots':affected,'source_valid_slot_checks':rows,'assumptions':['Every current/prior narrative and documenttype gate is assumed to pass. Extracted numerical predictors are not required because missing predictors are allowed.','No return values, labels, model forecasts, vocabulary or fit diagnostics were computed or read. panel.load_prices is used only for existing structural/action-basis qualification; liquidity uses preceding prices and volumes.','Current observations require61qualified precedingcloses, rawpreentryclose>=5, median60rawclose*volume>=2m and21qualifiedstock/SPYlabeldates. Label values are never calculated.','Pending maximum grants perfect sourceidentity/sharebasis/history/liquidity and labelcoverage only to sourcevalid2020slots with presentlyunqualifiedmissinghistory. The fourmeasuredMGTAliquidityfailures stayfixed; DNTH is a2023successorhistoryquery. No numericalpredictors or narrativefailures constrainthisoptimisticbound. PEGI remainsconditionalpendingindependentoriginalhalt/mergerverification.','Unrelatedfailedsource/price/identity slots are not replaced. No registeredrules or sources were changed.']}
panel.write(p/'sec-training-feasibility.json',out)
copy=p/'sec-checkpoints'/('feasibility-price-manifest-'+out['price_manifest_sha256']+'.json')
if not copy.exists():copy.write_bytes(manifest_raw)
print(json.dumps({k:v for k,v in out.items() if k not in ['source_valid_slot_checks','pending_affected_slots','eligible_source_pending_rescue_slots','assumptions']}))
print(json.dumps({'pending_affected_slots':[{k:r[k] for k in ['slot_id','historical_symbol','entry_date','exit_date','pending_queries','current_counted','reason']} for r in affected]}))
