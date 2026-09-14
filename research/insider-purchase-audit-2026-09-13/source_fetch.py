"""Bounded public-source capture for a field audit; no prices or return model."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = ROOT / 'data/snapshots/insider-purchase-audit-2026-09-13'
POLICY = json.loads((HERE / 'audit-policy.json').read_text())
MANIFEST = HERE / 'sources.json'


def fetch(url, name):
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    for r in manifest:
        if r['url'] == url:
            if r['status'] != 200:
                raise RuntimeError('Previously unsuccessful URL: ' + url)
            b = (ROOT / r['file']).read_bytes()
            assert hashlib.sha256(b).hexdigest() == r['sha256']
            return b
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(POLICY['created_at_utc']) + timedelta(hours=POLICY['max_elapsed_hours'])
    if now >= deadline:
        raise RuntimeError('Audit deadline exceeded')
    is_sec = urllib.parse.urlsplit(url).hostname in {'www.sec.gov', 'data.sec.gov'}
    if is_sec and sum(x['is_sec'] for x in manifest) >= POLICY['max_sec_http_requests']:
        raise RuntimeError('SEC request budget exceeded')
    if is_sec and any(x['is_sec'] and x['status'] == 429 for x in manifest):
        raise RuntimeError('SEC rate restriction recorded; stop collection')
    # The quarter ZIP returned 403. Do not retry it or another bulk archive.
    # A recorded sample amendment permits individual public filing documents.
    if is_sec and any(x['is_sec'] and x['status'] == 403 for x in manifest):
        amendment = HERE / 'sample-amendment.json'
        denied_filings = any(x['is_sec'] and x['status'] == 403 and
                            '/Archives/' in x['url'] for x in manifest)
        if denied_filings or not amendment.exists() or '/Archives/' not in url:
            raise RuntimeError('SEC access restriction outside amended individual-filing scope')
    remaining = POLICY['max_total_download_bytes'] - sum(x.get('bytes', 0) for x in manifest)
    if remaining <= 0:
        raise RuntimeError('Download budget exceeded')
    if is_sec:
        time.sleep(0.55)
    RAW.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={
        'User-Agent': 'BoringAlphaResearch/0.1 (personal financial research)',
        'Accept-Encoding': 'identity'})
    rec = {'url': url, 'requested_at_utc': now.isoformat(), 'is_sec': is_sec}
    try:
        with urllib.request.urlopen(request, timeout=35,
                                    context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')) as response:
            b = response.read(remaining + 1)
            if len(b) > remaining:
                raise RuntimeError('Response exceeds remaining download budget')
            path = RAW / name
            path.write_bytes(b)
            rec.update(status=response.status, bytes=len(b), file=str(path.relative_to(ROOT)),
                       sha256=hashlib.sha256(b).hexdigest(), final_url=response.url,
                       content_type=response.headers.get('Content-Type'))
    except urllib.error.HTTPError as e:
        rec.update(status=e.code, error=str(e))
        manifest.append(rec)
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
        raise
    except Exception as e:
        rec.update(status='ERROR', error=str(e))
        manifest.append(rec)
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
        raise
    manifest.append(rec)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    return b
