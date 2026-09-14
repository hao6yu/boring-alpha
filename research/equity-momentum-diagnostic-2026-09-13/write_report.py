"""Render the preserved diagnostic; does not run or modify the strategy."""
from datetime import datetime, timezone
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

from momentum_io import HERE, ROOT, SOURCE_HERE, POLICY_SHA, atomic, digest, policy


def run():
    spec = policy()
    result = json.loads((HERE / 'evaluation-result.json').read_text())
    verification = json.loads((HERE / 'account-verification.json').read_text())
    assert verification['result_sha256'] == digest(HERE / 'evaluation-result.json')
    base, stress = [result['accounts'][c]['momentum'] for c in ('base', 'stress')]
    ledgers = {}
    for cost in ('base', 'stress'):
        ref = result['ledgers'][cost]['momentum']
        assert digest(ROOT / ref['path']) == ref['sha256']
        ledgers[cost] = json.loads((ROOT / ref['path']).read_text())

    fig, ax = plt.subplots(figsize=(10.8, 5.5), layout='constrained')
    dates = [datetime.fromisoformat(r['date']) for r in ledgers['base']['daily']]
    elapsed = [(d - dates[0]).days + 1 for d in dates]
    for rate, color in [(0.06, '#669583'), (0.04, '#94b5a7')]:
        ax.plot(dates, [10000 * (1 + rate) ** (d / 365) for d in elapsed],
                color=color, linewidth=1.5, label=f'{rate:.0%} constant cash reference')
    for cost, color, style in [('base', '#2459a6', '-'), ('stress', '#ca6944', '--')]:
        ax.plot(dates, [float(r['nav']) for r in ledgers[cost]['daily']],
                color=color, linestyle=style, linewidth=1.8, label=f'Momentum: {cost} costs')
    halt = datetime(2022, 5, 9)
    ax.axvline(halt, color='#7a7f87', linewidth=.8, linestyle=':')
    ax.annotate('Loss halt: May 9, 2022\nLiquidated next session', xy=(halt, 8080),
                xytext=(datetime(2022, 8, 1), 9150), fontsize=10,
                arrowprops={'arrowstyle': '->', 'color': '#555b63'}, color='#333a43')
    ax.set(title='Fixed stock momentum diagnostic · $10,000 simulated account', ylabel='Account value, including verified cash claims')
    ax.set_xlim(dates[0], dates[-1])
    ax.set_ylim(7600, 11500)
    ax.yaxis.set_major_formatter(StrMethodFormatter('${x:,.0f}'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.grid(axis='y', alpha=.18)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(loc='upper left', frameon=False, fontsize=9)
    fig.supxlabel('Jan 2022–Dec 2023 · zero interest on strategy cash · reference rates are scenarios, not historical yields', fontsize=9)
    fig.savefig(HERE / 'account-value.png', dpi=160)
    plt.close(fig)

    evidence = json.loads((SOURCE_HERE / 'corporate-action-evidence.json').read_text())
    transition = next(r for r in evidence['security_status_events'] if r['security_id'] == '0001091907:single_common' and r['status'] == 'halted')
    manifest = json.loads((SOURCE_HERE / 'price-manifest.json').read_text())
    assert 'TKO' not in manifest['symbols']
    atomic(HERE / 'control-coverage-gap.json', {
        'status': 'FULL_CONTROL_COMPARISON_UNRESOLVED', 'policy_sha256': POLICY_SHA,
        'affected_controls_per_cost_case': ['unranked_00', 'unranked_10'],
        'first_unpriced_date': '2023-09-12', 'old_security_id': '0001091907:single_common',
        'held_old_shares_per_account': 15, 'source_status_record': transition,
        'qualified_successor_price_history_in_frozen_manifest': False,
        'corporate_action_evidence_sha256': digest(SOURCE_HERE / 'corporate-action-evidence.json'),
        'price_manifest_sha256': digest(SOURCE_HERE / 'price-manifest.json'),
        'resolution': 'Preserve missing NAVs and old-unit transition claim. No synthetic cash exit, stale-price fill, new provider request, control deletion, or post-result parameter change.'})

    rows = []
    for seed in range(20):
        name = f'unranked_{seed:02}'
        values = [result['accounts'][c][name] for c in ('base', 'stress')]
        def ending(a):
            return f"${a['ending_nav_usd']:,.2f}" if a.get('ending_nav_usd') is not None else 'Unresolved'
        def status(a):
            return 'Incomplete' if not a['daily_nav_complete'] else ('Halted' if a['stopped'] else 'Completed')
        rows.append(f'| {seed:02} | {ending(values[0])} | {status(values[0])} | {ending(values[1])} | {status(values[1])} |')
    control_table = '\n'.join(rows)
    now = datetime.now(timezone.utc)
    minutes = (now - datetime.fromisoformat(spec['work_started_at_utc'])).total_seconds() / 60
    text = f'''# Fixed stock momentum diagnostic: negative observed result

The $10,000 momentum account lost **$1,938.22 under base costs** and **$1,976.70 under stressed costs**. Both hit the $2,000 trailing-loss halt on May 9, 2022 and liquidated on May 10. **Shelve this implementation.** These results do not support funding or tuning it on the same history.

The momentum accounts have complete conditional accounting. The full comparison with unranked stocks remains **unresolved** because two of the 20 predeclared control baskets need an unimplemented WWE-to-TKO share transition and absent TKO prices. No controls were dropped to produce a more favorable comparison.

## Measured account economics

Evaluation: January 3, 2022–December 29, 2023, 501 trading sessions. After the halt, the accounts remain in cash and verified receivables for the rest of the window.

| Metric | Base costs | Stressed costs |
|---|---:|---:|
| Ending account value | ${base['ending_nav_usd']:,.2f} | ${stress['ending_nav_usd']:,.2f} |
| Net profit / loss | ${base['net_profit_usd']:,.2f} | ${stress['net_profit_usd']:,.2f} |
| Total return | {base['total_return']:.2%} | {stress['total_return']:.2%} |
| Annualized return over full window | {base['cagr']:.2%} | {stress['cagr']:.2%} |
| Maximum peak-to-trough drawdown | {base['max_drawdown_fraction']:.2%} | {stress['max_drawdown_fraction']:.2%} |
| Maximum dollar drawdown | ${base['max_drawdown_usd']:,.2f} | ${stress['max_drawdown_usd']:,.2f} |
| Closed positions | {base['completed_positions']} | {stress['completed_positions']} |
| Commissions and regulatory fees | ${base['commissions_and_regulatory_usd']:,.2f} | ${stress['commissions_and_regulatory_usd']:,.2f} |
| Assumed slippage | ${base['slippage_usd']:,.2f} | ${stress['slippage_usd']:,.2f} |
| Profit / loss adding back costs on identical fills | ${base['gross_same_fills_profit_usd']:,.2f} | ${stress['gross_same_fills_profit_usd']:,.2f} |
| Ending settled cash | ${base['ending_settled_cash_usd']:,.2f} | ${stress['ending_settled_cash_usd']:,.2f} |
| Ending dividend receivables | $24.62 | $24.62 |

Costs are not the principal explanation: even adding back every modeled fee and slippage charge leaves a base loss of $1,895.01. This is an accounting decomposition of the same fills, not a new zero-cost simulation. Stress costs also change affordable entries, so the accounts have different trades.

The trailing-loss threshold is observed at closing marks, with liquidation at the next executable session. The $28.48/$34.10 overshoot demonstrates why it is not a guaranteed loss ceiling. The subsequent liquidation close recovered part of that drawdown. Only one completed position was profitable in each cost case; all stock positions were closed by May 10, 2022.

Constant 4% and 6% annual cash reference scenarios end at **$10,811.35** and **$11,228.83** over the same 726 inclusive calendar days. These are comparison assumptions, not historical yields or an account-specific available rate. Strategy cash earns zero in this registered test; tax and operating expenses are excluded. Annualized returns include the long inactive period after the halt.

![Simulated account values](/Users/haoyu/development/boring-alpha/research/equity-momentum-diagnostic-2026-09-13/account-value.png)

## What was fixed before calculation

Rank the same 200 historical incumbent issuers by 11 months of adjusted-close return, skipping the latest month. For January 2022, the score is November 30, 2021 adjusted close divided by December 31, 2020 adjusted close, minus one. Enter the top 10% of eligible names and retain holdings while they remain in the top 20%, with monthly review, ceiling-rounded rank bands, and predetermined tie-breaking.

Use at most ten stock positions. Each new position receives at most $800, 8% of prior account value, and available settled cash above a $2,000 reserve. Whole-share quantities are committed before the entry session; a budget-based closing-limit proxy can cancel an entry. Retained positions drift without monthly resizing. Exiting positions occupy a slot through that day's fill; replacement waits until a later monthly review. Sale proceeds are locked for seven calendar days in the model. The permanent $2,000 trailing dollar-loss halt and final-window liquidation apply to every account.

Base/stress slippage is 10/50 basis points per side, plus the archived IBKR Pro Fixed commission/regulatory schedule. It is a current-rate counterfactual, not a reconstruction of historical fees or confirmation of the user's tariff. Verified corporate-action entitlements enter account value; spendability requires separate evidence. Unknown dividend payment dates leave receivables unavailable for reinvestment. No leverage or cash interest is used.

The lagged-return definition comes from [Open Source Asset Pricing's Mom12m implementation](https://github.com/OpenSourceAP/CrossSection/blob/master/Signals/pyCode/Predictors/Mom12m.py); this version requires complete formation history instead of imputing missing returns as zero. Separate entry and retention thresholds follow the trading-cost principle studied by [Novy-Marx and Velikov](https://doi.org/10.1093/rfs/hhv063). The long-only account, fixed cohort, and sizing are our adaptation, not a replication or a claim to reproduce published returns. Momentum is related to previously explored ETF, crypto, and futures families in this repository.

## Coverage and all controls

All **4,800 issuer-month slots** are preserved: 2,516 ready, 491 known listing-ineligible, 1,131 liquidity-ineligible, and **662 unresolved** (645 liquidity-price gaps, 17 formation-price gaps). Monthly qualified breadth ranges from 97 to 116 issuers. Missing slots are not classified as economically ineligible. The measured account is conditional on this qualified subset; missing opportunities could change rankings and trades. A fixed 2019 incumbent cohort is not a comprehensive, survivorship-free US market universe.

Each control is a separate simulated $10,000 account with the same eligibility, account rules, entry/retention fractions, costs and halt. Momentum order is replaced by a stable hash order using predeclared seeds 0–19. These 20 hypothetical accounts are comparison references, not a proposed pooled $200,000 portfolio.

| Control seed | Base ending value | Base status | Stress ending value | Stress status |
|---|---:|---|---:|---|
{control_table}

Controls 00 and 10, in each cost case, hold 15 old WWE shares at the September 12, 2023 transition. The archived [NYSE removal notice](https://corporate.wwe.com/f/docs/sec-filings/16925127.PDF) records their exchange for TKO shares. The frozen manifest has no TKO history, and the engine cannot silently treat a different issuer as the old security. Their NAVs remain missing from that date. See `control-coverage-gap.json` for the exact source record and hashes.

As registered, no full-ensemble average, paired confidence interval, or ranking-edge conclusion is computed from only the 18 complete controls. The negative momentum account is enough to decline this implementation for the user's objective; it does not resolve momentum's incremental return against the full control set.

## Verification, scope, and decision

Eight synthetic tests passed covering timing, missing history, rank bands, retention, cash settlement, fixed entry quantities, position/cash limits, halt execution, and fractional splits. A separate verifier recalculated 2,516 admitted scores and all 504 monthly model rankings from the frozen inputs and underlying prices. It also reconciled **38 complete accounts** (two momentum plus 36 controls), and the valid prefixes of four incomplete control runs: 20,734 daily NAV observations and 952 fills. It rechecked 124 raw price-file hashes, fees, cash claims, held units, verified splits, cash mergers, and first halt dates.

For cash-merger controls, the verifier includes merger-terminated lots when reconciling total P&L; the inherited `completed_positions` convenience field counts sell-filled closures only. This does not alter account NAV. Verification uses the same cached evidence and is not external data replication. Strategy code, source adapter code, policy, inputs and result hashes are unchanged. Details: `account-verification.json` and `verify_accounts.py`.

This is one exploratory diagnostic on already-examined 2022–2023 history. The early permanent halt means it does not measure an uninterrupted strategy through 2023. It neither validates a live execution model nor establishes that stock momentum generally fails. Increasing capital, relaxing the halt, changing ranks, or adding an overlay would be new hypotheses, not repairs to this result.

**Decision: shelve this exact implementation; no deployment or further variants are justified by this run.** Preserve the partial comparison and existing failures. A broader claim about the family remains unsupported. Reserved 2024–2025 strategy prices remain unopened.

New paid data: **$0**. Reporting checkpoint: **{minutes:.1f} minutes** from the recorded start, within the two-hour cap. No new market-data request or purchase was made. The policy was registered at {spec['registered_at_utc']}; calculation began at 00:32:01 UTC on September 14, 2026. The folder uses the local September 13 date.

Policy SHA-256: `{POLICY_SHA}`.
'''
    (HERE / 'RESULTS.md').write_text(text)
    decision = {'status': 'SHELVE_FIXED_IMPLEMENTATION_NEGATIVE_OBSERVED_ECONOMICS',
        'decided_at_utc': now.isoformat(), 'elapsed_minutes_to_report': minutes,
        'policy_sha256': POLICY_SHA, 'result_sha256': digest(HERE / 'evaluation-result.json'),
        'verification_sha256': digest(HERE / 'account-verification.json'),
        'new_paid_data_usd': 0, 'full_control_comparison': 'UNRESOLVED_WWE_TKO_TRANSITION',
        'further_variants_run': False, 'reserved_2024_2025_strategy_prices_opened': False,
        'interpretation': 'Complete conditional momentum accounts are negative; full-universe opportunity coverage and full-control ranking edge remain unresolved. No general rejection of stock momentum.'}
    atomic(HERE / 'decision.json', decision)
    print(json.dumps(decision))


if __name__ == '__main__':
    run()
