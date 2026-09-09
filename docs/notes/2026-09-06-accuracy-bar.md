# Round 13 — the bar each signal needs, priced on the trades it actually makes (`tools/accuracy_bar.py`)

Round 3 is the note that closed the signal hunt: *"break-even sits at 56% … no rule that exists here
clears its own window's bar,"* fifteen of sixteen rule×window cells short by 0.5 to 5.1 points, and every
later round took it as settled.
Nine rounds of leverage, financing and cadence work all sit on top of it, and the goal is still open,
so this round audits the instrument rather than auditioning one more signal on it — the same discipline
r5 and r6 demand of a comparator: **test the object that everything else is measured against.**

Two things were wrong in it. They pull in opposite directions — one made the bar too easy for a slow
rule, the other scored the rule too harshly — and they nearly cancel on the headline, which is precisely
why round 3's verdict survived and its number did not.

1. **Its shadow timer redraws its mind every week.** `required_accuracy.run` computes
   `chosen = better if rng.random() < accuracy else not better` *per bar*, unconditionally. At 50% that
   timer flips state roughly every other week — 844 switches over 1,691 bars, which is a coin's
   turnover, not a trend filter's. So the quoted "56–58%" is the bar for the single most twitchy timer
   arithmetic permits, and the 200-session trend filter — 107 runs, two sessions long when wrong and
   forty-six when right — was being charged that bar for a book it would never hold.
2. **The fund's expense ratio sat on the cash leg.** `weekly_bars` applies the sleeve's ratio to the
   leg you hold when you are *out*. Being flat is a decision, and round 3 priced it as if the fund's
   fee were paid by the T-bills that replaced the fund.

Run: `.venv/bin/python tools/accuracy_bar.py --reps 300` — three sleeves × four windows × twelve rows
in about four minutes. `--r3-expense` rebuilds the same grid with the fee on the cash leg, which is how
the attribution below is separated rather than argued.

## What the tool does instead

A two-state rule over a deposit book is a sequence of runs, and the book is *affine in each run*: entry
wealth multiplied by that run's fund-or-cash factor, plus the run's deposits compounded at the same
rate. So the whole grid can be priced by composing run affines instead of walking bars — which buys a
real identity check rather than a faster simulator: at accuracy 1.0 and the rule's own states, the
shadow must reproduce the bar-by-bar simulator. It does, to **$0.000000** on every cell the test walks
(`test_the_affine_shadow_reproduces_the_bar_by_bar_rule`). That was not free to earn: the first version
was $2,160 short on the candidate's row because `runs_of` restarts its index on whatever slice it is
handed, and a run list priced five bars left of where it lives is a wrong number that looks exactly
like a right one. The test now forces the error and asserts it is material — $67 on a one-run row,
**$1,626** on a twelve-run row, both silent.

Every rule is therefore given two numbers against **its own** calendar, both read off the same monotone
skill surface:

- **its bar** — the accuracy an i.i.d. timer on this rule's own run structure needs to match plain DCA;
- **its skill** — the accuracy such a timer would need to end where this rule actually ended.

The second is the inversion, not the count, and the inversion is the point: a percentage of decisions
cannot express *which* decisions were right. `wedge` is the difference, in points, and on one
calendar — the 126-session trend, run forward and then reversed — it is **+30 pp** one way and **−35 pp**
the other, while both rows lose money.

Controls: `always long` is the comparator and must print zero (it does, in all twelve cells);
`always flat` must need perfection (it does, bar 100.0%); the coin is drawn as **25 independent books**
— a single coin book came in at 41.7% on one seed against a true mean of 52.0%, and a control that
swings on its seed is not a control; and the bars are computed exactly (enumerated, no Monte Carlo)
below 15 runs, which is why the short-window rows are trustworthy rather than merely quiet.

The repo's own candidate is on the grid too, and its row is the most embarrassing on it: **1 run, 100%
long, bar 100.0%, gap +0.0 pp, +$0/mo, in all twelve cells.** With `min_weight = 0.30` the gate's weight
is never zero, so the two-state frame round 3 built — and the frame this tool inherits from it — has no
symbol for a rule that is only ever 30–130% in. Round 3 never scored the candidate; it scored an
always-long book wearing the candidate's name.

## Result 1 — the toll is not the wall, and the wall is not where round 3 said it was

SPY, full window, one-way cost swept across round 3's own three prices:

| one-way cost | coin's bar | 200-trend's bar | trend's skill | trend's $/mo |
|---|---|---|---|---|
| 0.3 bps | 56.76% | 70.38% | 59.6% | −$446 |
| 1.0 bps | 57.36% | 70.66% | 59.6% | −$454 |
| 2.0 bps | 58.24% | 71.00% | 59.5% | −$465 |

Six of round 3's fifty-eight points are structure; **1.5 points are the toll** (both at 300 draws). For the slow rule the
toll is worth half a point of bar and nineteen dollars a month — a rounding error on a book that is
eleven points short. Cost is not the wall, and the wall is not 58% either: it is 71.0% for a trend filter,
74.3% for a dual MA, 79.2% for 52-week momentum, and **69–90% for every real rule on this grid** (median
bar 69.4–90.0% by rule across all four windows). Slow rules are held to a *higher* standard, because
their bets are large and unhedgeable: 107 chances to be right about a two-year move, not 1,691 chances
to be right about a week.

## Result 2 — the count statistic was measuring something else

Round 3 scored the 200-session trend 0.5 points short of its bar; this grid says 11.5, and the same rows
carry a 35-point wedge between what the rule was right about and what it earned. The two numbers are not
the same statistic, and only one of them is attached to money.

| SPY, full window, 2 bps | runs | hits | skill | own bar | gap | wedge | $/mo |
|---|---|---|---|---|---|---|---|
| coin flip ×25 | 844 | 50.5% | 49.4% | 58.2% | −8.8 pp | −1 pp | −$823 |
| 200-session trend | 107 | 24.3% | 59.5% | 71.0% | −11.5 pp | +35 pp | −$465 |
| dual MA 50/200 | 31 | 48.4% | 67.9% | 74.3% | −6.4 pp | +20 pp | −$225 |
| 126-session trend | 157 | 27.4% | 57.7% | 68.3% | −10.5 pp | +30 pp | −$502 |
| reversed 126-trend | 157 | 72.6% | 37.8% | 68.3% | −30.5 pp | −35 pp | −$929 |

Two rows deserve to be read together, because they are one book seen twice. The 126-session trend
filter is right on **27.4%** of its runs, shows 57.7 points of implied skill, and costs $502 a month. Its
exact mirror image — same bars, same switch dates, every position reversed — is right on **72.6%** of
runs, comfortably above the 58% round 3 said was sufficient, and costs $929 a month. Same calendar. Count
moves **+45.2 points**; money moves −$427 the wrong way; wedge, the gap between implied skill and counted
hits, moves from +30 to −35. A statistic that a sign flip can move 45 points while leaving the dollars'
sign alone is a property of the scoreboard rather than of the book.

Why the count and the money part company is visible in the run lengths: the 200-session filter's 81 losing
runs are a median of two sessions long — a whipsaw, costing one switch and nothing else — while its 26
winning runs are 46 sessions long and sit on 78% of the calendar. Being wrong cheaply and right expensively
reads as failure to a percentage and as near-indifference to a balance sheet, and there is no version of
"how often was it right" that can tell those two books apart. The 13-week momentum rule, right on 33.1% of
runs and short by 11.7 points, and the dual MA, right on 48.4% and short by 6.4, are further along the same
curve and lose $540 and $225 a month respectively.

## Result 3 — nothing clears, and the two readings never contradict each other

**0 of 96** real-rule rule-windows clear their own bar — three sleeves (SPY, QQQ, VTI) × four windows ×
eight rules that are not controls, at the dearest cost on the menu. On the **89** rows that have a bar at
all — the 96 less the seven that print `no bar on earth`, meaning no accuracy at all lifts that rule's own
calendar above DCA in that window — the sign of the gap and the sign of the money agree without exception,
and all seven of the unreachable rows are losing money anyway. Twelve of the 89 are the candidate's gate,
whose row is exactly the comparator's; strip the rows where a rule made no decision and the best number
anywhere on the grid is **−$7 a month** (52-week momentum, VTI, 2022→2026: two runs, one of them right, and the book still
ended under DCA).

Per rule, over every cell where it scored:

| rule | cells | median hits | median skill | median bar | median gap | best $/mo |
|---|---|---|---|---|---|---|
| 52-week momentum | 9 | 36.7% | 72.4% | 90.0% | −19.4 pp | $0 |
| 200-session trend | 11 | 24.3% | 61.5% | 83.1% | −21.2 pp | −$95 |
| dual MA 50/200 | 9 | 40.0% | 62.9% | 80.3% | −19.7 pp | −$72 |
| 126-session trend | 12 | 28.7% | 61.1% | 79.2% | −22.1 pp | −$85 |
| 13-week momentum | 12 | 36.8% | 56.9% | 79.6% | −21.5 pp | −$72 |
| 4-week momentum | 12 | 37.8% | 53.8% | 69.4% | −17.1 pp | −$107 |
| 50-session trend | 12 | 31.4% | 52.3% | 70.5% | −24.4 pp | −$105 |

Every one of the seven sits **17 to 24 points** short of its own bar on the median across its cells —
one to five points was round 3's verdict, and this grid is four to twenty times that gap. The
grid is reproduced by `test_no_real_rule_clears_its_own_bar_anywhere_on_the_menu`, so a future edit that
quietly lets a rule through has to break that first.

## Attribution — what of round 3's 58% survives

Run with `--r3-expense` and the same grid, at the same 300 draws:

| | corrected | round 3's placement | difference |
|---|---|---|---|
| coin's bar, SPY full | 58.24% | 58.39% | 0.15 pp was the misplaced fee |
| always flat, $/mo | −$1,051 | −$1,083 | $32/mo of "insurance premium" was the fee on the wrong leg |
| coin's bar, 0.3 → 2.0 bps | 56.76 → 58.24% | — | 1.5 pp of it was the toll |
| a coin's turnover → a trend filter's | 58.2% | 71.0% | **12.8 pp of it was the redraw** |

So round 3's number was not fake, it was the bar for a different rule: the fee misplaced cost it 0.15 of
a point, the toll it quoted honestly, and the redraw moved it by roughly twelve points on the only rule
the goal would plausibly use. The *conclusion* — nothing here beats DCA on its own decisions — was right
and is now harder to dislodge, because it survives with a bigger margin and on the right statistic. What
died is the reason given for it, and with it the hope that the gap was narrow enough to close by tuning
a signal by a point or two.

## What this does to the goal

It closes the cheap version of the remaining door and opens the expensive one. If the mechanism is a
directional call on the whole book at a monthly-or-slower cadence, the bar is 69–90% — far outside
anything measured here, where the best skill any real rule shows in any window is 72%. That is not "not
yet tried", it is arithmetic on the deposit frame. The same arithmetic does say the bar falls as a rule
makes more, smaller bets — 58.2% for a coin spread over 844 runs, 63.4% for 4-week momentum's 353, 71.0%
for a trend filter's 107, all on the same window and the same two bps — so the direction worth pushing in
is more independent decisions, not better ones. What that door demands in exchange is what this archive
cannot supply: the toll is charged per switch ($87 a month at 2 bps for a coin against $19 for the trend
filter, affordable), but the *calls* have to be independent, and a trend or momentum feature produced 2
to 353 per window, not 1,691 — a rule can only be as many bets as it is allowed to make.

**That door was priced one round later, and it closes.** [The cadence grid](2026-09-06-cadence-bar.md)
ran the same rules on a one-session clock, where they do get every decision the signal can offer. Every
bar fell, by 0.2 to 3.7 points, exactly as the arithmetic above predicted. It bought nothing: across 33
comparable rows, 22 lost more money than the same rule on a weekly clock, 10 lost less, and the median
change was −$23 a month against a mean of −$68, because a faster clock turns a two-year bet into a
two-week bet and grades the same opinion on the shorter one.

**The escape both rounds named — many independent bets — has now been tested, and it is priced too.**
[The cross-sectional round](2026-09-06-cross-section.md) stopped asking one asset the same question and
started comparing nine sleeves instead, which is where a rule could finally earn the independence this
table says is required. It earned it and still failed: the ranking beat its own reversal by $413 a month,
which is the real signal, and holding nine sleeves rather than one cost $520 a month, which is the price
of the shelf it sat on. Nine names turned out to be 2.5 bets at +0.32 average pairwise correlation.

Which leaves the two things rounds 11 and 12 already pointed at and this round cannot touch: the
*sizing* of exposure rather than its direction (constant leverage clears the menu at 1.25x, and the cost
of that is drawdown), and the *withdrawal* frame, where a month is a month and a shallower worst month
is worth something even at flat dollars. Both are measured. Neither is a bot. The bot still needs an
edge that does not exist in this archive's prices, and the number it would need is now pinned per rule
instead of globally.

## Checks

`tests/test_accuracy_bar.py`, 24 tests, ~4.5 minutes: the affine shadow against the bar-by-bar rule to
six decimal places; the comparator landing exactly on its own bar at 100.0%; the bar refusing to exist
on calendars where it cannot (`no bar`, and those rows losing money anyway); the toll moving the bar the
right way; the reversed rule scoring its own complement; the fee charged to the leg that owes it and
never to the flat leg; four rules handed only a prefix of the closes and a fifth test that proves the
prefix is a real prefix and not a promise; the coin scoring 50% and reproducing round 3's headline at a
coin's turnover; and the grid's own conclusion pinned. Full suite: **1294 passed, 233 subtests**.
`journalctl verify`: chain intact, comparator spec `100% SPY, fee 0.000945` unchanged — nothing in this
round touched the sealed ledger.
