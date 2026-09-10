# Active quantitative trading research

Updated 2026-09-09. This is the current work brief; earlier ETF/withdrawal
research does not define the user's active objective.

## Mandate

- Active, systematic trading with a measurable edge. No ETF or regular-stock
  allocation proposals: the user already manages those investments.
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

**Current status: the authorized BA-011 test failed; no further work queued.**
The user deliberately reopened the paper-screen round for one fixed direct
test. [BA-011's measured result](notes/2026-09-09-ba011-development.md) now shows
costs exceeded the unrestricted strategy's gross profit, and the pilot halted
at its capital floor. End this reopened round as agreed. Do not tune BA-011,
run its holdout, expand the candidate list, buy data or build deployment tools
by default. A new research direction requires a deliberate scope change.

The first **CME MES intraday experiment**, [BA-010](strategies/BA-010.md), is
complete and failed development. Its base pilot ended up $106.65 over three
years but halted in December 2021 after a $1,000 trailing drawdown; the same
one-contract strategy ignoring account limits lost $106.52 after costs. Do not
promote it, tune it against those results, or run its 2024–2025 holdout.

The data-access blocker is resolved. Audited 2021–2025 MES history and a tested
minute-bar execution/account engine are available locally. Further research
requires a distinct economic hypothesis with a plausible cost/capacity argument
before another registered test. Treat 2021–2023 as seen history, preserve the
unused 2024–2025 strategy holdout, and track cumulative candidate trials. No
paper or funded pilot is justified by BA-010.

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
