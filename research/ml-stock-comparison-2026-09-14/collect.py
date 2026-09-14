#!/usr/bin/env python3
"""Bounded cached collectors. Separate source manifests; secrets only on stdin."""
from datetime import datetime, timedelta, timezone
import hashlib,json,re,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlencode
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];RAW=ROOT/'data/snapshots'/HERE.name
PREP=HERE.parent/'ml-free-data-preparation-2026-09-13';OLD=HERE.parent/'ml-free-data-feasibility-2026-09-13'
sys.path.insert(0,str(OLD))
from probe import curl,sha,write

def now():return datetime.now(timezone.utc)
def load(p,default):return json.loads(p.read_text()) if p.exists() else default

def tiingo(limit):
    cohort=load(PREP/'next-cohort.json',{})['rows'];manifest_path=HERE/'price-manifest.json'
    m=load(manifest_path,dict(requests=[],symbols={},new_paid_data_usd=0))
    key=None
    for line in (ROOT/'.env').read_text().splitlines():
        match=re.fullmatch(r'\s*(?:export\s+)?TIINGO_API_KEY\s*=\s*(.*?)\s*',line)
        if match:key=match[1].strip('\"\'')
    assert key and re.fullmatch(r'[A-Za-z0-9_-]+',key)
    cached=load(PREP/'tiingo-manifest.json',{})
    jobs=[r['Symbol'] for r in cohort]
    # Additional evidenced aliases/children only after the request list exists.
    jobs+=load(HERE/'extra-price-requests.json',{}).get('symbols',[])
    jobs=list(dict.fromkeys(jobs));made=0
    for symbol in jobs:
        if symbol in m['symbols']:continue
        if 'tiingo-'+symbol in cached:
            r=cached['tiingo-'+symbol];assert sha((ROOT/r['file']).read_bytes())==r['sha256']
            m['symbols'][symbol]=r|dict(status='REUSED_SAMPLE',source_manifest=str((PREP/'tiingo-manifest.json').relative_to(ROOT)))
            write(manifest_path,m);continue
        if made>=limit or len(m['requests'])>=150:break
        recent=[r for r in m['requests'] if now()-datetime.fromisoformat(r['at'])<timedelta(hours=1,seconds=5)]
        if len(recent)>=50:
            m['resume_after_utc']=(datetime.fromisoformat(recent[0]['at'])+timedelta(hours=1,seconds=6)).isoformat();write(manifest_path,m);break
        if m.get('provider_stop'):break
        assert re.fullmatch(r'[A-Z0-9.-]+',symbol)
        url=f'https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?'+urlencode(dict(startDate='2018-05-01',endDate='2023-12-31',format='json',resampleFreq='daily'))
        r=dict(symbol=symbol,url=url,at=now().isoformat());m['requests'].append(r);write(manifest_path,m)
        p=subprocess.run(['curl','--config','-','--silent','--show-error','--proto','=https','--max-time','35','--max-filesize','10000000','--write-out','\n%{http_code}',url],input=('header = "Authorization: Token '+key+'"\n').encode(),capture_output=True,timeout=40)
        body,_,status=p.stdout.rpartition(b'\n');assert key.encode() not in body
        r.update(http_status=int(status) if status.isdigit() else None,curl_exit=p.returncode,response_bytes=len(body));made+=1
        if not p.returncode and r['http_status']==200:
            data=json.loads(body);assert isinstance(data,list)
            assert all('2018-05-01'<=x['date'][:10]<'2024-01-01' for x in data)
            path=RAW/('tiingo-'+symbol+'.json');path.write_bytes(body)
            r.update(file=str(path.relative_to(ROOT)),sha256=sha(body),rows=len(data),status='DOWNLOADED' if data else 'EMPTY_HISTORY')
        else:
            r['status']='HTTP_OR_TRANSPORT_ERROR'
            if r['http_status'] in [401,403,429]:m['provider_stop']=r['http_status']
        m['symbols'][symbol]=dict(r);write(manifest_path,m)
        print(json.dumps({k:r.get(k) for k in ['symbol','http_status','rows','status']}),flush=True);time.sleep(.35)
    print(json.dumps(dict(requests=len(m['requests']),symbols=len(m['symbols']),resume_after=m.get('resume_after_utc'),provider_stop=m.get('provider_stop'))),flush=True)

def sec():
    mapping=load(HERE/'identity-candidates.json',{})['rows'];mp=HERE/'sec-manifest.json';m=load(mp,{})
    old=load(OLD/'sec-manifest.json',{})
    bycik={str(int(r['cik'])):r for r in old.values() if r.get('file')}
    for r in mapping:
        if not r.get('cik'):continue
        cik=str(r['cik']).zfill(10)
        if cik in m:continue
        if str(int(cik)) in bycik:
            rec=bycik[str(int(cik))];assert sha((ROOT/rec['file']).read_bytes())==rec['filtered_sha256'];m[cik]=rec|dict(status='REUSED_SAMPLE');write(mp,m);continue
        rec,b=curl(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
        if b is not None:
            d=json.loads(b);assert int(d['cik'])==int(cik)
            kept=dict(cik=d['cik'],entityName=d['entityName'],facts={});count=0
            for ns,concepts in d.get('facts',{}).items():
                kept['facts'][ns]={}
                for tag,c in concepts.items():
                    units={u:[x for x in rs if x.get('filed','9999')<'2024-01-01' and x.get('end','9999')<'2024-01-01'] for u,rs in c.get('units',{}).items()}
                    units={u:rs for u,rs in units.items() if rs}
                    if units:kept['facts'][ns][tag]=dict(units=units);count+=sum(map(len,units.values()))
            path=RAW/f'CIK{cik}-companyfacts-pre2024.json';write(path,kept)
            rec.update(file=str(path.relative_to(ROOT)),filtered_sha256=sha(path.read_bytes()),cik=cik,entity_name=kept['entityName'],retained_fact_rows=count,later_filing_values_discarded=True)
        m[cik]=rec;write(mp,m)
        print(json.dumps(dict(cik=cik,symbol=r['Symbol'],http_status=rec['http_status'],rows=rec.get('retained_fact_rows'))),flush=True);time.sleep(.35)

if __name__=='__main__':
    if sys.argv[1]=='tiingo':tiingo(int(sys.argv[2]) if len(sys.argv)>2 else 50)
    elif sys.argv[1]=='sec':sec()


def submissions():
    mp=HERE/'submissions-manifest.json';m=load(mp,{})
    for r in load(HERE/'identity-candidates.json',{})['rows']:
        cik=r.get('cik')
        if not cik or cik in m:continue
        rec,b=curl(f'https://data.sec.gov/submissions/CIK{cik}.json')
        if b is not None:
            d=json.loads(b);assert int(d['cik'])==int(cik)
            path=RAW/f'CIK{cik}-submissions.json';path.write_bytes(b)
            rec.update(file=str(path.relative_to(ROOT)),sha256=sha(b),cik=cik,name=d['name'],tickers=d.get('tickers'),former_names=d.get('formerNames'),metadata_only=True)
        m[cik]=rec;write(mp,m);print(json.dumps(dict(cik=cik,status=rec['http_status'],name=rec.get('name'))),flush=True);time.sleep(.4)

if __name__=='__main__' and sys.argv[1]=='submissions':submissions()
