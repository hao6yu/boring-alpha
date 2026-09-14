"""Inspect fixed original filings offline; no price data or return calculations."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from lxml import etree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = ROOT / 'data/snapshots/insider-purchase-audit-2026-09-13'


def number(s):
    if s is None or s.strip() == '':
        return None
    s = re.sub(r'\(\d+\)', '', s).replace('$', '').replace(',', '').strip()
    return format(Decimal(s).normalize(), 'f')


def run():
    manifest = json.loads((HERE / 'sources.json').read_text())
    for source in manifest:
        if source['status'] == 200:
            assert hashlib.sha256((ROOT / source['file']).read_bytes()).hexdigest() == source['sha256']
    selected = json.loads((HERE / 'filing-selection.json').read_text())['selected']
    control = json.loads((HERE / 'positive-control-amendment.json').read_text())
    selected = selected + [{'accession': control['accession'], 'form': '4',
                            'acceptance_utc': None, 'positive_control': True}]
    findings = []
    for item in selected:
        acc = item['accession']
        doc = etree.fromstring((RAW / (acc + '.xml')).read_bytes(),
                               parser=etree.XMLParser(resolve_entities=False, no_network=True))
        rendered = BeautifulSoup((RAW / (acc + '-rendered.html')).read_bytes(), 'html.parser')
        index = BeautifulSoup((RAW / (acc + '-index.html')).read_bytes(), 'html.parser')
        accepted_et = re.search(r'Accepted\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)',
                                index.get_text(' ', strip=True)).group(1)
        accepted = datetime.strptime(accepted_et, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('America/New_York'))
        cached = datetime.fromisoformat(item['acceptance_utc'].replace('Z', '+00:00')) if item['acceptance_utc'] else None
        owners = [{'cik': x.findtext('reportingOwnerId/rptOwnerCik'),
                   'name': x.findtext('reportingOwnerId/rptOwnerName'),
                   'relationship': {c.tag: c.text for c in x.find('reportingOwnerRelationship')}}
                  for x in doc.findall('reportingOwner')]
        notes = {x.get('id'): ''.join(x.itertext()) for x in doc.findall('footnotes/footnote')}
        transactions = []
        for x in doc.findall('nonDerivativeTable/nonDerivativeTransaction'):
            transactions.append({
                'title': x.findtext('securityTitle/value'),
                'transaction_date': x.findtext('transactionDate/value'),
                'code': x.findtext('transactionCoding/transactionCode'),
                'shares': number(x.findtext('transactionAmounts/transactionShares/value')),
                'acquired_disposed': x.findtext('transactionAmounts/transactionAcquiredDisposedCode/value'),
                'price': number(x.findtext('transactionAmounts/transactionPricePerShare/value')),
                'owned_after': number(x.findtext('postTransactionAmounts/sharesOwnedFollowingTransaction/value')),
                'ownership': x.findtext('ownershipNature/directOrIndirectOwnership/value'),
                'footnote_ids': [f.get('id') for f in x.findall('.//footnoteId')]})
        html_rows = []
        for tr in rendered.find_all('tr'):
            cells = tr.find_all(['td', 'th'], recursive=False)
            if len(cells) != 11:
                continue
            vals = []
            for cell in cells:
                cell = deepcopy(cell)
                for a in cell.find_all('a'):
                    a.decompose()
                vals.append(re.sub(r'\(\d+\)', '', cell.get_text(' ', strip=True)).strip())
            if not re.fullmatch(r'\d\d/\d\d/\d{4}', vals[1]):
                continue
            html_rows.append({'transaction_date': datetime.strptime(vals[1], '%m/%d/%Y').date().isoformat(),
                              'code': vals[3], 'shares': number(vals[5]),
                              'acquired_disposed': vals[6], 'price': number(vals[7]),
                              'owned_after': number(vals[8]), 'ownership': vals[9]})
        keys = ['transaction_date', 'code', 'shares', 'acquired_disposed', 'price', 'owned_after', 'ownership']
        matched = html_rows == [{k: x[k] for k in keys} for x in transactions]
        candidates = [x for x in transactions if x['code'] == 'P' and x['acquired_disposed'] == 'A'
                      and x['shares'] is not None and Decimal(x['shares']) > 0
                      and x['price'] is not None and Decimal(x['price']) > 0]
        findings.append({'accession': acc, 'is_selected_positive_control': item.get('positive_control', False),
                         'document_type': doc.findtext('documentType'),
                         'issuer_cik': doc.findtext('issuer/issuerCik'),
                         'issuer_name': doc.findtext('issuer/issuerName'),
                         'issuer_symbol': doc.findtext('issuer/issuerTradingSymbol'),
                         'accepted_eastern': accepted.isoformat(),
                         'accepted_utc': accepted.astimezone(timezone.utc).isoformat(),
                         'cached_acceptance_utc_as_supplied': item['acceptance_utc'],
                         'cached_acceptance_matches_index': cached == accepted if cached else None,
                         'timestamp_status': ('CONFLICT_QUARANTINE' if cached and cached != accepted
                                              else 'INDEX_AND_METADATA_AGREE' if cached
                                              else 'INDEX_ONLY'),
                         'accepted_at_or_after_16_eastern': accepted.hour >= 16,
                         'original_submission_date': doc.findtext('dateOfOriginalSubmission'),
                         'owners': owners, 'non_derivative_transactions': transactions,
                         'derivative_transaction_count': len(doc.findall('derivativeTable/derivativeTransaction')),
                         'html_xml_transaction_fields_match': matched,
                         'code_p_positive_price_acquisition_count': len(candidates),
                         'reported_purchase_notional_counted_once': format(sum((Decimal(x['shares']) * Decimal(x['price']) for x in candidates), Decimal(0)), 'f'),
                         'aff10b5one_xml': doc.findtext('aff10b5One'),
                         'footnote_mentions_10b5_1': bool(re.search(r'10b5[-– ]?1', ' '.join(notes.values()), re.I)),
                         'footnotes': notes,
                         'full_past_insider_history_status': 'NOT_ACQUIRED_OR_CLASSIFIED',
                         'index_url': next(s['url'] for s in manifest if s.get('file', '').endswith(acc + '-index.html'))})
    counts = Counter(x['code'] for r in findings for x in r['non_derivative_transactions'])
    summary = {'filings': len(findings), 'fixed_functional_sample_filings': 12, 'selected_positive_controls': 1,
               'html_xml_matches': sum(r['html_xml_transaction_fields_match'] for r in findings),
               'cached_metadata_timestamp_matches': sum(r['cached_acceptance_matches_index'] is True for r in findings),
               'metadata_timestamp_comparisons': sum(r['cached_acceptance_matches_index'] is not None for r in findings),
               'accepted_at_or_after_16_eastern': sum(r['accepted_at_or_after_16_eastern'] for r in findings),
               'non_derivative_transaction_codes': dict(counts),
               'filings_with_10b5_1_footnote': sum(r['footnote_mentions_10b5_1'] for r in findings),
               'insiders_classified': 0, 'security_return_observations_read': 0,
               'new_paid_data_usd': 0,
               'sec_requests': sum(s['is_sec'] for s in manifest),
               'successful_sec_requests': sum(s['is_sec'] and s['status'] == 200 for s in manifest),
               'captured_bytes_all_sources': sum(s.get('bytes', 0) for s in manifest)}
    out = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'field feasibility, not a strategy backtest',
           'summary': summary, 'filings': findings}
    (HERE / 'field-audit.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    run()
