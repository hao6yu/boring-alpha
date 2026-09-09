# The veto the news would have paid for

Measured 2026-09-07, round 72. New tool: [`news_veto.py`](../../tools/news_veto.py). Tests: 18 in
[`test_news_veto.py`](../../tests/test_news_veto.py).

The objective has two halves and only one has been tested. The price half has been measured eleven ways; the "analyse
trending and global news" half produced a corpus in round 18 and one verdict: page views do not forecast the index, six
cells from −$87 to −$479 a month, every one reproduced by a basket of articles about volcanoes and photosynthesis.

That closes attention *as a signal*. It does not test the weaker claim, which is the one people actually mean: not "news
forecasts the market" but **"news tells me when my rule is about to be wrong."** A veto does not need to forecast
returns — it needs to fire before the rule's bad months and not too often otherwise. That is a different test, priced here
with the same corpus, the same thresholds, the same control basket and the same $25/mo noise floor, with the shift and
both directions tested rather than assumed.

Three hypotheses, written before the arithmetic: **H1 warning** (high attention ⇒ shelter, the crowd sees something),
**H2 collapse** (attention *abandoning* the subject ⇒ shelter, the opposite reading), **H3 timing** (attention clusters
where the rule turns, so at minimum it could save the switching costs).

| reading | θ | fires | equity return in the months it would have vetoed | switches | $/mo, paired | t | control $/mo | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| warning | 0.5 | 17 | **+2.35%** | 29 | **−430.02** | −2.15 | −204.69 | the veto would have cost money |
| warning | 1.0 | 9 | +4.21% | 27 | −399.51 | −2.16 | −84.99 | n=9, too few to grade |
| warning | 1.5 | 1 | +12.69% | 19 | −115.50 | −0.83 | −59.82 | n=1, too few to grade |
| collapse | 0.5 | 35 | +2.01% | 32 | **−498.25** | −2.92 | −427.09 | REFUTED by the control basket |
| collapse | 1.0 | 17 | +1.18% | 32 | −61.06 | −0.72 | −41.28 | REFUTED by the control basket |
| collapse | 1.5 | 3 | +2.28% | 25 | −7.53 | −0.18 | +36.17 | n=3, too few to grade |

**Every cell is negative.** The veto costs the plan money in both readings and at every threshold, and the three cells with
enough firings to grade are two refuted by a volcano basket and one that simply lost money. The mechanism is visible in the
third column: the months an attention spike would have stepped aside from **averaged +2.35% to +12.69% in equities**.
Attention peaks with rallies, not with falls — so acting on it means selling into strength, which is how round 18's null
turns into a negative here rather than a zero. H3 goes the same way: at the rule's 19 turns on this record the mean |z| was
**0.70** against **0.63** for all months, so there is not even a switch-cost saving to argue about. The news half of the
objective, measured on the only point-in-time input a retail account can obtain and never revise, supports nothing.

## What had to be fixed in my own apparatus first

**The valuation had the wrong sign, twice.** The first draft computed the veto's worth as the average return of the months
it avoided, times the capital, minus costs — which credits a veto with the profit of the exposure it removed, and then
adds insult by ignoring the fee of the shelter it parked in. Both plans now go through the same engine over the same dates
(equity fee, shelter expense ratio, every switch charge) and the answer is the mean of a 128-month paired difference.
Paired is also the *right* design here: 128 months is a sample; the seven ten-year windows the record contains are not.

**A one-month cell was about to be published as a finding.** Before the sample clause existed, the θ=1.5 warning cell —
one month, a single +12.69% April — graded as `CANDIDATE worth $1,057/mo`. That is precisely the artefact round 18's
control clause was written to catch, and the control clause could not catch it because it compares magnitudes and a
one-month magnitude is enormous. `grade()` now reads `n` before it reads anything else, at `MIN_MONTHS = 12`, and the
message says what is wrong with the cell rather than hiding it.

**The corpus boundary is hard, and it was verified rather than remembered.** [Wikimedia's Analytics API serves page views
from 2015-07-01 and nothing earlier
](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html); [the tooling FAQ says the
same](https://pageviews.wmcloud.org/pageviews/faq/). A legacy endpoint covers 2008-2016 but counts views under a different
definition, so splicing it would revise the series in place — the exact property round 18's guard was built to protect.
Consequence, stated plainly: **the news half of the objective cannot be tested at the horizon the plan is denominated
in**, on data that satisfies the repository's own rules. Usable z-scores begin 2016-01, a decision needs the month before,
so 128 months and 7 windows. That is why the plan-level figures are printed with `UNRESOLVABLE` above them — the un-vetoed
plan's "safe $1,086/mo" on 2016-2026 is quoted and disowned in the same breath.

If the news half is ever to be taken seriously, the path is specific rather than aspirational: seal the 2008-2016 legacy
endpoint as a *separate* series with its own provenance, compute a bridge ratio on the 2015-07..2016-07 overlap where both
endpoints exist, and re-run this file with a level-shift control beside every cell. It would take a fetching round and a
guard. Without it, the honest sentence is the one above.

## Checks

18 tests, 11.7 s, offline. The z-scores are taken from `attention_bar.monthly` by identity, not recomputed; the veto is
forbidden from raising exposure and from firing in the month its reading is taken (a same-month veto is lookahead); the
one-month pulse must not ratchet; the paired dollar sign is pinned in both directions plus the identical-plan case; the
classifier is tested at n=11, at control-equals-half, at the noise floor, and on the negative-but-large cell that must
say "cost money"; and the record's thinness is asserted from the corpus' own first date. Whole suite **1911 passed**
(collected first: 1893 + 18); ledger chain intact.
