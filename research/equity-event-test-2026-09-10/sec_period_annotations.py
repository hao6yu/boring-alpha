"""Explicit 13/14-week quarter endpoints omitted by the original months parser."""
from copy import deepcopy
from datetime import date
import re
import sec_collect as s
PATTERN=re.compile(r'(?P<weeks>thirteen|fourteen|13|14)(?:\s+and\s+(?:twenty[ -]six|twenty[ -]seven|thirty[ -]nine|forty|fifty[ -]two|fifty[ -]three|26|27|39|40|52|53))?[ -]+weeks?(?:\s+periods?)?\s+(?:ended|ending)\s+(?P<end>'+s.parser.DATE_RE+r')',re.I)

def annotate(event):
 e=deepcopy(event)
 if e.get('classification')!='EARNINGS_RELEASE' or not e.get('quarter_ordinal') or not e.get('exhibit_file'):return e
 source=s.ROOT/e['exhibit_file'];text=s.parser.HTML(source.read_text()).text
 section=e.get('item_202_excerpt','');extra=[]
 for label,body in [('original_release',text),('primary_item_202',section)]:
  for match in PATTERN.finditer(body):
   endpoint=s.parser.parse_date(match['end'])
   if endpoint and 0<=(date.fromisoformat(e['filing_date'])-date.fromisoformat(endpoint)).days<200:
    extra.append({'period_end':endpoint,'kind':'quarter','raw_kind':match['weeks']+' weeks','duration_weeks':13 if match['weeks'].lower() in ('thirteen','13') else 14,'explicit_scopes':['quarter'],'quarter_ordinal':e['quarter_ordinal'],'source':label,'source_file':e['exhibit_file'] if label=='original_release' else e.get('primary_file'),'excerpt':body[max(0,match.start()-80):match.end()+100],'rule':'Original release independently labels fiscalquarter; exact13/14-week completed-period endpoint. Duration equality isnotinferred.'})
 if not extra:return e
 candidates={x['period_end'] for x in extra}
 # A competing endpoint is unresolved; never silently replace an existing endpoint.
 if len(candidates)!=1 or (e.get('period_end') and e['period_end'] not in candidates):
  e['week_period_annotation_status']='CONFLICT_REQUIRES_REVIEW';e['extra_week_period_candidates']=extra;return e
 e.setdefault('period_candidates',[]).extend(extra)
 if not e.get('period_end'):
  e['period_end']=extra[0]['period_end'];e['period_evidence']=extra[0]
 e['week_period_annotation_status']='EXPLICIT_QUARTER_ENDPOINT_SOURCE_VERIFIED';e['week_period_annotation_script_sha256']=s.digest(s.HERE/'sec_period_annotations.py')
 return e
