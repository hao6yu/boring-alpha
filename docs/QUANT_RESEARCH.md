# Active quantitative trading research

Updated 2026-09-10. This is the current work brief; earlier ETF/withdrawal
research does not define the user's active objective.

## Mandate

- Active, systematic trading with a measurable edge. No ETF or regular-stock
  allocation proposals: the user already manages those investments.
- On September 10 the user explicitly accepted active individual-stock trading
  around events. Earnings-release models are now in scope; passive allocation
  and an AI service business are not the current direction.
- U.S. resident using Robinhood, Coinbase, and IBKR. The user requested an
  IBKR Lite-to-Pro switch; review is pending. Databento historical access works.
- $5,000 eventual pilot, approximately $1,000 loss tolerance. Larger capital
  is conditional and is not authorized by a successful backtest.
- Beat an investable cash alternative after realistic costs, with drawdowns,
  collateral needs, and uncertainty made explicit.
- Use published fees and labeled cost ranges for research. Missing personal
  fee screens must not block public feasibility analysis.

## Current deliverables

1. [BA-007 correction record](notes/2026-09-09-quant-takeover.md): quantity ledger,
   seven-day feature, delayed execution, missing-mark refusal, fresh weekly
   random assignments, and corrected stationary bootstrap mechanics.
2. [BA-009 feasibility charter](strategies/BA-009.md): same-asset spot/futures
   relative value on Coinbase's U.S. venue, initially BTC and ETH.
3. [Public fees and assumptions](../research/us-crypto-fees-2026-09-09.json):
   Robinhood published tiers, Coinbase account uncertainty, and futures fee
   floors, distinguished from spreads and funding.
4. `tools/us_crypto_carry.py`: no-key public collector and reproducible cost
   screen. Stores immutable raw responses, timestamps, hashes, and every
   declared cost/holding-period scenario locally under `data/us_crypto/`.
5. `tools/us_funding_history.py`: validates and summarizes public U.S. funding
   exports. BTC and ETH each have 2,160 contiguous reported hourly rates in
   the acquired 90-day export; these are rate statistics, not strategy returns.
6. [BA-009B first feasibility result](notes/2026-09-09-ba009b-first-feasibility.md):
   four-book spread scanner and exact U.S. paired-candle archive. The sampled
   entry does not justify a pilot after cost stresses; no fitted model or
   executable historical return is claimed.
7. [BA-009B conditional screen and retail availability audit](notes/2026-09-09-ba009b-conditional-screen.md):
   a fixed past-only gap rule, preserved missing outcomes, and an independent
   minute alignment diagnostic. No credible retail edge has emerged. The
   apparent BTC signal predates the opening implied by the published rollover
   rule; ETH movement falls short of assumed costs.
8. [Public historical-data source search](notes/2026-09-09-ba009b-public-data-search.md):
   Coin Metrics catalogs the exact expired contracts, but tested Community
   price access is denied. No usable free replacement was verified. Separate
   CDE funding-event marks are documented, with authenticated access required
   by the tested endpoint. BA-009B remains parked pending usable data access.
9. [Authenticated Coinbase history probe](notes/2026-09-09-ba009b-authenticated-history.md):
   Ed25519 authentication and view-only permissions verified. A BTC futures
   control returned 24 hourly bars, but both expired August contracts still
   returned invalid-product errors. Retail API access did not unlock them.
10. [CoinDesk API access check](notes/2026-09-09-ba009b-coindesk-access.md):
    documented futures catalog/history routes and explicit CDE coverage;
    anonymous catalog requests require a key. Signed-in key settings return
    to pricing, and no usable key or exact August contract sample was obtained.
    A narrow derivatives-trial request is drafted, not sent.
11. [Databento access and research costs](notes/2026-09-09-databento-access.md):
    $125 signup credits verified; an expired MESZ5 contract returned 390 valid
    one-minute bars with no missing minutes in the requested session. This was
    followed by the full archive and BA-010 experiment below.
12. [BA-010 development result](notes/2026-09-09-ba010-development.md): five years
    of MES minute data downloaded at a cumulative provider quote of $6.45;
    1,245 full sessions audited with no missing minutes. The preregistered
    opening-range strategy failed its 2021–2023 development gate: the pilot
    hit its trailing-drawdown halt, and unrestricted one-contract trading lost
    money after costs. Version 1 is parked; no 2024–2025 strategy test was run.
13. [Bounded evidence shortlist](notes/2026-09-09-shortlist-screen.md): reviewed
    three families without new return calculations. Late-day futures momentum
    merits one cost/implementation screen; simple overnight drift is rejected
    on the paper's own cost evidence; pre-FOMC drift is deprioritized. No new
    strategy is registered or queued for a backtest.
14. [Late-day MES feasibility](notes/2026-09-09-late-day-feasibility.md): **no-go
    for insufficient evidence**. The published single-S&P trade magnitude is
    unavailable, while the reported portfolio statistics and one-tick cost
    comment cannot establish profitability at MES base/stress costs. The
    bounded shortlist round is complete; no new backtest or purchase occurred.
15. [BA-011 fixed development test](notes/2026-09-09-ba011-development.md): the
    user subsequently authorized one direct test to resolve that missing
    expectancy. **FAIL:** pilot lost $805.38 including post-halt data fees;
    unrestricted base lost $477.59 over 2021–2023 and stress lost $2,307.59.
    The pilot hit its capital floor in July 2021. No 2024–2025 price files were
    opened by this experiment, and no additional data was purchased.
16. [Strategy research before further implementation](notes/2026-09-10-strategy-research.md):
    the user authorized a broader research review with coding deferred. Three
    mechanisms were reviewed against primary evidence and current U.S. contract
    terms. Slow diversified long/short futures trend ranks first; dated crypto
    cash-and-carry ranks second; defined-risk options are parked. Both leading
    candidates overlap earlier research families, and neither is investment-ready.
    The note records counterevidence, small-account economics and a fixed next
    feasibility scope. No code, backtest, purchase or account change occurred.
17. [Five-market futures trend feasibility](notes/2026-09-10-futures-trend-feasibility.md):
    the user selected futures trend and authorized its feasibility worksheet.
    Verified NES/MTN/M6E/1OZ/MZC mechanics, public trading activity, broker fees,
    margins and explicit capital/stress arithmetic. One of each meets current
    margin but loses $1,050 before costs in the larger assumed joint shock.
    Allowing flat markets provides mechanically feasible smaller baskets;
    executable spreads and volatility-based integer sizing remain unresolved.
    Conditional continuation to one research protocol, not a funded or backtest
    pass. No strategy code, purchase, account change or return test occurred.
18. [BA-012 fixed research protocol](strategies/BA-012.md): the user authorized
    the next protocol stage. Fixed 252-session trend, 8% forecast volatility,
    covariance shrinkage, portfolio-level integer selection with cash allowed,
    causal rolls and separate execution phases, daily risk reductions and
    explicit costs/margin/loss budgets. First stage tests sizing only; it can
    reject an all-cash $5,000 implementation before a return backtest. Delayed
    IBKR bid/ask fields are documented, but account access and exact-contract
    coverage remain unverified. No new return calculations or purchases occurred.

## Commands

```sh
# Public read-only snapshot: no credentials or account access.
.venv/bin/python tools/us_crypto_carry.py

# Offline replay (use the path printed by the collector).
.venv/bin/python tools/us_crypto_carry.py --snapshot data/us_crypto/snapshots/STAMP

# Reproduce statistics from the archived U.S. funding export.
.venv/bin/python tools/us_funding_history.py data/us_crypto/funding-history/2026-09-09-cde-90d

# Focused synthetic checks.
.venv/bin/python -m pytest tests/test_futures_account.py tests/test_ba007.py tests/test_us_crypto_carry.py -q
```

Funding snapshot annualization is a scenario, not expected yield. The initial
BTC/ETH screen did not justify a trade after modeled fees and cash opportunity
cost. It does not falsify all carry trading. See the dated audit for numbers.

## Next work, in order

**Current direction: active equity event research.** The latest
[earnings-language experiment](notes/2026-09-10-equity-event-test.md) stopped
at its training-sample gate. Profitability remains untested.

The preceding availability repair now passes **97/100**, above its unchanged
95 requirement, after qualified Databento PTN histories supplied four windows.
The original pilot and repair artifacts remain preserved. The dedicated data
quote totals about 1.3 cents against existing credits; this is not an invoice.

A separate fixed 100-issuer, 1,600-slot cohort produced **175 usable 2020 training
events versus 200 required**, 200 validation events, and 378 evaluation events
across 57 issuers qualified before entry. Final original-source and extraction
audits are saved. No model was fitted or 2022–2023 evaluation targets opened.
The nine remaining planned price queries could add at most 24 training events,
leaving an optimistic 199; they were not acquired. Clearing CADE's ticker
warning cannot rescue the count: independent original-price anchors identify
the downloaded history as the acquirer rather than the selected issuer.

This is an inadequate sample under the frozen sourcing/trading rules, not a
negative profitability result. The minimum was not lowered and failed issuers
were not replaced. Any continuation requires a separately specified larger
cohort or materially better historical coverage and a finite effort/data
budget. Reuse the retained source collection and accounting tests. Do not
open evaluation returns or tune the strategy to rescue this run. No live
trade, account change or monitor occurred; 2024–2025 equity strategy prices remain
reserved for this experiment.

**Research direction reset:** the user requested a broader review after the
BA-012 result. The [research reset](notes/2026-09-10-research-reset.md) pauses
BA-012 variations and defers the proposed fractional/all-long diagnostic.
No new bot is nominated. The subsequently authorized
[expiring crypto cash-and-carry screen](notes/2026-09-10-dated-carry-screen.md)
is complete: both sampled September 25 entries fail even the 4% cash scenario
before fees at $5k/$25k/$100k under the fixed reserve policy. Public quotes
worked; insufficient entry premium ends this screen. No implementation or
monitor follows. Broad trend/carry remains conditional on affordable history
and attainable breadth. Pairs, options and generic ML searches are not queued.
No backtest, paid data or account change occurred in this screen. Earlier
research rankings below are preserved history.

**Current status: the completed larger-account profitability diagnostic loses
money under both cost assumptions at both balances.** The
[result note](notes/2026-09-10-ba012-traded-profitability.md) covers July 1, 2022
through November 23, 2023, with November 22 boundary liquidation. At $25,000,
base/stress net P&L is −$681.78/−$1,557.53, annualized −1.96%/−4.49%. At
$100,000, it is −$1,384.40/−$9,243.10, annualized −0.99%/−6.69%. All four fail
both cash scenarios. None reaches its permanent halt; event-marked drawdowns
range from 11.64% to 14.14% of running peaks. Fixed dollar loss budgets are
20% of initial capital, not a periodically reset allowance.

All four runs intended through December 2023 remain **UNRESOLVED** at the
missing November 24 held TNH4 10:00 mark. The common shorter endpoint was
fixed before P&L and used only for this data failure. All 377 execution queries
are acquired; absent individual bars remain null. The four completed shorter
ledgers use actual exact-contract parent bars with hypothetical child
multipliers and fees, continuous equity, real transition quantities, causal
prior-day settlement risk, and the explicitly recorded protection policy.
Higher costs also change later trades; the $100,000 paths first diverge at an
August 10, 2022 risk-cap crossing. This is a material sensitivity.

The earlier [capital comparison](notes/2026-09-10-ba012-capital-sensitivity.md)
still establishes 25/25 usable nonzero sizing cases at both larger balances;
it did not predict profit. The completed return diagnostic supplies no positive
evidence to advance this configuration. No parameter search, holdout,
all-long/fractional control, native-fill or funded pass has been performed.
The full 2018–2023 study remains incomplete, so do not generalize the shorter
loss to all years or every trend strategy.

The covered-period $5,000 cash-only profitability diagnostic remains complete
and negative. The [diagnostic report](notes/2026-09-10-ba012-profitability-diagnostic.md)
uses the longest fully covered stretch, July 2022–December 2023, with its June
2022 seed signal. The account makes zero trades and falls from $5,000 to
$4,916.30 after 18 modeled $4.65 data fees: −$83.70, −1.1161% calendar CAGR.
All 377 daily risk windows are complete. Monthly risk/money bounds were
independently rechecked at the account's actual declining equity; no missing
input was converted to a cash decision and no annual reset was used.

The 4% and 6% annual cash scenarios end at $5,303.84 and $5,457.99 respectively.
This coverage-selected expense diagnostic does not meet either hurdle and is
not the planned full 2018–2023 Stage B study. It establishes the inactivity of
this $5,000 implementation in the covered period, not the profitability of the
underlying trend signal at a different capital level. The later larger-capital
result is recorded above; holdout returns remain untested.

All 181 BA-012 settlement downloads are complete and verified.
The [completion report](notes/2026-09-10-ba012-download-complete.md) records
3,277,624 raw statistics records and $0.611430853385 cumulative provider estimates
against the $1 ceiling at that stage. All six failed/interrupted settlement
reservations remain counted. The subsequent execution acquisition adds
$0.187270641337 including four failed requests and successful retries, bringing
BA-012 cumulative estimates to $0.798701494722. Actual billing was not queried.
No download process or lock remains.

Under the unchanged version 2 selection rules, 8,488 of 10,211 required references
are eligible. Twenty-five monthly windows are complete: August–December 2019,
January 2020, June–December 2022, and all 2023. The existing $5,000 sizing check
returned verified cash decisions for all 25, with a necessary infeasibility
proof in each: fewer than three groups can hold even one contract within the
risk/money limits. The remaining 47 windows have null/unresolved decisions.
They are not cash observations. The prescribed 72-case capital rejection is not
met. The cash/expense, larger-capital sizing and shorter trading diagnostics
above have been calculated; full-period trading profitability remains unresolved.

The user's extension of download time superseded the acquisition stop in the
preserved [bounded-attempt record](notes/2026-09-10-ba012-final-feasibility.md).
The download blocker is now resolved. Remaining input issues concern settlement
flags and timing eligibility, largely in 2016–2017. Preserve the current result;
any future eligibility amendment must be explicit rather than silently changing
which already-observed records pass. No broad strategy search or return study
was queued by download completion. The subsequent explicit profitability request
authorized the separately recorded cash/expense diagnostic above, followed by
explicitly approved larger-capital sizing and profitability tests.

The preserved version 1 [Stage A result](notes/2026-09-10-ba012-stage-a-result.md)
records all 2,080 quoted dates acquired, with $0.162474512840 in provider estimates.

There are 134 missing exact-minute references across 125 joint dates: 85 gold,
47 Treasury and two corn. Of the gold gaps, 82 involve October contracts.
Every one of the 72 scheduled monthly windows is incomplete, so the $5,000,
$25,000 and $100,000 sizing cases remain unresolved. Missing inputs were never
counted as cash decisions or evidence of capital infeasibility. That preserved
version 1 result calculated no returns; later diagnostics are listed above.
No holdout price inspection or funded pilot has been run.

The [earlier diagnosis](notes/2026-09-10-ba012-data-design-diagnosis.md) led to
version 2's separately frozen gold schedule and settlement-selection rules.
The earlier bounded attempt confirmed that settlement messages could be acquired
and processed. The subsequent continuation completed acquisition and established
the partial sizing evidence above. This does not establish that diversified
trend trading fails economically. Preserve both versions; do not increase risk
or change selection rules to turn missing inputs into a passing result.

The earlier [static arithmetic](notes/2026-09-10-ba012-stage-a-preflight.md)
established only mechanical cost/margin possibility at $5,000. It remains
insufficient to establish a portfolio using measured risk. Larger virtual
cases are diagnostics, not deposit requests. IBKR Pro eligibility, account
permissions, actual child spreads and broker-specific delivery cutoffs remain
unverified. Crypto carry and options remain parked. No bot, subscription,
order or monitoring has been started.

[BA-011's measured result](notes/2026-09-09-ba011-development.md) remains a
failure: costs exceeded unrestricted gross profit and the pilot halted at its
capital floor. Do not tune it or run its holdout to rescue that result.

The first **CME MES intraday experiment**, [BA-010](strategies/BA-010.md), is
complete and failed development. Its base pilot ended up $106.65 over three
years but halted in December 2021 after a $1,000 trailing drawdown; the same
one-contract strategy ignoring account limits lost $106.52 after costs. Do not
promote it, tune it against those results, or run its 2024–2025 holdout.

The data-access blocker is resolved. Audited 2021–2025 MES history and a tested
minute-bar execution/account engine are available locally. Further research
requires a specific economic hypothesis with a plausible cost/capacity argument
before another registered test. Explicitly record extensions of prior families:
BA-001/002 already tested related long/cash ETF trend signals, and BA-009 already
opened spot/futures carry research. Treat MES 2021–2023 and prior ETF development
and validation history as seen, preserve unopened holdout files, and track
cumulative candidate trials. An untested instrument does not make an otherwise
examined calendar period an entirely unseen economic regime. No paper or funded
pilot is justified by BA-010.

[BA-009B, dated/perpetual futures spreads](strategies/BA-009B.md), is parked.
Its quote screen, conditional price diagnostic, and minute timing audit are
complete and weak after costs. Both August BTC/ETH candle probes failed through
public and authenticated Advanced Trade routes. Databento's CME contracts are
different instruments and cannot substitute for that missing Coinbase history.
Do not buy data or build paper execution to rescue the weak result. The original
BA-007 candidate is retired from deployment consideration; its broader funding
ranking hypothesis remains unresolved after the audit.

The remaining Coinbase carry work is optional follow-up, not a blocker for CME:

1. U.S. CDE funding history has been downloaded and checked for 90 days via
   the public portal's CSV export. Next obtain event-time settlement marks,
   basis and executable spread history, and a longer funding history if
   available. The International Exchange API is a different venue. Check
   public sources before considering paid data or asking for account access.
   No data request has been sent on the user's behalf.
2. Check funding persistence, entry/exit basis, spreads, and collateral jointly.
   Add dated-futures basis feasibility as a separately recorded extension if
   it offers a credible mechanism after costs. Do not extrapolate one hourly
   rate through a year as performance evidence.
3. Freeze a candidate's trade/abstention rules, cost assumptions, and evidence
   criteria before its independent forward test. A data-dependent revision is
   allowed and must remain exploratory on data it has already viewed.
4. Only after a credible candidate exists, build a paper execution adapter and
   reconcile fills, funding, margins, and equity. Live orders require a
   concrete review of the candidate and account-specific constraints.

The remaining historical data is a data-acquisition task, not evidence that
profitable quantitative trading is impossible. Keep a bounded experiment
ledger and stop individual unpromising hypotheses without declaring entire
fields exhausted. Do not schedule monitoring, subscribe to data, send messages,
or create live credentials without user authorization.
