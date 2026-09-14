#!/usr/bin/env python3
"""Audit as-of accounting coverage; numerical outputs are not a trading model."""
from datetime import date, timedelta
import json
from pathlib import Path
import exchange_calendars as xc
import pandas as pd
from probe import COMPANIES, DATES, HERE, ROOT, RAW, sha, write

CAL = xc.get_calendar('XNYS', start='2008-01-01', end='2024-01-01')
SESSIONS = CAL.sessions


def available(filed):
    i = SESSIONS.searchsorted(pd.Timestamp(filed), side='right')
    return SESSIONS[i + 1].date().isoformat()


def rows(data, tag, cut, unit='USD', namespace='us-gaap'):
    result = []
    for r in data['facts'].get(namespace, {}).get(tag, {}).get('units', {}).get(unit, []):
        if r.get('form') not in ('10-K', '10-K/A', '10-Q', '10-Q/A'):
            continue
        if r['filed'] <= cut and r['end'] <= cut and available(r['filed']) <= cut:
            result.append(r | dict(tag=tag, namespace=namespace, unit=unit, available=available(r['filed'])))
    return result


def choose(rs):
    if not rs:
        return None
    latest = max((r['filed'], r['accn']) for r in rs)
    candidates = [r for r in rs if (r['filed'], r['accn']) == latest]
    # Conflicting entity-level contexts are not resolved by array order.
    if len({r['val'] for r in candidates}) != 1:
        return None
    return candidates[0]


def instant(data, tag, cut, end=None, unit='USD', namespace='us-gaap'):
    rs = [r for r in rows(data, tag, cut, unit, namespace) if 'start' not in r]
    if not rs:
        return None
    target = end or max(r['end'] for r in rs)
    return choose([r for r in rs if r['end'] == target])


def days(r):
    return (date.fromisoformat(r['end']) - date.fromisoformat(r['start'])).days + 1


def ttm(data, tag, cut, target):
    rs = [r for r in rows(data, tag, cut) if 'start' in r]
    annual = choose([r for r in rs if r['end'] == target and 350 <= days(r) <= 380])
    if annual:
        return dict(value=annual['val'], method='reported_full_year', components=[annual])
    current = [r for r in rs if r['end'] == target and 50 <= days(r) < 350]
    if not current:
        return None
    # Prefer the cumulative fiscal YTD fact, not a single quarter or a comparative
    # full-year fact with a later filing fiscal-year label.
    start = min(r['start'] for r in current)
    ytd = choose([r for r in current if r['start'] == start])
    if not ytd:
        return None
    previous_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    prior_annual = choose([r for r in rs if r['end'] == previous_end and 350 <= days(r) <= 380])
    if not prior_annual:
        return None
    prior_ytd = choose([r for r in rs if r['start'] == prior_annual['start']
                        and abs(days(r) - days(ytd)) <= 8
                        and 350 <= (date.fromisoformat(target)-date.fromisoformat(r['end'])).days <= 378])
    if not prior_ytd:
        return None
    return dict(value=prior_annual['val'] + ytd['val'] - prior_ytd['val'],
                method='prior_full_year_plus_current_ytd_minus_prior_ytd',
                components=[prior_annual, ytd, prior_ytd])


def audit():
    manifest = json.loads((HERE / 'sec-manifest.json').read_text())
    output = []
    for label, cik, aliases in COMPANIES:
        record = manifest[label]
        if not record.get('file'):
            output += [dict(label=label, cut=cut, status='SEC_UNAVAILABLE') for cut in DATES]
            continue
        b = (ROOT / record['file']).read_bytes()
        assert sha(b) == record['filtered_sha256']
        data = json.loads(b)
        for cut in DATES:
            a = instant(data, 'Assets', cut)
            target = a['end'] if a else None
            equity = instant(data, 'StockholdersEquity', cut, target)
            eq_method = 'reported_parent_equity'
            if equity is None and target:
                total = instant(data, 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', cut, target)
                minority = instant(data, 'MinorityInterest', cut, target)
                if total and minority:
                    equity = dict(val=total['val'] - minority['val'], end=target, components=[total,minority])
                    eq_method = 'total_equity_minus_noncontrolling_interest'
            net = ttm(data, 'NetIncomeLoss', cut, target) if target else None
            common = ttm(data, 'NetIncomeLossAvailableToCommonStockholdersBasic', cut, target) if target else None
            cash = ttm(data, 'NetCashProvidedByUsedInOperatingActivities', cut, target) if target else None
            shares = instant(data, 'EntityCommonStockSharesOutstanding', cut, unit='shares', namespace='dei')
            if shares is None:
                shares = instant(data, 'CommonStockSharesOutstanding', cut, unit='shares')
            flags = []
            if shares is None:
                flags.append('NO_ENTITY_WIDE_COMMON_SHARE_COUNT_IN_COMPANYFACTS')
            if a and (date.fromisoformat(cut) - date.fromisoformat(a['end'])).days > 550:
                flags.append('STALE_REPORT_PERIOD')
            if a and (date.fromisoformat(cut) - date.fromisoformat(a['filed'])).days > 365:
                flags.append('STALE_FILING')
            if common is None:
                flags.append('COMMON_INCOME_NOT_SEPARATELY_TAGGED_DO_NOT_ASSUME_EQUALS_NET_INCOME')
            rec = dict(label=label, cik=cik, cut=cut, report_end=target,
                       assets=a, parent_equity=equity, equity_method=eq_method,
                       net_income_ttm=net, common_income_ttm=common, operating_cashflow_ttm=cash,
                       reported_common_shares=shares, flags=flags,
                       required_raw_accounting_fields_available=bool(a and equity and (net or common) and cash),
                       exact_original_six_features_qualified=False)
            output.append(rec)
    write(HERE / 'fundamental-coverage.json', output)
    summary = dict(issuer_count=len(COMPANIES), issuer_date_count=len(output),
                   raw_accounting_complete=sum(r.get('required_raw_accounting_fields_available',False) for r in output),
                   common_share_count_available=sum(r.get('reported_common_shares') is not None for r in output),
                   later_filing_values_used=False,
                   caveats=['Reported share counts can be stale and need split/class treatment before market-cap ratios.',
                            'Common income and parent net income are distinct; preferred stock and class coverage need explicit handling.',
                            'This checks raw fields/TTM construction, not the complete six-feature production panel.'])
    write(HERE / 'fundamental-summary.json', summary)
    print(json.dumps(summary,indent=2))
    for label,_,_ in COMPANIES:
        rs=[r for r in output if r['label']==label]
        print(label, [(r['cut'],r.get('report_end'),r.get('required_raw_accounting_fields_available'),bool(r.get('reported_common_shares'))) for r in rs])


if __name__ == '__main__':
    audit()
