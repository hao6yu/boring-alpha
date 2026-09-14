"""Capture the four fixed public archives with shared byte/time limits."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = ROOT / 'data/snapshots/insider-purchase-test-2026-09-13'
POLICY_SHA = '6519c99f01e44c233f0034f2f963477d883fa3c97d648e72229c26760bab7a42'


def now():
    return datetime.now(timezone.utc)


def atomic(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2) + '\n')
    tmp.replace(path)


def policy():
    b = (HERE / 'experiment-policy.json').read_bytes()
    assert hashlib.sha256(b).hexdigest() == POLICY_SHA
    return json.loads(b)


def run():
    p = policy()
    RAW.mkdir(parents=True, exist_ok=True)
    mp = HERE / 'download-manifest.json'
    m = json.loads(mp.read_text()) if mp.exists() else {
        'policy_sha256': POLICY_SHA, 'new_paid_data_usd': 0, 'files': [],
        'created_at_utc': now().isoformat()}
    assert m['policy_sha256'] == POLICY_SHA
    deadline = datetime.fromisoformat(p['deadline_utc'])
    for item in p['data_files']:
        previous = next((x for x in m['files'] if x['name'] == item['name']), None)
        if previous:
            if previous['status'] != 'VERIFIED':
                raise RuntimeError('Prior incomplete/failed source preserved; no automatic retry')
            continue
        used = sum(x['downloaded_bytes'] for x in m['files'])
        if now() >= deadline or used + item['expected_bytes'] > p['max_download_bytes']:
            raise RuntimeError('Time/download budget does not permit next source')
        rec = {**item, 'started_at_utc': now().isoformat(), 'status': 'DOWNLOADING',
               'downloaded_bytes': 0, 'new_paid_data_usd': 0}
        m['files'].append(rec)
        partial = RAW / (item['name'] + '.part')
        assert not partial.exists()
        rec['file'] = str(partial.relative_to(ROOT))
        atomic(mp, m)
        md5, sha = hashlib.md5(), hashlib.sha256()
        last_update = time.monotonic()
        print('Starting ' + item['name'], flush=True)
        try:
            req = Request(item['url'], headers={'User-Agent': 'BoringAlphaResearch/0.1',
                                               'Accept-Encoding': 'identity'})
            with urlopen(req, timeout=45, context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')) as response:
                rec['http_status'] = response.status
                rec['response_host'] = urlsplit(response.url).hostname
                rec['content_type'] = response.headers.get('Content-Type')
                assert response.status == 200
                length = response.headers.get('Content-Length')
                if length is not None:
                    assert int(length) == item['expected_bytes'], 'Unexpected archive size'
                with partial.open('wb') as dst:
                    while True:
                        if now() >= deadline:
                            raise RuntimeError('Study deadline reached')
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        rec['downloaded_bytes'] += len(block)
                        if used + rec['downloaded_bytes'] > p['max_download_bytes']:
                            raise RuntimeError('Shared source byte limit exceeded')
                        if rec['downloaded_bytes'] > item['expected_bytes']:
                            raise RuntimeError('Source exceeds fixed metadata size')
                        dst.write(block)
                        md5.update(block)
                        sha.update(block)
                        if time.monotonic() - last_update >= 10:
                            rec['updated_at_utc'] = now().isoformat()
                            atomic(mp, m)
                            print(item['name'] + ': ' + str(rec['downloaded_bytes']) + '/' + str(item['expected_bytes']), flush=True)
                            last_update = time.monotonic()
            rec['md5'] = md5.hexdigest()
            rec['sha256'] = sha.hexdigest()
            assert rec['downloaded_bytes'] == item['expected_bytes'], 'Incomplete archive'
            assert item['expected_checksum']['type'] == 'MD5'
            assert rec['md5'] == item['expected_checksum']['value'], 'Dataset checksum mismatch'
            final = RAW / item['name']
            partial.replace(final)
            rec['file'] = str(final.relative_to(ROOT))
            rec['status'] = 'VERIFIED'
            rec['completed_at_utc'] = now().isoformat()
            atomic(mp, m)
            print('Verified ' + item['name'], flush=True)
        except Exception as exc:
            rec['status'] = 'FAILED'
            rec['error_class'] = type(exc).__name__
            rec['error'] = str(exc).split('?')[0]
            rec['failed_at_utc'] = now().isoformat()
            atomic(mp, m)
            raise
    m['status'] = 'ALL_FIXED_ARCHIVES_VERIFIED'
    m['downloaded_bytes'] = sum(x['downloaded_bytes'] for x in m['files'])
    atomic(mp, m)
    print(json.dumps({'status': m['status'], 'bytes': m['downloaded_bytes']}), flush=True)


if __name__ == '__main__':
    run()
