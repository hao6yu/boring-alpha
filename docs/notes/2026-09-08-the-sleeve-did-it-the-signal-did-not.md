# The sleeve did it. The signal did not.

Goal round 3 (of 96), `goal-91eb485f…`. BA-005 failed holding 100% of the account in one asset and wrote a bar: a Coinbase candidate must hold
the volatile asset at a *fractional* weight and be graded against a blend. This round priced that — spec first
([BA-006.md](../strategies/BA-006.md), locked before any sleeve number existed), tool second, numbers last — and for the first time in 113
rounds this repository has something that beats the index on the promise rather than merely out-earning it and failing.

## What the archive's own machinery says

`tools/ba006.py`, monthly-rebalanced blends, the same 200-day signal as BA-005, the rest in VOO (P0), `monthly_income_race.safe_amount` for
every bill, 122 months, 63 overlapping 5-year windows — **two non-overlapping looks at one decade**, printed above the table:

| weight | affordable bill | vs P0 | P(erase) at P0's bill | max DD | seatbelt (signal − plain hold) | gates |
| --- | --- | --- | --- | --- | --- | --- |
| P0, 100% VOO | $831/mo | — | 0% | 23.9% | — | the bar |
| 5% | $919/mo | +10.7% | 0% | 24.1% | **−$23/mo** | fails 4 |
| 10% | $980/mo | +17.9% | 0% | 24.3% | **−$0/mo** | fails 4 |
| **20%** | **$1,045/mo** | **+25.8%** | **0%** | **24.8%** | **+$17/mo** | **clears 1-4** |

**Exit code 3. NO VERDICT.** Not because the numbers are bad — because the spec's fifth condition is a dated Coinbase fee record and there
isn't one. A fee grid sits under the table showing the ranking survives 240 bps per switch ($1,045 → $963, still +15.9% over P0), so the fee
is not the thing being hidden behind. The PASS is withheld anyway, because a pass here is a *trade licence* and rule 103 says this lab does not
issue one against a cost it cannot see. That is the first time in this project the missing fee has been the only thing between a candidate and
a licence, and it is working exactly as intended: the block is actionable, not fatal.

## Why the headline is not "a model beat the index"

Condition 4 — the seatbelt test, put in the spec precisely because it is awkward — is the story:

- at 5% weight, the signal blend supports a bill **$23/mo smaller** than simply buying and holding the same 5% of coin;
- at 10%, the difference is **zero**;
- at 20%, the signal beats plain holding by **$17/mo on an $831 base**, which a 122-month record of one asset's hundredfold decade cannot
  distinguish from nothing.

So the honest reading of the table is *a slice of bitcoin raises the affordable bill*, not *a model beat the index*. The sleeve does it. The
200-day signal does roughly nothing to it — the third independent confirmation of the archive's standing conclusion, now in a new asset class
and at a new weight.

And one number that is worth understanding rather than admiring: 20% of a sleeve whose own max drawdown is 56.5% adds only **0.9 points** to
VOO's 23.9%. That is not the timing protecting the account — that is the two assets' worst months being different months. The risk story here
is diversification, which belongs to holding *anything* uncorrelated, not to the rule.

## The part I want to be careful about out loud

One sample of one decade, in which the asset went from a few hundred dollars to ~$78,000. Two non-overlapping windows. The bill is the
*index's* bill, and the sleeve's expected return is what makes it affordable — change the decade and both go. P(erase) 0% is a statement about
63 overlapping windows, not a risk declaration. If this goes into a forward book, it goes in as a *prediction being tested*, and the first
sealed month that disagrees with the backtest is worth more than the whole table.

Which is why BA-006 now says, before any forward evidence exists: **if condition 5 is ever met, the fifth book carries both legs** — the
signal sleeve and the plain-hold sleeve at the same weight, sealed separately. History cannot separate them, the archive's whole history says
doing less wins, and choosing the more complicated of two indistinguishable designs on evidence that cannot tell them apart is the exact error
this repository has been built to avoid. Let the seals choose.

## State of the objective

Steps 1-4 are complete for BA-005 (failure, archived) and BA-006 is locked, priced, and **open on one input**. The fee record went from
"required, immaterial-looking" (round 110) to "the licence" (this round) — the ask is unchanged and now decisive: Coinbase app → Advanced
Trade → Fees, then

```
.venv/bin/python tools/venue_fees.py ingest --product advanced-trade --taker-bps <seen> --maker-bps <seen> \
    --tier "<tier>" --as-of 2026-09-08 --note "seen under Fees in the app"
```

and `tools/ba006.py` will render whatever it has to render, including the failure. Nothing is complete while the evidence is historical: the
forward loop is untouched, first real seal 2026-09-30, 23 more entries before any claim of skill, and a 20% sleeve idea that has never met a
sealed month is not a result — it's a hypothesis with paperwork.

## Checks

**2415 passed, 239 subtests** (2400 + 15 new; collected count printed before the run). Rules: **113**. P0 still 100% VOO, priced before
evidence; the gate is still BA-005's 1.25× and BA-006 imports it rather than copying it.

*Goal round 3. The first candidate that beats the index on the income promise is a sized position in a volatile asset, and the model attached
to it earned −$23, $0, and +$17 a month across the ladder. The sleeve is the finding. The signal is not.*
