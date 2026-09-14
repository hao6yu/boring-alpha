"""Check persisted results and render the full, non-selected comparison."""
from datetime import date,datetime,timezone
from decimal import Decimal as D
import math
from prepare import HERE,ROOT,RAW,load,sha,write,intact
from compare_support import verify_freezes,saved


def main():
    verify_freezes()
    for path,digest in load(HERE/'adapter-freeze.json')['files'].items():assert sha(ROOT/path)==digest,path
    windows={w:load(HERE/f'{w}-results.json') for w in ('old','recent')}
    frozen=load(HERE/'evaluation-freeze.json');observations=[];central=[]
    for window,result in windows.items():
        assert [r['name'] for r in result['cases']]==[r['name'] for r in frozen['cases'][window]]
        for case in result['cases']:
            for variant,v in case['variants'].items():
                a=saved(v['account_file']);paths=saved(v['reference_file']);m=v['metrics'];ledger=v['verification']['ledger']
                assert a['status']==m['status']
                assert len(paths)==v['reference']['days']
                assert sum(f['side']=='buy' for f in a['fills'])==ledger['buys_in_frozen_top_decile']==m['buys']
                complete=a['status']=='COMPLETE_ACCOUNTING'
                assert complete==ledger['complete']
                if window=='old':
                    pre_event=next(r for r in a['daily'] if r['date']=='2022-02-28')
                    assert 'ZBH' not in pre_event['holdings']
                if variant=='before':assert v['verification']['baseline_exactly_reproduced']
                if complete:
                    navs=[D(10000)]+[D(d['nav']) for d in a['daily']]
                    profit=float(navs[-1]-10000);high=navs[0];drawdown=D(0)
                    for nav in navs[1:]:high=max(high,nav);drawdown=max(drawdown,1-nav/high)
                    days=(date.fromisoformat(a['daily'][-1]['date'])-date.fromisoformat(a['daily'][0]['date'])).days+1
                    annual=(float(navs[-1])/10000)**(365/days)-1
                    assert abs(profit-m['profit'])<1e-8 and abs(annual-m['cagr'])<1e-12 and abs(float(drawdown)-m['max_drawdown'])<1e-12
                    assert v['reference']['complete']
                    assert abs(m['final_nav']-v['reference']['ending_nav']-v['reference']['selection_difference'])<1e-8
                    assert len(v['monthly'])=={'old':24,'recent':32}[window]
                else:
                    assert all(m[k] is None for k in ('profit','cagr','max_drawdown','final_nav'))
                    assert v['reference']['selection_difference'] is None and case['comparison']['full_period_comparison'] is None
                for row in v['monthly']:assert row['month']!='2026-09'
                observations.append(dict(window=window,case=case['name'],variant=variant,complete=complete,
                    account_sha256=v['account_file']['sha256'],days=ledger.get('nav_days',ledger.get('days_reconciled')),
                    fills=ledger.get('fills',ledger.get('fills_checked')),stopped=m['stopped']))
            comparison=case['comparison']
            if comparison['complete']:
                before=case['variants']['before'];after=case['variants']['after']
                assert abs(after['metrics']['profit']-before['metrics']['profit']-comparison['after_minus_before']['profit'])<1e-9
            if case['name'] in load(HERE/'protocol.json')['central_cases'][window]:central.append((window,case))
    assert len(observations)==60 and sum(o['complete'] for o in observations)==56
    counts=dict(account_case_replays=60,complete_account_cases=56,unresolved_account_prefixes=4,
        unique_account_payloads=len({o['account_sha256'] for o in observations}),
        baseline_account_cases_exactly_reproduced=30,
        priced_nav_observations_reconciled=sum(o['days'] for o in observations),
        fills_recomputed_across_cases=sum(o['fills'] for o in observations),
        note='Repeated sensitivity cases are not independent observations or new strategy trials.')
    result=dict(status='PASS_WITH_EXPLICIT_UNRESOLVED_STRICT_CASES',counts=counts,accounts=observations,
        prior_artifacts_unchanged=len(intact()['prior_files']),input_and_evaluation_freezes_intact=True,
        independent_metrics_from_saved_ledgers=True,all_scenarios_reported=True,
        every_verified_repair_used=True,remaining_unqualified_fields_still_missing=True,
        no_new_network_data_requests=True,new_paid_data_usd=0,model_fits=0,parameter_searches=0,
        source_audit='../financial-fix-comparison-2026-09-14/provenance-verification.json',
        arithmetic_adapter='adapter-freeze.json',finished_utc=datetime.now(timezone.utc).isoformat())
    write(HERE/'verification.json',result)
    recent_cases=[x for x in windows['recent']['cases'] if not x['name'].startswith('strict-')]
    assert all(x['comparison']['after_minus_before']['profit']<0 for x in recent_cases)
    assert all(x['variants']['after']['reference']['selection_difference']<0 for x in recent_cases)
    decision=dict(status='REPAIRS_TESTED_NO_RETURN_IMPROVEMENT',
        conclusion='Verified repairs reduce profit in both windows. Recent selection falls further behind its exposure/cost-matched reference. Historical results do not justify funding or scaling this strategy.',
        data_policy='Retain the verified repairs as a separately versioned research input; preserve the original baseline as a comparator. Do not prefer missing-data inputs merely because their seen backtest is higher.',
        scope_correction='The earlier 28/28 fixture gate was an assistant-imposed extraction-completeness requirement, not a necessary condition for this missing-aware controlled comparison. Its failure remains recorded.',
        unresolved='Whirlpool January 2026 earnings stay missing; strict recent corporate-action accounting remains unresolved in both variants.',
        interpretation='Exploratory, already-seen historical data; no fresh out-of-sample evidence; selection reference is an attribution diagnostic, not an executable alternative portfolio.',
        follow_on='This input-repair question is complete. A prospective locked strategy-versus-control paper test is a possible next research question, but has not been started or scheduled.',
        all_recent_conditional_cases=12,all_recent_profit_deltas_negative=True,all_recent_selection_differences_negative=True,
        new_paid_data_usd=0,new_network_requests=0,new_model_fits=0,parameter_searches=0)
    write(HERE/'decision.json',decision)
    money=lambda x:'unresolved' if x is None else (f'−${abs(x):,.2f}' if x<0 else f'${x:,.2f}')
    pct=lambda x:'unresolved' if x is None else f'{100*x:.2f}%'
    def ci(x):return f'{x["mean"]*10000:+.3f} [{x["ci95"][0]*10000:+.3f}, {x["ci95"][1]*10000:+.3f}]'
    lines=['# Verified-input comparison: better data did not improve returns','',
        'The already-authorized before/after comparison is complete. Applying all 189 verified repairs lowers net profit in both periods. Recent stock selection falls further behind the matched reference. The improved source coverage is useful research infrastructure, but this is not an improved income strategy.','',
        '## Why the earlier work stopped','',
        'The assistant incorrectly treated a 28/28 extraction-completeness gate as a prerequisite for any return comparison. The original fixed score already assigns missing financial features a neutral contribution. We can therefore test all verified repairs while leaving unqualified values missing, with exactly the same cohort and strategy rules. No further user information or account access was needed.','',
        'The earlier failed gate is preserved in the [accounting follow-up](../financial-fix-comparison-2026-09-14/RESULTS.md). It still prevents a claim that extraction is complete. Whirlpool January 2026 earnings remain missing in both variants. No tolerance was widened and no company/month was removed. The limited comparison scope was frozen before evaluating revised returns.','',
        '## Central cases: $10,000 starting account','',
        'These are net of the frozen trading fees and slippage, before taxes, without cash interest or new data charges. The old window is January 3, 2022–December 29, 2023; the recent window is January 2, 2024–September 11, 2026. Recent central results use the previously declared cash1/delay5 conditional settlement assumptions.','',
        '| Window / costs | Profit before | Profit after | Change | Annualized before → after | Max drawdown before → after |',
        '|---|---:|---:|---:|---:|---:|']
    for window,c in central:
        b,a=(c['variants'][v]['metrics'] for v in ('before','after'))
        lines.append(f'| {"2022–2023" if window=="old" else "2024–2026"} / {c["cost"]} | {money(b["profit"])} | {money(a["profit"])} | {money(a["profit"]-b["profit"])} | {pct(b["cagr"])} → {pct(a["cagr"])} | {pct(b["max_drawdown"])} → {pct(a["max_drawdown"])} |')
    lines += ['', 'No complete account hit the frozen $2,000 trailing-dollar halt. Recent drawdown falls slightly, but the revised stressed return is below the 4% cash hurdle and the revised base return is below 6%. Ending NAV includes unpaid dividend/merger entitlements and final sale proceeds; it is not all immediately withdrawable cash. These are separate accounts starting at $10,000, not one continuous 2022–2026 investment.','',
        '## Stock selection, trading and uncertainty','',
        'The reference uses the unchanged eligible universe at each account’s own prior-day stock exposure and subtracts its actual dated fee/slippage rate. Positive selection dollars mean the strategy finishes ahead of this diagnostic; negative dollars mean it trails. This reference is not executable and does not adjust for sectors, beta or other factor exposures.','',
        '| Window / costs | Selection dollars before → after | Fills before → after | Mean stock exposure before → after | Fees + slippage before → after |',
        '|---|---:|---:|---:|---:|']
    for window,c in central:
        b,a=(c['variants'][v] for v in ('before','after'));bm,am=b['metrics'],a['metrics']
        lines.append(f'| {window} / {c["cost"]} | {money(b["reference"]["selection_difference"])} → {money(a["reference"]["selection_difference"])} | {bm["fills"]} → {am["fills"]} | {pct(bm["mean_stock_exposure"])} → {pct(am["mean_stock_exposure"])} | {money(bm["fees"]+bm["slippage"])} → {money(am["fees"]+am["slippage"])} |')
    lines += ['', 'In the recent base case, extra fees/slippage account for only $2.81 of the $388.66 decline in profit. The weaker portfolio path, rather than an added data bill, explains most of the difference. Higher trading costs can change later whole-share sizing; base/stress are complete separate simulations. Turnover and every dated trade are retained in the JSON results and account files.','',
        'The paired bootstrap resamples the same months in both versions: 2,000 stationary resamples, expected block length 12 months, seed 20260914. It uses 24 old months and 32 complete recent months, excluding unfinished September 2026. The following are mean monthly changes in **basis points**, with 95% intervals; they are not annual-return intervals.','',
        '| Window / costs | Strategy return change, after − before | Selection return change, after − before |',
        '|---|---:|---:|']
    for window,c in central:
        p=c['comparison'];lines.append(f'| {window} / {c["cost"]} | {ci(p["strategy_return_change_interval"])} | {ci(p["selection_return_change_interval"])} |')
    lines += ['', 'All central paired intervals include zero. The recent selection interval’s positive endpoint is very close to zero; this does not justify a strong statistical conclusion in either direction. Individual before/after selection intervals and all monthly observations are saved as well. All these years have been seen, there are few independent market regimes, and intervals do not correct for earlier strategy searches. This test establishes the historical effect of this specific input repair, not future profitability.','',
        '## Every declared scenario','',
        'All seven old ZIMV cash/receipt scenarios are unchanged from the old strict result because neither version held ZBH at that event. They do not add independent performance evidence. Recent strict accounts remain unresolved from the held PXD conversion on May 3, 2024, in both variants. Their full-period profit and selection values remain null. Conditional completion is explicitly hypothetical about fractional cash and stock availability; it is not verification of actual broker receipts.','',
        '| Window / scenario | Before profit | After profit | After annualized | After selection dollars |',
        '|---|---:|---:|---:|---:|']
    for window,data in windows.items():
        for c in data['cases']:
            b,a=(c['variants'][v] for v in ('before','after'))
            lines.append(f'| {window} / {c["name"]} | {money(b["metrics"]["profit"])} | {money(a["metrics"]["profit"])} | {pct(a["metrics"]["cagr"])} | {money(a["reference"]["selection_difference"])} |')
    lines += ['', 'All 12 recent conditional cases earn less after repairs and trail the matched reference. Results are not selected for the best settlement assumption. No incomplete account was dropped or converted to a cash-only result.','',
        '## Data and verification','',
        'All 5,700 original company-month slots remain. Every one of the 189 recovered fields enters its eligible feature slot: 86 old and 103 recent. There are 142 affected company-months across 13 issuers. Market-cap denominators, the other four features, eligibility, score weights, ranking rules, prices and portfolio policies are unchanged. Cross-sectional ranks can change for issuers whose own inputs were not repaired. Entry lists change in 8 of 24 old months and 13 of 33 recent months; retention lists change in 16 and 17 months respectively.','',
        'Book-equity coverage rises from 39.5% to 41.0%, and trailing-earnings coverage from 43.7% to 45.5%. Coverage remains limited. The preceding numeric source audit verified all 189 repairs; this comparison does not claim to have repaired every missing input.','',
        f'{counts["baseline_account_cases_exactly_reproduced"]} baseline account cases exactly reproduce their saved objects. Across all 60 configured before/after replays, 56 are complete and four retain explicit unresolved prefixes. Independent Decimal ledger checks reconcile {counts["priced_nav_observations_reconciled"]:,} priced daily observations and recompute {counts["fills_recomputed_across_cases"]:,} fills across those cases. There are {counts["unique_account_payloads"]} distinct serialized account payloads; repeated scenarios are not independent tests. Frozen top-decile entry membership, position caps, cash, whole-share units, costs and complete-period summary metrics are checked.','',
        'The input panels and schedules were frozen before revised account evaluation. All 151 protected prior artifacts and frozen source hashes remain unchanged. A documented adapter restored the original completion benchmark’s floating-point summation order after a 1.11e-16 weight mismatch; account objects, signals and economic assumptions were unchanged. The original frozen code and failure stage are preserved in `adapter-freeze.json`.','',
        '**New network data requests: 0. New paid data: $0. Model fits: 0. Parameter searches: 0.**','',
        '## Decision','',
        'Keep the verified repairs as a separately versioned research input and preserve the original baseline for comparison. Do not discard accurate inputs just because the older missing-data version backtests better. This round did not improve the strategy’s return case and does not justify a funded bot or capital scaling.','',
        'The input-repair question is now answered. A future, locked strategy-versus-control paper test could assess signal availability and execution, but it has not been started or scheduled and a short paper run would not prove annual outperformance. No further parser loop or vendor search is needed to finish this comparison.','']
    (HERE/'RESULTS.md').write_text('\n'.join(lines))
    (HERE/'README.md').write_text('''# Verified financial-input comparison\n\nRead [RESULTS.md](RESULTS.md) for the complete before/after assessment and [decision.json](decision.json) for the research decision.\n\n`protocol.json` preserves the scope clarification and prior file hashes. `prepare.py` produced the frozen panels/schedules and 189-field change list. `worker.py` replays the original account engines. `resume_recent.py` reuses the original floating-point reference implementation; its bounded arithmetic correction is recorded in `adapter-freeze.json`. `finalize.py` verifies saved results and renders the report.\n\nThe old and recent workers must run in separate Python processes because the original recent adapter changes module globals. The existing freezes and result files intentionally prevent silent overwrites. `finalize.py` can regenerate summaries from the saved accounts without trading simulation or network access.\n\nRaw panels, schedules, predictions, account ledgers and reference paths are in `data/snapshots/verified-input-comparison-2026-09-14/`, under the existing ignored snapshot policy. Their hashes are recorded in the freezes and result files. No credentials are required by the offline comparison.\n''')
    paths=sorted(p for p in HERE.iterdir() if p.is_file() and p.name!='artifact-manifest.json')
    rawpaths=sorted(p for p in RAW.iterdir() if p.is_file())
    write(HERE/'artifact-manifest.json',dict(files={str(p.relative_to(ROOT)):sha(p) for p in paths},raw_files={str(p.relative_to(ROOT)):sha(p) for p in rawpaths},raw_files_gitignored=True))
    verify_freezes();print(counts)

if __name__=='__main__':main()
