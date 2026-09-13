"""Refresh reviewed action evidence from action-only audit records.

No prices, adjusted prices, returns, targets or forecasts are read. The parent
auditor supplies source hashes and structural/adjustment qualification separately.
This helper never treats a generic splitFactor as a proved share conversion.
Manually reviewed exceptions, source notices and status events remain in the
evidence envelope; rerunning after a download batch refreshes only its inventory.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path


HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
POLICY_SHA='5c9daa1573ead42077ea323e641433c69112d6d3977f5e20c91d8bd1d04513bc'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh():
    audit_path=HERE/'action-source-qualification.json'
    audit=json.loads(audit_path.read_text())
    manifest_path=HERE/'price-manifest.json'
    manifest=json.loads(manifest_path.read_text())
    cohort_path=HERE/'sec-cohort.json'
    cohort=json.loads(cohort_path.read_text())
    if any(d.get('policy_sha256')!=POLICY_SHA for d in [audit,manifest,cohort]):
        raise ValueError('Policy mismatch')
    # The collector may be adding a new batch. Audit each included immutable
    # response hash instead of requiring the still-growing manifest bytes to stop.
    for ticker,source in audit['symbols'].items():
        if source['source_sha256']!=manifest['symbols'][ticker]['sha256']:
            raise ValueError('Action audit response differs from current manifest')
    evidence_path=HERE/'corporate-action-evidence.json'
    result=json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    if result and result.get('policy_sha256')!=POLICY_SHA:
        raise ValueError('Existing action evidence policy mismatch')
    overrides=result.setdefault('reviewed_action_overrides',{})
    mapping={i['cik']:[(i['seed_acceptance_eastern'][:10],i['historical_symbol'].upper().replace('.','-'))]
             for i in cohort['issuers']}
    sec_paths=[]; checkpoints=[]
    for filename in ['sec-events.json','sec-events-current-roster.json']:
        path=HERE/filename
        if not path.exists(): continue
        packet=json.loads(path.read_text())
        if packet.get('selection_sha256',sha(cohort_path))!=sha(cohort_path): continue
        checkpoints.append((packet.get('updated_at',''),path,packet))
    if checkpoints:
        # Match panel.build's choice; do not merge superseded parser checkpoints.
        _,path,packet=max(checkpoints,key=lambda x:x[0])
        sec_paths.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path)})
        # Only static security/filing metadata is used; no financial text is used.
        for slot in packet.get('slots',[]):
            if slot['cik'] not in mapping: continue
            for role in ['current','prior']:
                record=slot.get(role) or {}
                security=record.get('security') or {}
                if security.get('status')!='VERIFIED_SINGLE_COMMON_CLASS' or not record.get('acceptance_eastern'):
                    continue
                day=max(record['filing_date'],record['acceptance_eastern'][:10])
                ticker=security['historical_symbol'].upper().replace('.','-')
                mapping[slot['cik']].append((day,ticker))
    for cik in mapping:
        mapping[cik]=sorted(set(mapping[cik]))
    actions={k:v for k,v in result.get('actions',{}).items() if v.get('type')=='merger_cash'}
    unmatched=[]; conflicts=[]; observed=0
    for ticker,source in audit['symbols'].items():
        if ticker=='SPY': continue
        for day,record in source['actions'].items():
            if not '2019-10-01'<=day<='2023-12-29':
                raise ValueError('Action date outside frozen window')
            owners=[]
            for cik,entries in mapping.items():
                previous=[entry for entry in entries if entry[0]<day]
                if not previous: continue
                latest=max(d for d,_ in previous)
                tickers={t for d,t in previous if d==latest}
                if ticker in tickers:
                    if len(tickers)>1:
                        conflicts.append({'cik':cik,'date':day,'symbols':sorted(tickers)})
                    else: owners.append(cik)
            if len(owners)!=1:
                unmatched.append({'ticker':ticker,'date':day,'candidate_issuers':owners,
                                  'reason':'No unique contemporaneously mapped cohort common class'})
                continue
            security_id=owners[0]+':single_common'
            qualified=record['qualified'] is True and not source.get('provider_identity_ambiguous',False)
            for kind,field,identity in [('dividend','divCash',Decimal(0)),('split','splitFactor',Decimal(1))]:
                amount=Decimal(str(record[field]))
                if amount==identity: continue
                observed+=1
                key=security_id+':'+day+':'+kind
                manual=overrides.get(ticker+':'+day+':'+kind,{})
                proof={'security_id':security_id,'effective_date':day,'type':kind,
                    'source_ticker':ticker,'source_price_sha256':source['source_sha256'],
                    'source_qualification':{'path':str(audit_path.relative_to(ROOT)),'sha256':sha(audit_path),
                        'qualified':qualified,'issues':record.get('issues',[])},
                    'source_evidence':{'vendor_documentation':'https://www.tiingo.com/documentation/end-of-day',
                        'original_identity_cohort_sha256':sha(cohort_path)},
                    'source_timing_note':'Provider field is attributed to ex-date. No exact public announcement timestamp or broker cash credit is inferred.'}
                if kind=='dividend':
                    proof.update(amount_per_share=str(amount),cash_available_date=None,
                        cash_availability_verified=False,entitlement_source='VENDOR_ONLY_NO_INDEPENDENT_ISSUER_CORROBORATION',
                        verified=qualified and record['splitFactor']==1)
                    if record['splitFactor']!=1:
                        proof['unresolved_reason']='Simultaneous share factor requires separate entitlement-basis review'
                else:
                    proof.update(factor=str(amount),action_kind='UNKNOWN_DISTRIBUTION_KIND',verified=False,
                        unresolved_reason='Issuer or exchange source must establish delivered stock-unit ratio')
                if manual:
                    expected=manual.get('expected_provider_amount')
                    if expected is not None and Decimal(str(expected))!=amount:
                        raise ValueError('Reviewed provider action amount changed')
                    proof.update({k:v for k,v in manual.items() if k!='expected_provider_amount'})
                    proof['verified']=qualified and manual.get('verified') is True
                if not qualified:
                    proof['unresolved_reason']='Source identity/adjustment qualification failed: '+','.join(record.get('issues',[]))
                if key in actions:
                    raise ValueError('Two source records map to the same action')
                actions[key]=proof
    pending=list(manifest.get('pending_symbols',[]))
    requested_without_body=[t for t,s in manifest['symbols'].items() if 'path' not in s]
    cohort_not_yet_audited=sorted({i['historical_symbol'].upper().replace('.','-') for i in cohort['issuers']}
                                -set(audit['symbols']))
    result.update(policy_sha256=POLICY_SHA,updated_utc=datetime.now(timezone.utc).isoformat(),
        before_strategy_returns=True,actions=actions,
        scope='Action fields and static issuer/status sources only. Vendor-qualified cash entitlements remain locked; '
              'this is not a certification of payment, fills, overall price accuracy or complete inactive-security coverage.',
        listing_source_assumption='Original contemporaneous listing covers carry forward between explicitly evidenced status events; '
              'not daily independent corroboration. Known unknown/conflicting events fail closed.',
        inputs={'action_qualification_sha256':sha(audit_path),'audited_manifest_sha256':audit['price_manifest_sha256'],
                'manifest_snapshot_sha256':sha(manifest_path),'cohort_sha256':sha(cohort_path),'sec_metadata':sec_paths,
                'convention_sha256':sha(HERE/'corporate-action-convention.json'),
                'price_source_exceptions_sha256':sha(HERE/'price-source-exceptions.json')},
        inventory={'audited_symbols':len(audit['symbols']),'current_manifest_symbols':len(manifest['symbols']),
            'mapped_nonidentity_action_fields':observed,'verified_actions':sum(a['verified'] for a in actions.values()),
            'unverified_actions':sum(not a['verified'] for a in actions.values()),
            'unmapped_action_dates':unmatched,'conflicting_identity_dates':conflicts,
            'requested_without_body':requested_without_body,'collector_pending_symbols':pending,
            'cohort_symbols_not_yet_audited':cohort_not_yet_audited,
            'next_batch_pending':bool(pending or requested_without_body or cohort_not_yet_audited or
                                     len(audit['symbols'])<len(manifest['symbols']))})
    result.setdefault('security_status_events',[])
    evidence_path.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'sha256':sha(evidence_path),'inventory':result['inventory']},sort_keys=True))


if __name__=='__main__':
    refresh()
