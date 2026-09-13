# Exploratory earnings-language execution proposal

Prepared before this candidate's training or performance calculation. This is a proposed fixed execution specification for the parent test plan to adopt and hash before P&L. It does not select the model, threshold, training dates, or eligible universe. The existing repair feature contract and source-backed ledger policy remain controlling for accounting scope, identity, availability, and corporate actions. No prices, returns, credentials, or account settings were accessed for this document.

## Account and chronology

- Start with **$5,000 cash**, whole shares, long only, no leverage, deposits, withdrawals, shorts, options, or assumed cash interest. The position purchase envelope is **$1,000 including entry costs**, with at most four occupied issuer slots. An occupied slot includes an unpriced holding or a locked merger claim. Market appreciation may take a held position above $1,000; the envelope is an entry limit, not a daily rebalance rule.
- Require at least **$1,000 unreserved, settled cash after every voluntary purchase**. Sales, dividends, and merger receivables cannot finance a purchase before their declared availability. The cash floor restricts purchases; it is not a promise that later costs or losses cannot breach it.
- Use one continuous account over the chronological evaluation window through the last declared session in **2023**. Do not reset capital, high-water marks, or a stopped account at calendar-year boundaries. Acquire/read no 2024–25 prices. Admit an event only if its planned entry plus 20 following sessions lies inside the predeclared endpoint; this is a calendar rule, not a filter based on observed subsequent outcomes.
- The model's decision uses the full original filing and permitted predecessors. Entry is the **close of the first exchange session strictly after the later of the filing date and Eastern acceptance date**, preserving the repaired daily-entry invariant where exact clocks conflict. Thus no same-day release close is available for entry. The model score, ranking, quantity, and order limit must already be committed before that entry session's close.
- Exit at the close **20 exchange-session intervals after entry**: entry index `e`, scheduled exit `e+20`. This requires 21 closes, not 20 inclusive dates. No pyramiding or resetting the clock on another release from an already held issuer. Simultaneous candidates use the parent plan's frozen score ordering, then acceptance-date ordering, CIK, and accession as deterministic ties; no future-return ranking. A candidate skipped for capacity is not queued for an opportunistic later entry.

## Integer orders without future-close sizing

Let `B=min(1000, settled_unreserved_cash-1000)` after reserving earlier ranked orders, and `Pprev` be the qualified raw close of the preceding session. Fix the largest integer `q` satisfying

`q*Pprev*1.005 + max(1, 0.005*q) + ceil_cent(0.000003*q) <= B`.

If no positive integer fits, do not trade. The 0.5% cushion is the declared stressed entry slippage below; it is not an estimated gap bound. Fix the all-in order budget `B` and quantity `q`; never recompute `q` using the entry close. Evaluate the closing-price proxy only if a qualified, positive-volume listed-session close exists. Fill the entire quantity only when `q*Pclose*1.005 + max(1,0.005*q) + ceil_cent(0.000003*q) <= B`; otherwise cancel that event's entry permanently. This is an explicitly declared **closing limit-order proxy with full-fill-or-no-fill**, not proof of auction execution or a market-on-close order. Record limit cancellations. The condition can reject upward gaps and that selection effect belongs in the result.

The budget reserves the uncapped commission, which is conservative; actual modeled commission applies the published cap below. Use the same stressed fill-eligibility guard in base and stress. Each scenario has its own chronological settled cash, so accumulated cost differences can change later quantities or participation. A separate same-fills cost decomposition may explain the fee effect, but must not replace either account.

## Costs: posted fees versus assumed execution loss

The user's IBKR plan, routing, and actual commissions are unknown. Use the paid **Pro Fixed** schedule for the primary comparison, not presumed Lite eligibility. The current official table lists $0.005/share, $1/order minimum, and 1% of trade-value maximum. Pro Tiered starts at $0.0035/share and $0.35/order but adds venue/clearing/pass-through charges; it is only an auxiliary lower-cost comparison unless routing is specified. Lite also has special closing-auction-volume conditions. These are current-rate counterfactual costs applied to historical trades, **not reconstructed 2022–23 broker invoices**. [IBKR US stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).

For `q` whole shares and modeled executed notional `V`, charge commission `min(0.01*V, max(1,0.005*q))`. Additionally use the currently posted regulatory rates: sell-side SEC `0.0000206*V`, sell-side FINRA TAF `min(9.79,0.000195*q)`, and CAT `0.000003*q` on each side. Round each nonzero fee component upward to a cent as a conservative declared modeling convention, not a claim about an actual invoice. Do not credit rebates. [IBKR fee table](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).

| Case | Buy proxy | Sell proxy | Commission/regulatory calculation |
|---|---|---|---|
| Base | raw close × 1.001 | raw close × 0.999 | Same formulas above |
| Stress | raw close × 1.005 | raw close × 0.995 | Same formulas above |

The **10/50 bps per side are assumptions**, not measured spreads, impact, or confidence bounds. Small/inactive names may cost more. Illustrative unchanged $50 reference prices and 10 shares ($500 reference principal) cost $3.05 base / $7.05 stress round trip; 20 shares ($1,000 reference principal) cost $4.06 / $12.06. These are fee/slippage arithmetic examples, not eligible order sizing examples or investment returns. Tiered's commission-only round-trip floor is $0.70, before its additional fees.

Keep one order per issuer per session. A later retry after a missing exit is a new order if filled; charge a new order minimum. Charge slippage once through the execution price, not again as a cash fee. Report gross price change, slippage, commissions, regulatory charges, and net account change separately. No subscription or tax is silently assumed zero: report trading-only results and deduct any separately authorized recurring data cost as a dated account expense in an additional affordability comparison.

## Settlement, actions, and daily NAV

For this 2022–23 study, sales settle **T+2**, not today's T+1. Credit a net sale receivable to spendable cash only at the start of its declared settlement day. Reserve/debit purchase principal and fees immediately so unsettled purchases cannot reuse funds. Settlement dates require a settlement-business-day calendar; NYSE trading sessions alone are insufficient around banking holidays. If a validated settlement calendar is not available, explicitly lock proceeds until the first NYSE session on or after seven calendar days following the sale. That fallback is a conservative model restriction, not an observed broker credit date. Choose and freeze the calendar or fallback before the run. [FINRA's T+1 transition notice](https://www.finra.org/rules-guidance/notices/24-04).

Record daily settled cash, reserved cash, unsettled sale receivables, dividend/merger claims, issuer units, cost basis, qualified close, mark source/status, pending exit, and each fee. For fully priced days,

`NAV = settled cash + unsettled net sale receivables + verified unpaid claims + sum(shares*qualified raw close)`.

Reserved cash is a subset of settled cash, not a second asset. Trade principal is exchanged for an asset/receivable, not itself a P&L expense. Apply verified splits to units and basis on the effective date. Use raw OHLC with separately recorded dividends; never combine adjusted-close total returns with separately credited distributions. `divCash` alone is not proof of a payment/availability date. A verified entitlement with unknown payment date remains a locked receivable; an unknown entitlement remains unresolved.

For ATVI, eligible shares become the documented $95/share merger receivable, carried at face value as the existing policy's accounting convention, with zero spendable credit until separately evidenced. Do not fill at its October 13 vendor row. For SIVB, enforce the March 10 halt and same-identity March 28 SIVBQ transition. Pre-transition halt rows are neither qualified current marks nor fills; later qualified OTC closes may value retained shares as the declared vendor proxy, but do not establish executable liquidation. The existing [source-backed ledger policy](../equity-event-repair-2026-09-10/source-backed-ledger-policy.md) provides the primary source evidence and exact scope.

## Halt, delayed exit, and loss stop

When an entry session is halted, missing, or ineligible, cancel the entry without a fee or fabricated fill. If an existing position cannot be exited on its scheduled day, retain its units and basis and flag `EXIT_PENDING`; attempt sale at the **first later qualified listed-session close** through the fixed endpoint. No new OTC purchases or OTC execution is assumed in this first specification. An OTC holding may therefore have a marked NAV while its liquidation remains pending. Record every actual delay; do not label such a lot a completed 20-session trade. At the fixed endpoint keep unresolved/open lots visible instead of forcing zero, a terminal sale, or a 2024 lookup.

If any held asset lacks a qualified current mark, primary daily NAV and daily return are **null**, with reason and last valid date retained. A last-price display is explicitly stale and cannot supply the primary drawdown series. Freeze all new entries while any asset is unpriced; existing scheduled exits continue when their own qualified fills are available. Report the length and identity of every gap. A later marked endpoint may support an endpoint valuation, but does not repair the unknown intervening drawdown or execution path.

Use a **$1,000 fixed-dollar high-water drawdown stop** (20% of initial capital), evaluated after each fully priced daily close and costs. Initial high water is $5,000. If `H-NAV >= 1000`, latch the account stopped, cancel future entries, and submit protective exits for the next qualified listed close; never execute that newly discovered stop at the already observed close. No annual reset. The rule also implies stopping at a known NAV of $4,000 or below, and can stop sooner after gains. For an unpriced holding, the entry freeze above applies; do not invent a zero mark to claim the stop was or was not breached. Report drawdown through any unpriced interval as unresolved. Gaps, delayed execution, or costs can take realized losses beyond $1,000; this is a stopping rule, not a guaranteed loss cap.

Daily order: release evidenced available cash; process effective corporate actions; prepare only orders supported by prior information and available cash; evaluate committed closing fills; mark remaining holdings; record fees/NAV; update high water and commit next-session protection. A closing sale cannot finance another same-close purchase. Do not retrospectively cancel an otherwise committed entry solely because the same close subsequently reveals a portfolio drawdown breach.

## Reuse and minimum verification

Read existing `tools/run_ba012_profitability.py:Account`, `src/boring_alpha/backtest/engine.py`, calendar validation, `tools/combined_account.py`, and the cost inventory. Reuse their ideas of immutable provenance, explicit executions, atomic required-mark validation, and no annual reset. The futures account's variation-margin equity, monthly ETF engine, shared-complete-universe calendar, and cash-yield assumptions are unsuitable for this event stock ledger without adaptation. `tools/action_ledger.py` is a research-summary table, not an event/corporate-action account engine.

Before using actual outcomes, verify one buy/sell with T+2 lock, simultaneous cash reservations, integer limit rejection, 20-interval indexing, dividends/splits without double count, ATVI locked claims, SIVB null halt marks and delayed exit, and the stop being executed only after its observation. Freeze code, inputs, dates, calendar, execution and model rules together. Publish each model's trades, skipped events, coverage gaps, account path, and paired fee scenarios; source qualification or a positive exploratory result is not evidence of out-of-sample profitability.
