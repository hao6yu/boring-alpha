# BA-001 development review

Date: 2026-09-04
Sweep: `4b9d1479f811d108`
Period: development, 2007-01-01 to 2017-12-31 (the full registered window)
Data: `yahoo-adjusted-v1+dgs3mo-v1`, sha256 `06ce65f1…`, loaded through 2017-12-29
Code: sha256 `4dd1eb16…`, commit `a49b80f`. The provenance record flags a dirty
working tree. The tracked tree is unchanged and the fingerprint matches a
recomputation over it, so the difference was not in the code; the run
configuration was untracked and is committed alongside this review.
Status: **written before the validation period was run.**

This is BA-001's first evaluation on historical market data. It is one period of
two; the charter's verdict needs both, and none is offered here.

---

## Result

All five advancement criteria passed.

| Metric | Strategy | Static | Exposure-matched | Cash |
|---|---:|---:|---:|---:|
| CAGR | 5.18% | 5.70% | 4.06% | 0.69% |
| Volatility | 7.55% | 12.72% | 8.19% | 0.08% |
| Max drawdown | −9.97% | −35.42% | −24.05% | 0% |
| Sharpe vs cash | 0.616 | 0.445 | 0.443 | — |
| Worst month | −7.15% | −15.99% | −10.36% | 0% |
| Avg gross exposure | 65% | 99% | 64% | 0% |
| One-way turnover | 0.74×/yr | 0.21×/yr | 0.14×/yr | — |
| Cost drag | 14.8 bps/yr | 4.1 bps/yr | 2.9 bps/yr | — |

| Criterion | Result |
|---|---|
| C1 drawdown ≤ 0.75 × static | pass — 9.97% against a 26.56% limit |
| C2 Sharpe ≥ static − 0.10 | pass — 0.616 against a 0.345 floor |
| C3 both hold at 20 bps | pass — 10.05% and 0.596 |
| C4 both hold at 9 and 15 months | pass — 12.52%/0.417 and 11.49%/0.387 |
| C5 both hold without SPY | pass — 9.44% and 0.556 |

130 monthly decisions. The portfolio was never fully in cash; the sparsest month
held one sleeve, and 19 months held all eight.

---

## How I read this

**The drawdown reduction is real and large.** Through the financial crisis the
strategy's worst drawdown was −9.44%, bottoming 2008-10-31, against the
benchmark's −35.42% bottoming 2009-03-09. Average gross exposure fell to 56% in
2008 and 43% in 2009. The rule got out of the way, which is what it is for.

It is not only de-risking. The exposure-matched benchmark — static weights
scaled to the strategy's own 65% average exposure — still drew down 24.05%.
Holding less explains part of the gap; *when* it held less explains the rest.

**The binding drawdown was not the crisis.** The strategy's −9.97% maximum
drawdown ran from 2011-04-29 to 2011-10-04, with the rule 93% invested; the
static benchmark lost 10.20% over the same episode. In April–May 2010 the
strategy fell 8.46% against the benchmark's 7.13%. In the two fast selloffs of
the period the rule offered no protection, and C1 was decided by 2008 alone.
Where it helped outside the crisis was the slow episodes: 5.59% against 8.09%
in the 2013 taper scare, and 4.77% against 16.86% from mid-2014 to early 2016.
That is the expected shape of a twelve-month rule — it needs months to turn —
and it belongs beside the headline: the drawdown advantage is a claim about
slow declines, not about shocks.

**But this is the window the rule is famous for, and that should dominate the
reading.** The charter's prior-evidence paragraph was written for this exact
moment. A twelve-month trend rule on a diversified sleeve universe is published
work, and avoiding the 2008 drawdown is the single result that made the family
well known. The development period contains that event. Passing C1 here was
close to a foregone conclusion. What this run establishes is that the
implementation reproduces a known effect on the period that effect is known
for — a check on the laboratory, not evidence about the future.

**On risk-adjusted return, this sample cannot tell the two apart.** The Sharpe
difference against static is +0.171 with a 90% interval of −0.240 to +0.543.
The interval contains zero. The drawdown difference is unambiguous; the Sharpe
difference is not, and it should not be quoted without the interval beside it.

**The strategy earned less.** 5.18% against 5.70% CAGR. That is the trade the
hypothesis proposed — the charter asks for reduced drawdown *without destroying*
risk-adjusted return, not for more return — so it is not a failure. But
"trend-following won" would misstate what happened.

---

## Observations that are not criteria

**Neighbouring lookbacks are much worse than twelve months, and C4 did not
notice.** Sharpe falls from 0.616 at twelve months to 0.417 at nine and 0.387 at
fifteen — a relative decline of a third. At both neighbours the strategy's
Sharpe is *below* its own static benchmark: 0.417 against 0.437 at nine months,
0.387 against 0.417 at fifteen. The edge over static does not shrink one step
away; it inverts. C4 passed because its bar is static's Sharpe minus 0.10 —
0.337 and 0.317 for the two variants, each static run over that variant's own
start — not a bar relative to the pre-registered result. So a rule whose edge
disappears one parameter step away still clears the stability check. (A small
part of the fifteen-month decline is the shorter window, whose first signal is
the May 2007 month-end rather than February's; static's own Sharpe falls from
0.445 to 0.417 on it, so the window explains roughly 0.03 of the 0.23.)

I am recording this rather than acting on it. The criteria are locked and the
first historical run has happened, so changing C4 now is precisely the
post-hoc adjustment the registry policy forbids. A future variant should ask
whether stability ought to be measured against the pre-registered result rather
than against the benchmark. For BA-001, the honest statement is that C4 was
passed on a weaker test than its name suggests, and the twelve-month result
should be treated as sitting on a narrower ridge than "stability check passed"
conveys.

**Concentration is a factor problem, not a sleeve problem.** The four equity
sleeves produced 65% of total excess return. C5 removes one *sleeve* — it
dropped SPY and the rule still passed, because IWM, EFA and EEM remain. The
variant's maximum drawdown, 9.44%, is the base run's crisis drawdown to six
figures: SPY was already in cash from the May 2008 month-end through the
trough, so removing it changed nothing where the drawdown test bites. The
criterion tests whether one holding carries the result; it does not test whether
one factor does. The charter already reserves correlation clustering as a later
question, and this run is the argument for taking it up.

**The excess-over-cash correction mattered on real data.** DBC contributed 6.67
in excess return against 682.05 in raw profit — a hundredfold gap, from a sleeve
that spent most of the period roughly tracking cash while deployed. It did not
change the outcome, since SPY tops both rankings here, but the two measures
demonstrably diverge outside a constructed fixture.

**Costs are not the binding constraint.** Turnover is modest at 0.74× one-way
per year, and doubling the cost assumption cost 0.02 of Sharpe. Whatever
eventually decides this strategy, it will not be trading friction at these
levels. Taxes remain unmodelled and the target account is taxable; at this
turnover that is a real omission, not a rounding error.

---

## Data provenance

Prices are Yahoo's chart endpoint with the open placed on the close's adjusted
basis; cash is FRED DGS3MO on an investment basis, converted from the rate known
before each session opened. Both are documented in
`tools/fetch_market_data.py` and stamped into the snapshot manifest, which the
loader checks against the run configuration.

Two limitations belong in this record. The price source is free, unofficial and
revisable, which is tolerable only because the sweep archives the dataset it saw
alongside its results. And `tr_open` is derived rather than sourced — the single
most likely place for an error to enter. Ingestion produced no quality findings,
and every sleeve's largest daily move falls on a genuine crisis date, but that is
absence of evidence for a problem, not independent verification against a second
vendor.

Two smaller notes. The sweep directory, including the archived inputs, is a
local artifact outside version control, so this review and the charter are the
only committed record of the run; that is why the figures are repeated here
rather than only cited. And the snapshot's first DBC bar is 2006-02-06, where
the charter says the fund began trading on 2006-02-03. The first eligible signal
is still the February 2007 month-end, so nothing in the run changes, but the
charter's date should be checked against the fund's own record before it is
relied on elsewhere.

The global-equity diagnostic is recorded unavailable; see
`docs/decisions/2026-09-04-global-equity-benchmark.md`.

---

## Decision

Proceed to the validation period. Nothing here justifies stopping, and nothing
here justifies confidence.

I would summarise the development result as: **the implementation works and
reproduces the known effect on the period that effect is known for.** That is
worth having and is not the same as evidence the rule will help going forward.

## What would change my reading

Written now, before the validation numbers exist, so that it cannot be adjusted
to fit them:

- **Strengthening.** Validation (2018–2021) clears C1 and C2 with the drawdown
  gap holding through the 2020 shock, *and* the nine- and fifteen-month Sharpes
  stay within roughly 0.10 of the twelve-month result rather than a third below.
- **Weakening.** Validation drawdown reduction falls below the C1 threshold, or
  the Sharpe advantage inverts, or the lookback spread widens further. Any of
  these would suggest the development result is the GFC and little else.
- **Not informative on its own.** A pandemic-shock drawdown close to static's.
  The 2020 fall took about five weeks, and 2010 and 2011 already show this rule
  does not get out of a fast decline. That outcome would confirm the development
  record rather than add to it. Validation C1 is still the full-period figure,
  and that is the one that counts.
- **Decisive either way it is not.** Two periods of monthly decisions on one
  universe cannot settle this. The sealed test is one reveal, and even it will
  leave the honest answer closer to "inconclusive" than the criteria's
  three-way classification implies.
