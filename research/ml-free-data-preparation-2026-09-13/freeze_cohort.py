#!/usr/bin/env python3
"""Freeze a dated public roster subset without observing candidate returns."""
import csv
import hashlib
import io
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RAW=ROOT/'data/snapshots'/HERE.name
COMMIT='5dfdfbc3b9f52802f89e72da6e050b5cafdec4a6'
SEED='ba-ml-free-cohort-v1|'

def main():
    b=(RAW/'historical-roster-2018-04-02.csv').read_bytes()
    rows=list(csv.DictReader(io.StringIO(b.decode())))
    assert len(rows)==505 and len({r['Symbol'] for r in rows})==505
    for r in rows:r['selection_hash']=hashlib.sha256((SEED+r['Symbol']).encode()).hexdigest()
    selected=sorted(rows,key=lambda r:(r['selection_hash'],r['Symbol']))[:100]
    output=dict(status='FROZEN_ACQUISITION_COHORT_NOT_INVESTMENT_QUALIFICATION',
                source=f'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/{COMMIT}/data/constituents.csv',
                commit=COMMIT,committer_date='2018-04-02T20:58:25Z',source_sha256=hashlib.sha256(b).hexdigest(),
                original_rows=505,selected_rows=100,selection_seed=SEED,
                selection='First 100 SHA256(seed + original case-sensitive symbol), hexadecimal ascending; one fixed seed, no reselection.',
                caveat='Community-maintained roster at a historical repository commit; not an independently certified S&P constituent history or an index replica.',
                issuer_resolution='Resolve historical issuer/CIK and classes next. Never map reused tickers solely to current company. No return-based replacement for missing or removed names. Any selected same-issuer classes share one issuer weight cap.',
                diagnostic_period='2022-01 through 2023-12; previously seen economic period, not untouched holdout',
                rows=selected)
    (HERE/'next-cohort.json').write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(selected=100,source_sha256=output['source_sha256'])))

if __name__=='__main__':main()
