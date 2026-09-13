"""Source-grounded, conservative earnings feature extraction; no network/prices.

extract_pair(slot) accepts the SEC collector's slot mapping: slot_id, current,
prior, prior_match.matched_scope (quarter/year), and original document records.
Each record supplies accession, period_end, exhibit_file, exhibit_sha256,
exhibit_url, acceptance_eastern/filing_date, and optionally explicitly identified
accounting_companions with file/sha256/document_type/source_evidence.

Returns {slot_id, status, flags, missing_reasons, current, original_prior,
comparisons, narrative}. Each document result has documents (verified hashes),
period_end, scope, accounting_basis, metrics.revenue/diluted_eps. A metric has
current and comparable_prior, each a value or null plus cell evidence and reasons.
Values are decimal strings in the displayed currency's units (revenue scaling
applied; EPS per-share). Current-release comparative columns remain separate from
the original prior document. No companyfacts, later amendments, prices, share
adjustments, predictors, investment returns, or zero-revenue assumptions.

The parser expands actual table spans and requires aligned year/scope headers.
It leaves PDF-like positioned text, ambiguous columns, units and non-GAAP tables
missing. A missing numerical field is not a missing source document. Narrative
excludes detected financial tables, while preserving prose inside layout tables.
extract_pair does not certify upstream event timing or an EPS/price share-basis
join; downstream must preserve these separately recorded gates.
Each present record also has currency_resolution (currency, method, literal
metric currencies, cover evidence, reasons and rule sources). Its regulatory
USD inference uses a hash-verified same-accession original US incorporation
cover and the pre-existing reporting rule; it never replaces literal labels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"script", "style", "noscript", "nav", "ix:hidden", "ix:header"}
VOID = {"br", "hr", "img", "meta", "link", "input", "wbr"}
MONTHS = "january february march april may june july august september october november december".split()
SCOPE = re.compile(r"\b(three\s+months?|quarter|thirteen\s+weeks?|fourteen\s+weeks?|1[34]\s*[- ]weeks?|year(?:s)?\s+ended|twelve\s+months?|fifty[- ](?:two|three)\s+weeks?)\b", re.I)
FINANCIAL = re.compile(r"revenue|sales|income|loss|earnings|assets|liabilities|cash\s+flow|expenses|diluted", re.I)
REVENUE = re.compile(r"^(?:(?:(?:total|net|total net|collaboration)\s+)?(?:revenues?|sales)|sales and service fees)(?:\s*\(\d+\))?\s*:?$", re.I)
NUMBER = re.compile(r"^\(?\s*[+$€£]?\s*[-−]?\s*(?:\d[\d,]*)(?:\.\d+)?\s*\)?$", re.I)
FINANCIAL_MARKER = re.compile(r"(?:[-–—]\s*)?Financial Tables (?:to )?Follow(?:\s*[-–—])?", re.I)
USD_RULE_SOURCES = [
    {"url": "https://www.sec.gov/files/rules/final/2018/33-10532.pdf", "pages": [1, 78, 178],
     "effective_date": "2018-11-05", "rule": "S-X 3-20(a)(2); domestic reporting USD, exceptional non-USD requests retained"},
    {"url": "https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual/frm-topic-6",
     "sections": ["6110.1", "6120.6", "6640"], "rule": "US incorporation differs from voluntary domestic-form filing by foreign issuers; limited reporting-currency exceptions"},
]
US_STATE_PAIRS = "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|DE:Delaware|DC:District of Columbia|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|WV:West Virginia|WI:Wisconsin|WY:Wyoming"
US_STATES = {value.lower(): name for pair in US_STATE_PAIRS.split('|') for code, name in [pair.split(':')] for value in (code, name)}


def clean(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("\u200b", "")).strip()


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "Node | None" = None
    offset: int = 0

    def text(self):
        if self.tag in SKIP or "display:none" in self.attrs.get("style", "").replace(" ", "").lower():
            return ""
        return clean(" ".join(x if isinstance(x, str) else x.text() for x in self.children))

    def walk(self, tag=None):
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk(tag)

    def nearest(self, tag):
        n = self.parent
        while n and n.tag != tag:
            n = n.parent
        return n


class Document(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self.line_starts = [0]
        self.line_starts.extend(m.end() for m in re.finditer("\n", raw))
        self.root = Node("root")
        self.stack = [self.root]
        self.table_prefixes = {}
        self._visible_prefix_tail = ""
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        line, col = self.getpos()
        node = Node(tag, dict(attrs), parent=self.stack[-1], offset=self.line_starts[line-1]+col)
        if tag == 'table':
            self.table_prefixes[node.offset] = self._visible_prefix_tail
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)
        if all(n.tag not in SKIP and "display:none" not in n.attrs.get("style", "").replace(" ", "").lower() for n in self.stack):
            self._visible_prefix_tail = clean(self._visible_prefix_tail + " " + value)[-1000:]


def grid(table):
    """Expand source colspan/rowspan, keeping each originating cell for evidence."""
    result, pending = [], {}
    for row in (r for r in table.walk("tr") if r.nearest("table") is table):
        out, col = {}, 0
        for c, (left, cell) in list(pending.items()):
            out[c] = cell
            if left == 1:
                del pending[c]
            else:
                pending[c] = (left-1, cell)
        cells = [c for c in row.walk() if c.tag in ("td", "th") and c.nearest("tr") is row]
        for cell in cells:
            while col in out:
                col += 1
            try:
                colspan = min(100, max(1, int(cell.attrs.get("colspan", "1"))))
                rowspan = min(100, max(1, int(cell.attrs.get("rowspan", "1"))))
            except ValueError:
                return []
            for c in range(col, col+colspan):
                out[c] = cell
                if rowspan > 1:
                    pending[c] = (rowspan-1, cell)
            col += colspan
        if out:
            result.append([out.get(i) for i in range(max(out)+1)])
    return result


def num(text):
    text = clean(text)
    if not NUMBER.fullmatch(text):
        return None
    negative = "(" in text or "−" in text or "-" in text
    try:
        value = Decimal(re.sub(r"[\s,$€£()+−-]", "", text))
    except InvalidOperation:
        return None
    return -value if negative else value


def texts(row):
    return [c.text() if c else "" for c in row]


def is_financial(table, rows):
    # Layout tables can contain narrative with numbers; pure numeric cells are key.
    short_numeric = sum(num(c.text()) is not None for row in rows for c in set(x for x in row if x))
    metric_rows = sum(bool(FINANCIAL.search(" ".join(texts(row)))) and sum(num(t) is not None for t in texts(row)) >= 2 for row in rows)
    return short_numeric >= 4 and metric_rows >= 2


def scope_of(header):
    q = bool(re.search(r"three\s+months?|quarter|(?:thirteen|fourteen|1[34])\s*[- ]weeks?", header, re.I))
    y = bool(re.search(r"years?\s+ended|twelve\s+months?|fifty[- ](?:two|three)\s+weeks?", header, re.I))
    return "quarter" if q and not y else "year" if y and not q else None


def missing(reason):
    return {"value": None, "reasons": [reason], "evidence": []}


def explicit_currency(text):
    """Currency presentation evidence, not an inference from a US listing."""
    patterns = {
        "USD": r"U\.?S\.?\s*\$|(?:amounts|figures|statements|presented|reported|expressed|denominated).{0,70}(?:U\.?S\.? dollars|United States dollars|\bUSD\b)|translat(?:ing|ed).{0,50}\bto\s+(?:U\.?S\.? dollars|United States dollars)\s+for financial reporting purposes",
        "CAD": r"Canadian\s+(?:dollars|\$)|C\$",
        "GBP": r"pounds sterling|\bGBP\b",
        "EUR": r"(?:amounts|figures|statements|presented|reported|expressed|denominated).{0,70}(?:euros|\bEUR\b)",
    }
    found = []
    for currency, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            found.append({"currency": currency, "excerpt": text[max(0, match.start()-50):match.end()+70]})
    return found[0] if len(found) == 1 else None


def cover_incorporation(doc):
    """Only DEI incorporation facts or the actual labeled cover-table column."""
    evidence = []
    for node in doc.root.walk():
        if node.attrs.get('name', '').lower() == 'dei:entityincorporationstatecountrycode':
            evidence.append({'method': 'ORIGINAL_DEI_INCORPORATION', 'value': node.text(),
                             'context_ref': node.attrs.get('contextref'), 'excerpt': node.text()})
    for ti, table in enumerate(doc.root.walk('table')):
        rows = grid(table)
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                if not cell or not re.fullmatch(r'\(?state or other jurisdiction of incorporation(?: or organization)?\)?', cell.text(), re.I):
                    continue
                for earlier in reversed(rows[max(0, ri-3):ri]):
                    value = earlier[ci].text() if ci < len(earlier) and earlier[ci] else ''
                    if value:
                        evidence.append({'method': 'ORIGINAL_LABELED_COVER_COLUMN', 'value': value,
                                         'table_index': ti, 'row_index': ri, 'column_index': ci,
                                         'excerpt': value+' | '+cell.text()})
                        break
    states = {US_STATES.get(clean(e['value']).lower()) for e in evidence}
    state = next(iter(states)) if len(states) == 1 and None not in states else None
    return {'state': state, 'status': 'US_STATE_SOURCE_VERIFIED' if state else 'FOREIGN_CONFLICTING_OR_UNRESOLVED_INCORPORATION', 'evidence': evidence}


@lru_cache(maxsize=4)
def _source_catalog(path, mtime_ns, size):
    raw = Path(path).read_bytes()
    return json.loads(raw).get('sources', {}), sha256(raw).hexdigest()


def original_cover_evidence(record, issuer_cik):
    """Hash-bind the same-accession cover; no later/current issuer metadata."""
    result = {'status': 'ORIGINAL_COVER_UNRESOLVED', 'reasons': []}
    try:
        if record.get('form') != '8-K' or not issuer_cik:
            raise ValueError('ORIGINAL_8K_ISSUER_BINDING_UNAVAILABLE')
        accession = record['accession']
        url = record['primary_url']
        expected = f'https://www.sec.gov/Archives/edgar/data/{int(issuer_cik)}/{accession.replace("-", "")}/'
        if not url.startswith(expected):
            raise ValueError('COVER_ACCESSION_OR_CIK_MISMATCH')
        available = datetime.fromisoformat(record['acceptance_eastern'])
        if available.tzinfo is None or record['filing_date'] < '2018-11-05':
            raise ValueError('COVER_TIMING_OR_RULE_DATE_UNRESOLVED')
        path = ROOT / record['primary_file']
        # The raw path identifies its acquisition ledger, not an issuer identity.
        relative = path.relative_to(ROOT).parts
        if relative[:2] != ('data', 'snapshots'):
            raise ValueError('COVER_SOURCE_LEDGER_UNAVAILABLE')
        catalog_path = ROOT/'research'/relative[2]/'sec-sources.json'
        stat = catalog_path.stat()
        catalog, catalog_hash = _source_catalog(str(catalog_path), stat.st_mtime_ns, stat.st_size)
        source = catalog[url]
        raw = path.read_bytes()
        actual = sha256(raw).hexdigest()
        if source['file'] != record['primary_file'] or source['sha256'] != actual:
            raise ValueError('COVER_SOURCE_HASH_OR_PATH_MISMATCH')
        doc = Document(raw.decode('utf-8', errors='replace'))
        result = {**cover_incorporation(doc), 'source': {'file': record['primary_file'], 'sha256': actual,
                  'url': url, 'accession': accession, 'cik': str(issuer_cik),
                  'available_at': record['acceptance_eastern'], 'filing_date': record['filing_date'],
                  'source_manifest_path': str(catalog_path.relative_to(ROOT)), 'source_manifest_snapshot_sha256': catalog_hash},
                  'foreign_private_issuer_mentioned': bool(re.search(r'foreign private issuer', doc.root.text(), re.I)), 'reasons': []}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        result['reasons'] = [str(exc) if isinstance(exc, ValueError) else 'ORIGINAL_COVER_OR_SOURCE_BINDING_UNAVAILABLE']
    return result


def resolve_currency(metrics, fulltext, cover, *, ifrs=False):
    """A regulatory inference is separate from literal metric currency labels.

    Returns currency/method/literal_metric_currencies/cover_evidence/reasons/
    rule_sources. USD inference does not convert amounts, establish EPS share
    basis, or certify that a furnished release itself is a filed S-X statement.
    """
    literal = {m: sorted({e['currency'] for role in roles.values() for e in role.get('evidence', [])}) for m, roles in metrics.items()}
    labels = {c for currencies in literal.values() for c in currencies}
    out = {'currency': None, 'method': 'UNRESOLVED', 'literal_metric_currencies': literal,
           'cover_evidence': cover, 'reasons': [], 'rule_sources': USD_RULE_SOURCES}
    if labels == {'USD'}:
        out.update(currency='USD', method='EXPLICIT_ORIGINAL_RELEASE_USD')
        return out
    if labels != {'DOLLAR_SYMBOL'}:
        out['reasons'].append('LITERAL_CURRENCY_MISSING_OR_CONFLICTING')
    if cover.get('status') != 'US_STATE_SOURCE_VERIFIED':
        out['reasons'].append('US_STATE_INCORPORATION_NOT_VERIFIED')
    if ifrs or cover.get('foreign_private_issuer_mentioned') or re.search(r'foreign private issuer|\bIFRS\b', fulltext, re.I):
        out['reasons'].append('FOREIGN_OR_IFRS_PRESENTATION_REQUIRES_EXPLICIT_CURRENCY')
    conflict = re.search(r'Canadian\s+(?:dollars|\$)|C\$|Australian\s+dollars|New Zealand\s+dollars|Hong Kong\s+dollars|Singapore\s+dollars|\b(?:CAD|AUD|NZD|HKD|SGD|RMB|CNY|EUR|GBP)\b|renminbi|pounds sterling|euros|reporting currency.{0,50}(?:other than|not).{0,20}(?:U\.?S\.?|United States)|(?:few|little|no) (?:assets|operations).{0,40}(?:U\.?S\.?|United States)', fulltext, re.I)
    if conflict:
        out['reasons'].append('NAMED_NON_USD_OR_REPORTING_EXCEPTION_EVIDENCE')
        out['conflicting_source_excerpt'] = fulltext[max(0, conflict.start()-50):conflict.end()+100]
    if not out['reasons']:
        out.update(currency='USD', method='REGULATORY_USD_INFERENCE')
    return out


def extract_tables(doc, source, end, prior_end, scope):
    candidates = {m: {p: [] for p in ("current", "comparable_prior")} for m in ("revenue", "diluted_eps")}
    financial_tables = set()
    table_count = 0
    document_currency = explicit_currency(doc.root.text())
    for table_index, table in enumerate(doc.root.walk("table")):
        rows = grid(table)
        if not rows or not is_financial(table, rows):
            continue
        financial_tables.add(table)
        table_count += 1
        prefix = doc.table_prefixes[table.offset]
        caption = clean(prefix + " " + table.text()[:600])
        # A statement heading overrides preceding reconciliation discussion.
        headings = list(re.finditer(r"(?:condensed\s+)?consolidated\s+(?:statements?|results)", caption, re.I))
        if headings:
            caption = caption[headings[-1].start():]
        if re.search(r"reconciliation|non[- ]gaap|adjusted\s+(?:results|income|earnings|eps)|managed\s+revenue", caption, re.I):
            continue
        standard_statement = bool(re.search(r"(?:statements?|results)\s+of\s+(?:operations|income|earnings)|statement.*comprehensive", caption, re.I))
        if not standard_statement and not re.search(r"\bGAAP\b", caption):
            continue
        scales = set()
        for unit, scale in (("thousands", 1000), ("millions", 1000000), ("billions", 1000000000)):
            if re.search(r"(?:in|and|\$)\s+"+unit+r"\b", caption, re.I):
                scales.add(scale)
        multiplier = next(iter(scales)) if len(scales) == 1 else None
        currency_proof = explicit_currency(caption) or document_currency
        currency = currency_proof['currency'] if currency_proof else "DOLLAR_SYMBOL" if "$" in table.text() else None
        all_header_rows = []
        previous_labels = []
        for ri, row in enumerate(rows):
            cells = texts(row)
            header_row = (any(SCOPE.search(t) for t in cells) or any(re.fullmatch(r"20\d{2}", t) for t in cells)
                          or any(re.fullmatch(r"(?:"+"|".join(MONTHS)+r")\s+\d{1,2},?", t, re.I) for t in cells))
            if header_row:
                all_header_rows.append(cells)
            positions = [(i, num(t)) for i, t in enumerate(cells) if num(t) is not None and not re.fullmatch(r"20\d{2}", t)]
            if not positions:
                label = clean(" ".join(dict.fromkeys(t for t in cells if t)))
                if label:
                    previous_labels.append(label)
                continue
            first_col = positions[0][0]
            label = clean(" ".join(dict.fromkeys(t for t in cells[:first_col] if t and t not in ("$", "(", ")"))))
            recent = " ".join(previous_labels[-3:])
            metric = "revenue" if REVENUE.fullmatch(label) else None
            eps_context = label + " " + recent
            shares_context = label + (" " + recent if label.lower() == "diluted" else "")
            if "diluted" in label.lower() and re.search(r"per\s+(?:common\s+)?share|earnings\s+per", eps_context, re.I) and not re.search(r"weighted|average.*shares|shares.*outstanding", shares_context, re.I):
                metric = "diluted_eps"
            previous_labels.append(label)
            if metric is None or re.search(r"non[- ]gaap|adjusted|managed|segment", label, re.I):
                continue
            for ci, value in positions:
                # Deduplicate a source cell expanded over multiple physical columns.
                if ci and row[ci] is row[ci-1]:
                    continue
                header = clean(" ".join(dict.fromkeys(h[ci] for h in all_header_rows if ci < len(h) and h[ci])))
                years = re.findall(r"\b20\d{2}\b", header)
                if len(set(years)) != 1 or scope_of(header) != scope:
                    continue
                role = "current" if end and years[0] == end[:4] else "comparable_prior" if prior_end and years[0] == prior_end[:4] else None
                if role is None:
                    continue
                period = end if role == "current" else prior_end
                month = MONTHS[int(period[5:7])-1]
                if not re.search(month+r"\s+"+str(int(period[8:10]))+r"\b", header, re.I):
                    continue
                cell_text = cells[ci]
                if (ci and cells[ci-1] == "(") or (ci+1 < len(cells) and cells[ci+1] == ")"):
                    value = -abs(value)
                scale = 1 if metric == "diluted_eps" else multiplier
                if scale is None or currency is None:
                    continue
                evidence = {**source, "table_index": table_index, "row_index": ri, "column_index": ci,
                            "row_label": label, "column_header": header, "cell_text": cell_text, "table_caption": caption[:750],
                            "period_end": period, "scope": scope, "currency": currency, "scale": scale,
                            "currency_source_evidence": currency_proof,
                            "units": "currency_per_share" if metric == "diluted_eps" else "currency_units",
                            "accounting_basis": "GAAP_STATEMENT", "raw_display_value": str(value)}
                candidates[metric][role].append({"value": str(value*scale), "evidence": evidence})
    result = {}
    for metric, roles in candidates.items():
        result[metric] = {}
        for role, found in roles.items():
            unique = {(f["value"], f["evidence"]["currency"], f["evidence"]["row_label"].lower()) for f in found}
            if not found:
                result[metric][role] = missing("NO_UNAMBIGUOUS_GAAP_SCOPE_ALIGNED_TABLE_CELL")
            elif len(unique) != 1:
                result[metric][role] = {"value": None, "reasons": ["CONFLICTING_OR_DIFFERENT_MEASURE_CANDIDATES"], "evidence": [f["evidence"] for f in found]}
            else:
                result[metric][role] = {"value": found[0]["value"], "reasons": [], "evidence": [f["evidence"] for f in found]}
    return result, financial_tables, table_count


def narrative(root, financial_tables):
    def walk(node):
        if node in financial_tables or node.tag in SKIP or node.tag == "img":
            return []
        if "display:none" in node.attrs.get("style", "").replace(" ", "").lower():
            return []
        out = []
        for child in node.children:
            out.extend([child] if isinstance(child, str) else walk(child))
        return out
    text = clean(" ".join(walk(root)))
    # PDF-converted releases may draw financial tables as positioned DIVs.
    # An explicit source marker establishes their boundary without deleting
    # ordinary narrative merely because it happens to live inside a table.
    marker = FINANCIAL_MARKER.search(text)
    if marker:
        text = text[:marker.start()]
    text = re.sub(r"https?://\S+|\b[\w.+-]+@[\w.-]+\b", " ", text)
    text = re.sub(r"\b[\w.-]*\d[\w.,:%/-]*\b", " ", text)
    return clean(text)


def read_record(record, prior_end, scope, issuer_cik=None):
    if not record:
        return {"source_ready": False, "missing_reasons": ["ORIGINAL_DOCUMENT_MISSING"], "narrative": "", "metrics": {m: {p: missing("ORIGINAL_DOCUMENT_MISSING") for p in ("current", "comparable_prior")} for m in ("revenue", "diluted_eps")}}
    sources = [{"file": record.get("exhibit_file"), "sha256": record.get("exhibit_sha256"), "url": record.get("exhibit_url"), "document_type": record.get("document_type", "EARNINGS_RELEASE")}]
    for companion in record.get("accounting_companions", []):
        if companion.get("document_type") == "SHAREHOLDER_LETTER" and companion.get("source_evidence"):
            sources.append({k: companion.get(k) for k in ("file", "sha256", "url", "document_type")})
    documents, metrics, narratives, fulltexts, reasons = [], [], [], [], []
    seen = set()
    for source in sources:
        try:
            raw = (ROOT / source["file"]).read_bytes()
            actual = sha256(raw).hexdigest()
            if actual != source["sha256"]:
                raise ValueError("DOCUMENT_HASH_MISMATCH")
        except (OSError, TypeError, ValueError) as exc:
            reasons.append(str(exc) if isinstance(exc, ValueError) else "ORIGINAL_DOCUMENT_OR_HASH_UNAVAILABLE")
            continue
        if actual in seen:
            continue
        seen.add(actual)
        doc = Document(raw.decode("utf-8", errors="replace"))
        evidence = {**source, "accession": record.get("accession"), "available_at": record.get("acceptance_eastern", record.get("filing_date"))}
        numerical, financial, count = extract_tables(doc, evidence, record.get("period_end"), prior_end, scope)
        metrics.append(numerical)
        text = narrative(doc.root, financial)
        full = doc.root.text()
        fulltexts.append(full)
        narratives.append(text)
        marker_applied = bool(FINANCIAL_MARKER.search(full))
        heading = re.search(r"(?:consolidated|selected)\s+statements?\s+of\s+(?:operations|income)", text, re.I)
        tail = text[heading.end():heading.end()+1600] if heading else ""
        dense_financial_labels = sum(bool(re.search(pattern, tail, re.I)) for pattern in (
            r"net (?:sales|revenues?)", r"(?:net|gross) (?:income|loss|profit)", r"cost (?:of|and)",
            r"operating expenses", r"weighted[- ]average", r"(?:basic|diluted).*per share")) >= 3
        unresolved_financial_text = not marker_applied and count == 0 and bool(heading) and dense_financial_labels
        corrupt_words = re.findall(r"\b\w+!\w+(?:!\w+)*\b", text)
        replacement_characters = text.count("\ufffd")
        documents.append({**evidence, "financial_tables_removed": count, "explicit_financial_section_marker_applied": marker_applied,
                          "unstructured_financial_text_unresolved": unresolved_financial_text,
                          "encoding_artifact_word_count": len(corrupt_words),
                          "encoding_artifact_word_fraction": len(corrupt_words)/max(1, len(text.split())),
                          "replacement_character_count": replacement_characters,
                          "narrative_words": len(text.split()), "narrative_sha256": sha256(text.encode()).hexdigest()})
    merged = {}
    for metric in ("revenue", "diluted_eps"):
        merged[metric] = {}
        for role in ("current", "comparable_prior"):
            found = [m[metric][role] for m in metrics if m[metric][role]["value"] is not None]
            values = {(f["value"], tuple(sorted({e["currency"] for e in f["evidence"]}))) for f in found}
            if not found:
                merged[metric][role] = {"value": None, "reasons": sorted({r for m in metrics for r in m[metric][role]["reasons"]}) or ["NO_UNAMBIGUOUS_GAAP_SCOPE_ALIGNED_TABLE_CELL"],
                                        "evidence": [e for m in metrics for e in m[metric][role]["evidence"]]}
            elif len(values) == 1:
                merged[metric][role] = {"value": found[0]["value"], "reasons": [], "evidence": [e for f in found for e in f["evidence"]]}
            else:
                merged[metric][role] = {"value": None, "reasons": ["CONFLICTING_DOCUMENT_VALUES_OR_CURRENCY"], "evidence": [e for f in found for e in f["evidence"]]}
    fulltext = " ".join(fulltexts)
    main_text = fulltexts[0] if fulltexts else ""
    ifrs = bool(re.search(r"\bIFRS\b|international financial reporting standards", fulltext, re.I))
    transition = bool(re.search(r"no longer reports.{0,90}IFRS|transitioned.{0,60}IFRS to GAAP", main_text, re.I))
    ifrs_presentation = bool(re.search(r"on an? IFRS basis|prepared.{0,80}accordance with IFRS", main_text, re.I)) and not transition
    us_gaap = (transition or bool(re.search(r"on a GAAP basis|prepared.{0,80}accordance with GAAP|U\.?S\.?\s+(?:GAAP|generally accepted accounting principles)", main_text, re.I))) and not ifrs_presentation
    if ifrs_presentation or (ifrs and not us_gaap):
        for metric in merged.values():
            for role in metric:
                metric[role] = {**metric[role], "reported_value_before_basis_gate": metric[role]["value"], "value": None, "reasons": ["ORIGINAL_ACCOUNTING_BASIS_IFRS_NOT_GAAP"]}
    duration_evidence = []
    unequal = False
    for match in re.finditer(r"(?:13[- ]week|thirteen[- ]week)", fulltext, re.I):
        excerpt = fulltext[max(0, match.start()-120):match.end()+500]
        if re.search(r"14(?:th)?[- ]week|fourteen[- ]week", excerpt, re.I) and "quarter" in excerpt.lower():
            unequal = True
            duration_evidence.append(excerpt)
    if scope == "year":
        for match in re.finditer(r"52[- ]week|fifty[- ]two[- ]week", fulltext, re.I):
            excerpt = fulltext[max(0, match.start()-120):match.end()+500]
            if re.search(r"53(?:rd)?[- ]week|fifty[- ]three[- ]week", excerpt, re.I) and "year" in excerpt.lower():
                unequal = True
                duration_evidence.append(excerpt)
    cover = original_cover_evidence(record, issuer_cik)
    currency_resolution = resolve_currency(merged, fulltext, cover, ifrs=ifrs_presentation or (ifrs and not us_gaap))
    return {"source_ready": len(documents) == len({s.get('sha256') for s in sources}) and bool(documents), "missing_reasons": reasons,
            "documents": documents, "period_end": record.get("period_end"), "scope": scope, "quarter_ordinal": record.get("quarter_ordinal"),
            "currency_resolution": currency_resolution,
            "accounting_basis": "US_GAAP_EXPLICIT" if us_gaap else "IFRS_EXPLICIT" if ifrs else "GAAP_STATEMENT_WHERE_EXTRACTED",
            "metrics": merged, "narrative": "\n\n".join(narratives), "narrative_words": sum(len(t.split()) for t in narratives),
            "flags": {"unequal_quarter_duration": unequal, "duration_evidence": duration_evidence,
                      "ifrs_mentioned": ifrs, "us_gaap_explicit": us_gaap,
                      "recast_or_restated_mentioned": bool(re.search(r"restat|recast|retrospective", fulltext, re.I)),
                      "split_mentioned": bool(re.search(r"stock split|reverse split|share split", fulltext, re.I)),
                      "text_encoding_artifact": bool(re.search(r"\w!\w", " ".join(narratives)) or "\ufffd" in fulltext),
                      "unstructured_financial_text_unresolved": any(d['unstructured_financial_text_unresolved'] for d in documents),
                      "source_document_types": [s['document_type'] for s in documents]}}


def extract_pair(slot):
    """See module schema. Never replace an uncertain value with zero."""
    current, prior = slot.get("current"), slot.get("prior")
    match = slot.get("prior_match") or {}
    scope = match.get("matched_scope")
    if scope not in ("quarter", "year"):
        scope = None
    cur = read_record(current, prior.get("period_end") if prior else None, scope, slot.get('cik'))
    old = read_record(prior, None, scope, slot.get('cik'))
    def roles(result):
        return ['PRESS_RELEASE' if t in ('EARNINGS_RELEASE', 'PRESS_RELEASE_WITH_ACCOUNTING_COMPANION', 'PRESS_RELEASE') else t
                for t in result.get('flags', {}).get('source_document_types', [])]
    flags = {"scope": scope, "scope_unresolved": scope is None,
             "period_join_verified": match.get("verified") is True,
             "fiscal_quarter_ordinal": current.get("quarter_ordinal") if current else None,
             "unequal_duration": cur.get("flags", {}).get("unequal_quarter_duration", False),
             "accounting_transition": old.get("flags", {}).get("ifrs_mentioned", False) and cur.get("flags", {}).get("us_gaap_explicit", False),
             "eps_price_share_basis_status": "REQUIRES_VERIFIED_PREENTRY_PRICE_AND_EFFECTIVE_SPLIT_JOIN",
             "current_metric_currency": {m: sorted({e['currency'] for e in cur['metrics'][m]['current']['evidence']}) for m in ('revenue', 'diluted_eps')},
             "document_types_match": roles(cur) == roles(old),
             "canonical_document_roles": {'current': roles(cur), 'original_prior': roles(old)},
             "predecessor_search_coverage": slot.get("predecessor_coverage", slot.get("predecessor_search", slot.get("predecessor_search_coverage", "NOT_PROVIDED")))}
    comparisons = {}
    for metric in ("revenue", "diluted_eps"):
        a, b = (cur["metrics"][metric][p] for p in ("current", "comparable_prior"))
        reasons = list(a["reasons"] + b["reasons"])
        bindings = lambda value: {(e['file'], e['table_index'], e['row_label'].lower(), e['currency']) for e in value['evidence']}
        if a['value'] is not None and b['value'] is not None and not bindings(a).intersection(bindings(b)):
            reasons.append('COMPARATIVES_NOT_IN_SAME_EXPLICIT_TABLE_ROW_AND_CURRENCY')
        if scope is None:
            reasons.append("DECLARED_FISCAL_SCOPE_UNRESOLVED")
        if not flags["period_join_verified"]:
            reasons.append("ORIGINAL_FISCAL_PERIOD_JOIN_UNVERIFIED")
        if flags["unequal_duration"]:
            reasons.append("UNEQUAL_FISCAL_DURATION")
        if metric == "revenue" and b["value"] is not None and Decimal(b["value"]) <= 0:
            reasons.append("NONPOSITIVE_PRIOR_REVENUE")
        original = old["metrics"][metric]["current"]
        comparisons[metric] = {"current_value": a["value"], "current_release_comparable_prior_value": b["value"],
                               "original_prior_value": original["value"], "same_current_release_comparison_eligible": not reasons,
                               "original_prior_reported_value_before_basis_gate": original.get("reported_value_before_basis_gate", original["value"]),
                               "missing_reasons": sorted(set(reasons)),
                               "original_vs_current_comparative_difference": str(Decimal(b["value"])-Decimal(original["value"])) if b["value"] is not None and original["value"] is not None else None}
    source_ready = cur["source_ready"] and old["source_ready"]
    return {"schema": "earnings-source-features-v1", "slot_id": slot.get("slot_id"),
            "status": "SOURCE_PAIR_READ_NUMERIC_COVERAGE_EXPLICIT" if source_ready else "SOURCE_PAIR_UNRESOLVED",
            "flags": flags, "missing_reasons": cur["missing_reasons"] + old["missing_reasons"],
            "current": {k: v for k, v in cur.items() if k != "narrative"},
            "original_prior": {k: v for k, v in old.items() if k != "narrative"},
            "comparisons": comparisons, "narrative": {"current": cur["narrative"], "original_prior": old["narrative"]}}
