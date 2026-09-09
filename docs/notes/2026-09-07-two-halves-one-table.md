# The two halves of the objective, in one table: the model is worth $23.68 a month and the bond leg is worth $134

Measured 2026-09-07, round 58. Tool: [`monthly_income_race.py`](../../tools/monthly_income_race.py) (new). Tests: 13 in
[`test_monthly_income_race.py`](../../tests/test_monthly_income_race.py).

The objective asks for two things at once — *earn extra each month* and *beat VOO*. Rounds 51-57 priced each half
against different metrics, so they never had to meet. Here they meet: one $100,000 account, one 10-year plan, one
failure budget of 5%, four equity legs at round 57's optimum frequency (monthly), four bill weights, all legs on the
same panel so no leg gets a friendlier sample (round 51's rule). The plan is round 52's: a level withdrawal, failure
means ever hitting zero **or** finishing below the start.

## The same plan, priced in dollars a month (2006-02 → 2026-09, 127 windows)

| leg | bills | own best $/mo | P(fail) | med terminal | P(halved) | at the index's $435/mo |
|---|---:|---:|---:|---:|---:|---:|
| **SPY hold** | 0% | **435.47** | 5% | 2.32× | **12%** | 5% · 2.32× · 12% |
| SPY hold | 25% | 378.09 | 5% | 1.82× | 0% | **17%** · 1.71× · 0% |
| SPY hold | 50% | 297.32 | 5% | 1.46× | 0% | 24% · 1.22× · 0% |
| SPY hold | 65% | 235.24 | 5% | 1.29× | 0% | **67%** · 0.97× · 0% |
| MA200 monthly | 0% | **593.13** | 5% | 1.35× | 0% | **0%** · 1.66× · 0% |
| MA200 monthly | 25% | 480.61 | 5% | 1.23× | 0% | 0% · 1.31× · 0% |
| MA200 monthly | 50% | 368.71 | 5% | 1.10× | 0% | 51% · 1.00× · 0% |
| mom_top1 monthly | 0% | 525.45 | 5% | 1.32× | 0% | 1% · 1.49× · 0% |
| mom_top1 monthly | 50% | 342.51 | 5% | 1.11× | 0% | 73% · 0.96× · 0% |
| static 60/40 | 0% | **569.45** | 5% | 1.28× | 0% | **0%** · 1.52× · 0% |
| static 60/40 | 65% | 257.63 | 5% | 1.10× | 0% | 100% · 0.84× · 0% |

Four things fall out of this, and they do not all point the same way.

**The trading legs pay more income than the index and grow less of it.** MA200 supports **$593.13/mo against the
index's $435.47 — 36% more** — and ends the plan at 1.35× where the index ends at 2.32×. It also has a 0% chance of
being halved, against the index's 12%. This is the first round in which the objective's two halves are both true at
once, and they are true of the *same* account.

**Most of that improvement is not the model.** A static 60/40 — no signal, one trade a month, 0.0010%/yr of cost —
supports **$569.45**. Decompose the trend rule's $157.66 advantage over the index: **$133.98 of it (85%) is the bond
leg, and $23.68 a month is the trading model** — $284 a year on $100,000. The rotation leg is worse than the asleep
control, not better: $525.45 against $569.45, **$44/mo of negative work**.

**Bills raise income only when the equity leg is a trend rule.** For the index, every bill weight *reduces* the safe
amount (435 → 378 → 297 → 235), and at the index's own $435/mo the blended versions fail 17%, 24% and 67% of the time.
For MA200, bills also reduce income but never produce a failure below 25% bills. This inverts round 54's result that
the guaranteed cheque peaks at 65% bills, and the reason is conventions, not disagreement: round 54 measured an
*indexed* cheque over 20-year windows across the full record including the high-rate years, and this plan is *nominal*
over 10 years starting in 2006, the flattest rate era in the record. Same engine, same archive, different promise and
different decades, and the "bills help" conclusion belongs to one of them.

**At the same payout, safety and income are different levers.** Six cells survive the index's $435/mo with zero
failures; every one of them holds bonds.

## On the whole record, and under both promises (1993→2026, 284 windows)

| leg | "ends whole" $/mo | "never zero" $/mo | med terminal | P(halved) | P(fail) at $0 |
|---|---:|---:|---:|---:|---:|
| SPY hold | **0.00** | 763.82 | 2.32× | 1% | **8%** |
| SPY hold + 65% bills | 142.15 | 893.71 | 1.40× | 0% | 0% |
| MA200 monthly | **557.91** | **1,098.43** | 1.51× | 0% | 0% |
| MA200 + 25% bills | 474.25 | 1,064.41 | 1.29× | 0% | 0% |

Plain equity's "ends whole" figure is **zero, not small**: in 8% of 10-year windows SPY finishes below where it
started with *nothing withdrawn*, so before a single dollar leaves the account the sleeve has already spent the whole
5% budget. The same sleeve prices at $763.82 under the weaker "never liquidated" promise. **The gap between those two
columns is not arithmetic, it is which promise the reader thought they were buying** — round 54's rule, arriving
again with a bigger number attached. On the long record the trend rule beats the index under *both* promises, and the
index's panel-era premium ($435) turns out to be a property of the sample rather than of the sleeve: the rule's figure
barely moves between samples ($593 → $558) while the index's goes $435 → $0.

And the growth half, on the same engine: SPY 11.15% (max DD 55.2%), MA200 9.42% (24.2%), mom_top1 10.19% (29.3%),
static 60/40 8.31% (30.1%). **The model does not beat the index. It converts better.**

## Two defects, both caught by tests written from identities rather than from the output

**A tuple/date key mismatch, hidden by a default.** `long_history` built its signal dict keyed by `(year, month)`
tuples and read it back with the `date` objects `monthly_complete` returns, using `sig.get(k, 0.0)`. Every lookup
missed; every miss answered "hold cash"; the long-history MA200 row printed **$31.04**, which is what a bill yield
looks like on this plan. The tell was that the row below it — the same series blended 75/25 with bills — printed
**$31.04 too**. Two rows agreeing to the cent is a bug report, not a coincidence. Fixed with a strict lookup: **a
`.get(key, default)` whose keys are built somewhere else is a silent failure mode; make the lookup strict and let the
KeyError find the mismatch.**

**Month-end marks that were not at month end.** `wealth_path[i-1]` is the balance at `ordered[i]`; `month_marks` built
its index map as `i + 1` and subtracted 1 at the use site, so every monthly mark was the balance one trading day
*after* the month end. 246 marks, each a month-shaped object that was subtly not a month. The compounding identity —
the product of the marks must equal the ratio of two balances on the daily path — fails by 1.4% over the sample and
names the bug exactly. This is why the path runner is pinned to `run_weights` to ten places (it matches to the bit,
diff 0.0 on all four legs) and why the marks are pinned to the path: the duplication is the risk, and the identity is
the guard.

## What this says about the objective, at last

A trading model on this archive, at its best frequency, on its friendlier sample, with a real failure budget and real
costs, is worth **$23.68 a month per $100,000 of net advantage over an allocation that computes nothing**. It is worth
considerably more than that as *insurance* — 0% chance of being halved against the index's 12%, and no 10-year window
in the whole record in which it finished underwater — and it is worth less than nothing if the version of it you pick
is the rotation. It does not beat the index on growth and nothing in rounds 55 to 58 says it can.

## Checks

13 tests: the path runner must end where `run_weights` says the same weights end, to 10 places, on all four legs; the
monthly marks must compound exactly to the ratio of two balances on the daily path, must exclude the panel's first
month (a three-week observation in a month's clothing) and its unfinished last one; every leg must be measured on the
same number of months; a bill weight of 1.0 must return the bill series exactly; failure rate must be monotone in the
withdrawal; **the long-history trend series must not equal the bill series, and must not agree with its own bill
blend to the cent** (the regression above); a weaker promise must never price below a stronger one; an empty sample
must read `None` and not 0%; and the bisected amount must meet its own budget while the amount $50 above it does not.
Full suite **1715 passed** (collected first: 1702 + 13). `journalctl verify`: chain intact, comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
