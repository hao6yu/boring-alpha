"""Bind source and coverage checks before a single fixed model fit."""
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import json
from panel import HERE, ROOT, POLICY_SHA, calendar, digest, write


def main():
    assert not (HERE/'frozen-models.json').exists()
    names=['experiment-policy.json','registration.json','inherited-evidence.json','panel-inventory.json',
        'sec-cohort.json','sec-events-current-roster.json','sec-coverage.json','cohort-prefix-audit.json',
        'new-event-owner-audit.json','feature-source-audit.json','feature-cell-review.json',
        'price-manifest.json','price-source-exceptions.json','corporate-action-evidence.json',
        'action-source-qualification.json','unchanged-model-audit.json','data-expense.json']
    docs={name:json.loads((HERE/name).read_text()) for name in names}
    inv=docs['panel-inventory.json'];spec=docs['experiment-policy.json'];m=docs['price-manifest.json']
    sec=docs['sec-events-current-roster.json'];feat=docs['feature-source-audit.json'];cells=docs['feature-cell-review.json']
    owners=docs['new-event-owner-audit.json'];prefix=docs['cohort-prefix-audit.json']
    actions=docs['corporate-action-evidence.json'];qa=docs['action-source-qualification.json']
    path=ROOT/inv['panel']['path'];assert digest(path)==inv['panel']['sha256']
    rows=json.loads(path.read_text());slots={s['slot_id']:s for s in sec['slots']};sessions=calendar()
    timing_errors=[]
    for r in rows:
        if r['status']!='READY':continue
        slot=slots[r['event_id']];cur,prior=slot['current'],slot['prior']
        available=max(r['filing_date'],r['acceptance_date_et']);idx=bisect_right(sessions,available)
        if r['entry_date']!=sessions[idx]:timing_errors.append([r['event_id'],'entry'])
        if r['exit_date'] and (idx+20>=len(sessions) or r['exit_date']!=sessions[idx+20]):
            timing_errors.append([r['event_id'],'horizon'])
        for role,source in [('current',cur),('prior',prior)]:
            if (source['classification']!='EARNINGS_RELEASE' or
                    max(source['filing_date'],source['acceptance_eastern'][:10])>=r['entry_date']):
                timing_errors.append([r['event_id'],role])
        if prior['acceptance_utc']>=cur['acceptance_utc']:timing_errors.append([r['event_id'],'prior_after_current'])
    used=len(m['requests'])-m['inherited_request_count']
    bounded_done=(not m.get('pending_symbols') or used>=spec['expansion_price_max_requests'] or
                  bool(m.get('provider_stop')) or datetime.now(timezone.utc)>=datetime.fromisoformat(spec['sec_collection_deadline_utc']))
    checks={
        'policy_hash_unchanged':digest(HERE/'experiment-policy.json')==POLICY_SHA,
        'complete_fixed_cohort_and_slots':len(docs['sec-cohort.json']['issuers'])==200 and len(rows)==len(slots)==3200,
        'registered_slot_ids_preserved':len({r['event_id'] for r in rows})==3200 and {r['event_id'] for r in rows}==set(slots),
        'all_issuer_source_passes_completed':sec['issuers_completed']==200 and not any(s['status']=='PENDING_COLLECTION' for s in slots.values()),
        'original_prefix_and_owner_audit':prefix['passed'] and prefix['selection_sha256']==digest(HERE/'sec-cohort.json') and owners['unresolved_owner_events']==0,
        'feature_snapshot_matches_final_sources':feat['sec_events_sha256']==inv['sec_events_sha256']==digest(HERE/'sec-events-current-roster.json') and not feat['extraction_errors'],
        'sampled_original_financial_cells_checked':cells['passed'] and cells['cells_reviewed']==32 and cells['feature_source_audit_sha256']==digest(HERE/'feature-source-audit.json'),
        'timing_and_prior_availability_checked':not timing_errors,
        'evaluation_targets_masked':all(r['target_pp'] is None for r in rows if (r['entry_date'] or '')>='2022-01-01'),
        'bounded_price_acquisition_completed':bounded_done and used<=spec['expansion_price_max_requests'],
        'panel_prices_and_exceptions_bound':inv['price_manifest_sha256']==digest(HERE/'price-manifest.json') and inv['price_source_exceptions_sha256']==digest(HERE/'price-source-exceptions.json'),
        'action_audit_matches_final_prices':qa['price_manifest_sha256']==digest(HERE/'price-manifest.json') and qa['price_source_exceptions_sha256']==digest(HERE/'price-source-exceptions.json') and actions['inputs']['action_qualification_sha256']==digest(HERE/'action-source-qualification.json'),
        'unchanged_model_and_synthetic_checks':docs['unchanged-model-audit.json']['existing_tests_passed']==75 and all(docs['unchanged-model-audit.json']['checks'].values()),
        'minimum_training_count_pass':inv['fit_observations']>=200,
        'minimum_validation_count_pass':inv['validation_observations']>=100,
        'minimum_evaluation_count_and_issuers_pass':inv['evaluation_preentry_observations']>=200 and inv['evaluation_preentry_issuers']>=40,
    }
    result={'policy_sha256':POLICY_SHA,'created_utc':datetime.now(timezone.utc).isoformat(),
        'ready':all(checks.values()),'status':'READY_FOR_SINGLE_FROZEN_FIT' if all(checks.values()) else 'SOURCE_OR_COVERAGE_CHECKS_PENDING',
        'checks':checks,'panel_inventory_sha256':digest(HERE/'panel-inventory.json'),
        'timing_errors':timing_errors,'new_price_requests':used,'price_requests_still_pending':m.get('pending_symbols',[]),
        'all_registered_slot_status_counts':dict(Counter(r['status'] for r in rows)),
        'references':{n:{'path':str((HERE/n).relative_to(ROOT)),'sha256':digest(HERE/n)} for n in names},
        'limits':'Exploratory expanded incumbent cohort after coverage failure. Root source review reuses earlier independent code audits; this is not an independent replication. Listing carry-forward, daily-close fill proxy, vendor-only distributions, unresolved corporate actions and missing historical observations remain explicit. No live trading or allocation is authorized by a pass.'}
    write(HERE/'source-readiness.json',result)
    print(json.dumps({'ready':result['ready'],'failed_checks':[k for k,v in checks.items() if not v],
                      'timing_errors':len(timing_errors),'new_price_requests':used}))


if __name__=='__main__':main()
