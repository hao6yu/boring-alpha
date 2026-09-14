"""Temporary loopback-only sink for original public filing DOM exports.

Browser controls navigate and read SEC pages; this endpoint only receives those
public document copies through its local form. It fetches nothing itself.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from datetime import datetime, timezone
from html import escape
import json
from prepare import HERE,RAW,load,write,sha

PLAN={j['id']:j for j in load(HERE/'filing-plan.json')}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,body):
        encoded=body.encode()
        self.send_response(status)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)))
        self.end_headers();self.wfile.write(encoded)
    def do_GET(self):
        if self.path=='/plan':return self.reply(200,'<!doctype html><title>Frozen filing plan</title><pre>'+escape(json.dumps(list(PLAN.values())))+'</pre>')
        if self.path!='/':return self.reply(404,'Unknown page')
        self.reply(200,'<!doctype html><title>Public filing capture</title><h1>Public filing capture</h1><form method="post" action="/save"><label for="payload">Document payload</label><textarea id="payload" name="payload"></textarea><button>Save filing</button></form>')
    def do_POST(self):
        if self.path!='/save':return self.reply(404,'Unknown action')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<40_000_000:raise ValueError('invalid document size')
            data=json.loads(parse_qs(self.rfile.read(size).decode(),strict_parsing=True)['payload'][0])
            job=PLAN[data['id']]
            if data['url']!=job['url']:raise ValueError('URL mismatch')
            html=data['html']
            if '<html' not in html.lower() or len(html)<10000 or not html.rstrip().lower().endswith('</html>') or len(html)!=data['document_characters']:raise ValueError('incomplete original document DOM')
            manifest=load(HERE/'retrieval-manifest.json')
            if any(r['id']==job['id'] and r.get('status')=='COMPLETE' for r in manifest['requests']):raise ValueError('duplicate document')
            if not 1<=data['navigation_attempt']<=90:raise ValueError('retrieval budget exhausted')
            path=RAW/f'{job["id"]:03d}-{job["accn"]}.html'
            if path.exists():
                partial=path.with_suffix('.partial.html')
                path.rename(partial)
                for old in manifest['requests']:
                    if old['id']==job['id']:old.update(file=str(partial.relative_to(HERE.parents[1])),status='TRUNCATED_CAPTURE_REJECTED')
            path.write_text(html)
            manifest['requests'].append(dict(id=job['id'],accn=job['accn'],url=job['url'],
                captured_at=datetime.now(timezone.utc).isoformat(),file=str(path.relative_to(HERE.parents[1])),
                sha256=sha(path),bytes=len(html.encode()),document_characters=len(html),navigation_attempt=data['navigation_attempt'],status='COMPLETE',method='original_document_DOM_via_normal_browser_in_bounded_chunks'))
            write(HERE/'retrieval-manifest.json',manifest)
            self.reply(200,f'<!doctype html><title>Saved</title><h1>Saved filing {job["id"]}</h1><p>{len(manifest["requests"])} of 90 documents captured.</p>')
        except Exception as e:
            self.reply(400,'Capture rejected: '+type(e).__name__)

if __name__=='__main__':
    server=HTTPServer(('127.0.0.1',0),Handler)
    print(f'Public-document capture sink: http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()
