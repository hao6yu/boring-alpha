"""Fixed evaluation of already simulated earnings-language accounts.

No network, model fitting, price files, or report writes occur here. Public API:

``evaluate(accounts, expected_dates=..., benchmark_returns=None,
           expense_accounts=None, data_expense=None, sample_counts=None,
           upstream_ready=None)``

accounts and expense_accounts are {base|stress: {numeric|text|matched_event:
portfolio.simulate result}}. expected_dates is the independent calendar's exact
evaluation slice, not dates inferred from successful observations. Benchmark
returns are an optional date->decimal daily total-return mapping; no inner join
or deletion of missing dates is allowed. Outputs contain metrics/metadata, never
licensed prices, security positions, or individual daily return observations.

data_expense is {amount_usd, basis: quote|invoice|no_charge, source}. A nonzero
expense needs separately simulated accounts charged at account start. Subtracting
the expense from an existing terminal value is not an allowed substitute because
the fee can change integer positions. A quote is not labeled an invoice.

sample_counts keys: fit_2020, validation_2021, evaluation, evaluation_issuers.
upstream_ready may be bool or {ready: bool|null, reasons: [str]}. It describes
source/identity/readiness controls, not future outcomes used to select events.

Before actual returns, root accepted these precise conventions: 365-day CAGR and
effective cash rates over inclusive calendar dates; CAGR difference for the 1pp
advantage gate; bootstrap of 252*mean daily paired return difference; active
months contain a stock holding or actual fill, not merely an unpaid claim.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np


POLICY_SHA = '5c9daa1573ead42077ea323e641433c69112d6d3977f5e20c91d8bd1d04513bc'
COSTS, MODELS = ('base', 'stress'), ('numeric', 'text', 'matched_event')
COMPARISON_TOLERANCE = 1e-12


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if np.isfinite(result) else None


def _dates(values):
    values = list(values)
    if not values or values != sorted(set(values)):
        raise ValueError('expected dates must be nonempty, sorted and unique')
    for value in values:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('dates must be canonical YYYY-MM-DD')
    return values


def _policy():
    raw = Path(__file__).with_name('experiment-policy.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != POLICY_SHA:
        raise ValueError('experiment policy checksum changed')
    return json.loads(raw)


def _gate(name, value, details=None):
    return {'name': name, 'status': 'UNRESOLVED' if value is None else ('PASS' if value else 'FAIL'),
            'details': details}


def _combine(gates):
    statuses = [g['status'] for g in gates]
    if 'UNRESOLVED' in statuses:
        return 'UNRESOLVED'
    return 'PASS' if all(s == 'PASS' for s in statuses) else 'FAIL'


def stationary_bootstrap(differences):
    """Circular paired stationary bootstrap; fixed seed, blocks, and replicates.

    Vectorized over 2,000 replicates. Draw all initial indices, then for each
    subsequent observation draw 2,000 restart uniforms followed by 2,000 fresh
    indices (including unused fresh indices). Continue circularly otherwise.
    This states RNG consumption exactly. NumPy linear percentiles are used.
    The estimand is annualized arithmetic mean difference, not CAGR difference.
    """
    values = [_number(v) for v in differences]
    meta = {'method': 'circular_stationary_bootstrap', 'generator': 'PCG64',
            'seed': 20260910, 'expected_block_sessions': 20, 'replicates': 2000,
            'annualization_sessions': 252, 'confidence': .95,
            'percentile_method': 'linear', 'observations': len(values)}
    if len(values) < 2 or any(v is None for v in values):
        return {**meta, 'status': 'UNRESOLVED', 'estimate': None, 'lower': None, 'upper': None,
                'reason': 'Every paired daily observation is required; at least two are needed.'}
    x = np.asarray(values, dtype=float)
    rng = np.random.Generator(np.random.PCG64(20260910))
    indices = rng.integers(0, len(x), size=2000)
    totals = x[indices].copy()
    for _ in range(1, len(x)):
        restart = rng.random(2000) < .05
        fresh = rng.integers(0, len(x), size=2000)
        indices = np.where(restart, fresh, (indices+1) % len(x))
        totals += x[indices]
    draws = 252*totals/len(x)
    low, high = np.quantile(draws, [.025, .975], method='linear')
    return {**meta, 'status': 'COMPLETE', 'estimate': float(252*np.mean(x)),
            'lower': float(low), 'upper': float(high),
            'replicate_sha256': hashlib.sha256(draws.astype('<f8').tobytes()).hexdigest(),
            'limitation': 'Paired whole-account daily differences preserve contemporaneous pairing. '
                          'Circular time blocks approximate serial dependence; this is not an issuer-cluster '
                          'bootstrap or proof that the short historical sample is stationary.'}


def _account(result, dates, benchmark_returns):
    """Internal metrics plus a private return vector that never enters reports."""
    issues = []
    if not isinstance(result, dict):
        return {'status': 'UNRESOLVED', 'reasons': ['Account result missing.'], 'cagr': None,
                'max_drawdown_fraction': None, 'completed_positions': None, 'active_months': None,
                'stopped': None, 'daily_nav_complete': False}, None
    daily = result.get('daily', [])
    observed = [r.get('date') for r in daily]
    if observed != dates:
        issues.append('Daily rows do not exactly match independent expected dates in order.')
    if result.get('start') != dates[0] or result.get('end') != dates[-1]:
        issues.append('Account window does not match expected dates.')
    if result.get('policy_sha256') != POLICY_SHA:
        issues.append('Account policy checksum is missing or mismatched.')
    if result.get('status') != 'COMPLETE_ACCOUNTING':
        issues.append('Simulator reports unresolved accounting or candidate-source coverage.')
    if type(result.get('stopped')) is not bool:
        issues.append('Explicit account stop state is missing.')
    initial = _number(result.get('initial_capital'))
    if initial is None or initial <= 0:
        issues.append('Positive initial capital missing.')
    navs = [_number(r.get('nav')) for r in daily]
    if not navs or any(v is None for v in navs):
        issues.append('At least one daily NAV is missing or non-finite; no filling or row deletion is allowed.')
    elif any(v <= 0 for v in navs):
        issues.append('Nonpositive NAV makes the prescribed log/ratio annualization undefined.')
    if navs and navs[-1] is not None:
        reported_end = _number(result.get('ending_nav'))
        if reported_end is None or not np.isclose(reported_end, navs[-1], rtol=1e-12, atol=1e-8):
            issues.append('Reported ending NAV differs from daily ledger.')

    fills = result.get('fills', [])
    active = {f['date'][:7] for f in fills if f.get('date') in dates}
    stock_values, cash_values, claim_values = [], [], []
    for row in daily:
        stock = 0.0
        for holding in row.get('holdings', {}).values():
            q, px = _number(holding.get('quantity')), _number(holding.get('qualified_close'))
            if q is None or q < 0 or px is None or px <= 0:
                stock = None
                break
            stock += q*px
            if q > 0:
                active.add(row['date'][:7])
        cash, claims = _number(row.get('settled_cash')), _number(row.get('unpaid_claim_value'))
        stock_values.append(stock); cash_values.append(cash); claim_values.append(claims)
        nav = _number(row.get('nav'))
        if stock is None:
            issues.append('A held position has no qualified current valuation.')
        if all(x is not None for x in (stock, cash, claims, nav)) and not np.isclose(
                stock+cash+claims, nav, rtol=1e-12, atol=1e-7):
            issues.append('Daily cash, claims and holdings do not reconcile to NAV.')

    days = (date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days+1
    output = {'status': 'UNRESOLVED' if issues else 'COMPLETE', 'reasons': sorted(set(issues)),
              'daily_nav_complete': not issues, 'expected_sessions': len(dates),
              'observed_rows': len(daily), 'elapsed_calendar_days_inclusive': days,
              'initial_capital': initial, 'initial_expense': _number(result.get('initial_expense')),
              'ending_nav': navs[-1] if navs else None,
              'completed_positions': len(result.get('completed_positions', [])),
              'delayed_completed_positions': sum(x.get('delay_sessions', 0) > 0 for x in result.get('completed_positions', [])),
              'active_months': len(active), 'active_month_definition': 'Any stock holding or actual fill; claims alone do not count.',
              'open_stock_lots': len(result.get('open_holdings', {})),
              'unpaid_claims': sum(not c.get('paid', False) for c in result.get('claims', [])),
              'stopped': result.get('stopped'), 'cagr': None, 'total_return': None,
              'max_drawdown_fraction': None, 'max_drawdown_dollars': None,
              'annualized_mean_daily_return': None, 'annualized_daily_volatility': None,
              'annual_returns': {}, 'cash_comparisons': [], 'diagnostics': {}}
    for rate in (.04, .06):
        cash_end = initial*(1+rate)**(days/365) if initial is not None else None
        output['cash_comparisons'].append({'effective_annual_rate': rate,
            'initial_all_capital': initial, 'ending_value': cash_end,
            'account_minus_cash': None if issues or cash_end is None else navs[-1]-cash_end,
            'basis': 'Effective annual rate,365-day year,inclusive study dates; no study-data expense charged to cash comparator.'})
    if issues:
        return output, None
    y = np.asarray(navs)
    previous = np.r_[initial, y[:-1]]
    returns = y/previous-1
    for row, derived in zip(daily, returns):
        if 'daily_return' in row:
            supplied = _number(row['daily_return'])
            if supplied is None or not np.isclose(supplied, derived, rtol=1e-9, atol=1e-11):
                output['status'] = 'UNRESOLVED'; output['daily_nav_complete'] = False
                output['reasons'].append('Supplied daily return differs from consecutive NAV accounting.')
                for cash_row in output['cash_comparisons']: cash_row['account_minus_cash'] = None
                return output, None
    peaks = np.maximum.accumulate(np.r_[initial, y])[1:]
    output.update(cagr=float((y[-1]/initial)**(365/days)-1), total_return=float(y[-1]/initial-1),
                  max_drawdown_fraction=float(np.max((peaks-y)/peaks)),
                  max_drawdown_dollars=float(np.max(peaks-y)),
                  annualized_mean_daily_return=float(252*np.mean(returns)),
                  annualized_daily_volatility=float(np.std(returns, ddof=1)*np.sqrt(252)) if len(y)>1 else None)
    for year in sorted({d[:4] for d in dates}):
        indices = [i for i,d in enumerate(dates) if d.startswith(year)]
        i, j = indices[0], indices[-1]
        output['annual_returns'][year] = {'first_session': dates[i], 'last_session': dates[j],
            'opening_nav': float(previous[i]), 'ending_nav': float(y[j]),
            'net_return': float(y[j]/previous[i]-1), 'capital_reset': False,
            'scope': 'Observed calendar-year portion; not annualized.'}
    diagnostics = output['diagnostics']
    for name, values in [('stock_exposure',stock_values), ('claim_exposure',claim_values), ('settled_cash_fraction',cash_values)]:
        if all(v is not None for v in values):
            ratios = np.asarray(values)/y
            diagnostics[name] = {'mean':float(np.mean(ratios)), 'maximum':float(np.max(ratios)),
                                 'basis':'End-of-day asset value / same-day NAV.'}
        else:
            diagnostics[name] = None
    notional = [(_number(f.get('quantity')), _number(f.get('raw_close'))) for f in fills]
    if all(q is not None and p is not None and q > 0 and p > 0 for q,p in notional):
        traded = sum(q*p for q,p in notional)
        diagnostics['turnover'] = {'two_sided_reference_notional':traded,
            'ratio_to_mean_daily_nav':float(traded/np.mean(y)),
            'annualized_ratio':float(traded/np.mean(y)*365/days),
            'basis':'Sum of buy and sell quantities*raw reference close / mean end-of-day NAV; not half-turnover.'}
    else:
        diagnostics['turnover'] = None
    diagnostics['trading_costs'] = {}
    for name, field in [('fees','fee_total'), ('slippage','slippage_cost')]:
        values = [_number(f.get(field)) for f in fills]
        diagnostics['trading_costs'][name] = sum(values) if all(v is not None for v in values) else None
    benchmark = [_number(benchmark_returns.get(d)) for d in dates] if benchmark_returns is not None else []
    if len(benchmark) == len(dates) and all(x is not None for x in benchmark) and len(benchmark)>1:
        b = np.asarray(benchmark); centered = b-b.mean(); denom = np.dot(centered,centered)
        diagnostics['beta'] = float(np.dot(returns-returns.mean(),centered)/denom) if denom>0 else None
        diagnostics['beta_status'] = 'COMPLETE' if denom>0 else 'ZERO_BENCHMARK_VARIANCE'
    else:
        diagnostics['beta'] = None
        diagnostics['beta_status'] = 'BENCHMARK_MISSING_OR_INCOMPLETE_NO_DATE_FILTERING'
    return output, returns


def account_metrics(result, *, expected_dates, benchmark_returns=None):
    """Metric-only view for one account; does not publish return vectors."""
    return _account(result, _dates(expected_dates), benchmark_returns)[0]


def _suite(accounts, dates, benchmark_returns, expected_expense):
    metrics, vectors, gates, comparisons = {}, {}, [], {}
    for cost in COSTS:
        metrics[cost], vectors[cost] = {}, {}
        for name in MODELS:
            source = accounts.get(cost, {}).get(name) if isinstance(accounts, dict) else None
            metric, vector = _account(source, dates, benchmark_returns)
            metrics[cost][name], vectors[cost][name] = metric, vector
            valid_cost = isinstance(source, dict) and source.get('cost_case') == cost
            valid_rank = isinstance(source, dict) and source.get('rank_mode') == ('matched' if name=='matched_event' else 'score')
            valid_capital = isinstance(source, dict) and _number(source.get('initial_capital')) == 5000
            expense = _number(source.get('initial_expense')) if isinstance(source, dict) else None
            valid_expense = expense is not None and expected_expense is not None and abs(expense-expected_expense) < 1e-9
            ready = metric['status']=='COMPLETE' and valid_cost and valid_rank and valid_capital and valid_expense
            gates.append(_gate(cost+':'+name+':qualified_account', True if ready else None,
                               {'source_complete':metric['status']=='COMPLETE','cost_case_matches':valid_cost,
                                'ranking_mode_matches':valid_rank,'capital_matches':valid_capital,
                                'initial_expense_matches':valid_expense}))
            if not ready: vectors[cost][name] = None
        t,n,b = (metrics[cost][name] for name in ('text','numeric','matched_event'))
        complete = all(vectors[cost][name] is not None for name in MODELS)
        advantage = t['cagr']-n['cagr'] if complete else None
        comparisons[cost] = {'annualized_net_text_minus_numeric_cagr':advantage,
            'text_minus_matched_event_cagr':t['cagr']-b['cagr'] if complete else None,
            'paired_annualized_mean_daily_difference':float(252*np.mean(vectors[cost]['text']-vectors[cost]['numeric'])) if complete else None}
        gates.extend([
            _gate(cost+':text_cagr_above_6pct', t['cagr']>.06+COMPARISON_TOLERANCE if complete else None),
            _gate(cost+':text_advantage_at_least_1pp', advantage>=.01-COMPARISON_TOLERANCE if complete else None),
            _gate(cost+':text_cagr_above_matched_event', t['cagr']>b['cagr']+COMPARISON_TOLERANCE if complete else None),
            _gate(cost+':at_least_40_completed_positions', t['completed_positions']>=40 if complete else None),
            _gate(cost+':at_least_12_active_months', t['active_months']>=12 if complete else None),
            _gate(cost+':max_drawdown_at_most_20pct', t['max_drawdown_fraction']<=.20+COMPARISON_TOLERANCE if complete else None),
            _gate(cost+':no_account_stop', t['stopped'] is False if complete else None)])
    base_complete = all(vectors['base'][name] is not None for name in ('text','numeric'))
    bootstrap = stationary_bootstrap(vectors['base']['text']-vectors['base']['numeric']) if base_complete else stationary_bootstrap([])
    gates.append(_gate('base:paired_bootstrap_lower_bound_positive', bootstrap['lower']>COMPARISON_TOLERANCE if bootstrap['status']=='COMPLETE' else None))
    return {'status':_combine(gates),'accounts':metrics,'comparisons':comparisons,'bootstrap':bootstrap,'gates':gates}


def evaluate(accounts, *, expected_dates, benchmark_returns=None, expense_accounts=None,
             data_expense=None, sample_counts=None, upstream_ready=None):
    """Evaluate both costs and baselines, preserving every missing-data failure."""
    policy = _policy(); dates = _dates(expected_dates)
    trading = _suite(accounts, dates, benchmark_returns, 0)
    expense = _number(data_expense.get('amount_usd')) if isinstance(data_expense,dict) else None
    expense_known = (expense is not None and expense>=0 and isinstance(data_expense,dict)
                     and data_expense.get('basis') in ('quote','invoice','no_charge')
                     and bool(data_expense.get('source'))
                     and (data_expense.get('basis')!='no_charge' or expense==0))
    if expense_known and expense==0 and expense_accounts is None:
        expense_accounts = accounts
    with_expense = _suite(expense_accounts, dates, benchmark_returns, expense if expense_known else None)
    metadata_gates = [_gate('full_frozen_evaluation_window', True if dates[0]==policy['evaluation_start'] and dates[-1]==policy['evaluation_end'] else None),
                      _gate('dedicated_data_expense_declared', True if expense_known else None)]
    readiness = upstream_ready.get('ready') if isinstance(upstream_ready,dict) else upstream_ready
    reasons = upstream_ready.get('reasons',[]) if isinstance(upstream_ready,dict) else []
    metadata_gates.append(_gate('upstream_source_identity_readiness', readiness if type(readiness) is bool else None, reasons))
    for key, minimum in [('fit_2020',200),('validation_2021',100),('evaluation',200),('evaluation_issuers',40)]:
        count = sample_counts.get(key) if isinstance(sample_counts,dict) else None
        metadata_gates.append(_gate('sample_count:'+key, count>=minimum if type(count) is int and count>=0 else None,
                                   {'observed':count,'minimum':minimum}))
    overall_gates = metadata_gates+[_gate('trading_only_performance', None if trading['status']=='UNRESOLVED' else trading['status']=='PASS'),
                                   _gate('after_data_expense_performance', None if with_expense['status']=='UNRESOLVED' else with_expense['status']=='PASS')]
    return {'status':_combine(overall_gates), 'policy_sha256':POLICY_SHA,
            'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'numpy_version':np.__version__, 'expected_dates_sha256':hashlib.sha256('\n'.join(dates).encode()).hexdigest(),
            'metadata':{'cagr_year_days':365,'calendar_day_interval':'inclusive start through end',
                        'fractional_return_comparison_tolerance':COMPARISON_TOLERANCE,
                        'bootstrap_estimand':'252*mean(text daily net return - numeric daily net return)',
                        'advantage_gate_estimand':'text net CAGR minus numeric net CAGR',
                        'data_expense':data_expense,'expense_treatment':'Separate initial-expense account reruns; no terminal subtraction.',
                        'capital_basis':'$5,000 original capital for accounts and both effective4/6% cash comparisons.',
                        'outcome_filtering':'None; exact independent dates and all required accounts are retained.',
                        'interpretation':'Passing is exploratory evidence, not funding approval. Unknown measures stay null.'},
            'trading_only':trading,'after_data_expense':with_expense,'gates':overall_gates}
