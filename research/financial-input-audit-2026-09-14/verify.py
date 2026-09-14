#!/usr/bin/env python3
"""Adversarial checks for material accounting and look-ahead failure modes."""
from copy import deepcopy
import json

import audit as a


def main():
    a.verify_hashes()
    rows = a.read(a.HERE/'reviewed-evidence.json')['rows']
    rows = {(r['symbol'],r['month']):r for r in rows}
    passed = []

    def rejects(name, original, change, fn):
        row = deepcopy(original)
        change(row)
        try:
            fn(row)
        except ValueError:
            passed.append(name)
        else:
            raise AssertionError(name+' was incorrectly accepted')

    pnr = rows['PNR','2024-01']
    rejects('filing date before the two-session lag', pnr,
            lambda r:r.update(cut='2023-10-25'), a.common_book)
    rejects('equity components from wrong period',pnr,
            lambda r:r['book']['parts'][0].update(end='2022-09-30'),a.common_book)
    rejects('equity component from different filing',pnr,
            lambda r:r['book']['parts'][0].update(accn='0000077360-25-000047'),a.common_book)
    rejects('incomplete trailing-year earnings',pnr,
            lambda r:r['income']['parts'].pop(),a.common_income)
    rejects('net income without common EPS qualification',pnr,
            lambda r:r['income']['parts'][0].update(common_scope_reviewed=False),a.common_income)
    rejects('YTD periods with different fiscal starts',pnr,
            lambda r:r['income']['parts'][2].update(start='2022-04-01'),a.common_income)
    rejects('consolidated income substituted for parent income',rows['MDLZ','2024-01'],
            lambda r:r['income']['parts'][0].update(val=2726000000),a.common_income)
    rejects('continuing income substituted for total earnings',rows['VFC','2026-01'],
            lambda r:r['income']['parts'][2].update(val=50482000),a.common_income)
    fls = rows['FLS','2026-01']
    rejects('preferred tag absence treated as zero',fls,
            lambda r:r['book'].update(preferred_issued_explicit_zero=False),a.common_book)
    rejects('equity including NCI substituted for parent',fls,
            lambda r:r['book']['parts'][0].update(tag='StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',val=2324434000),a.common_book)
    rejects('deferred-compensation equity omitted',rows['FLS','2024-01'],
            lambda r:r['book']['parts'].pop(),a.common_book)
    rejects('unreviewed manual equity value',rows['FLS','2024-01'],
            lambda r:r['book']['parts'][-1].update(val=7879000),a.common_book)
    rejects('negative book changed to positive',rows['HLT','2026-01'],
            lambda r:r['book'].update(expected=4932000000),a.common_book)
    assert a.common_book(rows['HLT','2026-01']) == -4932000000
    assert a.common_book(rows['AON','2024-01']) == -586000000
    passed.append('negative equity retained')
    absent = deepcopy(pnr)
    absent.update(book=None,income=None)
    assert a.common_book(absent) is None and a.common_income(absent) is None
    passed.append('unreviewed fields remain missing')
    # Independent arithmetic from the original three annual/YTD observations.
    assert a.common_income(rows['WHR','2024-01']) == -1614000000
    assert a.common_income(rows['VFC','2026-01']) == 90349000
    assert a.common_book(rows['FLS','2024-01']) == 1874107000
    passed.append('independent signed accounting arithmetic')
    assert a.available('2023-11-03') == '2023-11-07'
    assert a.available('2023-05-25') == '2023-05-30'
    passed.append('weekend and exchange-holiday filing lag')
    results = a.read(a.HERE/'audit-results.json')['rows']
    known = 0
    for row in results:
        for field in ('common_equity','common_income'):
            if row[field+'_before'] is not None:
                assert row[field+'_before'] == row[field+'_after']
                known += 1
    assert known==12
    passed.append('all twelve existing fields unchanged')
    out = dict(status='PASS',count=len(passed),checks=passed,
               limitation='These checks verify arithmetic, source matching and rejection behavior. Accounting-scope certificates remain manual review assertions, not independently certified accounting opinions.')
    a.write('verification.json',out)
    print(json.dumps(out,indent=2))


if __name__=='__main__':
    main()
