"""Small Tiingo identifier-recovery queries sharing the price collector quota."""
import argparse
from datetime import datetime, timedelta
import json
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, Request, build_opener

from price_data import ROOT, HERE, RAW, now, sha, symbol, read_key, NoRedirect, tls_context


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('symbols', nargs='+')
    args = ap.parse_args()
    tickers = list(dict.fromkeys(symbol(s) for s in args.symbols))
    assert 1 <= len(tickers) <= 10
    p = HERE / 'price-manifest.json'
    manifest = json.loads(p.read_text())
    metadata = manifest.setdefault('identity_metadata', {})
    key = read_key(ROOT / '.env')
    opener = build_opener(HTTPSHandler(context=tls_context()), NoRedirect())
    def save():
        manifest['updated_utc'] = now().isoformat()
        p.write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    for ticker in tickers:
        if ticker in metadata:
            continue
        recent = [r for r in manifest['requests'] if datetime.fromisoformat(r['requested_utc']) > now()-timedelta(hours=1,seconds=5)]
        waiting = manifest.get('server_retry_after_utc')
        if len(recent) >= 50 or (waiting and now() < datetime.fromisoformat(waiting)):
            print(json.dumps({'status':'WAIT_FOR_EXISTING_SHARED_QUOTA','symbol':ticker}))
            break
        url = f'https://api.tiingo.com/tiingo/daily/{ticker.lower()}'
        rec = {'kind':'identity_metadata','symbol':ticker,'url':url,'requested_utc':now().isoformat()}
        manifest['requests'].append(rec)
        save()
        try:
            with opener.open(Request(url, headers={'Authorization':f'Token {key}','Accept':'application/json',
                    'User-Agent':'BoringAlpha personal equity research'}),timeout=20) as response:
                assert response.status==200 and response.geturl()==url
                raw=response.read(100_001)
                rec['http_status']=response.status
            assert len(raw)<=100_000 and key.encode() not in raw
            payload=json.loads(raw)
            assert isinstance(payload,dict) and payload.get('ticker','').upper()==ticker
            path=RAW/(ticker+'-identity.json')
            assert not path.exists()
            path.write_bytes(raw)
            rec.update(path=str(path.relative_to(ROOT)),sha256=sha(path),bytes=len(raw))
            metadata[ticker]={'status':'DOWNLOADED',**{k:rec[k] for k in ['path','sha256']},
                'scope':'Current provider identifier recovery only; not a historical trading feature or membership criterion.'}
        except HTTPError as exc:
            rec['http_status']=exc.code
            metadata[ticker]={'status':'HTTP_ERROR','http_status':exc.code}
            if exc.code==429:
                value=exc.headers.get('Retry-After')
                delay=max(3606,int(value)) if value and value.isdecimal() else 3606
                manifest['server_retry_after_utc']=(now()+timedelta(seconds=delay)).isoformat()
        except Exception as exc:
            rec['error_class']=type(exc).__name__
            metadata[ticker]={'status':'FAILED','error_class':type(exc).__name__}
        rec['finished_utc']=now().isoformat()
        save()
        print(json.dumps({'symbol':ticker,'status':metadata[ticker]['status']}))
        if rec.get('http_status')==429:
            break


if __name__=='__main__':
    main()
