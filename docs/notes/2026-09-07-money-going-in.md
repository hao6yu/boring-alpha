# In a contribution plan the model never beats the index by $25 a month, at any capital tested

Measured 2026-09-07, round 60. Tool: [`contribution_race.py`](../../tools/contribution_race.py) (new). Tests: 11 in
[`test_contribution_race.py`](../../tests/test_contribution_race.py).

Round 58 priced the legs as a **withdrawal** plan: a lump sum, a level payout, a failure budget. That is the right
frame for a retirement and the wrong frame for this objective, which is "earn extra each month" — a person with a job,
a monthly contribution, and an account still growing. Same four legs, same panel, same monthly marks, nothing taken
out; the only cash flow is money going in. Three statistics, and the second is the only honest headline for a plan
like this: the model's advantage **as dollars a month**, and **P(terminal < total contributed)** — fifteen years of
saving ending smaller than the saving itself.

## $20,000 start, $1,000 a month, 10 years, $140,000 contributed

| leg | median end | × contributed | P(< contributed) | worst window | advantage over index |
|---|---:|---:|---:|---:|---:|
| **SPY hold** | **$302,594** | **2.161** | 0.0% | $225,348 | the bar |
| MA200 monthly | $242,302 | 1.731 | 0.0% | $197,885 | **−$502.43/mo** |
| mom_top1 monthly | $235,919 | 1.685 | 0.0% | $191,266 | −$555.62/mo |
| static 60/40 | $244,870 | 1.749 | 0.0% | $191,342 | −$481.04/mo |

**Every leg loses, and by a lot.** On the withdrawal metric the trend rule looked 36% better than the index; on the
contribution metric it is $502 a month worse. These are the same fact seen from opposite ends of the account: the rule
converts growth into sequence protection, and while contributions are still arriving a crash is a purchase rather than
a wound, so the protection is worth little and the 1.73pp of forgone growth is paid for in full.

## The advantage scales with the money at work, not with the cleverness applied to it

Advantage over the index, dollars a month, best of the three non-index legs:

| contributed | $0 start | $20k | $50k | $100k | $250k |
|---|---:|---:|---:|---:|---:|
| $500/mo | −$159 | −$311 | −$538 | −$884 | −$1,926 |
| $1,000/mo | −$318 | −$481 | −$686 | −$1,076 | −$2,109 |
| $2,000/mo | −$637 | −$761 | −$1,066 | −$1,373 | −$2,485 |

Fifteen cells, all negative, ranging from −$159 to −$2,485 — a factor of 16. The relationship is exactly linear in
capital — the test asserts `advantage(200k)/advantage(100k) == 2.000` and `advantage(250k)/advantage(50k) == 5.000` —
because with no withdrawal terminal wealth is linear in the balance. Two consequences for how the objective should be
phrased: **"a bot that earns me extra each month" has no answer without a capital figure attached**, and the
contribution stream itself is a large fixed annuity with a small investment return bolted on, so the model's share of
the outcome *shrinks* as the savings rate grows — 32.3% of terminal wealth with no contributions, 25.9% at $2,000/mo.

At the top of the range the model is never worth $25 a month:

    to clear $   25 a month: not anywhere in the range tested (up to $250,000)
    to clear $   50 a month: not anywhere in the range tested (up to $250,000)

## The insurance number, which is the one thing the model does win here

The panel is the flattering-looking sample, so the long record answers it. $0 start, $1,000/mo, 10 years, 1993→2026:

| leg | median end | × contributed | **P(< contributed)** | advantage over index |
|---|---:|---:|---:|---:|
| SPY hold | $201,290 | 1.677 | **4.2%** | the bar |
| MA200 monthly | $194,251 | 1.619 | **0.0%** | −$58.66/mo |
| static 60/40 | $165,887 | 1.382 | 3.2% | −$295.03/mo |

In **4.2% of 10-year windows on the long record, a contributor to plain equity finished with less than they put in**.
The trend rule has no such window — not one since 1993 — and it costs $58.66 a month on the median to buy that, not
the $502 the panel implies. The panel's own `P(< contributed)` is 0.0% for every leg, including the index, because
2006-onward contains no window where a contributor lost; that is a property of the sample, and the long record is
where the risk actually lives.

## The era split, again, in the frame the objective describes

Advantage over the index in $/mo, $1,000/mo contributed, long record:

| leg | 1993-2004 | 2005-2015 | 2016-now |
|---|---:|---:|---:|
| MA200 monthly (5y plan) | **+$82** | −$55 | **−$199** |
| MA200 monthly (10y plan) | **+$282** | −$299 | untested (n=9) |
| static 60/40 (5y plan) | −$35 | −$141 | −$162 |

Positive only in the oldest era and negative in both later ones, at either plan length, at 5 years where the newest
era can be scored at all. This is the third independent metric on which the trend rule's value has flipped sign by
era: growth (r55), failure rate at a fixed payout (r59), and now dollars in a contribution plan.

## Checks

11 tests, 9.7 s, offline: a flat series must return exactly `capital + contribution × months` and a multiple of 1.000;
a series falling every month must give `P(under) = 1.0`, not a near miss; an empty sample must return `None`, never
0.0 (round 58's rule that untested is not safe); the advantage must be linear in capital to three decimals; the
model's share of the outcome must shrink as contributions grow; every alternative leg must end smaller than the index
on the panel; the index must have a long-record `P(< contributed)` above 2% and the trend rule exactly 0%; the oldest
era must favour the rule at both plan lengths while the two later eras disfavour it; and both sample boundaries must
be the ones claimed, since half this note's argument is that the two boundaries disagree. Full suite
**1739 passed** (collected first: 1728 + 11). `journalctl verify`: chain intact, comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
