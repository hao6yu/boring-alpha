"""Verify inherited selection and new original-cover ownership without prices."""
import json
import re
import sec_collect as s

def main():
    source=s.HERE/'sec-selection.json'
    raw=source.read_bytes(); selection=json.loads(raw)
    oldpath=s.HERE.parent/'equity-event-test-2026-09-10/sec-selection.json'
    original=json.loads(oldpath.read_text())
    ranked=json.loads((s.HERE/'sec-ranked-seed.json').read_text())
    assert selection['issuers'][:100]==original['issuers']
    assert selection['screened'][:155]==original['screened']
    assert len({r['cik'] for r in selection['issuers']})==len(selection['issuers'])
    assert [r['seed_rank'] for r in selection['screened']]==list(range(1,len(selection['screened'])+1))
    for row in selection['screened']:
        expected=ranked['rows'][row['seed_rank']-1]
        assert row['cik']==expected['cik'] and row['rank_digest']==expected['rank_digest']
    manual_path=s.HERE/'cohort-owner-reviews.json'
    manual=json.loads(manual_path.read_text()) if manual_path.exists() else {}
    rows=[]
    for row in selection['screened'][155:]:
        if row['decision']!='SELECTED':continue
        event=row['selected_event']; index=s.ROOT/event['index_file']
        page=s.parser.HTML(index.read_text())
        ciks=sorted({n.zfill(10) for href,label in page.links for n in re.findall(r'[?&]CIK=(\d+)',href,re.I)})
        record={'cik':row['cik'],'issuer_name':row['issuer_name'],'seed_rank':row['seed_rank'],
            'symbol':event['security']['historical_symbol'],'index_ciks':ciks,
            'index_file':event['index_file'],'index_sha256':s.digest(index),
            'listing_rows':event['security']['common_stock_evidence'],
            'verified':ciks==[row['cik']]}
        if not record['verified'] and row['cik'] in manual:
            review=manual[row['cik']]
            assert review['index_sha256']==record['index_sha256']
            assert review['listed_symbol']==record['symbol']
            for proof in review['sources']:
                assert s.digest(s.ROOT/proof['file'])==proof['sha256']
            record.update(verified=review['verified'] is True,manual_review=review)
        rows.append(record)
    out={'policy_sha256':s.POLICY_SHA,'selection_sha256':s.sha(raw),
        'inherited_100_issuers_exactly_preserved':True,'inherited_155_rank_decisions_exactly_preserved':True,
        'original_selection_sha256':s.digest(oldpath),'rank_order_verified':True,
        'new_selected_issuers':len(rows),'new_verified_owners':sum(r['verified'] for r in rows),
        'unresolved_owners':[r for r in rows if not r['verified']],
        'complete':selection['selection_status']=='COMPLETE_200',
        'passed':selection['selection_status']=='COMPLETE_200' and all(r['verified'] for r in rows),
        'rows':rows,'scope':'Original company rank and cover ownership only; no price or return access.'}
    s.atomic(s.HERE/'cohort-prefix-audit.json',out)
    print(json.dumps({k:v for k,v in out.items() if k!='rows'}))

if __name__=='__main__':main()
