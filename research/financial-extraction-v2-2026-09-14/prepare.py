"""Freeze a coverage-selected filing plan without inspecting return labels."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RAW=ROOT/'data/snapshots'/HERE.name
OLD=ROOT/'research/ml-stock-comparison-2026-09-14'
RECENT=ROOT/'research/ml-stock-recent-validation-2026-09-14'
AUDIT=ROOT/'research/financial-input-audit-2026-09-14'

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')

def main():
    assert not (HERE/'protocol.json').exists(),'Preserve the frozen plan.'
    RAW.mkdir(parents=True,exist_ok=True)
    baseline={}
    for folder in [OLD,RECENT,AUDIT]:
        for p in folder.iterdir():
            if p.is_file():baseline[str(p.relative_to(ROOT))]=sha(p)
    source={};rows=[];jobs={};submissions={}
    for folder in [OLD,RECENT]:
        path=ROOT/'data/snapshots'/folder.name/'monthly-fundamentals.json'
        source[str(path.relative_to(ROOT))]=sha(path)
        rows.extend(r for r in load(path) if '2022-01'<=r['month']<='2026-09')
        manifest=folder/'submissions-manifest.json'
        for cik,rec in (load(manifest).items() if manifest.exists() else []):
            if rec.get('file'):
                p=ROOT/rec['file'];source[rec['file']]=sha(p)
                submissions[cik]=load(p)['filings']['recent']
    def add(cik,accn):
        key=(cik,accn)
        if key in jobs:return key
        sub=submissions.get(cik,{})
        if accn not in sub.get('accessionNumber',[]):return None
        i=sub['accessionNumber'].index(accn)
        jobs[key]=dict(cik=cik,accn=accn,filed=sub['filingDate'][i],
            report_end=sub['reportDate'][i],form=sub['form'][i],
            url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace("-", "")}/{sub["primaryDocument"][i]}',
            supports=[])
        return key
    for r in rows:
        if not r['filing_eligible'] or not r['assets']:continue
        cik=r.get('source_cik',r['cik'])
        current=add(cik,r['assets']['accn'])
        if current and r['common_equity'] is None:
            jobs[current]['supports'].append([r['symbol'],r['month'],'book'])
        if r['common_income_ttm'] is None and r['net_income_ttm']:
            for p in r['net_income_ttm']['components']:
                k=add(cik,p['accn'])
                if k:jobs[k]['supports'].append([r['symbol'],r['month'],'income'])
    fixtures=load(AUDIT/'reviewed-evidence.json')['rows']
    selected=[]
    for r in fixtures:
        for accn in [r['current']['accn']]+([p['accn'] for p in r['income']['parts']] if r['income'] else []):
            key=add(r['cik'],accn)
            if key not in selected:selected.append(key)
    required_fixture_docs=len(selected)
    # Remaining docs: one pass in original issuer order, highest missing-field
    # support count first within an issuer; repeat rounds until the fixed cap.
    cohort=load(OLD/'identity-candidates.json')['rows'][:100]
    order=[c['cik'] for c in cohort]
    remaining=defaultdict(list)
    for key,j in jobs.items():
        if key not in selected and j['supports']:
            remaining[key[0]].append(key)
    for cik in remaining:
        remaining[cik].sort(key=lambda k:(-len(set(tuple(x) for x in jobs[k]['supports'])),jobs[k]['filed'],k))
    while len(selected)<90:
        changed=False
        for cik in order+sorted(set(remaining)-set(order)):
            if remaining[cik] and len(selected)<90:
                selected.append(remaining[cik].pop(0));changed=True
        if not changed:break
    plan=[]
    for i,k in enumerate(selected):
        rec=jobs[k];rec.update(id=i+1,fixture=(i<required_fixture_docs))
        rec['supports']=sorted(set(tuple(x) for x in rec['supports']))
        plan.append(rec)
    write(HERE/'filing-plan.json',plan)
    write(HERE/'protocol.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),
        status='FROZEN_BEFORE_NEW_PARSER_AND_REVISED_RETURN_INSPECTION',
        target_months=['2022-01','2026-09'],company_month_slots=len(rows),cohort_size=100,
        max_original_filing_retrievals=90,new_paid_data_usd=0,one_implementation_pass=True,
        baseline_files=baseline,source_files=source,filing_plan_sha256=sha(HERE/'filing-plan.json'),
        selection='Fixture documents first, then original-issuer round robin; within issuer choose greatest missing-field support, ties by earlier filing date. No returns used.',
        gate=['Generic rules must reproduce all 28 audited recoveries without issuer-specific code or manually supplied production values.',
              'All 5700 company-month slots must be processed; preserve non-target inputs and unqualified missing values.',
              'Every changed value must reconcile with exact filing, period, ownership scope and two-session availability.',
              'If the 90-document limit or extensive manual certification prevents general extraction, stop with coverage and remaining work; do not run a partial-sample profitability test.'],
        evaluation='Only after data gate: one unchanged-score comparison, both declared date windows and all prior corporate-action/cost scenarios; no training or tuning.'))
    write(HERE/'retrieval-manifest.json',dict(requests=[],max_requests=90))
    print(json.dumps(dict(slots=len(rows),candidate_filings=len(jobs),planned=len(plan),fixture_documents=required_fixture_docs,issuer_count=len(set(x['cik'] for x in plan)))))

if __name__=='__main__':main()
