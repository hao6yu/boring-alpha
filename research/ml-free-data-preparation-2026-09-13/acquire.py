#!/usr/bin/env python3
"""Bounded original-filing and existing-entitlement action data acquisition."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=HERE.parent/'ml-free-data-feasibility-2026-09-13'
RAW=ROOT/'data/snapshots'/HERE.name
sys.path.insert(0,str(OLD))
from probe import COMPANIES, curl, write, sha


def fetch(label,url,key=None):
    mp=HERE/('tiingo-manifest.json' if label.startswith('tiingo-') else 'sec-manifest.json')
    manifest=json.loads(mp.read_text()) if mp.exists() else {}
    if label in manifest:
        r=manifest[label]
        if not r.get('file'): return None
        b=(ROOT/r['file']).read_bytes();assert sha(b)==r['sha256'];return b
    if key:
        assert url.startswith('https://api.tiingo.com/tiingo/daily/')
        args=['curl','--config','-','--silent','--show-error','--proto','=https','--max-time','40',
              '--max-filesize','10000000','--write-out','\n%{http_code}',url]
        p=subprocess.run(args,input=('header = "Authorization: Token '+key+'"\n').encode(),capture_output=True,timeout=45)
        b,_,code=p.stdout.rpartition(b'\n')
        assert key.encode() not in b
        meta=dict(url=url,http_status=int(code) if code.isdigit() else None,curl_exit=p.returncode,
                  response_bytes=len(b),at=datetime.now(timezone.utc).isoformat())
        if p.returncode or meta['http_status']!=200:b=None
    else:
        assert url.startswith(('https://data.sec.gov/','https://www.sec.gov/'))
        meta,b=curl(url)
    if b is not None:
        suffix='.json' if label.startswith(('submissions','tiingo')) else '.html'
        path=RAW/(label+suffix);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
        meta.update(file=str(path.relative_to(ROOT)),sha256=sha(b))
    manifest[label]=meta;write(mp,manifest)
    print(json.dumps(dict(label=label,status=meta['http_status'],bytes=meta['response_bytes'])),flush=True)
    time.sleep(.25)
    return b


def filings():
    previous=json.loads((OLD/'fundamental-coverage.json').read_text())
    jobs=[r for r in previous if r['label'] in ['META','JNJ']]
    selected={}
    for label in ['META','JNJ']:
        cik=next(c for s,c,_ in COMPANIES if s==label)
        b=fetch('submissions-'+label,f'https://data.sec.gov/submissions/CIK{cik}.json')
        if b is None:continue
        d=json.loads(b);tables=[d['filings']['recent']]
        required={j['assets']['accn'] for j in jobs if j['label']==label}
        for old in d['filings']['files']:
            if old['filingFrom'] <= '2023-12-31' and old['filingTo'] >= '2019-01-01':
                ob=fetch('submissions-'+old['name'],'https://data.sec.gov/submissions/'+old['name'])
                if ob is not None:tables.append(json.loads(ob))
        for table in tables:
            for i,acc in enumerate(table['accessionNumber']):
                if acc not in required:continue
                row={k:v[i] for k,v in table.items() if isinstance(v,list) and len(v)==len(table['accessionNumber'])}
                assert row['filingDate'] < '2024-01-01'
                url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-","")}/{row["primaryDocument"]}'
                selected[acc]=dict(label=label,cik=cik,url=url,**row)
                fetch('filing-'+acc,url)
    write(HERE/'selected-filings.json',selected)


def tiingo():
    # Reuse only the already configured Tiingo key; no signup/plan changes.
    key=None
    for line in (ROOT/'.env').read_text().splitlines():
        m=re.fullmatch(r'\s*(?:export\s+)?TIINGO_API_KEY\s*=\s*(.*?)\s*',line)
        if m:key=m[1].strip('"\'')
    assert key and re.fullmatch(r'[A-Za-z0-9_-]+',key)
    # Children are needed to value GE distributions; BBBYQ is the original
    # bankrupt issuer's history, not a new investment candidate.
    for symbol in [s for s,_,_ in COMPANIES]+['GEHC','BBBYQ','WAB']:
        start={'GEHC':'2023-01-04','WAB':'2019-02-25'}.get(symbol,'2018-05-01')
        url=f'https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?'+urlencode(dict(startDate=start,endDate='2023-12-31',resampleFreq='daily',format='json'))
        b=fetch('tiingo-'+symbol,url,key)
        if b is not None:
            rows=json.loads(b)
            assert isinstance(rows,list)
            assert all(start <= r['date'][:10] < '2024-01-01' for r in rows)
    key=None


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='filings':filings()
    elif mode=='tiingo':tiingo()
