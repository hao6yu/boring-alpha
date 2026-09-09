# The shelter is worth $64 to $224 a month of extra income, and the ranking has nothing to do with the shelters' own returns

Measured 2026-09-07, round 64. Tool: [`shelter_test.py`](../../tools/shelter_test.py) (new). Tests: 18 in
[`test_shelter_test.py`](../../tests/test_shelter_test.py).

Every income figure this repository has published credits the trend rule's off-equity half — **25% of days on this
panel** — with Treasury bills. The standing objection is decent: bills pay a rate, bonds and gold pay a return, and in
the episodes where a payout plan actually breaks, Treasuries return what equities lost. This round changes only the
shelter: same signal (round 58's month-end MA200 on SPY), same panel, same engine, same costs. The yardstick is round
58's own — the largest level monthly withdrawal whose ten-year failure rate stays under 5% — so the cash row has to
come back at **$593.13** before any delta below means anything. It does, to the cent.

| shelter | ER | safe $/mo | vs cash | P(fail) @435.47 | own CAGR | **held CAGR** | held maxDD | $/mo per pt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cash (bills) | — | **593.13** | — | 0.0% | 1.71% | — | 0.0% | — |
| IEF (7-10yr) | 0.60% | 657.16 | **+$64.03** | 0.0% | 3.21% | **7.40%** | 13.9% | 4.60 |
| IEF+TLT | 0.60% | 675.38 | +$82.25 | 0.0% | 3.09% | 7.98% | 21.3% | 3.87 |
| TLT (20yr+) | 0.60% | 683.33 | **+$90.20** | 0.0% | 2.75% | **8.23%** | 29.3% | 3.08 |
| GLD (gold) | 0.60% | 816.63 | **+$223.50** | 0.0% | 10.06% | **11.94%** | 29.4% | 7.60 |
| DBC (commodities) | 0.60% | 353.93 | **−$239.20** | **22.8%** | 2.51% | **−8.51%** | 63.6% | −3.76 |

Every shelter's fees are **not posted in this repository**, and `trend_cost_test.daily_legs` hands back `0.0` for them
via `.get(symbol, 0.0)` — round 58's silent-failure mode, live in the plumbing. Nothing here is scored at a zero fee:
each shelter is priced at 0.20%, 0.35% and 0.60%, the table shows the **pessimal** fee, and the sign of every row is
the same at all three (the fee moves IEF's gain by $5.78 across a 40bp range). The `$/mo per pt` column divides the
income gain by the shelter's drawdown *while held*, because a leg that swings 29% is not sheltering.

## The shelters' own histories rank them wrong; the episodes the signal picks rank them right

Ordered by unconditional return: TLT 2.75% < IEF 3.21% < GLD 10.06%. Ordered by income capacity: IEF $657 < TLT $683 <
GLD $817. **The first two are inverted.** Ordered by what each pays *while the rule actually holds it*: DBC −8.51% <
IEF 7.40% < IEF+TLT 7.98% < TLT 8.23% < GLD 11.94% — which gets every pair right, including DBC, whose −$239/mo and
22.8% failure rate are the reason the metric is trusted elsewhere.

Every shelter except commodities earned **more** while held than over its whole history (IEF 7.40% against 3.21%, TLT
8.23% against 2.75%), and every one drew down *less* while held than it ever has (TLT 29.3% against 48.4%). The reason
is the signal, not the asset classes: a month-end MA200 exit is a stress detector, and stress is when bonds and gold
rally. That is the whole finding, and it cuts both ways — the shelter's usefulness here is a property of the rule's
timing, so it is not a general fact about TLT that can be carried into a different strategy, and it cannot be counted on
in a stress the rule fails to detect.

## The two things that limit this before any fee does

**The data boundary.** IEF and TLT begin 2002-07-30, GLD 2004-11-18, DBC 2006-02-06. Round 62 located the entries that
break an index payout plan at **1998-02 to 2007-07, mostly 1998-2002**. No bond or gold ETF in this archive exists for
the first half of that stretch, so the table prices the shelter for the twenty years it has been quotable and not for
the crash it was invented for. The one thing that *can* be said about that episode is the opposite of the objection:
the rule went to cash and survived all 56 of those entries anyway (round 62).

**What gold in the shelter actually is.** GLD wins the income table by a distance and has a **29.4% drawdown while
being held** — nearly half of what the equities it is supposed to be hiding from did. A portfolio that holds gold when
it is out of stocks is running two bets and calling the second one insurance. It is a legitimate choice and it is not
the one the objection was about. The bond answer is worth +$64 to +$90/mo per $100k (+$160 to +$225 on $250k), clears
round 60's $25/mo bar at every fee, and IEF is the efficient version of it: the smallest held drawdown in the table and
the second-best income per point of that drawdown.

## Checks

18 tests, 7.7 s, offline. **The cash row must still print $593.13** (±1¢) — round 58's published figure, twelve rounds
down, or the whole comparison is measuring the harness. The panel is pinned at `2006-02-07` and 246 complete months,
identical for every shelter. Weight algebra: a cash shelter returns the signal untouched; an ETF shelter leaves the
equity weight unchanged, holds exactly `1 − w` in the shelter and zero everywhere else, and sums to 1.0 so nothing leaks
into cash by accident; a composite splits it evenly; an equity weight above 1.0 raises rather than being absorbed; the
fee lands on the shelter and not the equity; and a dearer shelter cannot support more income. `max_drawdown` checked
against hand-built paths. The conditional statistic: a 50/50 bond shelter's drawdown lies between its halves; a constant
+1% series compounds to 1.01^252 − 1 over one year; and the ordering claim above, including the IEF/TLT inversion and
the fact that DBC is the one shelter that pays *less* while held than over its history. Full suite **1805 passed**
(collected first: 1787 + 18). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
