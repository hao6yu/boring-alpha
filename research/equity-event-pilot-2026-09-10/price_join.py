#!/usr/bin/env python3
"""Bounded, internal-use price availability audit. No strategy returns.

Run from repository root: .venv/bin/python research/.../price_join.py fetch|join
Separate from the older ETF collectors and their authorized date windows.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import csv
from datetime import date, datetime, timezone
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
sys.path.insert(0, str(ROOT))
from tools.tiingo_seen_reference import read_key, NoRedirect
from tools.check_ba002_seen_prices import tls_context

HERE = Path(__file__).resolve().parent
RAW = ROOT / 'data/snapshots/equity-event-pilot-2026-09-10'
POLICY_HASH = 'f6178cb98b4716a8744b79a3bae2b0709f6c4ee056f3a66be0789fc38cb2e188'
START, END = '2022-07-01', '2023-10-31'
DEADLINE = datetime.fromisoformat('2026-09-11T01:30:01+00:00')
CALENDAR = ROOT / 'data/calendars/nyse-2006-2026-v1.json'
FIELDS = {'date', 'open', 'high', 'low', 'close', 'volume', 'adjOpen',
          'adjHigh', 'adjLow', 'adjClose', 'adjVolume', 'divCash', 'splitFactor'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_policy():
    if sha(HERE / 'policy.json') != POLICY_HASH:
        raise ValueError('Frozen policy hash mismatch')


def symbol_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,14}', value):
        return None
    return value.upper().replace('.', '-')


def parse(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if reader.fieldnames is None or set(reader.fieldnames) != FIELDS or len(reader.fieldnames) != len(FIELDS):
        raise ValueError('unexpected_csv_schema')
    rows, issues, previous = {}, {}, None
    for row in reader:
        label = row.get('date', '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T00:00:00(?:\.000)?(?:Z|\+00:00))?', label):
            raise ValueError('invalid_date_label')
        day = str(date.fromisoformat(label[:10]))
        if not START <= day <= END:
            raise ValueError('out_of_bounds_date_not_numerically_inspected')
        if day in rows or (previous and day < previous):
            raise ValueError('duplicate_or_nonchronological_session')
        previous = day
        faults = []
        try:
            values = {key: float(row[key]) for key in FIELDS - {'date'}}
        except (TypeError, ValueError, KeyError, OverflowError):
            rows[day] = None
            issues[day] = ['invalid_numeric_field']
            continue
        if None in row or any(not math.isfinite(v) for v in values.values()):
            faults.append('nonfinite_or_malformed_row')
        else:
            for keys in [('open', 'high', 'low', 'close'), ('adjOpen', 'adjHigh', 'adjLow', 'adjClose')]:
                opening, high, low, close = [values[k] for k in keys]
                if not 0 < low <= min(opening, close) <= max(opening, close) <= high:
                    faults.append('invalid_' + keys[0] + '_ohlc')
            if min(values['volume'], values['adjVolume'], values['divCash']) < 0 or values['splitFactor'] <= 0:
                faults.append('invalid_volume_or_action')
            if values['volume'] == 0 or values['adjVolume'] == 0:
                faults.append('zero_volume_requires_halt_or_tradability_review')
            if values['close'] > 0:
                factor = values['adjClose'] / values['close']
                for raw_key, adj_key in [('open', 'adjOpen'), ('high', 'adjHigh'), ('low', 'adjLow')]:
                    expected = values[raw_key] * factor
                    if abs(values[adj_key] - expected) > max(0.0001, abs(expected) * 0.00001):
                        faults.append('inconsistent_adjustment_ratio_' + raw_key)
        rows[day] = values
        if faults:
            issues[day] = sorted(set(faults))
    if not rows:
        raise ValueError('empty_price_history')
    ordered = list(rows)
    for before, day in zip(ordered, ordered[1:]):
        previous_row, values = rows[before], rows[day]
        if previous_row is None or values is None:
            continue
        if not (previous_row['close'] > 0 and values['close'] > 0):
            continue
        before_factor = previous_row['adjClose'] / previous_row['close']
        factor = values['adjClose'] / values['close']
        if not (math.isfinite(before_factor) and math.isfinite(factor) and before_factor > 0):
            continue
        relative_change = abs(factor / before_factor - 1)
        has_action = values['divCash'] != 0 or values['splitFactor'] != 1
        if has_action and relative_change <= 1e-8:
            issues.setdefault(day, []).append('declared_action_without_adjustment_change_requires_review')
        elif not has_action and relative_change > 1e-5:
            issues.setdefault(day, []).append('adjustment_change_without_declared_action_requires_review')
    return rows, issues


def fetch():
    check_policy()
    manifest_path = HERE / 'price-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'policy_sha256': POLICY_HASH, 'provider': 'Tiingo', 'internal_use_only': True,
        'start': START, 'end': END, 'request_cap': 35, 'requests': [], 'symbols': {},
        'calendar_sha256': sha(CALENDAR), 'created_utc': stamp(),
        'adjusted_ohlc_tolerance': 'max(0.0001, abs(raw_ohlc * adjClose / close) * 0.00001)',
        'adjustment_transition_checks': 'Flag declared action with relative factor change <=1e-8, or no action with change >1e-5. These are review flags, not proof of action accuracy.',
    }
    selection_path = HERE / 'sec-selection.json'
    if not selection_path.exists():
        print('Selection not ready; no price request made.')
        return
    selection = json.loads(selection_path.read_text())
    symbols = {symbol_name(i.get('historical_symbol')) for i in selection.get('issuers', [])}
    events_path = HERE / 'sec-events.json'
    if events_path.exists():
        for slot in json.loads(events_path.read_text()).get('slots', []):
            symbols.add(symbol_name(slot.get('historical_symbol')))
    aliases_path = HERE / 'price-aliases.json'
    if aliases_path.exists():
        for alias in json.loads(aliases_path.read_text()).get('aliases', {}).values():
            symbols.add(symbol_name(alias.get('provider_symbol')))
    symbols.discard(None)
    key = read_key(ROOT / '.env')
    opener = build_opener(HTTPSHandler(context=tls_context()), NoRedirect())
    RAW.mkdir(parents=True, exist_ok=True)
    if any(r.get('http_status') == 429 for r in manifest['requests']):
        print('Prior HTTP 429; quota reset must be verified before further requests.')
        return
    for symbol in sorted(symbols):
        if symbol in manifest['symbols']:
            continue
        if datetime.now(timezone.utc) >= DEADLINE or len(manifest['requests']) >= 35:
            manifest['stop_reason'] = 'deadline_or_initial_request_cap'
            break
        url = (f'https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices'
               f'?startDate={START}&endDate={END}&format=csv&resampleFreq=daily')
        record = {'symbol': symbol, 'url': url, 'requested_utc': stamp()}
        manifest['requests'].append(record)
        dump(manifest_path, manifest)
        try:
            request = Request(url, headers={'Authorization': f'Token {key}', 'Accept': 'text/csv',
                                           'User-Agent': 'BoringAlpha bounded equity event data pilot'})
            with opener.open(request, timeout=20) as response:
                if response.geturl() != url or response.status != 200:
                    raise ValueError('unexpected_response')
                raw = response.read(10_000_001)
                record['http_status'] = response.status
            if len(raw) > 10_000_000 or key.encode() in raw:
                raise ValueError('oversized_or_reflected_response')
            raw_path = RAW / f'{symbol}.prices.csv'
            raw_path.write_bytes(raw)
            record.update({'received_utc': stamp(), 'bytes': len(raw), 'raw_sha256': sha(raw_path),
                           'raw_path': str(raw_path.relative_to(ROOT))})
            rows, issues = parse(raw)
            sessions = set(json.loads(CALENDAR.read_text())['sessions'])
            manifest['symbols'][symbol] = {
                'status': 'downloaded', 'raw_path': record['raw_path'], 'raw_sha256': record['raw_sha256'],
                'rows': len(rows), 'first_session': min(rows), 'last_session': max(rows),
                'invalid_sessions': issues, 'unexpected_sessions': sorted(set(rows) - sessions),
                'dividend_rows': sum(v is not None and v['divCash'] > 0 for v in rows.values()),
                'split_rows': sum(v is not None and v['splitFactor'] != 1 for v in rows.values()),
                'action_check_scope': 'Structural fields and common raw/adjusted OHLC factor; action correctness reviewed separately.',
            }
        except HTTPError as error:
            record['http_status'] = error.code
            record['retry_after'] = error.headers.get('Retry-After')
            manifest['symbols'][symbol] = {'status': 'request_failed', 'http_status': error.code}
        except Exception as error:
            # No upstream exception text or response bodies enter public logs.
            record['error_class'] = type(error).__name__
            manifest['symbols'][symbol] = {'status': 'request_or_parse_failed', 'error_class': type(error).__name__}
        record['completed_utc'] = stamp()
        dump(manifest_path, manifest)
        print(f"{symbol}: {manifest['symbols'][symbol]['status']}", flush=True)
        if record.get('http_status') == 429:
            break
        time.sleep(0.25)
    manifest['updated_utc'] = stamp()
    dump(manifest_path, manifest)


def join():
    check_policy()
    sessions = json.loads(CALENDAR.read_text())['sessions']
    manifest = json.loads((HERE / 'price-manifest.json').read_text())
    events = json.loads((HERE / 'sec-events.json').read_text())
    aliases_path = HERE / 'price-aliases.json'
    aliases = json.loads(aliases_path.read_text()).get('aliases', {}) if aliases_path.exists() else {}
    cached, results = {}, []
    for slot in events.get('slots', []):
        result = {'slot_id': slot['slot_id'], 'price_window_success': False, 'unresolved_reasons': []}
        current = slot.get('current') or {}
        symbol = symbol_name(slot.get('historical_symbol'))
        result['symbol'] = symbol
        try:
            filing = str(date.fromisoformat(current['filing_date']))
            accepted = str(date.fromisoformat(current['acceptance_eastern'][:10]))
            entry_index = bisect_right(sessions, max(filing, accepted))
            expected = sessions[entry_index - 60:entry_index + 21]
            if len(expected) != 81:
                raise ValueError('calendar_coverage')
            result.update({'entry_session': sessions[entry_index], 'price_window_start': expected[0],
                           'price_window_end': expected[-1], 'expected_sessions': 81})
        except (ValueError, KeyError, TypeError, IndexError):
            result['unresolved_reasons'].append('missing_or_invalid_event_timing')
            results.append(result)
            continue
        source = manifest['symbols'].get(symbol, {})
        provider_symbol = symbol
        if source.get('status') != 'downloaded' and aliases.get(symbol, {}).get('provider_identity_verified'):
            provider_symbol = symbol_name(aliases[symbol]['provider_symbol'])
            source = manifest['symbols'].get(provider_symbol, {})
        result['provider_symbol'] = provider_symbol
        if source.get('status') != 'downloaded':
            result['unresolved_reasons'].append('historical_symbol_price_download_unavailable')
        else:
            if provider_symbol not in cached:
                raw_path = ROOT / source['raw_path']
                if sha(raw_path) != source['raw_sha256']:
                    raise ValueError('Raw price hash mismatch')
                cached[provider_symbol] = parse(raw_path.read_bytes())
            rows, issues = cached[provider_symbol]
            result['missing_sessions'] = [d for d in expected if d not in rows]
            result['invalid_sessions'] = {d: issues[d] for d in expected if d in issues}
            result['dividend_rows'] = sum(rows.get(d) is not None and rows[d]['divCash'] > 0 for d in expected)
            result['split_rows'] = sum(rows.get(d) is not None and rows[d]['splitFactor'] != 1 for d in expected)
            if result['missing_sessions']:
                result['unresolved_reasons'].append('missing_required_sessions')
            if result['invalid_sessions']:
                result['unresolved_reasons'].append('invalid_or_unresolved_price_rows')
            if source.get('unexpected_sessions'):
                result['unresolved_reasons'].append('provider_unexpected_calendar_sessions')
            result['price_window_success'] = not result['unresolved_reasons']
        results.append(result)
    output = {'policy_sha256': POLICY_HASH, 'created_utc': stamp(), 'calendar_sha256': sha(CALENDAR),
              'manifest_sha256': sha(HERE / 'price-manifest.json'), 'events_sha256': sha(HERE / 'sec-events.json'),
              'scope': 'Price structure and calendar coverage only; issuer identity and actual action correctness are separate gates.',
              'slots': results, 'price_window_success': sum(r['price_window_success'] for r in results)}
    dump(HERE / 'price-joins.json', output)
    print(f"Price coverage: {output['price_window_success']}/{len(results)} slots")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['fetch', 'join'])
    args = parser.parse_args()
    {'fetch': fetch, 'join': join}[args.action]()
