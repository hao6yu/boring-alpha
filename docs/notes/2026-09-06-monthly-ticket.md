# The monthly ticket: the surviving mechanism, priced at the size of the account in front of it

Measured 2026-09-06 on `data/current` (`methodology: yahoo-adjusted-v2+dgs3mo-v1`, dividend-adjusted closes,
through 2026-09-04). Tool: [`../monthly_ticket.py`](../../tools/monthly_ticket.py), tests:
[`../tests/test_monthly_ticket.py`](../../tests/test_monthly_ticket.py). Reproduce with
`.venv/bin/python tools/monthly_ticket.py [--sleeve SPY] [--lever 1.25] [--desk Public] [--value 20000] [--window full] [--json]`.

## Why this round exists instead of another test

Fifteen rounds have measured signals against plain DCA into the same fund. The scoreboard is one mechanism
wide: **constant leverage on a broad equity sleeve**, which carries no forecast, reads no news and responds
to nothing (rounds 4, 11, 12 — clears 1.25× and above on four of eight posted desks, median +$95/month at a
cheap desk, negative at the dearest). Everything the goal actually asked for — short-horizon decisions
informed by trend and news — has been priced and failed: BA-001–004, mean reversion, the overnight split,
weekly and daily timing, sector and timing overlays, cross-sectional rotation at full weight and at every
fraction of it.

What was missing was not another window. It was the artifact: a document with numbers in it that says what
to do this month, what it costs, what it has to earn, and — the part that decides whether any of it is
research rather than advocacy — **when to refuse**. So this file issues tickets and refuses them, on top of
the existing engine and the existing desk menu, re-deriving nothing.

## The default ticket, in full

1.25× SPY at Public's 4.900% base tier, written against $20,000 of NAV, priced at SPY $770.19 on 2026-09-04:

| | |
|---|---|
| target exposure | $25,000 (32.46 units) |
| the loan | $5,000 |
| carry, billed monthly | **$20.42** (122 bps of NAV a year) |
| delever trigger | SPY **$220.05** — a 71.4% fall forces the position to 1.00× |
| margin calls on the archive, same book | **0** |
| break-even borrow, all-in | full **8.72%** · since 2010 11.58% · recent 14.84% |
| headroom at Public | +3.82% (the binding window decides, never the average) |
| expected excess over unlevered DCA | +143 bps a year by the identity, **+136 bps** on the book's own measured costs |
| **at $20,000 of NAV** | **+23 dollars a month**, or +1.36% a year |

The ticket prints two money figures and keeps them apart on purpose: the archive's own run of this policy is
+$142/month, and it belongs to a path whose $500 deposits compound for the entire window. The account line
is the one that applies to anyone reading this. **The archive's headline is what this policy pays at roughly
$125,000 of NAV** — which is the actual content of the number that has been quoted around this repo since
round 11.

## The size ladder, because it is the only table that answers the goal as asked

Excess is `(L − 1) × (sleeve return − borrow rate)` minus measured costs: **linear in NAV, by construction**.

| NAV | carry billed | excess | what it would take |
|---|---|---|---|
| $5,000 | $5.10/mo | +$6/mo | noise, and one share of SPY is 15% of the position |
| $20,000 | $20.42/mo | +$23/mo | the default ticket |
| $50,000 | $51.04/mo | +$57/mo | — |
| $100,000 | $102.08/mo | +$114/mo | — |
| $200,000 | $204.17/mo | +$227/mo | the tier where the desk's rate actually drops |

So the constraint on "earn extra each month" is not the model and not the research. It is the size of the
balance sheet, and the mechanism is a *multiplier* on it — 1.25× of a small account is a small number of
dollars and a full-size drawdown.

## Refusal is the load-bearing feature

`--desk Fidelity` (10.575%, the rate on the menu at the largest custodian) prints no order and names the
number that refused it:

> REFUSED. Fidelity posts 10.575% and the break-even on the least generous window is 8.72% (full: 8.72%,
> since 2010: 11.58%, recent: 14.84%). Borrowing at this rate to buy SPY is expected to lose against just
> buying SPY. Desks that clear 8.72% on today's menu: Public, Robinhood Gold, IBKR Pro, Moomoo.

Three exit codes, deliberately distinct: **0** issued, **1** this desk is too dear (a fact about the world,
fixable by moving brokers), **2** there is no loan here to write a ticket about (`--lever 1.0`, which prints
"buy the sleeve; the comparator in every note in this repo is exactly that"). Exit 1 on a `--json` ticket is
what a future cron would gate on. `test_the_menu_decides_the_verdict_not_the_tools_opinion_of_leverage`
grades all eight desks against the threshold rather than trusting the tool's mood, and
`test_the_engine_can_actually_fire_the_rule_this_ticket_promises` checks at 3.0× that the forced-sale rule
the ticket invokes is capable of firing at all — 26 calls, because 3.00× sits at 33% equity against a 30%
requirement.

## What the trigger line taught me, twice

The first version printed `1 − L·m`. The exact breach point of a fixed-dollar loan is
`f* = (1 − m·L) / (L(1 − m))`, and the two forms cross at **L = 1/(1 − m) = 1.43×** at a 30% ratio. Below the
crossover the approximation is conservative by ~9 points of price — the kind of error that survives review
because it always looks like prudence. Above it the same formula tells the operator to watch a price the
broker has already breached: **a protective number that inverts its own sign of safety at a leverage nobody
was looking at**. 1.25× is on the safe side; 2× is not, and neither is anything a leveraged sleeve would
want. The crossover is now asserted numerically at exactly 1/(1−m), not just described.

The trigger is also honest about its own assumption. It is the price at which a loan that *just sits there*
gets force-sold. The same book rebalanced to target delevers as it falls and never gets there: 0 calls at
1.25×, 1.5×, and 2.0× across the full archive, which includes SPY's worst peak-to-trough fall of **−55.2%**
(110.87 into 2009-03-09, pinned in a test because every leverage conclusion in this repo is measured against
that one drawdown). So the real risk at 1.25× is not the margin call, which the archive never came within
16 points of price of triggering — it is the drawdown itself: −63% of account value at 1.25× in the same
window in which the policy earns +136 bps.

## The honest reading for the goal

This is the first artifact in the repository that produces an instruction rather than a verdict, and what it
instructs is worth **$23 a month at $20,000**, on a mechanism that is 25% borrowed large-cap equity and
nothing else. That is what survived fifteen rounds of testing against the only bar that matters, and the
number has been stated rather than the archive's six times larger version of it.

Three consequences follow, and they are the round's real output:

1. **The forward record is now writable.** The ticket emits a plan string and a `--json` form, so the journal
   can be closed against a *stated* policy instead of a mood. The ledger is still one entry and $0.00 paid in.
2. **The rate is the whole trade.** 710 bps of dispersion between desks dwarfs every signal this repo has
   ever measured; the same policy is +$23/mo at one custodian's posted rate and refused at another's. If the
   plan is real, the desk is the decision.
3. **The goal as literally stated is still unmet, and the reason is now quantitative.** A bot that reads news
   and trades short horizons has to beat +136 bps a year *plus its own costs* to justify itself over this
   baseline, and every attempt here at beating that baseline with price-only information has come back
   negative net of the shelf it sits on. The remaining door is an input the archive does not contain.

## Checks

`tests/test_monthly_ticket.py`, 18 tests, 31 s: the cheap desk is issued and the dear desk refused, with the
refusal naming its binding break-even and printing no order; all eight menu desks graded against the
threshold; exit codes 0/1/2 distinct; the printed trigger price breaches at exactly the maintenance ratio to
nine decimals; the naive approximation pinned on both sides of its crossover, including the crossover itself;
trigger direction monotone in leverage in both fall and price; the archive's −55.2% drawdown reconciles the
0 margin calls at 1.25× and the reachability of the trigger at 2×; the rule is shown to be *able* to fire at
3.0×; the money line scales exactly linearly in NAV while the bps do not; the archive figure and the
account figure both print and differ by an order of magnitude at $5,000; every printed identity recomputes
from the ticket's own fields; all 40 sleeve×desk combinations price without a zero; and the binding window is
the minimum, not the mean. Full suite: **1349 passed, 233 subtests**. `journalctl verify`: chain intact
(1 entry), comparator spec `100% SPY, fee 0.000945` unchanged.

*Followed by* [`2026-09-06-attention-feed.md`](2026-09-06-attention-feed.md), which took the other half of the
goal — the forecast, rather than the financing — and priced a point-in-time non-price feed against this same
$25/mo bar. It is worth −$87 to −$479 a month, and the ticket is the only survivor; the $23/mo figure above is
now the number any news idea has to beat.
