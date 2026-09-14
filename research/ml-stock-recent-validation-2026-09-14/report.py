"""Present the frozen recent-window results after independent verification."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from acquire import HERE,ROOT,RAW,OLD,load,write,sha,scope


def money(value):return 'Unresolved' if value is None else f'${value:,.2f}'
def pct(value):return 'Unresolved' if value is None else f'{100*value:.2f}%'


def main():
    scope();verification=load(HERE/'verification-after.json');assert verification['passed']
    result=load(HERE/'evaluation-result.json');coverage=load(HERE/'panel-coverage.json');previous=load(OLD/'evaluation-result.json')
    pm=load(HERE/'price-manifest.json');sm=load(HERE/'sec-manifest.json')
    lines=['# Fixed-score recent-window results','',
           'Evaluation: January 2, 2024–September 11, 2026. Rules were frozen before the recent-price requests; there were no model fits or parameter searches. Each cost case starts once with $10,000. The 2022–2023 results were already seen and are presented separately.','',
           '| New evaluation | Base costs | Stressed costs |','|---|---:|---:|']
    metrics=[('Account status','status',str),('Ending account value','final_nav',money),('Net profit','profit',money),('Annualized return over the full new window','cagr',pct),('Maximum drawdown','max_drawdown',pct),('Loss halt triggered','stopped',lambda x:'Yes' if x else 'No'),('Halt date','stop_date',lambda x:x or 'None'),('Average stock exposure on priced days','mean_stock_exposure',pct),('Trading fees','fees',money),('Slippage','slippage',money)]
    for label,key,fmt in metrics:lines.append('| '+label+' | '+' | '.join(fmt(result['accounts'][c][key]) for c in ['base','stress'])+' |')
    lines+=['','## Calendar-year behavior','','Annual figures follow the same continuous account; capital and loss halts are not reset each January. 2026 is a partial-year return, not an annual projection.','','| Period | Base return | Stress return |','|---|---:|---:|']
    for year in ['2024','2025','2026']:
        lines.append('| '+(year+' through September 11' if year=='2026' else year)+' | '+' | '.join(pct(result['accounts'][c]['yearly'][year]['return_fraction']) for c in ['base','stress'])+' |')
    lines+=['','## Comparison with stock exposure','','The reference replaces the stock leg with the equal mean return of the same prior-cut eligible cohort, using the strategy’s actual prior-close stock exposure. It subtracts the same dated fee/slippage rate relative to original strategy NAV. It is fractional attribution, not an executable whole-share portfolio, and does not remove sector or beta differences.','','| New-window attribution | Base | Stress |','|---|---:|---:|']
    for label,key in [('Reference ending value','ending_nav'),('Strategy minus reference','selection_difference')]:
        lines.append('| '+label+' | '+' | '.join(money(result['exposure_references'][c][key]) for c in ['base','stress'])+' |')
    for cost in ['base','stress']:
        b=result['exposure_references'][cost];interval=result['selection_uncertainty'][cost]['interval']
        if not b['complete']:lines+=['',f'{cost.title()} reference is incomplete: `{json.dumps(b["first_gap"],sort_keys=True)}`. No full-period selection advantage is claimed.']
        if interval:
            lo,hi=interval['ci95'];lines+=['',f'{cost.title()} mean monthly strategy-minus-reference return: {pct(interval["mean"])}; 95% stationary-block interval [{pct(lo)}, {pct(hi)}], using {interval["months"]} fully observed months. September 2026 is excluded from this monthly interval. Few years and market dependence limit inference.']
    lines+=['','## Already-seen 2022–2023 comparison','','| Earlier diagnostic | Base | Stress |','|---|---:|---:|',
            '| Net profit | '+' | '.join(money(previous['accounts']['fixed-'+c]['profit']) for c in ['base','stress'])+' |',
            '| Annualized return | '+' | '.join(pct(previous['accounts']['fixed-'+c]['cagr']) for c in ['base','stress'])+' |',
            '','These earlier results are unchanged. The new account starts from $10,000 in 2024; this report does not splice the two separately liquidated accounts into a continuous 2022–2026 trading return.','',
            '## Coverage and accounting','',
            f'All 3,300 original company-month slots are retained. Monthly eligible counts range from {min(x["eligible"] for x in coverage["monthly"])} to {max(x["eligible"] for x in coverage["monthly"])} out of the original 100. The cohort was selected from a 2018 roster; it is not the full current market or a retrospective list of AI winners.','',
            '| Period | Eligible company-months | Known full-month labels |','|---|---:|---:|']
    for year in ['2024','2025','2026']:
        months=[x for x in coverage['monthly'] if x['month'].startswith(year) and x['month']!='2026-09']
        lines.append(f'| {year if year!="2026" else "2026 through August"} | {sum(x["eligible"] for x in months)} | {sum(x["known_labels"] for x in months)} |')
    lines+=['','Newer splits and corporate events are listed in [recent_sources.py](recent_sources.py). Unqualified held distributions or missing marks leave account performance unresolved; those holdings are not deleted. Known dividends without supported payment dates remain non-spendable receivables. Cash and receivables earn zero interest. Returns include the declared trading costs but exclude personal taxes.','',
            'Costs preserve the earlier IBKR Pro Fixed counterfactual plus 10/50 basis points of slippage per side. These are historical close-based execution proxies, not verified broker fills or actual account tariffs. The account keeps a $2,000 settled-cash reserve and a permanent $2,000 trailing dollar-loss halt; that halt is not a guaranteed maximum realized loss.','',
            f'Acquisition used {len(pm["requests"])} Tiingo price requests in this scope (including the original three probes) and {len(sm)} SEC company-fact responses. New paid data cost: $0. API limits were respected; calendar waiting is not research effort.','',
            '## Verification','',
            f'Before outcomes: {load(HERE/"verification-before.json")["financial"]["components"]:,} financial components passed filing-date checks; independent percentile arithmetic checked every eligible score; future labels could not alter scores. Synthetic checks cover execution timing, costs, splits and unresolved distributions.','']
    for cost,check in verification['accounts'].items():
        lines.append(f'- {cost.title()}: {check["nav_days"]}/{check["total_days"]} daily NAV observations and {check["fills"]} fills reconciled independently; '+('complete account.' if check['complete'] else 'valid prefix only.'))
    lines+=['','Source and implementation hashes are in [evaluation-freeze.json](evaluation-freeze.json). Original experiment artifacts remain byte-for-byte unchanged. Raw provider data and account ledgers remain local and gitignored.','']
    decision={'funded_ready':False,'reason':'Historical result requires interpretation alongside coverage, attribution uncertainty, execution assumptions and risk; no funding follows automatically.',
              'account_complete':{c:result['accounts'][c]['status']=='COMPLETE_ACCOUNTING' for c in ['base','stress']},
              'annualized_above_4_percent':{c:(result['accounts'][c]['cagr']>.04 if result['accounts'][c]['cagr'] is not None else None) for c in ['base','stress']},
              'annualized_above_6_percent':{c:(result['accounts'][c]['cagr']>.06 if result['accounts'][c]['cagr'] is not None else None) for c in ['base','stress']},
              'model_fits':0,'parameter_searches':0,'new_paid_data_usd':0,'commit_before_work':'95dd022'}
    write(HERE/'decision.json',decision)
    if all(decision['account_complete'].values()):
        interpretation='The fixed strategy '+('exceeded 6% annualized in both cost cases' if all(decision['annualized_above_6_percent'].values()) else 'did not exceed the full 6% annual target in both cost cases')+' in the new window. This is evidence about this frozen implementation, not a funded-trading approval.'
    else:interpretation='Full account profitability remains unresolved in at least one cost case. Do not label missing accounting as a measured strategy loss or success.'
    lines[2:2]=[interpretation,'']
    (HERE/'RESULTS.md').write_text('\n'.join(lines))
    fig,ax=plt.subplots(figsize=(10,5.5))
    colors={'base':'#235b95','stress':'#bd5c31'}
    for cost in ['base','stress']:
        account=load(ROOT/result['account_files'][cost]['file']);valid=[d for d in account['daily'] if d['nav'] is not None]
        ax.plot(pd.to_datetime([d['date'] for d in valid]),[float(d['nav']) for d in valid],label=f'Fixed score — {cost}',color=colors[cost])
        paths=load(RAW/f'{cost}-reference-path.json')
        ax.plot(pd.to_datetime([d['date'] for d in paths]),[d['reference_nav'] for d in paths],label=f'Exposure reference — {cost}',color=colors[cost],ls='--',alpha=.65)
    ax.axhline(10000,color='#777777',lw=.8);ax.set_title('Frozen fixed score: 2024–September 11, 2026');ax.set_ylabel('Account value ($)');ax.grid(alpha=.15);ax.legend(fontsize=9)
    fig.text(.01,.01,'Base/stress include declared costs. References are attribution only. Gaps are not filled; cash earns zero.',fontsize=8)
    fig.tight_layout(rect=(0,.035,1,1));fig.savefig(HERE/'account-paths.png',dpi=160);plt.close(fig)
    lines.extend(['![Account and reference paths](account-paths.png)',''])
    (HERE/'RESULTS.md').write_text('\n'.join(lines))
    manifest={str(p.relative_to(ROOT)):sha(p) for p in HERE.iterdir() if p.is_file() and p.name!='artifact-manifest.json'}
    write(HERE/'artifact-manifest.json',dict(files=manifest,original_artifacts_unchanged=True))
    print(json.dumps(decision,indent=2))


if __name__=='__main__':main()
