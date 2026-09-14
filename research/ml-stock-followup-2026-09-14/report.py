"""Presentation of frozen follow-up outputs; no further strategy runs."""
from datetime import datetime,timezone,date
import json
import numpy as np
from followup import HERE,ROOT,RAW,read,write,sha,intact

def main():
    intact();r=read(HERE/'results.json');v=read(HERE/'verification-after.json');assert v['passed']
    def money(x):return f'-${abs(x):,.2f}' if x<0 else f'${x:,.2f}'
    fixed={c:r['strict']['metrics']['fixed-'+c] for c in ['base','stress']}
    bounds={}
    for cost in ['base','stress']:
        controls=[e[cost] for s,e in r['control_ensembles'].items() if s!='strict']
        ridge=[a['metrics']['ridge-'+cost] for a in r['receipt_scenarios'].values()]
        bounds[cost]=dict(control_mean_profit_range=[min(e['mean_ending_nav']-10000 for e in controls),max(e['mean_ending_nav']-10000 for e in controls)],
            controls_below_fixed_range=[min(e['controls_below_fixed'] for e in controls),max(e['controls_below_fixed'] for e in controls)],
            ridge_tested_profit_range=[min(a['profit'] for a in ridge),max(a['profit'] for a in ridge)])
    write(HERE/'presentation-statistics.json',bounds)
    lines=['# Fixed-score benchmark and linear-account follow-up','',
      '**The fixed score shows an exploratory selection advantage in this sample, but still misses the 4–6% account-return target. Both trained models remain unattractive under the tested conditions.**','',
      'This is the separately authorized, cached-data follow-up to the [original comparison](../ml-stock-comparison-2026-09-14/RESULTS.md). Predictions, source data and original results are unchanged. No model was retrained, no new market data was requested, and no reserved-year strategy prices were opened.','',
      '## Fixed score versus ordinary stock exposure','',
      'Each reference starts with $10,000. On every day it receives the prior-cut eligible cohort’s equal-mean stock return at the fixed strategy’s actual prior-close stock exposure fraction. It deducts the same dated fee/slippage rate, expressed as a fraction of the strategy’s prior NAV. Uninvested capital and receivables earn zero. This is a fractional attribution reference, not a whole-share executable strategy or a sector/volatility-adjusted alpha estimate.','',
      '| Cost case | Fixed-score profit | Matched-exposure reference profit | Fixed minus reference |','|---|---:|---:|---:|']
    for cost in ['base','stress']:
        e=r['exposure_reference'][cost]
        lines.append(f'| {cost} | {money(fixed[cost]["profit"])} | {money(e["ending_reference_nav"]-10000)} | {money(e["difference_dollars"])} |')
    lines+=['','Both years have a positive average monthly fixed-minus-reference difference. The planned stationary month-block intervals remain wide:','',
      '| Cost case | Mean monthly difference | 95% month-block interval | 2022 mean | 2023 mean |','|---|---:|---:|---:|---:|']
    for cost in ['base','stress']:
        e=r['exposure_reference'][cost];b=e['paired_month_interval'];lo,hi=b['ci95']
        lines.append(f'| {cost} | {100*b["mean"]:.3f} pp | [{100*lo:.3f}, {100*hi:.3f}] pp | {100*e["yearly_mean_month_difference"]["2022"]:.3f} pp | {100*e["yearly_mean_month_difference"]["2023"]:.3f} pp |')
    lines+=['','The interval uses 2,000 stationary resamples of 24 months with expected block length 12 months. It includes zero in both cost cases. The result is encouraging enough to retain the fixed score as a research lead, but it does not establish a reliable advantage. These market months were already familiar, and this follow-up was chosen after the original outcomes. Sector and other risk tilts can contribute to the difference.','',
      '## Twenty unranked account controls','',
      'Seeds 0–19 were fixed before these control outcomes. Each ranks the same eligible companies by a persistent hash of seed and issuer ID, independently of scores and realized returns. All use the same $10,000 capital, whole-share sizing, 10% entry/20% retention bands, cash reserve, proceeds lock, costs and permanent loss halt.','',
      '**The strict full ensemble remains incomplete:** controls 09 and 13 in each cost case encounter the same ZBH fractional-share cash gap as Ridge. No failed or incomplete control is deleted. The complete-ensemble figures below are conditional on all seven disclosed receipt scenarios.','',
      '| Cost case | Mean control profit across receipt scenarios | Controls beaten by fixed score |','|---|---:|---:|']
    for cost in ['base','stress']:
        b=bounds[cost];lo,hi=b['control_mean_profit_range'];nlo,nhi=b['controls_below_fixed_range']
        lines.append(f'| {cost} | {money(lo)} to {money(hi)} | {nlo} of 20'+('' if nhi==nlo else f' to {nhi} of 20')+' |')
    exemplar=r['control_ensembles']['cash_25.53_withheld']
    lines+=['','These controls share the account rules but are not exact turnover or risk matches:','',
      '| Base-cost diagnostic | Fixed score | Mean unranked control |','|---|---:|---:|',
      f'| Average stock exposure | {fixed["base"]["mean_stock_exposure"]:.2%} | {exemplar["base"]["mean_stock_exposure"]:.2%} |',
      f'| Purchases | {fixed["base"]["buys"]} | {exemplar["base"]["mean_buys"]:.2f} |',
      f'| Traded notional | {money(fixed["base"]["traded_notional"])} | {money(exemplar["base"]["mean_traded_notional"])} |','',
      'Persistent random ranks trade less than the changing fixed score. Three base and four stress controls hit the loss halt. Their lower average exposure also reflects those halts. The separate exposure/cost reference above addresses part of this mismatch. Beating 20 controls is a descriptive result, not a formal p-value or 20 independent economic histories.','',
      '## Ridge and the missing spinoff payment','',
      'The strict original Ridge account remains unresolved. Six ZBH shares create 0.6 ZIMV share; cached ZIMV data give a March 1, 2022 close of $25.53 and a maximum daily high of $33.44 over the retained 2022–2023 history. Neither establishes the broker’s cash-in-lieu sale or payment.','',
      'The protocol tested zero cash, $25.53 per ZIMV share (the ex-date reference), and a deliberately high $100 per ZIMV share. Positive amounts were paid hypothetically on the event date, April 1, or left unspendable through the end. These are seven sensitivity cases, not sourced receipts. Under this account’s six-share holding they correspond to $0, $15.318 or $60.','',
      '| Assumed total ZIMV receipt | Ridge base profit | Ridge stress profit | Stress halt |','|---|---:|---:|---|']
    for name,amount in [('zero_withheld',0),('cash_25.53_withheld',15.318),('cash_100_withheld',60)]:
        a=r['receipt_scenarios'][name]['metrics'];base=a['ridge-base'];stress=a['ridge-stress']
        lines.append(f'| {money(amount)} | {money(base["profit"])} | {money(stress["profit"])} | {stress["stop_date"] or "none"} |')
    lines+=['','Changing payment timing among the declared cases did not change their final returns. Changing the amount did change whole-share sizing, and the zero-receipt stress case triggered the September 30, 2022 loss halt. Outcomes are therefore not monotonic in the payment amount: the observed range is not an exhaustive mathematical bound on every possible account path. **Every tested Ridge case loses money.** There is no reason from this sensitivity check to spend more effort pursuing the exact payment to promote Ridge.','',
      '## Decision and verification','',
      '- Keep the fixed score as the only research lead from this comparison. It shows favorable selection evidence in this limited sample; a longer-history, correctly dated cohort would be the next kind of evidence to consider. No acquisition or follow-on test is queued here.',
      '- Keep the tree and Ridge versions shelved. Neither supports funding under the measured tree result or the disclosed Ridge scenarios.',
      '- The fixed score itself remains below the user’s target: 2.97%/1.95% annualized with 14.91%/15.07% drawdowns under base/stress costs. The benchmark comparison does not turn this into dependable extra income.',
      f'- Independent replay passed for {v["unique_accounts"]} distinct account files: {sum(a["complete"] for a in v["accounts"])} complete cases and six valid strict prefixes, {v["total_nav_days_reconciled"]:,} NAV days and {v["total_fills_recomputed"]:,} fills. Control rank orders, source hashes, cash availability, account sizing, halts and exposure-reference arithmetic were checked.',
      '- New paid data cost: $0. New network market-data requests: 0. New fitted models: 0. Original artifacts and predictions remain byte-for-byte unchanged.','',
      'Evidence: `protocol.json`, `run-freeze.json`, `results.json`, `orders.json`, `verification-before.json`, and `verification-after.json`. Full compressed ledgers and reference paths are in the local snapshot directory.']
    (HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    write(HERE/'decision.json',dict(status='FIXED_SCORE_EXPLORATORY_LEAD_TRAINED_MODELS_NOT_PROMOTED',fixed_score_cash_target_pass=False,
        fixed_score_reference_interval_excludes_zero=False,strict_control_ensemble_complete=False,all_control_receipt_scenarios_complete=True,
        all_tested_ridge_cases_negative=True,exact_ridge_broker_payment_resolved=False,new_paid_data_usd=0,new_fitted_models=0,
        new_network_data_requests=0,reserved_strategy_prices_opened=False,live_trading_approved=False,
        completed_utc=datetime.now(timezone.utc).isoformat(),results_sha256=sha(HERE/'results.json'),verification_sha256=sha(HERE/'verification-after.json')))
    print('Report and decision saved.')

if __name__=='__main__':main()
