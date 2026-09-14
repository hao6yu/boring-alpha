"""Bounded provider/sample check. Uses only Sharadar's published AAPL demo key.

No personal credentials, bulk downloads, strategy training or return ranking.
All requested price/financial/action observations end before reserved 2024–25.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = ROOT / 'data/snapshots' / HERE.name

PAGES = {
    'pricing': 'https://sharadar.com/subscribe',
    'fundamentals_docs': 'https://sharadar.com/docs/fundamentals',
    'stocks_docs': 'https://sharadar.com/docs/stocks',
    'actions_docs': 'https://sharadar.com/docs/actions',
    'tickers_docs': 'https://sharadar.com/docs/tickers',
    'faq': 'https://sharadar.com/docs/faqs',
    'license': 'https://sharadar.com/terms',
    'auth_docs': 'https://sharadar.com/docs/auth',
    'sp500_docs': 'https://sharadar.com/docs/sp500',
    'daily_docs': 'https://sharadar.com/docs/daily',
}
SAMPLES = {
    'fundamentals_art': ('fundamentals', {'dimension': 'ART', 'from': '2022-01-01', 'to': '2023-12-31',
        'fields': 'ticker,date,dimension,calendardate,reportperiod,assets,assetsavg,equityusd,netinccmnusd,netinc,ncfo,gp,revenue,debt,marketcap,lastupdated'}),
    'stocks': ('stocks', {'from': '2023-08-01', 'to': '2023-08-31',
        'fields': 'ticker,date,open,high,low,close,volume,closeadj,closeunadj,lastupdated'}),
    'actions': ('actions', {'from': '2023-01-01', 'to': '2023-12-31',
        'fields': 'date,action,ticker,value,contraticker'}),
    'tickers': ('tickers', {'table': 'fundamentals',
        'fields': 'table,permaticker,ticker,category,currency,firstpricedate,lastpricedate,isdelisted'}),
    'sp500': ('sp500', {'from': '2022-01-01', 'to': '2023-12-31',
        'fields': 'date,action,ticker,contraticker'}),
    'daily': ('daily', {'from': '2023-08-28', 'to': '2023-08-31',
        'fields': 'ticker,date,marketcap,lastupdated'}),
}


def fetch(item):
    name, url, params = item
    at = datetime.now(timezone.utc).isoformat()
    request_url = url + ('?' + urlencode(params) if params else '')
    # System curl uses the host trust store; never disable TLS verification.
    response = subprocess.run(['curl', '--silent', '--show-error', '--proto', '=https',
        '--max-time', '25', '--max-filesize', '2000000', '--user-agent', 'PersonalResearchSourceCheck/1.0',
        '--write-out', '\n%{http_code}', request_url], capture_output=True, check=True)
    content, status_bytes = response.stdout.rsplit(b'\n', 1)
    status = int(status_bytes)
    assert len(content) < 2_000_000, 'Unexpectedly large sample'
    suffix = '.json' if params else '.html'
    path = RAW / (name + suffix)
    path.write_bytes(content)
    record = {'name': name, 'request_endpoint': url,
        'parameters': {k: v for k, v in (params or {}).items() if k != 'api_key'},
        'authentication': 'vendor-published AAPL demo key' if params else 'public documentation',
        'requested_at_utc': at, 'status': status,
        'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
        'path': str(path.relative_to(ROOT))}
    if params and status == 200:
        obj = json.loads(content)
        record['json_type'] = type(obj).__name__
        record['top_level_keys'] = list(obj) if isinstance(obj, dict) else None
        rows = obj if isinstance(obj, list) else obj.get('data', [])
        if isinstance(rows, list) and all(isinstance(r, dict) for r in rows):
            record['rows'] = len(rows)
            record['fields'] = sorted(set().union(*(r.keys() for r in rows))) if rows else []
            dates = [r['date'][:10] for r in rows if isinstance(r.get('date'), str)]
            if dates:
                assert params['from'] <= min(dates) <= max(dates) <= params['to'] < '2024-01-01'
                record['observed_date_range'] = [min(dates), max(dates)]
            if name == 'fundamentals_art' and rows:
                assert all(r['dimension'] == 'ART' for r in rows)
                assert all(r['date'] >= r['reportperiod'] for r in rows)
                record['all_filing_dates_on_or_after_report_period'] = True
                record['all_dimensions_ART'] = True
    return record


def run():
    RAW.mkdir(parents=True, exist_ok=True)
    items = [(name, url, None) for name, url in PAGES.items()]
    for name, (table, parameters) in SAMPLES.items():
        params = dict(parameters, api_key='test-api-key', ticker='AAPL', format='json', limit=50)
        items.append((name, f'https://api.sharadar.com/v1.0/data/{table}', params))
    evidence_path = HERE / 'source-and-sample-evidence.json'
    prior = json.loads(evidence_path.read_text())['records'] if evidence_path.exists() else []
    prior = {r['name']: r for r in prior}
    def fetch_or_cached(item):
        name, url, params = item
        old = prior.get(name)
        public_params = {k: v for k, v in (params or {}).items() if k != 'api_key'}
        if old and old['request_endpoint'] == url and old['parameters'] == public_params:
            assert hashlib.sha256((ROOT / old['path']).read_bytes()).hexdigest() == old['sha256']
            return old
        return fetch(item)
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch_or_cached, items))
    result = {'status': 'PUBLIC_DOCUMENTATION_AND_AAPL_SAMPLE_CHECK_ONLY',
        'new_paid_data_usd': 0, 'records': records,
        'limitations': 'AAPL sample does not verify full-history paid entitlement, removed-stock breadth, historical listing transitions, or merger payout completeness. No predictive model or strategy returns computed.'}
    (HERE / 'source-and-sample-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps([{'name': r['name'], 'status': r['status'], 'rows': r.get('rows'),
        'json_type': r.get('json_type'), 'top_level_keys': r.get('top_level_keys'),
        'range': r.get('observed_date_range')} for r in records], indent=2))


if __name__ == '__main__':
    run()
