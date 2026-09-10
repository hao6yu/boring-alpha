# BA-012: larger-account profitability diagnostic

**Both larger balances lose money in the completed diagnostic, under both
cost assumptions.** More capital resolves the observed sizing obstacle, but
this test does not establish a profitable strategy.

The completed account window is **July 1, 2022 through November 23, 2023**
(end exclusive November 24): 511 calendar days and 352 joint sessions. All
positions close at the specified November 22 10:01 fills, the final joint
session before that boundary. These are hypothetical child exposures on parent
prices, not actual historical child executions or funded accounts.

## Completed results

| Virtual balance | Cost assumption | Ending equity | Net profit/loss | Calendar annualized return |
| --- | --- | ---: | ---: | ---: |
| $25,000 | Base | $24,318.22 | **−$681.78** | **−1.96%** |
| $25,000 | Stress | $23,442.47 | **−$1,557.53** | **−4.49%** |
| $100,000 | Base | $98,615.60 | **−$1,384.40** | **−0.99%** |
| $100,000 | Stress | $90,756.90 | **−$9,243.10** | **−6.69%** |

All four fail both the 4% and 6% annual cash scenarios over the same dates.
The $25,000 scenarios would end at $26,411.11 and $27,124.90; the $100,000
scenarios at $105,644.45 and $108,499.62. These rates are fixed comparison
scenarios, not claims about a currently offered cash account.

| Virtual balance / costs | Gross trading P&L | Execution costs | Data fees | Maximum marked drawdown | End-of-day invested sessions |
| --- | ---: | ---: | ---: | ---: | ---: |
| $25,000 / base | −$374.54 | $228.20 | $79.05 | $3,606.60 / 13.33% | 264 / 352 |
| $25,000 / stress | −$1,084.70 | $393.78 | $79.05 | $3,823.17 / 14.14% | 266 / 352 |
| $100,000 / base | −$258.12 | $1,047.22 | $79.05 | $12,283.81 / 11.64% | 244 / 352 |
| $100,000 / stress | −$7,598.41 | $1,565.64 | $79.05 | $13,931.01 / 13.90% | 239 / 352 |

Drawdown percentages use the running marked high-water value. Dollar loss
budgets remain $5,000/$20,000, fixed at 20% of initial capital, with no annual
reset. None of these accounts hits its permanent drawdown/maintenance halt.
Each has six protective liquidation batches and a separate final close.
The completed ledgers contain 114/126/138/143 market execution records,
respectively; these are fills by market, not counts of independent bets.
Monetary outputs retain fractional cents in JSON; displayed amounts use
round-half-even to cents, so rounded components can differ by one cent.

## Why the shorter result is separate

The original covered study runs through December 2023. **All four such runs
remain UNRESOLVED**, because they hold TNH4 on November 24, 2023 and its exact
09:59–10:00 reference bar is absent. No full-window ending equity or CAGR is
reported. A later fill or settlement is not substituted for the missing mark.

That gap was found before any strategy P&L was calculated. The plan fixed
November 24 as the shorter diagnostic's exclusive boundary in advance and
allowed it only for a valuation/fill data failure. All four accounts therefore
use the same earlier endpoint; it was not selected because a return looked
better. The November 22 liquidation is included in each shorter ledger.

All 377 requested execution windows were downloaded. Of 11,502 required
contract/minute slots, 11,497 contain bars. The five absent execution slots
and the separate known reference gap remain explicit nulls in the input
bundle. The completed shorter accounts need no invented held mark or fill.
Full 2018–2023 Stage B is also still unavailable: its 47 incomplete sizing
windows were not repaired or relabeled as cash.

## What the cost comparison tells us

Base and stress are independent continuous accounts. One/two adverse child
ticks plus commissions are charged once per execution, with actual holdings,
rolls, reversals and changing equity carried forward. Both use the same
stressed feasibility reserves. Higher costs can change subsequent quantities
and risk-triggered exits; the stress result is not obtained by subtracting a
larger fee from an unchanged gross return.

At $100,000, the first position-path difference occurs on August 10, 2022:
the base account keeps its basket, while the lower-equity stress account
crosses the forecast-risk cap and liquidates at the scheduled 10:05 phase.
Subsequent exposure and gross P&L differ. The large performance spread is
therefore also evidence of sensitivity to the account rules, not merely a
calculation of incremental commissions.

At the first divergence, cumulative execution-cost differences are $70.5625.
The stressed account's 10:02 forecast risk exceeds its dollar cap by just
$0.3031. A small cost difference therefore changes a discrete liquidation
decision. This sensitivity weakens any claim that a single favorable cost
assumption would demonstrate a robust implementation.

The protection interpretation was fixed before returns: optional transitions
must satisfy risk/funding limits at every partial-fill state, and an existing
hard-limit breach can force complete liquidation when no optional reduction
passes. A concentration-only problem is first repaired by a feasible reduction;
it does not automatically force cash. This conservative interpretation must
not be confused with a more permissive deleveraging policy.

## Scope and decision

This completes the requested bounded profitability diagnostic. **There is no
positive profitability evidence here to justify advancing this configuration.**
It does not establish that all diversified trend strategies fail, or provide
a valid full-period result by extrapolating the shorter one.

The window is coverage-selected development history. No parameter search,
all-long or fractional control, statistical edge claim, 2024–2025 holdout,
native liquidity validation, account change or order accompanies this result.
Those omissions prevent a formal Stage B or funded pass. Cash interest is
zero; taxes and hosting costs are excluded under the recorded assumptions.
Margins are fixed contemporary proxies, not reconstructed historical margins.

## Reproducibility and checks

- Plan frozen before P&L: `research/ba012-profitability/traded-v1/plan.json`
  (SHA256 `a9da9a602bcebca0653de7c4eb1259f8464dee4b1593d5fd4da129440d45c6cb`).
- Verified prices, identity mappings and causal risk inputs:
  `research/ba012-profitability/traded-inputs-v1.json`
  (SHA256 `a8240876425740bb53a62e0e7eea858e570ede44007b68ae7726e2f010b0b339`).
- Account engine: `tools/run_ba012_profitability.py`; transition optimizer:
  `tools/ba012_transition.py`. Exact code/runtime hashes were recorded before
  the first historical account run in `traded-v1/implementation-freeze.json`.
- Eight account records and their checksums: `research/ba012-profitability/traded-v1/`.
  Summary SHA256 `cfb057d1d0d244ed0ff3c51d4538f7e346b901e91a4b56f407056acb0490eac4`.
- 52 focused synthetic/offline checks passed before historical P&L, covering
  covariance/transition constraints, independent brute-force optima, costs,
  roll accounting, signal timing, missing data and output serialization.

An independent audit reconstructed completed gross P&L solely from signed
exact-contract fill cash flows and separately rebuilt every marked equity
event from the frozen input prices. Fees, execution charges, ending equity,
high-water marks, drawdowns, annual continuity and result hashes reconciled.
The shorter ledgers match their primary counterparts through November 21;
only the predeclared November 22 boundary liquidation changes the endpoint.

A separate decision audit checked all eight saved accounts: 704 completed
searches, 128 month-end plans, 278 entry rechecks, 11,892 partial-fill vertices,
1,022 resolved fills and 11,802 held-mark events. Prior-day morning covariance,
monthly quantity caps, retained lower bounds, daily reduction/roll limits,
mandatory-exit reasons and exact phase prices passed. No search limit became
cash. These counts include overlapping primary/prefix records and are audit
work counts, not independent statistical observations.

The new execution acquisition reserved **$0.187270641337** including four failed
requests and their successful retries. Cumulative BA-012 acquisition estimates
are **$0.798701494722**; actual provider billing was not queried. Historical
operating data fees are the separate 17 × $4.65 account charge above. All prior
protocols, amendments and results remain preserved.
