#!/usr/bin/env python3
"""Render the measured result after verification; no strategy selection here."""
from datetime import datetime,timezone
import json
from pathlib import Path
from models import HERE,ROOT,RAW
from probe import sha,write

def main():
    r=json.loads((HERE/'evaluation-result.json').read_text());v=json.loads((HERE/'account-verification.json').read_text());assert v['passed']
    coverage=json.loads((HERE/'panel-coverage.json').read_text());pm=json.loads((HERE/'price-manifest.json').read_text())
    frac=lambda x:'unresolved' if x is None else f'{x:.2%}'
    money=lambda x:'unresolved' if x is None else f'${x:,.2f}'
    diag=[x for x in coverage['monthly'] if x['month']>='2022-01'];active=sum(x['eligible'] for x in diag)
    lines=['# Fixed 100-stock monthly model comparison','',
           '**The registered linear/tree/fixed-score comparison has been run on the identified eligible subset. These are exploratory 2022–2023 results, not a validation pass or live-trading approval.**','',
           f'The original 100 security slots remain in all {coverage["rows"]:,} company-month records. Diagnostic entry eligibility ranges from {min(x["eligible"] for x in diag)} to {max(x["eligible"] for x in diag)} names per month. The predefined aggregate-coverage gate {"passes" if r["aggregate_coverage_pass"] else "does not pass; only the conditional identified-subset comparison is reported"}.','',
           '## Account outcomes','',
           'Each account starts with $10,000, holds whole shares, keeps a $2,000 settled-cash reserve and has a permanent $2,000 trailing dollar-loss halt. Base/stress slippage is 10/50 bps per side plus the preserved IBKR Pro Fixed fee scenario. These are historical close-based execution proxies; actual account fees and fills are not established.','',
           '| Ranking | Costs | Ending value | Net profit | Annualized return | Max drawdown | Halt date |','|---|---|---:|---:|---:|---:|---|']
    for name in ['ridge','tree','fixed']:
        for cost in ['base','stress']:
            a=r['accounts'][name+'-'+cost];lines.append(f'| {name} | {cost} | {money(a["final_nav"])} | {money(a["profit"])} | {frac(a["cagr"])} | {frac(a["max_drawdown"])} | {a["stop_date"] or "none"} |')
    lines+=['','Missing held marks or unqualified stock-distribution delivery/fractional cash make an account incomplete. No complete return is fabricated for such an account. Known unpaid dividends/merger claims remain in NAV but are not spendable; their payment dates were not guessed. Sale proceeds stay locked for seven calendar days. No tax estimate is included.','',
            '## Does the trained tree improve stock ranking?','',
            'The metric below is within-month Spearman correlation between predicted rank and realized excess return. Higher is better; this is not an account return. Excess returns subtract the mean of known eligible labels in that month.','',
            '| Ranking | 2022 mean correlation | 2023 mean correlation | Both years |','|---|---:|---:|---:|']
    for name in ['ridge','tree','fixed','tree_minus_ridge']:
        lines.append(f'| {name} | {r["yearly_mean_rank_correlations"]["2022"][name]:.4f} | {r["yearly_mean_rank_correlations"]["2023"][name]:.4f} | {r["rank_correlation_intervals"][name]["mean"]:.4f} |')
    delta=r['rank_correlation_intervals']['tree_minus_ridge'];lo,hi=delta['ci95']
    lines +=['',f'The 95% stationary month-block interval for the tree-minus-linear difference is [{lo:.4f}, {hi:.4f}]. It uses 2,000 resamples and expected block length 12 months. With only 24 already familiar market months, this interval has limited power and cannot establish a durable edge.','',
             '## Data and test scope','',
             '- Fixed cohort: one deterministic 100-security selection from the archived April 2018 roster; no survivor replacements or later IPO additions.',
             '- Initial training: 31 monthly labels, June 2019–December 2021; expanding annual refits for 2022 and 2023, using only completed earlier labels.',
             '- Models: Ridge alpha 100; one fixed histogram gradient boosting configuration; one fixed six-signal score. No hyperparameter search or outcome-driven feature changes.',
             '- SEC filing availability is lagged two NYSE sessions. Market cap uses a split-corrected reported-share proxy, not exact contemporaneous capitalization. Unidentified common-book or common-income fields stay missing with neutral ranks and missing indicators.',
             '- Reference return features reinvest distributions fractionally at the reference close. The whole-share account is separate. Current backfilled vendor data are not archived real-time data vintages.',
             '- Previous company failures and ticker changes are retained. Modern FOXA is excluded from the old Twenty-First Century Fox issuer. Sealed Air’s initial incorrect identifier was rejected before any features or models used it.',
             '- LyondellBasell’s January 2019 $15 vendor distribution is removed: it belongs to a subsidiary’s convertible special stock. Its June 2022 $6.39 common distribution is supported by the issuer.',
             '- The 2024–2025 strategy windows remain unopened. No broker order, new subscription or new cash data purchase occurred.','',
             f'This attempt made {len(pm["requests"])} additional Tiingo requests and reused available sample data. Acquisition obeyed the hourly quota; waiting time is not evidence of additional analysis. Source snapshots, input hashes, model refit boundaries and account replays are retained locally.','',
             '## Interpretation','']
    tree=r['accounts']['tree-base'];ridge=r['accounts']['ridge-base']
    if tree['cagr'] is None:lines.append('The tree account is incomplete; its full profitability remains unresolved. Ranking evidence can still be assessed on the documented subset, but it cannot substitute for an account result.')
    elif tree['cagr']<=.04:lines.append('The tree account did not beat the lower end of the user’s 4–6% cash hurdle. This version does not justify funding or promotion.')
    elif tree['cagr']<=.06:lines.append('The tree account exceeded 4% annualized but did not clear the upper 6% cash hurdle. This is insufficient evidence of the desired advantage.')
    else:lines.append('The tree account exceeded the 6% cash reference descriptively. That is a historical observation only; ranking contribution, drawdown, data coverage and the short seen period still determine whether separate validation is warranted.')
    if lo<=0<=hi:lines.append('The tree’s measured ranking advantage is not clearly separated from zero by the planned interval. Do not claim that the more complex model has demonstrated a reliable improvement.')
    elif hi<0:lines.append('The planned comparison favors the linear model’s ranking over the tree in this seen period.')
    else:lines.append('The planned comparison favors the tree’s ranking in this seen period, subject to the short-period and coverage limits above.')
    lines+=['','These findings concern this fixed implementation and dataset. They do not establish that quantitative trading generally works or fails. No parameter changes or reserved-year test are queued automatically.','',
            'Evidence: `panel-coverage.json`, `fit-audit.json`, `evaluation-start.json`, `evaluation-result.json`, `verification.json`, and `account-verification.json`.','',
            'Primary action sources: [LyondellBasell subsidiary distribution](https://www.lyondellbasell.com/en/news-events/corporate--financial-news/a.-schulman-inc2.-a-lyondellbasell-subsidiary-announces-convertible-special-stock-dividend), [Cerner exchange notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-127), [Kansas City Southern completion](https://www.sec.gov/Archives/edgar/data/54480/000119312521356252/d25745d8k.htm). Further reviewed facts and URLs are in `reviewed_sources.py`.']
    (HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    write(HERE/'decision.json',dict(status=r['status'],completed_at_utc=datetime.now(timezone.utc).isoformat(),models_fitted=True,new_paid_data_usd=0,
                                  aggregate_coverage_pass=r['aggregate_coverage_pass'],reserved_prices_opened=False,live_trading_approved=False,
                                  result_sha256=sha((HERE/'evaluation-result.json').read_bytes()),account_verification_sha256=sha((HERE/'account-verification.json').read_bytes())))
    print('Report written:',HERE/'RESULTS.md')

if __name__=='__main__':main()
