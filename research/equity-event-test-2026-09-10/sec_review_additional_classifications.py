#!/usr/bin/env python3
"""Additional named original-source decisions, offline and before model fitting."""
import json,re
import sec_collect as s
p=s.HERE;path=p/'sec-manual-decisions.json';manual=json.loads(path.read_text());changes=[]
records={
'0001164863-23-000020':('ACCOUNTING_MEASURE_CORRECTION','After the original February21 full results, this filing changes non-GAAP adjusted-income/EPS allocations, not a new original full release.',None,None),
'0001213900-20-017680':('SELECTED_METRICS_UPDATE','Comparable restaurant sales, liquidity and credit amendment; primary expressly calls these selected results.', '2020-06-28',2),
'0001534992-20-000049':('SELECTED_METRICS_UPDATE','Comparable restaurant sales and liquidity only; primary expressly calls these selected results.', '2020-09-27',3),
'0001534992-21-000007':('SELECTED_METRICS_UPDATE','Comparable restaurant sales and liquidity only, with explicit14-week fiscal fourthquarter; not full financial results.', '2021-01-03',4),
'0001444363-20-000004':('SELECTED_METRICS_UPDATE','Monthly operating metrics and quarterly revenue only; not a full quarterly earnings release.',None,None),
'0001529377-20-000045':('SELECTED_METRICS_UPDATE','COVID stakeholder letter provides loan portfolio/liquidity and previously declared cash dividend payment; not fullquarter financial results.',None,None),
'0001101680-23-000096':('FILING_DELAY_ACCOUNTING_REVIEW','Original notice of delayed second-quarter10-Q and ongoing review/restatement of first-quarter revenue; no full secondquarter earnings release.',None,None),
'0001101680-23-000123':('FILING_DELAY_ACCOUNTING_REVIEW','Original third-quarter filing-delay and prior-statement nonreliance notice; no full thirdquarter earnings release and no later restated values used.',None,None),
'0001104659-22-033970':('PRELIMINARY','OriginalItem2.02 expressly gives preliminary unaudited yearend cash only, before finalized annual financial statements.',None,None),
}
for acc,(classification,reason,end,q) in records.items():
 e=json.loads((p/'sec-parsed'/(acc+'.json')).read_text())['event'];primary=s.parser.HTML((s.ROOT/e['primary_file']).read_text()).text
 c=next((c for c in e['exhibit_candidates'] if c.get('file')),None);source=c['file'] if c else e['primary_file'];text=s.parser.HTML((s.ROOT/source).read_text()).text
 fields={'classification':classification,'document_type':classification,'information_scope_note':reason,'period_end':None,'period_evidence':None,'period_candidates':[], 'classification_evidence':{'manual_source_review':reason}}
 if classification=='PRELIMINARY':
  parsed=s.parser.classify_release(primary,e.get('item_202_excerpt',''),e['filing_date'])
  for key in ['period_end','period_evidence','period_candidates','quarter_ordinal','release_date']:fields[key]=parsed.get(key)
 if end:
  assert end in (c.get('period_end'),) or (acc=='0001213900-20-017680' and 'June 28, 2020' in text)
  period={'period_end':end,'kind':'quarter','raw_kind':'original explicit fiscal-quarter selected results','explicit_scopes':['quarter'],'source_file':source,'excerpt':text[:1900]}
  fields.update(period_end=end,period_evidence=period,period_candidates=[period],quarter_ordinal=q)
 manual['events'][acc]={'reason':reason,'source_file':source,'source_sha256':s.digest(s.ROOT/source),'source_excerpt':text[:2000],'primary_support':{'file':e['primary_file'],'sha256':s.digest(s.ROOT/e['primary_file']),'item_202_excerpt':e['item_202_excerpt']},'verified_fields':fields}
 changes.append({'accession':acc,'classification':classification,'source_sha256':s.digest(s.ROOT/source)})
for acc,end,q,release in [('0001564590-20-048932','2020-09-30',3,'2020-10-29'),('0000950170-22-013682','2022-06-30',2,'2022-08-01')]:
 e=json.loads((p/'sec-parsed'/(acc+'.json')).read_text())['event'];report,notice=[c for c in e['exhibit_candidates'] if c.get('file')]
 report_text=s.parser.HTML((s.ROOT/report['file']).read_text()).text;notice_text=s.parser.HTML((s.ROOT/notice['file']).read_text()).text;primary=s.parser.HTML((s.ROOT/e['primary_file']).read_text()).text
 assert re.search(r'quarterly stockholder letter|shareholder report',report_text,re.I)
 assert re.search(r'Statements of Comprehensive Income',report_text,re.I)
 assert 'financial results' in notice_text.lower() and report['period_end']==notice['period_end']==end
 reason='Original Item2.02 package contains the financial-results pressrelease99.2 and its explicitly linked samefiling quarterly shareholder report99.1; fullrelease package, not a call transcript or later website copy.'
 period={'period_end':end,'kind':'quarter','raw_kind':'original quarterly shareholder report and financial-results release','explicit_scopes':['quarter'],'source_file':report['file'],'excerpt':report_text[:1900]}
 companion={'file':report['file'],'url':report['url'],'sha256':s.digest(s.ROOT/report['file']),'document_type':'SHAREHOLDER_LETTER','source_evidence':{'source':'original_same_filing_Item2.02_and_release','accession':acc,'primary_file':e['primary_file'],'primary_sha256':s.digest(s.ROOT/e['primary_file']),'primary_excerpt':e['item_202_excerpt'],'release_excerpt':notice_text[:1700]}}
 fields={**{k:v for k,v in notice.items() if k not in ['file','url','description','classification']},'classification':'EARNINGS_RELEASE','document_type':'EARNINGS_RELEASE','exhibit_file':notice['file'],'exhibit_url':notice['url'],'exhibit_sha256':s.digest(s.ROOT/notice['file']),'release_excerpt':notice_text[:9000],'text_characters':len(notice_text),'release_date':release,'period_end':end,'period_evidence':period,'period_candidates':[period],'quarter_ordinal':q,'accounting_companions':[companion],'classification_evidence':{'manual_source_review':reason}}
 manual['events'][acc]={'reason':reason,'source_file':notice['file'],'source_sha256':s.digest(s.ROOT/notice['file']),'source_excerpt':notice_text[:1800],'additional_evidence':[report_text[:1900]],'primary_support':{'file':e['primary_file'],'sha256':s.digest(s.ROOT/e['primary_file']),'item_202_excerpt':e['item_202_excerpt']},'verified_fields':fields}
 changes.append({'accession':acc,'classification':'EARNINGS_RELEASE','source_sha256':s.digest(s.ROOT/notice['file']),'companion_sha256':companion['sha256']})
s.atomic(path,manual);s.atomic(p/'sec-additional-classification-review.json',{'policy_sha256':s.POLICY_SHA,'network_requests':0,'changes':changes,'scope':'Original document classification, with explicit same-filing companions and no outcome or price inspection.'});print(json.dumps({'reviewed':len(changes)}))
