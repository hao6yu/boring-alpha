#!/usr/bin/env python3
"""Dated symbols from original filing covers; no current-provider symbol lookup."""
import json
import sec_collect as s
from sec_apply_identity import apply as apply_identity
p=s.HERE;identity_path=p/'sec-identity-overrides.json';identity=json.loads(identity_path.read_text()) if identity_path.exists() else {'events':{}}
if identity_path.exists():assert identity['policy_sha256']==s.POLICY_SHA
roster=json.loads((p/'sec-selection.json').read_text());rows=[]
for issuer in roster['issuers']:
 f=p/'sec-issuers'/(issuer['cik']+'.json');by={}
 if f.exists():
  obj=json.loads(f.read_text());events={}
  for slot in obj['slots']:
   slot=apply_identity(slot,identity)
   for e in [slot.get('current'),slot.get('prior')]+slot.get('candidate_events',[]):
    if e and (e['accession'] not in events or e.get('identity_source_at_decision')):events[e['accession']]=e
  for e in events.values():
   security=e.get('security',{})
   if security.get('status')!='VERIFIED_SINGLE_COMMON_CLASS':continue
   symbol=security['historical_symbol'];source=e.get('identity_source_at_decision') or e.get('cohort_identity_source') or {'file':e.get('primary_file'),'url':e.get('primary_url')}
   if not source.get('file'):continue
   source={**source,'sha256':s.digest(s.ROOT/source['file'])}
   by.setdefault(symbol,[]).append({'accession':e['accession'],'filing_date':e['filing_date'],'acceptance_eastern':e.get('acceptance_eastern'),'listing_rows':security.get('common_stock_evidence',[]),'source':source})
 rows.append({'cik':issuer['cik'],'issuer_name_2019':issuer['issuer_name'],'seed_symbol':issuer['historical_symbol'],'original_cover_symbols':{k:sorted(v,key=lambda r:(r['filing_date'],r['accession'])) for k,v in sorted(by.items())},'source_status':'PARTIAL_COLLECTED_FRAME' if f.exists() else 'PENDING_FRAME'})
s.atomic(p/'sec-symbol-history.json',{'policy_sha256':s.POLICY_SHA,'selection_sha256':s.digest(p/'sec-selection.json'),'updated_at':s.now(),'issuers':rows,'scope':'Original filingcover evidence only. DifferentCIKs sharingtickerarenotlinked; laterpricegaps do not provealiascontinuity.'})
print(json.dumps({'issuers':len(rows),'with_cover_symbols':sum(bool(r['original_cover_symbols']) for r in rows),'changed_symbols':[{'cik':r['cik'],'seed':r['seed_symbol'],'symbols':list(r['original_cover_symbols'])} for r in rows if set(r['original_cover_symbols'])-{r['seed_symbol']}]}))
