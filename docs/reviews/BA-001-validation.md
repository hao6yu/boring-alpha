# BA-001 validation review

Date: 2026-09-04
Sweep: `f0a36ea722ebefd4`
Period: validation, 2018-01-01 to 2021-12-31 (the full registered window)
Data: `yahoo-adjusted-v1+dgs3mo-v1`, sha256 `d76c47df…`, loaded through 2021-12-31.
The same snapshot the development sweep used, truncated at this period's end; the
fingerprint differs from development's because the truncation point does.
Code: sha256 `4dd1eb16…`, commit `34d946d`. The fingerprint is identical to the
development sweep's, so the two periods were evaluated by the same code. The
provenance record flags a dirty working tree; the untracked file was the run
configuration, committed alongside this review.
Development review: `docs/reviews/BA-001-development.md`, sweep `4b9d1479f811d108`.
Status: **written before any sealed-period run. No unseal has occurred.**

This is BA-001's second of two evaluation periods. With it, the charter's
classification can be computed, and has been.

---

## Result

**Classification: Inconclusive.** C1 passed in both periods. C2 through C5 failed
in validation. Neither rejection trigger fired: the strategy's drawdown was well
below static's and its Sharpe was positive. The verdict is `classify`'s output
on the two sweeps, not a judgment.

| Metric | Strategy | Static | Exposure-matched | Cash |
|---|---:|---:|---:|---:|
| CAGR | 3.63% | 8.61% | 5.84% | 1.11% |
| Volatility | 6.89% | 11.20% | 6.85% | 0.06% |
| Max drawdown | −8.82% | −21.32% | −13.37% | 0% |
| Sharpe vs cash | 0.391 | 0.694 | 0.700 | — |
| Worst month | −3.85% | −8.91% | −5.48% | 0% |
| Avg gross exposure | 62% | 100% | 62% | 0% |
| One-way turnover | 0.79×/yr | 0.28×/yr | 0.19×/yr | — |
| Cost drag | 15.7 bps/yr | 5.7 bps/yr | 3.7 bps/yr | — |

| Criterion | Result |
|---|---|
| C1 drawdown ≤ 0.75 × static | pass — 8.82% against a 15.99% limit |
| C2 Sharpe ≥ static − 0.10 | **fail** — 0.391 against a 0.594 floor, short by 0.20 |
| C3 both hold at 20 bps | **fail** — 8.93% and 0.368 against a 0.589 floor |
| C4 both hold at 9 and 15 months | **fail** — 17.74%/0.163 and 16.14%/0.177; both neighbours fail C1 as well as C2 |
| C5 both hold without SPY | **fail** — 7.09% and 0.288 |

48 monthly decisions, from the December 2017 month-end to November 2021. One
month was spent entirely in cash (January 2019); three months held all eight
sleeves. The sweep produced no warnings.

The Sharpe difference against static is −0.304 with a 90% interval of −0.927 to
+0.225. The interval contains zero, as development's did; the point estimates
have opposite signs.

---

## How I read this

**The hypothesis has two halves, and they came apart.** The charter asks whether
the rule "may reduce severe drawdowns without destroying the portfolio's
long-run risk-adjusted return." The first half replicated: 8.82% against 21.32%,
and C1 passed with room in both periods. The second half did not: a Sharpe of
0.391 against static's 0.694 is the pre-registered guard failing by twice its
tolerance. On the numbers this sample cannot tell the two Sharpes apart, so
"destroyed" is too strong; "did not preserve" is what the record supports.

**The pandemic protection was real, and it came from where the trailing
returns already sat.** From 2020-02-21 to 2020-03-18 the strategy fell 7.42%
while static fell 21.32% and the exposure-matched benchmark 13.37%. The rule
entered the shock 75% invested: EEM and DBC had left at the January month-end,
their trailing returns already below the 2.0% cash hurdle. At the February
month-end, eight days into the decline, IWM stood at −5.4% and EFA at 0.0% over
twelve months against a 1.97% hurdle, and both left; SPY at +8.3% stayed. From
2020-03-02 the portfolio was 50% invested, in SPY, IEF, TLT and GLD, and over
the worst three weeks it lost 3.90% while static lost 16.59%. SPY left only at
the March month-end, after the trough. Compare 2011, when the same rule offered
no protection: at the July 2011 month-end every sleeve's trailing return was
between +2% and +37% against a hurdle near zero, so nothing could exit. A
twelve-month rule protects in a fast decline when the sleeves were already
marginal going in, and not otherwise. That is a statement about the draw as
much as about the rule, and one episode of each cannot separate them.

**The Sharpe failure is two rallies missed.** By year, strategy against static:

| Year | Strategy | Static | Strategy avg exposure |
|---|---:|---:|---:|
| 2018 | −4.93% | −7.48% | 64% |
| 2019 | +7.65% | +19.19% | 48% |
| 2020 | +4.75% | +15.15% | 64% |
| 2021 | +7.51% | +9.51% | 72% |

The fourth quarter of 2018 took every sleeve out by the December month-end.
January 2019 was spent entirely in cash, earning 0.01% while static earned
5.99%, and average exposure through 2019 was 48% in a year static returned 19%.
After the March 2020 trough, IWM, EFA and EEM stayed out until between August
and November; from 2020-03-31 to 2020-08-31 the strategy made 4.67% against
21.40%. Those two stretches are the whole shortfall. It is the classic cost of
a trend rule — it sells the bottom of a V and buys back well up the other side —
and it is exactly what the drawdown protection is paid for with.

**Timing subtracted value this period.** The exposure-matched benchmark holds
the strategy's own 62% average exposure with no timing at all, and earned a
Sharpe of 0.700. The strategy's 0.391 is 0.31 below it. In development the same
comparison ran the other way, +0.17. The drawdown comparison still favours the
strategy in both periods; the risk-adjusted comparison now depends entirely on
which period you look at.

**The cash hurdle cut both ways.** Trailing twelve-month cash returned 2.0 to
2.3% through 2019, the highest in the sample since 2008, and the rule compares
each sleeve to it. That hurdle held sleeves out through 2019's rally; it is
also what removed EEM in January 2020, at +0.6%, and EFA in February, at the
line, ahead of the worst of March. I have not computed how many decisions a
zero hurdle would have flipped over the period. That is a question for a later
variant, not for BA-001.

---

## Observations that are not criteria

**The neighbours failed the primary criterion, not only the guard.** The
nine-month rule drew down 17.74%, from 2020-01-17 to 2020-03-18 — a pandemic
drawdown barely better than static's 21.32%. The fifteen-month rule drew down
16.14% from 2018-01-26 to 2020-03-18, a twenty-six-month decline, and missed the
15.99% limit by 0.15 percentage points. Their Sharpes were 0.163 and 0.177. In
development I recorded that C4 had passed on a weaker test than its name
suggests. In validation it did not pass at all, and it failed on drawdown, which
is the half of the hypothesis that otherwise held. The twelve-month result is on
a ridge in both periods.

**Concentration changed shape.** Equity produced 41% of total excess return,
down from 65% in development, but SPY alone produced 40%: IWM and EEM together
barely offset EFA's negative contribution. Gold, commodities and bonds each
produced about a fifth. So this time C5 removed the sleeve that *was* the equity
factor, and Sharpe fell from 0.391 to 0.288. The criterion did what it was
designed to do here; the development review's point stands that it does not do
so in general.

**Costs are still not the binding constraint.** Turnover is 0.79× one-way per
year and doubling the cost assumption cost 0.023 of Sharpe. C3 failed because C2
failed, not because costs moved anything. Taxes remain unmodelled, and at this
turnover in a taxable account that is still a real omission.

---

## The development review's pre-commitments, checked

The development review wrote down what would change its reading before these
numbers existed. Against the outcome:

- **Strengthening** required C1 and C2 to clear with the drawdown gap holding
  through 2020, *and* the neighbouring lookbacks within roughly 0.10 of the
  twelve-month Sharpe. The drawdown half held. C2 failed, and the neighbours
  were 0.23 below. Did not fire.
- **Weakening** named three triggers: drawdown reduction below the C1 threshold,
  Sharpe advantage inverting, lookback spread widening. The first did not
  happen. The second and third did. The review said any of these "would suggest
  the development result is the GFC and little else." That is now too strong on
  the drawdown side, which replicated, and about right on the Sharpe side.
- **Not informative on its own** anticipated a pandemic drawdown close to
  static's. The opposite happened, and my reasoning was wrong in a specific
  way. I generalised from 2010 and 2011, when every sleeve carried a strong
  trailing return into the shock and nothing could exit. In 2020 half the
  sleeves were marginal going in, two were already out, and the first
  month-end fell eight days into the decline. The rule reacted because the
  trailing returns let it. I am recording that as a miss in my own reasoning,
  and the protection as real. It is not evidence that the rule would react in
  the next fast decline, which depends on the same accident of where trailing
  returns sit.

---

## Data provenance

Identical to the development run in every respect but the truncation date:
the same snapshot, the same methodology identifier, the same fetcher, and the
same loader checks. Ingestion produced no quality findings, and the sweep
produced no warnings of any kind — the twelve-month lookback was complete
before the period began, so every month-end from December 2017 produced a
signal. The limitations recorded in the development review carry over
unchanged: a free, revisable price source, and a derived rather than sourced
`tr_open`.

The sweep directory is a local artifact outside version control, so this review
is the committed record and repeats the figures for that reason.

The global-equity diagnostic remains unavailable; see
`docs/decisions/2026-09-04-global-equity-benchmark.md`.

---

## Decision

**Record BA-001 as Inconclusive.** Not Advance: C2 through C5 failed in
validation. Not Reject: the drawdown reduction held in both periods and Sharpe
was positive in both. The charter's own words apply — inconclusive is a real
outcome, not a failure to decide, and it is not an invitation to search for a
variant that advances.

Two things follow that I have not done, because they are yours to decide:

1. **The registry status.** `docs/strategies/README.md` still reads "Locked for
   implementation." It should say the evaluation is complete and inconclusive,
   with the sealed period unrevealed. The charter body should not change; the
   registry policy keeps results out of charters.

2. **Whether to reveal the sealed period at all.** The classification is fixed
   by development and validation; the sealed test cannot make BA-001 advance.
   Revealing it would be for information only, and it is a one-way act: any
   successor on this universe — a lookback ensemble, a correlation-cluster cap,
   a different hurdle — would then be tested on a period whose outcome for the
   parent rule is already known. My recommendation is to leave it sealed for a
   successor rather than spend it on a strategy that has already been
   classified. If it is revealed anyway, the charter's protocol says what to
   inspect: the 2022 equity-and-bond drawdown is the slow kind this rule has
   handled well in both periods, so protection there would be expected and
   would not repair the Sharpe half.

For a successor, the development and validation records together point at
three of the charter's reserved questions and one new one: whether an ensemble
of lookbacks removes the ridge that both periods sit on; whether correlation
clusters should cap the equity exposure that carried development; whether the
timing of re-entry after a fast decline can be improved without adding lookahead;
and, new, whether the cash hurdle should be zero rather than the cash return.
None of these may change BA-001.

## What would change my reading

Written now, before any sealed-period run:

- **If the sealed period is revealed and the rule protects through 2022 while
  again trailing static on Sharpe,** that is the same result a third time, and
  the reading hardens: this is a drawdown tool with a return cost, not a
  risk-adjusted improvement.
- **If it protects through 2022 and its Sharpe is within the C2 tolerance,**
  the validation result looks like a period-specific cost of two V-shaped
  rallies, and a successor variant deserves the benefit of the doubt on the
  Sharpe half.
- **If it fails to protect in 2022,** a slow decline of the kind it handled in
  2008, 2013 and 2015, the drawdown half of the hypothesis is in question too,
  and the family should be set aside for this universe.
- **Decisive it is not.** Three periods on one universe with monthly decisions
  is still a small sample, and the intervals will say so.
