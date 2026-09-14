"""Conservative structural extraction from original inline-XBRL filings.

No issuer identifiers, fixture answers or return data are used by these rules.
Unrecognized structures produce an abstention, not an imputed value.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import re
from lxml import html

D=Decimal
COMMON={'CommonStockValue','CommonStockValueOutstanding'}
COMPONENTS=COMMON|{'AdditionalPaidInCapital','AdditionalPaidInCapitalCommonStock',
    'RetainedEarningsAccumulatedDeficit','AccumulatedOtherComprehensiveIncomeLossNetOfTax',
    'TreasuryStockValue','TreasuryStockCommonValue','DeferredCompensationEquity'}
TREASURY={'TreasuryStockValue','TreasuryStockCommonValue'}
PARENT_TOTALS={'StockholdersEquity','EquityAttributableToParentNet'}
TOTALS=PARENT_TOTALS|{'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'}
INCOME={'NetIncomeLoss','NetIncomeLossAvailableToCommonStockholdersBasic'}
BASIC='WeightedAverageNumberOfSharesOutstandingBasic'
DILUTED='WeightedAverageNumberOfDilutedSharesOutstanding'


def text(node):return ' '.join(' '.join(node.itertext()).split())
def local(tag):return tag.split(':')[-1]
def rounding_radius(f):
    dec=f['decimals']
    return D(0) if dec=='INF' else D('0.5')*D(10)**(-int(dec))


class Filing:
    def __init__(self,markup,metadata):
        if not markup.rstrip().lower().endswith('</html>') or markup.endswith('[Truncated]'):
            raise ValueError('Incomplete document')
        self.meta=metadata
        self.doc=html.fromstring(markup,parser=html.HTMLParser(huge_tree=True))
        self.contexts={};self.units={};self.facts=[];self.by_node={}
        for e in self.doc.iter():
            if e.tag=='xbrli:context':
                children={local(x.tag):text(x) for x in e.iter() if local(x.tag) in ('identifier','instant','startdate','enddate')}
                dims=[(x.get('dimension'),text(x)) for x in e.iter() if x.tag in ('xbrldi:explicitmember','xbrldi:typedmember')]
                self.contexts[e.get('id')]=dict(cik=children.get('identifier'),
                    start=children.get('startdate'),end=children.get('instant',children.get('enddate')),dimensions=dims)
            elif e.tag=='xbrli:unit':
                self.units[e.get('id')]=text(e).replace(' ','')
        for e in self.doc.xpath('//*[@contextref]'):
            if e.tag!='ix:nonfraction' or any(a.tag=='ix:hidden' for a in e.iterancestors()):continue
            context=self.contexts.get(e.get('contextref'))
            if not context or context['dimensions'] or str(context['cik']).zfill(10)!=metadata['cik']:continue
            raw=text(e);fmt=e.get('format','').lower()
            if e.get('xsi:nil')=='true':continue
            try:
                if ('zero' in fmt or 'numdash' in fmt) and not re.search(r'\d',raw):value=D(0)
                else:value=D(raw.replace(',','').replace(' ','').replace('−','-'))
                value*=D(10)**int(e.get('scale','0'))
                if e.get('sign')=='-':value=-value
            except (InvalidOperation,ValueError):continue
            tag=local(e.get('name',''))
            unit=self.units.get(e.get('unitref'),'')
            # A simple measure must be USD; divided USD/share units remain distinct.
            unit='USD' if unit in ('iso4217:USD','USD') else ('shares' if unit in ('xbrli:shares','shares') else unit)
            f=dict(tag=tag,qualified_tag=e.get('name'),val=value,unit=unit,
                   start=context['start'],end=context['end'],context=e.get('contextref'),
                   decimals=e.get('decimals'),id=e.get('id'))
            self.facts.append(f);self.by_node[e]=f
        self.tables=[]
        for ti,table in enumerate(self.doc.xpath('//table')):
            rows=[]
            for tr in table.xpath('./tr|./tbody/tr|./thead/tr|./tfoot/tr'):
                fs=[self.by_node[e] for e in tr.xpath('.//*[@contextref]') if e in self.by_node]
                # Nested layout tables cannot establish a clean statement boundary.
                if tr.xpath('.//table'):continue
                rows.append(dict(label=text(tr),facts=fs))
            self.tables.append(dict(index=ti,rows=rows,facts=[f for r in rows for f in r['facts']],text=text(table)))
        self.full_text=text(self.doc)

    def provenance(self,f,table):
        out={k:(int(v) if isinstance(v,D) and v==v.to_integral() else str(v) if isinstance(v,D) else v)
             for k,v in f.items()}
        out.update(accn=self.meta['accn'],filed=self.meta['filed'],url=self.meta['url'],table=table)
        return out

    def books(self):
        candidates=defaultdict(list);reasons=[]
        for table in self.tables:
            tags={f['tag'] for f in table['facts']}
            if not ({'Assets','LiabilitiesAndStockholdersEquity'}<=tags and tags&COMMON):continue
            ends=sorted({f['end'] for f in table['facts'] if f['tag'] in TOTALS and f['start'] is None})
            for end in ends:
                rows=[]
                for row in table['rows']:
                    fs=[f for f in row['facts'] if f['end']==end and f['start'] is None]
                    rows.append((row['label'],fs))
                # Full equity block starts after the last total-liabilities row,
                # or, when that subtotal is omitted, the first common/preferred row.
                liabilities=[i for i,(_,fs) in enumerate(rows) if any(f['tag']=='Liabilities' and f['unit']=='USD' for f in fs)]
                capital=[i for i,(label,fs) in enumerate(rows) if any(f['tag'] in COMMON for f in fs) or re.search(r'preferred (?:stock|shares)',label,re.I)]
                parent=[i for i,(_,fs) in enumerate(rows) if any(f['tag'] in PARENT_TOTALS and f['unit']=='USD' for f in fs)]
                totals=parent or [i for i,(_,fs) in enumerate(rows) if any(f['tag'] in TOTALS and f['unit']=='USD' for f in fs)]
                if not capital or not totals:continue
                stop=totals[0];start=min(capital)
                if start>=stop:continue
                block=rows[start:stop];parts=[];failed=None
                for bi,(label,fs) in enumerate(block):
                    usd=[f for f in fs if f['unit']=='USD']
                    if re.search(r'preferred (?:stock|shares)',label,re.I):
                        # Issuance details may occupy a continuation row beneath
                        # the preferred capital amount, before the next dollar row.
                        for next_label,next_fs in block[bi+1:]:
                            if any(f['unit']=='USD' for f in next_fs):break
                            label+=' '+next_label
                            fs=fs+next_fs
                        explicit=[f for f in fs if f['tag'] in ('PreferredStockSharesIssued','PreferredStockSharesOutstanding') and f['val']==0]
                        if not explicit:
                            # Text evidence must refer to issuance, never merely authorization/par value.
                            explicit=bool(re.search(r'(?:no|none|zero)\s+(?:shares\s+)?(?:are\s+|were\s+)?issued|(?:shares\s+)?issued\s*[-–—,:]?\s*(?:none|zero)',label,re.I))
                        if not explicit or any(f['val']!=0 for f in usd):failed='PREFERRED_SCOPE_UNRESOLVED';break
                        continue
                    for f in usd:
                        tag=f['tag']
                        if tag not in COMPONENTS:
                            # Original tagged custom deferred-compensation equity is
                            # admissible only inside the reconciled parent-equity block.
                            if re.search(r'deferred compensation (?:obligation|equity)',label,re.I):
                                part=dict(f,component_role='DeferredCompensationEquity')
                            else:failed='UNKNOWN_EQUITY_COMPONENT:'+tag;break
                        else:part=dict(f,component_role=tag)
                        part['arithmetic_sign']=-1 if tag in TREASURY else 1
                        parts.append(part)
                    if failed:break
                if failed:reasons.append(dict(end=end,table=table['index'],reason=failed));continue
                # A component appearing twice is a structure ambiguity, not two balances.
                roles=[p['component_role'] for p in parts]
                if len(roles)!=len(set(roles)) or not(set(roles)&COMMON) or 'RetainedEarningsAccumulatedDeficit' not in roles:continue
                target=[f for f in rows[stop][1] if f['tag'] in TOTALS and f['unit']=='USD']
                if len(target)!=1:continue
                value=sum((p['val']*p['arithmetic_sign'] for p in parts),D(0))
                # Published rounded components can differ from the published
                # total. Require overlapping precision intervals; retain the
                # directly reported parent total as the canonical point value.
                try:allowance=sum((rounding_radius(p) for p in parts),D(0))+rounding_radius(target[0])
                except (TypeError,ValueError):allowance=D(0)
                if abs(value-target[0]['val'])>allowance:
                    reasons.append(dict(end=end,table=table['index'],reason='EQUITY_RECONCILIATION_FAILED'));continue
                candidates[end].append(dict(value=int(target[0]['val']),method='complete_original_common_equity_block',
                    sum_of_rounded_components=int(value),rounding_difference=int(value-target[0]['val']),
                    rounding_allowance=str(allowance),
                    parts=[self.provenance(p,table['index']) for p in parts],
                    total=self.provenance(target[0],table['index'])))
        out={}
        for end,cs in candidates.items():
            if len({c['value'] for c in cs})==1:out[end]=cs[0]
            else:reasons.append(dict(end=end,reason='CONFLICTING_COMMON_EQUITY'))
        return out,reasons

    def incomes(self):
        candidates=defaultdict(list);reasons=[]
        # An explicit accounting policy can link a main income statement to
        # its total basic EPS, even when the EPS footnote covers continuing ops.
        policy=bool(re.search(r'basic (?:earnings.{0,40}per share|eps).{0,100}(?:dividing|divid).{0,25}net (?:income|earnings).{0,160}(?:common|ordinary) (?:stock|shares)',self.full_text,re.I)
                    or re.search(r'basic eps equals net income divided by.{0,100}(?:common|ordinary) shares',self.full_text,re.I))
        # A method expressly confined to diluted EPS does not disqualify a
        # separately explicit basic-EPS policy. Participating claims still need
        # their own reconciliation; this pass does not infer their allocation.
        two_class=bool(re.search(r'participating securities',self.full_text,re.I) or
                       (not policy and re.search(r'two[- ]class method',self.full_text,re.I)))
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
                    explicit_policy_used=not dedicated))
        out={}
        for period,cs in candidates.items():
            if len({c['value'] for c in cs})==1:out['|'.join(period)]=cs[0]
            else:reasons.append(dict(start=period[0],end=period[1],reason='CONFLICTING_COMMON_EARNINGS'))
        return out,reasons

    def extract(self):
        books,br=self.books();incomes,ir=self.incomes()
        return dict(metadata=self.meta,book=books,income=incomes,abstentions=br+ir,
                    visible_entity_facts=len(self.facts),parsed_tables=len(self.tables))
