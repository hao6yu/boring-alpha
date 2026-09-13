#!/usr/bin/env python3
"""Targeted public SEC source inspection; no prices, credentials or returns."""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = ROOT / 'research/equity-event-pilot-2026-09-10'
RAW = ROOT / 'data/snapshots/equity-event-repair-2026-09-10/sec'
POLICY_SHA = '023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05'
MAX_BYTES = 8 * 1024 * 1024

def sha(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

class Fetch:
    def __init__(self):
        policy = (HERE / 'policy.json').read_bytes()
        if sha(policy) != POLICY_SHA: raise ValueError('policy_hash_mismatch')
        self.deadline = datetime.fromisoformat(json.loads(policy)['deadline_utc'].replace('Z', '+00:00'))
        self.manifest_path = HERE / 'dtss-sources.json'
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {
            'policy_sha256': POLICY_SHA, 'sources': {}, 'attempts': [], 'cache_reads': [],
            'original_source_manifest_sha256': sha((OLD / 'sec-sources.json').read_bytes())}
        self.old = json.loads((OLD / 'sec-sources.json').read_text())['sources']
        context = ssl.create_default_context()
        if not context.cert_store_stats()['x509_ca']:
            context = ssl.create_default_context(cafile='/etc/ssl/cert.pem')
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
        self.last = 0.0

    def get(self, url):
        u = urllib.parse.urlsplit(url)
        if u.scheme != 'https' or u.netloc not in {'www.sec.gov', 'data.sec.gov'} or u.username or u.fragment:
            raise ValueError('not_public_SEC_https')
        for origin, sources in [('repair', self.manifest['sources']), ('original_pilot', self.old)]:
            rec = sources.get(url)
            if rec and rec.get('status') == 200:
                path = ROOT / rec['file']
                b = path.read_bytes()
                if sha(b) != rec['sha256']: raise ValueError('cached_hash_mismatch')
                if origin == 'original_pilot':
                    self.manifest['cache_reads'].append({'url': url, 'file': rec['file'], 'sha256': rec['sha256'], 'read_at': now()})
                    save(self.manifest_path, self.manifest)
                return b, rec['file']
        for attempt in (1, 2):
            if (self.deadline - datetime.now(timezone.utc)).total_seconds() < 22:
                raise RuntimeError('deadline')
            time.sleep(max(0, .26 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            rec = {'url': url, 'started_at': now(), 'attempt': attempt}
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'BoringAlphaResearch/0.1 (personal financial research)', 'Accept-Encoding': 'identity'})
                with self.opener.open(req, timeout=20) as response:
                    if response.status != 200: raise ValueError('unexpected_status')
                    b = response.read(MAX_BYTES + 1)
                    if len(b) > MAX_BYTES: raise ValueError('response_size_limit')
                    length = response.headers.get('Content-Length')
                    if length is not None and int(length) != len(b): raise ValueError('incomplete_response')
                    path = RAW / (sha(url.encode()) + (Path(u.path).suffix or '.bin'))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists(): raise ValueError('orphan_or_duplicate_output')
                    path.write_bytes(b)
                    rec.update(status=200, bytes=len(b), sha256=sha(b), file=str(path.relative_to(ROOT)), completed_at=now())
                    self.manifest['sources'][url] = rec
                    self.manifest['attempts'].append(rec)
                    save(self.manifest_path, self.manifest)
                    return b, rec['file']
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as exc:
                code = getattr(exc, 'code', None)
                rec.update(status=code, error=type(exc).__name__, failed_at=now())
                self.manifest['attempts'].append(rec)
                save(self.manifest_path, self.manifest)
                transient = (isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)) and code is None) or code in (500, 502, 503, 504)
                if not transient or attempt == 2: raise RuntimeError('SEC_request_failed') from None
                time.sleep(1)

def main():
    spec = importlib.util.spec_from_file_location('original_sec_parser', OLD / 'sec_collect.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # Only its offline HTML parser is used.
    accessions = ['0001213900-21-058737', '0001213900-22-006734', '0001213900-21-060038']
    plan = {'policy_sha256': POLICY_SHA, 'reason': 'Inspect original DTSS report/registration filing indices for separate earnings-release exhibits; financial statements alone cannot satisfy the prior-release requirement.',
            'queries': [f'https://www.sec.gov/Archives/edgar/data/1631282/{acc.replace("-", "")}/{acc}-index.html' for acc in accessions]}
    plan_path = HERE / 'dtss-inspection-plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan: raise ValueError('plan_changed')
    if not plan_path.exists(): save(plan_path, plan)
    client = Fetch()
    result = {'policy_sha256': POLICY_SHA, 'plan_sha256': sha(plan_path.read_bytes()), 'indices': []}
    for acc, url in zip(accessions, plan['queries']):
        b, path = client.get(url)
        page = module.HTML(b.decode('utf-8', 'replace'))
        record = {'accession': acc, 'url': url, 'file': path, 'sha256': sha(b), 'document_rows': page.rows, 'links': page.links}
        result['indices'].append(record)
        save(HERE / 'dtss-index-inspection.json', result)
        print(json.dumps({'accession': acc, 'file': path, 'document_rows': page.rows}), flush=True)

if __name__ == '__main__': main()
