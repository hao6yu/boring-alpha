"""Date-gated recent-history collector; existing credentials stay off stdout."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = ROOT / 'data/snapshots' / HERE.name
OLD = HERE.parent / 'ml-stock-comparison-2026-09-14'


def now():
    return datetime.now(timezone.utc)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')


def scope():
    spec = load(HERE / 'protocol.json')
    for name, digest in spec['original_artifacts'].items():
        assert sha(ROOT / name) == digest, name
    return spec


def key():
    for line in (ROOT / '.env').read_text().splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?TIINGO_API_KEY\s*=\s*(.*?)\s*', line)
        if match:
            value = match[1].strip('\"\'')
            if re.fullmatch(r'[A-Za-z0-9_-]+', value):
                return value
    raise RuntimeError('Tiingo credential unavailable; value omitted')


def request_prices(symbol, spec, manifest):
    limits = spec['acquisition']
    assert re.fullmatch(r'[A-Z0-9.-]+', symbol)
    if symbol in manifest['symbols']:
        return manifest['symbols'][symbol]
    assert len(manifest['requests']) < limits['max_tiingo_requests']
    prior = load(OLD / 'price-manifest.json')['requests']
    recent = [r for r in prior + manifest['requests']
              if now() - datetime.fromisoformat(r['at']) < timedelta(hours=1, seconds=6)]
    if len(recent) >= limits['tiingo_requests_per_hour']:
        resume = min(datetime.fromisoformat(r['at']) for r in recent) + timedelta(hours=1, seconds=7)
        manifest['resume_after_utc'] = resume.isoformat()
        write(HERE / 'price-manifest.json', manifest)
        raise RuntimeError('Local hourly quota reached; resume time recorded')
    if manifest.get('provider_stop'):
        raise RuntimeError('Provider stopped acquisition')
    url = f'https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?' + urlencode({
        'startDate': limits['price_start'], 'endDate': limits['price_end'],
        'format': 'json', 'resampleFreq': 'daily'})
    record = dict(symbol=symbol, url=url, at=now().isoformat())
    manifest['requests'].append(record)
    write(HERE / 'price-manifest.json', manifest)
    token = key()
    response = subprocess.run([
        'curl', '--config', '-', '--silent', '--show-error', '--proto', '=https',
        '--max-time', '35', '--max-filesize', '10000000', '--write-out', '\n%{http_code}', url
    ], input=('header = "Authorization: Token ' + token + '"\n').encode(),
       capture_output=True, timeout=40)
    body, _, code = response.stdout.rpartition(b'\n')
    assert token.encode() not in body, 'Credential echo rejected'
    record.update(http_status=int(code) if code.isdigit() else None,
                  curl_exit=response.returncode, response_bytes=len(body))
    if response.returncode == 0 and record['http_status'] == 200:
        rows = json.loads(body)
        assert isinstance(rows, list)
        dates = [r['date'][:10] for r in rows]
        assert len(dates) == len(set(dates))
        assert all(limits['price_start'] <= d <= limits['price_end'] for d in dates)
        path = RAW / f'tiingo-{symbol}-recent.json'
        path.write_bytes(body)
        record.update(file=str(path.relative_to(ROOT)), sha256=sha(path), rows=len(rows),
                      first_date=min(dates) if dates else None,
                      last_date=max(dates) if dates else None,
                      status='DOWNLOADED' if rows else 'EMPTY')
    else:
        record['status'] = 'HTTP_OR_TRANSPORT_ERROR'
        if record['http_status'] in (401, 403, 429):
            manifest['provider_stop'] = record['http_status']
    manifest['symbols'][symbol] = dict(record)
    write(HERE / 'price-manifest.json', manifest)
    print(json.dumps({k: record.get(k) for k in
                      ['symbol', 'http_status', 'status', 'rows', 'first_date', 'last_date']}), flush=True)
    time.sleep(.4)
    return record


def probe():
    spec = scope()
    freeze = HERE / 'acquisition-freeze.json'
    if not freeze.exists():
        write(freeze, dict(at_utc=now().isoformat(), code_sha256=sha(Path(__file__)),
                           protocol_sha256=sha(HERE / 'protocol.json')))
    frozen = load(freeze)
    assert sha(Path(__file__)) == frozen['code_sha256']
    assert sha(HERE / 'protocol.json') == frozen['protocol_sha256']
    manifest = load(HERE / 'price-manifest.json', dict(requests=[], symbols={}, new_paid_data_usd=0))
    rows = []
    for symbol in spec['acquisition']['date_probe_symbols']:
        rows.append(request_prices(symbol, spec, manifest))
        if manifest.get('provider_stop'):
            break
    passed = len(rows) == 3 and all(r.get('last_date') == spec['acquisition']['price_end'] for r in rows)
    result = dict(at_utc=now().isoformat(), passed=passed,
                  target_end=spec['acquisition']['price_end'],
                  symbols=[{k:r.get(k) for k in ['symbol','status','rows','first_date','last_date','http_status']} for r in rows],
                  new_paid_data_usd=0, account_evaluations=0,
                  next_step='Coverage gate passed; full acquisition can proceed' if passed else 'Stop broad acquisition; report actual endpoint coverage before further work')
    write(HERE / 'date-probe.json', result)
    scope()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if sys.argv[1:] == ['probe']:
        probe()
    else:
        raise SystemExit('Supported command: probe')
