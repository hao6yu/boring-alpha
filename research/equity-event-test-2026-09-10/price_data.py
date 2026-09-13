#!/usr/bin/env python3
"""Collect whole security histories within the registered dates and free quota."""
import argparse
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = ROOT / 'data/snapshots/equity-event-test-2026-09-10/prices'
sys.path.insert(0, str(ROOT))
from tools.tiingo_seen_reference import read_key, NoRedirect
from tools.check_ba002_seen_prices import tls_context

START, END = '2019-10-01', '2023-12-29'
FIELDS = {'date', 'open', 'high', 'low', 'close', 'volume', 'adjOpen', 'adjHigh',
          'adjLow', 'adjClose', 'adjVolume', 'divCash', 'splitFactor'}


def now():
    return datetime.now(timezone.utc)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbol(value):
    assert isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,14}', value)
    return value.upper().replace('.', '-')


def parse(raw):
    # Tiingo may return JSON [] for a symbol with no history, even when CSV
    # format was requested. Preserve the response; it is missing data.
    if raw.strip() == b'[]' or re.fullmatch(rb"Error: Ticker '[A-Za-z0-9.\-]+' not found", raw.strip()):
        return {}, {}
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    assert reader.fieldnames and set(reader.fieldnames) == FIELDS
    rows, issues = {}, {}
    previous = None
    for row in reader:
        label = row['date']
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T00:00:00(?:\.000)?(?:Z|\+00:00))?', label)
        day = str(date.fromisoformat(label[:10]))
        assert START <= day <= END, 'Out-of-scope date refused before numeric inspection'
        assert day not in rows and (previous is None or previous < day)
        previous = day
        values = {k: float(row[k]) for k in FIELDS - {'date'}}
        faults = []
        if any(not math.isfinite(v) for v in values.values()):
            faults.append('nonfinite_value')
        else:
            for prefix in ['', 'adj']:
                op, hi, lo, cl = [values[(prefix + k.title()) if prefix else k] for k in ['open', 'high', 'low', 'close']]
                if not 0 < lo <= min(op, cl) <= max(op, cl) <= hi:
                    faults.append('invalid_' + prefix + '_OHLC')
            if min(values['volume'], values['adjVolume'], values['divCash']) < 0 or values['splitFactor'] <= 0:
                faults.append('invalid_volume_or_action')
            if values['volume'] == 0:
                faults.append('zero_volume_needs_status_review')
            if values['close'] > 0:
                factor = values['adjClose'] / values['close']
                for k in ['open', 'high', 'low']:
                    if abs(values['adj' + k.title()] - values[k] * factor) > max(.0001, abs(values[k] * factor) * .00001):
                        faults.append('inconsistent_adjusted_' + k)
        rows[day] = values
        if faults:
            issues[day] = faults
    return rows, issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=48)
    ap.add_argument('--include-aliases', action='store_true', help='Also query source-evidenced present identifiers for missing historical symbols')
    ap.add_argument('--retry-transient', action='store_true', help='One quota-counted retry for prior transport failures without a stored response')
    args = ap.parse_args()
    assert 0 < args.limit <= 50
    policy = json.loads((HERE / 'experiment-policy.json').read_text())
    policy_sha = sha(HERE / 'experiment-policy.json')
    assert policy['price_start'] == START and policy['price_end_inclusive'] == END
    cp = HERE / 'sec-cohort.json'
    cohort = json.loads(cp.read_text())
    issuers = cohort['issuers']
    assert 0 < len(issuers) <= 100 and len({x['cik'] for x in issuers}) == len(issuers)
    assert all(x.get('membership_final_in_resolved_prefix') is True for x in issuers)
    requests = ['SPY'] + [symbol(x['historical_symbol']) for x in issuers]
    events_path = HERE / 'sec-events.json'
    if events_path.exists():
        for s in json.loads(events_path.read_text()).get('slots', []):
            c = s.get('current')
            if c and c.get('security', {}).get('status') == 'VERIFIED_SINGLE_COMMON_CLASS':
                requests.append(symbol(c['security']['historical_symbol']))
    if args.include_aliases:
        for alias in json.loads((HERE / 'price-alias-candidates.json').read_text())['aliases']:
            if alias['cik'] in {x['cik'] for x in issuers}:
                requests.append(symbol(alias['provider_query_symbol']))
    requests = list(dict.fromkeys(requests))
    mp = HERE / 'price-manifest.json'
    manifest = json.loads(mp.read_text()) if mp.exists() else {
        'created_utc': now().isoformat(), 'policy_sha256': policy_sha, 'cohort_snapshots': [],
        'resolved_cohort_prefix': [],
        'start': START, 'end': END, 'requests': [], 'symbols': {}, 'provider': 'Tiingo',
        'new_paid_data_usd': 0, 'internal_use_only': True,
    }
    assert manifest['policy_sha256'] == policy_sha
    prefix = [{'cik': x['cik'], 'historical_symbol': x['historical_symbol']} for x in issuers]
    old_prefix = manifest['resolved_cohort_prefix']
    removed = [item for item in old_prefix if item not in prefix]
    if removed:
        # Original joint-cover ownership repair was independently evidenced
        # before this issuer's prices were queried. Preserve the correction.
        correction_path = HERE / 'sec-parent-identity-correction.json'
        correction = json.loads(correction_path.read_text())
        assert correction['policy_sha256'] == policy_sha
        assert correction['after_sha256'] == sha(cp)
        assert len(removed) == 1 and removed[0]['cik'] == correction['removed_cik']
        assert removed[0]['historical_symbol'] not in manifest['symbols']
        assert not any(r['symbol'] == removed[0]['historical_symbol'] for r in manifest['requests'])
        manifest.setdefault('source_membership_repairs', []).append({
            'removed': removed, 'evidence_path': str(correction_path.relative_to(ROOT)),
            'evidence_sha256': sha(correction_path), 'no_removed_security_prices_queried': True})
        old_prefix = [item for item in old_prefix if item in prefix]
    # A documented eligibility-parser correction may insert an earlier member
    # before the final 100 are reached. Previously selected identities may not
    # disappear, change, or be reordered based on their subsequent prices.
    positions = [prefix.index(item) for item in old_prefix]
    assert positions == sorted(positions), 'Previously resolved membership changed'
    manifest['resolved_cohort_prefix'] = prefix
    if not manifest['cohort_snapshots'] or manifest['cohort_snapshots'][-1]['sha256'] != sha(cp):
        manifest['cohort_snapshots'].append({'sha256': sha(cp), 'issuers': len(issuers), 'observed_utc': now().isoformat()})
    RAW.mkdir(parents=True, exist_ok=True)
    def save():
        manifest['updated_utc'] = now().isoformat()
        temp = mp.with_suffix('.json.tmp')
        temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        temp.replace(mp)
    key = read_key(ROOT / '.env')
    opener = build_opener(HTTPSHandler(context=tls_context()), NoRedirect())
    made = 0
    for ticker in requests:
        previous = manifest['symbols'].get(ticker)
        retryable = (args.retry_transient and previous and
            previous.get('status') == 'REQUEST_OR_PARSE_ERROR' and 'path' not in previous and
            previous.get('error_class') in ('URLError', 'TimeoutError', 'ConnectionError') and
            sum(r['symbol'] == ticker for r in manifest['requests']) == 1)
        if previous and not retryable:
            continue
        if made >= args.limit:
            break
        recent = [r for r in manifest['requests'] if datetime.fromisoformat(r['requested_utc']) > now() - timedelta(hours=1, seconds=5)]
        if len(recent) >= 50:
            manifest['quota_wait_until_utc'] = (datetime.fromisoformat(recent[0]['requested_utc']) + timedelta(hours=1, seconds=6)).isoformat()
            break
        waiting = manifest.get('server_retry_after_utc')
        if waiting and now() < datetime.fromisoformat(waiting):
            break
        url = f'https://api.tiingo.com/tiingo/daily/{ticker.lower()}/prices?startDate={START}&endDate={END}&format=csv&resampleFreq=daily'
        rec = {'symbol': ticker, 'url': url, 'requested_utc': now().isoformat()}
        if retryable:
            rec['retry_of_transport_failure'] = previous
        manifest['requests'].append(rec)
        made += 1
        save()
        try:
            req = Request(url, headers={'Authorization': f'Token {key}', 'Accept': 'text/csv', 'User-Agent': 'BoringAlpha equity event research'})
            with opener.open(req, timeout=20) as response:
                assert response.status == 200 and response.geturl() == url
                raw = response.read(10_000_001)
                rec['http_status'] = response.status
            assert len(raw) <= 10_000_000 and key.encode() not in raw
            path = RAW / (ticker + '.csv')
            assert not path.exists(), 'Refuse to overwrite raw response'
            path.write_bytes(raw)
            rec.update(path=str(path.relative_to(ROOT)), sha256=sha(path), bytes=len(raw))
            rows, issues = parse(raw)
            manifest['symbols'][ticker] = {
                'status': 'DOWNLOADED' if rows else 'EMPTY_HISTORY', 'path': rec['path'], 'sha256': rec['sha256'],
                'rows': len(rows), 'first_session': min(rows) if rows else None, 'last_session': max(rows) if rows else None,
                'invalid_sessions': issues, 'dividend_rows': sum(r['divCash'] > 0 for r in rows.values()),
                'split_rows': sum(r['splitFactor'] != 1 for r in rows.values()),
                'qualification': 'Structural provider fields only; issuer, event, action and held-position checks remain separate.',
            }
        except HTTPError as exc:
            rec['http_status'] = exc.code
            manifest['symbols'][ticker] = {'status': 'HTTP_ERROR', 'http_status': exc.code}
            if exc.code == 429:
                retry = exc.headers.get('Retry-After')
                seconds = max(3606, int(retry)) if retry and retry.isdecimal() else 3606
                manifest['server_retry_after_utc'] = (now() + timedelta(seconds=seconds)).isoformat()
                # A throttled query remains retryable only after the recorded time.
                del manifest['symbols'][ticker]
        except Exception as exc:
            rec['error_class'] = type(exc).__name__
            manifest['symbols'][ticker] = {'status': 'REQUEST_OR_PARSE_ERROR', 'error_class': type(exc).__name__,
                **{k: rec[k] for k in ['path', 'sha256', 'bytes'] if k in rec}}
        rec['finished_utc'] = now().isoformat()
        save()
        print(json.dumps({'symbol': ticker, 'status': manifest['symbols'].get(ticker, {}).get('status', 'RATE_LIMITED'),
                          'requests_this_run': made, 'collected_symbols': len(manifest['symbols'])}), flush=True)
        if rec.get('http_status') == 429:
            break
        time.sleep(.25)
    manifest['pending_symbols'] = [s for s in requests if s not in manifest['symbols']]
    save()
    print(json.dumps({'made': made, 'pending': len(manifest['pending_symbols']), 'quota_wait_until': manifest.get('quota_wait_until_utc')}))


if __name__ == '__main__':
    main()
