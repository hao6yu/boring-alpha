"""Narrow source-linked EPS policy support; v2 book and numeric rules preserved.

No issuer identifiers, fixture values, or returns are used by these rules.
The original v2 parser remains immutable in its own experiment directory.
"""
from pathlib import Path
import importlib.util
import re
from datetime import datetime
from collections import defaultdict

BASE = Path(__file__).resolve().parent.parent/'financial-extraction-v2-2026-09-14'
spec = importlib.util.spec_from_file_location('frozen_extraction_v2', BASE/'extract.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
INCOME, BASIC, DILUTED = v2.INCOME, v2.BASIC, v2.DILUTED
rounding_radius = v2.rounding_radius


def policy_excerpt(filing):
    patterns = [
        r'basic (?:earnings.{0,40}per share|eps).{0,100}(?:dividing|divid).{0,25}net (?:income|earnings).{0,220}(?:common|ordinary) (?:stock|shares).{0,180}',
        r'basic eps equals net income divided by.{0,100}(?:common|ordinary) shares.{0,180}',
    ]
    for pattern in patterns:
        match=re.search(pattern, filing.full_text, re.I)
        if match:
            return dict(text=match.group(0), accn=filing.meta['accn'], filed=filing.meta['filed'],
                        cik=filing.meta['cik'], report_end=filing.meta['report_end'],
                        url=filing.meta['url'], kind='same_filing_explicit_basic_eps_policy')
    return None


def linked_policy(filing, filings):
    direct=policy_excerpt(filing)
    if direct:return direct
    # Parse the annual period stated in the original quarterly basis note.
    # A generic reference to past reports is insufficient.
    pattern=r'should be read in conjunction.{0,260}Form 10.K for the year ended ([A-Za-z]+ \d{1,2}, \d{4})'
    match=re.search(pattern,filing.full_text,re.I)
    reference=match.group(0) if match else None
    annual_end=None
    if match:
        annual_end=datetime.strptime(match.group(1),'%B %d, %Y').date().isoformat()
    else:
        # Fiscal-year wording is accepted only with an explicit unchanged-policy
        # statement and one uniquely matching annual report in the saved set.
        match=re.search(r'There have been no material changes in.{0,90}accounting policies.{0,100}Fiscal (\d{4}) Form 10.K',filing.full_text,re.I)
        if match:reference=match.group(0)
    if not match:return None
    candidates=[]
    for annual in filings:
        if annual.meta['form']!='10-K' or annual.meta['cik']!=filing.meta['cik']:continue
        if annual.meta['filed']>=filing.meta['filed']:continue
        if annual_end and annual.meta['report_end']!=annual_end:continue
        if not annual_end and not annual.meta['report_end'].startswith(match.group(1)):continue
        evidence=policy_excerpt(annual)
        if evidence:candidates.append(evidence)
    if len(candidates)!=1:return None
    return dict(candidates[0],kind='explicitly_referenced_annual_basic_eps_policy',
                quarterly_reference=reference, referencing_accn=filing.meta['accn'])


class Filing(v2.Filing):
    policy_evidence = None

    def incomes(self):
        candidates=defaultdict(list);reasons=[]
        # Only use an explicit source policy, either in this filing or in the
        # particular annual filing it tells readers to consult. The evidence
        # is attached to each qualification and checked again at historical use.
        evidence = self.policy_evidence
        policy = evidence is not None
        linked_text = evidence['text'] if evidence else ''
        participating = 'participating securities' in (self.full_text + linked_text).lower()
        included_in_basic = bool(re.search(
            r'basic earnings per share.{0,180}weighted.average.{0,100}'
            r'ordinary shares outstanding, including participating securities', linked_text, re.I))
        two_class = (participating and not included_in_basic) or (
            not policy and bool(re.search(r'two[- ]class method', self.full_text, re.I)))
        adjustments=[f for f in self.facts if any(s in f['tag'].lower() for s in ('preferredstockdividends','undistributedearningsallocated','incomelossattributabletoparticipating')) and f['val']!=0]
        for table in self.tables:
            tags={f['tag'] for f in table['facts']}
            if not (tags&INCOME):continue
            dedicated=(BASIC in tags and DILUTED in tags and not tags&{'Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','Assets','CostOfGoodsAndServicesSold','OperatingIncomeLoss'})
            explicit_numerator=bool(re.search(r'numerator.{0,60}basic',table['text'],re.I))
            if not dedicated and not (policy and 'EarningsPerShareBasic' in tags):continue
            byperiod=defaultdict(list)
            for f in table['facts']:
                if f['start'] is not None:byperiod[f['start'],f['end']].append(f)
            for period,fs in byperiod.items():
                common=[f for f in fs if f['tag']=='NetIncomeLossAvailableToCommonStockholdersBasic' and f['unit']=='USD']
                net=common or [f for f in fs if f['tag']=='NetIncomeLoss' and f['unit']=='USD']
                if not net or len({f['val'] for f in net})!=1:continue
                f=net[0]
                if not common and (two_class or any(x['start']==period[0] and x['end']==period[1] for x in adjustments)):
                    reasons.append(dict(start=period[0],end=period[1],reason='COMMON_EARNINGS_ADJUSTMENT_UNRESOLVED'));continue
                # Match the denominator and total basic EPS by exact entity/period.
                pool=[x for x in self.facts if x['start']==period[0] and x['end']==period[1]]
                shares=[x for x in fs if x['tag']==BASIC] or [x for x in pool if x['tag']==BASIC]
                eps=[x for x in fs if x['tag']=='EarningsPerShareBasic'] or [x for x in pool if x['tag']=='EarningsPerShareBasic']
                if not shares or len({x['val'] for x in shares})!=1 or shares[0]['val']<=0:continue
                if eps and len({x['val'] for x in eps})==1:
                    s,e=shares[0],eps[0]
                    try:
                        tolerance=rounding_radius(f)+abs(s['val'])*rounding_radius(e)+abs(e['val'])*rounding_radius(s)+rounding_radius(s)*rounding_radius(e)
                    except (TypeError,ValueError):continue
                    if abs(f['val']-s['val']*e['val'])>tolerance:
                        reasons.append(dict(start=period[0],end=period[1],reason='BASIC_EPS_RECONCILIATION_FAILED'));continue
                elif not (dedicated and explicit_numerator):continue
                candidates[period].append(dict(value=int(f['val']),
                    method='explicit_basic_numerator_table' if explicit_numerator else 'total_basic_eps_reconciliation',
                    source=self.provenance(f,table['index']),shares=self.provenance(shares[0],table['index']),
                    eps=self.provenance(eps[0],table['index']) if eps and len({x['val'] for x in eps})==1 else None,
                    explicit_policy_used=not dedicated,policy_evidence=evidence if policy else None))
        out={}
        for period,cs in candidates.items():
            if len({c['value'] for c in cs})==1:out['|'.join(period)]=cs[0]
            else:reasons.append(dict(start=period[0],end=period[1],reason='CONFLICTING_COMMON_EARNINGS'))
        return out,reasons

