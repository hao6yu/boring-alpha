"""Freeze all verified repairs into otherwise unchanged historical panels."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import gzip,hashlib,json,math,sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RAW=ROOT/'data/snapshots'/HERE.name
OLD=HERE.parent/'ml-stock-comparison-2026-09-14'
RECENT=HERE.parent/'ml-stock-recent-validation-2026-09-14'
FOLLOW=HERE.parent/'ml-stock-followup-2026-09-14'
FIX=HERE.parent/'financial-fix-comparison-2026-09-14'

def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def intact():
    spec=load(HERE/'protocol.json')
    for group in ('prior_files','source_files'):
        for path,digest in spec[group].items():assert sha(ROOT/path)==digest,path
    return spec
def schedule(predictions):
    candidates=[];keep={};orders=[]
    for month in sorted({r['month'] for r in predictions}):
        rows=sorted([r for r in predictions if r['month']==month],key=lambda r:(-r['fixed'],r['symbol']))
        n=len(rows);entry=rows[0]['entry'];keep[entry]=[r['symbol'] for r in rows[:math.ceil(.2*n)]]
        orders.append(dict(month=month,entry=entry,all_symbols=[r['symbol'] for r in rows],entry_count=math.ceil(.1*n),retention_count=math.ceil(.2*n)))
        for rank,r in enumerate(rows[:math.ceil(.1*n)]):
            candidates.append(dict(event_id=f'fixed:{month}:{r["symbol"]}',security_id=r['symbol'],cik=r['cik'],signal_date=r['cut'],
                                   score=r['fixed'],eligibility_status='READY',selection_key=f'{rank:04}:{r["symbol"]}'))
    return dict(candidates=candidates,keep=keep,orders=orders)

def main():
    intact();assert not (HERE/'input-freeze.json').exists(),'Do not overwrite prepared comparison.'
    assert load(FIX/'verification.json')['status']=='PASS'
    assert load(FIX/'provenance-verification.json')['status']=='PASS'
    for path,digest in load(FIX/'extraction-freeze.json')['files'].items():assert sha(ROOT/path)==digest
    RAW.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(OLD));import models
    revised=load(ROOT/'data/snapshots'/FIX.name/'revised-monthly-fundamentals.json')
    revised={(r['symbol'],r['month']):r for r in revised}
    assert len(revised)==5700
    changes=[];summaries={};generated=[]
    for window,folder in [('old',OLD),('recent',RECENT)]:
        raw=ROOT/'data/snapshots'/folder.name
        original={(r['symbol'],r['month']):r for r in load(raw/'monthly-fundamentals.json')}
        before=[r for r in load(raw/'monthly-panel.json') if r['month']>='2022-01']
        after=deepcopy(before)
        for b,a in zip(before,after):
            key=b['symbol'],b['month'];old=original[key];new=revised[key];cap=b['market_cap_proxy']
            assert old['cut']==new['cut']==b['cut'] and old['cik']==new['cik']==b['cik']
            for field,feature in [('common_equity','book_price'),('common_income_ttm','earnings_price')]:
                ov,nv=old[field],new[field]
                if isinstance(ov,dict):ov=ov['value']
                if isinstance(nv,dict):nv=nv['value']
                expected=ov/cap if ov is not None and cap is not None else None
                assert b['features'][feature]==expected,(key,feature)
                if ov is not None:assert ov==nv
                if nv is None:assert a['features'][feature] is None;continue
                if ov is None and cap is not None:
                    a['features'][feature]=nv/cap
                    changes.append(dict(window=window,symbol=b['symbol'],month=b['month'],field=field,feature=feature,
                                        value=nv,denominator=cap,feature_value=nv/cap,eligible=b['eligible']))
            assert {k:v for k,v in b.items() if k!='features'}=={k:v for k,v in a.items() if k!='features'}
            assert all(b['features'][k]==a['features'][k] for k in models.FEATURES[2:])
        saved={(r['symbol'],r['month']):r for r in load(raw/'predictions.json')}
        forecasts={};schedules={}
        for variant,rows in [('before',before),('after',after)]:
            pred=[]
            for month in sorted({r['month'] for r in rows}):
                group=[r for r in rows if r['month']==month and r['eligible']]
                x=models.transformed(group);score=(x[:,0]+x[:,1]+x[:,2]+x[:,3]+x[:,4]-x[:,5])/6
                for row,value in zip(group,score):
                    p=dict(symbol=row['symbol'],cik=row['cik'],month=month,cut=row['cut'],entry=row['entry'],fixed=float(value))
                    if variant=='before':
                        ref=saved[row['symbol'],month]
                        assert all(ref[k]==v for k,v in p.items()),(window,p)
                    pred.append(p)
            forecasts[variant]=pred;schedules[variant]=schedule(pred)
            for name,payload in [('panel',rows),('predictions',pred),('schedule',schedules[variant])]:
                path=RAW/f'{window}-{variant}-{name}.json';write(path,payload);generated.append(path)
        smap={(r['symbol'],r['month']):r for r in forecasts['before']}
        changed_scores=sum(r['fixed']!=smap[r['symbol'],r['month']]['fixed'] for r in forecasts['after'])
        b_orders=schedules['before']['orders'];a_orders=schedules['after']['orders']
        changed_entries=sum(b['all_symbols'][:b['entry_count']]!=a['all_symbols'][:a['entry_count']] for b,a in zip(b_orders,a_orders))
        changed_retention=sum(b['all_symbols'][:b['retention_count']]!=a['all_symbols'][:a['retention_count']] for b,a in zip(b_orders,a_orders))
        summaries[window]=dict(slots=len(before),eligible=len(forecasts['before']),changed_scores=changed_scores,
                               changed_entry_months=changed_entries,changed_retention_months=changed_retention,
                               feature_repairs=sum(x['window']==window for x in changes),
                               eligible_feature_repairs=sum(x['window']==window and x['eligible'] for x in changes))
    whr=revised['WHR','2026-01'];assert whr['common_income_ttm'] is None
    assert next(r for r in load(RAW/'recent-after-panel.json') if r['symbol']=='WHR' and r['month']=='2026-01')['features']['earnings_price'] is None
    write(HERE/'input-checks.json',dict(status='PASS',windows=summaries,source_repairs=189,translated_feature_repairs=len(changes),
        all_original_slots_retained=True,eligibility_unchanged=True,baseline_scores_exactly_reproduced=True,
        unresolved_WHR_income_still_missing=True,parameter_tuning=False,full_extraction_gate_still_failed=True))
    write(HERE/'feature-changes.json',changes)
    paths=generated+[HERE/'protocol.json',HERE/'prepare.py',HERE/'input-checks.json',HERE/'feature-changes.json']
    write(HERE/'input-freeze.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),status='BEFORE_REVISED_RETURN_EVALUATION',
                                      files={str(p.relative_to(ROOT)):sha(p) for p in paths}))
    intact();print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()
