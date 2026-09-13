"""Audit new event index owners without loading prices or model outputs."""
import json
import re
from functools import lru_cache
import sec_collect as s

@lru_cache(maxsize=None)
def owners(filename):
    page=s.parser.HTML((s.ROOT/filename).read_text())
    return sorted({n.zfill(10) for href,label in page.links for n in re.findall(r'[?&]CIK=(\d+)',href,re.I)})

def main():
    cohort=json.loads((s.HERE/'sec-cohort.json').read_text())
    reviews=json.loads((s.HERE/'cohort-owner-reviews.json').read_text())
    verified=[];unresolved=[];joint=[]
    for issuer in cohort['issuers'][100:]:
        path=s.HERE/'sec-issuers'/(issuer['cik']+'.json')
        if not path.exists():continue
        block=json.loads(path.read_text());seen=set()
        for slot in block['slots']:
            for role in ('current','prior'):
                event=slot.get(role)
                if not event or event['accession'] in seen:continue
                seen.add(event['accession'])
                ids=owners(event['index_file'])
                rec={'cik':issuer['cik'],'seed_symbol':issuer['historical_symbol'],'accession':event['accession'],
                    'index_ciks':ids,'index_file':event['index_file'],'index_sha256':s.digest(s.ROOT/event['index_file']),
                    'primary_file':event['primary_file'],'symbol':event['security'].get('historical_symbol')}
                if ids==[issuer['cik']]:verified.append(rec)
                else:
                    text=s.parser.HTML((s.ROOT/event['primary_file']).read_text()).text
                    start=text.find('UNITED STATES')
                    rec['cover_excerpt']=text[max(0,start):max(0,start)+3700]
                    rec['item_202_excerpt']=event.get('item_202_excerpt','')[:1000]
                    rec['listing_rows']=event['security'].get('common_stock_evidence',[])
                    rec['known_seed_joint_parent']=reviews.get(issuer['cik'])
                    pld = (issuer['cik']=='0001045609' and ids==['0001045609','0001045610']
                        and any('Prologis, Inc.' in row['row_excerpt'] and row['symbols']==['PLD']
                                for row in rec['listing_rows']))
                    src = (issuer['cik']=='0001308606' and ids==['0001308606','0001703181']
                        and any('Spirit Realty Capital, Inc.' in row['row_excerpt'] and row['symbols']==['SRC']
                                for row in rec['listing_rows']))
                    frt = (issuer['cik']=='0000034903' and ids==['0000034903','0001901876']
                        and bool(re.search(r'Federal Realty Investment Trust Title.{0,150}Common Shares.{0,140}FRT New York Stock Exchange',text))
                        and bool(re.search(r'Federal Realty OP LP Title.{0,150}None N/A N/A',text)))
                    parent_proof=None
                    for cik,expected_ids,pattern in [
                        ('0001286043',['0001286043','0001636315'],r'Kite Realty Group Trust.{0,35}NYSE.{0,8}KRG'),
                        ('0001534504',['0001534504','0001566011','0001645026'],r'PBF Energy Inc\..{0,35}NYSE.{0,8}PBF')]:
                        if issuer['cik']==cik and ids==expected_ids:
                            parent_proof=re.search(pattern,event.get('release_excerpt',''),re.I)
                    if issuer['cik']=='0001534504' and ids==['0001534504','0001566011']:
                        parent_proof=re.search(r'PBF Energy Inc\..{0,35}NYSE.{0,8}PBF',event.get('release_excerpt',''),re.I)
                    rec['original_release_owner_excerpt']=parent_proof[0] if parent_proof else None
                    rec['owner_verified']=pld or src or frt or bool(parent_proof)
                    rec['owner_review']=('Original listing row explicitly assigns PLD common to Prologis, Inc.; L.P. separately lists debt.' if pld
                        else 'Original registrant column explicitly assigns SRC common to Spirit Realty Capital, Inc.; preferred SRC-A is separate and L.P. is a different registrant.' if src
                        else 'Original cover separates Investment Trust listing section with FRT common from OP LP section None/N/A. Original index explicitly maps Investment Trust to CIK34903 and OP LP to1901876.' if frt
                        else 'Original issuer-authored release explicitly pairs the parent company name with the listed common symbol; joint cover names its LP/LLC subsidiaries.' if parent_proof else None)
                    joint.append(rec)
                    if not rec['owner_verified']: unresolved.append(rec)
    result={'policy_sha256':s.POLICY_SHA,'cohort_sha256':s.digest(s.HERE/'sec-cohort.json'),
            'unique_index_owner_events':len(verified),'joint_or_conflicting_events':joint,
            'unresolved_owner_events':len(unresolved),
            'scope':'Original current/prior event index identity only; joint records require explicit parent review. No prices.'}
    s.atomic(s.HERE/'new-event-owner-audit.json',result)
    print(json.dumps({'unique_owner_events':len(verified),'joint_or_conflicting_events':len(joint),
        'joint_issuers':sorted({r['cik'] for r in joint})}))

if __name__=='__main__':main()
