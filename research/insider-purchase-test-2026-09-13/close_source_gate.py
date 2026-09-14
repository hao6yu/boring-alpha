"""Close the registered experiment after a verified, decisive sample-size bound."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from download_sources import HERE, RAW, POLICY_SHA, policy, atomic


def run():
    p=policy()
    bound=json.loads((HERE/'opportunity-upper-bound-mandatory-witnesses.json').read_text())
    check=json.loads((HERE/'necessary-bound-verification.json').read_text())
    original=json.loads((HERE/'original-source-audit.json').read_text())
    sources=json.loads((HERE/'download-manifest.json').read_text())
    assert check['status']=='NECESSARY_HISTORY_BOUND_VERIFIED'
    assert bound['status']=='STOP_INSUFFICIENT_OPPORTUNITY_UPPER_BOUND'
    assert original['all_original_checks_pass'] and not original['missing_from_bulk']
    assert sources['status']=='ALL_FIXED_ARCHIVES_VERIFIED'
    roster=json.loads((HERE/'cohort.json').read_text())['issuers']
    assert len(roster)==200
    db=sqlite3.connect('file:'+str(RAW/'submission-index.sqlite')+'?mode=ro',uri=True)
    rows=json.loads((RAW/'candidate-ledger.json').read_text())['rows']
    per_slot=defaultdict(list)
    for row in rows:per_slot[(row['issuer_cik'],row['disclosure_month'])].append(row)
    final=json.loads((RAW/'optimistic-event-slots-mandatory-witnesses.json').read_text())
    possible={k:{(r['issuer'],r['month'][:4]+'-'+r['month'][4:]) for r in v} for k,v in final.items()}
    months=[(f'{year:04d}-{month:02d}',f'{year:04d}-{month-1:02d}' if month>1 else f'{year-1:04d}-12')
            for year in (2022,2023) for month in range(1,13)]
    slots=[]
    for issuer in roster:
        for entry_month,disclosure_month in months:
            key=(issuer['cik'],disclosure_month)
            records=per_slot.get(key,[])
            slots.append({'issuer_cik':issuer['cik'],'seed_symbol':issuer['historical_symbol'],
                          'entry_month':entry_month,'disclosure_month':disclosure_month,
                          'raw_purchase_rows':len(records),
                          'record_status':'REPORTED_P_ROWS_RETAINED' if records else 'NO_P_ROWS_IN_ACQUIRED_RECORDS',
                          'possible_nonroutine_under_upper_bound':key in possible['any_classifiable'],
                          'possible_routine_under_upper_bound':key in possible['routine'],
                          'row_states':dict(Counter(r['status'] for r in records)),
                          'performance_status':'NOT_EVALUATED_SOURCE_GATE_STOP'})
    assert len(slots)==4800 and len({(s['issuer_cik'],s['entry_month']) for s in slots})==4800
    assert sum(s['possible_nonroutine_under_upper_bound'] for s in slots)==bound['nonroutine_upper_bound']['issuer_months']
    assert sum(s['possible_routine_under_upper_bound'] for s in slots)==bound['routine_upper_bound']['issuer_months']
    atomic(RAW/'all-issuer-month-slots.json',{'policy_sha256':POLICY_SHA,'slots':slots})
    now=datetime.now(timezone.utc)
    elapsed=(now-datetime.fromisoformat(p['work_started_at_utc'])).total_seconds()/60
    assert now<datetime.fromisoformat(p['deadline_utc'])
    decision={'policy_sha256':POLICY_SHA,'status':'STOP_SOURCE_SAMPLE_SIZE',
              'completed_at_utc':now.isoformat(),'elapsed_minutes':round(elapsed,2),
              'source_download_bytes':sources['downloaded_bytes'],'new_paid_data_usd':0,
              'cohort_issuers':200,'issuer_month_slots_preserved':4800,
              'purchase_rows_preserved':sum(s['raw_purchase_rows'] for s in slots),
              'nonroutine_issuer_month_upper_bound':bound['nonroutine_upper_bound']['issuer_months'],
              'routine_issuer_month_upper_bound':bound['routine_upper_bound']['issuer_months'],
              'gates':bound['gates'],
              'slot_ledger_file':str((RAW/'all-issuer-month-slots.json').relative_to(HERE.parent.parent)),
              'slot_ledger_sha256':hashlib.sha256((RAW/'all-issuer-month-slots.json').read_bytes()).hexdigest(),
              'profitability_status':'NOT_TESTED', 'security_return_observations_read':0,
              'remaining_historical_footnote_review':'Not completed: even resolving all remaining cases favorably cannot clear the recorded source-conditional bound. Preliminary classification outputs are not certified signal counts.',
              'scope':'This fixed 200-issuer rule/sample cannot meet its operational minimums in the acquired records. Not a general rejection of insider strategies and not evidence of negative returns.',
              'next_action':'Close this version. No cohort expansion, retuning, reserved-window opening, orders or paid data.'}
    atomic(HERE/'final-decision.json',decision)
    print(json.dumps(decision),flush=True)


if __name__=='__main__':run()
