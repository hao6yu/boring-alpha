"""Bounded continuation of the frozen recent-date probe; no strategy evaluation."""
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
import time
from acquire import HERE, ROOT, RAW, OLD, load, write, sha, scope, now, request_prices

sys.path.insert(0, str(OLD))
from reviewed_sources import ALIASES, LIFECYCLE


def plan():
    spec = scope()
    assert load(HERE / 'date-probe.json')['passed']
    path = HERE / 'bulk-acquisition-plan.json'
    if path.exists():
        return load(path)
    cohort = load(OLD / 'identity-candidates.json')['rows'][:100]
    active = [r for r in cohort if LIFECYCLE.get(r['Symbol'], {}).get('end', '9999') >= '2024-01-01']
    jobs = list(dict.fromkeys(ALIASES.get(r['Symbol'], {}).get('provider', r['Symbol']) for r in active))
    out = dict(at_utc=now().isoformat(), protocol_sha256=sha(HERE / 'protocol.json'),
               initial_symbols=jobs, initial_ciks=list(dict.fromkeys(r['cik'] for r in active)),
               excluded_from_new_requests=[dict(symbol=r['Symbol'],reason='Documented removal before new evaluation; retain historical cohort slot',lifecycle=LIFECYCLE[r['Symbol']]) for r in cohort if r not in active],
               request_basis='Original cohort order and already-qualified aliases; later evidenced successors/children may be added explicitly within the original cap.',
               start_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               initial_collector_sha256=sha(HERE / 'collect_bulk.py'))
    write(path, out)
    return out


def prices(wait=False):
    jobs=plan()['initial_symbols'] + load(HERE/'extra-price-requests.json',{}).get('symbols',[])
    spec=scope()
    while True:
        manifest=load(HERE/'price-manifest.json')
        pending=[s for s in dict.fromkeys(jobs) if s not in manifest['symbols']]
        if not pending:
            print(json.dumps(dict(status='ALL_PLANNED_PRICE_REQUESTS_ATTEMPTED',requests=len(manifest['requests']))),flush=True)
            return
        try:
            request_prices(pending[0],spec,manifest)
        except RuntimeError as e:
            if 'hourly quota reached' not in str(e):raise
            record=load(HERE/'price-manifest.json')
            remaining=max(0,(datetime.fromisoformat(record['resume_after_utc'])-now()).total_seconds())
            print(json.dumps(dict(status='WAITING_FOR_HOURLY_QUOTA',pending=len(pending),resume_after_utc=record['resume_after_utc'])),flush=True)
            if not wait:return
            # Bounded internal sleeps keep the process interruptible. No retry
            # requests are made while the known request allowance is exhausted.
            while remaining>0:
                time.sleep(min(30,remaining))
                remaining=max(0,(datetime.fromisoformat(record['resume_after_utc'])-now()).total_seconds())


def sec():
    p=plan();spec=scope();manifest=load(HERE/'sec-manifest.json',{})
    jobs=list(dict.fromkeys(p['initial_ciks']+load(HERE/'extra-sec-requests.json',{}).get('ciks',[])))
    for cik in jobs:
        if cik in manifest:continue
        assert len(manifest)<spec['acquisition']['max_sec_requests']
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
        response=subprocess.run(['curl','--silent','--show-error','--proto','=https','--max-time','55','--max-filesize','40000000',
                                  '--user-agent','BoringAlphaResearch/0.1 (personal financial research)','--write-out','\n%{http_code}',url],capture_output=True,timeout=60)
        body,_,code=response.stdout.rpartition(b'\n')
        record=dict(url=url,at=now().isoformat(),http_status=int(code) if code.isdigit() else None,curl_exit=response.returncode,response_bytes=len(body),response_sha256=__import__('hashlib').sha256(body).hexdigest(),cik=cik)
        if not response.returncode and record['http_status']==200:
            data=json.loads(body);assert int(data['cik'])==int(cik)
            filtered=dict(cik=data['cik'],entityName=data['entityName'],facts={});count=0
            for ns,concepts in data.get('facts',{}).items():
                filtered['facts'][ns]={}
                for tag,concept in concepts.items():
                    units={unit:[r for r in rows if r.get('filed','9999')<=spec['new_evaluation'][1] and r.get('end','9999')<=spec['new_evaluation'][1]] for unit,rows in concept.get('units',{}).items()}
                    units={unit:rows for unit,rows in units.items() if rows}
                    if units:filtered['facts'][ns][tag]=dict(units=units);count+=sum(map(len,units.values()))
            target=RAW/f'CIK{cik}-companyfacts-through-cutoff.json';write(target,filtered)
            record.update(file=str(target.relative_to(ROOT)),filtered_sha256=sha(target),retained_fact_rows=count,entity_name=data['entityName'])
        manifest[cik]=record;write(HERE/'sec-manifest.json',manifest)
        print(json.dumps({k:record.get(k) for k in ['cik','http_status','retained_fact_rows','entity_name']}),flush=True)
        if record['http_status'] in (401,403,429):raise RuntimeError('SEC access stop; no automatic retry')
        time.sleep(.4)
    scope()


if __name__=='__main__':
    if sys.argv[1]=='prices':prices('--wait' in sys.argv)
    elif sys.argv[1]=='sec':sec()
    elif sys.argv[1]=='plan':print(json.dumps(plan(),indent=2))
