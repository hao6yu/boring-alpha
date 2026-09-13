# Earnings-language expansion: do not advance to a pilot

The fixed 200-company expansion completed acquisition, model fitting and its
2022–2023 evaluation. **The earnings-language candidate does not meet the
predeclared return requirement.** The text model's complete account returned
5.42% annually with base execution costs and 2.05% with stressed costs. Neither
exceeds the required 6%, and the base-cost evidence does not establish an
incremental advantage from language.

The original pending research was preserved in commit `b579208`. This expansion
retains that first 100-company cohort and all 3,200 registered quarterly slots.
It is an exploratory, coverage-driven extension, not independent confirmation.

## Actual results

All figures below use the fixed $5,000 account, whole shares, no leverage,
commissions and the entire recorded study data expense. Base/stress execution
loss is 10/50 basis points per side. Fees use the previously frozen IBKR Pro
Fixed schedule as a current-rate counterfactual. These are historical simulated
results before taxes, conditional on the declared source and fill assumptions.

| Model | Cost case | Annualized return | Ending NAV | Maximum drawdown | Completed positions |
|---|---|---:|---:|---:|---:|
| Numeric inputs plus earnings language | Base | 5.42% | $5,552.97 | 11.99% | 45 |
| Numeric inputs plus earnings language | Stress | 2.05% | $5,206.31 | 13.01% | 47 |
| Numeric inputs only | Base | 6.77% | $5,695.99 | 14.26% | 45 |
| Numeric inputs only | Stress | 0.20% | $5,020.29 | 15.72% | 45 |

Both scored models have complete account records for all 501 evaluation
sessions and no account stop. Text was active in all 24 months. NAV includes
unpaid dividend claims under the frozen convention; text ending settled cash
was $5,458.11/base and $5,122.59/stress, with $94.86/$83.72 in locked dividend
claims. No claim is treated as spendable without a verified credit date.

The text model lagged numeric-only by 1.36 percentage points of CAGR under
base costs. Its paired bootstrap estimate for the **annualized mean daily
return difference** was -1.48 percentage points, with a 95% interval of
**-7.94 to +4.59 percentage points**. This is a different estimand from CAGR;
the interval does not establish a positive language advantage. On all 731
evaluation outcomes, the text score's Pearson correlation was -0.003 and its
prediction MSE was 102.92 squared percentage points, versus 94.09 for numeric-only.

## One benchmark remains unresolved

The frozen full-suite evaluator reports **UNRESOLVED**, which is preserved in
[evaluation-result.json](evaluation-result.json). The unscored matched-event
control encountered `LIQUIDITY_DATA_UNRESOLVED` for the January 26, 2023 Triumph
Financial event (`0001539638-2023Q1`) across the TBK/TFIN history join. Its
control-account metrics therefore remain unpublished. This is a candidate-input
coverage gap; the simulation reported no unpriced holding days.

The evaluator conservatively suppresses several suite gates when any required
control is unresolved. That does not erase the separately complete scored-model
results above: **text fails the 6% hurdle in both cost cases, fails the base
1-percentage-point advantage requirement, and fails the positive bootstrap
lower-bound requirement.** Resolving the third control cannot turn those known
failures into passes. No source changes, refits, threshold adjustments or second
evaluation followed the result. The numeric baseline's stressed 0.20% return
also provides no basis for advancing it as an alternative income strategy.

## What was actually completed

- Selected the first 200 eligible companies from the same fixed 2019-Q3 hash
  ranking, preserving the original 100 companies and first 155 rank decisions.
- Completed all 200 issuer source passes: 6,346 new SEC attempts and 109 new
  free price requests, below the registered limits. Price responses: 99 histories
  and 10 empty histories. No new paid data was purchased.
- Retained all 3,200 slots and their missing/ineligible states. The final sample
  supplied 360 usable 2020 fit events, 393 usable 2021 validation events, and
  731 evaluation candidates across 117 companies. All 731 evaluation labels
  were available after the forecasts were frozen.
- Checked original issuer ownership, entry timing, prior-source availability,
  corporate actions and missing-data treatment. A fixed sample of 32 financial
  cells matched 11 original financial tables. This bounded root-agent review
  does not certify population accuracy or constitute an independent replication.
- Reused the fixed models, features, execution rules and metrics. Both models
  selected alpha 1.0 from the registered grid. One null-date guard was repaired
  before any fit; two new synthetic regressions prove missing slots preserve
  fitted models and cannot conceal evaluation labels. The first failed pre-fit
  manifest and repair record are retained.

The $0.012873232367 inherited data expense uses its existing quoted basis, not
a claimed new invoice. The daily closing-limit fill proxy, effective-status
observability convention, vendor-based distribution entitlements, conservative
cash locks and incumbent-only cohort limit the interpretation. The 2024–2025
equity strategy price window remains reserved. No live or paper trading,
subscription, account change or funded pilot was started.

**Decision: stop this candidate under the current protocol.** Keep the data and
test infrastructure as research assets. Another experiment would need a distinct
economic hypothesis and a new fixed budget; these results do not establish that
quantitative trading in general is impossible.
