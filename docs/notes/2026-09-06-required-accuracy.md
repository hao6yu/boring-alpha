# Required accuracy — what a weekly timing signal has to be right about

Date: 2026-09-06 · Round 3 of the trading-model goal · tool: `tools/required_accuracy.py`
Status: **measurement, not proposal.** Nothing here is a candidate strategy.

## Why this note exists

The goal on the table is a model that earns extra money each month and beats VOO/QQQ,
probably by short-term trading informed by trends and global news. Rounds 1 and 2 killed
specific mechanisms. Guessing at the next one — including a news-driven one — would repeat
the mistake already made twice in this repo: arguing about a signal before asking what
accuracy it would need. So this round measures the bar instead of auditioning another
signal against it.

The question is narrow and answerable from the archive we have:

> On this data, with this deposit schedule and real costs, how often must a weekly
> market/flat call be correct before it beats plain DCA into the same fund?

If the answer is a number no rule here achieves, then the search for a short-term signal
is not "unfinished", it is aimed at the wrong quantity — and a news feature has to clear
the same number, because news only changes what a timer predicts, not what it pays to be wrong.

## Method

- Universe: the archive's SPY series (the VOO proxy; see the caveat below). Daily closes
  and `cash_daily.csv`, so "flat" earns the actual T-bill path, not zero.
- Weekly grid: five sessions per bar, 1,691 bars over 1993→2026. Each bar is
  `(equity_return, cash_return, deposit)`. $5,000 opening, $500/month, deposited at the
  week's start — same convention as the funded simulator, so the numbers are comparable
  to the vol-target and constant-leverage results.
- Costs: charged on switches, both legs (out and back in), at 0.3 / 1.0 / 2.0 bps.
  The fund's 9.45 bps expense ratio is carried in the cash leg. Reported bar is the
  **dearest** cost; a rule that only works frictionless is not a rule.
- Simulator: at accuracy *a* the call names the leg it thinks wins; with probability *a*
  it names the true winner. 300 seeds averaged. Position is long or flat, never short.
- Comparator: plain DCA into the same fund, same deposits, one entry cost. Everything is
  reported as terminal dollars relative to that comparator, which is the P0 dominance test.
- Achieved accuracy is measured on the same grid and definition for four rules that
  actually exist here and need no new data: 200- and 50-session trend, 4- and 13-week
  momentum. Long when the rule says long; accuracy = share of held weeks where the fund
  beat cash. Standard error is the binomial one on the weeks shown.

## Result 1 — the bar is roughly 56–58% a week, and the slope is brutal

Terminal dollars vs plain DCA, at 2.0 bps/leg, full window:

| weekly accuracy | 50% | 52% | 54% | 56% | 58% | 60% | 66% | 75% |
|---|---|---|---|---|---|---|---|---|
| vs DCA | −68% | −54% | −30% | **+7%** | +66% | +166% | +1042% | +11537% |

Break-even sits at **56%** over the full window and **58%** in every sub-window, and it
barely moves with cost between 0.3 and 2 bps. Cost is not the wall. The wall is the slope:

- **Two points of accuracy is the difference between losing a third of your money to DCA
  and roughly matching it.** From 54% to 56% is +38 points of terminal wealth.
- A coin-flip timer is not neutral. It is **68% behind** DCA over 33 years, because half
  its flips pay two legs and none of them carry information.
- The curve is convex, so errors compound asymmetrically: the reward for being good is
  enormous and the penalty for being mediocre is enormous, and there is almost no plateau
  in between to land on by accident.

Sub-window bars: seen A (2007-06→2017-12) 58%, seen B (2018→2021) 58%, recent
(2022→2026) 58%. Base rates — the accuracy you get for free by simply never selling —
are 58.3%, 57.8%, 61.6%, 57.3%. **In three of four windows the bar is above the free
accuracy of just holding.** The timer must beat "do nothing" on the same axis that doing
nothing already exploits.

## Result 2 — no rule that exists here clears its own window's bar

| rule | full | seen A | seen B | recent |
|---|---|---|---|---|
| 200-session trend | 55.5% (−0.5 pp, −0.42 SE) | 55.2% (−2.8, −1.70) | 57.2% (−0.8, −0.32) | 56.7% (−1.3, −0.37) |
| 50-session trend | 53.9% (−2.1, −1.73) | 53.2% (−4.8, −2.99) | 54.4% (−3.6, −1.51) | 55.8% (−2.2, −0.66) |
| 4-week momentum | 53.5% (−2.5, −2.09) | 54.1% (−3.9, −2.44) | 52.9% (−5.1, −2.12) | 57.0% (−1.0, −0.32) |
| 13-week momentum | 54.4% (−1.6, −1.36) | 54.8% (−3.2, −1.98) | 56.9% (−1.1, −0.47) | **58.4% (+0.4, +0.11)** |

Fifteen of sixteen rule×window cells fall short of the bar. The one cell above it —
13-week momentum, recent window, +0.4 pp — is **+0.11 standard errors**, which is a coin
toss recorded slightly favourably. Worse, that same rule is 3.2 pp short in seen A and
1.6 pp short over the full window: its sign flips by window, which is the signature of a
number that was never there.

**Verdict: `Redundant` for weekly market timing on trend/momentum, on the P0 rule.** Not
because it loses badly — it loses by a few tenths of a standard error — but because the
cost of being wrong is so much larger than the gap between the best available rule and
break-even that no honest plan closes it.

## Result 3 — why the slope is so steep: the growth is not spread out

| window | best 1% of weeks carry | best 5% of weeks carry |
|---|---|---|
| full 1993→2026 | 38% | 121% |
| seen A | 42% | 132% |
| seen B | 25% | 96% |
| recent | 22% (2 weeks) | 106% |

Over 33 years, **17 weeks hold 38% of all the log growth**, and the best 85 weeks hold
**more than all of it** — the remaining 95% of weeks are net negative. Same shape in every
sub-window, and it is tightening: the last four years put 22% of everything into two weeks.

This is the mechanism the accuracy table is measuring. A timer is not graded on the
average week; it is graded on whether it happens to be holding the fund during a handful
of specific weeks whose dates it cannot know in advance. Being right about the average
week and blind to those weeks is not slightly worse than holding — it is structurally
worse, which is why 54% accuracy is a catastrophe and 60% is life-changing, with almost
nothing in between.

## What this says about the news idea specifically

This is the round's actual payoff, because it applies to a signal we do not have yet.

News cannot change the bar. It can only change the accuracy, and it must produce the same
**2–4 points of accuracy above the base rate, every week, for years** — from a feature
whose entire realistic content on an index is already priced within minutes. It must also
be right disproportionately often in the *big* weeks, since those carry the growth, and
big weeks are exactly where headline-driven signals are least distinguishable from noise.

And the arithmetic is one-sided in the wrong direction. From the table: a news feature
that is a *little* better than a coin flip is worth roughly **−40% to −30%** versus doing
nothing, while one that is spectacularly good is worth multiples. An idea whose upside is
"if it's great" and whose expected value is "if it's ordinary, it is worse than the thing
you already rejected for being too slow" is not a trade, it is a subscription fee.

So the honest recommendation stands and is now quantitative: **do not buy a news history
archive to hunt for index-level timing alpha.** If news data gets bought, its defensible
role is the one the dominance rule permits — a *risk-off gate* on position size, the same
job the 200-day gate does in the paper bot, evaluated on forward months, not as a source
of weekly direction.

## The bug this round found in its own tool, recorded

The first version of this tool reported a flat, non-monotone table — every accuracy from
50% to 75% lost about 62%, which looked like a striking finding and was arithmetic
nonsense. The signalled leg had been written as a nudge to last week's position
(`want = held if chosen else not held`) instead of the position itself, so the call and
the holding were statistically independent and "accuracy" only controlled how often the
book flipped. The output never said *bug*; it said *timing is hopeless*. It was caught
only because a correct simulator must be monotone in accuracy and the table was not.

Pinned now by `tests/test_required_accuracy.py` (8 tests), whose `test_better_calls_are_
worth_more` fails on the old line and whose `test_perfect_accuracy_never_holds_the_losing_
leg` pins the semantics against a reference implementation. The lesson generalises to
every simulator in this repo: **a monotonicity invariant is worth more than a plausible
number**, and the ones we cannot check we should not quote.

## Caveats, stated plainly

- This measures **weekly** calls. The user's "short term" could mean daily or intraday,
  and no intraday data exists in this repo. The direction of the correction is not in
  doubt, though: more switches, same base rate, higher cost per unit of information.
  Shorter horizons raise the bar, they do not lower it.
- The Monte-Carlo assumes errors are independent across weeks. Real trend and news
  signals fail in clusters, in exactly the regime breaks that matter, so the required
  accuracy computed here is a **floor**, not a realistic estimate.
- Monthly deposits mean timing also affects how much of the money is exposed when the
  big weeks arrive; that is in the simulation, and it is one more reason a timer's
  variance, not just its mean, is what an account actually feels.
- "Beat QQQ" remains unmeasurable here — no QQQ in the archive. SPY is the VOO proxy and
  that is the honest limit of the claim.
- The synthetic simulator and the real rules are compared on identical grids, but a
  2-percentage-point bar gap between windows is inside the sampling error of the bar
  itself. The conclusion is drawn from every cell pointing the same way, not one number.

## What this does *not* say

It does not say trading is impossible, and it does not rehabilitate BA-004, which is
dead on its own grounds (see the retention audit). It says a specific thing: **on this
asset and this data, the accuracy required to beat DCA by timing weeks exceeds what the
available signals achieve, by more than the noise floor, in every window tested.**

Everything in this repo that has actually beaten DCA did it by **borrowing**, not by
predicting — constant leverage with no signal at all beat DCA in all four windows at
1.25–3×, which is why the paper bot's candidate wants 128% exposure. That is a real,
repeatable mechanism and it is also not free: it converts a market return into a levered
one and hands the difference to the margin lender. If the goal is extra money each month,
the live question is not "which signal predicts next week" — it is whether the one
demonstrated edge (a modest, disciplined, capped use of borrowed money against a
high-quality sleeve) survives forward months at the 1.5× cap already recorded for BA-006.

That is the question the forward journal is built to answer, and it will be answered on
forward months, not by another backtest.

## Reproduce

```
.venv/bin/python tools/required_accuracy.py --reps 300
.venv/bin/python tools/required_accuracy.py --cost-bps 0.3 --cost-bps 2.0
.venv/bin/python -m pytest tests/test_required_accuracy.py -q
```
