# BA-010 development result: park the opening-range strategy

Completed September 9, 2026 America/Chicago (September 10 UTC).
**Version 1 failed its preregistered development gate.** The simulated pilot
triggered its trailing-drawdown halt on December 9, 2021. Continuing the same
one-contract strategy without account limits would have lost money after costs
over 2021–2023. No 2024–2025 strategy evaluation was run.

This closes one unproven opening-range hypothesis. It does not establish that
MES, futures, or quantitative trading in general cannot be profitable.

## What was fixed before the test

[BA-010 version 1](../strategies/BA-010.md) was committed as `b893119` before
computing MES strategy returns. The tested engine was committed as `141393f`
before the historical run. There was one declared rule set and no parameter
search or reversal of the signal after seeing its returns.

The strategy takes the first eligible breakout from the 09:30–09:59 New York
opening range, enters with a full minute of delay after the signal close, stops
at the range midpoint, and exits by 15:55. One MES contract, at most one trade
per full NYSE session, no overnight position. Planned signal-time loss including
base execution friction must be $25–$75; subsequent entry gaps remain in the
ledger even when they exceed that budget.

Each model starts with $5,000 for the entire three-year period. The pilot uses
a $4,240 entry-equity floor and a $1,000 absolute trailing-drawdown halt measured
from minute-close/flat liquidation equity. This trailing rule is stricter than
merely stopping $1,000 below initial principal. It can stop an account that is
still above $5,000. The unrestricted diagnostic separately checks whether the
strategy made money without that account policy.

## Results after modeled costs

All amounts below cover January 2021 through December 2023. Unrestricted rows
hold the same one contract and ignore account limits; they are diagnostics.

| Model | Trades | Gross P&L | Trading friction | Data fees | Net P&L | Ending equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Base pilot | 165 | $776.25 | $613.80 | $55.80 | **+$106.65** | $5,106.65 |
| Pilot, double slippage | 162 | $905.00 | $1,007.64 | $55.80 | **−$158.44** | $4,841.56 |
| Base, account limits ignored | 476 | $1,720.00 | $1,770.72 | $55.80 | **−$106.52** | $4,893.48 |
| Double slippage, account limits ignored | 476 | $1,720.00 | $2,960.72 | $55.80 | **−$1,296.52** | $3,703.48 |

The base pilot halted on **December 9, 2021**, at $5,143.85, down $1,002.14 from
its observed $6,145.99 high water. Monthly data fees continued after the halt,
as declared, reducing ending equity to $5,106.65. The corresponding maximum
minute-close/flat drawdown including those later fees was $1,039.34. The stress
pilot halted on November 30, 2021. Neither pilot resumed or received a deposit.

The pilot's positive final balance therefore does **not** mean it passed.
Its formal failure reason is `base_pilot_halted`. Annualized over the entire
three-year account path, its +2.13% cumulative return is approximately 0.71%.
Hypothetical 4% and 6% annual cash comparators gain $624.32 and $955.08 over the
same three years. These are benchmark scenarios, not reconstructed historical
deposit yields or available product offers.

The unrestricted base diagnostic earned only **$3.61 gross per trade**, versus
**$3.72 trading friction per round trip**, before monthly data fees. Its yearly
net P&L was +$52.99 in 2021, +$9.16 in 2022, and −$168.67 in 2023. The same
476 trades at doubled slippage lose $1,296.52. This provides no cost cushion
supporting a paper or funded pilot under the declared execution assumptions.

The five largest base-pilot winners totaled $1,233.90, or 26.0% of all positive
trade P&L; their total exceeds the strategy's final net gain. Six entries exceeded
the $75 planned-risk ceiling after the delayed opening price arrived; three
trades actually lost more than $75. The worst base-pilot trade lost $79.97.
In the unrestricted base diagnostic, 27 entries exceeded the plan and the worst
trade lost $94.97. A planned stop budget is not a guaranteed realized-loss cap.

The [account-path chart](../../experiments/BA-010/20260910-first-run/development/overview.png)
uses daily closes. Its drawdown panel differs from the minute-close liquidation
series used by the halt. The separately reported intrabar OHLC upper bounds
are deliberately loose envelopes, not reconstructed executable tick paths.

## Data acquired and audited

Databento `GLBX.MDP3`, `MES.v.0`, `ohlcv-1m`, 2021-01-01 through 2026-01-01
exclusive: **1,767,925 bars**, mapped to 21 actual-contract intervals. The
cumulative provider download quote was **$6.454313173890**, within the previously
verified $125 credit balance. That is a usage quote, not a reconciled invoice.
Acquisition is recorded separately from trading returns. No new subscription
or live-trading connection was made.

| Year | Raw minute bars | Full NYSE sessions | Missing minutes in full sessions |
| --- | ---: | ---: | ---: |
| 2021 | 353,230 | 251 | 0 |
| 2022 | 354,123 | 250 | 0 |
| 2023 | 353,177 | 248 | 0 |
| 2024 | 354,823 | 249 | 0 |
| 2025 | 352,572 | 247 | 0 |

All 1,245 full sessions contain 390 minute bars. Raw/compressed hashes, counts,
timestamps, contract mappings, tick grid, OHLC consistency, positive volume,
and historical session membership reconcile. Early closes and holidays are
excluded using a hashed `exchange_calendars` 4.13.2 XNYS schedule with tzdata
2026.3, including the January 9, 2025 closure. The volume-ranked continuous
series uses previous-day ranking and unadjusted contract prices; positions
never cross a daily contract roll. No missing prices were forward-filled.

Integrity checks processed 2024–2025 data, but the strategy engine opened only
2021–2023 session files. Development failure prohibited a holdout evaluation.
The earlier November 3, 2025 API sample was a bar-integrity check, not a strategy
test. No out-of-sample performance or bootstrap confidence claim is made.

## Assumptions and limits

The base uses $0.61 per side in current public broker/exchange/regulatory fees
and one adverse $1.25 tick at each fill. Stress doubles slippage. A $1.55 monthly
nonprofessional CME L1 fee is applied, including months after a halt.
These are scenario inputs applied across history, not a reconstruction of the
user's historical bill. Sources checked September 9–10, 2026:
[IBKR commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php),
[CME charges](https://www.interactivebrokers.com/en/accounts/fees/CME.php), and
[market data pricing](https://portal.interactivebrokers.com/en/pricing/market-data-pricing.php?menu=B).

Minute trade bars cannot verify bid/ask spreads, queueing, actual market-order
fills, or stop execution through gaps. Historical/account-specific margin is
not reconstructed; the $3,240 initial-margin proxy is a current public assumption.
Idle cash earns zero, taxes and additional computer/hosting costs are excluded.
A different fill model could change the result, but reducing assumed costs
after seeing this failure would require independent execution evidence.

## Reproduction and preserved evidence

Focused offline validation: **237 tests passed** across the access probe,
downloader, archive audit and strategy engine. Cases cover quote limits,
secret containment, malformed data, mappings, calendars, causality, gaps, stop
ordering, accounting, account halts and refusal to open the holdout after failure.
An independent review reconciled the recorded ledgers and result interpretation.

Local artifacts are excluded from Git and retain their source hashes:

- Archive: `data/futures/databento-history/20260910T031551686415Z/manifest.json`
- Audited inputs: `data/futures/ba010-inputs/20260910T031821312589Z/manifest.json`
- [Development report](../../experiments/BA-010/20260910-first-run/development/report.json)
- [Daily ledger](../../experiments/BA-010/20260910-first-run/development/day-ledger.jsonl)
- [Trade ledger](../../experiments/BA-010/20260910-first-run/development/trade-ledger.jsonl)

| Artifact | SHA-256 |
| --- | --- |
| Frozen protocol | `bc02412ff6d82d360e5d2b1ee4defba51a7056236636555d579ba453ce6dfb8b` |
| Frozen engine | `c1c9b514a898688f3f678e41d7be6b7e1adc545ad95a13b14126fcdf83a23023` |
| Audited input manifest | `3294b004a0fa56dbf7dcb567481ed3cb913a3f4a3e529539074083dce9d640ca` |
| Calendar | `140c6f3dc84ab742905adb5e1d3dc6ca9ff74ab23f6697f4e3f85e9bd5e21a74` |
| Development report | `b3567775d07220d7492092c65d1e86c9ce32ac28fc54395acc8f09f77fa0d26b` |
| Daily ledger | `e32a7ab61a5897cf95ea1fe6c0b5dd08c72b84ee509e249060594f048c13a2d4` |
| Trade ledger | `828ced8a1d3feb50b1701a54116df8bd3225ed18d5cd822668c5c0f46d8e1871` |

The archived run is immutable. An intentional reproduction must use a new
output root; the runner refuses to overwrite existing results.

```sh
.venv/bin/python tools/ba010.py \
  --input data/futures/ba010-inputs/20260910T031821312589Z/manifest.json \
  --stage development \
  --output-root experiments/BA-010/reproduction
```

## Decision and subsequent research

Park BA-010 version 1. Do not tune its range, delay, stop, direction or costs
against this result, and do not open 2024–2025 to search for a rescue. No money
should be allocated on the evidence from this experiment.

The reusable outcome is an audited MES archive and a tested execution/account
engine. Before another return run, require a distinct economic hypothesis,
an explicit cost and capacity argument, and a registered test. Any later use
of these 2021–2023 observations must be labeled as already seen. Repeatedly
trying new candidates against the same 2024–2025 holdout would eventually
consume its evidential value even without parameter tuning.
