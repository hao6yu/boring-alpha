"""Read-only collection summary, saved as a compact continuation checkpoint."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def main():
    policy=json.loads((HERE/'experiment-policy.json').read_text())
    selection=json.loads((HERE/'sec-selection.json').read_text())
    sources=json.loads((HERE/'sec-sources.json').read_text())
    prices=json.loads((HERE/'price-manifest.json').read_text())
    prior=json.loads((HERE.parent/'equity-event-test-2026-09-10/price-manifest.json').read_text())
    old=set(prior['symbols'])
    next_quota=prices.get('quota_wait_until_utc')
    if next_quota and datetime.fromisoformat(next_quota)<=datetime.now(timezone.utc):next_quota=None
    report={'updated_utc':datetime.now(timezone.utc).isoformat(),
        'stage':'SOURCE_COLLECTION','parent_commit':'b579208',
        'cohort_target':policy['cohort_count'],'selected_issuers':len(selection['issuers']),
        'screened_ranks':len(selection['screened']),'selection_status':selection['selection_status'],
        'sec_attempts':sources['attempt_count'],'sec_stop_reason':sources['stop_reason'],
        'new_price_requests':len(prices['requests'])-prices['inherited_request_count'],
        'new_price_responses':dict(Counter(v['status'] for t,v in prices['symbols'].items() if t not in old)),
        'price_quota_wait_until_utc':next_quota,'collection_deadline_utc':policy['sec_collection_deadline_utc'],
        'new_paid_data_cost_usd':0,'model_fitted':(HERE/'frozen-models.json').exists(),
        'profitability':'UNTESTED','inherited_quarterly_slots':1600}
    if selection['selection_status']=='BLOCKED_EARLIER_RANK':
        last=selection['screened'][-1]
        report['next_source_review']={k:last[k] for k in ['cik','issuer_name','seed_rank','reason']}
    event_path=HERE/'sec-events-current-roster.json'
    if not event_path.exists():event_path=HERE/'sec-events.json'
    if event_path.exists():
        e=json.loads(event_path.read_text());report['completed_issuer_source_passes']=e['issuers_completed']
    inventory_path=HERE/'panel-inventory.json'
    if inventory_path.exists():
        inventory=json.loads(inventory_path.read_text())
        report['coverage']={k:inventory[k] for k in ['fixed_slots','fit_observations','validation_observations',
            'evaluation_preentry_observations','evaluation_preentry_issuers']}
        report['stage']='FINAL_PRICE_PASS_PENDING' if prices.get('pending_symbols') else 'SOURCE_AUDIT'
    if report['model_fitted']:report['stage']='MODELS_FROZEN'
    result_path=HERE/'evaluation-result.json'
    if result_path.exists():
        result=json.loads(result_path.read_text())
        report.update(stage='EVALUATION_COMPLETE',profitability=result['status'],
                      evaluation_result=str(result_path.relative_to(HERE.parents[1])))
    decision_path=HERE/'decision-summary.json'
    if decision_path.exists():
        report['pilot_decision']=json.loads(decision_path.read_text())['decision']
    raw=json.dumps(report,indent=2,sort_keys=True)+'\n'
    (HERE/'progress.json').write_text(raw)
    print(raw)

if __name__=='__main__':main()
