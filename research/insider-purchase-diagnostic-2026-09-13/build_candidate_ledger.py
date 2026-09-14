"""Construct source-only event and history ledgers; never reads security returns."""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3

from diagnostic_io import HERE, ROOT, RAW, SOURCE_RAW, SOURCE_HERE, POLICY_SHA, policy, atomic
from insider_rules import truth, disclosure_day, transaction_state, linked_footnotes, disclosure_flags, classify, transaction_day


def run():
    p = policy()
    assert datetime.now(timezone.utc) < datetime.fromisoformat(p['deadline_utc'])
    db = sqlite3.connect('file:' + str(SOURCE_RAW / 'submission-index.sqlite') + '?mode=ro', uri=True)
    source_audit = json.loads((SOURCE_HERE / 'table-projection-audit.json').read_text())
    assert source_audit['status'] == 'ALL_PROJECTION_PASSES_COMPLETE'
    assert all(source_audit[k]==0 for k in ['transaction_row_conflicts','footnote_id_conflicts','owner_role_conflicts'])
    subs = {acc:json.loads(v) for acc,v in db.execute('SELECT accession,payload FROM submissions WHERE accession IN (SELECT accession FROM work_accessions)')}
    owners, notes, trades = defaultdict(list), defaultdict(dict), defaultdict(list)
    for acc,v in db.execute('SELECT accession,payload FROM owners WHERE accession IN (SELECT accession FROM work_accessions)'):
        owners[acc].append(json.loads(v))
    for acc,i,t in db.execute('SELECT accession,note_id,content FROM footnotes'):
        notes[acc][i] = t
    for acc,v in db.execute('SELECT accession,payload FROM transactions'):
        trades[acc].append(json.loads(v))
    cohort = {r[0] for r in db.execute('SELECT cik FROM cohort')}
    relevant = {r[0] for r in db.execute('SELECT owner_cik FROM relevant_owners')}
    db.close()
    codebook_path = HERE / 'footnote-review.json'
    codebook = json.loads(codebook_path.read_text())['decisions'] if codebook_path.exists() else {}
    review, histories, uncertain = {}, defaultdict(list), defaultdict(list)
    event_rows, history_counts = [], Counter()
    quarantined = {'0001626199-23-000025'}

    def queue(text, reason, acc, t):
        normalized = ' '.join(text.split())
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        if digest not in review:
            review[digest] = {'text':normalized, 'reasons':[], 'examples':[], 'row_count':0}
        block = review[digest]
        if reason not in block['reasons']:
            block['reasons'].append(reason)
        if len(block['examples']) < 4:
            block['examples'].append({'accession':acc,'row':t['tableRow'],'code':t['transactionCode'],
                                      'title':t['securityTitle'],'transaction_date':t['transactionDate']})
        block['row_count'] += 1
        return digest, codebook.get(digest)

    for acc, txns in trades.items():
        sub = subs.get(acc)
        if sub is None:
            continue
        try:
            public = disclosure_day(sub)
        except (ValueError, KeyError):
            public = None
        person = owners.get(acc, [])
        for t in txns:
            state, flags = transaction_state(t, sub, notes[acc])
            if state == 'NOT_PS':
                continue
            history_counts[state] += 1
            text, missing = linked_footnotes(t, notes[acc])
            text += '\n' + sub.get('remarks','')
            hist_status = state
            review_id = None
            if state == 'PS_FIELDS_VALID' and 'NONMARKET_OR_PRIVATE_REVIEW' in flags:
                review_id, decision = queue(text, 'HISTORY_NONMARKET', acc, t)
                hist_status = 'PS_FIELDS_VALID' if decision and decision['history']=='ALLOW' else 'EXCLUDED_NONMARKET' if decision and decision['history']=='EXCLUDE' else 'HISTORY_NOTE_UNRESOLVED'
            if state == 'SECURITY_TITLE_REVIEW':
                review_id, decision = queue(t['securityTitle']+'\n'+text, 'SECURITY_TITLE', acc, t)
                hist_status = transaction_state({**t, 'securityTitle':'Common Stock'}, sub, notes[acc])[0] if decision and decision['history']=='ALLOW' else 'EXCLUDED_NONMARKET' if decision and decision['history']=='EXCLUDE' else 'SECURITY_TITLE_REVIEW'
            if acc in quarantined:
                hist_status = 'TIMESTAMP_QUARANTINE'
            if len(person) != 1 and hist_status == 'PS_FIELDS_VALID':
                hist_status = 'JOINT_OWNER_ASSOCIATION_UNRESOLVED'
            txyear = int(t['transactionDate'][:4]) if len(t['transactionDate'])>=4 and t['transactionDate'][:4].isdigit() else None
            for owner in person:
                cik = owner['rptOwnerCik']
                if cik not in relevant:
                    continue
                if hist_status == 'PS_FIELDS_VALID' and public:
                    histories[cik].append({'accession':acc,'table_row':t['tableRow'],
                                           'transaction_date':transaction_day(t['transactionDate']),'disclosure_day':public})
                elif hist_status not in {'NOT_COMMON','EXCLUDED_NONMARKET'}:
                    uncertain[cik].append({'accession':acc,'table_row':t['tableRow'],'review_id':review_id,'reason':hist_status,'year':txyear,
                                           'disclosure_day':public})
            if t['transactionCode'] != 'P' or sub['issuerCik'].zfill(10) not in cohort or not public or not '2021-12-01'<=public<='2023-11-30':
                continue
            relevant_people = [o['rptOwnerCik'] for o in person if truth(o['isOfficer']) or truth(o['isDirector'])]
            record = {'accession':acc,'table_row':t['tableRow'],'issuer_cik':sub['issuerCik'].zfill(10),
                      'disclosure_day':public,'disclosure_month':public[:7], 'transaction_date':t['transactionDate'],
                      'security_title':t['securityTitle'], 'shares':t['transactionShares'],'reported_price':t['transactionPricePerShare'],
                      'officer_director_owners':relevant_people,'field_status':state,
                      'history_row_status':hist_status,'status':'CANDIDATE', 'review_id':review_id}
            if sub['documentType']!='4':
                record['status']='AMENDMENT_NOT_NEW_SIGNAL'
            elif not relevant_people:
                record['status']='NO_OFFICER_OR_DIRECTOR'
            elif hist_status != 'PS_FIELDS_VALID':
                record['status']=hist_status
            elif (date.fromisoformat(public)-date.fromisoformat(transaction_day(t['transactionDate']))).days>90:
                record['status']='TRANSACTION_TOO_OLD'
            elif t.get('equitySwapInvolved')=='1':
                record['status']='EQUITY_SWAP_UNRESOLVED'
            else:
                # Read the full filing's note context before certifying a current signal.
                full_text = '\n'.join(notes[acc][k] for k in sorted(notes[acc]))+'\n'+sub.get('remarks','')
                full_flags = disclosure_flags(full_text)
                if full_flags:
                    digest, decision = queue(full_text, 'CURRENT_PURCHASE_CONTEXT', acc, t)
                    record['review_id']=digest
                    if not decision:
                        record['status']='CURRENT_NOTE_UNRESOLVED'
                    elif decision['signal']=='EXCLUDE':
                        record['status']='DISCLOSED_PLAN_OR_NONMARKET'
                    elif decision['signal']!='ALLOW':
                        record['status']='CURRENT_NOTE_UNRESOLVED'
            full_text = '\n'.join(notes[acc][k] for k in sorted(notes[acc]))+'\n'+sub.get('remarks','')
            full_digest = hashlib.sha256(' '.join(full_text.split()).encode()).hexdigest()
            full_decision = codebook.get(full_digest)
            if full_decision and full_decision['signal'] == 'EXCLUDE' and record['status'] != 'AMENDMENT_NOT_NEW_SIGNAL':
                record['status'] = 'DISCLOSED_PLAN_OR_NONMARKET'
            event_rows.append(record)

    labels = {}
    for owner in relevant:
        for year in [2021,2022,2023]:
            # Later corrections never contaminate an earlier annual classification.
            past_uncertain = [u for u in uncertain[owner] if u['disclosure_day'] and u['disclosure_day']<f'{year}-01-01']
            years = [u['year'] for u in past_uncertain if u['year'] is not None]
            if any(u['year'] is None for u in past_uncertain):
                years += list(range(year-3,year))
            labels[(owner,year)] = classify(histories[owner],year,years)
    grouped = defaultdict(list)
    for row in event_rows:
        if row['status']=='CANDIDATE':
            labs = [labels.get((o,int(row['disclosure_day'][:4])),'UNKNOWN_MISSING_OWNER') for o in row['officer_director_owners']]
            row['owner_labels']=labs
            row['classification'] = labs[0] if labs and len(set(labs))==1 else 'MIXED_OR_UNKNOWN'
            grouped[(row['issuer_cik'],row['disclosure_month'])].append(row)
    uncertain_current = defaultdict(list)
    clear_exclusions = {'NO_OFFICER_OR_DIRECTOR', 'NOT_COMMON', 'EXCLUDED_NONMARKET',
                        'DISCLOSED_PLAN_OR_NONMARKET', 'TRANSACTION_TOO_OLD'}
    for row in event_rows:
        if row['status'] != 'CANDIDATE' and row['status'] not in clear_exclusions:
            uncertain_current[(row['issuer_cik'],row['disclosure_month'])].append(row)
    slots=[]
    for (cik,month),rows in sorted(grouped.items()):
        labs={r['classification'] for r in rows}
        slots.append({'issuer_cik':cik,'disclosure_month':month,
                      'classification':('UNRESOLVED_CURRENT_PURCHASE' if uncertain_current[(cik,month)] else next(iter(labs)) if len(labs)==1 else 'MIXED_OR_UNKNOWN'),
                      'unresolved_transaction_keys':[[r['accession'],r['table_row']] for r in uncertain_current[(cik,month)]],
                      'transaction_keys':[[r['accession'],r['table_row']] for r in rows]})
    counts={}
    for category in ['NONROUTINE','ROUTINE']:
        selected=[s for s in slots if s['classification']==category]
        counts[category]={'issuer_months':len(selected),'issuers':len({s['issuer_cik'] for s in selected}),
                          'months':len({s['disclosure_month'] for s in selected})}
    result={'policy_sha256':POLICY_SHA,'status':'SOURCE_CLASSIFICATION_PENDING_REVIEW',
            'history_field_states':dict(history_counts),'event_row_states':dict(Counter(r['status'] for r in event_rows)),
            'classification_counts':counts,'slot_classifications':dict(Counter(s['classification'] for s in slots)),
            'review_texts':len(review),'unreviewed_texts':len(set(review)-codebook.keys()),
            'all_event_rows':len(event_rows),'cohort_issuer_month_slots':200*24,
            'completed_at_utc':datetime.now(timezone.utc).isoformat(),'security_return_observations_read':0}
    atomic(RAW/'candidate-ledger.json',{'policy_sha256':POLICY_SHA,'rows':event_rows,'slots':slots})
    atomic(RAW/'owner-histories.json',{'history':dict(histories),'uncertainties':dict(uncertain),
                                      'labels':[{'owner_cik':o,'disclosure_year':y,'label':l} for (o,y),l in sorted(labels.items())]})
    atomic(RAW/'footnote-review-queue.json',review)
    atomic(HERE/'candidate-source-summary.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    run()
