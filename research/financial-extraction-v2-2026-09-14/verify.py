"""Independent arithmetic, temporal and adversarial extraction checks."""
from copy import deepcopy
from decimal import Decimal
from lxml import html
import json
import re
from prepare import HERE,ROOT,RAW,AUDIT,load,write,sha
from extract import Filing
from process import available,lookup,recover,intact


def main():
    intact()
    freeze=load(HERE/'parser-freeze.json')
    for name,digest in freeze['files'].items():assert sha(HERE/name)==digest,name
    plan={j['id']:j for j in load(HERE/'filing-plan.json')}
    records={r['id']:r for r in load(HERE/'retrieval-manifest.json')['requests'] if r['status']=='COMPLETE'}
    checks=[]
    def source(i):return (ROOT/records[i]['file']).read_text()
    def parse(i,markup=None):return Filing(source(i) if markup is None else markup,plan[i]).extract()
    def mutate(i,fn):
        d=html.fromstring(source(i),parser=html.HTMLParser(huge_tree=True));fn(d)
        return parse(i,html.tostring(d,encoding='unicode'))
    def fact(d,tag,context=None):
        return [f for f in d.xpath('//*[@contextref]') if f.get('name','').endswith(':'+tag)
                and (context is None or f.get('contextref')==context)]
    # Exact independent figures from source filings, not fixture-production inputs.
    assert parse(1)['book']['2023-09-30']['value']==3040900000
    assert parse(33)['book']['2023-09-30']['value']==1874107000
    assert parse(26)['book']['2025-09-30']['value']==-4932000000
    checks.append('ordinary equity, deferred compensation and negative book reproduced')
    # Prefer directly reported parent total when independently rounded components differ.
    whr=parse(15)['book']['2025-09-30']
    assert whr['value']==2380000000 and whr['sum_of_rounded_components']==2381000000
    checks.append('rounded equity uses the reported parent total and records discrepancy')
    def remove_deferred(d):
        for f in d.xpath('//*[@contextref]'):
            if f.get('name','').endswith(':CompensationAndBenefitsTrust') and f.get('unitref'):
                f.getparent().remove(f)
    out=mutate(33,remove_deferred)
    assert '2023-09-30' not in out['book']
    checks.append('omitted deferred compensation fails full equity reconciliation')
    def wrong_currency(d):
        for e in d.iter():
            if e.tag=='xbrli:measure' and (e.text or '').endswith(':USD'):e.text='iso4217:CAD'
    assert not mutate(1,wrong_currency)['book']
    checks.append('non-USD balances cannot fill USD equity')
    def nci_dimension(d):
        for e in d.iter():
            if e.tag=='xbrli:context':
                dim=html.Element('xbrldi:explicitmember',dimension='us-gaap:StatementEquityComponentsAxis')
                dim.text='us-gaap:NoncontrollingInterestMember';e.append(dim)
    assert not mutate(1,nci_dimension)['book']
    checks.append('dimensional noncontrolling balances are excluded')
    def corrupt_total(d):
        for f in fact(d,'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest','c-2'):
            f.text='9,040.9'
    assert '2023-09-30' not in mutate(1,corrupt_total)['book']
    checks.append('material equity mismatch rejected beyond rounding bounds')
    try:parse(1,source(1)[:200000]+'[Truncated]')
    except ValueError:checks.append('truncated document rejected')
    else:raise AssertionError('truncated document accepted')
    # PNR's original EPS table supports parent common earnings without a ticker rule.
    doc=parse(1);period='2023-01-01|2023-09-30'
    assert doc['income'][period]['value']==414700000
    def corrupt_income(d):
        for f in fact(d,'NetIncomeLoss','c-1'):f.text='914.7'
    assert period not in mutate(1,corrupt_income)['income']
    checks.append('basic EPS arithmetic rejects a substituted numerator')
    # The prototype deliberately abstains on unresolved participating claims.
    assert not parse(18)['income']
    checks.append('participating-security scope requires explicit additional handling')
    def remove_preferred_issuance(d):
        for e in d.iter():
            if e.text:e.text=re.sub(r'no\s+shares\s+issued','issuance not specified',e.text,flags=re.I)
            if e.tail:e.tail=re.sub(r'no\s+shares\s+issued','issuance not specified',e.tail,flags=re.I)
        for f in fact(d,'PreferredStockSharesIssued')+fact(d,'PreferredStockSharesOutstanding'):
            f.getparent().remove(f)
    assert not mutate(34,remove_preferred_issuance)['book']
    checks.append('zero preferred par value alone is not zero issued shares')
    assert available('2023-11-03')=='2023-11-07' and available('2023-05-25')=='2023-05-30'
    checks.append('filing lag respects weekends and exchange holidays')
    docs={(plan[1]['cik'],plan[1]['accn']):doc}
    assert lookup(docs,plan[1]['cik'],plan[1]['accn'],'2023-10-25') is None
    assert lookup(docs,plan[1]['cik'],plan[1]['accn'],'2023-10-26') is not None
    checks.append('future or insufficiently delayed filings cannot repair historical inputs')
    base=next(r for r in load(ROOT/'data/snapshots/ml-stock-recent-validation-2026-09-14/monthly-fundamentals.json')
              if r['symbol']=='PNR' and r['month']=='2024-01')
    after,proof,reasons=recover(base,docs)
    assert after['common_equity']==3040900000 and after['common_income_ttm'] is None
    checks.append('one quarterly document cannot fill a trailing annual earnings input')
    coverage=load(HERE/'coverage.json');revised=load(RAW/'revised-monthly-fundamentals.json')
    assert len(revised)==5700 and len({(r['symbol'],r['month']) for r in revised})==5700
    assert len({r['symbol'] for r in revised})==100
    checks.append('all 5700 slots and 100 original issuer identities retained')
    # The historical parser is intentionally unable to override its failed data gate.
    assert coverage['data_gate_passed']==all(r['passed'] for r in coverage['fixture_results'])
    checks.append('data gate reflects every original fixture, including discrepancies')
    manifest=load(HERE/'retrieval-manifest.json')
    assert max(r['navigation_attempt'] for r in manifest['requests'])<=90
    assert manifest['navigation_attempts']==60 and manifest['unused_navigation_budget']==30
    assert manifest['complete_documents']==len(records)==52
    attempts={r['navigation_attempt'] for r in manifest['requests']}
    attempts.add(manifest['uncaptured_navigation']['navigation_attempt'])
    assert attempts==set(range(1,61))
    for r in manifest['requests']:
        assert sha(ROOT/r['file'])==r['sha256']
    checks.append('retrieval budget and complete/partial source hashes verified')
    out=dict(status='PASS',count=len(checks),checks=checks,fixture_gate_passed=coverage['data_gate_passed'],
        note='Passing defensive checks is distinct from passing the coverage/fixture gate. No profitability result is produced when the latter fails.')
    write(HERE/'verification.json',out)
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
