#!/usr/bin/env python3
"""Offline original index-CIK and listed-class ownership review."""
import json,re
import sec_collect as s
p=s.HERE;selection=json.loads((p/'sec-selection.json').read_text());rows=[]
manual={
 '0001562401':('American Homes 4 Rent','AMH','JointcovernamesMarylandAmericanHomes4Rent andDelawareLP separately. Originalrelease explicitly AmericanHomes4Rent(NYSE:AMH); coverlistsClassAcommonshares; LP operatinginterest is separate.'),
 '0000065984':('Entergy Corporation','ETR','JointcoverlistingrowexplicitlyassignsETRcommonstocktoEntergyCorporation, the selectedparentCIK.'),
 '0001733998':('Northwest Natural Holding Company','NWN','JointcoverlistingrowexplicitlyassignsNWNcommonstocktoNorthwestNaturalHoldingCompany, the selectedparentCIK.')}
for r in selection['screened']:
 if r['decision']!='SELECTED':continue
 e=r['selected_event'];index=s.ROOT/e['index_file'];page=s.parser.HTML(index.read_text());ids=sorted(set(x.zfill(10) for h,label in page.links for x in re.findall(r'[?&]CIK=(\d+)',h,re.I)))
 rec={'cik':r['cik'],'seed_rank':r['seed_rank'],'issuer_name':r['issuer_name'],'historical_symbol':e['security']['historical_symbol'],'index_ciks':ids,'index_file':e['index_file'],'index_sha256':s.digest(index),'listing_rows':e['security']['common_stock_evidence']}
 if len(ids)==1 and ids[0]==r['cik']:
  rec.update(status='SINGLE_INDEX_REGISTRANT_AND_LISTED_COMMON_COVER',verified=True)
 elif r['cik'] in manual and r['cik'] in ids:
  owner,symbol,note=manual[r['cik']];proof=' '.join(x['row_excerpt'] for x in e['security']['common_stock_evidence'])
  if r['cik']=='0001562401':
   release=s.parser.HTML((s.ROOT/e['exhibit_file']).read_text()).text
   match=re.search(r'American Homes 4 Rent\s*\(NYSE:\s*AMH\)',release)
   okay=bool(match);rec['release_owner_excerpt']=match[0] if match else None
   rec['release_file']=e['exhibit_file'];rec['release_sha256']=s.digest(s.ROOT/e['exhibit_file'])
  else:okay=owner in proof
  rec.update(status='SOURCE_REVIEWED_JOINT_REGISTRANT_OWNER',verified=okay and symbol==e['security']['historical_symbol'],listed_owner=owner,reason=note)
 else:rec.update(status='UNRESOLVED_JOINT_OWNER',verified=False)
 rows.append(rec)
result={'policy_sha256':s.POLICY_SHA,'selection_sha256':s.digest(p/'sec-selection.json'),'status':'PASS' if len(rows)==100 and all(r['verified'] for r in rows) else 'FAIL','selected_count':len(rows),'source_reviewed_joint_cases':len([r for r in rows if r['status']=='SOURCE_REVIEWED_JOINT_REGISTRANT_OWNER']),'rows':rows,'correction_record':{'file':'sec-parent-identity-correction.json','sha256':s.digest(p/'sec-parent-identity-correction.json')},'scope':'Original2019cohortownership only. Eachlaterdecisionstillrequiresdatedsecurityidentity; thisdoesnotcertifyeventcoverage.'}
s.atomic(p/'sec-cohort-ownership-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
