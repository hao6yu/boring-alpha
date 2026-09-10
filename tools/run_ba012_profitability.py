#!/usr/bin/env python3
"""Causal, continuous covered-window parent-exposure diagnostic. No order API."""
from __future__ import annotations
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import platform
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ba012_sizing as policy
import ba012_transition as transition

HERE = ROOT / 'research/ba012-profitability/traded-v1'
PLAN_HASH = 'a9da9a602bcebca0653de7c4eb1259f8464dee4b1593d5fd4da129440d45c6cb'
SENS = np.array([.5,100,12500,1,5])
STRESS_COST = np.array(policy.EXECUTION,dtype=float)/policy.MONEY_SCALE
INITIAL_LONG = np.array(policy.INITIAL_LONG,dtype=float)/policy.MONEY_SCALE
INITIAL_SHORT = np.array(policy.INITIAL_SHORT,dtype=float)/policy.MONEY_SCALE
MAINT_LONG = np.array(policy.MAINTENANCE_LONG,dtype=float)/policy.MONEY_SCALE
MAINT_SHORT = np.array(policy.MAINTENANCE_SHORT,dtype=float)/policy.MONEY_SCALE
SHOCK = np.array(policy.SHOCK,dtype=float)/policy.MONEY_SCALE
ZERO = [0]*5


def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sign(p): return np.sign(p).astype(int).tolist()
def rawprice(value):
    if value is None: return None
    if isinstance(value,dict):
        value=value.get('price',value.get('close'))
    return None if value is None else float(value)


def hard_violations(terminal):
    # These limits apply to every partial state. Basket composition applies
    # only to the completed target and can be repaired by a valid reduction.
    return [v for v in terminal['violations'] if v not in ('concentration','diversification')]


class Unresolved(Exception):
    def __init__(self, message, category='implementation'):
        super().__init__(message)
        self.category=category


class Account:
    def __init__(self, capital, cost, window):
        self.initial=self.equity=self.high=float(capital)
        self.budget=capital*.2
        self.unitcost=np.array(cost,dtype=float)
        self.window=window
        self.p=np.zeros(5,dtype=int)
        self.symbols=[None]*5
        self.marks=[None]*5
        self.gross=np.zeros(5)
        self.costs=np.zeros(5)
        self.fees=0.
        self.halted=False
        self.halt_reason=None
        self.events=[]
        self.executions=[]
        self.decisions=[]
        self.daily=[]
        self.max_dd=self.max_dd_frac=0.
        self.min_funding=float('inf')
        self.nodes=0
        self.active_date=''
        self.peak_gross_contracts=0

    def terminal(self,sigma,p=None,equity=None,high=None):
        p=self.p if p is None else np.asarray(p,dtype=int)
        equity=self.equity if equity is None else equity
        high=self.high if high is None else high
        n=np.abs(p); violations=[]
        vol=np.sqrt(np.diag(sigma)); risk=float(np.sqrt(max(0,p@sigma@p)))
        if np.any(p):
            if len({policy.GROUPS[i] for i in range(5) if p[i]})<3 or np.count_nonzero(p)<3: violations.append('diversification')
            stand=n*vol
            if 2*max(stand)>sum(stand)+1e-9: violations.append('concentration')
        if risk>.08*equity+1e-8: violations.append('forecast_risk')
        reserve=float(n@STRESS_COST); stress=float(n@SHOCK)
        if max(0,high-equity)+stress+reserve>self.budget+1e-8: violations.append('stress_budget')
        margin=float(n@np.where(p>=0,MAINT_LONG,MAINT_SHORT))
        funding=equity-stress-reserve-2*margin-100
        if funding < -1e-8: violations.append('stressed_funding')
        return {'feasible':not violations,'violations':violations,'risk_usd':risk,'funding_headroom_usd':funding,'maintenance_usd':margin}

    def event(self, phase, extra=None):
        self.high=max(self.high,self.equity)
        dd=self.high-self.equity
        self.max_dd=max(self.max_dd,dd)
        self.max_dd_frac=max(self.max_dd_frac,dd/self.high)
        maintenance=float(np.abs(self.p)@np.where(self.p>=0,MAINT_LONG,MAINT_SHORT))
        if dd>self.budget+1e-8 or self.equity<maintenance-1e-8:
            self.halted=True
            self.halt_reason=self.halt_reason or ('drawdown_budget' if dd>self.budget+1e-8 else 'maintenance')
        self.peak_gross_contracts=max(self.peak_gross_contracts,int(np.abs(self.p).sum()))
        value={'date':self.active_date,'phase':phase,'equity':self.equity,'high_water':self.high,
            'drawdown':dd,'quantities':self.p.tolist(),'symbols':self.symbols.copy(),'halted':self.halted}
        if extra:value.update(extra)
        self.events.append(value)

    def mark(self, prices, phase):
        moves=np.zeros(5)
        next_marks=self.marks.copy()
        for i,n in enumerate(self.p):
            if n:
                price=rawprice(prices.get(self.symbols[i]))
                if price is None:
                    raise Unresolved(f'{self.active_date} {phase}: missing held mark {self.symbols[i]}','held_valuation_data')
                if not np.isfinite(price) or price<=0:raise Unresolved('invalid held price','held_valuation_data')
                assert self.marks[i] is not None
                moves[i]=n*SENS[i]*(price-self.marks[i]); next_marks[i]=price
        self.marks=next_marks
        self.gross+=moves; self.equity+=float(moves.sum())
        self.event(phase,{'gross_pnl_by_market':moves.tolist()})

    def fill(self, target, prices, symbols, phase):
        # All required held marks and committed fill observations must resolve.
        for i in range(5):
            if int(target[i])!=self.p[i]:
                sym=self.symbols[i] if self.p[i] else symbols[i]
                if rawprice(prices.get(sym)) is None:
                    raise Unresolved(f'{self.active_date} {phase}: missing committed fill {sym}','committed_fill_data')
        self.mark(prices,phase+'_pre_fill')
        for i,value in enumerate(target):
            value=int(value); old=int(self.p[i]); delta=value-old
            if not delta:continue
            assert not old or not value or np.sign(old)==np.sign(value)
            sym=self.symbols[i] if old else symbols[i]
            price=rawprice(prices.get(sym)); cost=abs(delta)*self.unitcost[i]
            self.p[i]=value; self.costs[i]+=cost; self.equity-=cost
            self.symbols[i]=sym if value else None
            self.marks[i]=price if value else None
            self.executions.append({'date':self.active_date,'phase':phase,'market':policy.SYMBOLS[i],
                'symbol':sym,'old_quantity':old,'new_quantity':value,'signed_quantity':delta,
                'raw_parent_price':price,'inclusive_cost_usd':cost})
            self.event(phase+'_fill',{'market':policy.SYMBOLS[i],'inclusive_cost_usd':cost})

    def optimize(self,sigma,signs,upper=None,lower=None,roll=None,reduction=False):
        if self.equity<=0:raise Unresolved('nonpositive equity requires protective liquidation')
        args={'roll_mask':roll,'component_upper_bound':upper,'reduction_only':reduction,'max_nodes':2_000_000}
        if lower is not None:args['component_lower_bound']=lower
        result=transition.optimize_transition(sigma,signs,self.equity,self.high,self.budget,self.p.tolist(),**args)
        self.nodes+=result.get('search',{}).get('nodes',0)
        if result['status']=='SEARCH_LIMIT':raise Unresolved('transition optimization SEARCH_LIMIT','solver_limit')
        if result.get('quantities') is None:return None,result
        return np.asarray(result['quantities'],dtype=int),result


def bars(day,minute,field):
    return {symbol:None if b.get(minute) is None else b[minute].get(field)
        for symbol,b in day['execution_bars'].items()}


def monthly_plan(account,seed,nextday,signs,sigma):
    if account.halted:return np.zeros(5,dtype=int), {'status':'HALTED'}
    t=account.terminal(sigma)
    if hard_violations(t) and np.any(account.p):return np.zeros(5,dtype=int), {'status':'PROTECTIVE_FLAT','violations':t['violations']}
    roll=[bool(m['is_roll']) and bool(account.p[i]) for i,m in enumerate(nextday['markets'])]
    upper=np.ceil(np.sqrt(2)*.08*account.equity/np.sqrt(np.diag(sigma))).astype(int).tolist()
    for i in range(5):
        if roll[i]:upper[i]=abs(int(account.p[i]))
    target,result=account.optimize(sigma,signs,upper=upper,roll=roll)
    if target is None:return np.zeros(5,dtype=int),dict(result,protection_required=True)
    return target,result


def run_account(bundle,plan,capital,cost_case,window):
    account=Account(capital,plan[cost_case+'_execution_cost_per_unit_usd'],window)
    days=[d for d in bundle['days'] if window['start_inclusive']<=d['date_chicago']<window['end_exclusive']]
    assert len(days)==window['joint_sessions']
    assert days[-1]['date_chicago']==window['boundary_liquidation_date']
    instructions=0; protected=0; planq=None; planmeta={}; unresolved=None; unresolved_category=None
    protection_committed_after_settlement=False
    pending_daily_reduction_cap=None
    monthly_signs=bundle['seed']['signs']
    prev_sigma=np.array(bundle['seed']['sigma_after_1630'],dtype=float)
    account.active_date=bundle['seed']['date_chicago']
    try:
        planq,planmeta=monthly_plan(account,bundle['seed'],days[0],monthly_signs,prev_sigma)
        for index,day in enumerate(days):
            account.active_date=day['date_chicago']
            sigma=np.array(day['sigma_before_1000'],dtype=float)
            assert np.allclose(prev_sigma,sigma,rtol=1e-11,atol=1e-10)
            newmonth=day['first_joint_of_month']
            isfinal=index==len(days)-1
            if newmonth:
                account.equity-=plan['monthly_data_fee_usd'];account.fees+=plan['monthly_data_fee_usd']
                account.event('monthly_data_fee',{'fee':plan['monthly_data_fee_usd']})
                monthly_signs=day['signs'];instructions+=1
            account.mark(day['reference_1000'],'10:00_reference')
            held_before=account.p.copy()
            roll=[bool(m['is_roll']) and bool(account.p[i]) for i,m in enumerate(day['markets'])]
            active=[m['active_parent_raw_symbol'] for m in day['markets']]
            existing=account.terminal(sigma)
            mandatory=bool(isfinal or account.halted or protection_committed_after_settlement or (np.any(account.p) and bool(hard_violations(existing))))
            reason=('boundary_liquidation' if isfinal else 'halt' if account.halted else
                'previous_settlement_constraint_breach' if protection_committed_after_settlement else
                'existing_constraint_breach' if mandatory else None)
            protection_committed_after_settlement=False
            result={}
            if mandatory:
                target=np.zeros(5,dtype=int);protected+=int(not isfinal)
            elif newmonth:
                if planq is None:raise Unresolved('preceding monthly plan unresolved')
                upper=np.abs(planq).tolist()
                for i,sym in enumerate(active):
                    # Absent NEW precommit prices block that addition; a held
                    # mark was already required above and cannot be substituted.
                    if rawprice(day['reference_1000'].get(sym)) is None:upper[i]=0
                    if roll[i]:upper[i]=min(upper[i],abs(int(held_before[i])))
                target,result=account.optimize(sigma,monthly_signs,upper=upper,roll=roll)
                if target is None:
                    target=np.zeros(5,dtype=int);mandatory=True;reason='no_feasible_optional_monthly_transition';protected+=1
            else:
                target=account.p.copy()
                # Forced roll replacement is allowed but cannot increase a sleeve.
                if any(roll) or not existing['feasible'] or pending_daily_reduction_cap is not None:
                    upper=np.abs(account.p).tolist()
                    if pending_daily_reduction_cap is not None:
                        upper=[min(a,b) for a,b in zip(upper,pending_daily_reduction_cap)]
                    for i,sym in enumerate(active):
                        if rawprice(day['reference_1000'].get(sym)) is None:upper[i]=0
                    target,result=account.optimize(sigma,sign(account.p),upper=upper,roll=roll,reduction=True)
                    if target is None:
                        target=np.zeros(5,dtype=int);mandatory=True;reason='no_feasible_roll_transition';protected+=1
            pending_daily_reduction_cap=None
            target=np.array(target,dtype=int)
            if mandatory:
                retained=np.zeros(5,dtype=int)
            else:
                retained=np.array([0 if roll[i] or np.sign(target[i])!=np.sign(account.p[i]) else
                    int(np.sign(account.p[i])*min(abs(account.p[i]),abs(target[i]))) for i in range(5)])
            decision={'date':account.active_date,'monthly':newmonth,'signal_date':day['monthly_signal_date'],
                'sigma_through':day['previous_joint_date_chicago'],'starting_quantities':held_before.tolist(),
                'committed_terminal_target_1000':target.tolist(),'retained_after_exits':retained.tolist(),
                'roll_mask':roll,'mandatory':mandatory,'reason':reason,'search':result.get('search')}
            if np.any(retained!=account.p):
                account.fill(retained,bars(day,'10:01','open'),active,'10:01_exit')
            account.mark(bars(day,'10:01','close'),'10:02_recheck')
            entered=False; unwind=False
            if not mandatory and np.any(target!=retained):
                if account.halted:
                    unwind=True;remaining=None
                else:
                    upper=np.abs(target).tolist()
                    closing=bars(day,'10:01','close')
                    for i,sym in enumerate(active):
                        if rawprice(closing.get(sym)) is None:upper[i]=abs(int(account.p[i]))
                    remaining,result2=account.optimize(sigma,monthly_signs if newmonth else sign(target),
                        upper=upper,lower=np.abs(account.p).tolist())
                    decision['entry_search']=result2.get('search')
                if remaining is None:
                    unwind=unwind or not account.terminal(sigma)['feasible']
                    decision['remaining_additions']='NONE_FEASIBLE'
                else:
                    decision['committed_target_1002']=remaining.tolist()
                    if np.any(remaining!=account.p):
                        account.fill(remaining,bars(day,'10:03','open'),active,'10:03_entry');entered=True
            elif not mandatory and np.any(account.p):
                # An adverse exit fill can invalidate the completed reduced basket.
                unwind=not account.terminal(sigma)['feasible'] or account.halted
            account.mark(bars(day,'10:03','close'),'10:04_batch_check')
            term=account.terminal(sigma)
            initial=float(np.abs(account.p)@np.where(account.p>=0,INITIAL_LONG,INITIAL_SHORT))
            funding=account.equity-float(np.abs(account.p)@(SHOCK+STRESS_COST))-2*initial-100
            initial_failure=entered and funding < -1e-8
            unwind=unwind or account.halted or not term['feasible'] or initial_failure
            decision['completed_batch_violations']=term['violations']+(['initial_funding'] if initial_failure else [])
            if unwind and np.any(account.p):
                protected+=1;decision['protective_unwind_1005']=True
                account.fill(ZERO,bars(day,'10:05','open'),active,'10:05_protective_unwind')
            account.decisions.append(decision)
            account.mark(day['settlement_1630'],'16:30_settlement_reference')
            sigma_end=np.array(day['sigma_after_1630'],dtype=float)
            term=account.terminal(sigma_end)
            protection_committed_after_settlement=bool(np.any(account.p) and hard_violations(term))
            if (index+1<len(days) and not day['last_joint_of_month'] and np.any(account.p)
                    and not term['feasible'] and not protection_committed_after_settlement):
                next_roll=[bool(m['is_roll']) and bool(account.p[i]) for i,m in enumerate(days[index+1]['markets'])]
                reduction,reduction_result=account.optimize(sigma_end,sign(account.p),
                    upper=np.abs(account.p).tolist(),roll=next_roll,reduction=True)
                if reduction is None:
                    protection_committed_after_settlement=True
                else:
                    pending_daily_reduction_cap=np.abs(reduction).tolist()
                account.decisions.append({'date':account.active_date,'phase':'16:30_daily_reduction_plan',
                    'quantities':None if reduction is None else reduction.tolist(),'status':reduction_result['status'],
                    'search':reduction_result.get('search')})
            account.min_funding=min(account.min_funding,term['funding_headroom_usd'])
            account.daily.append({'date':account.active_date,'equity':account.equity,'quantities':account.p.tolist(),
                'symbols':account.symbols.copy(),'high_water':account.high,'drawdown':account.high-account.equity,
                'halted':account.halted,'terminal':term})
            if index+1<len(days) and day['last_joint_of_month']:
                monthly_signs=day['monthly_after_1630_signs']
                planq,planmeta=monthly_plan(account,day,days[index+1],monthly_signs,sigma_end)
                account.decisions.append({'date':account.active_date,'phase':'16:30_monthly_plan',
                    'signs':monthly_signs,'quantities':None if planq is None else planq.tolist(),
                    'status':planmeta.get('status'),'search':planmeta.get('search')})
            prev_sigma=sigma_end
    except Unresolved as exc:
        unresolved=str(exc);unresolved_category=exc.category
    reconciled=account.initial+account.gross.sum()-account.costs.sum()-account.fees
    assert abs(reconciled-account.equity)<1e-6, (reconciled,account.equity)
    complete=unresolved is None and len(account.daily)==len(days) and not np.any(account.p)
    elapsed=(date.fromisoformat(window['end_exclusive'])-date.fromisoformat(window['start_inclusive'])).days
    summary={'status':'COMPLETE_DIAGNOSTIC' if complete else 'UNRESOLVED','unresolved_reason':unresolved,
        'unresolved_category':unresolved_category,
        'capital':capital,'cost_case':cost_case,'window':window,'completed_joint_days':len(account.daily),
        'ending_equity':account.equity if complete else None,'partial_marked_equity':account.equity,
        'gross_trading_pnl':float(account.gross.sum()),'execution_costs':float(account.costs.sum()),
        'data_fees':account.fees,'net_pnl':account.equity-capital if complete else None,
        'cagr':(account.equity/capital)**(365/elapsed)-1 if complete and account.equity>0 else None,
        'total_return':account.equity/capital-1 if complete else None,
        'max_marked_drawdown_usd':account.max_dd,'max_marked_drawdown_fraction':account.max_dd_frac,
        'fixed_loss_budget_usd':account.budget,'halted':account.halted,'halt_reason':account.halt_reason,
        'execution_events':len(account.executions),'contract_sides':sum(abs(x['signed_quantity']) for x in account.executions),
        'nonzero_eod_days':sum(any(x['quantities']) for x in account.daily),
        'minimum_eod_stressed_funding_headroom':account.min_funding if account.daily else None,
        'monthly_instructions':instructions,'protective_batches':protected,'total_solver_nodes':account.nodes,
        'gross_pnl_by_market':dict(zip(policy.SYMBOLS,account.gross.tolist())),
        'execution_costs_by_market':dict(zip(policy.SYMBOLS,account.costs.tolist())),
        'cash_comparisons':[{'annual_rate':rate,'ending_value':capital*(1+rate)**(elapsed/365),
            'strategy_minus_cash':account.equity-capital*(1+rate)**(elapsed/365) if complete else None}
            for rate in [.04,.06]],
        'economic_gate_pass':bool(complete and account.equity>0 and (account.equity/capital)**(365/elapsed)-1>.06 and
            not account.halted and account.max_dd<=account.budget+1e-8),
        'calendar_days':elapsed,'events':account.events,'executions':account.executions,
        'decisions':account.decisions,'daily_ledger':account.daily}
    annual=[];opening=capital
    for year in sorted({d['date'][:4] for d in account.daily}):
        rows=[d for d in account.daily if d['date'].startswith(year)];closing=rows[-1]['equity']
        annual.append({'year':year,'opening_equity':opening,'closing_equity':closing,'pnl':closing-opening,
            'return_fraction':closing/opening-1,'joint_days':len(rows)})
        opening=closing
    summary['annual_periods']=annual
    return summary


def main():
    plan_path=HERE/'plan.json';assert digest(plan_path)==PLAN_HASH
    plan=json.loads(plan_path.read_text())
    for s in plan['sources']:assert digest(ROOT/s['path'])==s['sha256'],s['path']
    source=ROOT/'research/ba012-profitability/traded-inputs-v1.json'
    assert digest(source)==source.with_suffix('.json.sha256').read_text().split()[0]
    bundle=json.loads(source.read_text())
    assert bundle['schema']=='ba012-traded-inputs-v1' and not bundle['strategy_pnl_calculated']
    implementation={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'tools/ba012_transition.py',source]}
    runtime={'python':sys.version,'numpy':np.__version__,'platform':platform.platform()}
    freeze={'registered_at_utc':datetime.now(timezone.utc).isoformat(),'implementation':implementation,'runtime':runtime,'plan_sha256':PLAN_HASH}
    with (HERE/'implementation-freeze.json').open('x') as f:json.dump(freeze,f,sort_keys=True,indent=2);f.write('\n')
    records=[]
    for capital in plan['capitals_usd']:
        for case in plan['cost_cases']:
            result=run_account(bundle,plan,capital,case,plan['primary'])
            tag=f'{capital}-{case}-primary';dest=HERE/(tag+'.json')
            with dest.open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
            dest.with_suffix('.json.sha256').write_text(digest(dest)+'  '+dest.name+'\n')
            compact={k:v for k,v in result.items() if k not in ['events','executions','decisions','daily_ledger']}
            records.append({'name':tag,'sha256':digest(dest),'summary':compact});print(json.dumps({'name':tag,**compact}),flush=True)
            if result['status']=='UNRESOLVED' and result['unresolved_category'] in ('held_valuation_data','committed_fill_data'):
                fallback=run_account(bundle,plan,capital,case,plan['data_only_fallback'])
                tag=f'{capital}-{case}-coverage-prefix';dest=HERE/(tag+'.json')
                with dest.open('x') as f:json.dump(fallback,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
                dest.with_suffix('.json.sha256').write_text(digest(dest)+'  '+dest.name+'\n')
                compact={k:v for k,v in fallback.items() if k not in ['events','executions','decisions','daily_ledger']}
                records.append({'name':tag,'sha256':digest(dest),'summary':compact});print(json.dumps({'name':tag,**compact}),flush=True)
    for name,sha in implementation.items():assert digest(ROOT/name)==sha,name
    output={'schema':'ba012-covered-traded-profitability-results-v1','label':plan['label'],'plan_sha256':PLAN_HASH,
        'implementation':implementation,'runtime':runtime,'results':records,'holdout_prices_read':False,'live_orders_submitted':False,
        'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    dest=HERE/'summary.json'
    with dest.open('x') as f:json.dump(output,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    dest.with_suffix('.json.sha256').write_text(digest(dest)+'  '+dest.name+'\n')

if __name__=='__main__':main()
