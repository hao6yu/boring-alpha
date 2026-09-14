"""Check the policy linkage and preserve the remaining source inconsistency."""
from copy import deepcopy
from decimal import Decimal as D
from replay import HERE,ROOT,RAW,V2,load,write,sha,intact,documents,available
from extract_v3 import Filing,linked_policy


def main():
    intact()
    for name,digest in load(HERE/'extraction-freeze.json')['files'].items():assert sha(ROOT/name)==digest
    objects,docs=documents();byid={f.meta['id']:f for f in objects};checks=[]
    c=load(HERE/'coverage.json')
    assert c['fixtures_passed']==27 and c['fixture_targets']==28 and not c['data_gate_passed']
    assert [(r['symbol'],r['month'],r['field']) for r in c['fixture_results'] if not r['passed']]==[('WHR','2026-01','common_income_ttm')]
    checks.append('27 source-qualified fixture values; remaining WHR failure is retained')
    assert c['profitability_runs']==c['new_network_requests']==c['new_model_fits']==0
    checks.append('failed gate has produced no return comparison, fit or acquisition')
    # Policy reference must be in the current quarterly filing and must match
    # both the issuer and the specific available annual report.
    for qi,ai in [(7,8),(17,18),(19,20)]:
        quarter,annual=byid[qi],byid[ai]
        p=linked_policy(quarter,[annual])
        assert p and p['accn']==annual.meta['accn']
        assert p['text'] in annual.full_text and p['quarterly_reference'] in quarter.full_text
        assert linked_policy(quarter,[]) is None
        assert linked_policy(quarter,[annual,annual]) is None
        text=quarter.full_text
        quarter.full_text=text.replace(p['quarterly_reference'],'reference removed')
        assert linked_policy(quarter,[annual]) is None
        quarter.full_text=text
        for key,bad in [('cik','9999999999'),('report_end','2001-12-31'),('filed','2026-09-14')]:
            old=annual.meta[key];annual.meta[key]=bad
            assert linked_policy(quarter,[annual]) is None
            annual.meta[key]=old
    checks.append('missing, wrong-issuer, wrong-period, future and ambiguous policy sources rejected')
    # Participating securities require an explicit inclusion in the basic-share
    # policy. Numeric agreement alone does not bypass the scope check.
    f=byid[20];e=deepcopy(f.policy_evidence)
    assert f.incomes()[0]
    f.policy_evidence=dict(e,text=e['text'].replace('including participating securities','excluding participating securities'))
    assert not f.incomes()[0]
    f.policy_evidence=e
    checks.append('participating-security acceptance depends on the explicit basic denominator policy')
    # Arithmetic and conflicting claim adjustments remain binding even with a
    # qualified annual policy.
    original=D('2654000000');facts=[x for x in f.facts if x['tag']=='NetIncomeLoss' and x['start']=='2024-01-01']
    saved=[x['val'] for x in facts]
    for x in facts:x['val']=original+D('1000000000')
    assert '2024-01-01|2024-12-31' not in f.incomes()[0]
    for x,val in zip(facts,saved):x['val']=val
    adj=dict(tag='UndistributedEarningsAllocatedToParticipatingSecurities',val=D('1000000'),start='2024-01-01',end='2024-12-31')
    f.facts.append(adj)
    assert '2024-01-01|2024-12-31' not in f.incomes()[0]
    f.facts.pop()
    checks.append('policy linkage does not override EPS mismatch or disclosed allocation adjustments')
    new={(r['symbol'],r['month']):r for r in load(RAW/'revised-monthly-fundamentals.json')}
    previous=load(ROOT/'data/snapshots/financial-extraction-v2-2026-09-14/revised-monthly-fundamentals.json')
    for row in previous:
        for field in ('common_equity','common_income_ttm'):
            old=row[field];val=new[row['symbol'],row['month']][field]
            if old is not None:
                assert (old['value'] if isinstance(old,dict) else old)==(val['value'] if isinstance(val,dict) else val)
    assert len(new)==5700 and len({k[0] for k in new})==100
    checks.append('all prior v2 candidate values, company identities and 5700 slots are preserved')
    # Every referenced annual policy is visible and available at each repaired
    # historical input date. The production code never reads manual fixtures.
    policy_uses=0
    for row in load(RAW/'change-provenance.json'):
        for part in row['proof'].get('income',{}).get('components',[]):
            policy=part.get('policy_evidence')
            if not policy:continue
            source=next(f for f in objects if f.meta['accn']==policy['accn'])
            assert source.meta['cik']==policy['cik']
            assert policy['text'] in source.full_text and available(policy['filed'])<=row['cut']
            if policy['kind']=='explicitly_referenced_annual_basic_eps_policy':
                q=next(f for f in objects if f.meta['accn']==policy['referencing_accn'])
                assert q.meta['cik']==source.meta['cik'] and policy['quarterly_reference'] in q.full_text
            policy_uses+=1
    checks.append('all accepted policy excerpts and historical availability independently checked')
    # Compute exact rounding intervals, separately from the parser's symmetric
    # error bound, for the remaining source arithmetic inconsistency.
    whr=byid[15];issues=[]
    for start in ('2024-01-01','2024-07-01'):
        fs=[x for x in whr.facts if x['start']==start and x['end']=='2024-09-30']
        pick=lambda tag:next(x for x in fs if x['tag']==tag)
        n,s,e=pick('NetIncomeLoss'),pick('WeightedAverageNumberOfSharesOutstandingBasic'),pick('EarningsPerShareBasic')
        radius=lambda x:D('0.5')*D(10)**(-int(x['decimals']))
        ni=[n['val']-radius(n),n['val']+radius(n)]
        implied=[(s['val']-radius(s))*(e['val']-radius(e)),(s['val']+radius(s))*(e['val']+radius(e))]
        assert implied[0]>ni[1]
        issues.append(dict(start=start,end='2024-09-30',accn=whr.meta['accn'],url=whr.meta['url'],
                           net_income=str(n['val']),basic_shares=str(s['val']),basic_eps=str(e['val']),
                           net_income_interval=list(map(str,ni)),eps_implied_income_interval=list(map(str,implied)),
                           minimum_nonoverlap_usd=str(implied[0]-ni[1]),fact_ids=[n['id'],s['id'],e['id']]))
    checks.append('independent interval arithmetic confirms WHR discrepancy without widening tolerance')
    resolution=dict(resolved_targets=[r for r in c['fixture_results'] if r['symbol'] in ('VFC','AON') and r['field']=='common_income_ttm'],
                    remaining_issue=issues,policy_uses_checked=policy_uses,
                    note='WHR discloses a changed rounding presentation, but gives no quantified explanation that closes these intervals. No earnings value is inferred backwards from rounded EPS.')
    write(HERE/'accounting-resolution.json',resolution)
    write(HERE/'verification.json',dict(status='PASS',count=len(checks),checks=checks,data_gate_passed=False,policy_uses_checked=policy_uses))
    intact();print(dict(status='PASS',checks=len(checks),policy_uses=policy_uses,remaining_fixture_failures=1))


if __name__=='__main__':main()
