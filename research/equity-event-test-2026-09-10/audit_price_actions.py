"""Publish action dates and source qualification without prices or returns."""
import hashlib
import json

from panel import HERE, POLICY_SHA, digest, load_prices, write


def main():
    manifest_raw = (HERE / 'price-manifest.json').read_bytes()
    series, audit = load_prices(manifest=json.loads(manifest_raw))
    result = {
        'policy_sha256': POLICY_SHA,
        'price_manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
        'scope': 'Action dates and qualification only; no price levels or return calculations.',
        'symbols': {},
    }
    exceptions = HERE / 'price-source-exceptions.json'
    result['price_source_exceptions_sha256'] = digest(exceptions) if exceptions.exists() else None
    for ticker, source in series.items():
        result['symbols'][ticker] = {
            'source_sha256': source['source_sha256'],
            'provider_identity_ambiguous': audit[ticker]['provider_identity_ambiguous'],
            'actions': {day: {'splitFactor': row['splitFactor'], 'divCash': row['divCash'],
                             'qualified': day not in source['issues'],
                             'issues': source['issues'].get(day, [])}
                        for day, row in source['rows'].items()
                        if row['splitFactor'] != 1 or row['divCash']},
        }
    checksum = write(HERE / 'action-source-qualification.json', result)
    print(json.dumps({'symbols': len(series), 'sha256': checksum}))


if __name__ == '__main__':
    main()
