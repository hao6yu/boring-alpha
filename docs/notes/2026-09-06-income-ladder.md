# What capital clears a monthly target, and the grid artefact that made long plans look safer

Measured 2026-09-07, round 50. Tools: [`income_targets.py`](../../tools/income_targets.py) (new),
[`income_accounting.py`](../../tools/income_accounting.py) (`guarantee(..., until=)`). Tests: 13 in
[`test_income_targets.py`](../../tests/test_income_targets.py).

## The question was always in dollars, and every tool answered it at someone else's capital

The ledger prices actions at $20,000. The guarantee engine prices stances at $100,000. The objective is stated as
*"earn extra each month"*. Nobody had inverted the arithmetic to ask what capital produces a given cheque, which is
the only form of the answer that can be acted on. So the table, with `required = target × 12 / rate`:

| engine | cash %/yr | $500/mo needs | regime-sensitive? | principal |
|---|---:|---:|---|---|
| systematic sale, common start grid | 8.28% | $72,439 | no | consumed |
| **systematic sale, SPY 1.0×, worst start in 33y** | **4.37%** | **$137,192** | **no** | consumed |
| T-bill ladder, today's bill curve (3.91%) | 3.82% | $157,046 | **total** | intact |
| T-bill ladder, the record's median month | 2.04% | $293,657 | **total** | intact |
| the ledger's variance-free rows, as a yield | 1.84% | $326,158 | low | n/a |
| SPY's own distribution yield (from the dividend file) | 1.65% | $362,679 | low | intact |
| the 1.25× tilt, as a yield | 1.63% | $367,107 | total | n/a |
| T-bill ladder, the zero-rate era | **−0.00%** | **never** | total | intact |

Two things fall out, and the second one is the round's rule.

### 1. The ladder loses to just holding the index, at both comparators

The P0 rule asks whether an action beats plain DCA into the same thing, net of costs. Applied to *income*, the
comparator is the index with a sale rule, and it is computed by the existing engine over every start date in the
record: **4.373%/yr, guaranteed against the worst of 165 20-year starts** — linearity in capital verified at
$40k and $250k, so the inversion is legal. The ladder needs **$157,046** for $500/mo at today's 65th-percentile
bill; the sale rule needs **$137,192**. At the record's *median* bill the ladder needs **$293,657**, 2.1×, and in
2021 it clears no target at any capital — net of SGOV's 9bp and the spread over the sweep, the zero-rate era's
ladder rate is **−0.00%**, so "never" is arithmetic and not a rounding.

And it is the fragile one of the two. The sale rule's rate is a path minimum, so it does not care what the Fed does;
the ladder's rate *is* what the Fed does. **Cash income is not a strategy, it is a decision not to hold equities,
and the archive prices that decision at roughly half the cheque and all of the regime risk.** The ladder's only
live defence is that you are not allowed to sell — a behavioural constraint, not an economic one, and the honest way
to hold it is as a constraint you chose, not as a yield.

### 2. A guarantee is a minimum, and nobody had printed the sample size next to it

The horizon table, SPY at 1.0×, per $100k per month:

| years | raw guarantee | starts | on one common grid | starts | raw says |
|---:|---:|---:|---:|---:|---|
| 10 | $592.97 | 285 | $1,269.14 | 44 | — |
| 15 | $428.91 | 225 | $853.12 | 44 | falls / falls |
| 20 | $364.45 | 165 | $690.23 | 44 | falls / falls |
| 25 | $333.98 | 105 | $617.58 | 44 | falls / falls |
| 30 | **$577.73** | 45 | $581.25 | 44 | **RISES (impossible)** / falls |

A 30-year plan guaranteeing **more** than a 20-year plan is not a result, it is a bug in the comparison: a longer
plan can only start earlier, so its grid *shrinks* — at 30 years there are 45 starts, all of them 1993 to
September 1996, while the 20-year minimum is taken over 165 starts that include the 2000s. **The minimum is not
measuring patience, it is measuring which decade you sampled.** Re-measured on one shared 44-start grid the
guarantee falls monotonically at every step — 1,269 → 853 → 690 → 618 → 581 — which is the only shape the
arithmetic allows.

The direction makes this worth a rule rather than a footnote: the artefact *flattered* the longest, most prudent
plan, in the direction nobody questions. Note also that the control moves the short horizons by 2.1× and the 30-year
row by 0.6% — it is nearly a no-op exactly where the raw grid already coincides with the common one, which is the
cleanest available proof that the two columns differ because of the sample and not the method.

So `guarantee(..., until=)` exists, and the rule it enforces: **print the count next to every minimum, and never take
a slope across minima computed on different samples.** The published $364.45 stays the headline — it is the
conservative conditioning (any start, 165 of them), and the common-grid $690.23 is the number conditional on a
pre-1996 start, which is a different claim. This is r44's rule turned inside out: condition an income on the state
before calling it income, and condition a minimum on its grid before comparing it.

## What this says about the objective, in the objective's own units

To clear **$500 a month** with a number that survives the worst 20 years in the record, the requirement is
**~$137,000 in the index with a systematic sale rule** — no model, no leverage, no signal, and the guarantee is
computed after costs, sweep cash and posted borrow. At today's $20,000 the honest monthly figures this repository
has ever defended are: the cash switch **+$63**, the variance-free rows **+$31**, and the leveraged tilt **+$27**
with a guarantee *below* the unlevered one. There is no configuration of the measured edges here that produces
$500/mo at that capital; the capital, not the model, is the binding quantity.

## Checks

13 tests, 1.8 s, offline. The inversion must round-trip to 8 decimal places at three rates and three targets;
`required` must be infinite at zero and negative rates; the guarantee must be capital-invariant to 10 places
(verified at $40k and $250k — the table's whole premise, tested rather than assumed); the common grid must hold one
sample count across all five horizons and stay strictly monotone; the raw grid **must keep its non-monotone step**
(pinning the defect so the control cannot be "simplified" away, and so the claim dies loudly if the archive grows);
the horizon claim must survive with no refinement flag present; the median-month ladder must stay ≥2× the sale
rule's required capital; and the zero-rate-era rate must stay ≤ +0.10%, because the printed "never" depends on it.
Full suite **1610 passed** (collected first: 1597 + 13). `journalctl verify`: chain intact, comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
