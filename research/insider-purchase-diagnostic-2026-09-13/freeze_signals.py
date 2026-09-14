"""Freeze source-only decisions, including every excluded issuer-month."""
from collections import Counter
from datetime import datetime, timezone
import json

from diagnostic_io import HERE, ROOT, RAW, SOURCE_HERE, POLICY_SHA, atomic, digest, check_budget


def run():
    check_budget()
    assert not (HERE / 'signal-freeze.json').exists()
    ledger = json.loads((RAW / 'candidate-ledger.json').read_text())
    cohort = json.loads((SOURCE_HERE / 'cohort.json').read_text())
    # The source copy is the full original issuer envelope.
    issuers = cohort['issuers']
    rows = {(r['accession'], r['table_row']):r for r in ledger['rows']}
    existing = {(s['issuer_cik'],s['disclosure_month']):s for s in ledger['slots']}
    months = ['2021-12']+[f'{y}-{m:02}' for y in (2022,2023) for m in range(1,13) if (y,m)<=(2023,11)]
    slots = []
    for issuer in issuers:
        cik = issuer['cik']
        for month in months:
            purchases = [r for r in ledger['rows'] if (r['issuer_cik'],r['disclosure_month'])==(cik,month)]
            item = existing.get((cik,month), {'issuer_cik':cik,'disclosure_month':month,
                'classification':'NO_QUALIFIED_PURCHASE' if purchases else 'NO_P_DISCLOSURE',
                'transaction_keys':[]})
            slots.append({**item, 'historical_symbol':issuer['historical_symbol'],
                'any_p_disclosure':bool(purchases),
                'row_state_counts':dict(Counter(r['status'] for r in purchases))})
    assert len(slots)==4800 and len({(x['issuer_cik'],x['disclosure_month']) for x in slots})==4800
    signals = []
    for s in slots:
        if s['classification'] not in ('NONROUTINE','ROUTINE'):
            continue
        evidence = [rows[tuple(k)] for k in s['transaction_keys']]
        assert evidence and all(r['status']=='CANDIDATE' for r in evidence)
        assert all(r['owner_labels'] and set(r['owner_labels'])=={s['classification']} for r in evidence)
        assert not s['unresolved_transaction_keys']
        signals.append({**s, 'source_rows':evidence})
    output = {'policy_sha256':POLICY_SHA,'slots':slots,'signals':signals}
    sha = atomic(RAW / 'frozen-signals.json', output)
    report = {'policy_sha256':POLICY_SHA,'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'SOURCE_CLASSIFICATION_FROZEN_WITH_EXPLICIT_ABSTENTIONS',
        'security_price_outcomes_read':False,'all_issuer_months':len(slots),
        'classifications':dict(Counter(s['classification'] for s in slots)),
        'signals':{'path':str((RAW/'frozen-signals.json').relative_to(ROOT)), 'sha256':sha},
        'source_files':{name:digest(HERE/name) for name in ['experiment-policy.json','footnote-review.json','insider_rules.py','build_candidate_ledger.py']},
        'limitations':['Unresolved source histories, ambiguous joint owners and amendments cause abstention under the fixed rules.',
            'This is a diagnostic of the identifiable subset; unresolved events are not certified ineligible in economic reality.',
            'No missing or ambiguous record is recoded as a non-routine purchase.']}
    atomic(HERE/'signal-freeze.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['source_files','signals','limitations']}))


if __name__=='__main__':
    run()
