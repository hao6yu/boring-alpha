#!/usr/bin/env python3
"""Join the fixed accounting sample to dated, raw venue prices; no returns."""
from collections import Counter, defaultdict
from decimal import Decimal
import json
import pandas as pd
from analyze import CAL
from probe import COMPANIES, DATES, HERE, ROOT, RAW, sha, write

SOURCES = dict(
    fb_meta='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125',
    previous_meta_fund='https://www.miaxglobal.com/alert/2022/01/28/miax-exchange-group-options-markets-corporate-action-alert-roundhill-ball-0',
    atvi_acquisition='https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b',
    bbby_suspension='https://www.sec.gov/Archives/edgar/data/886158/000119312523115523/d89202dex991.htm',
    ge_reverse_split='https://www.ge.com/news/press-releases/ge-completes-one-for-eight-reverse-stock-split',
    ge_spinoff='https://www.gehealthcare.com/en-us/about/newsroom/press-releases/ge-healthcare-completes-spin-off-and-begins-trading-on-nasdaq',
)


def audit():
    manifest = json.loads((HERE / 'databento-manifest.json').read_text())
    raw = (ROOT / manifest['sample-daily-bars']['file']).read_bytes()
    assert sha(raw) == manifest['sample-daily-bars']['response_sha256']
    mapping_raw = (ROOT / manifest['sample-symbol-map']['file']).read_bytes()
    assert sha(mapping_raw) == manifest['sample-symbol-map']['response_sha256']
    mappings = json.loads(mapping_raw)['result']
    bars = [json.loads(line) for line in raw.splitlines()]
    by = defaultdict(dict)
    excluded = []
    errors = []
    for r in bars:
        symbol = r['symbol']
        day = r['hd']['ts_event'][:10]
        assert '2018-05-01' <= day < '2024-01-01'
        intervals = [i for i in mappings[symbol] if i['d0'] <= day < i['d1']]
        if len(intervals) != 1 or int(intervals[0]['s']) != r['hd']['instrument_id']:
            errors.append(dict(symbol=symbol,day=day,error='SYMBOL_MAP_MISMATCH'))
        if symbol == 'META' and day < '2022-06-09':
            excluded.append(dict(symbol=symbol,day=day,reason='EARLIER_UNRELATED_META_FUND'))
            continue
        if symbol == 'FB' and day >= '2022-06-09':
            errors.append(dict(symbol=symbol,day=day,error='FB_AFTER_RENAME'))
            continue
        label = 'META' if symbol == 'FB' else symbol
        px = {k:Decimal(r[k]) for k in ('open','high','low','close')}
        valid = all(v.is_finite() and v > 0 for v in px.values()) and int(r['volume']) > 0
        valid = valid and px['low'] <= min(px['open'],px['close']) <= max(px['open'],px['close']) <= px['high']
        if not valid:
            errors.append(dict(symbol=symbol,day=day,error='INVALID_OHLCV'))
        if day in by[label]:
            errors.append(dict(symbol=symbol,day=day,error='DUPLICATE_ISSUER_DATE'))
        by[label][day] = r | {'valid_ohlcv': valid}
    coverage = []
    for label,cik,_ in COMPANIES:
        end = {'ATVI':'2023-10-12','BBBY':'2023-05-02'}.get(label,'2023-12-29')
        expected = {s.date().isoformat() for s in CAL.sessions_in_range('2018-05-01',end)}
        actual = set(by[label])
        coverage.append(dict(label=label,cik=cik,expected_sessions=len(expected),price_days=len(actual),
                             missing_sessions=sorted(expected-actual),unexpected_dates=sorted(actual-expected),
                             first=min(actual),last=max(actual)))
    fundamentals = json.loads((HERE / 'fundamental-coverage.json').read_text())
    joined = []
    for f in fundamentals:
        label,cut = f['label'],f['cut']
        session = CAL.date_to_session(pd.Timestamp(cut),direction='previous').date().isoformat()
        r = by[label].get(session)
        inactive = (label=='ATVI' and cut >= '2023-10-13') or (label=='BBBY' and cut >= '2023-05-03')
        j = dict(label=label,cik=f['cik'],cut=cut,price_session=session,
                 listing_status='REMOVED_FROM_NASDAQ_FEED' if inactive else 'EXPECTED_TRADING',
                 valid_raw_price=bool(r and r['valid_ohlcv']),
                 raw_accounting_available=f['required_raw_accounting_fields_available'],
                 reported_shares_available=bool(f['reported_common_shares']),
                 full_feature_panel_qualified=False)
        if r:
            j.update(symbol=r['symbol'],instrument_id=r['hd']['instrument_id'],raw_close=r['close'])
        joined.append(j)
    active = [j for j in joined if j['listing_status']=='EXPECTED_TRADING']
    summary = dict(raw_rows=len(bars),unrelated_ticker_rows_excluded=len(excluded),
                   retained_rows=sum(len(x) for x in by.values()),
                   source_errors=errors, missing_active_price_sessions=sum(len(c['missing_sessions']) for c in coverage),
                   checked_issuer_dates=len(joined),expected_trading_issuer_dates=len(active),
                   valid_active_price_joins=sum(j['valid_raw_price'] for j in active),
                   raw_accounting_and_price_joins=sum(j['valid_raw_price'] and j['raw_accounting_available'] for j in active),
                   accounting_price_and_reported_shares_joins=sum(j['valid_raw_price'] and j['raw_accounting_available'] and j['reported_shares_available'] for j in active),
                   full_feature_panel_qualified=False,no_strategy_returns=True,
                   semantics='Raw Nasdaq-venue UTC-day bars. Dated alias correction verified. Corporate actions and regular-session fill suitability are not qualified.',
                   event_sources=SOURCES)
    write(HERE/'price-summary.json',summary)
    write(HERE/'price-coverage.json',coverage)
    write(HERE/'sample-joins.json',joined)
    write(HERE/'excluded-unrelated-symbol-rows.json',excluded)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    audit()
