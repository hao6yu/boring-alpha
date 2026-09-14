#!/usr/bin/env python3
"""Offline replay of filing-specific financial input certificates.

This does not build rankings, access market data, or run a trading model.
"""
from datetime import date
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CAL = xcals.get_calendar('XNYS', start='2008-01-01', end='2027-01-01')


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def available(filed):
    # Original convention: two exchange sessions strictly after filing date.
    index = CAL.sessions.searchsorted(pd.Timestamp(filed), side='right')
    return CAL.sessions[index + 1].date().isoformat()


@lru_cache(None)
def payload(cik):
    m = read(ROOT / 'research/ml-stock-recent-validation-2026-09-14/sec-manifest.json')
    return read(ROOT / m[cik]['file'])


@lru_cache(None)
def submissions(cik):
    m = read(ROOT / 'research/ml-stock-comparison-2026-09-14/submissions-manifest.json')
    return read(ROOT / m[cik]['file'])['filings']['recent']


def filing(cik, accn, cut, url):
    sub = submissions(cik)
    require(accn in sub['accessionNumber'], 'unknown accession')
    ix = sub['accessionNumber'].index(accn)
    filed = sub['filingDate'][ix]
    expected = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace("-", "")}/{sub["primaryDocument"][ix]}'
    require(url == expected, 'source URL mismatch')
    require(sub['form'][ix] in ('10-K','10-Q','10-K/A','10-Q/A'), 'unsupported form')
    require(available(filed) <= cut, 'filing unavailable at cutoff')
    return filed


def numeric_fact(cik, part, cut, url):
    filed = filing(cik, part['accn'], cut, url)
    require(part['end'] <= cut, 'future period')
    require(part.get('unit') == 'USD', 'non-USD fact')
    if 'filed' in part:
        require(part['filed'] == filed, 'filing date mismatch')
    if 'available' in part:
        require(part['available'] == available(filed), 'lag mismatch')
    if part.get('source') == 'manual_filing_transcription':
        # One explicitly reviewed statement component, not a generic fallback.
        require((cik,part['accn'],part['end'],part['tag'],part['val']) ==
                ('0000030625','0000030625-23-000136','2023-09-30','DeferredCompensationEquity',7878000),
                'unreviewed manual component')
        return Decimal(part['val'])
    facts = payload(cik)['facts'].get(part.get('namespace','us-gaap'), {})
    rows = facts.get(part['tag'],{}).get('units',{}).get('USD',[])
    rows = [r for r in rows if r.get('accn') == part['accn'] and r['end'] == part['end']
            and r.get('start') == part.get('start') and r['filed'] == filed]
    require(rows and {r['val'] for r in rows} == {part['val']}, 'exact fact mismatch or ambiguity')
    return Decimal(part['val'])


def common_book(row):
    cert = row['book']
    if cert is None:
        return None
    require(cert['common_scope_reviewed'], 'common equity scope not reviewed')
    source = cert['source']
    filed = filing(row['cik'],source['accn'],row['cut'],source['url'])
    require(source['filed'] == filed, 'certificate filing date mismatch')
    require(source['accn'] == row['current']['accn'], 'wrong current filing')
    if cert['method'] == 'parent_less_explicit_zero_preferred_issued':
        require(cert['preferred_issued_explicit_zero'], 'preferred absence is not zero')
        require(len(cert['parts'])==1 and cert['parts'][0]['tag']=='StockholdersEquity', 'not parent equity')
    else:
        require(cert['method']=='reviewed_complete_common_equity_components', 'unreviewed book method')
    total = Decimal(0)
    for p in cert['parts']:
        require(p['accn'] == source['accn'] and p['end'] == row['report_end'] and 'start' not in p,
                'book components from different periods or filings')
        require(p['sign'] in (-1,1), 'invalid component sign')
        total += p['sign'] * numeric_fact(row['cik'],p,row['cut'],source['url'])
    require(total == cert['expected'], 'equity components do not reconcile to reviewed total')
    # Independent filed total: prefer parent, otherwise total minus explicit NCI.
    data = payload(row['cik'])['facts']['us-gaap']
    def balance(tag):
        rs = [r for r in data.get(tag,{}).get('units',{}).get('USD',[])
              if r.get('accn')==source['accn'] and r['end']==row['report_end'] and 'start' not in r]
        require(len({r['val'] for r in rs}) <= 1, 'ambiguous balance')
        return rs[0]['val'] if rs else None
    parent = balance('StockholdersEquity')
    if parent is None:
        consolidated = balance('StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest')
        nci = balance('MinorityInterest')
        if nci is not None:
            parent = consolidated - nci
        else:
            require(row['symbol']=='PNR' and cert['method']=='reviewed_complete_common_equity_components',
                    'NCI not reconciled')
            parent = consolidated  # Explicit ordinary-component certificate, not a zero NCI fact.
    require(total == parent, 'reconstructed equity does not match filed parent scope')
    return int(total)


def common_income(row):
    cert = row['income']
    if cert is None:
        return None
    require(cert['method']=='reviewed_total_basic_common_eps_numerators', 'unreviewed income method')
    parts = cert['parts']
    require(len(parts)==3 and [p['sign'] for p in parts]==[1,1,-1], 'incomplete trailing year')
    annual, current, previous = parts
    require(all(p['common_scope_reviewed'] for p in parts), 'unreviewed EPS numerator')
    require(current['accn']==previous['accn']==row['current']['accn'], 'YTD filing mismatch')
    require(current['end']==row['report_end'], 'wrong current YTD end')
    d = date.fromisoformat
    require(350 <= (d(annual['end'])-d(annual['start'])).days <= 378, 'not full fiscal year')
    require(annual['start']==previous['start'] and annual['end']>previous['end'], 'prior YTD mismatch')
    require((d(current['start'])-d(annual['end'])).days==1, 'fiscal year gap or overlap')
    require(abs((d(current['end'])-d(current['start'])).days-
                (d(previous['end'])-d(previous['start'])).days)<=7, 'YTD duration mismatch')
    total = Decimal(0)
    for p in parts:
        require(p['val']==p['expected'], 'wrong EPS numerator amount')
        total += p['sign'] * numeric_fact(row['cik'],p,row['cut'],p['source_url'])
    return int(total)


def verify_hashes():
    protocol = read(HERE/'protocol.json')
    sources = read(HERE/'source-manifest.json')
    freeze = read(HERE/'extraction-freeze.json')
    groups = [protocol['baseline_files'],protocol['source_files'],
              sources['cached_numeric_and_metadata_files'],sources['web_excerpts']]
    for group in groups:
        for path,digest in group.items():
            require(sha(ROOT/path)==digest, 'changed input: '+path)
    for name,digest in freeze['files'].items():
        require(sha(HERE/name)==digest,'changed frozen certificate: '+name)
    return dict(baseline_files=len(protocol['baseline_files']), original_payloads=len(protocol['source_files']),
                fact_and_submission_payloads=len(sources['cached_numeric_and_metadata_files']),
                web_excerpt_files=len(sources['web_excerpts']), frozen_files=len(freeze['files']))


def main():
    checks = verify_hashes()
    protocol = read(HERE/'protocol.json')
    baseline = read(HERE/'baseline-inputs.json')
    evidence = read(HERE/'reviewed-evidence.json')['rows']
    expected_keys = [(c['symbol'],a['month']) for c in protocol['sample'] for a in c['anchors']]
    require([(r['symbol'],r['month']) for r in evidence]==expected_keys, 'sample changed')
    original = read(ROOT/'data/snapshots/ml-stock-recent-validation-2026-09-14/monthly-fundamentals.json')
    original = {(r['symbol'],r['month']):r for r in original}
    output = []
    for base,cert in zip(baseline,evidence):
        require((base['symbol'],base['month'])==(cert['symbol'],cert['month']), 'baseline order mismatch')
        old = original[base['symbol'],base['month']]
        for k,v in base.items():
            if k != 'current_filing_url':
                require(old[k]==v,'baseline copy mismatch: '+k)
        book = base['common_equity']
        income = base['common_income_ttm']['value'] if base['common_income_ttm'] else None
        reviewed_book,reviewed_income = common_book(cert),common_income(cert)
        require(book is None or reviewed_book is None or reviewed_book==book,'existing book changed')
        require(income is None or reviewed_income is None or reviewed_income==income,'existing income changed')
        output.append(dict(symbol=base['symbol'],month=base['month'],cut=base['cut'],
            common_equity_before=book,common_equity_after=book if book is not None else reviewed_book,
            common_income_before=income,common_income_after=income if income is not None else reviewed_income))
    counts = {field:{phase:sum(r[field+'_'+phase] is not None for r in output)
                     for phase in ('before','after')} for field in ('common_equity','common_income')}
    write('audit-results.json',dict(status='COMPLETED_DATA_AUDIT_ONLY',counts=counts,rows=output,
          sample_company_dates=len(output),checks=checks,new_paid_data_usd=0,
          profitability_evaluations=0,new_fits=0,baseline_unchanged=True))
    print(json.dumps(dict(counts=counts,checks=checks,profitability_evaluations=0),indent=2))


if __name__=='__main__':
    main()
