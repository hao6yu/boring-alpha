#!/usr/bin/env python3
"""Named source-reviewed classification repairs; no network or outcome access."""
import json,re
import sec_collect as s
p=s.HERE;path=p/'sec-manual-decisions.json';manual=json.loads(path.read_text());changes=[]
groups={
 'PRELIMINARY':{
  '0001193125-20-065263':'Item2.02 incorporates selected unaudited2019financialdata fromItem8.01; actualresults maychange beforeannualaudit finalization. Offeringrelease is not fullannualearnings.',
  '0001055160-20-000012':'Primary explicitly calls bookvalue estimate preliminary for quarter endedMarch31,2020; liquidity/forbearance announcement is not fullresults.',
  '0001193125-20-005816':'Primary explicitly preliminary unfinalized2019 yearend cash estimate; no fullfinancialrelease.',
  '0001193125-21-010198':'Primary explicitly preliminary unfinalized2020 yearend cash estimate; no fullfinancialrelease.',
  '0001564590-20-000550':'Unfinalized year-end cash, equivalents and securities estimate; not full financial results.',
  '0001564590-21-000493':'Unfinalized year-end cash, equivalents and securities estimate; not full financial results.',
  '0000950170-22-000098':'Unfinalized year-end cash, equivalents and securities estimate; not full financial results.',
  '0000950170-23-000179':'Unfinalized year-end cash, equivalents and securities estimate; not full financial results.',
  '0001193125-21-225843':'Clarifies preliminary June30 cash estimate; actual full results remain subject to financial closing.',
  '0001193125-23-026931':'Preliminary year-end cash estimate explicitly states it is not comprehensive financial results.',
  '0001490281-20-000048':'Item2.02 expressly incorporates preliminary first-quarter results from Item8.01; rights agreement is not the earnings release.',
  '0001493152-21-009909':'Shareholder letter says completed first-quarter performance was in line with expectations; full results will follow in May.',
  '0001091907-20-000003':'Estimated full-year AdjustedOIBDA before full financial release; retains prior published guidance context.'},
 'GUIDANCE_UPDATE':{
  '0001493152-21-002462':'Shareholder letter reaffirms previously issued2020 guidance; no full earnings release.',
  '0001638833-21-000008':'Investor-conference guidance based on results only through November; full-year and next-year forecasts.',
  '0001638833-23-000002':'Investor-conference guidance reaffirmation based on results through November; subject to year-end closing.'},
 'SELECTED_METRICS_UPDATE':{
  '0001055160-20-000015':'Current cash and collateral marketvalues related to secondforbearance agreement; not fullquarterresults.',
  '0001104659-20-069459':'Outstanding repurchase obligations and forbearance agreement update; not fullquarterresults.',
  '0000065984-23-000086':'OriginalItem2.02 discloses specific regulatory writeoffs following settlement in principle; not fullquarterearnings.',
  '0000922224-20-000007':'Supplemental unaudited UKsegment information; not full consolidated company release.',
  '0000922224-21-000008':'Supplemental unaudited UKsegment information; not full consolidated company release.',
  '0001638833-20-000032':'Referenced Item7.01 gives current operating disruption, cash balance and liquidity response; not fullquarter release.',
  '0001193125-20-105921':'Referenced Item7.01 gives March31 cash and credit availability alongside credit-agreement amendment.',
  '0001171843-20-003653':'April monthly revenue and consultant update; not full fiscal-quarter earnings.',
  '0001171843-21-000155':'December monthly revenue and consultant update; not full fiscal-quarter earnings.',
  '0001171843-21-002382':'March monthly revenue and consultant update; not full fiscal-quarter earnings.'},
 'OTHER_CORPORATE_UPDATE':{'0001193125-21-034362':'CEO employment agreement announcement; general record-revenue statement does not constitute fullquarter earnings.'},
 'EARNINGS_RELEASE':{
  '0000950170-23-058156':'OriginalItem2.02 fullquarterfinancialresults with consolidated operations table; clinicalupdate opening delayed numericalfinancial evidence.',
  '0001193125-19-312046':'OriginalItem2.02 fullannualresults release with consolidated operations table; revenue-growth headline was a parser false negative.',
  '0001193125-20-032157':'OriginalItem2.02 fullquarterresults release with consolidated operations table; revenue-growth headline was a parser false negative.',
  '0001193125-20-218274':'OriginalItem2.02 fullquarterresults release with consolidated operations table; revenue-growth headline was a parser false negative.',
  '0001193125-21-035313':'OriginalItem2.02 fullquarterresults release with consolidated operations table; revenue-growth headline was a parser false negative.',
  '0001193125-21-243807':'OriginalItem2.02 fullquarterresults release with consolidated operations table; revenue-growth headline was a parser false negative.',
  '0001193125-21-345937':'OriginalItem2.02 fullannualresults release with consolidated operations table; opening clinicaltrials text exceeded financialnumber heuristic.',
  '0000950170-22-001865':'Explicit fourth-quarter/full-year financial-results release with consolidated operations statement; numeric evidence appears beyond heuristic opening limit.',
  '0001628280-22-028987':'OriginalItem2.02 identifies three/nine-month financial results; release contains full condensed consolidated operations statement despite revenue-growth headline.'}}
for classification,records in groups.items():
 for acc,reason in records.items():
  f=p/'sec-parsed'/(acc+'.json')
  if not f.exists():continue
  e=json.loads(f.read_text())['event'];primary=s.parser.HTML((s.ROOT/e['primary_file']).read_text()).text
  fields={'classification':classification,'document_type':classification,'information_scope_note':reason}
  source=e['primary_file'];quote=e['item_202_excerpt'];additional=[]
  if classification=='EARNINGS_RELEASE':
   c=next(x for x in e['exhibit_candidates'] if x.get('file'));source=c['file'];text=s.parser.HTML((s.ROOT/source).read_text()).text
   fields.update({k:v for k,v in c.items() if k not in ['file','url','description','classification']})
   fields.update(classification=classification,exhibit_file=source,exhibit_url=c['url'],exhibit_sha256=s.digest(s.ROOT/source),release_excerpt=text[:9000],text_characters=len(text),document_type='EARNINGS_RELEASE')
   quote=text[:1600]
   match=re.search(r'(?:Condensed )?Consolidated Statements of Operations',text,re.I)
   if not match:raise ValueError('manual_full_release_statement_evidence_missing')
   additional.append(text[match.start():match.start()+500])
  else:
   # Financialscope is not inferred from proximity, month names or segment tables.
   parsed=s.parser.classify_release(primary,e.get('item_202_excerpt',''),e['filing_date'])
   if classification in {'PRELIMINARY','GUIDANCE_UPDATE'}:
    for k in ['period_end','period_evidence','period_candidates','quarter_ordinal','release_date']:
     fields[k]=parsed.get(k)
   else:fields.update(period_end=None,period_evidence=None,period_candidates=[])
   if len(quote)<180 or 'Item 8.01' in primary and acc in {'0001490281-20-000048','0001193125-20-065263'}:
    needle='Item 7.01' if acc in {'0001638833-20-000032','0001193125-20-105921'} else 'Item 8.01' if acc in {'0001490281-20-000048','0001193125-20-065263'} else 'Item 2.02'
    positions=[m.start() for m in re.finditer(re.escape(needle),primary)];position=positions[-1] if positions else 0;quote=primary[position:position+1800]
  if acc=='0001628280-22-028987':
   period={'period_end':'2022-09-30','kind':'quarter','raw_kind':'three months and nine months ended','explicit_scopes':['quarter'],'source':'primary_item_202','source_file':e['primary_file'],'excerpt':e['item_202_excerpt']}
   fields.update(period_end='2022-09-30',period_evidence=period,quarter_ordinal=3,period_candidates=fields.get('period_candidates',[])+[period])
  fields['classification_evidence']={**(fields.get('classification_evidence') or {}),'manual_source_review':reason}
  manual['events'][acc]={'reason':reason,'source_file':source,'source_sha256':s.digest(s.ROOT/source),'source_excerpt':quote,'additional_evidence':additional,'primary_support':{'file':e['primary_file'],'sha256':s.digest(s.ROOT/e['primary_file']),'item_202_excerpt':e['item_202_excerpt']},'verified_fields':fields}
  changes.append({'accession':acc,'classification':classification,'source_file':source,'source_sha256':s.digest(s.ROOT/source)})
s.atomic(path,manual);s.atomic(p/'sec-classification-review.json',{'policy_sha256':s.POLICY_SHA,'changes':changes,'network_requests':0,'scope':'Named original-document source review before fitting; predecessor fiscal scope remains separately checked.'});print(json.dumps({'reviewed':len(changes)}))
