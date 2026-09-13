#!/usr/bin/env python3
"""Read-only PTN metadata and cost probe; no market-data download or billing change."""
import base64
import getpass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from fetch_market_data import _CONTEXT
from databento_history_probe import NoRedirect

DATASETS = ['EQUS.SUMMARY', 'XASE.PILLAR', 'XNAS.ITCH']
HERE = Path(__file__).resolve().parent
RAW = ROOT / 'data/snapshots/equity-event-test-2026-09-10/databento-probe'


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    key = getpass.getpass('Databento key (hidden, process memory only): ').strip()
    auth = 'Basic ' + base64.b64encode((key + ':').encode()).decode()
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
    RAW.mkdir(parents=True, exist_ok=True)
    out = {'started_utc': now(), 'scope': 'PTN metadata and quotes only; no purchases or data requests', 'requests': []}
    jobs = []
    for ds in DATASETS:
        jobs.append(('metadata.get_dataset_range', {'dataset': ds}))
        jobs.append(('metadata.list_schemas', {'dataset': ds}))
    for method, params in jobs:
        url = 'https://hist.databento.com/v0/' + method + '?' + urllib.parse.urlencode(params)
        record = {'method': method, 'params': params, 'requested_utc': now()}
        req = urllib.request.Request(url, headers={'Authorization': auth, 'User-Agent': 'BoringAlpha-PTN-Qualification/1.0'})
        try:
            try:
                response = opener.open(req, timeout=25)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                data = response.read(2_000_001)
                record['http_status'] = response.code
            if len(data) > 2_000_000 or key.encode() in data or auth.encode() in data:
                record['status'] = 'REJECTED_UNSAFE_OR_OVERSIZE'
            elif record['http_status'] == 200:
                payload = json.loads(data)
                path = RAW / (params['dataset'] + '-' + method.split('.')[-1] + '.json')
                if path.exists():
                    raise RuntimeError('Refuse to overwrite archived response')
                path.write_bytes(data)
                record.update(status='OK', path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(data).hexdigest(), payload=payload)
            else:
                lower = data.lower()
                record.update(status='HTTP_ERROR', mentions_auth=b'auth' in lower or b'api key' in lower,
                              mentions_license=b'licens' in lower or b'agreement' in lower,
                              mentions_dataset=b'dataset' in lower)
        except Exception as exc:
            record.update(status='ERROR', error_class=type(exc).__name__)
        record['finished_utc'] = now()
        out['requests'].append(record)
        (HERE / 'databento-metadata-probe.json').write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')
        print(json.dumps(record), flush=True)
    out.update(finished_utc=now(), new_paid_data_usd=0, market_data_downloaded=False,
               script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (HERE / 'databento-metadata-probe.json').write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
