#!/usr/bin/env python3
"""Free, date-bounded Palatin source qualification. No strategy returns."""
from __future__ import annotations
import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener
from zoneinfo import ZoneInfo

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
RAW=ROOT/'data/snapshots/equity-event-repair-2026-09-10'
POLICY='023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05'
START='2022-07-01';END='2023-10-31'
CALENDAR=ROOT/'data/calendars/nyse-2006-2026-v1.json'
EVENTS=ROOT/'research/equity-event-pilot-2026-09-10/sec-events.json'
NY=ZoneInfo('America/New_York')
def sha(b):return hashlib.sha256(b).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    b=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(b);tmp.replace(path)
    return sha(b)
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None
def fetch(url,name,manifest):
    deadline=datetime.fromisoformat(json.loads((HERE/'policy.json').read_text())['deadline_utc'].replace('Z','+00:00'))
    if (deadline-datetime.now(timezone.utc)).total_seconds()<25:raise ValueError('deadline_no_new_request')
    if urlsplit(url).hostname not in {'query1.finance.yahoo.com','api.nasdaq.com','help.yahoo.com','palatin.com','finance.yahoo.com','stooq.com','www.annualreports.com'}:raise ValueError('unapproved_host')
    existing=next((r for r in manifest['requests'] if r['url']==url and r.get('status')==200),None)
    if existing:
        b=(ROOT/existing['file']).read_bytes()
        if sha(b)!=existing['sha256']:raise ValueError('cache_hash')
        return b
    if len(manifest['requests'])>=10:raise ValueError('bounded_public_request_cap')
    if any(r.get('status')==429 and urlsplit(r['url']).hostname==urlsplit(url).hostname for r in manifest['requests']):raise ValueError('host_rate_limit_stop')
    context=ssl.create_default_context()
    if not context.cert_store_stats()['x509_ca']:context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    opener=build_opener(HTTPSHandler(context=context),NoRedirect())
    rec={'url':url,'started_at':stamp()};manifest['requests'].append(rec);save(HERE/'ptn-source-manifest.json',manifest)
    try:
        request=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; BoringAlphaResearch/0.1; public historical-data audit)','Accept':'application/json,text/html,text/csv;q=0.9','Accept-Encoding':'identity'})
        with opener.open(request,timeout=20) as response:
            raw=response.read(10_000_001);rec.update(status=response.status,received_at=stamp(),content_type=response.headers.get('Content-Type'))
            if len(raw)>10_000_000:raise ValueError('payload_bound')
            if response.status!=200 or response.url!=url:raise ValueError('unexpected_response')
        file=RAW/name;file.parent.mkdir(parents=True,exist_ok=True);tmp=file.with_suffix(file.suffix+'.tmp');tmp.write_bytes(raw);tmp.replace(file)
        rec.update(file=str(file.relative_to(ROOT)),bytes=len(raw),sha256=sha(raw));save(HERE/'ptn-source-manifest.json',manifest);return raw
    except HTTPError as e:
        rec.update(status=e.code,retry_after=e.headers.get('Retry-After'),finished_at=stamp(),error_type=type(e).__name__);save(HERE/'ptn-source-manifest.json',manifest);return None
    except Exception as e:
        rec.update(error_type=type(e).__name__,finished_at=stamp());save(HERE/'ptn-source-manifest.json',manifest);return None

def yahoo_url():
    p1=int(datetime(2022,7,1,tzinfo=timezone.utc).timestamp());p2=int(datetime(2023,11,1,tzinfo=timezone.utc).timestamp())
    return 'https://query1.finance.yahoo.com/v8/finance/chart/PTN?'+urlencode({'period1':p1,'period2':p2,'interval':'1d','events':'div,splits','includeAdjustedClose':'true'})
def assess_yahoo(raw):
    d=json.loads(raw)
    if d.get('chart',{}).get('error'):return {'status':'PROVIDER_ERROR','provider_error':d['chart']['error']}
    results=d.get('chart',{}).get('result')
    if not results:return {'status':'NO_RESULT'}
    r=results[0];meta=r.get('meta',{});timestamps=r.get('timestamp',[])
    dates=[datetime.fromtimestamp(t,timezone.utc).astimezone(NY).date().isoformat()for t in timestamps]
    # Check date bounds before inspecting any numerical historical quote field.
    if any(not START<=d<=END for d in dates):return {'status':'REJECTED_OUT_OF_SCOPE_DATES_WITHOUT_PRICE_INSPECTION','dates_only':dates}
    if len(set(dates))!=len(dates)or dates!=sorted(dates):raise ValueError('duplicate_or_unsorted_dates')
    q=r.get('indicators',{}).get('quote',[{}])[0];adj=r.get('indicators',{}).get('adjclose',[{}])[0].get('adjclose',[])
    lengths={k:len(v)for k,v in q.items()}
    if any(v!=len(dates)for v in lengths.values())or len(adj)!=len(dates):raise ValueError('array_lengths')
    rows={};issues={}
    for i,day in enumerate(dates):
        v={k:q[k][i]for k in ('open','high','low','close','volume')};v['adjusted_close']=adj[i]
        faults=[]
        if any(x is None or not isinstance(x,(int,float))or not math.isfinite(x)for x in v.values()):faults.append('missing_or_invalid_numeric_value')
        elif not 0<v['low']<=min(v['open'],v['close'])<=max(v['open'],v['close'])<=v['high']:faults.append('invalid_ohlc')
        elif v['adjusted_close']<=0 or v['volume']<=0:faults.append('invalid_adjusted_close_or_zero_volume')
        rows[day]=v
        if faults:issues[day]=faults
    sessions=json.loads(CALENDAR.read_text())['sessions'];required=[d for d in sessions if START<=d<=END]
    slots=[]
    for event in json.loads(EVENTS.read_text())['slots']:
        if event['cik']!='0000911216':continue
        e=event['current'];anchor=max(e['filing_date'],e['acceptance_eastern'][:10]);entry=bisect_right(sessions,anchor);window=sessions[entry-60:entry+21]
        missing=[d for d in window if d not in rows];invalid={d:issues[d]for d in window if d in issues}
        slots.append({'slot_id':event['slot_id'],'entry_session':sessions[entry],'expected_sessions':len(window),'start':window[0],'end':window[-1],'missing_sessions':missing,'invalid_sessions':invalid,'source_coverage_success':len(window)==81 and not missing and not invalid,'qualified_price_window_success':False})
    name=meta.get('longName')or meta.get('shortName')
    out={'status':'COVERAGE_ONLY_PRICE_BASIS_AND_ACTIONS_NOT_QUALIFIED','provider':'Yahoo public chart','symbol':meta.get('symbol'),'issuer_name':name,'currency':meta.get('currency'),'exchange_name':meta.get('fullExchangeName')or meta.get('exchangeName'),'instrument_type':meta.get('instrumentType'),'identity_name_match':bool(name and 'PALATIN'in name.upper() and meta.get('symbol')=='PTN'),'rows':len(rows),'first_session':min(rows)if rows else None,'last_session':max(rows)if rows else None,'expected_period_sessions':len(required),'missing_period_sessions':[d for d in required if d not in rows],'unexpected_dates':sorted(set(rows)-set(sessions)),'invalid_sessions':issues,'provider_reported_events':r.get('events',{}),'event_field_present':'events'in r,'price_basis':'Not yet qualified; Yahoo Close may be restated for subsequent splits. adjusted_close is split/dividend adjusted per official documentation. Never relabeled raw.','unresolved_reasons':['UNADJUSTED_HISTORICAL_OHLC_NOT_ESTABLISHED','COMPLETE_CORPORATE_ACTION_HISTORY_NOT_ESTABLISHED'],'slots':slots}
    observation_path=RAW/'ptn-yahoo-observations.json'
    observation_hash=save(observation_path,{'policy_sha256':POLICY,'basis':out['price_basis'],'rows':rows})
    out['observations']={'file':str(observation_path.relative_to(ROOT)),'sha256':observation_hash}
    save(HERE/'ptn-yahoo-observations.json',{'policy_sha256':POLICY,'local_observations':out['observations'],'rows':len(rows),'price_basis':out['price_basis'],'qualified':False})
    return out

def evidence_and_finalize(assessment,manifest):
    """Offline source classification; no reconstruction or strategy arithmetic."""
    for record in manifest['requests']:
        if record.get('status')!=200:
            record['payload_classification']='HTTP_FAILURE'
            continue
        raw=(ROOT/record['file']).read_bytes()
        if sha(raw)!=record['sha256']:raise ValueError('source_hash')
        host=urlsplit(record['url']).hostname
        if host=='api.nasdaq.com':
            x=json.loads(raw);data=x.get('data')or{}
            record['provider_status']=x.get('status')
            record['payload_classification']='EMPTY_HISTORICAL_RESPONSE'if x.get('status',{}).get('rCode')==200 and data.get('totalRecords')==0 else 'PROVIDER_PARAMETER_ERROR'
        elif host=='stooq.com':
            record['payload_classification']='BROWSER_VERIFICATION_HTML_NOT_PRICE_DATA'
        elif host=='query1.finance.yahoo.com':record['payload_classification']='BOUNDED_HISTORICAL_CHART_336_SESSIONS'
        else:record['payload_classification']='SOURCE_DOCUMENT'
    report=RAW/'ptn-annual-report-2023.pdf'
    body=subprocess.check_output(['pdftotext','-layout',str(report),'-']).decode()
    if 'PALATIN TECHNOLOGIES, INC.'not in body:raise ValueError('issuer_report_identity')
    dividend=re.search(r'Dividends and dividend policy\. We have never declared or paid any dividends\.',body)
    anchor=re.search(r'On June 20, 2023, the Chairman of the board of directors.{0,1000}?the business day immediately preceding the date of\s+grant',body,re.S)
    if not dividend or not anchor or '$2.19' not in anchor.group(0):raise ValueError('primary_evidence_not_found')
    sessions=json.loads(CALENDAR.read_text())['sessions']
    previous_session=sessions[sessions.index('2023-06-20')-1]
    if previous_session!='2023-06-16':raise ValueError('anchor_session')
    observations=json.loads((RAW/'ptn-yahoo-observations.json').read_text())['rows']
    source_close=observations[previous_session]['close']
    anchor_ratio=source_close/2.19
    # This is a single source-basis check, never a return, backtest or transformed series.
    primary_sources=[
      {'id':'issuer_2022_split','url':'https://palatin.com/press_releases/palatin-announces-intent-to-effect-reverse-stock-split/','facts':{'new_shares':1,'old_shares':25,'legal_effective_eastern':'2022-08-30T17:00:00-04:00','expected_adjusted_trading_session':'2022-08-31','post_split_cusip':'696077502','historical_symbol':'PTN','historical_exchange':'NYSE American'},'scope':'Issuer announcement; corroborated by the FY2023 annual report and the chart split event.'},
      {'id':'issuer_2025_split','url':'https://palatin.com/press_releases/palatin-announces-1-for-50-reverse-stock-split/','facts':{'new_shares':1,'old_shares':50,'announced_legal_effective_eastern':'2025-08-08T17:00:00-04:00','expected_adjusted_trading_session':'2025-08-11','post_split_cusip':'696077601'},'scope':'Action-only issuer announcement. Not a complete later-action ledger or an executed-date confirmation; no 2024–2025 price series was requested.'},
      {'id':'issuer_2023_annual_report','url':'https://www.annualreports.com/HostedData/AnnualReportArchive/p/AMEX_PTN_2023.pdf','file':str(report.relative_to(ROOT)),'sha256':sha(report.read_bytes()),'scope':'Issuer-authored FY2023 report on a third-party document mirror. Its dividend statement is not extended through October 2023.'},
      {'id':'yahoo_adjusted_close_help','url':'https://help.yahoo.com/kb/SLN28256.html','scope':'Official provider definition: adjusted close incorporates splits and dividend distributions; this does not establish raw OHLC or volume adjustment semantics.'}
    ]
    evidence={'policy_sha256':POLICY,'created_at':stamp(),'source_documents':primary_sources,'identity':{'issuer':'Palatin Technologies, Inc.','cik':'0000911216','historical_common_stock_symbol':'PTN','historical_exchange':'NYSE American','current_provider_name_match':assessment['identity_name_match'],'current_provider_exchange_is_not_historical_evidence':True},'dividends':{'issuer_statement':dividend.group(0),'document_fiscal_year_end':'2023-06-30','document_current_information_date':'2023-09-27','reported_yahoo_dividend_events':0,'absence_of_dividend_key_is_not_zero_event_proof':True,'through_october_2023_verified':False},'historical_close_anchor':{'source_excerpt':re.sub(r'\s+',' ',anchor.group(0)),'grant_date':'2023-06-20','preceding_regular_session':previous_session,'issuer_reported_close_usd':2.19,'yahoo_current_historical_close':source_close,'source_to_contemporaneous_ratio':anchor_ratio,'matches_50_factor':math.isclose(anchor_ratio,50,rel_tol=0,abs_tol=1e-10),'conclusion':'The downloaded close is not contemporaneous raw; this one anchor is consistent with the later 1:50 split. It does not certify every OHLC field or the complete adjustment chain.'},'volume':{'provider_basis_verified':False,'independent_historical_volume_anchor':None,'inversion_performed':False},'reconstruction':{'performed':False,'reason':'Complete subsequent corporate actions and OHLC/volume adjustment semantics remain unresolved; a single price anchor cannot justify a full raw reconstruction.'},'network_stop':'Bounded ten-request pass completed; no browser verification workaround or further vendor search.','no_strategy_returns':True}
    evidence_hash=save(HERE/'ptn-evidence.json',evidence)
    assessment['evidence']={'file':str((HERE/'ptn-evidence.json').relative_to(ROOT)),'sha256':evidence_hash}
    assessment['status']='REPAIR_COMPLETE_COVERAGE_ONLY_UNQUALIFIED'
    assessment['price_basis']='Split-restated close, independently shown at 2023-06-16; OHLC and volume have not been certified or inverted to contemporaneous raw units.'
    assessment['volume_basis_verified']=False
    assessment['complete_subsequent_actions_verified']=False
    assessment['dividends_through_2023_10_31_verified']=False
    assessment['unresolved_reasons']=['ALL_OHLC_ADJUSTMENT_SEMANTICS_UNVERIFIED','VOLUME_ADJUSTMENT_BASIS_AND_RAW_ANCHOR_UNVERIFIED','COMPLETE_SUBSEQUENT_CORPORATE_ACTIONS_UNVERIFIED','DIVIDEND_HISTORY_THROUGH_OCTOBER_2023_UNVERIFIED']
    for slot in assessment['slots']:
        slot['qualified_price_window_success']=False
        slot['unresolved_reasons']=assessment['unresolved_reasons'][:3]+(['DIVIDEND_HISTORY_THROUGH_WINDOW_END_UNVERIFIED']if slot['end']>'2023-09-27'else[])
    manifest.update(status='BOUNDED_PASS_FINISHED_NO_QUALIFIED_PRICE_WINDOWS',finished_at=stamp(),new_paid_cost_usd=0)
    manifest_hash=save(HERE/'ptn-source-manifest.json',manifest)
    assessment['source_manifest']={'file':str((HERE/'ptn-source-manifest.json').relative_to(ROOT)),'sha256':manifest_hash}
    return assessment
def main():
    a=argparse.ArgumentParser();a.add_argument('command',choices=['yahoo','nasdaq','assess','evidence','finalize']);a=a.parse_args()
    if sha((HERE/'policy.json').read_bytes())!=POLICY:raise ValueError('policy_hash')
    mp=HERE/'ptn-source-manifest.json';manifest=json.loads(mp.read_text())if mp.exists()else{'policy_sha256':POLICY,'start':START,'end':END,'requests':[],'no_strategy_returns':True,'no_reserved_period_prices':True}
    if a.command=='evidence':
        docs=[('https://www.annualreports.com/HostedData/AnnualReportArchive/p/AMEX_PTN_2023.pdf','ptn-annual-report-2023.pdf')]
        for url,name in docs:
            b=fetch(url,name,manifest);print(json.dumps({'document':name,'downloaded':b is not None}))
        return
    if a.command=='yahoo':raw=fetch(yahoo_url(),'ptn-yahoo-chart.json',manifest)
    elif a.command=='nasdaq':
        u='https://api.nasdaq.com/api/quote/PTN/historical?'+urlencode({'assetclass':'stocks','fromdate':'2022-07-01','todate':'2023-10-31','limit':'9999'})
        raw=fetch(u,'ptn-nasdaq-history.json',manifest);print(json.dumps({'downloaded':raw is not None}));return
    else:raw=(RAW/'ptn-yahoo-chart.json').read_bytes()
    assessment=assess_yahoo(raw)if raw else{'status':'REQUEST_FAILED','qualified_price_window_success':False}
    if a.command=='finalize':assessment=evidence_and_finalize(assessment,manifest)
    assessment.update(policy_sha256=POLICY,calendar_sha256=sha(CALENDAR.read_bytes()),events_sha256=sha(EVENTS.read_bytes()),created_at=stamp(),script_sha256=sha(Path(__file__).read_bytes()))
    digest=save(HERE/'ptn-qualification.json',assessment)
    print(json.dumps({'status':assessment['status'],'rows':assessment.get('rows'),'issuer':assessment.get('issuer_name'),'coverage_windows':sum(x['source_coverage_success']for x in assessment.get('slots',[])),'qualified_windows':sum(x['qualified_price_window_success']for x in assessment.get('slots',[])),'sha256':digest}),flush=True)
if __name__=='__main__':main()
