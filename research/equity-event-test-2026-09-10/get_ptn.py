#!/usr/bin/env python3
"""Fetch fixed PTN primary-venue samples under a fresh cumulative quote cap."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import getpass
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / 'data/snapshots/equity-event-test-2026-09-10/ptn-xase'
sys.path.insert(0, str(ROOT / 'tools'))
from fetch_market_data import _CONTEXT
from databento_history_probe import NoRedirect, quote_value


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument('stage', choices=['sample', 'quote-full', 'full'])
    args = arg.parse_args()
    policy = json.loads((HERE / 'data-policy.json').read_text())
    policy_sha = sha(HERE / 'data-policy.json')
    cap = Decimal(str(policy['cumulative_quote_cap_usd']))
    if args.stage == 'full':
        audit = json.loads((HERE / 'ptn-sample-audit.json').read_text())
        assert audit['full_download_recommended'] is True
    ranges = [('2022-08-30', '2022-08-31'), ('2022-08-31', '2022-09-01'), ('2023-06-16', '2023-06-17')]
    if args.stage != 'sample':
        ranges = [('2022-07-01', '2023-11-01')]
    jobs = [dict(dataset='XASE.PILLAR', symbols='PTN', stype_in='raw_symbol',
                 schema=schema, start=start, end=end, limit=3_000_000)
            for start, end in ranges for schema in ['trades', 'statistics', 'definition']]
    key = getpass.getpass('Databento key (hidden, process memory only): ').strip()
    auth = 'Basic ' + base64.b64encode((key + ':').encode()).decode()
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=_CONTEXT))
    RAW.mkdir(parents=True, exist_ok=True)
    mp = HERE / 'ptn-download-manifest.json'
    manifest = json.loads(mp.read_text()) if mp.exists() else {
        'started_utc': now(), 'policy_sha256': policy_sha, 'requests': [], 'downloads': [],
        'cumulative_quote_usd': '0', 'billing_note': 'Quotes are estimates, not invoice reconciliation or server-enforced limits.',
    }
    assert manifest['policy_sha256'] == policy_sha

    def save():
        mp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')

    def fetch(method, params, max_bytes):
        url = 'https://hist.databento.com/v0/' + method + '?' + urllib.parse.urlencode(params)
        rec = {'method': method, 'params': params, 'requested_utc': now()}
        req = urllib.request.Request(url, headers={'Authorization': auth, 'User-Agent': 'BoringAlpha-PTN-Qualification/1.0'})
        payload = None
        try:
            try:
                response = opener.open(req, timeout=40)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                raw = response.read(max_bytes + 1)
                rec['http_status'] = response.code
            if len(raw) > max_bytes or key.encode() in raw or auth.encode() in raw:
                rec['status'] = 'UNSAFE_OR_OVERSIZE'
            elif rec['http_status'] != 200:
                lower = raw.lower()
                rec.update(status='HTTP_ERROR', mentions_license=b'licens' in lower or b'agreement' in lower,
                           mentions_credit=b'credit' in lower, mentions_auth=b'auth' in lower)
            else:
                rec.update(status='OK', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                payload = raw
        except Exception as exc:
            rec.update(status='ERROR', error_class=type(exc).__name__)
        rec['finished_utc'] = now()
        manifest['requests'].append(rec)
        save()
        return rec, payload

    for params in jobs:
        label = params['start'] + '-' + params['end'] + '-' + params['schema']
        path = RAW / (label + '.jsonl')
        existing = next((d for d in manifest['downloads'] if d['label'] == label), None)
        if existing:
            assert path.exists() and sha(path) == existing['sha256']
            print(json.dumps({'label': label, 'status': 'REUSED_HASH_VERIFIED'}), flush=True)
            continue
        rec, raw = fetch('metadata.get_cost', params, 2_000_000)
        quote = quote_value(raw)
        print(json.dumps({'label': label, 'quote_usd': quote, 'quote_status': rec['status'], 'http_status': rec.get('http_status')}), flush=True)
        if quote is None:
            manifest['stop_reason'] = 'QUOTE_UNAVAILABLE'
            break
        cost = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
        rec['quote_usd'] = str(cost)
        save()
        if args.stage == 'quote-full':
            continue
        if Decimal(manifest['cumulative_quote_usd']) + cost > cap:
            manifest['stop_reason'] = 'CUMULATIVE_QUOTE_CAP'
            break
        assert not path.exists(), 'Refuse to overwrite raw data'
        # Reserve the quote before a possibly billed download, including uncertain failures.
        manifest['cumulative_quote_usd'] = str(Decimal(manifest['cumulative_quote_usd']) + cost)
        save()
        rec, raw = fetch('timeseries.get_range', params | {'encoding': 'json', 'compression': 'none'}, 300_000_000)
        if raw is None:
            manifest['stop_reason'] = 'DOWNLOAD_UNAVAILABLE'
            print(json.dumps({'label': label, **{k: v for k, v in rec.items() if k not in ['params', 'requested_utc', 'finished_utc']}}), flush=True)
            break
        path.write_bytes(raw)
        count = len(raw.splitlines())
        entry = dict(label=label, params=params, quote_usd=str(cost), rows=count,
                     path=str(path.relative_to(ROOT)), sha256=sha(path), bytes=len(raw))
        manifest['downloads'].append(entry)
        save()
        print(json.dumps({k: v for k, v in entry.items() if k != 'params'}), flush=True)
        if count >= params['limit']:
            manifest['stop_reason'] = 'RECORD_LIMIT_POTENTIALLY_TRUNCATED'
            break
    manifest.update(updated_utc=now(), last_stage=args.stage, last_script_sha256=sha(Path(__file__)))
    save()


if __name__ == '__main__':
    main()
