"""Validate source-linked accounting changes before any strategy evaluation."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
V2=HERE.parent/'financial-extraction-v2-2026-09-14'
RAW=ROOT/'data/snapshots'/HERE.name
sys.path.insert(0,str(V2))
from process import recover, available
from extract_v3 import Filing, linked_policy


def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def intact():
    for name,digest in load(HERE/'protocol.json')['prior_files'].items():
        assert sha(ROOT/name)==digest,name


def documents():
    plan={r['id']:r for r in load(V2/'filing-plan.json')}
    objects=[];records={}
    for r in load(V2/'retrieval-manifest.json')['requests']:
        if r['status']!='COMPLETE':continue
        assert sha(ROOT/r['file'])==r['sha256']
        markup=(ROOT/r['file']).read_text()
        assert len(markup)==r['document_characters']
        f=Filing(markup,plan[r['id']]);objects.append(f);records[f.meta['accn']]=r
    results={}
    for f in objects:
        f.policy_evidence=linked_policy(f,objects)
        out=f.extract();record=records[f.meta['accn']]
        out.update(source_file=record['file'],source_sha256=record['sha256'])
        results[f.meta['cik'],f.meta['accn']]=out
    return objects,results


def original_rows():
    rows=[]
    for name in ('ml-stock-comparison-2026-09-14','ml-stock-recent-validation-2026-09-14'):
        rows.extend(r for r in load(ROOT/'data/snapshots'/name/'monthly-fundamentals.json')
                    if '2022-01'<=r['month']<='2026-09')
    return rows


def main():
    intact();RAW.mkdir(parents=True,exist_ok=True)
    objects,docs=documents();old=original_rows();after=[];changes=[];why=Counter();by_issuer=defaultdict(Counter)
    assert len(old)==5700 and len({(r['symbol'],r['month']) for r in old})==5700
    for row in old:
        new,proof,reasons=recover(row,docs)
        assert {k:v for k,v in row.items() if k not in ('common_equity','common_income_ttm')}=={
            k:v for k,v in new.items() if k not in ('common_equity','common_income_ttm')}
        for field in ('common_equity','common_income_ttm'):
            if row[field] is not None:assert new[field]==row[field]
        for part in proof.get('income',{}).get('components',[]):
            policy=part.get('policy_evidence')
            if policy:assert available(policy['filed'])<=row['cut']
        after.append(new);why.update(reasons)
        if proof:
            changes.append(dict(symbol=row['symbol'],month=row['month'],cut=row['cut'],proof=proof))
            for k in proof:by_issuer[row['symbol']][k]+=1
    before_map={(r['symbol'],r['month']):r for r in old};after_map={(r['symbol'],r['month']):r for r in after}
    fixtures=[]
    for row in load(HERE.parent/'financial-input-audit-2026-09-14/audit-results.json')['rows']:
        key=row['symbol'],row['month']
        for field,short in [('common_equity','common_equity'),('common_income_ttm','common_income')]:
            if before_map[key][field] is not None:continue
            original_target=row[short+'_after'];expected=original_target
            # Evaluation target correction is isolated from production rules.
            # This reported total was identified and documented in the prior run.
            correction=None
            if key==('WHR','2026-01') and field=='common_equity':
                expected=2380000000;correction='Reported parent equity replaces the sum of rounded components; prior ERRATA.md.'
            actual=after_map[key][field]
            if isinstance(actual,dict):actual=actual['value']
            fixtures.append(dict(symbol=key[0],month=key[1],field=field,original_target=original_target,
                                 expected=expected,actual=actual,correction=correction,passed=expected==actual))
    counts={k:dict(before=sum(r[k] is not None for r in old),after=sum(r[k] is not None for r in after))
            for k in ('common_equity','common_income_ttm')}
    write(RAW/'extracted-documents.json',list(docs.values()))
    write(RAW/'revised-monthly-fundamentals.json',after)
    write(RAW/'change-provenance.json',changes)
    write(HERE/'coverage.json',dict(slots=5700,counts=counts,changed_company_dates=len(changes),
        by_issuer={k:dict(v) for k,v in sorted(by_issuer.items())},changed_issuers=len(by_issuer),
        unresolved_reasons=dict(why),fixture_results=fixtures,fixtures_passed=sum(f['passed'] for f in fixtures),
        fixture_targets=len(fixtures),data_gate_passed=all(f['passed'] for f in fixtures),
        documents=len(docs),new_network_requests=0,new_paid_data_usd=0,new_model_fits=0,profitability_runs=0,
        revised_payload_sha256=sha(RAW/'revised-monthly-fundamentals.json')))
    write(HERE/'extraction-freeze.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),
        status='FROZEN_BEFORE_ANY_REVISED_RETURN_INSPECTION',files={str(p.relative_to(ROOT)):sha(p)
            for p in [HERE/'protocol.json',HERE/'extract_v3.py',HERE/'replay.py',HERE/'coverage.json',
                      RAW/'revised-monthly-fundamentals.json',RAW/'change-provenance.json']}))
    intact()
    print(json.dumps(dict(counts=counts,fixtures_passed=sum(f['passed'] for f in fixtures),
                         failures=[f for f in fixtures if not f['passed']]),indent=2))


if __name__=='__main__':main()
