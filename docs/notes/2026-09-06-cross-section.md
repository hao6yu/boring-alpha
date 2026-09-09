# The rotation bar: nine sleeves, one bet, and a signal that cannot pay for its own universe

Measured 2026-09-06 on `data/current` (`methodology: yahoo-adjusted-v2+dgs3mo-v1`, all closes
dividend-adjusted, every sleeve ending 2026-09-04, 73,009 distribution rows). Tool: [`../cross_section.py`](../../tools/cross_section.py),
tests: [`../tests/test_cross_section.py`](../../tests/test_cross_section.py). Reproduce with
`.venv/bin/python tools/cross_section.py [--cost-bps 0.3|2|5] [--lookback N] [--window …]`.

## Why this round exists

Round 13 established that weekly timing on one sleeve needs 63–98% of its calls right and its rules
show 41–83%. Round 14 established that reviewing the same signal daily lowers the bar by two to four
points and the money by more, because a faster clock buys *events*, not *independent evidence*. Both
rounds ended at the same sentence: a rule needs many roughly independent bets, and one autocorrelated
price series cannot supply them. This archive contains nine tradeable sleeves across four asset
classes, which is the only place in the repository where that premise can be tested instead of
asserted — a cross-sectional rule makes a decision every month by *comparing* sleeves, so it does not
have to ask the same asset the same question twice.

It is also the rule family closest to the goal as it was actually stated. "Beat VOO or QQQ" is not a
directional claim about the market. It is a claim about *which* sleeve to hold this month, which is
what a rotation answers, and a monthly rebalance is short-term trading in the only sense a $500-a-month
account can execute.

## What was fixed before the first run

Not a number — a rule, and it is worth restating because the result is read entirely in its terms:

- **Two comparators, neither of which grades the other.** `equal-weight all` is the P0 dominance test:
  a rotation that cannot beat buying every sleeve it is allowed to name, on the same deposits and the
  same calendar, is paying for the privilege of ranking them. DCA into the index fund is the *goal's*
  bar, because the alternative to a rotation in this account is not a basket of nine funds, it is the
  boring thing that would have been bought instead. Both must be beaten.
- **Pass rule.** Beat both, in every window, at 0.3 and 2 and 5 bps a leg, with the reversed ranking
  losing. If the reversal wins too, the ranking is carrying nothing and the rest of the table is void.
- **The bar is solved, not counted.** `bar` is the fraction of rebalances at which the shadow rotation
  must hold the ranking's own pick instead of falling back to the equal-weight basket, for its account
  to reach what index DCA reaches. Money is linear in that fraction — a month is either the pick or the
  basket, so the account is a blend of two fixed books — which makes the solve exact rather than
  simulated. `hits` is the realised share of months where the pick beat the basket, printed next to it
  as a *wedge*, not as evidence: round 13's rule r13 says a count cannot rank two books the money
  already ranks.
- **Availability, not intersection.** The panel runs on the SPY calendar and each sleeve is unavailable
  before its own listing. The obvious alternative — keep only month-ends where every sleeve trades —
  makes the sample begin in September 2010 because VOO listed then, which would have thrown 2007, 2008
  and 2009 out of a momentum test. Nine sleeves' first-scored month is 2007-03-30, thirteen months of
  warm-up after DBC's February 2006 listing, and 235 scored months to the end of the archive.
- **Expense ratios, priced not typed.** Seven of these sleeves had no ratio pinned anywhere in this
  repository, and a cross-sectional test that charges the same fee to every sleeve is testing an
  assumption, not a rotation. IWM 0.19%, EFA 0.32%, EEM 0.72%, TLT 0.15%, IEF 0.15%, GLD 0.40%, DBC
  0.87% are pinned as literals with the issuers' published numbers, alongside the five already in
  `withdrawal_capacity`. The cheapest and dearest sleeve here differ by 72 bps a year, which is more
  than most timing edges this repository has ever measured.

Two things the design chose *not* to do. VTI and ITOT are excluded from the ranked set — they are the
same bet as SPY at the same fee, and a top-3 that can hold all three has made one bet three times.
VOO is excluded from the ranking because it is the bar, and a bar does not compete with what it grades;
before VOO existed the bar is SPY, printed as its own row rather than folded into an invisible splice.

## The table: 2007-03 to 2026-08, 235 months, 2 bps a leg

| rule | ending | $/mo vs equal-weight | $/mo vs index | turnover | fees | worst dip | hits |
|---|---|---|---|---|---|---|---|
| always SPY | $580,590 | +$544 | +$24 | 0.1× | $1 | −22.8% | 56.2% |
| **index DCA (SPY→VOO 2010)** | **$568,889** | **+$520** | **±$0** | 0.2× | $11 | −22.8% | 56.2% |
| equal-weight all | $314,677 | ±$0 | −$520 | 0.1× | $1 | −18.2% | — |
| top-1 momentum | $388,312 | +$151 | −$370 | 7.5× | $2,480 | −39.2% | 53.2% |
| top-2 momentum | $397,567 | +$170 | −$351 | 5.9× | $2,482 | −23.4% | 51.5% |
| top-3 momentum | $456,028 | +$289 | −$231 | 4.7× | $2,371 | −13.6% | 54.9% |
| top-2 **reversed** | $195,927 | −$243 | −$763 | 5.0× | $1,639 | −27.5% | 43.8% |

**Zero of twelve rotation rows clear the pass rule.** Every rotation beats its own naive version and
every rotation loses to just buying the fund — in every window, at every cost, at every lookback but
one.

## The three numbers that explain the whole table

**1. The ranking is worth +$413 a month and the universe costs −$520.** Forward top-2 minus reversed
top-2 is $413/month equivalent over 235 months: the ranking carries a real, large, correctly-signed
signal, and the reversal never out-earns the forward rule in any window at the twelve-month lookback.
But holding nine sleeves instead of one costs $520/month — the equal-weight basket ends $254,211 behind
index DCA, because 2007–2026 was the worst nineteen-year stretch in memory for everything that was not
American large-cap equity. The rotation spends its entire signal escaping a bad universe and still
lands $351/month short of doing nothing. The mechanism works. The admission fee is larger than the
wage.

**2. The comparator is fuzzier than the result.** Holding SPY forever beats the SPY→VOO switch by
$24/month, from a one-turnover splice between two funds tracking the same index at a 6.45 bps fee
difference. That noise is the same order of magnitude as the only positive result in this round, and
bigger than four of the twelve shortfall figures in round 13's grid. Any conclusion in this file that
is worth less than about $25 a month is a rounding artefact of which near-identical fund the tool
happened to name as the bar.

**3. Nine sleeves are 2.5 bets.** Average pairwise monthly correlation is +0.32, implying an effective
*n_eff* of **2.5 of 9** over the full window, and **+0.45 / 2.0** in the recent window — the sleeves
move together *more* in exactly the stretch where the rotation looks best. TLT/IEF correlate at +0.92,
SPY/IWM at +0.91. The 235 decisions are real; the 235 *independent* decisions are not, and the round-13
arithmetic is not discharged by a cross-section this concentrated. Round 13 asked for many independent
calls and this is what nine ETFs actually supply.

## The one window where it works, and what it costs to believe it

Since 2022 — 57 scored months — all three rotations clear both comparators:

| rule | $/mo vs index | $/mo vs EW | bar | hits | wedge |
|---|---|---|---|---|---|
| top-1 momentum | +$69 | +$142 | 51.4% | 64.9% | +14 pp |
| top-2 momentum | +$83 | +$156 | 46.8% | 57.9% | +11 pp |
| top-3 momentum | +$48 | +$121 | 60.2% | 61.4% | +1 pp |
| top-2 reversed | −$178 | −$105 | no bar | 47.4% | — |

*(That single window has since been priced at every size a real account could actually use, in
[the partial tilt](2026-09-06-partial-tilt.md): +$5 a month at 5% of the account and +$45 at 50%, on a
spread series whose persistence turns its 57 calendar months into 21.*

Three things have to be said about that before it is allowed to matter.

**It is not a cost story.** At 0.3 bps the same rows are +$71/+$85/+$50 and at 5 bps +$66/+$79/+$45.
Turnover is only 4–5× a year and total fees are 0.6% of a nineteen-year ending balance. A win that
ignores a 16-fold change in cost is not an arbitrage being squeezed; it is a *tilt* — the rotation
spent 2022–2026 out of long duration and in the sleeves that paid, which is a view, not an edge.

**It does not survive its own parameter neighbourhood.** Same nine sleeves, same window, twelve months
of lookback is the only setting that clears:

| lookback | top-1 | top-2 | top-3 | reversed top-2 |
|---|---|---|---|---|
| 3 months | −$161 | −$188 | −$122 | **+$30** |
| 6 months | +$21 | −$56 | −$36 | −$34 |
| **12 months** | **+$69** | **+$83** | **+$48** | −$178 |
| 18 months | +$21 | +$1 | −$11 | −$264 |

At three months the sign inverts: the forward rule loses two hundred dollars a month and *buying the
losers wins* +$30. A signal that flips sign one notch away from its preferred setting is not a signal
with a parameter sensitivity, it is a parameter with a signal attached. The 12-1 setting is the one
with a literature behind it, and it is the one the only positive cell sits on, which is exactly the
coincidence that round 3's rule r3 exists to make loud about.

**And it is the most recent window, chosen last.** Seen A (2007–2017, 127 months) loses by $132–247 a
month. Seen B (2018–2021, 48 months) loses by $144–206. Every window that ends before the current one
fails, and the one that succeeds is the one a person looking for a trade would notice first.

## What this does to the goal

This is the first mechanism in fifteen rounds to beat its own naive version in *every* window while
also being beaten by doing-nothing in *most* of them, and that combination is precisely the shape of a
`Redundant` verdict with a pulse: the ranking carries money (rule r13's own test, the reversal, passes
cleanly) and the money still does not reach the index.

So the goal stays open, and this round's contribution is a sharper list of what is not yet excluded.
The failure is no longer "signals cannot find anything". The failure is now specific and priced: **a
cross-sectional rule in a nine-sleeve universe pays $520/month for the universe and earns $413/month on
the ranking.** Three doors follow, and one of them is already closing:

- *A smaller universe.* Rank only among equity sleeves and the −$520 admission fee shrinks. This is the
  obvious next edit to this file and it is **worthless as written**, because the choice of which
  sleeves to drop can only be made by someone who has already seen which ones lost. Any universe
  selected after this table is priced at zero until it survives a window it has not been shown.
- *A partial tilt.* Never hold 1/9 of a gold ETF; hold the index fund and override a *fraction* of the
  account with the top-ranked sleeve. That is the shape this account would actually trade, and it is the
  same shape as the one mechanism in this repository that clears its bar (round 11's constant 1.25–1.5×
  exposure). It needs its own pre-registration, written before the tilt size is chosen, because
  otherwise it is the previous bullet in a different hat.
- *A forward record.* Every retrospective window in this archive has now been inspected by something.
  `tools/journalctl.py` still holds one entry and $0.00 paid in. A rotation that clears its bar in the
  recent window is exactly the kind of claim that is cheap to *make* and expensive to *believe*, and the
  only currency that settles that argument is entries it has not yet seen.

## Checks

`tests/test_cross_section.py`, 19 tests: the engine reproduces a hand-computed account to the cent and
a no-weights account reproduces the T-bill leg from the panel's cash factors alone; the initial purchase
costs exactly one leg and a monthly switcher costs more than eight of them; truncating the archive at
month 40 leaves every earlier weight identical, index for index; holding GLD before its listing raises;
a window whose warm-up it does not have raises; a schedule the wrong length raises rather than silently
shifting every decision into the month after the one that made it; `solve_blend` returns `None` — never
a clamped `0.0%` — when the target is beyond the pick *and* when the pick sits on the wrong side of its
own fallback; the blend is exactly linear in *p*, which is what makes the bar a solve rather than a
simulation; the forward ranking beats the reversed one by more than $100,000 of ending balance; no
rotation beats the fund on the full record; every rotation beats equal weight; and the 3-month lookback
must invert the sign rather than merely fade it. Full suite: **1318 passed, 233
subtests**. `journalctl verify`: chain intact (1 entry), comparator spec `100% SPY, fee 0.000945`
unchanged — nothing in this round touched the sealed ledger, and the forward record is still one entry
and $0.00 paid in.

Two known gaps, named rather than hid: the whole universe is survivorship-biased (these nine exist in
2026 because someone selected them for being liquid and famous, and every one of them survived), and
`tr_close` close-to-close at a flat per-leg toll is the cheapest execution in the world — no odd-hour
spread, no tax bill on a realised gain, and DBC and IEF do not trade at the SPY's spread.
