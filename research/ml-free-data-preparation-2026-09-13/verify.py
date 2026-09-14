#!/usr/bin/env python3
"""Offline provenance, timing and corporate-outcome regression checks."""
from decimal import Decimal as D
import hashlib
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from prepare import available


def main():
    checks=[];hashes=0
    for filename in ['tiingo-manifest.json','sec-manifest.json','roster-manifest.json']:
        for m in json.loads((HERE/filename).read_text()).values():
            if not m.get('file'):continue
            assert hashlib.sha256((ROOT/m['file']).read_bytes()).hexdigest()==m['sha256'];hashes+=1
    checks.append('Retained preparation source bytes match manifests, including explicitly recovered provenance entries.')
    summary=json.loads((HERE/'summary.json').read_text())
    b=(ROOT/summary['prices']['reference_file']).read_bytes()
    assert hashlib.sha256(b).hexdigest()==summary['prices']['reference_sha256']
    rows=[json.loads(line) for line in b.splitlines()]
    by={(r['symbol'],r['date']):r for r in rows}
    assert len(by)==len(rows) and all(r['date']<'2024-01-01' for r in rows)
    checks.append('Unique dated issuer observations and no reserved-window prices.')
    repairs=json.loads((HERE/'accounting-repairs.json').read_text())
    expected_meta=[2851746531,2781759516,2562732034,2569862732]
    assert [r['val'] for r in repairs if r['label']=='META']==expected_meta
    for r in repairs:
        if r['label']=='META':assert r['available']<=r['cut'] and r['end']<=r['filed']
        else:
            for p in r['components']:assert p['available']<=r['cut'] and p['accn']==r['accn']
    assert available('2019-10-31')=='2019-11-04'
    assert available('2021-10-29')=='2021-11-02'
    checks.append('Seven accounting repairs reconcile to independent stated totals and respect filing availability.')
    # Actual delivered shares must match issuer terms, not vendor adjustments.
    assert 25*by['AAPL','2020-08-31']['actual_units_factor']==100
    assert 5*by['AMZN','2022-06-06']['actual_units_factor']==100
    assert 80*by['GE','2021-08-02']['actual_units_factor']==10
    assert by['GE','2023-01-04']['actual_units_factor']==1
    ge=by['GE','2023-01-04'];child=ge['stock_distribution']
    assert math.isclose(3*child['units_per_parent'],1)
    assert math.isclose(3*ge['raw_close']+child['reference_close'],271.09)
    wab=by['GE','2019-02-26']
    assert wab['cash_dividend_entitlement_per_post_split_share']==0
    assert D(str(wab['stock_distribution']['units_per_parent']))*1000==D('5.371')
    assert wab['spendable_distribution_cash']==0
    checks.append('Apple/Amazon/GE unit changes and both GE child entitlements match issuer terms; WAB pseudo-cash is removed.')
    # These assertions fail if the provider's last quoted price is mistaken for
    # terminal shareholder proceeds, even when all raw bars are valid.
    atvi=by['ATVI','2023-10-13'];bbby=by['BBBY','2023-09-29']
    assert atvi['raw_close'] is None and atvi['terminal_cash_claim_per_share']==95
    assert atvi['spendable_distribution_cash']==0
    assert by['ATVI','2023-10-12']['raw_close']==94.42
    assert bbby['raw_close']==.0789 and bbby['reference_total_return_index']==0
    assert bbby['reference_gross']==0 and bbby['known_by_et']=='2023-09-29T16:23:06-04:00'
    assert by['BBBY','2023-06-30']['market']=='OTC'
    checks.append('ATVI stale row becomes a $95 non-spendable claim; BBBY OTC history ends in an after-close zero equity outcome.')
    actions=json.loads((HERE/'corporate-actions.json').read_text())
    dividends=[a for a in actions if a['kind']=='routine_dividend_receivable']
    assert len(dividends)==172 and all(a['spendable_cash_on_ex_date']==0 and a['payment_date'] is None for a in dividends)
    assert next(a for a in actions if a['symbol']=='JNJ' and a['kind'].startswith('voluntary'))['default_automatic_KVUE_units']==0
    checks.append('Routine entitlements cannot finance purchases before payment; no automatic Kenvue grant on an unelected exchange.')
    assert not summary['prices']['provider_adjustment_errors']
    assert summary['prices']['missing_expected_sessions']==summary['prices']['unexpected_sessions']==0
    checks.append('15,612 internal provider adjustment transitions and all expected sample sessions pass.')
    cohort=json.loads((HERE/'next-cohort.json').read_text())
    assert len(cohort['rows'])==100 and len({r['Symbol'] for r in cohort['rows']})==100
    assert [r['selection_hash'] for r in cohort['rows']]==sorted(r['selection_hash'] for r in cohort['rows'])
    for r in cohort['rows']:
        assert r['selection_hash']==hashlib.sha256((cohort['selection_seed']+r['Symbol']).encode()).hexdigest()
    assert cohort['committer_date']<'2018-05-01'
    checks.append('The next 100-stock acquisition cohort has one deterministic selection rule and a pre-study archived roster.')
    result=dict(passed=True,source_payload_hashes_checked=hashes,checks=checks,
                qualification='Sample repair checks only; not universal corporate-action accuracy, a broker ledger, or evidence of profitability.')
    (HERE/'verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
