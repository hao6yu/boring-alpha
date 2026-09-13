#!/usr/bin/env python3
"""Fetch two original SEC sources for the authorized PTN actions-only check."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import ssl
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / 'data/snapshots/equity-event-test-2026-09-10/sec'
URLS = [
    'https://www.sec.gov/Archives/edgar/data/911216/000165495424012498/0001654954-24-012498-index.html',
    'https://www.sec.gov/Archives/edgar/data/911216/000165495424012498/ptn_10k.htm',
]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def main():
    def sha(b): return hashlib.sha256(b).hexdigest()
    def now(): return datetime.now(timezone.utc).isoformat()
    path = HERE / 'ptn-actions-sources.json'
    manifest = json.loads(path.read_text()) if path.exists() else {
        'scope': 'Original FY2024 10-K/index, corporate-action and identity evidence only; no prices or returns.',
        'fixed_urls': URLS, 'attempts': [], 'sources': []}
    assert manifest['fixed_urls'] == URLS
    def save():
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        temp.replace(path)
    save()
    context = ssl.create_default_context()
    if not context.cert_store_stats()['x509_ca']:
        context = ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    RAW.mkdir(parents=True, exist_ok=True)
    for url in URLS:
        existing = next((s for s in manifest['sources'] if s['url'] == url), None)
        if existing:
            assert sha((ROOT / existing['file']).read_bytes()) == existing['sha256']
            continue
        record = {'url': url, 'started_at': now()}
        manifest['attempts'].append(record)
        save()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'BoringAlphaResearch/0.1 (personal financial research)', 'Accept-Encoding': 'identity'})
            with opener.open(req, timeout=20) as response:
                assert response.status == 200
                b = response.read(16 * 1024 * 1024 + 1)
                assert len(b) <= 16 * 1024 * 1024
                length = response.headers.get('Content-Length')
                assert length is None or int(length) == len(b)
                output = RAW / (sha(url.encode()) + Path(url).suffix)
                assert not output.exists()
                output.write_bytes(b)
                record.update(status=200, file=str(output.relative_to(ROOT)), bytes=len(b), sha256=sha(b), received_at=now())
                manifest['sources'].append(dict(record))
                save()
                print(json.dumps({'file': record['file'], 'bytes': len(b), 'sha256': record['sha256']}))
        except Exception as exc:
            record.update(error=type(exc).__name__, failed_at=now())
            save()
            raise RuntimeError('public_SEC_actions_fetch_failed') from None
        time.sleep(.3)

if __name__ == '__main__': main()
