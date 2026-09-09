# Active quantitative trading research

Updated 2026-09-09. This is the current work brief; earlier ETF/withdrawal
research does not define the user's active objective.

## Mandate

- Active, systematic trading with a measurable edge. No ETF or regular-stock
  allocation proposals: the user already manages those investments.
- U.S. resident using Robinhood and Coinbase; other accessible venues are
  possible if justified.
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
