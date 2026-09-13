#!/usr/bin/env python3
"""Narrow original-cover recovery after the main source pass, same SEC ledger/bounds."""
import argparse,fcntl,json,re
from datetime import datetime
import sec_collect as s

def build_plan():
 p=s.HERE;roster=json.loads((p/'sec-selection.json').read_text());targets={}
 for issuer in roster['issuers']:
  f=p/'sec-issuers'/(issuer['cik']+'.json')
  if not f.exists():continue
  for slot in json.loads(f.read_text())['slots']:
   current=slot.get('current')
   if current and current.get('security',{}).get('status')=='UNRESOLVED_COMMON_CLASS':
    key=current['accession'];anchor=current.get('daily_entry_anchor_index')
    if anchor and current.get('daily_entry_invariant'):
     targets[key]={'cik':issuer['cik'],'accession':key,'anchor_date':anchor,'slot_id':slot['slot_id'],'original_security':current['security'],'release_opening':current.get('release_excerpt','')[:1800]}
 return {'policy_sha256':s.POLICY_SHA,'selection_sha256':s.digest(p/'sec-selection.json'),'targets':list(targets.values()),'rule':'Original10-Q/10-K cover filed and accepted no later than the current daily decision anchor. Single indexregistrant must matchCIK; preserve original8-Kcover and exactprice-independent timing. No newprice/return access.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');args=ap.parse_args();p=s.HERE
 plan=build_plan();s.atomic(p/'sec-identity-repair-plan.json',plan)
 if not args.acquire:print(json.dumps({'targets':len(plan['targets']),'mode':'OFFLINE_PLAN_ONLY'}));return
 lock=(p/'sec-collector.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 fetcher=s.Fetcher();client=s.Client(fetcher);outpath=p/'sec-identity-overrides.json'
 out=json.loads(outpath.read_text()) if outpath.exists() else {'policy_sha256':s.POLICY_SHA,'events':{},'unresolved':{}}
 assert out['policy_sha256']==s.POLICY_SHA
 frames={}
 try:
  for target in plan['targets']:
   acc=target['accession'];cik=target['cik'];anchor=target['anchor_date']
   if acc in out['events']:continue
   try:
    if re.search(r'\bOTCQ[XB]?\b|\bOTC[ -]?(?:Markets|Pink)\b',target['release_opening'],re.I):
     out['unresolved'][acc]={'target':target,'reason':'CURRENT_RELEASE_INDICATES_OTC'};s.atomic(outpath,out);continue
    if cik not in frames:frames[cik]=client.submissions(cik,'2019-01-01','2023-12-31',('10-Q','10-K'))
    candidates=[r for r in frames[cik] if r['filingDate']<=anchor]
    reasons=[];found=None
    for row in reversed(candidates[-2:]):
     coveracc=row['accessionNumber'];base=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{coveracc.replace("-","")}/'
     ib,ip=client.get(base+coveracc+'-index.html');idx=s.parser.HTML(ib.decode('utf8','replace'))
     ids={n.zfill(10) for href,label in idx.links for n in re.findall(r'[?&]CIK=(\d+)',href,re.I)}
     accepted=re.search(r'Accepted\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})',idx.text)
     if ids!={cik} or not accepted or max(row['filingDate'],accepted[1])>anchor:
      reasons.append({'accession':coveracc,'reason':'JOINT_OWNER_OR_TIMING_NOT_VERIFIED'});continue
     b,f=client.get(base+row['primaryDocument']);security=s.common_identity(s.parser.HTML(b.decode('utf8','replace')))
     if security['status']!='VERIFIED_SINGLE_COMMON_CLASS':
      reasons.append({'accession':coveracc,'reason':security['status']});continue
     named_symbols=set(re.findall(r'(?:NASDAQ|NYSE(?:\s+American)?)\s*:\s*([A-Z][A-Z0-9.-]{0,9})',target['release_opening'],re.I))
     if named_symbols and security['historical_symbol'] not in {v.upper() for v in named_symbols}:
      reasons.append({'accession':coveracc,'reason':'CURRENT_RELEASE_SYMBOL_DISAGREES_WITH_OLDER_COVER'});continue
     found={'security':security,'original_release_cover_security':target['original_security'],'identity_source_at_decision':{'accession':coveracc,'filing_date':row['filingDate'],'acceptance_eastern_wallclock':' '.join(accepted.groups()),'available_by_daily_anchor':anchor,'file':f,'url':base+row['primaryDocument'],'sha256':s.sha(b),'index_file':ip,'index_sha256':s.sha(ib),'index_ciks':sorted(ids),'scope':'Original sameCIK cover available before dailydecision; not relabeled as originalearnings8-Kbody.'}}
     break
    if found:out['events'][acc]=found
    else:out['unresolved'][acc]={'target':target,'attempted_covers':reasons}
   except s.StopCollection:raise
   except Exception as exc:out['unresolved'][acc]={'target':target,'error':type(exc).__name__}
   out['updated_at']=s.now();s.atomic(outpath,out);fetcher.flush()
 finally:fetcher.flush()
 print(json.dumps({'targets':len(plan['targets']),'verified':len(out['events']),'unresolved':len(out['unresolved']),'requests':len(fetcher.attempts)}))
if __name__=='__main__':main()
