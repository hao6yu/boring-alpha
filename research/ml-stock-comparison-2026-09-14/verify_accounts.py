#!/usr/bin/env python3
"""Independent raw-mark, fee and cash/claim/share replay of account outputs."""
from collections import defaultdict
from datetime import date,timedelta
from decimal import Decimal as D, ROUND_CEILING
import json
from models import HERE,ROOT,RAW,SESSIONS,account_frames
from probe import sha,write

def main():
    result=json.loads((HERE/'evaluation-result.json').read_text());before=json.loads((HERE/'evaluation-start.json').read_text())
    for name,h in before['code'].items():assert sha((HERE/name).read_bytes())==h
    frames,actions=account_frames();byday=defaultdict(list)
    for action in actions:byday[action['effective_date']].append(action)
    cents=lambda v:v.quantize(D('.01'),rounding=ROUND_CEILING)
    reports=[]
    for name,ref in result['account_files'].items():
        b=(ROOT/ref['file']).read_bytes();assert sha(b)==ref['sha256'];account=json.loads(b)
        slip=D('.001') if name.endswith('-base') else D('.005');fills=defaultdict(list)
        for f in account['fills']:
            day,s=f['date'],f['security_id'];q=D(f['quantity']);close=D(frames[day][s]['close'])
            assert q>0 and q==q.to_integral_value() and close==D(f['raw_close'])
            notional=q*close*(1+slip if f['side']=='buy' else 1-slip)
            fees=dict(commission=cents(min(D('.01')*notional,max(D(1),D('.005')*q))),sec=cents(D('.0000206')*notional) if f['side']=='sell' else D(0),
                      taf=cents(min(D('9.79'),D('.000195')*q)) if f['side']=='sell' else D(0),cat=cents(D('.000003')*q))
            assert fees=={k:D(v) for k,v in f['fees'].items()} and notional==D(f['notional'])
            assert sum(fees.values())==D(f['fee_total']) and q*close*slip==D(f['slippage_cost'])
            if f['side']=='buy':assert day==[d for d in SESSIONS if d[:7]==day[:7]][1]
            fills[day].append(f)
        cash=high=D(10000);holdings={};claims={};claimed={c['claim_id']:c for c in account['claims']};first_stop=None;checked=0
        for row in account['daily']:
            day=row['date']
            if row['nav'] is None:break
            for c in claims.values():
                if not c['paid'] and c['cash_available_date'] is not None and c['cash_available_date']<=day:cash+=D(c['amount']);c['paid']=True
            for action in sorted(byday[day],key=lambda x:x['action_id']):
                s,key=action['security_id'],action['action_id']
                if s not in holdings:continue
                assert action['verified'];h=holdings[s]
                if action['type']=='split':h['quantity']*=D(action['factor']);assert h['quantity']==h['quantity'].to_integral_value()
                elif action['type'] in ['dividend','merger_cash']:
                    c=dict(claimed[key],paid=False);assert D(c['amount'])==h['quantity']*D(action['amount_per_share']);claims[key]=c
                    assert c['cash_available_date']==action['cash_available_date']
                    if c['cash_available_date'] is not None and c['cash_available_date']<=day:cash+=D(c['amount']);c['paid']=True
                    if action['type']=='merger_cash':del holdings[s]
                else:raise AssertionError('A held unqualified distribution cannot have a complete NAV.')
            for f in fills[day]:
                s,q=f['security_id'],D(f['quantity']);value,fee=D(f['notional']),D(f['fee_total'])
                if f['side']=='buy':
                    assert s not in holdings and first_stop is None;cash-=value+fee;holdings[s]=dict(quantity=q,basis=value+fee)
                    assert cash>=2000 and len(holdings)<=10
                else:
                    assert holdings[s]['quantity']==q
                    c=next(c for c in account['claims'] if c['type']=='sale' and c['event_id']==f['event_id'])
                    assert D(c['amount'])==value-fee
                    earliest=(date.fromisoformat(day)+timedelta(days=7)).isoformat();available=next((d for d in SESSIONS if d>=earliest),None)
                    assert c['cash_available_date']==available;claims[c['claim_id']]=dict(c,paid=False);del holdings[s]
            equity=sum((h['quantity']*D(frames[day][s]['close']) for s,h in holdings.items()),D(0));unpaid=sum((D(c['amount']) for c in claims.values() if not c['paid']),D(0));nav=cash+equity+unpaid
            assert nav==D(row['nav']) and cash==D(row['settled_cash']) and unpaid==D(row['unpaid_claim_value'])
            assert set(holdings)==set(row['holdings'])
            high=max(high,nav)
            if high-nav>=2000 and first_stop is None:first_stop=day
            assert row['account_stopped']==(first_stop is not None);checked+=1
        complete=checked==len(account['daily'])
        if complete:
            assert account['status']=='COMPLETE_ACCOUNTING' and not holdings and not account['open_holdings']
            assert nav==D(account['ending_nav']) and first_stop==account['stop_date']
            pnl=sum((D(x['net_sale_proceeds'])-D(x['cost_basis']) for x in account['completed_positions']),D(0))
            pnl+=sum((D(c['amount']) for c in account['claims'] if c['type']=='dividend'),D(0))
            pnl+=sum((D(c['amount'])-D(c['originating_position_basis']) for c in account['claims'] if c['type']=='merger_cash'),D(0))
            assert pnl==nav-10000
        else:assert account['status']=='UNRESOLVED' and account['ending_nav'] is None
        reports.append(dict(account=name,status='RECONCILED_COMPLETE' if complete else 'RECONCILED_VALID_PREFIX_ONLY',nav_days_reconciled=checked,
                            total_days=len(account['daily']),fills_recomputed=len(account['fills']),halt_recomputed=first_stop))
    fit=json.loads((HERE/'fit-audit.json').read_text())
    for f in fit:
        assert f['training_last_month']<str(f['year'])+'-01'
        w=list(f['monthly_weight_sums'].values());assert max(w)-min(w)<1e-8
    out=dict(passed=True,accounts=reports,source_code_unchanged=True,annual_refit_cutoffs_and_equal_month_weights_checked=True)
    write(HERE/'account-verification.json',out);print(json.dumps(out,indent=2))

if __name__=='__main__':main()
