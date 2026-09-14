"""A $10,000 model-ranked cash account with second-session monthly reviews.

This module reads no prices, networks, or model artifacts by itself. ``simulate``
accepts these already validated inputs:

* calendar: sorted unique ISO NYSE session dates, including 60 lookback sessions.
* prices: {date: {stable_security_id: {close, volume, status, qualified,
  divCash, splitFactor}}}. Status is listed/otc/halted/unknown. An optional
  status_before_open is separately evidenced knowledge available before today's
  order preparation; final-day status alone cannot cancel a morning commitment.
  Decimal strings
  are preferred. ``qualified`` concerns the historical price/identity source,
  not guaranteed execution. divCash and splitFactor describe that day's actions.
* candidates: dictionaries with event_id, security_id, cik, accession,
  signal_date, score, and eligibility_status. The last is
  READY/INELIGIBLE/UNRESOLVED for upstream original-source/identity gates. Scores
  must have been produced by the parent's frozen causal model. This module
  independently checks dates, 60-session liquidity, and account eligibility.
* actions: {action_id, security_id, effective_date, type, verified, ...}.
  Types: split (factor); dividend (amount_per_share, cash_available_date or
  null); merger_cash (amount_per_share, cash_available_date or null). A verified
  record asserts evidence for the effective entitlement and share basis.
  Availability is a separately evidenced spendable-cash date, not a dividend
  ex-date or merger effective date. An unverified held action remains unresolved.

Keep a security ID through a ticker change. Distinct share classes use distinct
IDs. CIK is the occupied issuer slot. Split quantities that become fractional
remain explicit and unresolved: this first engine does not invent cash-in-lieu.

Internally money uses Decimal. Returned money is decimal strings, null when
unknown; counts are integers. An interval adjacent to a null NAV has null return.
Base/stress accounts must be run separately. ``rank_mode='matched'`` removes the
score threshold and uses the precomputed fixed hash selection order.
Optional start/end narrow the evaluation window within the frozen dates, mainly
for synthetic checks; they never extend it into reserved years. Initial expense is zero for this offline diagnostic.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
from pathlib import Path
from statistics import median


D = Decimal
ZERO, CENT = D(0), D('.01')
POLICY_SHA256 = 'ac2ff7be47da595c66ca2421f09711a85ef462059ef8a936258a1001bf3c0bc1'


def number(value):
    """Reject non-finite values; floats are interpreted through their spelling."""
    if isinstance(value, bool):
        raise ValueError('boolean is not a price or amount')
    try:
        value = D(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid numeric value') from None
    if not value.is_finite():
        raise ValueError('non-finite numeric value')
    return value


def iso(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('date must be canonical YYYY-MM-DD')
    return value


def cents(value):
    return value.quantize(CENT, rounding=ROUND_CEILING)


def fees(quantity, executed_notional, side):
    """Posted Pro Fixed counterfactual fees, each component rounded upward."""
    if type(quantity) is not int or quantity <= 0 or side not in ('buy', 'sell'):
        raise ValueError('positive whole quantity and buy/sell required')
    v = number(executed_notional)
    if v <= 0:
        raise ValueError('positive executed notional required')
    return {
        'commission': cents(min(D('.01')*v, max(D(1), D('.005')*quantity))),
        'sec': cents(D('.0000206')*v) if side == 'sell' else ZERO,
        'taf': cents(min(D('9.79'), D('.000195')*quantity)) if side == 'sell' else ZERO,
        'cat': cents(D('.000003')*quantity),
    }


def stress_budget(quantity, reference):
    """Uncapped reserve from the execution plan, not actual commission."""
    return (quantity*reference*D('1.005') + max(D(1), D('.005')*quantity)
            + cents(D('.000003')*quantity))


def whole_quantity(budget, previous_close):
    q = max(0, int(budget/(previous_close*D('1.005'))))
    while q and not fits_stressed(q, previous_close, budget):
        q -= 1
    return q


def fits_stressed(quantity, reference, budget):
    """Also cover upward commission rounding; never enlarge the stated reserve."""
    notional = quantity*reference*D('1.005')
    actual = notional+sum(fees(quantity, notional, 'buy').values(), ZERO)
    return stress_budget(quantity, reference) <= budget and actual <= budget


def serial(value):
    if isinstance(value, D):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def frozen_policy():
    path = Path(__file__).with_name('account-policy.json')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != POLICY_SHA256:
        raise ValueError('experiment policy checksum changed')
    return json.loads(raw)


def simulate(*, calendar, prices, candidates, actions=(), cost_case='base',
             rank_mode='matched', start=None, end=None, initial_expense=0, retention_by_day=None):
    """Return decisions, fills, claims, lots and daily NAV without fitting anything.

    Missing candidate data is recorded as skipped/unresolved, never as a made-up
    trade. Missing held valuation makes the whole performance verdict unresolved,
    although accounting continues and qualified positions may still exit.
    """
    policy = frozen_policy()
    if cost_case not in ('base', 'stress') or rank_mode not in ('score', 'matched'):
        raise ValueError('unknown cost case or ranking mode')
    start, end = iso(start or policy['evaluation_start']), iso(end or policy['evaluation_end'])
    if not policy['evaluation_start'] <= start <= end <= policy['evaluation_end']:
        raise ValueError('window is outside frozen evaluation dates')
    calendar = [iso(x) for x in calendar]
    if calendar != sorted(set(calendar)) or start not in calendar or end not in calendar:
        raise ValueError('unique complete-window calendar with start/end sessions required')
    ci = {d: i for i, d in enumerate(calendar)}
    expense = number(initial_expense)
    if not ZERO <= expense < 10000:
        raise ValueError('initial expense must be in [0,10000)')
    slip = D('.001') if cost_case == 'base' else D('.005')
    cash, high = D(10000)-expense, D(10000)
    holdings, claims, decisions, fills, daily, completed = {}, [], [], [], [], []
    action_log, unresolved, candidate_gaps = [], [], []
    stopped = expense >= 2000
    stop_date = start if stopped else None
    previous_nav = D(10000)
    previous_unpriced = False
    max_observed_dd = ZERO
    events_by_day, actions_by_day = {}, {}

    def bar(day, sec, allow_otc=False):
        b = prices.get(day, {}).get(sec)
        allowed = ('listed', 'otc') if allow_otc else ('listed',)
        if not isinstance(b, dict) or b.get('qualified') is not True or b.get('status') not in allowed:
            return None
        try:
            close, volume = number(b['close']), number(b['volume'])
        except (KeyError, ValueError):
            return None
        if close <= 0 or volume <= 0:
            return None
        return close

    retention_by_day = retention_by_day or {}
    held_exit_decisions = []
    seen = set()
    for original in candidates:
        event = deepcopy(original)
        required = ('event_id', 'security_id', 'cik', 'signal_date', 'score', 'eligibility_status')
        if any(k not in event for k in required) or event['event_id'] in seen:
            raise ValueError('candidate fields missing or duplicate event_id')
        seen.add(event['event_id'])
        if event['eligibility_status'] not in ('READY', 'INELIGIBLE', 'UNRESOLVED'):
            raise ValueError('invalid upstream eligibility status')
        available = iso(event['signal_date'])
        index = bisect_right(calendar, available) + 1
        event['available_date'] = available
        event['score'] = None if event['score'] is None else number(event['score'])
        if index >= len(calendar):
            decisions.append({'event_id': event['event_id'], 'status': 'OUTSIDE_WINDOW'})
            continue
        day = calendar[index]
        if not start <= day <= end:
            decisions.append({'event_id': event['event_id'], 'date': day, 'status': 'OUTSIDE_WINDOW'})
            continue
        if day != [d for d in calendar if d[:7] == day[:7]][1]:
            raise ValueError('Model review must be second session of month')
        event['exit_date'] = end
        events_by_day.setdefault(day, []).append(event)

    seen = set()
    for original in actions:
        a = deepcopy(original)
        for k in ('action_id', 'security_id', 'effective_date', 'type', 'verified'):
            if k not in a:
                raise ValueError('corporate action fields missing')
        if a['action_id'] in seen:
            raise ValueError('duplicate action_id')
        seen.add(a['action_id'])
        day = iso(a['effective_date'])
        if a['type'] not in ('split', 'dividend', 'merger_cash', 'stock_distribution'):
            raise ValueError('unsupported action type')
        numeric_field = 'factor' if a['type'] == 'split' else 'amount_per_share'
        if numeric_field not in a:
            raise ValueError('explicit corporate action factor/amount required')
        amount = number(a[numeric_field])
        if amount < 0 or (a['type'] == 'split' and amount == 0):
            raise ValueError('invalid corporate action factor/amount')
        if a['type'] != 'split' and 'cash_available_date' not in a:
            raise ValueError('cash availability must be explicit, including null')
        available = a.get('cash_available_date')
        if available is not None and iso(available) < day:
            raise ValueError('claim cannot be available before entitlement')
        # Non-trading-day effective actions are processed before the next session.
        j = bisect_left(calendar, day)
        if j < len(calendar):
            actions_by_day.setdefault(calendar[j], []).append(a)

    def occupied():
        return {h['cik'] for h in holdings.values()} | {
            c['cik'] for c in claims if c['type'] == 'merger_cash' and not c['paid']}

    def add_claim(h, amount, kind, day, available, action_id=None):
        claims.append({'claim_id': action_id or h['event_id']+':sale',
                       'security_id': h['security_id'], 'cik': h['cik'],
                       'event_id': h['event_id'], 'entitled_quantity': h['quantity'],
                       'originating_position_basis': h['cost_basis'],
                       'amount': amount, 'type': kind, 'created_date': day,
                       'cash_available_date': available, 'paid': False})

    def record_fill(h, q, ref, side, day):
        executed = ref*(1+slip if side == 'buy' else 1-slip)
        notional = q*executed
        charge = fees(q, notional, side)
        fee = sum(charge.values(), ZERO)
        fill = {'event_id': h['event_id'], 'security_id': h['security_id'],
                'cik': h['cik'], 'date': day, 'side': side, 'quantity': q,
                'raw_close': ref, 'executed_price': executed, 'notional': notional,
                'fees': charge, 'fee_total': fee, 'slippage_cost': q*ref*slip}
        fills.append(fill)
        return notional+fee if side == 'buy' else notional-fee

    for day in calendar[ci[start]:ci[end]+1]:
        # Only already-created claims release cash, plus today's evidenced actions below.
        for c in claims:
            if not c['paid'] and c['cash_available_date'] is not None and c['cash_available_date'] <= day:
                cash += c['amount']; c['paid'] = True; c['credited_date'] = day

        todays = actions_by_day.get(day, [])
        # Mixed action bases need an explicit order; fail closed rather than invent one.
        types_by_security = {}
        for a in todays:
            types_by_security.setdefault(a['security_id'], []).append(a['type'])
        bad_actions = {s for s, kinds in types_by_security.items()
                       if len(kinds) != len(set(kinds)) or ('split' in kinds and len(kinds) > 1)}
        for a in todays:
            if a['type'] == 'merger_cash':
                continue
            raw = prices.get(day, {}).get(a['security_id'])
            field, expected = (('splitFactor', a['factor']) if a['type'] == 'split'
                               else ('divCash', a['amount_per_share']))
            if (isinstance(raw, dict) and raw.get('missing_provider_row') is not True
                    and (field not in raw or number(raw[field]) != number(expected))):
                bad_actions.add(a['security_id'])
        reference_factors = {}
        for a in sorted(todays, key=lambda x: x['action_id']):
            sec = a['security_id']; h = holdings.get(sec)
            valid = a['verified'] is True and sec not in bad_actions
            factor = number(a['factor']) if a['type'] == 'split' else D(1)
            if a['type'] == 'split' and factor <= 0:
                raise ValueError('split factor must be positive')
            if valid and a['type'] == 'split':
                reference_factors[sec] = factor
            if h is None:
                continue
            if not valid or h.get('unresolved_action'):
                # Do not let a later merger erase unresolved units or dividends.
                h['unresolved_action'] = a['action_id']
                continue
            if a['type'] == 'split':
                h['quantity'] *= factor
                # Aggregate basis stays constant, even where a fractional claim is unresolved.
                if h['quantity'] != h['quantity'].to_integral_value():
                    h['unresolved_action'] = 'fractional_split:'+a['action_id']
            else:
                amount = number(a['amount_per_share'])*h['quantity']
                if amount < 0:
                    raise ValueError('cash entitlement cannot be negative')
                add_claim(h, amount, a['type'], day, a['cash_available_date'], a['action_id'])
                if a['cash_available_date'] is not None and a['cash_available_date'] <= day:
                    cash += amount; claims[-1]['paid'] = True; claims[-1]['credited_date'] = day
                if a['type'] == 'merger_cash':
                    del holdings[sec]
            action_log.append({'date': day, 'action_id': a['action_id'], 'security_id': sec,
                               'source_effective_date': a['effective_date'], 'type': a['type']})

        # A provider's declared action must have a corresponding verified source record.
        for sec, h in holdings.items():
            raw = prices.get(day, {}).get(sec)
            # Separately evidenced status can exist without a vendor price row.
            # Treat this like an absent row for action comparisons, not evidence
            # of a malformed action. Its missing mark still makes NAV unresolved.
            if not isinstance(raw, dict) or raw.get('missing_provider_row') is True:
                continue
            for field, kind, identity in [('divCash', 'dividend', ZERO), ('splitFactor', 'split', D(1))]:
                if field not in raw:
                    h['unresolved_action'] = 'missing_action_fields'
                    continue
                if number(raw[field]) != identity and not any(
                        a['security_id'] == sec and a['type'] == kind and a['verified'] is True
                        for a in todays):
                    h['unresolved_action'] = 'unverified_declared_'+kind

        if day in retention_by_day:
            keep = set(retention_by_day[day])
            for sec, h in holdings.items():
                retained = sec in keep and not h['exit_pending']
                held_exit_decisions.append({'date':day,'event_id':h['event_id'],
                    'security_id':sec,'status':'RETAINED' if retained else 'RANK_OR_DATA_EXIT'})
                if not retained:
                    h['exit_pending'] = True
                    h['exit_date'] = min(h['exit_date'], day)
                    h['exit_reason'] = 'RANK_OR_DATA_EXIT'

        # A morning decision cannot know today's absent closing observation. Known
        # statuses can block it now; a missing close discovered later cannot resize it.
        entry_frozen = previous_unpriced or any(h.get('unresolved_action') for h in holdings.values())
        entry_frozen |= any(prices.get(day, {}).get(s, {}).get('status_before_open') in ('halted', 'unknown')
                            for s in holdings)
        planned, reserved, planned_issuers = [], ZERO, set()
        day_events = events_by_day.get(day, [])
        if rank_mode == 'score':
            day_events.sort(key=lambda e: (-(e['score'] if e['score'] is not None else D('-Infinity')),
                                           e['available_date'], str(e['cik']), e['event_id']))
        else:
            day_events.sort(key=lambda e: (e['selection_key'], e['event_id']))
        for e in day_events:
            decision = {'event_id': e['event_id'], 'date': day, 'security_id': e['security_id'],
                        'score': e['score'], 'exit_date': e['exit_date']}
            decisions.append(decision)
            reason = None
            if e['eligibility_status'] != 'READY':
                reason = 'UPSTREAM_'+e['eligibility_status']
            elif rank_mode == 'score' and (e['score'] is None or e['score'] < 1):
                reason = 'BELOW_THRESHOLD' if e['score'] is not None else 'MISSING_SCORE'
            elif stopped or entry_frozen:
                reason = 'ACCOUNT_STOPPED' if stopped else 'UNPRICED_ENTRY_FREEZE'
            elif prices.get(day, {}).get(e['security_id'], {}).get('status_before_open') == 'halted':
                reason = 'ENTRY_HALTED'
            elif prices.get(day, {}).get(e['security_id'], {}).get('status_before_open') == 'otc':
                reason = 'ENTRY_NONLISTED'
            elif prices.get(day, {}).get(e['security_id'], {}).get('status_before_open') == 'unknown':
                reason = 'ENTRY_STATUS_UNRESOLVED'
            elif e['cik'] in occupied() | planned_issuers:
                reason = 'ISSUER_OCCUPIED'
            elif len(occupied() | planned_issuers) >= 10:
                reason = 'SLOTS_FULL'
            lookback = calendar[max(0, ci[day]-63):ci[day]]
            refs = [bar(d, e['security_id']) for d in lookback]
            if reason is None and any(prices.get(d, {}).get(e['security_id'], {}).get('status')
                                      in ('halted', 'otc') for d in lookback):
                reason = 'LIQUIDITY_INELIGIBLE'
            if reason is None and (len(refs) != 63 or any(p is None for p in refs)):
                reason = 'LIQUIDITY_DATA_UNRESOLVED'
            if reason is None:
                dollar_vol = [p*number(prices[d][e['security_id']]['volume']) for p,d in zip(refs,lookback)]
                if refs[-1] < 5 or median(dollar_vol) < 10_000_000:
                    reason = 'LIQUIDITY_INELIGIBLE'
            if reason is None and (e['security_id'] in bad_actions or any(
                    a['security_id'] == e['security_id'] and a['verified'] is not True for a in todays)):
                reason = 'ENTRY_ACTION_UNRESOLVED'
            if reason is not None:
                decision['status'] = reason
                if 'UNRESOLVED' in reason or reason == 'MISSING_SCORE':
                    candidate_gaps.append(e['event_id'])
                continue
            payable_reserve = sum((-c['amount'] for c in claims if not c['paid'] and c['amount'] < 0), ZERO)
            budget = min(D(800), D('.08')*previous_nav, cash-reserved-payable_reserve-D(2000))
            ref = refs[-1]/reference_factors.get(e['security_id'], D(1))
            q = whole_quantity(budget, ref) if budget > 0 else 0
            decision.update(budget=budget, previous_close_reference=ref, committed_quantity=q)
            if not q:
                decision['status'] = 'CASH_OR_INTEGER_LIMIT'
                continue
            decision['status'] = 'COMMITTED'
            planned.append((e, decision, q, budget)); reserved += budget; planned_issuers.add(e['cik'])

        # Existing exits were committed before observing today's closing mark.
        for sec, h in list(holdings.items()):
            if not (stopped or h['exit_date'] <= day or h['exit_pending']):
                continue
            h['exit_pending'] = True
            h['exit_reason'] = 'ACCOUNT_STOP' if stopped else h.get('exit_reason', 'EVALUATION_END')
            ref = bar(day, sec)
            if ref is None or h.get('unresolved_action'):
                continue
            q = int(h['quantity'])
            proceeds = record_fill(h, q, ref, 'sell', day)
            earliest = (date.fromisoformat(day)+timedelta(days=7)).isoformat()
            j = bisect_left(calendar, earliest)
            available = calendar[j] if j < len(calendar) else None
            add_claim(h, proceeds, 'sale', day, available)
            completed.append({**h, 'actual_exit_date': day, 'net_sale_proceeds': proceeds,
                              'delay_sessions': max(0, ci[day]-ci[h['exit_date']])})
            del holdings[sec]

        # Do not redeploy reservations released by today's cancelled orders.
        for e, decision, q, budget in planned:
            ref = bar(day, e['security_id'])
            if ref is None:
                raw = prices.get(day, {}).get(e['security_id'], {})
                if raw.get('status') in ('halted', 'otc'):
                    decision['status'] = 'ENTRY_HALTED' if raw['status'] == 'halted' else 'ENTRY_NONLISTED'
                elif raw.get('qualified') is True and raw.get('status') == 'listed' and number(raw.get('volume', -1)) == 0:
                    decision['status'] = 'ENTRY_NO_VOLUME'
                else:
                    decision['status'] = 'ENTRY_UNAVAILABLE'; candidate_gaps.append(e['event_id'])
                continue
            if not fits_stressed(q, ref, budget):
                decision['status'] = 'ENTRY_LIMIT_CANCELLED'
                continue
            h = {'event_id': e['event_id'], 'security_id': e['security_id'], 'cik': e['cik'],
                 'quantity': D(q), 'entry_date': day, 'exit_date': e['exit_date'],
                 'exit_pending': False, 'raw_entry_close': ref, 'last_qualified_mark': ref}
            spend = record_fill(h, q, ref, 'buy', day)
            if spend > budget or cash-spend < 2000:
                raise AssertionError('committed order breached its cash envelope')
            cash -= spend; h['cost_basis'] = spend; holdings[e['security_id']] = h
            decision.update(status='FILLED', spend=spend)

        missing, marked, holding_rows = [], ZERO, {}
        for sec, h in holdings.items():
            ref = None if h.get('unresolved_action') else bar(day, sec, allow_otc=True)
            if ref is None:
                missing.append(sec)
            else:
                marked += h['quantity']*ref; h['last_qualified_mark'] = ref
            holding_rows[sec] = {**h, 'qualified_close': ref,
                                 'mark_status': prices.get(day, {}).get(sec, {}).get('status', 'missing')}
        unpaid = sum((c['amount'] for c in claims if not c['paid']), ZERO)
        nav = None if missing else cash+unpaid+marked
        ret = None if nav is None or previous_nav is None else nav/previous_nav-1
        if nav is not None:
            high = max(high, nav)
            dd = high-nav; max_observed_dd = max(max_observed_dd, dd)
            if dd >= 2000 and not stopped:
                stopped = True; stop_date = day
        else:
            dd = None
            unresolved.append({'date': day, 'security_ids': missing})
        daily.append({'date': day, 'settled_cash': cash, 'reserved_cash_eod': ZERO,
                      'unpaid_claim_value': unpaid, 'holdings': deepcopy(holding_rows),
                      'nav': nav, 'daily_return': ret, 'high_water_observed': high,
                      'drawdown_observed': dd, 'unpriced_security_ids': missing,
                      'account_stopped': stopped})
        previous_nav, previous_unpriced = nav, bool(missing)

    return serial({'status': 'UNRESOLVED' if unresolved or candidate_gaps else 'COMPLETE_ACCOUNTING',
                   'policy_sha256': POLICY_SHA256, 'cost_case': cost_case, 'rank_mode': rank_mode,
                   'start': start, 'end': end, 'initial_capital': D(10000), 'initial_expense': expense,
                   'ending_nav': daily[-1]['nav'], 'ending_settled_cash': cash,
                   'execution_status': 'OPEN_OR_PENDING_LOTS' if holdings else 'NO_OPEN_STOCK_LOTS',
                   'stopped': stopped, 'stop_date': stop_date,
                   'max_drawdown': None if unresolved else max_observed_dd,
                   'max_observed_drawdown': max_observed_dd,
                   'daily': daily, 'decisions': decisions, 'fills': fills, 'claims': claims,
                   'open_holdings': holdings, 'completed_positions': completed,
                   'action_log': action_log, 'held_exit_decisions': held_exit_decisions, 'unpriced_days': unresolved,
                   'unresolved_candidate_ids': sorted(set(candidate_gaps))})
