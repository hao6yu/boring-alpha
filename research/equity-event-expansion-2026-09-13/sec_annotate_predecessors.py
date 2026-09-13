"""Offline fiscal-scope annotation; proximity alone never proves earnings precedence."""
from copy import deepcopy

def scopes(event):
    end=event.get('period_end');out=set()
    for row in event.get('period_candidates',[]) + ([event['period_evidence']] if event.get('period_evidence') else []):
        if row.get('period_end')==end:out.update(row.get('explicit_scopes',[]))
    return out.intersection({'quarter','year'})

def annotate(slot):
    s=deepcopy(slot)
    if not s.get('current'):return s
    current=s['current'];target=(s.get('prior_match') or {}).get('matched_scope')
    if target is None and len(scopes(current))==1:target=next(iter(scopes(current)))
    nearby=s.get('nearby_information_disclosures',s.get('information_predecessors',[]));matched=[];unresolved=[];different=[]
    for e in nearby:
        record=deepcopy(e)
        if not current.get('period_end') or not e.get('period_end') or target not in {'quarter','year'} or not scopes(e):
            status='UNRESOLVED_FISCAL_SCOPE';unresolved.append(record)
        elif e['period_end']!=current['period_end'] or target not in scopes(e):
            status='DIFFERENT_FISCAL_PERIOD_OR_SCOPE';different.append(record)
        else:
            status='VERIFIED_SAME_FISCAL_PERIOD_AND_SCOPE';matched.append(record)
        record['predecessor_match']={'status':status,'current_period_end':current.get('period_end'),'current_scope':target,'candidate_period_end':e.get('period_end'),'candidate_explicit_scopes':sorted(scopes(e))}
    s['nearby_information_disclosures']=matched+unresolved+different
    s['information_predecessors']=matched
    s['unresolved_predecessor_scope']=unresolved
    s['different_period_disclosures']=different
    s['known_preliminary_information']='KNOWN_YES' if any(e.get('classification')=='PRELIMINARY' for e in matched) else 'UNKNOWN'
    s['predecessor_coverage']={**s.get('predecessor_coverage',{}),'fiscal_scope_match_required':True,'scope_unresolved_count':len(unresolved),'same_scope_predecessors':len(matched),'different_scope_nearby_disclosures':len(different),'absence_verified':False}
    return s
