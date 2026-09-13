#!/usr/bin/env python3
"""Bounded, public SEC document collector for the frozen availability pilot.

No price data or returns. Heuristic document extraction remains reviewable in
the saved source excerpts; ambiguous matches are not passed automatically.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
POLICY_SHA = 'f6178cb98b4716a8744b79a3bae2b0709f6c4ee056f3a66be0789fc38cb2e188'
RAW = ROOT / 'data/snapshots/equity-event-pilot-2026-09-10/sec'
NY = ZoneInfo('America/New_York')
UTC = timezone.utc

def now(): return datetime.now(UTC).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(b); tmp.replace(path)
    return sha(b)

class HTML(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.links=[]; self.rows=[]; self.row=None
        self.cell=None; self.anchor=None; self.skip=0; self.tags=[]; self.ix=[]
        self.feed(raw)
        self.text=re.sub(r'\s+', ' ', ' '.join(self.parts)).strip()
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript','ix:hidden'): self.skip+=1
        if tag=='tr': self.row=[]
        if tag in ('td','th'): self.cell=[]
        if tag=='a': self.anchor=[a.get('href',''),[]]
        if tag in ('ix:nonfraction','ix:nonnumeric'):
            self.tags.append([tag,a.get('name',''),[]])
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','ix:hidden'): self.skip=max(0,self.skip-1)
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None:self.row.append(re.sub(r'\s+',' ',' '.join(self.cell)).strip())
            self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None
        if tag=='a' and self.anchor:
            self.links.append((self.anchor[0],re.sub(r'\s+',' ',' '.join(self.anchor[1])).strip())); self.anchor=None
        if self.tags and tag==self.tags[-1][0]:
            t=self.tags.pop();self.ix.append((t[1],re.sub(r'\s+',' ',' '.join(t[2])).strip()))
    def handle_data(self,s):
        if self.skip:return
        s=s.strip()
        if not s:return
        self.parts.append(s)
        if self.cell is not None:self.cell.append(s)
        if self.anchor:self.anchor[1].append(s)
        if self.tags:self.tags[-1][2].append(s)

class Collector:
    def __init__(self):
        pb=(HERE/'policy.json').read_bytes()
        if sha(pb)!=POLICY_SHA:raise ValueError('frozen policy hash mismatch')
        self.policy=json.loads(pb);self.deadline=datetime.fromisoformat(self.policy['deadline_utc'].replace('Z','+00:00'))
        self.sources_path=HERE/'sec-sources.json'
        self.sources=json.loads(self.sources_path.read_text()) if self.sources_path.exists() else {'policy_sha256':POLICY_SHA,'sources':{},'attempts':[]}
        self.last=0.0
        self.context=ssl.create_default_context()
        if not self.context.cert_store_stats()['x509_ca']:
            self.context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
        self.events_cache={}
        self.offline=False
    def get(self,url):
        if not url.startswith(('https://www.sec.gov/','https://data.sec.gov/')):raise ValueError('non-SEC URL')
        old=self.sources['sources'].get(url)
        if old and old.get('status')==200:
            b=(ROOT/old['file']).read_bytes()
            if sha(b)!=old['sha256']:raise ValueError('cached hash mismatch')
            return b,old['file']
        if old and old.get('terminal'):raise RuntimeError('prior_terminal:'+str(old.get('error')))
        if self.offline:raise RuntimeError('OFFLINE_SOURCE_NOT_CACHED:'+url)
        for attempt in range(2):
            if (self.deadline-datetime.now(UTC)).total_seconds()<22:raise RuntimeError('DEADLINE')
            time.sleep(max(0,.26-(time.monotonic()-self.last)));self.last=time.monotonic()
            rec={'url':url,'started_at':now(),'attempt_in_call':attempt+1}
            try:
                request=urllib.request.Request(url,headers={'User-Agent':'BoringAlphaResearch/0.1 (personal financial research)','Accept-Encoding':'identity'})
                with urllib.request.urlopen(request,timeout=20,context=self.context) as response:
                    b=response.read(32*1024*1024+1)
                    if len(b)>32*1024*1024:raise ValueError('payload_limit')
                    rec.update(status=response.status,received_at=now(),bytes=len(b),sha256=sha(b),response_url=response.url)
                    if response.status!=200:raise ValueError('non200')
                    suffix=Path(urllib.parse.urlsplit(url).path).suffix or '.bin'
                    path=RAW/(sha(url.encode())+suffix)
                    path.parent.mkdir(parents=True,exist_ok=True)
                    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(b);tmp.replace(path)
                    rec['file']=str(path.relative_to(ROOT))
                    self.sources['sources'][url]=rec;self.sources['attempts'].append(rec)
                    atomic(self.sources_path,self.sources)
                    return b,rec['file']
            except Exception as e:
                code=getattr(e,'code',None)
                transient=isinstance(e,(urllib.error.URLError,TimeoutError,ConnectionError)) and code not in (400,401,403,404,429)
                if code and code>=500:transient=True
                rec.update(status=code,error=type(e).__name__+':'+str(e),failed_at=now(),terminal=not transient or attempt==1)
                self.sources['sources'][url]=rec;self.sources['attempts'].append(rec);atomic(self.sources_path,self.sources)
                if not transient or attempt==1:raise
                time.sleep(1)
        raise RuntimeError('unreachable')
    def submissions(self,cik,start,end,forms=('8-K','8-K/A')):
        b,file=self.get(f'https://data.sec.gov/submissions/CIK{cik}.json');d=json.loads(b)
        tables=[(d['filings']['recent'],file)]
        recent=d['filings']['recent']
        if not recent.get('filingDate') or min(recent['filingDate'])>start:
            for old in d['filings'].get('files',[]):
                if old['filingFrom']<=end and old['filingTo']>=start:
                    b,file=self.get('https://data.sec.gov/submissions/'+old['name']);tables.append((json.loads(b),file))
        rows={}
        for table,file in tables:
            for i,day in enumerate(table['filingDate']):
                if start<=day<=end and table['form'][i] in forms:
                    row={k:v[i] for k,v in table.items() if isinstance(v,list) and len(v)==len(table['filingDate'])}
                    row['metadata_file']=file;rows[row['accessionNumber']]=row
        return sorted(rows.values(),key=lambda r:(r['filingDate'],r.get('acceptanceDateTime',''),r['accessionNumber']))
    def event(self,cik,row):
        acc=row['accessionNumber']
        if acc in self.events_cache:return self.events_cache[acc]
        base=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-","")}/'
        ib,ip=self.get(base+acc+'-index.html');idx=HTML(ib.decode('utf-8','replace'))
        pb,pp=self.get(base+row['primaryDocument']);primary=HTML(pb.decode('utf-8','replace'))
        accepted=re.search(r'Accepted\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})',idx.text)
        local=datetime.fromisoformat(' '.join(accepted.groups())).replace(tzinfo=NY) if accepted else None
        api=row.get('acceptanceDateTime');api_dt=datetime.fromisoformat(api.replace('Z','+00:00')) if api else None
        identity=cover_identity(primary)
        anchor_index=max(row['filingDate'],local.date().isoformat()) if local else None
        anchor_api=max(row['filingDate'],api_dt.astimezone(NY).date().isoformat()) if api_dt else None
        exact=bool(local and api_dt and local==api_dt)
        invariant=bool(anchor_index and anchor_api and anchor_index==anchor_api)
        out={'accession':acc,'filing_date':row['filingDate'],'acceptance_eastern':local.isoformat() if local else None,'acceptance_utc':api,'timing_match':exact,'daily_entry_anchor_index':anchor_index,'daily_entry_anchor_api':anchor_api,'daily_entry_invariant':invariant,'timing_proxy_status':'EXACT_TIMESTAMP_RECONCILED' if exact else 'EXACT_TIMESTAMP_UNRESOLVED_DAILY_ENTRY_INVARIANT' if invariant else 'UNRESOLVED','release_date':None,'period_end':None,'primary_url':base+row['primaryDocument'],'primary_file':pp,'index_file':ip,'metadata_file':row['metadata_file'],'security':identity,'items':row.get('items'),'form':row['form'],'classification':'UNRESOLVED','classification_evidence':[],'exhibit_candidates':[]}
        item=re.search(r'Item\s*2\.02[.\s:]*Results\s+of\s+Operations',primary.text,re.I) or re.search(r'Item\s*2\.02[.\s:]*',primary.text,re.I)
        section=primary.text[item.start():item.start()+4500] if item else primary.text[-6500:]
        next_item=re.search(r'\bItem\s*[1-9]\.\d{2}',section[12:],re.I)
        if next_item:section=section[:12+next_item.start()]
        out['item_202_excerpt']=section
        letter_match=re.search(r'(?:letter to (?:its |the )?shareholders|full text of the Shareholder Letter).{0,320}?Exhibit\s+(99\.\d+)',section,re.I)
        letter_exhibit=letter_match[1] if letter_match and re.search(r'press release',section,re.I) else None
        paired_letter_release=letter_exhibit is not None
        out['accounting_companions']=[]
        candidates=[]
        for cells in idx.rows:
            if any(re.fullmatch(r'EX-?99(?:\.\d+)?',x,re.I) for x in cells):
                for href,label in idx.links:
                    if label in cells and re.search(r'\.(htm|html|txt)$',href,re.I):
                        url=urllib.parse.urljoin(base,href)
                        if url not in [x[0] for x in candidates]:candidates.append((url,' | '.join(cells)))
        if letter_exhibit:
            candidates.sort(key=lambda pair:0 if re.search(r'EX-?'+re.escape(letter_exhibit)+r'\b',pair[1],re.I) else 1)
        for url,desc in candidates[:5]:
            if 'supplement' in desc.lower() or 'presentation' in desc.lower():
                out['exhibit_candidates'].append({'url':url,'description':desc,'status':'REJECTED_SUPPLEMENT_OR_PRESENTATION'});continue
            eb,ep=self.get(url);ex=HTML(eb.decode('utf-8','replace'))
            classify=classify_release(ex.text,section,row['filingDate'])
            if paired_letter_release and re.search(r'EX-?'+re.escape(letter_exhibit)+r'\b',desc,re.I):
                out['accounting_companions'].append({'url':url,'file':ep,'sha256':sha(eb),'document_type':'SHAREHOLDER_LETTER','source_evidence':section,'text_excerpt':ex.text[:2500],**classify})
                out['exhibit_candidates'].append({'url':url,'description':desc,'file':ep,'status':'ACCOUNTING_COMPANION_SHAREHOLDER_LETTER'})
                continue
            out['exhibit_candidates'].append({'url':url,'description':desc,'file':ep,**classify})
            if classify['classification']=='EARNINGS_RELEASE':
                out.update(classify);out.update(exhibit_url=url,exhibit_file=ep,exhibit_sha256=sha(eb),exhibit_description=desc,release_excerpt=ex.text[:9000],text_characters=len(ex.text))
                out['document_type']='PRESS_RELEASE_WITH_ACCOUNTING_COMPANION' if out['accounting_companions'] else 'EARNINGS_RELEASE'
                break
        if out['classification']=='UNRESOLVED':
            rejected=next((x for x in out['exhibit_candidates'] if x.get('classification') in ('PRELIMINARY','GUIDANCE_UPDATE','FUTURE_RELEASE_NOTICE')),None)
            if rejected:
                for k in ('classification','classification_evidence','release_date','release_date_candidates','period_end','period_evidence','period_candidates'):
                    if k in rejected:out[k]=rejected[k]
                out['rejected_exhibit_url']=rejected['url'];out['rejected_exhibit_file']=rejected.get('file')
            if re.search(r'preliminary.{0,50}(?:results|financial)|(?:results|financial).{0,50}preliminary',section,re.I):
                out['classification']='PRELIMINARY'
                out['classification_evidence']={'primary_item_202':section}
            elif re.search(r'updated financial guidance|updates?.{0,60}(?:guidance|expectations)',section,re.I):
                out['classification']='GUIDANCE_UPDATE'
                out['classification_evidence']={'primary_item_202':section}
            elif re.search(r'transition.{0,90}IFRS.{0,90}U.S. GAAP|transition from IFRS to U.S. GAAP',section,re.I) and re.search(r'presentation',section,re.I):
                out['classification']='ACCOUNTING_TRANSITION_PRESENTATION'
                out['classification_evidence']={'primary_item_202':section}
        self.events_cache[acc]=out
        return out

def cover_identity(h):
    rows=[]
    for cells in h.rows:
        t=' | '.join(cells)
        if re.search(r'common\s+(stock|shares)|ordinary\s+shares|shares\s+of\s+beneficial',t,re.I) and re.search(r'Nasdaq|New York Stock|NYSE|NYSE American',t,re.I):
            # Table rows retain class, symbol and listing exchange together.
            symbols=[x for x in cells if re.fullmatch(r'[A-Z][A-Z0-9.\-/]{0,9}',x) and x not in ('NYSE','NASDAQ','AMEX')]
            if symbols:rows.append({'row_excerpt':t,'symbols':symbols})
    # Inline XBRL is corroboration; never use current submissions ticker lists.
    ix=[v for k,v in h.ix if k.lower()=='dei:tradingsymbol']
    symbols=list(dict.fromkeys(s for r in rows for s in r['symbols']))
    return {'status':'VERIFIED_SINGLE_COMMON_CLASS' if len(symbols)==1 else 'MULTIPLE_COMMON_CLASSES' if len(symbols)>1 else 'UNRESOLVED_COMMON_CLASS','historical_symbol':symbols[0] if len(symbols)==1 else None,'symbols':symbols,'common_stock_evidence':rows,'inline_trading_symbols':ix}

MONTH=r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)'
DATE_RE=rf'{MONTH}\s+\d{{1,2}}\s*,?\s*20\d{{2}}'
def parse_date(s):
    s=s.replace(',',' ').replace('.','');s=re.sub(r'\s+',' ',s).strip().replace('Sept ','Sep ')
    for fmt in ('%B %d %Y','%b %d %Y'):
        try:return datetime.strptime(s,fmt).date().isoformat()
        except ValueError:pass
    return None

def classify_release(text,section,filing_date):
    text=re.sub(r'\s+,',',',text);section=re.sub(r'\s+,',',',section)
    head=text[:16000];combined=text+' '+section
    evidence=[]
    quarter_words=r'(?:quarter|annual|year.end|year ended|fiscal year|full year|(?:three|3)(?:\s+and\s+(?:six|nine|twelve|6|9|12))?\s+months)'
    earned=bool(re.search(quarter_words+r'.{0,100}(?:results|earnings|net income)|(?:reports|announces|reported|announced).{0,100}(?:results|earnings).{0,100}'+quarter_words,head[:4500],re.I))
    preliminary=bool(re.search(r'(?:announces|reports|provides).{0,40}preliminary|preliminary.{0,35}(?:results|earnings)',head[:900],re.I))
    future=bool(re.search(r'(?:will release|will report|plans to release|scheduled to release).{0,80}(?:earnings|results)',head[:1400],re.I))
    guidance_only=bool(re.search(r'(?:updated|updates|provides|reaffirms).{0,60}(?:financial guidance|expectations|guidance)',head[:700]+' '+section,re.I) and not re.search(r'(?:reports|announces|announced|reported).{0,80}(?:financial results|quarter.{0,30}results|year.{0,30}results)',head[:700]+' '+section,re.I))
    numeric=bool(re.search(r'\$\s*\d|\d[.,]\d.{0,20}(?:million|billion)',head[:9000],re.I))
    posted_results=bool(re.search(r'today posted.{0,180}shareholder letter containing the financial results',head[:2000],re.I) and re.search(r'released its financial results',section,re.I))
    periods=[]
    pattern=rf'(?P<kind>(?:(?:first|second|third|fourth|fiscal|[1234](?:st|nd|rd|th))\s+)?quarter|(?:three|3)(?:\s+and\s+(?:six|nine|twelve|6|9|12))?\s+months|(?:six|nine|twelve|6|9|12)\s+months|fiscal\s+year|year)\s+(?:and\s+(?:(?:(?:fiscal|full)\s+)?year|quarter|period)\s+)?(?:ended|ending)\s+(?P<day>{DATE_RE})'
    for m in re.finditer(pattern,combined,re.I):
        d=parse_date(m['day'])
        if d and d<=filing_date and (date.fromisoformat(filing_date)-date.fromisoformat(d)).days<200:
            raw_kind=m['kind'].lower()
            kind='three months' if re.match(r'(?:three|3)\s+and\s+',raw_kind) else raw_kind
            scopes=[]
            if 'quarter' in m[0].lower() or kind in ('three months','3 months'):scopes.append('quarter')
            if 'year' in m[0].lower() or kind in ('twelve months','12 months'):scopes.append('year')
            periods.append({'period_end':d,'kind':kind,'raw_kind':raw_kind,'explicit_scopes':scopes,'source':'primary_item_202' if m.start()>len(text) else 'earnings_exhibit','excerpt':combined[max(0,m.start()-80):m.end()+100]})
    # Prefer an explicitly quarterly period to a year-to-date table column.
    periods=sorted(periods,key=lambda p:(p['period_end'],'quarter' in p['kind'] or p['kind'] in ('three months','3 months'),p['source']=='primary_item_202'),reverse=True)
    period=periods[0] if periods else None
    q=re.search(r'\b(first|second|third|fourth|1st|2nd|3rd|4th)(?:\s+fiscal)?[ -]+quarter\b',head[:600],re.I)
    ordinal={'first':1,'second':2,'third':3,'fourth':4,'1st':1,'2nd':2,'3rd':3,'4th':4}.get(q[1].lower()) if q else None
    release_dates=[]
    for m in re.finditer(DATE_RE,head[:2400]):
        d=parse_date(m[0])
        if d and d<=filing_date and (date.fromisoformat(filing_date)-date.fromisoformat(d)).days<=10:release_dates.append(d)
    for m in re.finditer(rf'(?:On|dated|issue on)\s+({DATE_RE})',section,re.I):
        d=parse_date(m[1])
        if d and d<=filing_date and (date.fromisoformat(filing_date)-date.fromisoformat(d)).days<=10:release_dates.append(d)
    release_dates=sorted(set(release_dates))
    primary_dates=[]
    for m in re.finditer(rf'(?:On\s+({DATE_RE}).{{0,180}}?(?:issued\s+a\s+press\s+release|announced\s+its\s+financial\s+results|reported\s+its\s+financial\s+results|released\s+its\s+financial\s+results)|issue\s+on\s+({DATE_RE}))',section,re.I):
        d=parse_date(m[1] or m[2])
        if d and d<=filing_date:primary_dates.append(d)
    primary_dates=sorted(set(primary_dates))
    selected_release_date=primary_dates[0] if len(primary_dates)==1 else release_dates[0] if len(release_dates)==1 else None
    classification='EARNINGS_RELEASE' if earned and (numeric or posted_results) and not preliminary and not future and not guidance_only else 'PRELIMINARY' if preliminary else 'GUIDANCE_UPDATE' if guidance_only else 'FUTURE_RELEASE_NOTICE' if future else 'NOT_VERIFIED_EARNINGS'
    return {'classification':classification,'classification_evidence':{'earnings_pattern':earned,'numerical_results':numeric,'posted_actual_results_in_companion':posted_results,'preliminary':preliminary,'guidance_only':guidance_only,'future_release_notice':future},'release_date':selected_release_date,'release_date_candidates':release_dates,'primary_release_date_candidates':primary_dates,'release_date_selection_rule':'unique Item2.02 actual-release date takes precedence over other dates mentioned in exhibit opening; otherwise unique opening date','period_end':period['period_end'] if period else None,'period_evidence':period,'period_candidates':periods[:12],'quarter_ordinal':ordinal,'accounting_flags':{'non_gaap':bool(re.search(r'non[ -]GAAP',text,re.I)),'constant_currency':bool(re.search(r'constant currency',text,re.I)),'restated_or_recast':bool(re.search(r'restat|recast|revis(?:ed|ion)',text,re.I))}}

def main():
    args=argparse.ArgumentParser();args.add_argument('--phase',choices=['selection','events','priors','all','fallbacks','finalize'],default='all');args.add_argument('--rebuild-selection',action='store_true');args.add_argument('--rebuild-events',action='store_true');args=args.parse_args()
    c=Collector();selection_path=HERE/'sec-selection.json';events_path=HERE/'sec-events.json'
    if args.phase=='fallbacks':
        return prior_fallbacks(c)
    if args.phase=='finalize':
        c.offline=True
        return finalize_collected(c)
    mb,mp=c.get(c.policy['seed_index_url']);ranked={}
    for line in mb.decode('latin-1').splitlines():
        fields=line.split('|')
        if len(fields)==5 and fields[2]=='8-K' and fields[0].isdigit():
            cik=fields[0].zfill(10)
            ranked.setdefault(cik,{'cik':cik,'issuer_name':fields[1],'seed_index_filings':[]})['seed_index_filings'].append({'filing_date':fields[3],'path':fields[4]})
    ranking=sorted(ranked.values(),key=lambda x:sha((c.policy['seed']+'|'+x['cik']).encode()))
    for i,r in enumerate(ranking,1):r.update(seed_rank=i,rank_digest=sha((c.policy['seed']+'|'+r['cik']).encode()))
    rankfile={'policy_sha256':POLICY_SHA,'master_file':mp,'master_sha256':sha(mb),'rows':ranking}
    ranksha=atomic(HERE/'sec-ranked-seed.json',rankfile)
    selection=json.loads(selection_path.read_text()) if selection_path.exists() and not args.rebuild_selection else {'policy_sha256':POLICY_SHA,'ranked_seed_sha256':ranksha,'cohort_id':'corrected-ranked-cohort-v1','selection_status':'IN_PROGRESS','issuers':[],'screened_exclusions':[],'screened':[]}
    if args.phase in ('selection','all'):
        inspected={x['cik'] for x in selection['screened']}
        for r in ranking[:c.policy['max_seed_issuers_inspected']]:
            if len(selection['issuers'])>=25:break
            if r['cik'] in inspected:continue
            screen={**r,'candidates':[]}
            try:
                rows=c.submissions(r['cik'],'2023-07-01','2023-09-30')
                candidates=[x for x in rows if x['form']=='8-K' and '2.02' in x.get('items','')]
                for row in candidates:
                    ev=c.event(r['cik'],row);screen['candidates'].append(ev)
                    if ev['classification']=='EARNINGS_RELEASE' and ev['security']['symbols']:
                        issuer={k:r[k] for k in ('cik','issuer_name','seed_rank','rank_digest')}
                        issuer.update(historical_symbol=ev['security']['historical_symbol'],historical_symbols=ev['security']['symbols'],seed_accession=ev['accession'],seed_filing_date=ev['filing_date'],common_stock_evidence=ev['security']['common_stock_evidence'],security_status=ev['security']['status'])
                        selection['issuers'].append(issuer);screen['decision']='SELECTED';screen['reason']='quarterly_or_year_end_earnings_and_contemporaneous_common_class';break
                if 'decision' not in screen:screen.update(decision='EXCLUDED',reason='NO_VERIFIED_EARNINGS_AND_COMMON_CLASS')
            except Exception as e:screen.update(decision='UNRESOLVED',reason=type(e).__name__+':'+str(e))
            selection['screened'].append(screen)
            if screen['decision']!='SELECTED':selection['screened_exclusions'].append(screen)
            selection['updated_at']=now();atomic(selection_path,selection)
            print(json.dumps({'phase':'selection','rank':r['seed_rank'],'cik':r['cik'],'decision':screen['decision'],'selected':len(selection['issuers']),'symbol':selection['issuers'][-1]['historical_symbol'] if screen['decision']=='SELECTED' else None}),flush=True)
        selection['selection_status']='COMPLETE_25' if len(selection['issuers'])==25 else 'INCOMPLETE'
        if any(x['decision']=='UNRESOLVED' for x in selection['screened']):selection['selection_status']+='__UNRESOLVED_EARLIER_RANKS'
        selection['updated_at']=now();atomic(selection_path,selection)
    if args.phase=='selection':return
    result=json.loads(events_path.read_text()) if events_path.exists() and not args.rebuild_events else {'policy_sha256':POLICY_SHA,'selection_file':str(selection_path.relative_to(ROOT)),'cohort_id':selection.get('cohort_id','initial-published-cohort-v1'),'slots':[],'status':'IN_PROGRESS'}
    result['status']='IN_PROGRESS_PRIORS' if args.phase in ('priors','all') else 'IN_PROGRESS_CURRENT_EVENTS'
    result['phase']=args.phase
    slots={x['slot_id']:x for x in result['slots']}
    for issuer in selection['issuers']:
        cik=issuer['cik']
        # A release at quarter-end can be filed in the next calendar window.
        history_start='2021-10-01' if args.phase in ('priors','all') else '2022-10-01'
        try:rows=c.submissions(cik,history_start,'2023-10-10')
        except Exception as e:rows=[];issuer_error=type(e).__name__+':'+str(e)
        else:issuer_error=None
        for wi,(start,end) in enumerate(c.policy['event_windows'],1):
            slot_id=cik+'-W'+str(wi)
            slot=slots.setdefault(slot_id,{'slot_id':slot_id,'cik':cik,'seed_symbol':issuer['historical_symbol'],'historical_symbol':issuer['historical_symbol'],'window_start':start,'window_end':end,'status':'PENDING','current':None,'prior':None,'candidate_events':[],'prior_candidates':[],'checks':{},'unresolved_reasons':[]})
            if slot['current'] is None:
                slot['candidate_events']=[];slot['unresolved_reasons']=[]
                extended_end=(date.fromisoformat(end)+timedelta(days=10)).isoformat()
                candidates=[r for r in rows if start<=r['filingDate']<=extended_end and r['form']=='8-K' and '2.02' in r.get('items','')]
                qualifying=[]
                for row in candidates:
                    try:ev=c.event(cik,row)
                    except Exception as e:
                        slot['candidate_events'].append({'accession':row['accessionNumber'],'error':type(e).__name__+':'+str(e)});slot['unresolved_reasons'].append('CANDIDATE_COLLECTION_FAILED');continue
                    slot['candidate_events'].append(ev)
                    if ev['classification']=='UNRESOLVED':slot['unresolved_reasons'].append('UNCLASSIFIED_ITEM_202_CANDIDATE')
                    if ev['classification']=='EARNINGS_RELEASE':
                        if ev.get('release_date') and start<=ev['release_date']<=end:qualifying.append(ev)
                        elif ev.get('release_date'):ev['window_rejection']='RELEASE_DATE_OUTSIDE_WINDOW'
                        else:slot['unresolved_reasons'].append('CANDIDATE_RELEASE_DATE_UNRESOLVED')
                if qualifying:
                    qualifying.sort(key=lambda e:(e['release_date'],e.get('acceptance_eastern') or '',e['accession']))
                    slot['current']=qualifying[0]
                    slot['earliest_selection_evidence']={'rule':'earliest verified release date then acceptance then accession; all original Item2.02 candidates through ten calendar days after window end inspected','candidate_accessions':[r['accessionNumber'] for r in candidates],'qualifying_accessions_in_order':[e['accession'] for e in qualifying],'complete_candidate_review':not slot['unresolved_reasons']}
                if slot['current'] is None:slot['unresolved_reasons'].append('CURRENT_RELEASE_UNRESOLVED' if candidates else 'NO_ITEM_202_ORIGINAL_IN_WINDOW')
                if issuer_error:slot['unresolved_reasons'].append('ISSUER_METADATA_COLLECTION_FAILED:'+issuer_error)
            current=slot['current']
            if current:
                slot['historical_symbol']=current['security']['historical_symbol']
                slot['checks'].update(current_release=True,identity=current['security']['status']=='VERIFIED_SINGLE_COMMON_CLASS',timing=current['daily_entry_invariant'] and current['release_date'] is not None,earliest_event=slot.get('earliest_selection_evidence',{}).get('complete_candidate_review',False))
                slot['status']='CURRENT_READY_PENDING_PRIOR'
            if args.phase in ('priors','all') and current and slot['prior'] is None:
                slot['prior_candidates']=[]
                pe=current.get('period_end')
                if pe:
                    target=date.fromisoformat(pe)
                    earliest=date(target.year-1,max(1,target.month-2),1).isoformat()
                    latest=min(current['filing_date'],date(target.year,target.month,1).isoformat())
                    priorrows=[r for r in rows if earliest<=r['filingDate']<latest and r['form']=='8-K' and '2.02' in r.get('items','')]
                    for row in priorrows:
                        try:prior=c.event(cik,row)
                        except Exception as e:
                            slot['prior_candidates'].append({'accession':row['accessionNumber'],'error':type(e).__name__+':'+str(e)});continue
                        match=period_match(current,prior)
                        slot['prior_candidates'].append({'event':prior,'match':match})
                        if match['verified']:
                            slot['prior']=prior;slot['prior_match']=match;break
                slot['checks']['prior_release']=slot['prior'] is not None
            if current:
                slot['checks']['period_identity']=bool(current.get('period_end'))
                slot['status']='SEC_JOIN_READY' if all(slot['checks'].get(k,False) for k in ['current_release','identity','timing','prior_release','period_identity','earliest_event']) else 'SEC_JOIN_UNRESOLVED' if args.phase in ('priors','all') else slot['status']
            else:slot['status']='SEC_JOIN_UNRESOLVED'
            result['slots']=list(slots.values());result['updated_at']=now();atomic(events_path,result)
            print(json.dumps({'phase':'events','slot':slot_id,'symbol':slot['historical_symbol'],'status':slot['status'],'period':current.get('period_end') if current else None,'prior':slot['prior']['period_end'] if slot['prior'] else None}),flush=True)
    result['status']='COLLECTION_FINISHED';result['updated_at']=now();atomic(events_path,result)

def period_match(current,prior):
    if prior.get('classification')!='EARNINGS_RELEASE' or not current.get('period_end') or not prior.get('period_end'):return {'verified':False,'reason':'missing_verified_earnings_period'}
    c=date.fromisoformat(current['period_end']);p=date.fromisoformat(prior['period_end'])
    kindc=current.get('period_evidence',{}).get('kind','');kindp=prior.get('period_evidence',{}).get('kind','')
    def scope(k):return 'quarter' if 'quarter' in k or k in ('three months','3 months') else 'year' if 'year' in k or k in ('twelve months','12 months') else k
    def scopes(e):
        s=set()
        for candidate in e.get('period_candidates',[]):
            if candidate['period_end']==e['period_end']:
                s.update(candidate.get('explicit_scopes',[]));s.add(scope(candidate['kind']))
        return s.intersection({'quarter','year'})
    common=scopes(current).intersection(scopes(prior))
    exact=(c.year==p.year+1 and (c.month,c.day)==(p.month,p.day) and bool(common))
    weeks=(c-p).days in range(357,373) and current.get('quarter_ordinal') is not None and current['quarter_ordinal']==prior.get('quarter_ordinal') and bool(common)
    before=prior['filing_date']<current['filing_date'] and bool(prior.get('acceptance_eastern'))
    return {'verified':bool(before and (exact or weeks)),'reason':'explicit_same_period_end_and_scope' if exact else 'explicit_same_fiscal_quarter_and_52_53_week_period' if weeks else 'PERIOD_MISMATCH_OR_AMBIGUOUS','matched_scope':'quarter' if 'quarter' in common else 'year' if 'year' in common else None,'common_explicit_scopes':sorted(common),'current_period_evidence':current.get('period_evidence'),'prior_period_evidence':prior.get('period_evidence'),'current_quarter':current.get('quarter_ordinal'),'prior_quarter':prior.get('quarter_ordinal'),'prior_filed_before_current':before,'numeric_measure_comparability':'NOT_CERTIFIED_BY_DOCUMENT_JOIN'}

def prior_fallbacks(c):
    """Named, source-motivated prior-form checks; no change to current eligibility."""
    path=HERE/'sec-events.json';result=json.loads(path.read_text())
    result.update(status='IN_PROGRESS_PRIOR_FORM_CHECKS',phase='fallbacks');atomic(path,result)
    targets={
        '0001789769-W1':('2021-11-15','2021-11-15',('8-K',)),
        '0001650372-W1':('2021-10-01','2021-12-31',('6-K',)),
        '0001650372-W2':('2022-01-01','2022-03-31',('6-K',)),
        '0001650372-W3':('2022-04-01','2022-06-30',('6-K',)),
        '0001650372-W4':('2022-07-01','2022-09-30',('6-K',)),
        '0001631282-W1':('2021-10-01','2021-12-31',('8-K','6-K')),
        '0001631282-W2':('2022-01-01','2022-03-31',('8-K','6-K')),
    }
    evidence={'policy_sha256':POLICY_SHA,'started_at':now(),'scope':'Known prior-document form differences; original prior clause does not require Item2.02. Current8-K Item2.02 eligibility unchanged.','targets':[]}
    team_rows=c.submissions('0001650372','2022-10-03','2022-10-03')
    team_transition=c.event('0001650372',next(r for r in team_rows if r['accessionNumber']=='0001650372-22-000071'))
    for slot in result['slots']:
        if slot['slot_id'] not in targets:continue
        start,end,forms=targets[slot['slot_id']]
        rows=c.submissions(slot['cik'],start,end,forms)
        record={'slot_id':slot['slot_id'],'metadata_start':start,'metadata_end':end,'forms':list(forms),'metadata_candidates':[{'accession':r['accessionNumber'],'form':r['form'],'filing_date':r['filingDate'],'items':r.get('items'),'primary_document':r['primaryDocument'],'metadata_file':r['metadata_file']} for r in rows],'inspected':[]}
        if slot['cik']=='0001650372':
            # Metadata filenames explicitly distinguish earnings releases from
            # AGM notices, later quarterly reports and other corporate events.
            rows=[r for r in rows if 'earningrelease' in r['primaryDocument'].lower()]
            record['candidate_narrowing']='prior6-K primary filename explicitly earningrelease; actual release and period verified from body'
            slot['corporate_continuity']={'source_cik':slot['cik'],'current_and_prior_same_SEC_registrant_history':True,'transition_accession':team_transition['accession'],'transition_primary_file':team_transition['primary_file'],'transition_excerpt':team_transition['item_202_excerpt'],'accounting_basis_change':'IFRS_TO_US_GAAP; numeric comparability not certified'}
            slot['accounting_measure_comparability']={'status':'ACCOUNTING_BASIS_CHANGED','note':'Original prior IFRS and current U.S.GAAP require an explicit measurement bridge before modeling; document join does not supply one.'}
            for candidate in slot['candidate_events']:
                if candidate['accession']==team_transition['accession']:
                    candidate.update(classification=team_transition['classification'],classification_evidence=team_transition['classification_evidence'])
            if team_transition['classification']=='ACCOUNTING_TRANSITION_PRESENTATION':
                slot['unresolved_reasons']=[r for r in slot['unresolved_reasons'] if r!='UNCLASSIFIED_ITEM_202_CANDIDATE']
                slot['checks']['earliest_event']=not slot['unresolved_reasons']
                slot['earliest_selection_evidence']['complete_candidate_review']=not slot['unresolved_reasons']
        for row in rows:
            try:
                prior=c.event(slot['cik'],row);match=period_match(slot['current'],prior)
                pair={'event':prior,'match':match};record['inspected'].append(pair)
                slot['prior_candidates'].append(pair)
                if match['verified'] and slot['prior'] is None:
                    slot['prior']=prior;slot['prior_match']=match;slot['checks']['prior_release']=True
            except Exception as e:record['inspected'].append({'accession':row['accessionNumber'],'error':type(e).__name__+':'+str(e)})
        slot['prior_form_coverage']={'forms':list(forms),'start':start,'end':end,'metadata_candidates':len(record['metadata_candidates']),'inspected_candidates':len(record['inspected'])}
        if not slot['prior']:
            slot['unresolved_reasons'].append('PRIOR_RETRIEVAL_OR_PERIOD_MATCH_UNRESOLVED_AFTER_TARGETED_ORIGINAL_FORM_CHECK')
        slot['status']='SEC_JOIN_READY' if all(slot['checks'].get(k,False) for k in ['current_release','identity','timing','prior_release','period_identity','earliest_event']) else 'SEC_JOIN_UNRESOLVED'
        evidence['targets'].append(record);evidence['updated_at']=now();atomic(HERE/'sec-prior-form-checks.json',evidence);atomic(path,result)
        print(json.dumps({'phase':'fallbacks','slot_id':slot['slot_id'],'prior':slot['prior']['accession'] if slot['prior'] else None,'status':slot['status']}),flush=True)
    for slot in result['slots']:
        slot.setdefault('accounting_measure_comparability',{'status':'NOT_AUDITED_FOR_MODEL_FEATURES','note':'Original fiscal-period document join does not certify GAAP/nonGAAP metric identity, equal duration, or usable feature values.'})
        if slot['slot_id']=='0001856430-W2':
            slot['accounting_measure_comparability']={'status':'QUARTER_DURATION_MISMATCH','current_quarter_weeks':13,'prior_quarter_weeks':14,'evidence_file':'research/equity-event-pilot-2026-09-10/manual-period-review.json','note':'Same fiscalQ4 original documents; no automatic normalization or like-length claim.'}
        if not slot['prior'] and slot['current'] and not any('PRIOR_' in r for r in slot['unresolved_reasons']):slot['unresolved_reasons'].append('PRIOR_RETRIEVAL_OR_PERIOD_MATCH_UNRESOLVED')
    result.update(status='COLLECTION_FINISHED_PENDING_INDEPENDENT_AUDIT',phase='collected',updated_at=now())
    atomic(path,result);atomic(HERE/'sec-progress.json',{'status':result['status'],'updated_at':now(),'policy_sha256':POLICY_SHA})

def finalize_collected(c):
    path=HERE/'sec-events.json';result=json.loads(path.read_text())
    mp=HERE/'sec-manual-decisions.json'
    manual=json.loads(mp.read_text()) if mp.exists() else {'decisions':{}}
    def refresh(cik,event):
        table=json.loads((ROOT/event['metadata_file']).read_text())
        if 'filings' in table:table=table['filings']['recent']
        i=table['accessionNumber'].index(event['accession'])
        row={k:v[i] for k,v in table.items() if isinstance(v,list) and len(v)==len(table['accessionNumber'])};row['metadata_file']=event['metadata_file']
        out=c.event(cik,row)
        decision=manual['decisions'].get(out['accession'])
        if decision:
            out['automated_classification_before_manual_review']=out['classification']
            out['classification']=decision['classification'];out['manual_classification_review']=decision
        return out
    for slot in result['slots']:
        slot['candidate_events']=[refresh(slot['cik'],e) if 'metadata_file' in e else e for e in slot['candidate_events']]
        if slot['current']:slot['current']=refresh(slot['cik'],slot['current'])
        if slot['prior']:
            slot['prior']=refresh(slot['cik'],slot['prior']);slot['prior_match']=period_match(slot['current'],slot['prior'])
            slot['checks']['prior_release']=slot['prior_match']['verified']
        current=slot['current'];preliminary=[];unknown=[]
        if current:
            for e in slot['candidate_events']:
                if e.get('classification')=='UNRESOLVED':unknown.append(e['accession'])
                if e.get('classification')=='PRELIMINARY':
                    day=e.get('release_date') or e['filing_date']
                    if slot['window_start']<=day<=slot['window_end'] and day<current['release_date']:
                        preliminary.append({'accession':e['accession'],'release_date':e.get('release_date'),'filing_date':e['filing_date'],'classification_evidence':e.get('classification_evidence'),'index_file':e['index_file'],'primary_file':e['primary_file'],'exhibit_file':e.get('rejected_exhibit_file')})
            slot['checks']['timing']=bool(current['daily_entry_invariant'] and current['release_date'])
            slot['checks']['identity']=current['security']['status']=='VERIFIED_SINGLE_COMMON_CLASS'
            slot['checks']['period_identity']=bool(current.get('period_end'))
            slot['checks']['full_nonpreliminary_release_selection']=not unknown and not any('COLLECTION_FAILED' in r for r in slot['unresolved_reasons'])
            slot['checks']['earliest_event']=slot['checks']['full_nonpreliminary_release_selection'] and not preliminary
            slot['earliest_selection_evidence']['complete_candidate_review']=not unknown
            slot['unresolved_reasons']=[r for r in slot['unresolved_reasons'] if r!='UNCLASSIFIED_ITEM_202_CANDIDATE']
            if unknown:slot['unresolved_reasons'].append('UNCLASSIFIED_ITEM_202_CANDIDATE')
            if preliminary:
                slot['event_selection_policy_ambiguity']={'status':'BLOCKED_EARLIEST_EVENT_ADMISSION','note':'Frozen policy does not explicitly exclude preliminary actual results. Selected full non-preliminary release remains unchanged, but cannot be claimed first earnings information.','predecessors':preliminary}
                if 'PRELIMINARY_ACTUAL_RESULTS_PREDECESSOR_POLICY_AMBIGUITY' not in slot['unresolved_reasons']:slot['unresolved_reasons'].append('PRELIMINARY_ACTUAL_RESULTS_PREDECESSOR_POLICY_AMBIGUITY')
        slot['status']='SEC_JOIN_READY' if all(slot['checks'].get(k,False) for k in ['current_release','identity','timing','prior_release','period_identity','earliest_event']) else 'SEC_JOIN_UNRESOLVED'
    result['counts']={
        'fixed_slots':len(result['slots']),
        'selected_full_earnings_releases':sum(bool(s['current']) for s in result['slots']),
        'original_prior_document_matches':sum(bool(s['prior']) and s['checks'].get('prior_release',False) for s in result['slots']),
        'historical_security_cover_success':sum(s['checks'].get('identity',False) for s in result['slots']),
        'daily_timing_proxy_success':sum(s['checks'].get('timing',False) for s in result['slots']),
        'exact_timestamp_mismatches_current':sum(bool(s['current']) and not s['current']['timing_match'] for s in result['slots']),
        'preliminary_predecessor_policy_ambiguity':sum(bool(s.get('event_selection_policy_ambiguity')) for s in result['slots']),
        'sec_join_ready_excluding_prices_and_accounting_feature_validation':sum(s['status']=='SEC_JOIN_READY' for s in result['slots']),
    }
    result.update(status='SEC_COLLECTION_COMPLETE_PENDING_INDEPENDENT_AUDIT',phase='finalized',updated_at=now(),collector_script_sha256=sha(Path(__file__).read_bytes()),manual_decisions_sha256=sha(mp.read_bytes()) if mp.exists() else None)
    digest=atomic(path,result)
    for filename in ('sec-events.json','sec-selection.json','sec-ranked-seed.json','sec-sources.json','sec-prior-form-checks.json'):
        f=HERE/filename
        if f.exists():(HERE/(filename+'.sha256')).write_text(sha(f.read_bytes())+'\n')
    correction_path=HERE/'sec-selection-correction.json';correction=json.loads(correction_path.read_text())
    correction.update(corrected_selection_sha256=sha((HERE/'sec-selection.json').read_bytes()),corrected_events_sha256=digest,script_after_sha256=sha(Path(__file__).read_bytes()),additional_parser_corrections=['Relevant Item2.02 section and dateline disambiguation','Full-document period extraction; explicit quarter/YTD and quarter/year scope','Guidance-only predecessors distinguished from actual releases','Press release and accounting companion retain actual exhibit identities','Exact clock conflicts retained; equal daily timing anchors separately verified','Preliminary actual-results predecessor ambiguity blocks earliest-event admission'])
    atomic(correction_path,correction)
    atomic(HERE/'sec-progress.json',{'status':result['status'],'updated_at':now(),'policy_sha256':POLICY_SHA,'sec_events_sha256':digest,'counts':result['counts']})
    print(json.dumps({'sha256':digest,'counts':result['counts']}),flush=True)

if __name__=='__main__':main()
