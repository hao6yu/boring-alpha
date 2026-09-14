"""Finite in-turn continuation of the authorized bounded collection."""
from datetime import datetime,timedelta,timezone
import json,time
from collect import HERE,PREP,load,tiingo

def run():
    deadline=datetime.fromisoformat(load(HERE/'experiment-start.json',{})['panel_checkpoint_utc'])
    announced=None
    while datetime.now(timezone.utc)<deadline:
        m=load(HERE/'price-manifest.json',{});jobs={r['Symbol'] for r in load(PREP/'next-cohort.json',{})['rows']}
        jobs.update(load(HERE/'extra-price-requests.json',{}).get('symbols',[]))
        missing=jobs-set(m.get('symbols',{}))
        if not missing:print('Fixed request list completed.',flush=True);return
        if m.get('provider_stop') or len(m.get('requests',[]))>=150:
            print('Provider or request-cap stop; preserve current results.',flush=True);return
        now=datetime.now(timezone.utc)
        recent=[datetime.fromisoformat(r['at']) for r in m.get('requests',[]) if now-datetime.fromisoformat(r['at'])<timedelta(hours=1,seconds=5)]
        if len(recent)>=50:
            resume=min(recent)+timedelta(hours=1,seconds=6)
            if announced!=resume:
                print(json.dumps(dict(waiting_for_hourly_quota_until_utc=resume.isoformat(),unrequested_symbols=len(missing))),flush=True);announced=resume
            time.sleep(min(55,max(1,(resume-now).total_seconds())))
            continue
        tiingo(50)
    print('Panel checkpoint reached; no additional requests.',flush=True)

if __name__=='__main__':run()
