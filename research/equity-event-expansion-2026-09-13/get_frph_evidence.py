"""Two public issuer publications for the unresolved original cohort member."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, build_opener, HTTPSHandler

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from tools.check_ba002_seen_prices import tls_context
from tools.tiingo_seen_reference import NoRedirect

URLS={
    'frph-original-release-2019-08-05.html':'https://www.globenewswire.com/news-release/2019/08/05/1896995/0/en/frp-holdings-inc-nasdaq-frph-announces-results-for-the-second-quarter-and-six-months-ended-june-30-2019.html',
    'frph-original-2019-q1-10q.pdf':'https://www.frpdev.com/wp-content/uploads/2020/08/frph-20190331-10q.pdf',
}

def main():
    rawdir=ROOT/'data/snapshots/equity-event-expansion-2026-09-13/issuer-evidence'
    rawdir.mkdir(parents=True,exist_ok=True)
    path=HERE/'frph-issuer-evidence.json'
    out=json.loads(path.read_text()) if path.exists() else {'sources':{},'requests':[],
        'scope':'Original issuer-authored publications for2019cohort eligibility only. Blocked SEC document is not retried; these independent public sources do not substitute for2020–2023 SEC model inputs.'}
    opener=build_opener(HTTPSHandler(context=tls_context()),NoRedirect())
    failures=[]
    for name,url in sorted(URLS.items(), key=lambda item: not item[0].endswith('.pdf')):
        if name in out['sources']:continue
        attempts=[r for r in out['requests'] if r['url']==url]
        if any(r.get('status') in (401,403,429) for r in attempts) or len(attempts)>=2:
            failures.append({'url':url,'reason':'No further authorized retry'})
            continue
        request={'url':url,'started_utc':datetime.now(timezone.utc).isoformat()}
        out['requests'].append(request)
        try:
            with opener.open(Request(url,headers={'User-Agent':'BoringAlphaResearch/0.1 (personal financial research)'}),timeout=20) as response:
                assert response.status==200 and response.geturl()==url
                body=response.read(15_000_001);assert len(body)<=15_000_000
                request['status']=200
            target=rawdir/name;assert not target.exists();target.write_bytes(body)
            out['sources'][name]={'url':url,'file':str(target.relative_to(ROOT)),
                'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),
                'retrieved_utc':datetime.now(timezone.utc).isoformat()}
        except Exception as exc:
            request.update(status=getattr(exc,'code',None),error=type(exc).__name__)
            path.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
            failures.append({'url':url,'error':type(exc).__name__})
            continue
        path.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'sources':list(out['sources']),'failures':failures,'additional_SEC_requests':0}))

if __name__=='__main__':main()
