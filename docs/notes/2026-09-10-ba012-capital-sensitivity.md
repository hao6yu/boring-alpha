# BA-012: virtual $25,000 and $100,000 sizing

**Both larger virtual accounts form nonzero portfolios in all 25 usable monthly
cases.** The $5,000 baseline forms none. This resolves the no-participation
problem in the observed complete cases; it does not establish profitability.

The user explicitly requested these two sizing cases. The inputs, capitals and
evaluation rules were recorded before running them. The calculation reused
the verified settlement panel and unchanged optimizer, with no new data charge.
All results below describe hypothetical child exposures on parent settlement
history, not native historical child executions.

| Virtual account | Verified nonzero portfolios | Verified cash cases | Incomplete cases | Active markets in nonzero cases |
| --- | ---: | ---: | ---: | --- |
| $5,000 baseline, reused | 0 / 25 | 25 | 47 | None |
| **$25,000** | **25 / 25** | **0** | **47** | **4–5** |
| **$100,000** | **25 / 25** | **0** | **47** | **5** |

The 25 usable dates are August–December 2019, January 2020, June–December 2022,
and all of 2023. The participation denominator excludes the 47 incomplete
windows. These are independent from-cash monthly sizing decisions, not executed
trades or a continuous historical account.

## Rules and measured capacity

The annual volatility target remains 8%: $2,000 of annual dollar volatility at
$25,000 and $8,000 at $100,000. The 20% simulated loss budgets are $5,000 and
$20,000 respectively. The $100 operating buffer is unchanged. Signals, 252-day
covariance, shrinkage, child multipliers, static margin proxies, costs, stress
shocks, three-group diversification, concentration, partial-fill requirements,
tracking objective and tie-breaks are all unchanged. These risk budgets are
model constraints, not guaranteed real-world loss limits.

At $25,000, NES, M6E, gold and corn are selected in every usable case; MTN is
selected in 15 of 25. Thus all cases span at least three asset groups. At
$100,000, every case includes all five markets and four groups.

Forecast terminal annual volatility as a percentage of post-entry equity is
7.266%–7.970% for $25,000 and 7.571%–7.998% for $100,000. These are risk estimates,
not annual returns. The minimum modeled funding headroom after stipulated
entry/exit charges, price stress, twice initial margin and the operating buffer
is $10,003.351 and $38,464.036 respectively.

All 50 new optimizations completed with verified optima. The maximum explored
search-node count was 87 at $25,000 and 712 at $100,000, below the unchanged
two-million-node limit. No solver limit was converted into a result. The
previously verified $5,000 baseline is copied with its source provenance.

An independent audit recomputed covariance from each pinned input and verified
all 50 selected portfolios and all 1,600 empty/full partial-fill states without
rerunning the optimizer. Signs, diversification, concentration, costs, stress,
funding and volatility constraints passed. Plan, input, script and all 72 result
hashes matched; the reused baseline matched exactly. Missing cases remained
unresolved throughout.

## Interpretation

The $25,000 case is the smaller tested account that permits participation in
every usable case. It is therefore a reasonable primary research candidate for
a subsequent return study, with $100,000 available as a capital-sensitivity
comparison. Neither balance is a deposit recommendation or a funded approval.

Both formal statuses remain `INCOMPLETE_STUDY_WITH_PARTICIPATION_EVIDENCE` because
47 of 72 scheduled input windows are unresolved. No CAGR, strategy profit,
path-dependent drawdown, account halt history, native liquidity or fill quality
was calculated at either capital. The earlier $5,000 cash/expense result cannot
be scaled into a larger-account return result now that positions are nonzero.

A return study must use a defined, causally timed execution model and reconcile
costs, rolls, daily risk changes and account equity. The downloaded settlements
are reference inputs; they do not establish the protocol's 10:01/10:03 fills.
No 2024–2025 holdout prices were read.

## Records

- Frozen request and inputs: `research/ba012-stage-a/capital-sensitivity-v2/plan.json`
- Reproducible offline calculation: `research/ba012-stage-a/capital-sensitivity-v2/run.py`
- Summary and provenance: `research/ba012-stage-a/capital-sensitivity-v2/summary.json`
- All 72 date records: `research/ba012-stage-a/capital-sensitivity-v2/results/`

No earlier protocol, data amendment, input report or result was overwritten.
