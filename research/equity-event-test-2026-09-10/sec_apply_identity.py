"""Validate original-cover identity overrides at the daily decision anchor, offline."""
from copy import deepcopy
from datetime import date
import sec_collect as s

def apply(slot,overrides):
    out=deepcopy(slot);event=out.get('current')
    if not event or event['accession'] not in overrides.get('events',{}):return out
    row=overrides['events'][event['accession']];proof=row['identity_source_at_decision'];anchor=event['daily_entry_anchor_index']
    assert event['daily_entry_invariant'] and row['original_release_cover_security']==event['security']
    assert event['security']['status']=='UNRESOLVED_COMMON_CLASS'
    assert row['security']['status']=='VERIFIED_SINGLE_COMMON_CLASS'
    assert proof['index_ciks']==[out['cik']] and proof['available_by_daily_anchor']==anchor
    assert max(proof['filing_date'],proof['acceptance_eastern_wallclock'][:10])<=anchor
    for key,hashkey in [('file','sha256'),('index_file','index_sha256')]:assert s.digest(s.ROOT/proof[key])==proof[hashkey]
    event['original_release_cover_security']=deepcopy(event['security']);event['security']=deepcopy(row['security']);event['identity_source_at_decision']=deepcopy(proof)
    out['historical_symbol']=event['security']['historical_symbol'];out['checks']['identity']=True
    out['unresolved_reasons']=[r for r in out['unresolved_reasons'] if r!='HISTORICAL_SECURITY_UNRESOLVED']
    out['status']='BASE_SEC_JOIN_READY_PENDING_PREDECESSOR_AUDIT' if all(out['checks'].values()) else 'SEC_JOIN_UNRESOLVED'
    return out
