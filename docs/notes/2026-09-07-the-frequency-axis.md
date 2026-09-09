# What the short term costs: both families peak at monthly, and the reason differs

Measured 2026-09-07, round 57. Tool: [`frequency_cost.py`](../../tools/frequency_cost.py) (new). Tests: 13 in
[`test_frequency_cost.py`](../../tests/test_frequency_cost.py).

Rounds 55 and 56 tested two families, each at one frequency, and both lost. The objective's own words are about
*short-term* trading, so this round varies the one thing the objective specifies — how often the model acts — and
holds the information fixed. Two families carried forward rather than invented (`ma200`, `mom_top1`), six frequencies
from annual to daily, one accounting engine, on the 2006-02 → 2026-09 panel (5,177 days, 20.5 years). Gross charges
the expense ratios and no trading cost; net adds the posted 0.0002 one-way, and again at 4x.

## MA200 — the information does not care how often you read it

| freq | updates | exposure | GROSS | net@1x | net@4x | max DD | trades/yr | cost/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| annual | 19 | 66% | 9.01% | 9.00% | 8.98% | 38.9% | 0.3 | 0.0068% |
| quarterly | 78 | 74% | 8.30% | 8.28% | 8.22% | 33.7% | 0.9 | 0.0185% |
| **monthly** | 235 | 75% | **9.45%** | **9.42%** | 9.32% | 24.2% | 1.5 | 0.0302% |
| biweekly | 493 | 75% | 8.64% | 8.60% | 8.46% | 21.8% | 2.1 | 0.0419% |
| weekly | 985 | 75% | 9.05% | 8.98% | 8.79% | **19.7%** | 3.0 | 0.0594% |
| daily | 4,924 | 75% | 8.86% | 8.74% | 8.38% | 20.7% | 5.5 | 0.1100% |

Gross spans **1.15pp across the entire axis with no trend at all** — annual 9.01% against daily 8.86%. A 200-day
average is the same number whether you look at it once a year or every morning. What does move monotonically is the
invoice (cost/yr rises 16×, 0.0068% → 0.1100%) and the **drawdown, which improves steadily: 38.9% → 19.7%**. So the
sensation that watching more closely is working is not imaginary — the equity line really does get smoother — while
the payment happens in the column nobody screenshots.

## Momentum — here the information itself degrades

| freq | updates | exposure | GROSS | net@1x | net@4x | max DD | trades/yr | cost/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| annual | 19 | 76% | 5.91% | 5.88% | 5.81% | 64.3% | 0.8 | 0.0243% |
| quarterly | 78 | 84% | 8.33% | 8.28% | 8.12% | 42.2% | 1.4 | 0.0497% |
| **monthly** | 235 | 83% | **10.29%** | **10.19%** | 9.90% | **29.3%** | 2.4 | 0.0886% |
| biweekly | 493 | 83% | 9.15% | 8.95% | 8.37% | 30.2% | 4.8 | 0.1782% |
| weekly | 985 | 83% | 7.89% | 7.61% | 6.77% | 29.0% | 7.1 | 0.2619% |
| daily | 4,924 | 83% | 7.53% | 6.86% | **4.88%** | 40.1% | 17.0 | 0.6222% |

Both families peak at **monthly**, the slow end of the axis. For momentum the gross figure falls from 10.29% to
7.53% — **2.76pp of the loss is the information getting worse, not the bill getting bigger**: a 12-month ranking
recomputed every day is mostly noise about which sleeve had the best fortnight. Net 6.86%, and at 4x slippage
**4.88% against 11.15% for doing nothing**, with a worse drawdown than the monthly version (40.1% against 29.3%).

| family | best freq | net@1x | daily net | faster costs | gross moved | DD at best | DD daily |
|---|---|---:|---:|---:|---:|---:|---:|
| ma200 | monthly | 9.42% | 8.74% | 0.68pp | +0.59pp | 24.2% | 20.7% |
| mom_top1 | monthly | 10.19% | 6.86% | 3.33pp | +2.76pp | 29.3% | 40.1% |

And at the optimum — monthly, the friendliest point on the axis — **both still lose to holding SPY at 11.15%**.

## The defect the tests caught, which was not in any headline

`signal_days("daily")` returned every index and skipped the warm-up gate that every other frequency applied. The
momentum slice for a 252-day ranking is `rets[s][i-251:i+1]`, and **Python clamps a negative start to zero** rather
than raising, so the first daily signals were computed from one to a handful of days of history and treated as a
year of evidence. Caught by `test_every_family_holds_cash_until_its_first_signal_at_every_frequency`, not by anything
being visibly wrong. After the fix the daily row moved from 7.51% gross / 6.84% net to 7.53% / 6.86% — the conclusion
was never load-bearing on it, which is exactly why a defect like this survives review: it changes nothing you are
looking at. → **A negative slice start is not a guard clause, it is a silent redefinition of the signal, and warm-up
belongs to the engine rather than to each caller that remembers it.**

## What this says about the objective

The objective's plan is short-term trading. On the frequency axis itself, the optimum is **monthly**, and both
directions from it are deductions: slower misses regime (momentum annual: 5.88%, DD 64.3%), faster pays for noise
(momentum daily: 6.86% net, 4.88% at 4x). The one component of "short term" that measurably improves is drawdown, and
it improves most for the rule that trades least often after monthly. Nothing here says a person cannot trade; it says
the *short-term* part of the plan is the most expensive part of the plan and buys the least.

## Checks

13 tests, 3.1 s, offline: the frequencies must nest as their names claim (annual ⊂ quarterly ⊂ monthly, biweekly ⊂
weekly ⊂ daily) and the sub-monthly counts must be exactly the arithmetic they imply, so a swap to a calendar rule
fails rather than quietly measuring an accident; a 200-day average must be `None` on day 199 and exact on day 200;
every family at every frequency must hold cash until its first signal; MA200's gross must span under 1.5pp across the
axis; momentum's *gross* monthly-to-daily gap must exceed 2pp (the information, not the invoice); both families must
peak at monthly; costs must be linear in the multiplier to 10 places and never help; both families must lose to SPY
at all six frequencies; daily momentum at 4x must stay under 6% and at least 5pp behind the index. Full suite
**1702 passed** (collected first: 1689 + 13). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`,
$0.00 paid in.
