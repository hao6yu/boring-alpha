"""Past-only classification and deterministic filing checks; no return inputs."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


def truth(value):
    return str(value).strip().lower() in {'1', 'true'}


def transaction_day(value):
    # SEC XML xs:date may carry a timezone; preserve its stated calendar day.
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:Z|[+-]\d{2}:\d{2})?', value):
        raise ValueError('Invalid XML transaction date')
    return date.fromisoformat(value[:10]).isoformat()


def compact_day(value):
    return datetime.strptime(value, '%Y%m%d').date().isoformat()


def disclosure_day(submission):
    raw = submission['acceptanceDatetime']
    if not re.fullmatch(r'\d{14}', raw):
        raise ValueError('Missing or unqualified acceptance timestamp')
    accepted = datetime.strptime(raw, '%Y%m%d%H%M%S').date().isoformat()
    return max(accepted, compact_day(submission['filingDate']))


def positive(value):
    try:
        number = Decimal(value)
        return number.is_finite() and number > 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def common_stock(title):
    text = title.lower()
    if re.search(r'preferred|warrant|option|phantom|\bunits?\b|depositary|convertible', text):
        return False
    return bool(re.search(r'\b(common|ordinary)\s+(stock|shares?)\b', text))


def linked_footnotes(transaction, notes):
    required = set()
    for key, value in transaction.items():
        if key.endswith('Fn'):
            required.update(re.findall(r'\bF\d+\b', value))
    missing = required - notes.keys()
    return '\n'.join(notes[k] for k in sorted(required) if k in notes), sorted(missing)


def disclosure_flags(text):
    """Conservative review flags, not a claim that regex proves trading venue."""
    flags = []
    if re.search(r'10b5[-– ]?1', text, re.I):
        flags.append('DISCLOSED_TRADING_PLAN_REVIEW')
    if re.search(r'privat(?:e|ely)|negotiated|subscription agreement|purchase agreement|'
                 r'direct(?:ly)? (?:purchase|purchased|from)|rights offering|public offering|'
                 r'underwrit|registered direct|from the issuer|from the company', text, re.I):
        flags.append('NONMARKET_OR_PRIVATE_REVIEW')
    return flags


def transaction_state(transaction, submission, notes):
    """Eligible open-market-history proxy or an explicit missingness reason."""
    t = transaction
    if t['transactionType'] != 'nonDerivativeTransaction' or t['transactionCode'] not in {'P', 'S'}:
        return 'NOT_PS', []
    if submission['documentType'] != '4':
        return 'AMENDMENT_REVIEW', []
    if not common_stock(t['securityTitle']):
        obvious = re.search(r'preferred|warrant|option|phantom|\bunits?\b|deposit[oa]ry|convertible', t['securityTitle'], re.I)
        return ('NOT_COMMON' if obvious else 'SECURITY_TITLE_REVIEW'), []
    if not positive(t['transactionShares']) or not positive(t['transactionPricePerShare']):
        return 'MISSING_POSITIVE_PRICE_OR_SHARES', []
    if t['transactionAcquiredDisposedCode'] != {'P':'A', 'S':'D'}[t['transactionCode']]:
        return 'ACQUISITION_DIRECTION_CONFLICT', []
    try:
        day = transaction_day(t['transactionDate'])
        public = disclosure_day(submission)
        if day > public:
            return 'TRANSACTION_AFTER_DISCLOSURE', []
    except (ValueError, KeyError):
        return 'DATE_REVIEW', []
    text, missing = linked_footnotes(t, notes)
    if missing:
        return 'MISSING_FOOTNOTE', missing
    flags = disclosure_flags(text + '\n' + submission.get('remarks', ''))
    return 'PS_FIELDS_VALID', flags


def classify(history, disclosure_year, uncertain_years=()):
    """A missing year is unknown; an unseen future filing cannot alter a label."""
    years = set(range(disclosure_year - 3, disclosure_year))
    if years & set(uncertain_years):
        return 'UNKNOWN_HISTORY'
    months = {year: set() for year in years}
    cutoff = f'{disclosure_year}-01-01'
    for trade in history:
        if trade['disclosure_day'] >= cutoff:
            continue
        day = date.fromisoformat(trade['transaction_date'])
        if day.year in months:
            months[day.year].add(day.month)
    if any(not value for value in months.values()):
        return 'UNKNOWN_INSUFFICIENT_YEARS'
    overlap = set.intersection(*months.values())
    return 'ROUTINE' if overlap else 'NONROUTINE'
