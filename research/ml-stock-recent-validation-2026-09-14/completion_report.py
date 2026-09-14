"""Report the verified conditional accounts without changing frozen experiments."""
from collections import defaultdict
from datetime import datetime, timezone
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter
import numpy as np
import pandas as pd
import completion as c
from acquire import HERE, ROOT, RAW, OLD, load, write, sha, scope


def money(v): return f'${v:,.2f}'
def pct(v): return f'{100*v:.2f}%'


def main():
    scope()
    verification = load(HERE/'completion-verification-after.json')
    assert verification['passed']
    result = load(HERE/'completion-results.json')
    cases = result['cases']
    central = {cost:next(x for x in cases if x['name'] == f'cash1-delay5-{cost}') for cost in ('base','stress')}
    assert set(load(HERE/'completion-freeze.json')['central_cases']) == {x['name'] for x in central.values()}
    ranges = {}
    for cost in central:
        selected = [x for x in cases if x['cost'] == cost]
        ranges[cost] = {key: [min(x['metrics'][key] for x in selected), max(x['metrics'][key] for x in selected)]
                        for key in ('profit','cagr','max_drawdown')}
        ranges[cost]['selection_difference'] = [min(x['reference']['selection_difference'] for x in selected),
                                               max(x['reference']['selection_difference'] for x in selected)]
    decision = dict(status='PROFITABLE_CONDITIONAL_BACKTEST_NO_DEMONSTRATED_SELECTION_EDGE',
        central_cases={k:v['name'] for k,v in central.items()}, ranges=ranges,
        funded_ready=False, model_fits=0, ranking_parameter_searches=0, settlement_scenarios=12,
        new_paid_data_usd=0, prior_commit='95dd022',
        recommendation='Keep the fixed score as a research baseline; do not scale capital or tune these now-seen years. Any next experiment needs fresh evidence of selection advantage and realistic execution.',
        conditional_accounting='Ordinary dividends and cash-merger entitlements are valued but not spendable without supported payment dates; fractional cash and stock availability are declared sensitivities, not brokerage receipts.',
        recent_cohort_prices_now_seen=True)
    write(HERE/'completion-decision.json', decision)

    lines = ['# Recent fixed-score test: completed conditional results', '',
        '**The strategy made money in this backtest, but its stock ranking did not beat the exposure-matched reference.** The central scenario earned 5.91% annualized after base costs and 5.16% after stressed costs. These results support keeping a baseline, not a claim of a proven income-producing bot.', '',
        'The evaluation runs January 2, 2024–September 11, 2026, starting with $10,000. The six-signal rule, original 100-security cohort, entries, retention, sizing, cash reserve and loss halt were fixed before the recent-price requests. No trained model was fitted and no ranking parameter was searched.', '',
        'The [initial strict result](RESULTS.md) remains unresolved at the Pioneer-to-Exxon conversion. A separate [completion protocol](completion-protocol.json) declared 12 settlement scenarios before calculating their outcomes. The central scenario (1× published fractional-cash reference, five-session share availability delay) was selected in [completion-freeze.json](completion-freeze.json) before those runs. It is conditional accounting, not an observed brokerage account.', '',
        '## Central scenario', '', '| $10,000 account | Base costs | Stressed costs |', '|---|---:|---:|']
    metrics = [('Ending account value','final_nav',money), ('Net profit','profit',money),
               ('Annualized return','cagr',pct), ('Maximum peak-to-trough drawdown','max_drawdown',pct),
               ('Average stock exposure','mean_stock_exposure',pct), ('Trading fees','fees',money),
               ('Slippage','slippage',money), ('Loss halt triggered','stopped',lambda v:'Yes' if v else 'No')]
    for label,key,fmt in metrics:
        lines.append('| '+label+' | '+' | '.join(fmt(x['metrics'][key]) for x in central.values())+' |')
    lines += ['', 'Returns include the frozen IBKR Pro Fixed fee counterfactual and 10/50 basis points of slippage per side, using daily closing prices. They exclude personal taxes. Cash and receivables earn zero interest. Actual account fees and fills are not established by this simulation.', '',
        'For the same dates, hypothetical constant 4% and 6% annual cash hurdles end at '+money(central['base']['metrics']['cash_reference_end_values']['0.04'])+' and '+money(central['base']['metrics']['cash_reference_end_values']['0.06'])+'. The central account exceeds the 4% hurdle under both cost assumptions and falls short of 6%. Those are comparison assumptions, not a claim that either rate was continuously available. Stock drawdowns make equal percentage returns economically different.', '',
        '## Calendar-year behavior', '', 'One account continues across all three years; there are no annual capital or halt resets. The 2026 figure is year-to-date.', '',
        '| Period | Base return | Stressed return |', '|---|---:|---:|']
    for year in ('2024','2025','2026'):
        lines.append('| '+(year+' through September 11' if year == '2026' else year)+' | '+' | '.join(pct(x['metrics']['yearly'][year]['return_fraction']) for x in central.values())+' |')
    lines += ['', '## Does the ranking add value?', '',
        'The reference uses the equal mean daily return of the same month’s eligible securities, at the strategy’s actual prior-close stock exposure, with the same dated fee/slippage rate. It also includes floating fractional-entitlement exposure until that entitlement becomes a fixed cash claim. This is an attribution reference, not a tradable whole-share portfolio or a sector/beta-adjusted alpha estimate.', '',
        '| Central scenario | Base | Stress |', '|---|---:|---:|']
    for label,key in [('Reference ending value','ending_nav'),('Strategy minus reference','selection_difference')]:
        lines.append('| '+label+' | '+' | '.join(money(x['reference'][key]) for x in central.values())+' |')
    for cost, case in central.items():
        interval = case['uncertainty']['interval']; lo,hi = interval['ci95']
        lines.append(f'\n{cost.title()}: mean monthly strategy-minus-reference return {pct(interval["mean"])}; 95% stationary-block interval [{pct(lo)}, {pct(hi)}], from 32 complete months, 2,000 resamples and expected block length 12 months. September 2026 is excluded. These short, dependent samples and selection after earlier experiments limit inference.')
    lines += ['', 'Every settlement case trails its exposure-matched reference. A positive strategy return therefore does not establish that this particular ranking earned an advantage over taking comparable stock exposure.', '',
        '## All declared settlement cases', '',
        '| Fractional-cash multiple | Share delay (sessions) | Costs | Profit | Annualized return | Max drawdown | Strategy minus reference |',
        '|---:|---:|---|---:|---:|---:|---:|']
    for x in cases:
        m=x['metrics']
        lines.append(f'| {x["cash_multiplier"]}× | {x["delay_sessions"]} | {x["cost"]} | {money(m["profit"])} | {pct(m["cagr"])} | {pct(m["max_drawdown"])} | {money(x["reference"]["selection_difference"])} |')
    lines += ['',
        'All 12 accounts have complete conditional accounting, 39 purchases and 77 total fills; none triggers the permanent $2,000 trailing dollar-loss halt. No forced distribution pushes holdings above the 10-position entry cap. Sensitivity cases are not independent strategy trials and are not exhaustive bounds.', '',
        'Only the Pioneer stock conversion is encountered while held: three PXD shares create six whole XOM shares and a 0.9702-share fractional claim on May 3, 2024. The claim follows the dated XOM close until May 10; the central fixed amount is $113.10, with $0 and $141.38 alternatives. It never finances purchases. The XOM shares sell on June 4, after both declared availability dates, explaining why the zero/five-session delay cases are identical.', '',
        'The [Exxon completion announcement](https://www.sec.gov/Archives/edgar/data/34088/000095010324006322/dp210867_ex9901.htm) supports the 2.3234 exchange ratio. The [May 10 OCC memo](https://infomemo.theocc.com/infomemos?number=54574) publishes a fractional-cash unit price of $116.5789 for its option adjustment. That is evidence for the scenario reference, not proof of this user’s ordinary-share brokerage receipt. Aptiv/VGNT and LEG/SGI were included in the declared action handling but were not held at their stock-distribution dates.', '',
        '## Account value and spendable cash', '',
        'The ending account value includes receivables. Under the unchanged conservative accounting rules, all stocks are liquidated at the evaluation cutoff, and recent sale proceeds remain locked for seven calendar days. Ordinary dividends and the Sealed Air cash-merger entitlement remain non-spendable because actual payment dates were not sourced. These claims are valued in NAV; the reported ending value is not all immediately withdrawable cash.', '',
        '| Central case at cutoff | Base | Stress |', '|---|---:|---:|']
    breakdown={}
    for cost, case in central.items():
        account=c.load_account(case['account_file']); values=defaultdict(float)
        for claim in account['claims']:
            if not claim['paid']: values[claim['type']] += float(claim['amount'])
        breakdown[cost]=values
    lines.append('| Settled cash | '+' | '.join(money(x['metrics']['ending_cash']) for x in central.values())+' |')
    for key,label in [('sale','Unsettled sale proceeds'),('dividend','Dividend receivables'),('merger_cash','Cash-merger receivable'),('fractional_cash','Conditional fractional-cash claim')]:
        lines.append('| '+label+' | '+' | '.join(money(breakdown[cost][key]) for cost in central)+' |')
    lines += ['', 'The Sealed Air receivable is 18 shares × $42.15 = $758.70, supported by its [April 9 completion announcement](https://sealedair.gcs-web.com/news-releases/news-release-details/sealed-air-announces-completion-acquisition-cdr). None of this changes the original seven-day sale-lock or unsupported-payment-date rules.', '',
        '## Earlier results and coverage', '',
        'The already-seen 2022–2023 fixed-score test earned 2.97% annualized under base costs and 1.95% under stress. Those files are unchanged. This test resets the account to $10,000 in January 2024, so the two experiments cannot be presented as one continuous 2022–2026 trading return. Stronger recent performance does not establish that older regimes are obsolete.', '',
        'All 3,300 original company-month slots are retained across 33 months; 84–88 stocks are eligible per month, producing 2,859 fixed scores. Eligible labels are complete for January 2024–August 2026; unfinished September full-month labels are excluded. The cohort is a deterministic sample from a 2018 roster, not today’s full market or a list of AI winners. Missing financial factors receive the original neutral score, so “eligible” does not mean every factor is available.', '']
    coverage=load(HERE/'panel-coverage.json')['monthly']
    for feature in ('book_price','earnings_price','roa','cfo_assets'):
        counts=[x['financial_feature_available'][feature] for x in coverage]
        lines.append(f'- {feature}: {min(counts)}–{max(counts)} original securities with that feature per month.')
    lines += ['', 'The recent cohort prices and results are now seen research data. Future changes evaluated on these years are exploratory; preserve fresh evidence for any later validation.', '',
        '## Verification and artifacts', '',
        'Independent Decimal replays reconcile all 8,112 daily account observations, 924 fills and all 12 exposure-reference paths. Each conditional account exactly reproduces the initial strict account’s first 85 priced days. Synthetic tests cover conversion and spinoff value, whole-share delivery, trading delay, non-spendable fractions, quote timing, missing child prices, and exact no-action regression.', '',
        'Before outcomes, 35,900 financial components passed filing-date and availability checks, all 2,859 eligible scores matched independent percentile arithmetic, and 46,593 overlapping raw provider rows matched the earlier snapshot. Original experiment files, original strict result, predictions and completion implementation hashes remain unchanged.', '',
        'Acquisition completed with 96 Tiingo price requests (including the three date probes) and 94 SEC company-fact responses at $0 new paid data cost. The 12 accounting scenarios use cached data only. Raw provider payloads and detailed ledgers remain local and gitignored; hashes and concise derived results are committed.', '',
        '- [Full conditional results](completion-results.json)',
        '- [Independent account verification](completion-verification-after.json)',
        '- [Completion implementation freeze](completion-freeze.json)',
        '- [Original strict result](evaluation-result.json)',
        '- [Research decision](completion-decision.json)', '',
        '## Research decision', '',
        'Keep the fixed score as a baseline, with this version unproven for allocating additional capital. The later window improves absolute profitability but weakens the earlier suggestion of a selection advantage. More tuning on these years would consume research effort without creating independent evidence.', '',
        'A prospective paper comparison of the locked score against a predeclared unranked control could check signal availability and execution, if pursued next. A few months would test mechanics; it would not by itself establish dependable annual income. No new strategy search or paid data is needed to interpret this completed result.', '',
        '![Conditional account and reference paths](completion-paths.png)', '']
    (HERE/'COMPLETION_RESULTS.md').write_text('\n'.join(lines))

    plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
    fig, axes=plt.subplots(1,2,figsize=(13,5.8),sharey=True)
    for ax,(cost,case) in zip(axes,central.items()):
        account=c.load_account(case['account_file']); paths=load(RAW/f'completion-{case["name"]}-reference.json')
        dates=pd.to_datetime([x['date'] for x in account['daily']])
        all_nav=np.array([[float(d['nav']) for d in c.load_account(x['account_file'])['daily']] for x in cases if x['cost']==cost])
        ax.fill_between(dates,all_nav.min(axis=0),all_nav.max(axis=0),color='#2671a4',alpha=.15,label='Settlement scenario range')
        ax.plot(dates,[float(d['nav']) for d in account['daily']],color='#165e91',lw=2,label='Fixed score · central scenario')
        ax.plot(dates,[d['reference_nav'] for d in paths],color='#ba6129',lw=1.7,ls='--',label='Exposure-matched reference')
        ax.axhline(10000,color='#747474',lw=.8)
        ax.set_title(f'{cost.title()} costs\n{pct(case["metrics"]["cagr"])} annualized · {pct(case["metrics"]["max_drawdown"])} max drawdown',fontsize=11)
        ax.yaxis.set_major_formatter(StrMethodFormatter('${x:,.0f}')); ax.grid(alpha=.15)
        ax.tick_params(axis='x',rotation=25); ax.legend(loc='upper left',fontsize=8.4,frameon=False)
    axes[0].set_ylabel('Account value including receivables')
    fig.suptitle('Fixed stock ranking: profitable, below its exposure-matched reference',fontsize=15,y=.98)
    fig.text(.5,.905,'January 2, 2024–September 11, 2026 · $10,000 starting account · same frozen rules',ha='center',fontsize=10)
    fig.text(.02,.035,'Conditional settlement assumptions; no cash interest or personal taxes. Reference is attribution, not an executable portfolio.',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.87));fig.savefig(HERE/'completion-paths.png',dpi=160);plt.close(fig)
    write(RAW/'continuation-checkpoint.json',dict(status='COMPLETED_AND_VERIFIED',at_utc=datetime.now(timezone.utc).isoformat(),results=str(HERE/'COMPLETION_RESULTS.md'),new_paid_data_usd=0))
    print(json.dumps(decision,indent=2))


if __name__=='__main__': main()
