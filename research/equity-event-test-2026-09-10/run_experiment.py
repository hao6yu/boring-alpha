"""Freeze development models and then evaluate their fixed historical signals.

This command never downloads, trades or chooses new strategy parameters. A
source-readiness record must be completed from actual audits before fitting.
Provider-derived panels, forecasts and account ledgers stay in ignored storage.
"""
import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import subprocess

import exchange_calendars as xcals
import joblib
import numpy as np

from evaluation_metrics import evaluate
from model import select_and_refit, policy, POLICY_SHA
from panel import ROOT, HERE, RAW, calendar, digest, load_prices, target, write
from portfolio import simulate
from price_data import symbol

CODE = ['model.py', 'panel.py', 'price_data.py', 'feature_extract.py', 'portfolio.py', 'evaluation_metrics.py', 'run_experiment.py']
BOUND_INPUTS = ['source-readiness.json', 'panel-inventory.json', 'corporate-action-evidence.json',
                'data-expense.json', 'tiingo-directory-source.json', 'price-source-exceptions.json']


def now():
    return datetime.now(timezone.utc).isoformat()


def code_hashes():
    return {name: digest(HERE / name) for name in CODE}


def session_schedule(sessions):
    cal = xcals.get_calendar('XNYS')
    return {d: {'open': cal.session_open(d).isoformat(), 'close': cal.session_close(d).isoformat()}
            for d in sessions}


def runtime_provenance(sessions):
    schedule = session_schedule(sessions)
    return {'versions': {name: version(name) for name in ['numpy', 'scikit-learn', 'joblib', 'exchange-calendars']},
            'session_schedule_sha256': hashlib.sha256(json.dumps(schedule,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'sessions': len(sessions)}


def bound_inputs():
    # Action kind/payment evidence and data expenses affect the account path.
    return {name: digest(HERE/name) for name in BOUND_INPUTS}


def private_path(path):
    """Fail before putting provider-derived content outside ignored raw storage."""
    path = path.resolve()
    if not path.is_relative_to(RAW.resolve()):
        raise ValueError('Provider-derived artifacts must remain under the registered raw directory')
    checked = subprocess.run(['git','check-ignore','--quiet','--no-index',str(path)],cwd=ROOT,
                             capture_output=True,check=False)
    if checked.returncode != 0:
        raise ValueError('Provider-derived artifact path is not git-ignored')
    return path


def unique_events(rows, label):
    ids = [r['event_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(label+' contains duplicate event IDs')
    return set(ids)


def checked_forecasts(pool, rows):
    if unique_events(pool,'Pool') != unique_events(rows,'Forecasts'):
        raise ValueError('Forecasts do not match the complete frozen pool')
    forecasts = {r['event_id']: r for r in rows}
    for row in pool:
        other = forecasts[row['event_id']]
        if any(other[k] != row[k] for k in ['cik','entry_date','exit_date']):
            raise ValueError('Forecast timing or issuer differs from the frozen pool')
        if any(not math.isfinite(float(other[k])) for k in ['numeric','text']):
            raise ValueError('Non-finite frozen forecast')
    return forecasts


def checked_pool_timing(pool, sessions):
    """Require the panel horizon to equal the simulator's source-date horizon."""
    for row in pool:
        available = max(row['filing_date'],row['acceptance_date_et'])
        i = bisect_right(sessions,available)
        if (i+20 >= len(sessions) or row['entry_date'] != sessions[i] or
                row['exit_date'] != sessions[i+20]):
            raise ValueError('Frozen panel dates differ from the source-date execution horizon')


def freeze():
    """No evaluation targets are available to this phase."""
    spec = policy()
    frozen_path = HERE / 'frozen-models.json'
    if frozen_path.exists():
        raise ValueError('Models are already frozen; do not silently refit or overwrite them')
    readiness_path = HERE / 'source-readiness.json'
    readiness = json.loads(readiness_path.read_text())
    if readiness.get('ready') is not True or readiness.get('policy_sha256') != POLICY_SHA:
        raise ValueError('Actual source audits and coverage have not cleared model fitting')
    inventory_path = HERE / 'panel-inventory.json'
    inventory = json.loads(inventory_path.read_text())
    if readiness['panel_inventory_sha256'] != digest(inventory_path):
        raise ValueError('Readiness audit covers a different data panel')
    if (inventory['price_manifest_sha256'] != digest(HERE/'price-manifest.json') or
            inventory['price_source_exceptions_sha256'] != digest(HERE/'price-source-exceptions.json') or
            inventory['panel_code_sha256'] != digest(HERE/'panel.py') or
            inventory['feature_code_sha256'] != digest(HERE/'feature_extract.py')):
        raise ValueError('Panel source or extraction implementation changed before fitting')
    if not inventory['minimum_development_pass'] or not inventory['minimum_evaluation_preentry_pass']:
        raise ValueError('Frozen minimum observation counts not met')
    panel_path = ROOT / inventory['panel']['path']
    private_path(panel_path)
    if digest(panel_path) != inventory['panel']['sha256']:
        raise ValueError('Development panel checksum changed')
    rows = json.loads(panel_path.read_text())
    unique_events(rows,'Registered panel')
    if len(rows) != 1600:
        raise ValueError('The registered 1600 slots must remain in the panel')
    pool = [r for r in rows if r['status'] == 'READY' and
            spec['evaluation_start'] <= (r['entry_date'] or '') <= spec['last_entry_date']]
    if len(pool) < 200 or len({r['cik'] for r in pool}) < 40:
        raise ValueError('Frozen evaluation observation or issuer minimum not met')
    if any(r['target_pp'] is not None for r in pool):
        raise ValueError('Evaluation outcomes must remain masked before fitting')
    sessions = calendar()
    checked_pool_timing(pool,sessions)
    # Membership is fixed before training, separately from each score threshold.
    pool_path = RAW / 'frozen-evaluation-pool.json'
    private_path(pool_path)
    # Resolve all required execution records before any fit or pool output.
    source_inputs = bound_inputs()
    runtime = runtime_provenance(sessions)
    pool_sha = write(pool_path, pool)
    exclusions = [{'event_id': r['event_id'], 'cik': r['cik'], 'status': r['status'],
                   'entry_date': r['entry_date'], 'reasons': r['reasons']}
                  for r in rows if r not in pool]
    exclusions_path = HERE / 'registered-slot-exclusions.json'
    exclusion_sha = write(exclusions_path, exclusions)
    prefit = {'created_utc': now(), 'policy_sha256': POLICY_SHA,
        'readiness_sha256': digest(readiness_path), 'inventory_sha256': digest(inventory_path),
        'cohort_sha256': inventory['cohort_sha256'], 'sec_events_sha256': inventory['sec_events_sha256'],
        'price_manifest_sha256': inventory['price_manifest_sha256'], 'code_sha256': code_hashes(),
        'bound_execution_inputs_sha256': source_inputs, 'runtime': runtime,
        'status_source_assumption': 'Original contemporaneous listing covers carry forward between explicitly reviewed status events. '
            'This is not daily independent venue corroboration. Pre-open knowledge uses available_at; closing status uses effective_at.',
        'panel': inventory['panel'], 'evaluation_pool': {'path': str(pool_path.relative_to(ROOT)), 'sha256': pool_sha,
            'observations': len(pool), 'issuers': len({r['cik'] for r in pool})},
        'excluded_registered_slots': {'path': str(exclusions_path.relative_to(ROOT)), 'sha256': exclusion_sha,
            'note': 'Includes development observations and non-actionable evaluation slots; full original statuses preserved.'},
        'sample_counts': {'fit_2020': inventory['fit_observations'], 'validation_2021': inventory['validation_observations'],
            'evaluation': len(pool), 'evaluation_issuers': len({r['cik'] for r in pool})},
        'evaluation_outcomes_masked': True}
    write(HERE / 'prefit-inputs.json', prefit)
    models, selection_report = select_and_refit(rows)
    model_path = RAW / 'frozen-models.joblib'
    private_path(model_path)
    if model_path.exists():
        raise ValueError('Refuse to overwrite an existing serialized model')
    joblib.dump(models, model_path)
    forecasts = []
    scores = {name: fitted.predict(pool) for name, fitted in models.items()}
    for i, row in enumerate(pool):
        forecasts.append({'event_id': row['event_id'], 'cik': row['cik'],
            'entry_date': row['entry_date'], 'exit_date': row['exit_date'],
            **{name: float(values[i]) for name, values in scores.items()}})
    forecast_path = RAW / 'frozen-forecasts.json'
    private_path(forecast_path)
    checked_forecasts(pool,forecasts)
    forecast_sha = write(forecast_path, forecasts)
    report = {**prefit, 'models_frozen_utc': now(), 'selection': selection_report,
        'model_artifact': {'path': str(model_path.relative_to(ROOT)), 'sha256': digest(model_path)},
        'forecasts': {'path': str(forecast_path.relative_to(ROOT)), 'sha256': forecast_sha},
        'evaluation_outcomes_opened': False}
    write(frozen_path, report)
    return {'status': 'FROZEN_BEFORE_EVALUATION', 'pool_events': len(pool),
            'selected_alpha': {k: v['frozen_model']['alpha'] for k,v in selection_report['models'].items()}}


def source_frames(series, sessions, sec, cohort):
    """Map each original cover's currently known ticker to a stable issuer ID.

    A later ticker is not projected backward through its first evidenced cover.
    Gaps between an actual ticker change and our source evidence remain visible.
    Additional exact effective-date source resolutions can be added before use.
    """
    mapping = {x['cik']: [(x['seed_acceptance_eastern'][:10], symbol(x['historical_symbol']))]
               for x in cohort['issuers']}
    for slot in sec['slots']:
        for key in ['current', 'prior']:
            record = slot.get(key)
            if not record or record.get('security', {}).get('status') != 'VERIFIED_SINGLE_COMMON_CLASS':
                continue
            if not record.get('acceptance_eastern'):
                continue
            available = max(record['filing_date'], record['acceptance_eastern'][:10])
            mapping[slot['cik']].append((available, symbol(record['security']['historical_symbol'])))
    prices, actions, identity_audit = {}, [], {}
    action_evidence_path = HERE / 'corporate-action-evidence.json'
    envelope = json.loads(action_evidence_path.read_text()) if action_evidence_path.exists() else {}
    if envelope and envelope.get('policy_sha256') != POLICY_SHA:
        raise ValueError('Corporate action evidence belongs to a different policy')
    evidence = envelope.get('actions', {})
    # Status events require timezone-aware effective_at and available_at. The
    # former determines actual closing eligibility; only knowledge available by
    # session open may affect morning commitments. No after-hours halt is moved
    # backward to that day's close. Unverified/conflicting events mean unknown.
    schedule = session_schedule(sessions)
    def timestamp(value):
        stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Status evidence timestamps must include a timezone')
        return stamp.astimezone(timezone.utc)
    status_events = {}
    known_securities = {cik+':single_common' for cik in mapping}
    for event in envelope.get('security_status_events', []):
        if event.get('status') not in ('listed','otc','halted','unknown'):
            raise ValueError('Unknown security status classification')
        row = {**event,'effective':timestamp(event['effective_at']),'available':timestamp(event['available_at'])}
        if event['security_id'] not in known_securities:
            raise ValueError('Status evidence names a security outside the frozen cohort')
        status_events.setdefault(event['security_id'], []).append(row)
    def status_at(security_id, cutoff, knowledge_cutoff=None):
        eligible = [e for e in status_events.get(security_id, []) if e['effective'] <= cutoff
                    and (knowledge_cutoff is None or e['available'] <= knowledge_cutoff)]
        if not eligible:
            return 'listed'
        latest = max(e['effective'] for e in eligible)
        newest = [e for e in eligible if e['effective']==latest]
        states = {e['status'] if e.get('verified') is True and e.get('source_evidence') else 'unknown' for e in newest}
        return states.pop() if len(states)==1 else 'unknown'
    for cik, entries in mapping.items():
        entries = sorted(set(entries))
        for day in {x[0] for x in entries}:
            if len({ticker for when,ticker in entries if when==day})>1:
                raise ValueError('Conflicting historical tickers share an availability date')
        identity_audit[cik] = entries
        for day in sessions:
            available = [x for x in entries if x[0] < day]
            if not available:
                continue
            ticker = available[-1][1]
            source = series.get(ticker)
            security_id = cik + ':single_common'
            opened, closed = (timestamp(schedule[day][k]) for k in ('open','close'))
            status_fields = {'status': status_at(security_id,closed),
                             'status_before_open': status_at(security_id,opened,opened)}
            if not source or day not in source['rows']:
                if security_id in status_events:
                    # Carry separately evidenced status even if the quote is
                    # absent. No price or corporate action value is invented.
                    prices.setdefault(day,{})[security_id] = {**status_fields,
                        'qualified':False,'source_ticker':ticker,'missing_provider_row':True}
                continue
            raw = source['rows'][day]
            qualified = day not in source['issues']
            prices.setdefault(day, {})[security_id] = {
                'close': raw['close'], 'volume': raw['volume'], 'qualified': qualified,
                **status_fields,
                'divCash': raw['divCash'], 'splitFactor': raw['splitFactor'],
                'source_ticker': ticker, 'source_sha256': source['source_sha256']}
            for kind, field, identity in [('dividend','divCash',0),('split','splitFactor',1)]:
                if raw[field] == identity:
                    continue
                action_id = security_id + ':' + day + ':' + kind
                proof = evidence.get(action_id)
                # Entitlement classification must be established in a separate
                # action-source review; provider fields are never a fake payment.
                verified = bool(proof and proof.get('verified') is True and
                    proof.get('source_price_sha256') == source['source_sha256'] and
                    proof.get('effective_date') == day and proof.get('type') == kind)
                if verified and proof.get('security_id',security_id) != security_id:
                    raise ValueError('Corporate action proof names a different security')
                action = {'action_id': action_id, 'security_id': security_id,
                    'effective_date': day, 'type': kind, 'verified': verified,
                    'source_price_sha256': source['source_sha256']}
                if kind == 'split':
                    action['factor'] = raw[field]
                    # A generic distribution price factor is not evidence of a
                    # share-unit conversion. Classification is a separate review.
                    verified = verified and proof.get('action_kind') in ('stock_split','reverse_stock_split')
                    action['verified'] = verified
                    if verified and float(proof['factor']) != raw[field]:
                        raise ValueError('Verified split source conflicts with provider factor')
                else:
                    action.update(amount_per_share=raw[field], cash_available_date=proof.get('cash_available_date') if verified else None)
                    if verified and float(proof['amount_per_share']) != raw[field]:
                        raise ValueError('Verified dividend source conflicts with provider amount')
                    if action['cash_available_date'] is not None and not (
                            proof.get('cash_availability_verified') is True and proof.get('cash_availability_evidence')):
                        raise ValueError('A spendable cash date needs separate availability evidence')
                actions.append(action)
    # A merger entitlement is a separate legal claim. It need not appear in an
    # EOD vendor's divCash column or have a terminal quote. Payment remains locked
    # unless the source review independently supplies a cash availability date.
    for action_id, proof in evidence.items():
        if proof.get('type') != 'merger_cash':
            continue
        if proof['security_id'] not in known_securities:
            raise ValueError('Merger proof names a security outside the frozen cohort')
        amount = float(proof['amount_per_share'])
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError('Merger cash entitlement must be finite and positive')
        available = proof.get('cash_available_date')
        if available is not None and not (proof.get('cash_availability_verified') is True
                                        and proof.get('cash_availability_evidence')):
            raise ValueError('A spendable cash date needs separate availability evidence')
        actions.append({'action_id':action_id,'security_id':proof['security_id'],
            'effective_date':proof['effective_date'],'type':'merger_cash',
            'amount_per_share':proof['amount_per_share'],'cash_available_date':available,
            'verified':proof.get('verified') is True and bool(proof.get('source_evidence'))})
    return prices, actions, identity_audit


def run_evaluation():
    spec = policy()
    frozen_path = HERE / 'frozen-models.json'
    frozen = json.loads(frozen_path.read_text())
    if frozen.get('policy_sha256') != POLICY_SHA:
        raise ValueError('Frozen model policy mismatch')
    if frozen['code_sha256'] != code_hashes():
        raise ValueError('Code changed after model freeze; do not evaluate silently')
    if frozen['price_manifest_sha256'] != digest(HERE / 'price-manifest.json'):
        raise ValueError('Price-source manifest changed after model freeze')
    if frozen.get('bound_execution_inputs_sha256') != bound_inputs():
        raise ValueError('An execution/readiness/expense input changed after model freeze')
    sessions = calendar()
    if frozen.get('runtime') != runtime_provenance(sessions):
        raise ValueError('Runtime or session schedule changed after model freeze')
    if (HERE/'evaluation-result.json').exists() or (RAW/'evaluation-ledgers.json').exists():
        raise ValueError('Refuse to overwrite an existing evaluation')
    model_path = private_path(ROOT/frozen['model_artifact']['path'])
    if digest(model_path) != frozen['model_artifact']['sha256']:
        raise ValueError('Serialized model artifact changed after freeze')
    pool_path = ROOT / frozen['evaluation_pool']['path']
    forecast_path = ROOT / frozen['forecasts']['path']
    private_path(pool_path); private_path(forecast_path)
    if (digest(pool_path) != frozen['evaluation_pool']['sha256'] or
            digest(forecast_path) != frozen['forecasts']['sha256']):
        raise ValueError('Frozen pool or forecasts changed')
    pool = json.loads(pool_path.read_text())
    checked_pool_timing(pool,sessions)
    forecasts = checked_forecasts(pool,json.loads(forecast_path.read_text()))
    if (len(pool)!=frozen['evaluation_pool']['observations'] or
            len({r['cik'] for r in pool})!=frozen['evaluation_pool']['issuers'] or
            any(r['status']!='READY' or r['target_pp'] is not None or
                not spec['evaluation_start']<=r['entry_date']<=spec['last_entry_date'] for r in pool)):
        raise ValueError('Frozen pool qualification or counts changed')
    inventory = json.loads((HERE / 'panel-inventory.json').read_text())
    sec_path = ROOT / inventory.get('sec_events_path',str((HERE/'sec-events.json').relative_to(ROOT)))
    if digest(sec_path) != frozen['sec_events_sha256']:
        raise ValueError('Frozen SEC event sources changed')
    cohort_path = HERE / 'sec-cohort.json'
    if digest(cohort_path) != frozen['cohort_sha256']:
        raise ValueError('Frozen issuer cohort changed')
    sec, cohort = json.loads(sec_path.read_text()), json.loads(cohort_path.read_text())
    expected = [d for d in sessions if spec['evaluation_start'] <= d <= spec['evaluation_end']]
    series, _ = load_prices()
    prices, actions, identities = source_frames(series, sessions, sec, cohort)
    candidates = {}
    for model_name in ['numeric','text','matched_event']:
        candidates[model_name] = [{k: row[k] for k in ['event_id','security_id','cik','accession','filing_date','acceptance_date_et']}
            | {'score': None if model_name == 'matched_event' else forecasts[row['event_id']][model_name],
               'eligibility_status': 'READY'} for row in pool]
    expense_record = json.loads((HERE / 'data-expense.json').read_text())
    expense = float(expense_record['amount_usd'])
    accounts, expense_accounts = {}, {}
    for cost in ['base', 'stress']:
        accounts[cost], expense_accounts[cost] = {}, {}
        for name in ['numeric','text','matched_event']:
            kwargs = {'calendar': sessions, 'prices': prices, 'candidates': candidates[name], 'actions': actions,
                      'cost_case': cost, 'rank_mode': 'matched' if name=='matched_event' else 'score'}
            accounts[cost][name] = simulate(**kwargs)
            expense_accounts[cost][name] = simulate(**kwargs, initial_expense=expense)
    # Endpoint coverage is inspected only after the models and pool were fixed.
    labels, gaps = [], []
    for row in pool:
        value, audit = target(row, series, sessions)
        if value is None:
            gaps.append({'event_id': row['event_id'], **audit})
        else:
            labels.append({'event_id': row['event_id'], 'target_pp': value})
    spy = series.get('SPY', {'rows': {}, 'issues': {}})
    benchmark = {}
    for day in expected:
        before = sessions[sessions.index(day)-1]
        benchmark[day] = None if any(x not in spy['rows'] or x in spy['issues'] for x in [before, day]) else (
            spy['rows'][day]['adjClose']/spy['rows'][before]['adjClose']-1)
    readiness = json.loads((HERE / 'source-readiness.json').read_text())
    report = evaluate(accounts, expected_dates=expected, benchmark_returns=benchmark,
        expense_accounts=expense_accounts, data_expense=expense_record,
        sample_counts=frozen['sample_counts'], upstream_ready={'ready': readiness['ready'], 'reasons': readiness.get('reasons', [])})
    diagnostics = {}
    if labels:
        actual = np.asarray([r['target_pp'] for r in labels])
        for name in ['numeric','text']:
            prediction = np.asarray([forecasts[r['event_id']][name] for r in labels])
            diagnostics[name] = {'qualified_labels': len(labels), 'mse_percentage_points_squared': float(np.mean((actual-prediction)**2)),
                'pearson_prediction_target': float(np.corrcoef(actual,prediction)[0,1]) if np.std(actual)>0 and np.std(prediction)>0 else None,
                'qualification': 'Diagnostic on the labeled subset only; labels did not select the simulated event pool.'}
    ledger_path = RAW / 'evaluation-ledgers.json'
    private_path(ledger_path)
    ledger_sha = write(ledger_path, {'trading_only': accounts, 'after_data_expense': expense_accounts,
        'evaluation_labels': labels, 'label_gaps': gaps, 'source_identity_timeline': identities})
    report.update(evaluated_utc=now(), frozen_models_sha256=digest(frozen_path),
        source_readiness_sha256=digest(HERE / 'source-readiness.json'),
        action_evidence_sha256=digest(HERE / 'corporate-action-evidence.json') if (HERE / 'corporate-action-evidence.json').exists() else None,
        label_coverage={'frozen_pool': len(pool), 'qualified_outcomes': len(labels), 'unresolved_outcomes': len(gaps),
                        'pool_not_filtered_by_outcome_availability': True},
        prediction_diagnostics=diagnostics,
        ledgers={'path': str(ledger_path.relative_to(ROOT)), 'sha256': ledger_sha},
        interpretation='Conditional on original-source-qualified pre-entry events. This is an exploratory historical comparison, not live fill evidence or authorization to invest.')
    write(HERE / 'evaluation-result.json', report)
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['freeze', 'evaluate'])
    args = ap.parse_args()
    result = freeze() if args.stage == 'freeze' else run_evaluation()
    print(json.dumps(result if args.stage == 'freeze' else {k: v for k,v in result.items() if k in ['status','overall_status','label_coverage']}))
