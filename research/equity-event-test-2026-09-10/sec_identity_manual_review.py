#!/usr/bin/env python3
"""Three named original CLRB cover rows, offline; common stock is not its warrant."""
import json,re
import sec_collect as s
p=s.HERE;path=p/'sec-identity-overrides.json';before=path.read_bytes();prior_hash=s.sha(before)
backup=p/'sec-checkpoints'/('identity-before-CLRB-review-'+prior_hash+'.json')
if not backup.exists():backup.write_bytes(before)
out=json.loads(before);sources=json.loads((p/'sec-sources.json').read_text())['sources'];changes=[]
for event_acc,cover_acc in [('0001104659-20-057785','0001104659-20-057790'),('0001104659-20-123047','0001104659-20-122799'),('0001104659-21-030726','0001104659-21-030445')]:
 if event_acc in out['events']:continue
 target=out['unresolved'][event_acc]['target'];assert target['cik']=='0001279704'
 base=f'https://www.sec.gov/Archives/edgar/data/1279704/{cover_acc.replace("-","")}/';idx_url=base+cover_acc+'-index.html';ir=sources[idx_url]
 page=s.parser.HTML((s.ROOT/ir['file']).read_text());assert s.digest(s.ROOT/ir['file'])==ir['sha256']
 ids={x.zfill(10) for href,label in page.links for x in re.findall(r'[?&]CIK=(\d+)',href,re.I)};assert ids=={'0001279704'}
 acceptance=re.search(r'Accepted\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})',page.text);filing=re.search(r'Filing Date\s+(\d{4}-\d{2}-\d{2})',page.text);assert acceptance and filing
 assert max(acceptance[1],filing[1])<=target['anchor_date']
 pairs=[(u,r) for u,r in sources.items() if u.startswith(base) and not u.endswith('-index.html')];assert len(pairs)==1
 url,record=pairs[0];assert s.digest(s.ROOT/record['file'])==record['sha256'];text=s.parser.HTML((s.ROOT/record['file']).read_text()).text
 match=re.search(r'Common stock, par value \$0\.00001 Warrant to purchase common stock, expiring April 20, 2021 CLRB CLRBZ NASDAQ Capital Market NASDAQ Capital Market',text);assert match
 evidence={'row_excerpt':match[0],'class':'Common stock, par value $0.00001','symbol':'CLRB','exchange':'NASDAQ Capital Market','manual_column_pairing':'Two classnames, two symbols and two exchanges in originaltable order; secondsecurity CLRBZ is an expiringwarrant, not anothercommonclass.'}
 security={'status':'VERIFIED_SINGLE_COMMON_CLASS','historical_symbol':'CLRB','symbols':['CLRB'],'common_stock_evidence':[evidence],'excluded_common_unit_rows':[],'excluded_derivative_rows':[{'symbol':'CLRBZ','class':'Warrant to purchase common stock, expiring April20,2021'}]}
 proof={'accession':cover_acc,'filing_date':filing[1],'acceptance_eastern_wallclock':' '.join(acceptance.groups()),'available_by_daily_anchor':target['anchor_date'],'file':record['file'],'url':url,'sha256':record['sha256'],'index_file':ir['file'],'index_sha256':ir['sha256'],'index_ciks':['0001279704'],'source_excerpt':match[0],'scope':'Named originalsameCIK cover common/warrant columnpairing; oldercover availableatdailydecision, not earnings8-Kbody or proofnointerveningactions.'}
 out['events'][event_acc]={'security':security,'original_release_cover_security':target['original_security'],'identity_source_at_decision':proof,'manual_review':evidence,'automatic_unresolved_preserved':out['unresolved'].pop(event_acc)}
 changes.append({'event_accession':event_acc,'cover_accession':cover_acc,'source_sha256':record['sha256']})
out['updated_at']=s.now();s.atomic(path,out);s.atomic(p/'sec-identity-manual-review.json',{'policy_sha256':s.POLICY_SHA,'before_sha256':prior_hash,'before_file':str(backup.relative_to(s.ROOT)),'after_sha256':s.digest(path),'network_requests':0,'changes':changes});print(json.dumps({'verified':len(out['events']),'unresolved':len(out['unresolved']),'manual_rows':len(changes)}))
