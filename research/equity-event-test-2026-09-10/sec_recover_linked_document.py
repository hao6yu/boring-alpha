#!/usr/bin/env python3
"""Single explicitly authorized first request to a previously unrequested linked document."""
import fcntl,json
import sec_collect as s
URL='https://www.sec.gov/Archives/edgar/data/819689/000081968919000073/micr-20190814xex99_01.htm'
HERE=s.HERE
lock=(HERE/'sec-collector.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
f=s.Fetcher()
path=HERE/'sec-endpoint-recovery.json'
if path.exists():raise SystemExit('recovery_record_already_exists')
if any(r['url']==URL for r in f.attempts):raise SystemExit('document_already_attempted')
record={'policy_sha256':s.POLICY_SHA,'created_at':s.now(),'authorization':'Root explicitly authorized a single first request after cooldown to this already-index-linked previously unrequested original document. No retry of denied complete-submission endpoint, identity rotation, proxy, count reset, or deadline extension.','denied_url':'https://www.sec.gov/Archives/edgar/data/819689/000081968919000073/0000819689-19-000073.txt','url':URL,'prior_attempts':len(f.attempts),'prior_stop':f.stop_reason,'status':'AUTHORIZED_SINGLE_FIRST_REQUEST'}
s.atomic(path,record)
f.stop_reason=None
try:
 b,name=f.get(URL)
 record.update(status='RECOVERED_LINKED_HTML',file=name,sha256=s.sha(b),completed_at=s.now(),attempt_count=len(f.attempts))
except Exception as exc:
 record.update(status='RECOVERY_FAILED',error=type(exc).__name__,completed_at=s.now(),attempt_count=len(f.attempts))
 f.stop_reason=f.stop_reason or 'RECOVERY_FAILED'
finally:s.atomic(path,record);f.flush()
print(json.dumps({k:v for k,v in record.items() if k not in ('authorization',)}))
