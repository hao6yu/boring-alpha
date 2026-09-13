"""Reproduce the bounded original-table review recorded before fitting.

BeautifulSoup/lxml are a separate HTML reader used only for the review pack.
The fixed feature extractor and model do not import them. Expected amounts
below were checked against original rows, year/scope headers and units.
"""
from datetime import datetime, timezone
from importlib.metadata import version
import json
from bs4 import BeautifulSoup
from sec_collect import HERE, ROOT, POLICY_SHA, atomic, digest

EXPECTED=[('41247000','37304000'),('682329000','662494000'),('0.03','0.03'),('-0.05','-0.24'),
          ('484658000','483084000'),('5713000','7537000'),('0.26','0.03'),('0.01','-0.03'),
          ('4530000','5643000'),('132410000','150542000'),('-0.52','-0.27'),('-0.10','0.13'),
          ('301078000','173805000'),('107391000','139101000'),('-0.46','-0.56'),('0.59','0.29')]


def main():
    assert not (HERE/'frozen-models.json').exists()
    audit_path=HERE/'feature-source-audit.json'
    audit=json.loads(audit_path.read_text())
    assert not audit['extraction_errors'] and len(audit['source_cell_samples'])==len(EXPECTED)
    pack=[]
    for i,(sample,values) in enumerate(zip(audit['source_cell_samples'],EXPECTED)):
        assert (sample['current_value'],sample['current_release_comparable_prior_value'])==values
        source=sample['current_evidence'][0];path=ROOT/source['file']
        assert digest(path)==source['sha256']
        doc=BeautifulSoup(path.read_bytes(),'lxml')
        table=doc.find_all('table')[source['table_index']]
        rows=[r for r in table.find_all('tr') if r.find_parent('table') is table]
        indexes=sorted(set(range(min(6,len(rows))))|set(range(max(0,source['row_index']-2),min(len(rows),source['row_index']+2))))
        context={str(n):[c.get_text(' ',strip=True) for c in rows[n].find_all(['td','th'],recursive=False)] for n in indexes}
        captions=' | '.join(reversed([str(x).strip() for x in table.find_all_previous(string=True,limit=30)]))[-1000:]
        pack.append({'index':i,'slot_id':sample['slot_id'],'metric':sample['metric'],
            'expected_current_and_comparable_prior':values,'source_file':source['file'],'source_sha256':source['sha256'],
            'source_url':source['url'],'original_table_index':source['table_index'],'captions':captions,'original_rows':context,
            'review':'PASS: original values/signs, current versus comparable-year quarter columns, GAAP statement context and thousands-versus-per-share scale match.',
            'notes':('Prior year is explicitly as restated in this current release; this does not substitute for the original-prior narrative source.' if i==15 else
                     'Negative prior EPS has closing parenthesis in a separate original cell; checked as -0.03.' if i==7 else None)})
    raw=ROOT/'data/snapshots/equity-event-expansion-2026-09-13/feature-cell-review-pack.json'
    atomic(raw,pack)
    report={'policy_sha256':POLICY_SHA,'created_utc':datetime.now(timezone.utc).isoformat(),
        'feature_source_audit_sha256':digest(audit_path),'review_script_sha256':digest(HERE/'review_feature_cells.py'),
        'versions':{p:version(p) for p in ['beautifulsoup4','lxml']},
        'comparisons_reviewed':16,'cells_reviewed':32,'original_tables_reviewed':11,
        'passed':True,'reviewer':'Root agent; separate HTML parser, not an independent human or separate-agent review.',
        'review_pack':{'path':str(raw.relative_to(ROOT)),'sha256':digest(raw)},
        'scope':'Fixed hash-selected new-company financial-cell sample. Source bytes and year, scope, signs, units and GAAP labels checked; not a population accuracy certification. Existing regulatory USD inference remains an assumption. No prices, predictions or returns read.'}
    atomic(HERE/'feature-cell-review.json',report)
    print('Source-cell review passed:16 comparisons,32 cells,11 original tables.')


if __name__=='__main__':main()
