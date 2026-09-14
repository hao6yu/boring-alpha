#!/usr/bin/env python3
"""Small SEC/Databento feasibility probe. No strategy returns or model training."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = ROOT / 'data/snapshots' / HERE.name
COMPANIES = [
    ('AAPL', '0000320193', ['AAPL']),
    ('MSFT', '0000789019', ['MSFT']),
    ('JPM', '0000019617', ['JPM']),
    ('XOM', '0000034088', ['XOM']),
    ('JNJ', '0000200406', ['JNJ']),
    ('AMZN', '0001018724', ['AMZN']),
    ('GE', '0000040545', ['GE']),
    ('META', '0001326801', ['FB', 'META']),
    ('ATVI', '0000718877', ['ATVI']),
    ('BBBY', '0000886158', ['BBBY']),
]
DATES = ['2019-12-31', '2021-12-31', '2023-06-30', '2023-11-30']
PRICE_QUERY = dict(dataset='XNAS.ITCH', schema='ohlcv-1d',
                   symbols=','.join(s for _, _, aliases in COMPANIES for s in aliases),
                   stype_in='raw_symbol', start='2018-05-01', end='2024-01-01')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def plan():
    p = HERE / 'plan.json'
    spec = dict(kind='DATA_FEASIBILITY_ONLY', companies=[dict(label=s, cik=c, aliases=a) for s,c,a in COMPANIES],
                sample_decision_dates=DATES, price_query=PRICE_QUERY,
                selection='Predetermined coverage cases, not a performance-selected or representative portfolio.',
                purpose='Check as-filed financial availability, price joins, ticker transitions, removed securities and costs.',
                price_semantics='Unadjusted Nasdaq venue UTC-day OHLCV; not qualified fills, total returns or consolidated volume.',
                fundamental_rule='Only facts filed before 2024; each decision uses filing availability plus two NYSE sessions.',
                credit_quote_ceiling_usd=1, fresh_credit_verification_required=True,
                no_new_cash=True, no_strategy_returns=True, no_models=True,
                no_reserved_2024_2025_strategy_values=True)
    if p.exists():
        assert json.loads(p.read_text()) == spec, 'Frozen sample changed'
    else:
        write(p, spec)
    return spec


def curl(url, key=None, max_bytes=40_000_000):
    args = ['curl', '--silent', '--show-error', '--proto', '=https', '--max-time', '55',
            '--max-filesize', str(max_bytes), '--user-agent', 'BoringAlphaResearch/0.1 (personal financial research)',
            '--write-out', '\n%{http_code}', url]
    config = ''
    auth = None
    if key:
        auth = 'Basic ' + base64.b64encode((key + ':').encode()).decode()
        args[1:1] = ['--config', '-']
        config = 'header = "Authorization: ' + auth + '"\n'
    result = subprocess.run(args, input=config.encode(), capture_output=True, timeout=60)
    body, _, code = result.stdout.rpartition(b'\n')
    if key and (key.encode() in body or auth.encode() in body):
        raise RuntimeError('Credential echo rejected')
    meta = dict(url=url, at=now(), http_status=int(code) if code.isdigit() else None,
                curl_exit=result.returncode, response_bytes=len(body), response_sha256=sha(body))
    # Databento documents 206 as successful data with partially resolved symbols.
    # Preserve it for an explicit symbol/date coverage audit, not as a full pass.
    if result.returncode or meta['http_status'] not in (200, 206):
        return meta, None
    return meta, body


def sec():
    plan()
    manifest_path = HERE / 'sec-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for label, cik, _ in COMPANIES:
        if label in manifest and manifest[label].get('file'):
            old = manifest[label]
            assert sha((ROOT / old['file']).read_bytes()) == old['filtered_sha256']
            continue
        url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
        meta, body = curl(url)
        if body is not None:
            data = json.loads(body)
            assert int(data['cik']) == int(cik)
            # The API transports the full filing history. Discard later filings
            # before any feature calculation; do not persist their values.
            selected = dict(cik=data['cik'], entityName=data['entityName'], facts={})
            n = 0
            for taxonomy, concepts in data.get('facts', {}).items():
                selected['facts'][taxonomy] = {}
                for tag, concept in concepts.items():
                    units = {}
                    for unit, rows in concept.get('units', {}).items():
                        keep = [r for r in rows if r.get('filed', '9999') < '2024-01-01'
                                and r.get('end', '9999') < '2024-01-01']
                        if keep:
                            units[unit] = keep
                            n += len(keep)
                    if units:
                        selected['facts'][taxonomy][tag] = dict(units=units)
            path = RAW / f'{label}-companyfacts-pre2024.json'
            write(path, selected)
            meta.update(file=str(path.relative_to(ROOT)), filtered_sha256=sha(path.read_bytes()),
                        cik=cik, entity_name=selected['entityName'], retained_fact_rows=n,
                        later_filing_values_discarded=True)
        manifest[label] = meta
        write(manifest_path, manifest)
        print(json.dumps(dict(source='SEC', label=label, status=meta['http_status'], rows=meta.get('retained_fact_rows'))), flush=True)
        time.sleep(.3)


def db_request(key, method, params, label):
    path = RAW / (label + '.json')
    manifest_path = HERE / 'databento-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if label in manifest and manifest[label].get('file'):
        old = manifest[label]
        assert old['method'] == method and old['params'] == params
        body = (ROOT / old['file']).read_bytes()
        assert sha(body) == old['response_sha256']
        return body
    url = 'https://hist.databento.com/v0/' + method + '?' + urlencode(params)
    meta, body = curl(url, key)
    meta.update(method=method, params=params)
    if body is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        meta['file'] = str(path.relative_to(ROOT))
    manifest[label] = meta
    write(manifest_path, manifest)
    print(json.dumps(dict(source='Databento', label=label, status=meta['http_status'], bytes=meta['response_bytes'])), flush=True)
    if body is None:
        raise RuntimeError('Databento request failed; secret/error body omitted')
    return body


def databento(key, download=False):
    plan()
    if not key.startswith('db-'):
        raise ValueError('Invalid credential format')
    sample_cost = json.loads(db_request(key, 'metadata.get_cost', PRICE_QUERY, 'sample-daily-quote'))
    # A broad quote provides a concrete upper-scope comparison, not an order.
    broad = PRICE_QUERY | {'symbols': 'ALL_SYMBOLS'}
    broad_cost = json.loads(db_request(key, 'metadata.get_cost', broad, 'all-symbols-daily-quote'))
    write(HERE / 'quotes.json', dict(sample_usd=sample_cost, all_nasdaq_venue_symbols_usd=broad_cost,
                                    excludes='SEC normalization, historical universe, corporate-action/reference products and execution-quality data',
                                    billing='Quote only; remaining credits and final provider debit require separate verification.'))
    if not download:
        return
    evidence = json.loads((HERE / 'credit-check.json').read_text())
    age = datetime.now(timezone.utc) - datetime.fromisoformat(evidence['checked_at_utc'])
    assert age.total_seconds() < 3600 and evidence['remaining_credits_usd'] >= 1
    assert isinstance(sample_cost, (int, float)) and 0 <= sample_cost <= 1
    # Refresh a quote immediately before acquisition, use no automatic retries.
    meta, body = curl('https://hist.databento.com/v0/metadata.get_cost?' + urlencode(PRICE_QUERY), key)
    assert body is not None
    fresh = json.loads(body)
    assert isinstance(fresh, (int, float)) and 0 <= fresh <= 1
    write(HERE / 'pre-download-quote.json', meta | {'quote_usd': fresh})
    db_request(key, 'timeseries.get_range', PRICE_QUERY | dict(encoding='json', compression='none', pretty_px='true', pretty_ts='true', map_symbols='true'), 'sample-daily-bars')
    db_request(key, 'symbology.resolve', dict(dataset='XNAS.ITCH', symbols=PRICE_QUERY['symbols'],
               stype_in='raw_symbol', stype_out='instrument_id', start_date='2018-05-01', end_date='2024-01-01'), 'sample-symbol-map')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['plan','sec','quotes','download'])
    args = parser.parse_args()
    if args.mode == 'sec': sec()
    elif args.mode == 'plan': plan()
    else: databento(getpass.getpass('Databento key (not saved): '), args.mode == 'download')
