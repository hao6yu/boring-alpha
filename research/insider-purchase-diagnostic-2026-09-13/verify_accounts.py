"""Reconcile completed ledgers independently of the account simulator."""
from collections import defaultdict
import csv
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal as D, ROUND_CEILING
import io
import json

from diagnostic_io import HERE, ROOT, RAW, POLICY_SHA, atomic, digest


def run():
    result=json.loads((HERE/'evaluation-result.json').read_text())
    assert result['policy_sha256']==POLICY_SHA
    assert digest(ROOT/result['ledger']['path'])==result['ledger']['sha256']
    accounts=json.loads((ROOT/result['ledger']['path']).read_text())
    cand=json.loads((RAW/'frozen-account-candidates.json').read_text())
    identity=json.loads((RAW/'price-identity-audit.json').read_text())['identities']
    manifest=json.loads((HERE.with_name('equity-event-expansion-2026-09-13')/'price-manifest.json').read_text())
    raw_cache={}
    def source(cik,day):
        ticker=sorted((t,s) for t,s in identity[cik] if t<day)[-1][1]
        if ticker not in raw_cache:
            meta=manifest['symbols'][ticker]; path=ROOT/meta['path']
            assert digest(path)==meta['sha256']
            rows=list(csv.DictReader(io.StringIO(path.read_text())))
            assert all('2019-10-01'<=r['date'][:10]<='2023-12-29' for r in rows)
            raw_cache[ticker]={r['date'][:10]:r for r in rows}
        return raw_cache[ticker][day]
    cent=lambda x:x.quantize(D('.01'),rounding=ROUND_CEILING)
    report=[]
    for cost,models in accounts.items():
        slip=D('.001') if cost=='base' else D('.005')
        for name,a in models.items():
            events={r['event_id']:r for r in cand['candidates'][name]}
            fills=defaultdict(list)
            for f in a['fills']:
                fills[f['date']].append(f)
                q=D(f['quantity']); raw=source(f['cik'],f['date'])
                assert D(f['raw_close'])==D(raw['close'])
                notional=q*D(raw['close'])*(1+slip if f['side']=='buy' else 1-slip)
                expected={'commission':cent(min(D('.01')*notional,max(D(1),D('.005')*q))),
                    'sec':cent(D('.0000206')*notional) if f['side']=='sell' else D(0),
                    'taf':cent(min(D('9.79'),D('.000195')*q)) if f['side']=='sell' else D(0),
                    'cat':cent(D('.000003')*q)}
                assert expected=={k:D(v) for k,v in f['fees'].items()}
                assert D(f['notional'])==notional and D(f['fee_total'])==sum(expected.values())
                assert D(f['slippage_cost'])==q*D(raw['close'])*slip
                event=events[f['event_id']]
                if f['side']=='buy': assert max(event['filing_date'],event['acceptance_date_et'])<f['date']
            assert not any(x['type']=='split' for x in a['action_log']), 'Extend replay explicitly if an actual held split exists'
            claims=[]; cash=D(10000); holdings={}; high=D(10000); first_stop=None
            recomputed=[]
            for row in a['daily']:
                day=row['date']
                for c in claims:
                    if not c['paid'] and c['cash_available_date'] is not None and c['cash_available_date']<=day:
                        cash+=D(c['amount']); c['paid']=True
                for c in a['claims']:
                    if c['created_date']!=day or c['type']=='sale': continue
                    assert c['type']=='dividend'
                    q=holdings[c['security_id']]['quantity']; raw=source(c['cik'],day)
                    assert D(c['amount'])==q*D(raw['divCash']) and D(c['entitled_quantity'])==q
                    cc={**c,'paid':False}
                    if c['cash_available_date'] is not None and c['cash_available_date']<=day:
                        cash+=D(c['amount']); cc['paid']=True
                    claims.append(cc)
                for f in fills[day]:
                    sec=f['security_id']; q=D(f['quantity']); v=D(f['notional']); fee=D(f['fee_total'])
                    if f['side']=='buy':
                        assert sec not in holdings
                        assert first_stop is None
                        cash-=v+fee; holdings[sec]={'quantity':q,'cik':f['cik']}
                        assert cash>=2000
                    else:
                        assert holdings[sec]['quantity']==q
                        del holdings[sec]
                        expected=v-fee
                        claim=next(c for c in a['claims'] if c['event_id']==f['event_id'] and c['type']=='sale')
                        assert D(claim['amount'])==expected
                        available=next((r['date'] for r in a['daily'] if r['date']>=(date.fromisoformat(day)+timedelta(days=7)).isoformat()),None)
                        assert claim['cash_available_date']==available
                        claims.append({**claim,'paid':False})
                equity=sum((h['quantity']*D(source(h['cik'],day)['close']) for h in holdings.values()),D(0))
                unpaid=sum((D(c['amount']) for c in claims if not c['paid']),D(0))
                nav=cash+unpaid+equity
                assert nav==D(row['nav']) and cash==D(row['settled_cash']) and unpaid==D(row['unpaid_claim_value'])
                assert set(holdings)==set(row['holdings'])
                high=max(high,nav)
                assert high==D(row['high_water_observed']) and high-nav==D(row['drawdown_observed'])
                if high-nav>=2000 and first_stop is None: first_stop=day
                assert row['account_stopped']==(first_stop is not None)
                recomputed.append(nav)
            assert first_stop==a['stop_date'] and not holdings
            positions=result['accounts'][cost][name]['position_results']
            assert abs(sum(D(str(p['net_profit_usd'])) for p in positions)-(recomputed[-1]-10000))<D('.00000001')
            report.append({'cost_case':cost,'account':name,'daily_NAVs_reconciled':len(recomputed),
                'fills_recomputed_from_raw_source':len(a['fills']),'cash_claims_checked':len(claims),
                'ending_nav':str(recomputed[-1]),'first_halt_recomputed':first_stop,'status':'RECONCILED'})
    frozen=json.loads((HERE/'signal-freeze.json').read_text())
    assert all(digest(HERE/name)==sha for name,sha in frozen['source_files'].items())
    roster=json.loads((HERE/'source-roster-cross-check.json').read_text())
    assert not roster['daily_mapping_differences']
    record={'status':'ALL_SIX_CONDITIONAL_ACCOUNT_LEDGERS_RECONCILED','verified_at_utc':datetime.now(timezone.utc).isoformat(),
        'accounts':report,'raw_price_files_rechecked':len(raw_cache),
        'source_policy_and_signal_code_unchanged':True,
        'qualification':'Independent Decimal cash/claim/share replay and raw-file fill checks. Same source data; not external replication. This verifies conditional account arithmetic, not missing opportunity or control coverage.'}
    atomic(HERE/'account-verification.json',record)
    print(json.dumps(record))


if __name__=='__main__': run()
