"""Independent source-only upper bound: generously relax every purchase filter."""
from collections import defaultdict
from datetime import date
import argparse
import hashlib
import json
import re
import sqlite3

from download_sources import HERE, RAW, POLICY_SHA, policy, atomic


def run(current_rules=False, mandatory_witnesses=False):
    p = policy()
    db=sqlite3.connect('file:'+str(RAW/'submission-index.sqlite')+'?mode=ro',uri=True)
    cohort={x[0] for x in db.execute('SELECT cik FROM cohort')}
    relevant={x[0] for x in db.execute('SELECT owner_cik FROM relevant_owners')}
    subs={a:json.loads(v) for a,v in db.execute('SELECT accession,payload FROM submissions WHERE accession IN (SELECT accession FROM work_accessions)')}
    owners=defaultdict(set)
    allowed_owners=defaultdict(set)
    for a,o,payload in db.execute('SELECT accession,owner_cik,payload FROM owners WHERE accession IN (SELECT accession FROM work_accessions)'):
        owners[a].add(o)
        role=json.loads(payload)
        # Only two explicit negatives establish that the owner lacks both roles.
        if not all(str(role[k]).strip().lower() in {'0','false'} for k in ['isOfficer','isDirector']):
            allowed_owners[a].add(o)
    notes=defaultdict(dict)
    if current_rules:
        for a,i,t in db.execute('SELECT accession,note_id,content FROM footnotes'):
            notes[a][i]=t
    decisions=json.loads((HERE/'footnote-review.json').read_text())['decisions'] if current_rules else {}
    amended_months=set()
    for sub in subs.values():
        if sub['documentType']=='4/A':
            available=max(sub['filingDate'],sub['acceptanceDatetime'][:8])
            amended_months.add((sub['issuerCik'].zfill(10),available[:6]))
    history=defaultdict(list)
    buys=[]
    transaction_titles={}
    exclusions=defaultdict(int)
    for acc,payload in db.execute('SELECT accession,payload FROM transactions'):
        t=json.loads(payload)
        transaction_titles[(acc,t['tableRow'])]=t['securityTitle']
        if t['transactionType']!='nonDerivativeTransaction' or t['transactionCode'] not in {'P','S'}:
            continue
        sub=subs.get(acc)
        if not sub:
            # Unknown submission cannot be used to tighten a purported upper bound.
            for owner in owners[acc]:
                history[owner].append({'date':None,'available':'00000000','accession':acc})
            continue
        filing=sub['filingDate']
        accepted=sub['acceptanceDatetime'][:8]
        available=max(filing,accepted) if len(accepted)==8 and accepted.isdigit() else filing
        try:
            txn=date.fromisoformat(t['transactionDate'])
            if txn.strftime('%Y%m%d')>available:
                txn=None
        except ValueError:
            txn=None
        for owner in owners[acc]:
            history[owner].append({'date':txn,'available':available,'accession':acc})
        if t['transactionCode']=='P' and sub['issuerCik'].zfill(10) in cohort and '20211201'<=available<='20231130':
            current_owners=owners[acc]
            if current_rules:
                if sub['documentType']=='4/A':
                    exclusions['AMENDMENT_NOT_NEW_SIGNAL']+=1;continue
                if owners[acc] and not allowed_owners[acc]:
                    exclusions['NO_OFFICER_DIRECTOR']+=1;continue
                if re.search(r'preferred|warrant|option|phantom|\bunits?\b|deposit[oa]ry|convertible',t['securityTitle'],re.I):
                    exclusions['CLEARLY_NONCOMMON']+=1;continue
                full='\n'.join(notes[acc][k] for k in sorted(notes[acc]))+'\n'+sub.get('remarks','')
                key=hashlib.sha256(' '.join(full.split()).encode()).hexdigest()
                if decisions.get(key,{}).get('signal')=='EXCLUDE':
                    exclusions['EXPLICIT_PLAN']+=1;continue
                current_owners=allowed_owners[acc]
            buys.append({'issuer':sub['issuerCik'].zfill(10),'month':available[:6],
                         'year':int(available[:4]),'owners':current_owners,'accession':acc,
                         'table_row':t['tableRow'],'security_title':t['securityTitle']})
    yearly={}
    for owner,rows in history.items():
        for yr in (2021,2022,2023):
            months={y:set() for y in range(yr-3,yr)}
            for row in rows:
                if row['available']>=f'{yr}0101':
                    continue
                tx=row['date']
                if tx is None:
                    for value in months.values():
                        value.update(range(1,13))
                elif tx.year in months:
                    months[tx.year].add(tx.month)
            every=all(months.values())
            common=set.intersection(*months.values())
            yearly[(owner,yr)]={'three_year_presence':every,'routine_possible':bool(common),
                                'year_month_sets':{str(y):sorted(v) for y,v in months.items()}}
    any_class, routine = {},{}
    for buy in buys:
        # Keep every possible share-class/title path; a witness for an unlisted
        # or unrelated class cannot remove another class's possible opportunity.
        key=(buy['issuer'],buy['month'],buy['security_title'])
        # Unknown owner association is maximally permissive, not a negative label.
        if not buy['owners']:
            any_class[key]=buy;routine[key]=buy
            continue
        for owner in buy['owners']:
            if owner not in relevant or owner=='0000000000':
                # An incompletely projected owner's history cannot tighten the bound.
                any_class[key]=buy;routine[key]=buy
                continue
            labels=yearly.get((owner,buy['year']))
            if labels and labels['three_year_presence']:
                any_class[key]=buy
            if labels and labels['routine_possible']:
                routine[key]=buy
    def counts(rows):
        return {'issuer_months':len({k[:2] for k in rows}),'issuers':len({k[0] for k in rows}),
                'months':len({k[1] for k in rows})}
    witnesses=[]
    if mandatory_witnesses:
        assert current_rules
        ledger=json.loads((RAW/'candidate-ledger.json').read_text())['rows']
        for row in ledger:
            # Only already-valid, single-owner current purchases can be compulsory.
            # Any same-issuer amendment in this month removes the witness entirely.
            key=(row['issuer_cik'],row['disclosure_month'].replace('-',''),
                 transaction_titles[(row['accession'],row['table_row'])])
            acc=row['accession']
            if row['status']!='CANDIDATE' or len(owners[acc])!=1 or key[:2] in amended_months:
                continue
            if len(row['officer_director_owners'])!=1:
                continue
            owner=row['officer_director_owners'][0]
            if owner not in relevant or owner=='0000000000':
                continue
            state=yearly[(owner,int(row['disclosure_day'][:4]))]
            excludes=[]
            if not state['three_year_presence']:
                any_class.pop(key,None)
                excludes.append('NONROUTINE')
            if not state['routine_possible']:
                routine.pop(key,None)
                excludes.append('ROUTINE')
            if excludes:
                witnesses.append({'issuer_cik':key[0],'month':key[1],'accession':acc,
                                  'security_title':key[2],
                                  'table_row':row['table_row'],'owner_cik':owner,
                                  'excluded_classes':excludes,'maximal_history_months':state['year_month_sets']})
    limits=p['minimum_sample_before_price_outcomes']
    gates=[]
    for name,rows,prefix in [('nonroutine',any_class,'nonroutine'),('routine',routine,'routine')]:
        c=counts(rows)
        for metric,key in [('issuer_months',prefix+'_issuer_months'),('issuers',prefix+'_distinct_issuers'),('months',prefix+'_active_entry_months')]:
            gates.append({'sample':name,'metric':metric,'optimistic_upper_bound':c[metric],
                          'required':limits[key],'cannot_reach_minimum':c[metric]<limits[key]})
    result={'policy_sha256':POLICY_SHA,'current_rules_applied':current_rules,
            'mandatory_witnesses_applied':mandatory_witnesses,
            'share_class_safe':True,
            'method':'Historical upper bound uses every source P/S row, even amendments, private/prearranged trades, non-common securities and missing prices. Ignore mixed-owner/month exclusions and liquidity. Invalid dates can fill every historical month. Nonroutine ceiling also counts routine-capable owners. Unprojected/unknown owners may qualify both ways. Refined current rules, when enabled, remove only amendments, explicitly negative officer/director roles, clearly noncommon securities and six exact reviewed trading-plan disclosures.',
            'current_row_exclusions':dict(exclusions),
            'mandatory_witness_rule':'Only exact matching security titles are grouped for necessary witnesses; alternative possible classes/titles remain allowed, and any surviving class keeps the issuer-month in the bound. A valid single-owner current purchase with no possible three-year history blocks both classes for its title; no possible shared month blocks routine for its title. Ignore any issuer-month with a known amendment. Current cases needing review never act as witnesses.',
            'mandatory_witness_count':len(witnesses),
            'raw_purchase_rows':len(buys),'raw_purchase_issuer_months':len({(x['issuer'],x['month']) for x in buys}),
            'nonroutine_upper_bound':counts(any_class),'routine_upper_bound':counts(routine),
            'gates':gates,'status':'STOP_INSUFFICIENT_OPPORTUNITY_UPPER_BOUND' if any(x['cannot_reach_minimum'] for x in gates) else 'UPPER_BOUND_DOES_NOT_REJECT',
            'security_return_observations_read':0}
    suffix='-mandatory-witnesses' if mandatory_witnesses else '-current-rules' if current_rules else ''
    atomic(HERE/f'opportunity-upper-bound{suffix}.json',result)
    atomic(RAW/f'optimistic-owner-year-coverage{suffix}.json',[{'owner_cik':o,'year':y,**v} for (o,y),v in sorted(yearly.items())])
    atomic(RAW/f'optimistic-event-slots{suffix}.json',{'any_classifiable':[{**v,'owners':sorted(v['owners'])} for k,v in sorted(any_class.items())],
                                             'routine':[{**v,'owners':sorted(v['owners'])} for k,v in sorted(routine.items())]})
    if mandatory_witnesses:
        atomic(HERE/'necessary-history-witnesses.json',{'policy_sha256':POLICY_SHA,'witnesses':witnesses})
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--current-rules',action='store_true')
    ap.add_argument('--mandatory-witnesses',action='store_true')
    args=ap.parse_args()
    run(args.current_rules,args.mandatory_witnesses)
