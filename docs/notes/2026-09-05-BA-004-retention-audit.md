# BA-004 — Retention audit: first result note

Date: 2026-09-05. Verdict: **Redundant** (superseded 2026-09-05; first read as
**Works, conditionally** — see the correction below, which is the reviewer's
finding and not a softening of it).

Charter [BA-004.md](../strategies/BA-004.md). Protocol
[BA-004-test-protocol.md](../reviews/BA-004-test-protocol.md), pinned before
computation. 52 scenario runs over four return regimes at two account scales;
36 unit and injection tests. Result digest
`43969ac6ed4f09381f6870308222bb8456087dcec327c03d968f5a0908226599`.

This note answers the question the protocol fixed in advance. It does not
forecast a market, it does not audit a live account, and it does not endorse the
instrument. What it does say is whether the declared budget is reachable and
whether the instrument that measures it can see anything.

## Verdict, against the two axes the protocol fixed

**Axis B — is the audit discriminating? PASSED, completely.** Every channel
planted at a declared magnitude was detected *and* attributed to the correct
channel. The engine was additionally validated against an independent
implementation written without shared code, agreeing within 0.22–0.24 bps in
every regime tested.

**Axis A — is the budget reachable? PASSED, only under four named conditions.**
The registered policy sits at 0.5–1.5 bps and clears the 30 bps gate in every
regime. That figure is flattering: it belongs to an account holding no idle cash
at all, which is not the account the charter describes. Under the charter's *own
declared* assumptions the gate **fails** — 3% idle cash costs 54.0 bps in seen B,
and a $10/month platform fee costs 34–95 bps at the real account size. The
budgets in charter §6 are not mutually consistent, and that is a finding about
the charter, not about the market.

Under the protocol's vocabulary this is **Works, conditionally**: Axis B passes,
Axis A passes only under a named subset of assumptions, and the binding channel
and binding assumption are named below.

## The one finding that matters more than the verdict

The same physical leakage — a 3% idle-cash sleeve, nothing else — costs:

| Account shape, identical seen-A prices | Shortfall |
|---|---:|
| Lump sum, never contributed to | **7.28 bps/year** |
| Funded: $2,000 opening, $500/month | **24.86 bps/year** |

The prices are identical. Only the funding profile differs. **The same leak costs
3.4 times more to an account that is contributed to than to one that is not**,
and it is invariant to the size of the account while doing so — $500 a month on a
$2,000 opening and $5,000 a month on a $20,000 opening give the same 24.86 bps to
two decimals.

Every figure in BA-001, BA-002 and BA-003 was computed on a self-financing lump
sum, because the engine could not do otherwise: `metrics/performance.py`
annualises `end_equity / start_equity` and has no way to represent a deposit. The
consequence is now measured rather than argued: **that framework understates
cost-type leakage for a funded account by roughly a factor of three.** This is
not a defect in those three strategies' conclusions — they were answering a
question about signal, and the signal conclusion stands. It is a defect in the
reach of those conclusions, and it is why BA-004's principal deliverable was the
cash-flow layer rather than a new signal.

The same divergence is sharper still where it matters. A fund that falls 10%
while only $1,000 is invested, then receives $18,000 afterwards: time-weighted
−10.0%, money-weighted −0.1%. A gap of **890 bps**, from arithmetic alone
(`tests/test_cashflow.py`). Had BA-004 reported CAGR, it would have been
describing a fund rather than the account that paid for it.

## Scenario grid, 1x scale

| Scenario | trending | random walk | seen A | seen B | Binding channel | Gate |
|---|---:|---:|---:|---:|---|---|
| S-CLEAN | 0.57 | 0.59 | 0.51 | 1.50 | — | pass |
| S-MARKET-ORDER | 2.30 | 2.38 | 2.06 | 6.00 | — | pass |
| S-CASH-1 | 0.59 | −4.51 | 8.80 | 18.98 | idle cash | pass |
| S-CASH-3 *(charter A10 ceiling)* | 0.65 | −14.69 | 25.41 | **53.99** | idle cash | **fail in seen B** |
| S-CASH-8 | 0.98 | −40.02 | **67.08** | **141.83** | idle cash | fail |
| S-LATE-10 | 9.70 | 8.04 | 11.06 | **44.53** | latency | **fail in seen B** |
| S-FIXED-FEE ($10/mo) | **38.08** | **39.65** | **34.28** | **95.15** | platform fee | **fail everywhere at 1x** |
| S-EXPENSIVE-FUND (42 bps) | 0.58 | 0.59 | 0.51 | 1.50 | — at Tier 2 | pass, but see below |
| S-BEHAVIOUR-1 | 0.57 | 0.59 | 0.51 | 1.50 | — | **fail by rule** |

At 10x, S-FIXED-FEE collapses from 34–95 bps to 3.9–10.8 bps and passes. All
proportional scenarios are unchanged to two decimals, as they must be.

Two entries need a word. **S-BEHAVIOUR-1 fails with a near-perfect shortfall**,
0.51–1.50 bps: one registered violation voids the run's return as evidence about
the strategy. The register has teeth because it can fail a run that looks
excellent, which is precisely the failure mode that made BA-001 through BA-003
worth less than they should have been. **S-EXPENSIVE-FUND passes its Tier-2 gate
and must not be read as a pass**: the 42 bps wrapper puts 41–50 bps into the
Tier-1 gap, entirely outside the gate, and the Tier-2 behaviour score is
unchanged from clean to within 0.0066 bps. A holder audited on Tier 2 alone would
be told their behaviour is impeccable while losing half the budget to a fund
prospectus. That separation is the design's central claim and it survived.

## Against the six predictions written before any of this was computed

| # | Prediction | Result |
|---|---|---|
| P1 | Idle cash dominates, roughly 0–15 bps, the only channel that can bind alone | **Confirmed in direction, wrong in magnitude.** Idle cash binds in every regime with a positive equity–cash gap and is the only channel that fails the gate on its own. But it is not ~15 bps: it is −40.0 (random walk, where cash *outperforms*), 0.65 (trending), 25.41 (seen A), 53.99 (seen B). A single number was the wrong shape of prediction |
| P2 | Spread cost shrinks as the account grows; year 1 above 3 bps, year 10 below 1 | **Confirmed by direction, not yet measured by year.** Market orders cost 6.00 bps in the short small-balance seen B and 2.06 in the long large-balance seen A; spread never binds anywhere. Per-year decomposition not run; this row is only partly tested |
| P3 | Clean run lands near 16–20 bps with headroom from cash discipline | **Wrong.** Measured 0.51–1.50. The prediction quietly assumed the account held cash at its declared maximum; the clean scenario as specified holds none. **S-CLEAN is not a realistic account and should not be the reference run** — the honest reference is S-CASH-1 |
| P4 | A 42 bps wrapper fails the gate on its own | **Confirmed and stronger than predicted.** 41–50 bps of Tier-1 gap against a 30 bps total gate: the instrument choice alone consumes 140–165% of the entire budget before the holder places one order |
| P5 | Channel ordering holds across regimes | **Confirmed.** Idle cash binds wherever equity leads cash; spread never binds; latency binds only in the widest-gap regime |
| P6 | A fixed-dollar fee fails at 1x, passes at 10x | **Confirmed and larger than predicted.** 34–95 bps at 1x versus 3.9–10.8 at 10x |

Four of six confirmed, one partly tested, one flatly wrong. P3 was the wrong
shape of prediction, and the fact that it was written down is the only reason its
wrongness is a finding rather than a shrug.

## The audit's own limits, measured not asserted

- **Cross-check error is proportional, not fixed.** Over 286 policy combinations
  the Dietz/IRR cross-check error peaked at 19.69 bps absolute and 4.19% of the
  shortfall, with the ratio essentially flat. So the audit cannot distinguish a
  shortfall below roughly 3 bps/year from zero; S-CLEAN at 0.51 bps is
  *indistinguishable from zero by this instrument*, not a measured zero.
- **Attribution is additive to within 0.18 bps** across all 52 runs, so the
  residual term is doing nothing and the decomposition can be trusted.
- **A wrapper fee is not perfectly inert in a money-weighted shortfall** — 0.0066
  bps of contamination from a 35 bps fee swing. Immaterial, and asserted as
  measured rather than assumed to be zero: a multiplicative fee does not cancel
  in a difference under money-weighted return.
- **The synthetic `trending` regime is nearly cash-neutral** (+2.57 bps) despite
  an arithmetic mean above the cash rate, because volatility drag consumes the
  excess. The generator's own docstring forbids using it as market evidence, and
  nothing in this verdict rests on it.
- **Only two of four regimes are real prices.** The synthetic regimes test
  plumbing across a return range and nothing more.

## The four conditions, stated as constraints rather than findings

1. **Idle cash must be capped near 1%, not the charter's declared 3%.** At the
   3% ceiling the gate fails in a strong bull regime, which is the regime where
   the opportunity cost of sitting out is largest and the regime a holder is most
   likely to tolerate cash in. This is the binding condition.
2. **A fixed-dollar platform fee is unaffordable at the real account size.** The
   charter assumed $0 in A13 and that assumption is doing almost all the work: at
   $10/month the gate fails in every regime tested. An eligible zero-fee vehicle
   is not a preference, it is a precondition.
3. **The wrapper fee must be pinned before the account opens.** P4 says the
   largest single term in the entire budget is decided before the strategy runs,
   by a choice with no research content at all.
4. **Contributions must arrive on the declared day.** Ten days of procrastination
   costs 8.0–44.5 bps. This is a habit, not a parameter, and it is the cheapest
   30 bps available.

Market orders, by contrast, cost 2.06–6.00 bps and never bind. Effort spent on
order placement is effort spent on the smallest term in the budget; effort spent
on the cash buffer and the fee schedule attacks the two largest.

## What this does not establish, and will not

No live account has been audited; the charter's three-year live audit remains
future work and this note does not substitute for it. No market return is
forecast. Whether the *instrument* is the right one to hold is untouched — a
retention strategy can pass every gate here and still hold the wrong asset, and
the charter says so in its own §9. And nothing here rescues BA-001, BA-002 or
BA-003: their signals lost pre-tax on both feeds and still do. BA-004's verdict is
a statement about plumbing and behaviour, and the honest summary is that the
plumbing can be made to work under four specific conditions, all of which are
choices rather than predictions.

## Artifacts

- `src/boring_alpha/metrics/cashflow.py` — XIRR, Modified Dietz, guards
- `src/boring_alpha/capture.py` — funded account, six channels, ablation audit
- `tests/test_cashflow.py`, `tests/test_capture.py` — 36 tests, including the
  injection battery
- `tools/run_ba004_audit.py`, `experiments/BA-004-grid.json` — grid and results
- Full suite: **1,080 passed, 224 subtests, 2:28**, no regression to BA-001 or
  BA-002 behaviour

## Correction, same day: the verdict was the wrong shape

The note above reads the §6 gate as the whole test. It is not. Charter §13
applies a dominance rule that this note did not have when written, and under it
the verdict changes to **Redundant**.

The arithmetic is not close. On the same $5,000 plus $500/month schedule, over
seen A, plain DCA into SPY with no strategy and no machinery ends at **$140,155**
(money-weighted 12.23%). The best BA-004 configuration in the grid lands at
**$134,496**. BA-004 loses to doing nothing by about **$5,700, or 8.4% of
everything paid in**, and the gap is the wrapper fee plus the cash it holds —
that is the entire mechanism, because there is nothing else in it.

Worse for the framing: that $5,700 is *smaller* than the spread between funds.
Seen A on the same schedule runs from **$49,857** (DBC) to **$140,155** (SPY).
The single decision of what to own moved **$90,298**. Everything the grid
measured — latency, spread, idle cash, platform fees, the whole behavioural
bundle — moved at most **$8,815**. The repo spent its attention on the third
largest term.

So the honest summary of BA-004 is: **excellent instrument, empty strategy.**
Keep the engine, kill the claim. The retention audit is worth its cost as a
pre-flight check on the *other* strategies, which do leak and do lose money to
it — BA-001's own review shows 15.7 bps/yr of cost drag against a benchmark's
5.7. What it is not is a way to earn money, and it should never have been
registered in the strategy column.
