# What a monthly income actually costs: four spending rules, one equaliser, and no surviving loan

Measured 2026-09-06. Tool: [`income_frontier.py`](../../tools/income_frontier.py) (20-year and 10-year plans,
`--years`, `--floor`, `--stride`), tests [`test_income_frontier.py`](../../tests/test_income_frontier.py).
Reproduce: `.venv/bin/python tools/income_frontier.py --years 10` and `--years 20`. The engine is
[`withdrawal_capacity.py`](../../tools/withdrawal_capacity.py), imported and extended, never re-implemented.

## Why this round priced a spreadsheet cell instead of a model

Round 7 measured withdrawal capacity and concluded, in its own words, that **the spending rule beats the
trading rule**: nothing on the menu moved the reliable monthly number as much as the decision about whether
the cheque is allowed to shrink. That decision costs nothing and needs no forecast. It has never been priced
across the rule family — the tool had one guardrail shape and a fixed cheque, and it could not express a
fixed-*fraction* cheque at all. Meanwhile eighteen rounds kept finding that a forecast is worth less than the
trade it causes. So the largest unmeasured lever in the repository was not a signal. It was the withdrawal
rule, and it is the thing the goal is written in: dollars per month.

## The equaliser

Comparing spending rules by their first cheque is the trick that makes every flexible rule look generous,
because a flexible rule's first cheque is a promise it withdraws in the worst year — the only year the number
is worth anything. So each rule is scored by the **smallest cheque it actually handed over, across every start
date in the record** — its floor — and each rule is scaled until it delivers a chosen floor, and only then
compared on the median mean cheque it paid. Same floor, compare the average. That ordering was fixed before the
first cell was computed.

Feasibility for every cell: **every** start date survives to the horizon **with no margin call**, on the
archive, at each sleeve's real expense ratio, 2 bps a unit one way, borrow at the archive cash index plus a
spread, forced sale at 30% equity. Levered rows are priced all-in at 4.90% — April 2026's cheapest posted base
tier — which against today's 3.51% cash index is a spread of +1.39%.

## The table, ten-year plans asked to promise $400 a month on a $100,000 lump

143 start dates (every second month, 1993-02 to 2016-10) unless stated. VOO has 37, all from 2010-10 to
2016-10: the mildest decade this asset class has seen, so VOO is the flattered party in every row, not the
injured one.

| plan | rule | floor paid | median/mo | ×floor | min end | at $20k |
|---|---|---|---|---|---|---|
| cash | fixed | $400 | $400 | 1.00× | 0.54 | $80 |
| cash | indexed | $400 | $453 | 1.13× | 0.48 | $91 |
| cash | guardrail | $400 | $530 | 1.32× | 0.41 | $106 |
| cash | fraction | **$256** | $352 | — | 0.64 | cannot promise $400 |
| SPY | fixed | $400 | $400 | 1.00× | 0.37 | $80 |
| SPY | guardrail | $400 | **$637** | 1.59× | 0.30 | $127 |
| SPY | fraction | $148 | $522 | — | 0.45 | cannot promise $400 |
| SPY 1.25× | fixed | $400 | $400 | 1.00× | **0.24** | $80 |
| SPY 1.25× | guardrail | $400 | $620 | 1.55× | 0.21 | $124 |
| SPY 1.50× | guardrail | $400 | $620 | 1.55× | **0.12** | $124 |
| VOO | guardrail | $400 | $797 | 1.99× | 1.26 | $159 |
| QQQ | all four rules | — | — | — | 0.00 | **died at 2000-02** |

Four things fall out of it, largest first.

1. **The spending rule is worth more than the asset.** Inside one plan the rules run 1.00× to 1.99× their own
   promise; the entire distance between the best and worst *plan* at this floor is $397/month, and most of
   that is VOO's flattering record. The guardrail — a rule with no forecast, no signal and no cost — is worth
   32% more income on T-bills and 59% more on SPY than the fixed cheque, at an identical guarantee. That is
   the biggest lever this repository has ever measured, and it is a checkbox.
2. **The loan is Redundant in this unit, and the capital tells on it.** At an equal floor a levered plan cannot
   pay more than the same sleeve unlevered, because a fixed cheque's median *is* its floor for every plan by
   definition — the plan only gets to choose whether the promise can be kept and what is left afterwards. And
   what is left is the whole story: the worst 10-year start leaves 37% of the lump on plain SPY, 24% at 1.25×
   and **12% at 1.50×**. Round 17's levered ticket earns +$23/month of *terminal* dollars; in the unit the goal
   is written in, the same mechanism pays $17/month less and halves what survives.
3. **A fraction of NAV cannot promise a dollar floor, and it is not close.** It is the only rule here that
   cannot die — feasible at every start, on every plan, QQQ included — and it is the only rule that cannot
   make a promise: on SPY its worst cheque is $148 against a $400 promise while its median is $522. High
   average, unreliable tail. The guardrail dominates it on both statistics at this floor, which is the
   opposite of the intuition that a flexible rule is the safe one. Note the guardrail's ratio is bounded at
   2.00× **by its own definition** (it keeps half its cheque), not by anything about markets; a test enforces
   that so nobody reads 1.99× as a finding.
4. **Twenty years is a different contest, and only two plans are still in it.** At $400 a month for 20 years,
   plain SPY and plain cash clear it under a fixed cheque; SPY also clears it under the guardrail (1.49×).
   QQQ dies at 1999-08 and 1999-04. **Both levered plans fail at every rule** — the 1.25× fixed cheque dies at
   2000-04, and the 1.50× guardrail row takes 8 forced sales on the way out. Cash keeps the fixed promise only
   because 2000-2004 T-bills paid 5-6%; its indexed and guarded rows both die (2000-06, 2004-06), which is the
   quiet reason a cash plan is a floor and not a retirement.

## The start grid is part of the claim

At stride 2 the 20-year levered rows fail; at stride 3 the 1.25× fixed row passes — with **8% of the lump left
at the worst start** — because the start date that ends it, 2000-04, is not sampled. A guarantee measured on a
coarse grid is a weaker promise wearing the same clothes, so the default is every second month and there is a
test that fails if this stops being reproducible. The *dominance* verdict does not move with the grid: the
levered plans are Redundant at stride 2, 3 and 6 alike (−$17 to −$197/month).

## Two bugs this round found in itself

- **`withdrawal_capacity.run` scored a cash account as ruined in its first month.** Its ruin test read
  `value <= 0 or position <= 0`, which is the same event for an all-equity book and a wrong one for a plan that
  never held a sleeve: every T-bill row this tool could ever have produced came back dead, and the repository
  has been quoting equity floors against a benchmark it could not compute since round 7. It also wrongly killed
  a 50/50 account whose sleeve a cheque had temporarily emptied. Ruin is now `value <= 0`, and the 36 tests
  that predate the change still pass, which is the evidence that it is behaviour-preserving for everything the
  tool has ever scored.
- **The frontier's own feasibility test ignored margin calls** for about an hour. Round 7's standard is that a
  call disqualifies the withdrawal whoever survives it; the calls were being accumulated and thrown away. Now
  they end feasibility and the count is printed — it is what finishes the 1.50× guardrail row at 20 years.

Both were found by tests written for other reasons, which is the third time in three rounds that the boring
test has been the one that matters.

## What this leaves the goal standing

Twenty rounds, and the honest answer in the goal's own unit is now measurable rather than asserted:

- No trading mechanism this repository has produced pays a larger **monthly** income than the same exposure
  bought cheaply. The loan that survived the accumulation tests is Redundant here and disqualified at 20 years.

*Amended the same day* in [`2026-09-06-candidate-frontier.md`](2026-09-06-candidate-frontier.md): that sentence
was written after pricing **constant** leverage, and round 8's pre-registered candidate — a volatility target
with a trend gate — had already raised a withdrawal floor and now clears the equal-floor bar too, +$123/mo per
$100k over the same sleeve held flat, with its own reversed path dying. The loan is still Redundant. The claim
about "no trading mechanism" was too broad, and the over-broad sentence is the one this file is most likely to
be quoted for.
- The one decision that reliably moves monthly income by a large amount is the spending rule, and it costs
  nothing: **a 25%-triggered guardrail that keeps half the cheque is worth 32-59% more income than a fixed
  cheque at an identical guarantee**, on the same asset, with no forecast anywhere in it.
- Therefore the bot's job is not to raise the cheque. If a bot is worth building at all, it is worth building
  to make the *cheap* promise (a guardrailled index withdrawal, or the T-bill floor) less likely to be cut — a
  drawdown problem, not an alpha problem — and every mechanism that has tried that here has lost to its own
  costs. That is a discouraging conclusion about trading and an encouraging one about the plan, and it is now
  supported by a table rather than by mood.

## Checks

`tests/test_income_frontier.py`, 19 tests, 1.7 s: a cash plan survives its first month and its ending is
hand-checkable arithmetic to six places; a cheque bigger than the sleeve is funded from the cash line and kills
nothing; a plan that loses its sleeve while holding one still dies; a fraction refuses to be indexed or guarded
and refuses values outside (0,1); a fixed cheque's median equals its floor to six places; no guardrail pays more
than twice its floor; the dollars scale linearly in account size; the floor every clearing rule actually pays is
the floor it was promised; `verdict()` says "not measured" for VOO at 20 years instead of "cannot promise"; no
levered plan pays more than plain SPY at an equal floor; the start grid is named as part of the claim. Full
suite: **1391 passed, 233 subtests**. `journalctl verify`: chain intact (1 entry), comparator spec
`100% SPY, fee 0.000945` unchanged — still $0.00 paid in.
