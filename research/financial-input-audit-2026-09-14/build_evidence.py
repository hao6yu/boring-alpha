#!/usr/bin/env python3
"""Serialize the manually reviewed filing mappings. No network or price reads.

The numeric constants below were transcribed while reviewing original filings.
They are evidence assertions, not inferred aliases for arbitrary SEC concepts.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = ROOT / 'data/snapshots' / HERE.name


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Order: common stock, paid-in capital if separate, retained earnings,
# accumulated other comprehensive income, treasury stock if present.
CS = 'CommonStockValue'
CSO = 'CommonStockValueOutstanding'
AP = 'AdditionalPaidInCapital'
APC = 'AdditionalPaidInCapitalCommonStock'
RE = 'RetainedEarningsAccumulatedDeficit'
OCI = 'AccumulatedOtherComprehensiveIncomeLossNetOfTax'
TS = 'TreasuryStockValue'
TSC = 'TreasuryStockCommonValue'
BOOK = {
    'PNR': ([CSO, AP, RE, OCI], [[1700000,1585200000,1696100000,-242100000], [1700000,1351800000,2700600000,-271700000]], [3040900000,3782400000]),
    'WHR': ([CS, AP, RE, OCI, TSC], [[114000000,3074000000,7961000000,-2075000000,7010000000], [65000000,3479000000,1272000000,-1888000000,547000000]], [2064000000,2381000000]),
    'AON': ([CS, APC, RE, OCI], [[2000000,7015000000,-3024000000,-4579000000], [2000000,13379000000,-1527000000,-3915000000]], [-586000000,7939000000]),
    'HLT': ([CSO, AP, RE, OCI, TS], [[3000000,10925000000,-4316000000,-728000000,7647000000], [3000000,11220000000,-1770000000,-713000000,13672000000]], [-1763000000,-4932000000]),
    'MDLZ': ([CS, APC, RE, OCI, TSC], [[0,32181000000,33866000000,-11232000000,26280000000], [0,32299000000,36390000000,-11464000000,31048000000]], [28535000000,26177000000]),
    'CMI': ([CSO, RE, OCI, TS], [[2558000000,19520000000,-2051000000,9369000000], [2651000000,22300000000,-2211000000,10676000000]], [10658000000,12064000000]),
    'FLS': ([CS, APC, RE, OCI, TS], [[220991000,501378000,3818392000,-659653000,2014879000], [220991000,496356000,4317965000,-596990000,2180651000]], [1874107000,2264197000]),
}
BOOK_NOTES = {
    'PNR': 'Balance sheet and changes in equity identify ordinary share capital, additional paid-in capital, retained earnings and AOCI. The complete ordinary-capital components reconcile to total equity. This is a reviewed component reconstruction; the absent NCI/preferred tags are not set to zero.',
    'WHR': 'Common stock, paid-in capital, retained earnings, AOCI and treasury common stock reconcile to Whirlpool equity. NCI is reported separately. The 2025 parent total is consolidated equity less the separately reported NCI.',
    'AON': 'Class A ordinary capital and its paid-in capital, retained deficit and AOCI reconcile to Aon shareholder equity, excluding separately presented NCI. Negative 2023 equity is retained.',
    'HLT': 'Balance sheet and Note 10 common-equity columns reconcile to Hilton shareholder deficit. NCI and redeemable NCI are outside these components. Both negative balances are retained.',
    'MDLZ': 'Common stock, additional paid-in common capital, retained earnings, AOCI and treasury stock reconcile to Mondelez shareholder equity. The separately reported NCI is excluded. Rounded zero common par value is not evidence about preferred capital.',
    'CMI': 'Common-stock balance already includes additional paid-in capital. Add retained earnings and AOCI, subtract treasury stock. The result reconciles to Cummins shareholder equity, excluding NCI and any redeemable NCI. Do not add paid-in capital twice.',
    'FLS': '2023: the complete parent equity statement includes a deferred compensation equity obligation of $7,878,000 in addition to the five standard common-equity components, and excludes separately presented NCI. This additional component is manually transcribed because the same-date fact is absent from companyfacts. 2025: the balance sheet explicitly states no preferred shares issued; subtract zero preferred capital from the reported parent equity, not from equity including NCI.',
}
# Prior full year, current YTD, prior YTD. These are independently transcribed
# financial statement/EPS amounts, in dollars; preserve negative earnings.
INCOME = {
    'PNR': [[480900000,414700000,385900000],[625400000,487700000,459000000]],
    'VFC': [[118584000,-508122000,-174392000],[-189716000,73357000,-206708000]],
    'CSCO': [[12613000000,3638000000,2670000000],[10180000000,2860000000,2711000000]],
    'WHR': [[-1519000000,-10000000,85000000],[-323000000,210000000,69000000]],
    'AON': [[2589000000,2066000000,1932000000],[2654000000,2002000000,1938000000]],
    'RHI': [[657919000,323842000,510266000],[251598000,101234000,197308000]],
    'MDLZ': [[2717000000,4009000000,2134000000],[4611000000,1786000000,2866000000]],
}
EPS_NOTES = {
    'PNR': 'EPS reconciliation uses net income and weighted-average ordinary shares for basic EPS; annual and current/prior YTD numerator amounts match these facts.',
    'VFC': 'Annual significant-accounting-policy disclosure explicitly defines basic EPS as total net income (loss) divided by common shares. Current statements reconcile total net income to total basic common EPS. In 2025 preserve discontinued operations in total income; the continuing-operations-only EPS footnote is not the target numerator.',
    'CSCO': 'Note 20 EPS table uses net income as the basic common EPS numerator in both annual and current filings, including prior YTD comparatives.',
    'WHR': 'Annual and current EPS tables explicitly identify earnings available to Whirlpool as the numerator for basic and diluted common EPS. These parent earnings exclude NCI.',
    'AON': 'Annual and current GAAP income statements and EPS disclosures use income attributable to Aon shareholders and basic ordinary shares, after excluding NCI. Adjusted non-GAAP EPS is not used.',
    'RHI': 'Annual and current EPS footnotes reconcile net income and basic common shares, with no separate basic numerator adjustment in the table. Current and comparative YTD amounts and the original full year are reviewed.',
    'MDLZ': 'Annual Note 17 and current EPS tables subtract noncontrolling-interest earnings before basic common EPS. Use parent net earnings, not consolidated earnings including NCI.',
}


def main():
    protocol = read(HERE / 'protocol.json')
    baseline = {(r['symbol'], r['month']): r for r in read(HERE / 'baseline-inputs.json')}
    annuals = {(r['symbol'], r['month']): r for r in read(HERE / 'annual-filing-jobs.json')}
    sm = read(ROOT / 'research/ml-stock-comparison-2026-09-14/submissions-manifest.json')
    fm = read(ROOT / 'research/ml-stock-recent-validation-2026-09-14/sec-manifest.json')
    evidence = []
    dependencies = {}
    for issuer in protocol['sample']:
        symbol, cik = issuer['symbol'], issuer['cik']
        sub = read(ROOT / sm[cik]['file'])['filings']['recent']
        dependencies[sm[cik]['file']] = sm[cik]['sha256']
        dependencies[fm[cik]['file']] = fm[cik]['filtered_sha256']
        for n, anchor in enumerate(issuer['anchors']):
            base = baseline[symbol, anchor['month']]
            accession = anchor['asset_accession']
            ix = sub['accessionNumber'].index(accession)
            current = dict(url=base['current_filing_url'], accn=accession,
                           filed=sub['filingDate'][ix], report_end=anchor['report_end'],
                           sections='Balance sheet, statement of equity, income statement and EPS disclosures')
            row = dict(symbol=symbol, cik=cik, month=anchor['month'], cut=anchor['cut'],
                       report_end=anchor['report_end'], current=current, book=None, income=None)
            if symbol in BOOK:
                tags, values, totals = BOOK[symbol]
                parts = [dict(tag=tag, val=val, sign=-1 if tag in (TS,TSC) else 1,
                              source='companyfacts', namespace='us-gaap', unit='USD',
                              accn=accession, end=anchor['report_end'])
                         for tag,val in zip(tags,values[n])]
                if symbol == 'FLS' and n == 0:
                    parts.append(dict(tag='DeferredCompensationEquity',val=7878000,sign=1,
                                      source='manual_filing_transcription',namespace='us-gaap',
                                      unit='USD',accn=accession,end=anchor['report_end']))
                method = 'reviewed_complete_common_equity_components'
                if symbol == 'FLS' and n == 1:
                    method = 'parent_less_explicit_zero_preferred_issued'
                    parts = [dict(tag='StockholdersEquity',val=totals[n],sign=1,source='companyfacts',
                                  namespace='us-gaap',unit='USD',accn=accession,end=anchor['report_end'])]
                row['book'] = dict(method=method, parts=parts, expected=totals[n],
                                   common_scope_reviewed=True, preferred_issued_explicit_zero=(symbol=='FLS' and n==1),
                                   note=BOOK_NOTES[symbol], source=current)
            if symbol in INCOME:
                components = base['net_income_ttm']['components']
                assert [p['val'] for p in components] == INCOME[symbol][n]
                annual = annuals[symbol,anchor['month']]
                row['income'] = dict(method='reviewed_total_basic_common_eps_numerators',
                                     note=EPS_NOTES[symbol], parts=[])
                for i,(part,expected) in enumerate(zip(components,INCOME[symbol][n])):
                    record = dict(part)
                    record.update(expected=expected,sign=[1,1,-1][i],
                                  common_scope_reviewed=True,
                                  source_url=annual['url'] if i==0 else current['url'])
                    row['income']['parts'].append(record)
            evidence.append(row)
    write('reviewed-evidence.json',dict(status='MANUALLY_REVIEWED_NUMERIC_AND_SEMANTIC_CERTIFICATES',
          note='Certificates are filing-specific human-readable review assertions. Reproduction verifies numbers and dates against caches; it does not automate accounting judgment or authorize reuse on other filings.',
          rows=evidence))
    write('source-manifest.json',dict(cached_numeric_and_metadata_files=dependencies,
          web_excerpts={str(p.relative_to(ROOT)):sha(p) for p in sorted(RAW.glob('web-evidence-*.json'))},
          browser_review='browser-review.json',
          note='Web-reader excerpts are cached, not complete original HTML. The normal browser resolved oversized annual reports; public-page observations are summarized in browser-review.json. No page export was available.'))
    write('extraction-freeze.json',dict(status='FROZEN_BEFORE_COVERAGE_REPLAY_NO_RETURN_EVALUATION',
          files={name:sha(HERE/name) for name in ['protocol.json','baseline-inputs.json','reviewed-evidence.json','source-manifest.json','browser-review.json','build_evidence.py']},
          rules=['Apply only exact reviewed issuer, accession, period and USD scope.',
                 'Use complete common-equity components reconciled to the filed total, or explicit zero issued preferred shares with parent equity.',
                 'Require three dated total basic common EPS numerator components with aligned fiscal periods.',
                 'Never fill absent preferred or common-earnings adjustment tags with zero.',
                 'Retain original nonmissing values and all unreviewed fields.']))


if __name__ == '__main__':
    main()
