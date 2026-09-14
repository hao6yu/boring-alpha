"""Independent checks of accepted facts against saved DOM and cached SEC API data.

Does not call the extraction parser, edit inputs, or inspect prices/returns.
Cached companyfacts agreement checks numerical transcription, not accounting scope.
"""
from collections import Counter
from decimal import Decimal
from lxml import html
from prepare import HERE, ROOT, RAW, load, write, sha
from process import available, intact


def main():
    intact()
    records = [r for r in load(HERE/'retrieval-manifest.json')['requests'] if r['status']=='COMPLETE']
    plan = {r['id']:r for r in load(HERE/'filing-plan.json')}
    documents = {}
    for r in records:
        assert sha(ROOT/r['file']) == r['sha256']
        tree = html.fromstring((ROOT/r['file']).read_text(), parser=html.HTMLParser(huge_tree=True))
        documents[r['accn']] = (tree, plan[r['id']])
    cached = {}
    cache_hashes = {}
    checked = set()
    stats = Counter()
    absent = []

    def verify_fact(f, cut):
        tree, meta = documents[f['accn']]
        assert f['url']==meta['url'] and f['filed']==meta['filed']
        assert available(f['filed'])<=cut
        nodes=tree.xpath('//*[@id=$id]', id=f['id'])
        assert len(nodes)==1
        node=nodes[0]
        assert node.get('name')==f['qualified_tag'] and node.get('contextref')==f['context']
        context=tree.xpath('//*[@id=$id]', id=f['context'])[0]
        vals={x.tag.split(':')[-1]:' '.join(x.itertext()).strip() for x in context.iter()}
        assert vals['identifier'].zfill(10)==meta['cik']
        assert vals.get('instant',vals.get('enddate'))==f['end']
        assert vals.get('startdate')==f['start']
        assert not any(x.tag in ('xbrldi:explicitmember','xbrldi:typedmember') for x in context.iter())
        unit=tree.xpath('//*[@id=$id]', id=node.get('unitref'))[0]
        measures=[(''.join(x.itertext())).strip() for x in unit.iter() if x.tag=='xbrli:measure']
        expected = ['iso4217:USD'] if f['unit']=='USD' else ['xbrli:shares'] if f['unit']=='shares' else ['iso4217:USD','xbrli:shares']
        assert measures==expected,(f['unit'],measures)
        raw=''.join(node.itertext()).replace(',','').replace(' ','').strip()
        if not any(c.isdigit() for c in raw):
            assert 'zero' in node.get('format','').lower() or 'numdash' in node.get('format','').lower()
            value=Decimal(0)
        else:value=Decimal(raw)
        value*=Decimal(10)**int(node.get('scale','0'))
        if node.get('sign')=='-':value=-value
        assert value==Decimal(str(f['val']))
        stats['fact_uses_checked']+=1
        identity=f['accn'],f['id']
        if identity in checked:return
        checked.add(identity)
        cik=meta['cik']
        if cik not in cached:
            paths=[ROOT/'data/snapshots/ml-stock-recent-validation-2026-09-14'/f'CIK{cik}-companyfacts-through-cutoff.json',
                   ROOT/'data/snapshots/ml-stock-comparison-2026-09-14'/f'CIK{cik}-companyfacts-pre2024.json']
            cached[cik]=[]
            for p in paths:
                if p.exists():
                    cached[cik].append(load(p));cache_hashes[str(p.relative_to(ROOT))]=sha(p)
        namespace,tag=f['qualified_tag'].split(':',1)
        apiunit='USD/shares' if expected==['iso4217:USD','xbrli:shares'] else f['unit']
        matches=[]
        for payload in cached[cik]:
            observations=payload.get('facts',{}).get(namespace,{}).get(tag,{}).get('units',{}).get(apiunit,[])
            matches.extend(x for x in observations if x['accn']==f['accn'] and x['end']==f['end'] and x.get('start')==f['start'])
        if matches:
            assert all(Decimal(str(x['val']))==value for x in matches),identity
            stats['unique_facts_with_matching_companyfacts']+=1
        else:
            stats['unique_facts_without_exact_companyfacts_record']+=1
            absent.append(dict(accn=f['accn'],tag=f['qualified_tag'],start=f['start'],end=f['end']))

    changes=load(RAW/'change-provenance.json')
    for row in changes:
        for kind,proof in row['proof'].items():
            if kind=='book':
                for f in proof['parts']+[proof['total']]:verify_fact(f,row['cut'])
                total=sum(Decimal(str(f['val']))*f['arithmetic_sign'] for f in proof['parts'])
                assert total==proof['sum_of_rounded_components']
                assert abs(total-proof['value'])<=Decimal(proof['rounding_allowance'])
                assert proof['value']==proof['total']['val']
            else:
                for part in proof['components']:
                    for f in [part['source'],part['shares'],part['eps']]:
                        if f:verify_fact(f,row['cut'])
                assert proof['value']==sum(p['value']*s for p,s in zip(proof['components'],[1,1,-1]))
            stats['changed_fields_checked']+=1
    out=dict(status='PASS',changed_company_dates=len(changes),unique_source_facts=len(checked),counts=dict(stats),
             exact_api_records_absent=absent,additional_cached_source_hashes=cache_hashes,
             limitation='Exact companyfacts matches verify numbers only. Missing API records do not invalidate original filing facts; accounting qualification remains subject to the failed fixture gate.')
    write(HERE/'provenance-verification.json',out)
    print({k:v for k,v in out.items() if k not in ('exact_api_records_absent','additional_cached_source_hashes')})


if __name__=='__main__':main()
