"""Finish the registered price request queue within this active research run."""
from datetime import datetime, timezone
import json
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent

def main():
    policy=json.loads((HERE/'experiment-policy.json').read_text())
    deadline=datetime.fromisoformat(policy['sec_collection_deadline_utc'])
    last_wait=None
    while datetime.now(timezone.utc)<deadline:
        m=json.loads((HERE/'price-manifest.json').read_text())
        used=len(m['requests'])-m['inherited_request_count']
        if used>=policy['expansion_price_max_requests'] or m.get('provider_stop'):
            print(json.dumps({'status':'BOUNDED_PRICE_PASS_STOPPED','requests':used,'reason':m.get('provider_stop','REQUEST_BUDGET')}),flush=True)
            return
        waits=[datetime.fromisoformat(m[k]) for k in ['quota_wait_until_utc','server_retry_after_utc'] if m.get(k)]
        wake=max(waits) if waits else datetime.now(timezone.utc)
        seconds=(wake-datetime.now(timezone.utc)).total_seconds()
        if seconds>0:
            if last_wait!=wake:
                print(json.dumps({'status':'FREE_QUOTA_WAIT','resume_utc':wake.isoformat(),'requests':used}),flush=True)
                last_wait=wake
            time.sleep(min(30,seconds));continue
        subprocess.run([sys.executable,str(HERE/'price_data.py'),'--limit','50','--retry-transient'],check=True)
        after=json.loads((HERE/'price-manifest.json').read_text())
        if not after.get('pending_symbols'):
            print(json.dumps({'status':'CURRENT_REGISTERED_PRICE_QUEUE_FINISHED','requests':len(after['requests'])-after['inherited_request_count']}),flush=True)
            return
        if len(after['requests'])==len(m['requests']) and not after.get('quota_wait_until_utc') and not after.get('server_retry_after_utc'):
            print(json.dumps({'status':'NO_FURTHER_REQUEST_WITHIN_REGISTERED_BOUNDS'}),flush=True)
            return
    print(json.dumps({'status':'REGISTERED_COLLECTION_DEADLINE_REACHED'}),flush=True)

if __name__=='__main__':main()
