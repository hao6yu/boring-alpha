#!/usr/bin/env python3
"""Bounded SEC collection for the frozen chronological experiment; no prices."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / 'equity-event-pilot-2026-09-10'
RAW = ROOT / 'data/snapshots/equity-event-expansion-2026-09-13/sec'
POLICY_SHA = '5c9daa1573ead42077ea323e641433c69112d6d3977f5e20c91d8bd1d04513bc'
PARSER_SHA = '75ab86dc530899d4ef29a7068f9384146f34f3e054e6ceafc60e4221d02a32b2'
SCRIPT_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
UTC = timezone.utc
MAX_BYTES = 32 * 1024 * 1024

def now(): return datetime.now(UTC).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def digest(p): return sha(p.read_bytes())
def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(obj, indent=2, sort_keys=True) + '\n').encode()
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(b)
    tmp.replace(path)
    return sha(b)

assert digest(OLD / 'sec_collect.py') == PARSER_SHA
spec = importlib.util.spec_from_file_location('frozen_availability_parser', OLD / 'sec_collect.py')
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)  # No old Collector is instantiated and no old main runs.

class StopCollection(RuntimeError): pass
class SourceFailure(RuntimeError): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def common_identity(page):
    identity = parser.cover_identity(page)
    evidence = []
    for cells in page.rows:
        text = ' | '.join(cells)
        common = re.search(r'common\s+(?:stock|shares)|ordinary\s+shares', text, re.I)
        derivative = re.search(r'\b(?:warrants?|units?|rights?|options?|preferred)\b', text, re.I)
        if not common or (derivative and derivative.start() < common.start()): continue
        if not re.search(r'Nasdaq|New York Stock|NYSE|NYSE American', text, re.I): continue
        symbols = []
        for cell in cells:
            value = re.sub(r'^Trading Symbol(?:\(s\)|s)?\s*', '', cell, flags=re.I).strip()
            # Some original SEC covers put a literal trading symbol in paired
            # quotation marks. Preserve the raw listing row as evidence.
            if len(value) > 2 and (value[0], value[-1]) in {('“','”'), ('"','"'), ("'","'")}:
                value = value[1:-1].strip()
            if re.fullmatch(r'[A-Z][A-Z0-9.\-/]{0,9}', value) and value not in {'NYSE', 'NASDAQ', 'AMEX'}:
                symbols.append(value)
        if symbols: evidence.append({'row_excerpt': text, 'symbols': symbols})
    symbols = list(dict.fromkeys(s for r in evidence for s in r['symbols']))
    unit_rows = [' | '.join(r) for r in page.rows if re.search(r'common\s+units', ' | '.join(r), re.I)
                 and re.search(r'NASDAQ|New York Stock|NYSE', ' | '.join(r), re.I)]
    status = 'VERIFIED_SINGLE_COMMON_CLASS' if len(symbols) == 1 else 'MULTIPLE_COMMON_CLASSES' if symbols else 'INELIGIBLE_COMMON_UNITS' if unit_rows else 'UNRESOLVED_COMMON_CLASS'
    return {**identity, 'status': status, 'symbols': symbols, 'historical_symbol': symbols[0] if len(symbols) == 1 else None,
            'common_stock_evidence': evidence, 'excluded_common_unit_rows': unit_rows}

class Fetcher:
    """Shared start limiter and durable attempt journal; one SEC owner/process."""
    def __init__(self, offline=False):
        pb = (HERE / 'experiment-policy.json').read_bytes()
        if sha(pb) != POLICY_SHA: raise StopCollection('policy_hash_mismatch')
        self.policy = json.loads(pb)
        self.deadline = datetime.fromisoformat(self.policy['sec_collection_deadline_utc'])
        self.offline = offline
        self.lock = threading.RLock()
        self.url_locks = {}
        self.last_start = 0.0
        self.thread_local = threading.local()
        self.log_path = HERE / 'sec-source-log.jsonl'
        self.snapshot_path = HERE / 'sec-sources.json'
        self.sources = {}
        self.cache_sources = {}
        self.attempts = []
        self.cache_uses = {}
        self.stop_reason = None
        self.denied_urls = set()
        self.completed_since_snapshot = 0
        self.context = ssl.create_default_context()
        if not self.context.cert_store_stats()['x509_ca']:
            self.context = ssl.create_default_context(cafile='/etc/ssl/cert.pem')
        for path in [OLD / 'sec-sources.json', HERE.parent / 'equity-event-repair-2026-09-10/dtss-sources.json', HERE.parent / 'equity-event-test-2026-09-10/sec-sources.json']:
            raw_manifest = path.read_bytes()
            m = json.loads(raw_manifest)
            manifest_sha = sha(raw_manifest)
            manifest_path = str(path.relative_to(ROOT))
            for u, r in m.get('sources', {}).items():
                if r.get('status') == 200:
                    self.cache_sources[u] = {**r, 'cache_manifest': manifest_path, 'cache_manifest_sha256': manifest_sha}
        if self.log_path.exists():
            for line in self.log_path.read_text().splitlines():
                r = json.loads(line)
                if r['policy_sha256'] != POLICY_SHA: raise StopCollection('journal_policy_mismatch')
                if r['type'] == 'attempt_started': self.attempts.append(r)
                elif r['type'] == 'attempt_finished':
                    if r['status'] == 200: self.sources[r['url']] = r
                    elif r['status'] in {401, 403, 429}:
                        self.stop_reason = 'HTTP_' + str(r['status']); self.denied_urls.add(r['url'])
                elif r['type'] == 'cache_used': self.cache_uses[r['url']] = r
        recovery_path = HERE / 'sec-endpoint-recovery.json'
        if recovery_path.exists():
            recovery = json.loads(recovery_path.read_text())
            if recovery['policy_sha256'] != POLICY_SHA: raise StopCollection('recovery_policy_mismatch')
            if recovery['status'] == 'RECOVERED_LINKED_HTML':
                rec = self.sources.get(recovery['url'])
                if not rec or digest(ROOT / rec['file']) != recovery['sha256']: raise StopCollection('recovery_source_integrity')
                later_denied = any(json.loads(line).get('status') in {401, 403, 429} and json.loads(line).get('failed_at', '') > recovery['completed_at'] for line in self.log_path.read_text().splitlines())
                if not later_denied: self.stop_reason = None
        restriction_path = HERE / 'sec-format-restriction.json'
        if restriction_path.exists():
            restriction = json.loads(restriction_path.read_text())
            if restriction['policy_sha256'] != POLICY_SHA: raise StopCollection('format_restriction_policy')
            if restriction['status'] == 'AUTHORIZED_HTML_INDEX_SUBMISSIONS_ONLY' and self.denied_urls.issubset(set(restriction['denied_urls'])):
                self.stop_reason = None
        if len({r['attempt_id'] for r in self.attempts}) != len(self.attempts):
            raise StopCollection('duplicate_attempt_id')
        self.flush()

    def journal(self, r):
        r = {**r, 'policy_sha256': POLICY_SHA}
        with self.log_path.open('a') as f:
            f.write(json.dumps(r, sort_keys=True) + '\n')
            f.flush()
            import os
            os.fsync(f.fileno())

    def flush(self):
        with self.lock:
            atomic(self.snapshot_path, {'policy_sha256': POLICY_SHA, 'script_sha256': SCRIPT_SHA,
                   'parser_sha256': PARSER_SHA, 'updated_at': now(), 'sources': self.sources,
                   'attempts': self.attempts, 'cache_uses': list(self.cache_uses.values()),
                   'attempt_count': len(self.attempts), 'stop_reason': self.stop_reason,
                   'journal': str(self.log_path.relative_to(ROOT)),
                   'limit_per_second': self.policy['sec_max_per_second'],
                   'request_limit': self.policy['sec_max_requests'],
                   'deadline_utc': self.policy['sec_collection_deadline_utc']})
            self.completed_since_snapshot = 0

    def get(self, url):
        u = urllib.parse.urlsplit(url)
        if u.scheme != 'https' or u.netloc not in {'www.sec.gov', 'data.sec.gov'} or u.username or u.fragment:
            raise StopCollection('non_public_SEC_URL')
        if not (u.path.startswith('/Archives/') or re.fullmatch(r'/submissions/CIK\d{10}(?:-submissions-\d+)?\.json', u.path)):
            raise StopCollection('unexpected_SEC_endpoint')
        with self.lock: gate = self.url_locks.setdefault(url, threading.Lock())
        with gate:
            with self.lock: rec = self.sources.get(url) or self.cache_sources.get(url)
            if rec:
                path = ROOT / rec['file']
                b = path.read_bytes()
                if path.is_symlink() or sha(b) != rec['sha256']: raise StopCollection('cached_source_integrity')
                if url not in self.sources and url not in self.cache_uses:
                    with self.lock:
                        use = {'type': 'cache_used', 'url': url, 'file': rec['file'], 'sha256': rec['sha256'],
                               'cache_manifest': rec['cache_manifest'], 'cache_manifest_sha256': rec['cache_manifest_sha256'], 'read_at': now()}
                        self.cache_uses[url] = use
                        self.journal(use)
                return b, rec['file']
            if url in self.denied_urls: raise SourceFailure('previously_denied_endpoint_not_retried')
            if u.path.lower().endswith('.txt'):
                # Complete-submission bundles remain disabled. An individually
                # indexed original document may be reviewed explicitly; this
                # does not retry either previously denied bundle URL.
                allow_path = HERE / 'individual-text-source-review.json'
                allowed = json.loads(allow_path.read_text()).get('documents', {}) if allow_path.exists() else {}
                proof = allowed.get(url)
                if re.search(r'/\d{10}-\d{2}-\d{6}\.txt$', u.path) or not proof:
                    raise SourceFailure('TXT_format_disabled_no_request')
                if digest(ROOT/proof['index_file']) != proof['index_sha256']:
                    raise StopCollection('individual_text_index_binding')
                links = parser.HTML((ROOT/proof['index_file']).read_text()).links
                if not any(urllib.parse.urljoin(url, href) == url for href, _ in links):
                    raise StopCollection('individual_text_not_in_original_index')
            if self.offline: raise SourceFailure('offline_source_not_cached')
            previous = sum(r['url'] == url for r in self.attempts)
            if previous >= 2: raise SourceFailure('URL_attempt_limit_reached')
            for attempt in range(previous + 1, 3):
                with self.lock:
                    if self.stop_reason: raise StopCollection(self.stop_reason)
                    if len(self.attempts) >= self.policy['sec_max_requests']:
                        self.stop_reason = 'REQUEST_LIMIT'; raise StopCollection(self.stop_reason)
                    delay = max(0, .26 - (time.monotonic() - self.last_start))
                    if (self.deadline - datetime.now(UTC)).total_seconds() < delay + 22:
                        self.stop_reason = 'DEADLINE'; raise StopCollection(self.stop_reason)
                    if delay: time.sleep(delay)
                    self.last_start = time.monotonic()
                    started = {'type': 'attempt_started', 'attempt_id': len(self.attempts) + 1,
                               'url': url, 'attempt_for_url': attempt, 'started_at': now()}
                    self.journal(started)
                    self.attempts.append(started)
                result = {**started, 'type': 'attempt_finished'}
                try:
                    if not hasattr(self.thread_local, 'opener'):
                        self.thread_local.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))
                    req = urllib.request.Request(url, headers={'User-Agent': 'BoringAlphaResearch/0.1 (personal financial research)', 'Accept-Encoding': 'identity'})
                    with self.thread_local.opener.open(req, timeout=20) as response:
                        if response.status != 200: raise SourceFailure('non200')
                        length = response.headers.get('Content-Length')
                        if length is not None and not (0 <= int(length) <= MAX_BYTES): raise SourceFailure('payload_bound')
                        chunks = []; size = 0
                        while True:
                            if (self.deadline - datetime.now(UTC)).total_seconds() < 21: raise StopCollection('DEADLINE_DURING_READ')
                            b = response.read(min(65536, MAX_BYTES + 1 - size))
                            if not b: break
                            chunks.append(b); size += len(b)
                            if size > MAX_BYTES: raise SourceFailure('payload_bound')
                        b = b''.join(chunks)
                        if length is not None and int(length) != len(b): raise SourceFailure('incomplete_response')
                    output = RAW / (sha(url.encode()) + (Path(u.path).suffix or '.bin'))
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if output.exists(): raise StopCollection('orphan_output')
                    output.write_bytes(b)
                    result.update(status=200, file=str(output.relative_to(ROOT)), bytes=len(b), sha256=sha(b), received_at=now())
                    with self.lock:
                        self.journal(result); self.sources[url] = result
                        self.completed_since_snapshot += 1
                        if self.completed_since_snapshot >= 20: self.flush()
                    return b, result['file']
                except Exception as exc:
                    code = getattr(exc, 'code', None)
                    transient = code in {500, 502, 503, 504} or (code is None and isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)))
                    result.update(status=code, error=type(exc).__name__, transient=transient, failed_at=now())
                    with self.lock:
                        self.journal(result)
                        if code in {401, 403, 429}: self.stop_reason = 'HTTP_' + str(code)
                        if isinstance(exc, StopCollection): self.stop_reason = str(exc)
                        self.flush()
                    if self.stop_reason: raise StopCollection(self.stop_reason) from None
                    if not transient or attempt == 2: raise SourceFailure('SEC_source_unavailable:' + str(code or type(exc).__name__)) from None
                    time.sleep(1)
            raise SourceFailure('attempts_exhausted')

class Client(parser.Collector):
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.events_cache = {}
        self.policy = fetcher.policy
    def get(self, url):
        extracted_path = HERE / 'sec-extracted' / (sha(url.encode()) + '.json')
        if extracted_path.exists():
            r = json.loads(extracted_path.read_text())
            if r['requested_url'] != url or r['policy_sha256'] != POLICY_SHA: raise StopCollection('extracted_source_binding')
            for field, hashfield in [('file', 'sha256'), ('container_file', 'container_sha256')]:
                if digest(ROOT / r[field]) != r[hashfield]: raise StopCollection('extracted_source_integrity')
            return (ROOT / r['file']).read_bytes(), r['file']
        return self.fetcher.get(url)
    def submissions(self, cik, start, end, forms=('8-K', '8-K/A', '6-K')):
        b, f = self.get(f'https://data.sec.gov/submissions/CIK{cik}.json')
        d = json.loads(b)
        tables = [(d['filings']['recent'], f)]
        for item in d['filings'].get('files', []):
            if item['filingFrom'] <= end and item['filingTo'] >= start:
                b, f = self.get('https://data.sec.gov/submissions/' + item['name'])
                tables.append((json.loads(b), f))
        rows = {}
        for table, f in tables:
            for i, day in enumerate(table['filingDate']):
                if start <= day <= end and table['form'][i] in forms:
                    row = {k: v[i] for k, v in table.items() if isinstance(v, list) and len(v) == len(table['filingDate'])}
                    row['metadata_file'] = f; rows[row['accessionNumber']] = row
        return sorted(rows.values(), key=lambda r: (r['filingDate'], r.get('acceptanceDateTime', ''), r['accessionNumber']))
    def event(self, cik, row):
        special_path = HERE / 'sec-special-events.json'
        if special_path.exists():
            special = json.loads(special_path.read_text())
            if special['policy_sha256'] != POLICY_SHA: raise StopCollection('special_event_policy')
            rec = special['events'].get(row['accessionNumber'])
            if rec:
                for f, h in rec['raw_hashes'].items():
                    if digest(ROOT / f) != h: raise StopCollection('special_event_source_integrity')
                return rec['event']
        path = HERE / 'sec-parsed' / (row['accessionNumber'] + '.json')
        if path.exists():
            saved = json.loads(path.read_text())
            if saved['policy_sha256'] != POLICY_SHA or saved['parser_sha256'] != PARSER_SHA: raise StopCollection('parsed_binding')
            for name, value in saved['raw_hashes'].items():
                if digest(ROOT / name) != value: raise StopCollection('parsed_raw_hash')
            event = saved['event']
            event['security'] = common_identity(parser.HTML((ROOT / event['primary_file']).read_text()))
            return event
        event = super().event(cik, row)
        # Reject fund-like beneficial interests as cohort common-stock evidence.
        event['security'] = common_identity(parser.HTML((ROOT / event['primary_file']).read_text()))
        files = {v for k, v in event.items() if k.endswith('_file') and isinstance(v, str)}
        for r in event.get('exhibit_candidates', []) + event.get('accounting_companions', []):
            if r.get('file'): files.add(r['file'])
        atomic(path, {'policy_sha256': POLICY_SHA, 'parser_sha256': PARSER_SHA, 'wrapper_script_sha256': SCRIPT_SHA,
                      'raw_hashes': {f: digest(ROOT / f) for f in sorted(files)}, 'event': event})
        return event

def manual_decisions():
    path = HERE / 'sec-manual-decisions.json'
    return json.loads(path.read_text()) if path.exists() else {'screens': {}, 'events': {}}

def screen(client, ranked):
    r = {**ranked, 'candidates': []}
    rows = client.submissions(r['cik'], '2019-07-01', '2019-09-30')
    master_acc = {Path(x['path']).stem for x in r['seed_index_filings']}
    metadata_acc = {x['accessionNumber'] for x in rows if x['form'] == '8-K'}
    r['missing_master_accessions'] = sorted(master_acc - metadata_acc)
    if r['missing_master_accessions']: return {**r, 'decision': 'UNRESOLVED', 'reason': 'MASTER_METADATA_MISMATCH'}
    reviewed = manual_decisions()['screens'].get(r['cik'])
    if reviewed and reviewed['decision'] == 'EXCLUDED':
        return {**r, 'decision': 'EXCLUDED', 'reason': reviewed['reason'], 'manual_review': reviewed}
    candidates = [x for x in rows if x['form'] == '8-K' and '2.02' in x.get('items', '')]
    r['candidate_accessions'] = [x['accessionNumber'] for x in candidates]
    unknown = False
    for row in candidates:
        e = event_override(client.event(r['cik'], row))
        r['candidates'].append(e)
        accepted = datetime.fromisoformat(e['acceptance_eastern']) if e.get('acceptance_eastern') else None
        if not accepted: unknown = True; continue
        if accepted.date().isoformat() >= '2019-09-30':
            e['selection_rejection'] = 'ACCEPTED_ON_OR_AFTER_LITERAL_CUTOFF'; continue
        if e['classification'] == 'EARNINGS_RELEASE':
            if e['security']['status'] == 'UNRESOLVED_COMMON_CLASS' and re.search(r'\bOTCQ[XB]?\s*:', e.get('release_excerpt', ''), re.I):
                primary_text = parser.HTML((ROOT / e['primary_file']).read_text()).text
                no_registration = re.search(r'Securities registered pursuant to Section 12\(b\).{0,220}?\bNone\b', primary_text[:5000], re.I)
                if no_registration:
                    e['security']['status'] = 'INELIGIBLE_EXPLICIT_OTC_NO_EXCHANGE_REGISTRATION'
                    e['security']['OTC_evidence'] = {'primary_excerpt': no_registration[0],
                        'release_excerpt': re.search(r'.{0,70}\bOTCQ[XB]?\s*:.{0,100}', e['release_excerpt'], re.I)[0]}
            if e['security']['status'] == 'UNRESOLVED_COMMON_CLASS':
                # A Q3 earnings8-K may omit the listing table. A later cover
                # already available before the frozen cohort cutoff may prove
                # membership, but is not relabeled as evidence at the earnings time.
                covers = client.submissions(r['cik'], '2019-01-01', '2019-09-29', ('10-Q', '10-K'))
                for cover in reversed(covers):
                    url = f'https://www.sec.gov/Archives/edgar/data/{int(r["cik"])}/{cover["accessionNumber"].replace("-", "")}/{cover["primaryDocument"]}'
                    b, f = client.get(url)
                    security = common_identity(parser.HTML(b.decode('utf-8', 'replace')))
                    if security['status'] != 'UNRESOLVED_COMMON_CLASS':
                        e = json.loads(json.dumps(e))
                        e['original_earnings_cover_security'] = e['security']
                        e['security'] = security
                        e['cohort_identity_source'] = {'accession': cover['accessionNumber'], 'filing_date': cover['filingDate'],
                            'url': url, 'file': f, 'sha256': sha(b), 'scope': 'Already-public cover before cohort cutoff; not earnings-time evidence.'}
                        r['candidates'][-1] = e
                        break
            if e['security']['status'] == 'VERIFIED_SINGLE_COMMON_CLASS':
                r.update(decision='SELECTED', reason='FULL_ORIGINAL_RELEASE_AND_SINGLE_LISTED_COMMON_BEFORE_CUTOFF', selected_event=e)
                return r
            if e['security']['status'] == 'UNRESOLVED_COMMON_CLASS': unknown = True
        elif e['classification'] == 'UNRESOLVED': unknown = True
    r.update(decision='UNRESOLVED' if unknown else 'EXCLUDED', reason='UNRESOLVED_EARNINGS_OR_SECURITY' if unknown else 'NO_ELIGIBLE_FULL_RELEASE_SINGLE_COMMON_BEFORE_CUTOFF')
    override = manual_decisions()['screens'].get(r['cik'])
    if override:
        r['manual_review'] = override
        r.update({k: override[k] for k in ('decision', 'reason')})
        if override['decision'] == 'SELECTED': r['selected_event'] = next(e for e in r['candidates'] if e['accession'] == override['accession'])
    return r

def selection(fetcher, workers):
    client = Client(fetcher)
    b, master = client.get(fetcher.policy['cohort_master_index'])
    ranked = {}
    for line in b.decode('latin-1').splitlines():
        x = line.split('|')
        if len(x) == 5 and x[2] == '8-K' and x[0].isdigit():
            cik = x[0].zfill(10)
            ranked.setdefault(cik, {'cik': cik, 'issuer_name': x[1], 'seed_index_filings': []})['seed_index_filings'].append({'filing_date': x[3], 'path': x[4]})
    ranked = sorted(ranked.values(), key=lambda x: sha((fetcher.policy['cohort_seed'] + '|' + x['cik']).encode()))
    for i, r in enumerate(ranked, 1): r.update(seed_rank=i, rank_digest=sha((fetcher.policy['cohort_seed'] + '|' + r['cik']).encode()))
    rankpath = HERE / 'sec-ranked-seed.json'
    ranksha = atomic(rankpath, {'policy_sha256': POLICY_SHA, 'master_file': master, 'master_sha256': sha(b), 'rows': ranked})
    path = HERE / 'sec-selection.json'
    out = json.loads(path.read_text()) if path.exists() else {'policy_sha256': POLICY_SHA, 'ranked_seed_sha256': ranksha, 'issuers': [], 'screened': []}
    if out['policy_sha256'] != POLICY_SHA or out['ranked_seed_sha256'] != ranksha: raise StopCollection('selection_binding')
    # Revisit the final unresolved rank; already selected prefix is unchanged.
    if out['screened'] and out['screened'][-1]['decision'] == 'UNRESOLVED': out['screened'].pop()
    out.update(selection_status='IN_PROGRESS', cutoff='acceptance_eastern < 2019-09-30T00:00:00-04:00',
               cohort_id='fixed-2019Q3-incumbents-expanded200', no_future_price_selection=True)
    start = len(out['screened'])
    def job(r):
        try: return screen(Client(fetcher), r)
        except StopCollection: raise
        except Exception as e: return {**r, 'decision': 'UNRESOLVED', 'reason': type(e).__name__, 'candidates': []}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        for i in range(start, min(start + workers, len(ranked))): pending[i] = pool.submit(job, ranked[i])
        i = start
        while i < len(ranked) and len(out['issuers']) < 200:
            r = pending.pop(i).result()
            out['screened'].append(r)
            if r['decision'] == 'SELECTED':
                e = r['selected_event']
                out['issuers'].append({k: r[k] for k in ('cik', 'issuer_name', 'seed_rank', 'rank_digest')})
                out['issuers'][-1].update(historical_symbol=e['security']['historical_symbol'], seed_accession=e['accession'],
                    seed_filing_date=e['filing_date'], seed_acceptance_eastern=e['acceptance_eastern'],
                    common_stock_evidence=e['security']['common_stock_evidence'], security_status=e['security']['status'],
                    primary_file=e['primary_file'], index_file=e['index_file'], membership_final_in_resolved_prefix=True,
                    source=e.get('cohort_identity_source') or {'accession': e['accession'], 'file': e['primary_file'], 'url': e['primary_url'], 'sha256': digest(ROOT / e['primary_file'])})
            out['updated_at'] = now()
            out['selection_status'] = 'BLOCKED_EARLIER_RANK' if r['decision'] == 'UNRESOLVED' else 'COMPLETE_200' if len(out['issuers']) == 200 else 'IN_PROGRESS'
            atomic(path, out)
            atomic(HERE / 'sec-cohort.json', out)
            fetcher.flush()
            print(json.dumps({'phase': 'selection', 'rank': r['seed_rank'], 'cik': r['cik'], 'decision': r['decision'], 'selected': len(out['issuers']), 'requests': len(fetcher.attempts)}), flush=True)
            if r['decision'] == 'UNRESOLVED' or len(out['issuers']) == 200: break
            nxt = i + workers
            if nxt < len(ranked): pending[nxt] = pool.submit(job, ranked[nxt])
            i += 1
    fetcher.flush()
    return out

def event_override(event):
    override = manual_decisions()['events'].get(event['accession'])
    if override:
        event = json.loads(json.dumps(event))
        event['manual_review'] = override
        event.update(override.get('verified_fields', {}))
    return event

def collect_issuer(fetcher, issuer):
    # Apply the already reviewed explicit 13/14-week annotation before matching
    # current releases to original prior fiscal periods.
    from sec_period_annotations import annotate
    client = Client(fetcher)
    cik = issuer['cik']
    rows = client.submissions(cik, '2019-01-01', '2023-12-31')
    events = {}
    failures = []
    # Full Item2.02 frame includes prior-year originals and predecessors.
    for row in rows:
        if row['form'] == '8-K' and '2.02' in row.get('items', ''):
            try:
                event = event_override(client.event(cik, row))
                if event.get('cohort_only_source_recovery'):
                    raise SourceFailure('cohort_only_publication_is_not_SEC_model_input')
                events[row['accessionNumber']] = annotate(event)
            except StopCollection: raise
            except Exception as exc: failures.append({'accession': row['accessionNumber'], 'filing_date': row['filingDate'], 'error': type(exc).__name__})
    slots = []
    for year in range(2020, 2024):
        for quarter in range(1, 5):
            start = date(year, quarter * 3 - 2, 1)
            end = date(year + 1, 1, 1) - timedelta(days=1) if quarter == 4 else date(year, quarter * 3 + 1, 1) - timedelta(days=1)
            candidates = [e for e in events.values() if start.isoformat() <= e['filing_date'] <= end.isoformat()]
            qualifying = [e for e in candidates if e['classification'] == 'EARNINGS_RELEASE' and e.get('release_date')]
            qualifying.sort(key=lambda e: (e['acceptance_eastern'] or '', e['accession']))
            current = qualifying[0] if qualifying else None
            reasons = []
            candidate_failures = [f for f in failures if start.isoformat() <= f['filing_date'] <= end.isoformat()]
            if candidate_failures: reasons.append('CANDIDATE_SOURCE_FAILURE')
            relevant_unknown = [e for e in candidates if e['classification'] == 'UNRESOLVED' and (not current or e['filing_date'] <= current['filing_date'])]
            if relevant_unknown: reasons.append('EARLIER_UNCLASSIFIED_CANDIDATE')
            if not current: reasons.append('NO_VERIFIED_CURRENT_FULL_RELEASE')
            prior = None; prior_match = None; prior_candidates = []
            predecessors = []
            if current:
                for candidate in sorted(events.values(), key=lambda e: (e['filing_date'], e['accession'])):
                    match = parser.period_match(current, candidate)
                    if match['verified']:
                        prior_candidates.append({'event': candidate, 'match': match})
                if prior_candidates:
                    prior = prior_candidates[0]['event']; prior_match = prior_candidates[0]['match']
                if not prior: reasons.append('ORIGINAL_PRIOR_NOT_YET_VERIFIED')
                cutoff = date.fromisoformat(current['release_date']) - timedelta(days=90)
                for e in events.values():
                    if cutoff.isoformat() <= e['filing_date'] < current['filing_date']:
                        if e['classification'] in {'PRELIMINARY', 'GUIDANCE_UPDATE', 'ACCOUNTING_TRANSITION_PRESENTATION'}:
                            predecessors.append(e)
                if not current['daily_entry_invariant']: reasons.append('TIMING_PROXY_UNRESOLVED')
                if current['security']['status'] != 'VERIFIED_SINGLE_COMMON_CLASS': reasons.append('HISTORICAL_SECURITY_UNRESOLVED')
            checks = {'current_release': current is not None, 'earliest_event': bool(current and not relevant_unknown and not candidate_failures),
                      'prior_release': prior is not None, 'period_identity': bool(current and current.get('period_end') and prior_match),
                      'identity': bool(current and current['security']['status'] == 'VERIFIED_SINGLE_COMMON_CLASS'),
                      'timing': bool(current and current['daily_entry_invariant'])}
            slot = {'slot_id': f'{cik}-{year}Q{quarter}', 'cik': cik, 'seed_symbol': issuer['historical_symbol'],
                    'historical_symbol': current['security']['historical_symbol'] if current else issuer['historical_symbol'],
                    'window_start': start.isoformat(), 'window_end': end.isoformat(), 'window_basis': 'ORIGINAL_FILING_DATE',
                    'current': current, 'prior': prior, 'prior_match': prior_match, 'candidate_events': candidates,
                    'candidate_failures': candidate_failures, 'prior_candidates': prior_candidates,
                    'checks': checks, 'unresolved_reasons': sorted(set(reasons)), 'information_predecessors': predecessors,
                    'predecessor_coverage': {'status': 'ITEM_202_FRAME_ONLY_PENDING_NON202_REVIEW',
                       'days_before_current_release': 90, 'absence_verified': False, 'other_referenced_originals_reviewed': False},
                    'known_preliminary_information': 'KNOWN_YES' if any(e['classification'] == 'PRELIMINARY' for e in predecessors) else 'UNKNOWN',
                    'status': 'BASE_SEC_JOIN_READY_PENDING_PREDECESSOR_AUDIT' if all(checks.values()) else 'SEC_JOIN_UNRESOLVED',
                    'accounting_feature_values_verified': False}
            slots.append(slot)
    output = {'policy_sha256': POLICY_SHA, 'issuer': issuer, 'metadata_rows': rows, 'slots': slots,
              'updated_at': now(), 'status': 'INITIAL_ITEM_202_PASS_COMPLETE', 'source_failures': failures}
    atomic(HERE / 'sec-issuers' / (cik + '.json'), output)
    return output

def collect_events(fetcher, selected, workers):
    if selected['selection_status'] != 'COMPLETE_200': raise StopCollection('cohort_not_frozen')
    out = {'policy_sha256': POLICY_SHA, 'selection_sha256': digest(HERE / 'sec-selection.json'),
           'slot_definition': '2020–2023 original filing-date calendar quarters; root clarification, no2024bodies',
           'fixed_slots': 3200, 'slots': [], 'status': 'IN_PROGRESS', 'issuers_completed': 0}
    by_cik = {}
    for issuer in selected['issuers']:
        path = HERE / 'sec-issuers' / (issuer['cik'] + '.json')
        if path.exists():
            r = json.loads(path.read_text())
            if r['policy_sha256'] != POLICY_SHA: raise StopCollection('issuer_policy_mismatch')
            if r.get('status') == 'INITIAL_ITEM_202_PASS_COMPLETE': by_cik[issuer['cik']] = r
    def publish():
        slots = []
        for issuer in selected['issuers']:
            cik = issuer['cik']
            if cik in by_cik: slots.extend(by_cik[cik]['slots'])
            else:
                for y in range(2020, 2024):
                    for q in range(1, 5): slots.append({'slot_id': f'{cik}-{y}Q{q}', 'cik': cik, 'seed_symbol': issuer['historical_symbol'], 'status': 'PENDING_COLLECTION', 'current': None, 'prior': None, 'checks': {}})
        out.update(slots=slots, issuers_completed=len(by_cik), updated_at=now(), requests=len(fetcher.attempts))
        atomic(HERE / 'sec-events.json', out); fetcher.flush()
    publish()
    todo = [i for i in selected['issuers'] if i['cik'] not in by_cik]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(collect_issuer, fetcher, i): i for i in todo[:workers]}
        next_index = len(jobs)
        from concurrent.futures import wait, FIRST_COMPLETED
        terminal = None
        while jobs:
            done, _ = wait(jobs, return_when=FIRST_COMPLETED)
            for job in done:
                issuer = jobs.pop(job)
                try:
                    r = job.result(); by_cik[issuer['cik']] = r
                    print(json.dumps({'phase': 'events', 'cik': issuer['cik'], 'completed_issuers': len(by_cik), 'slots': len(by_cik) * 16, 'base_joins': sum(all(s['checks'].values()) for s in r['slots']), 'requests': len(fetcher.attempts)}), flush=True)
                except Exception as exc:
                    terminal = type(exc).__name__ + ':' + str(exc)
                    out.setdefault('issuer_failures', []).append({'cik': issuer['cik'], 'error': terminal})
                publish()
                if terminal is None and next_index < len(todo):
                    i = todo[next_index]; next_index += 1
                    jobs[pool.submit(collect_issuer, fetcher, i)] = i
        out['status'] = 'STOPPED:' + terminal if terminal else 'INITIAL_ITEM_202_PASS_COMPLETE_PENDING_SOURCE_AUDIT'
    publish()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=['selection', 'events', 'all'], default='selection')
    ap.add_argument('--workers', type=int, choices=range(1, 5), default=4)
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args()
    # A process lock prevents two invocations from sharing one request allowance.
    import fcntl
    lock_file = (HERE / 'sec-collector.lock').open('a')
    try: fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('SEC collector already running')
    f = Fetcher(offline=args.offline)
    try:
        if args.phase in ('selection', 'all'): selected = selection(f, args.workers)
        else: selected = json.loads((HERE / 'sec-selection.json').read_text())
        if args.phase in ('events', 'all'): collect_events(f, selected, args.workers)
    finally: f.flush()

if __name__ == '__main__': main()
