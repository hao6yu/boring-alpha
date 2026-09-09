# BA-007's first cross-sectional sweep: both signals fail their own gates, and the honest-stop note is the deliverable

> **Further audit, 2026-09-09:** additional defects invalidate reliance on the
> economic estimates and broad conclusions below. Momentum used the wrong
> horizon; weekly positions were accounted as constant daily weights; missing
> bars removed held positions; random controls reused static assignments.
> Execution and funding assumptions also limit inference. The original text
> is retained as history. See [the repair record](2026-09-09-quant-takeover.md).
> No corrected profitability claim or fresh holdout is implied.

Measured 2026-09-09 on the first full snapshot of the spine. Charter [`docs/strategies/BA-007.md`](../strategies/BA-007.md) was locked
2026-09-08, before any signal touched a real price; this note reports the verdict its gates computed — **FAIL for both pre-registered
signals** — and stops the charter's question under its own §11 stopping rule. No lookback is nudged, no tercile is widened, and the
reversal that won is *not* promoted to a candidate: it is the third hypothesis the charter's multiple-testing accounting pre-empted, and
it would need its own charter to be scored at all.

## Provenance

- Snapshot `data/perps/snapshots/20260909T053321419791Z`: **703,507 daily rows over 1,018 symbols** (of 1,032 listed; 14 directories with
  no monthly archive), **2,831,180 funding events**, 2,221 day holes inside served spans — reported, never stitched. sha256:
  prices `9fe74b854af0b7d8…`, funding `030c3f05cf73792e…`. Full archive facts in
  [`docs/data/binance-perps.md`](../data/binance-perps.md).
- Sweep artifacts `data/perps/backtests/20260909T071505Z` (`metrics.json` + one daily CSV per signal per period). Engine commit: the one
  this note's git hash names; charter locked at `f1c5f08`, unamended between lock and sweep. The sweep ran in 28.5 seconds.

## What ran (fixed by charter §4–§8 before any of it saw the archive)

Two signals, one construction, one fee grid — the whole family: **XS-MOM** (7-day cross-sectional momentum) and **XS-CARRY** (72-hour
summed funding, ranked ascending), weekly dollar-neutral tercile books at gross 1.0, top-30-by-trailing-30-day-median-quote-volume
universe, point-in-time, delisted symbols eligible at their own ranks. Costs 5 bps taker per side primary, 10 bps stress, funding always
at realized rates. Development 2020-02-01 → 2022-12-31 (1,042 sessions), validation 2023-01-01 → 2024-12-31 (731). The sealed window
(2025-01-01 → latest) is untouched and stays unspent: neither signal earned the reveal.

## The table

| signal | period | net/yr | bootstrap 95% | reversed | scrambled med | stress net | G1 | G3 | G4 |
|---|---|---|---|---|---|---|---|---|---|
| XS-MOM | development | **+21.67%** | [−6.74%, +51.09%] | −28.30% | −2.38% | +18.35% | ✗ | ✓ | ✗ |
| XS-MOM | validation | **−5.85%** | [−37.31%, +27.15%] | — | — | −9.44% | ✗ | — | ✗ |
| XS-CARRY | development | **−42.98%** | [−72.94%, −14.00%] | **+38.28%** | −2.38% | −45.33% | ✗ | ✗ | ✗ |
| XS-CARRY | validation | **−50.50%** | [−73.89%, −27.07%] | **+45.23%** | −0.21% | −53.13% | ✗ | — | ✗ |

Verdicts, computed from the artifacts by `ba007.verdict()`: **XS-MOM FAIL (2/6 gates)** — only the two G3 controls passed. **XS-CARRY
FAIL (0/6)**. Per charter §11, development failing G1 ends the question: the honest-stop note is this document, Phase 4's paper-book
integration does not happen, and the sealed window stays sealed.

## What the numbers actually say

1. **XS-MOM: the ranking was real in development and still not an edge.** The candidate beat its reversed mirror by 50 points a year and
   its scrambled median by 24 — the ranking carried information, which is exactly why this is worth reporting rather than burying. But the
   bootstrap interval of the net annualized mean contains zero (the point estimate rides on a handful of mania months), and validation
   **reversed** (−5.85% where development promised +21.67%). That is BA-001's shape wearing a cross-sectional coat: a development
   advantage that dies out of sample is the finding, and G2 (both windows or nothing) is the gate that exists to catch it. The failure is
   not fee-driven — the whole cost stack (fees 9.5% + funding 1.7% of a year, at 66× turnover) is smaller than the development-to-
   validation swing.
2. **XS-CARRY: the funding cross-section was positively predictive of returns — the harvest was run over by the mania.** The carry book
   *received* +12.35%/yr of funding and still lost 43% a year gross, because the short leg (the highest-funding names) appreciated through
   the floor: short leg −86.99% in development with a −99.4% drawdown, long leg flat at +1.04%. On this archive, high funding marked the
   crowd's *winners*, not their reversals — the reversed book earned +38.28% and +45.23% a year by holding what the carry book shorted.
   That asymmetry held in both windows, which makes it a documented observation about this archive rather than a fluke — and, per charter
   §4's declared multiple-testing accounting, **a documented observation is all it is**: "funding as a momentum proxy" is a new
   hypothesis, and scoring it on these same seen windows without a new pre-registered charter is precisely the variant-shopping this
   charter was written to forbid.
3. **The construction worked; the edges did not.** Beta versus BTCUSDT: +0.001 and −0.016 — the dollar-neutral book is beta-neutral as
   designed. Fourteen symbols delisted mid-development and were closed at their last observed prices; the universe inherited
   survivorship bias from nowhere. The controls moved exactly as the gates required them to. The machinery this charter leave behind — a
   survivorship-free 1,018-symbol panel, a weekly cross-sectional engine with mirror-image and scrambled controls, and a mechanical
   verdict — is the part that survives the verdict.

## What this does to the objective

The user's standing question was whether a *quantitative* program could earn extra weekly. After one full pre-registered sweep: the
cross-sectional question is answered **no for this construction** — weekly momentum at retail taker fees is indistinguishable from zero and
reverses out of sample, and the funding cross-section pays the trend, not the carry harvester. Per the charter's stopping rule, BA-007
stops here. The repo's honest ledger now reads: timing one asset — Inconclusive; sizing one asset — failed its gates; capturing the
index — Redundant; ranking many assets at weekly cadence — failed both signals' gates. Every branch the objective gestured at has now been
priced, and every price came back negative or inconclusive. That is not a failure of the instrument; it is the instrument working.

*The next hypothesis, if there is one, starts as a new charter with gates locked before the first rank — the sealed window is still
unspent, and the lab is still the most valuable thing here.*

---

## Correction, 2026-09-09 (same day, and it changes the CARRY verdict)

**The engine implemented XS-CARRY's ranking inverted against the locked charter.** Charter §4 registers CARRY as *rank ascending — long the
most-negative-funding tercile*. The engine ranked descending, so the sweep graded the mirror of the registered signal as the candidate and
scored the registered construction as its "reversed control." The table above stands as printed — those rows are real — but the labels were
swapped: the row marked *reversed* (+38.28%/+45.23%, bootstrap excluding zero in both windows) **is** the charter's registered CARRY, and
the row marked *candidate* (−42.98%/−50.50%) is its mirror.

Corrected, with the engine fixed and the direction pinned by a fixture test that quotes this charter's sentence:

| signal | period | net/yr | bootstrap 95% | stress net | verdict |
|---|---|---|---|---|---|
| XS-CARRY (as registered) | development | **+31.69%** | [+2.55%, +61.52%] | +29.36% | ✓ |
| XS-CARRY (as registered) | validation | **+41.36%** | [+18.42%, +64.94%] | +38.71% | ✓ |

**Corrected verdict: XS-CARRY PASS 6/6.** Both windows' intervals exclude zero, the mirror loses by 68 and 88 points a year, the scrambles
lose, and stress holds. Per charter §11 this opens the sealed reveal (2025-01-01 → latest — twenty months on disk, untouched by any signal)
as a deliberate next act, and only then the paper book. XS-MOM's FAIL is unchanged and stands.

Two things the correction surfaced, both disclosed rather than buried:

1. **A funding clamp tie straddles the tercile boundary.** Six symbols print exactly −0.000900 per 72h (a venue clamp), and a 6-way tie cut
   by the ranking's two mirror orderings lands different members in the short tercile: one resolution shorts ADA, the other XRP. The two
   resolutions differ by ±6.6%/yr on the development estimate (+38.28% vs +31.69%) and **both pass every gate**. The tie-break is
   deterministic (stable sort, alphabetical within equal scores) and now part of the record; the magnitude of its freedom is the number
   this disclosure exists to carry.
2. **The mechanism narrative above the correction is inverted and left as printed.** The data says the *lowest*-funding names outperformed
   the highest — the academic crowding-reversal direction, which is what the charter registered — not the mania-run-over story this note
   first told. The correction is the record; the original text stays as the record of the error.

**What this does to BA-008:** its locked premise — long the *highest* funding forward — was derived from the inverted reading. The
registered direction is the one that passed, and its next test is BA-007's own sealed reveal. BA-008 is amended the same day (allowed
before its first graded session): see its change log.

---

## The sealed reveal, 2026-09-09: the hypothesis dies where it was supposed to be tested

Approved by the account holder the same day (reason recorded in the reveal artifacts), opened for XS-CARRY only — XS-MOM failed its gates
and its sealed sessions stay sealed. Window: **2025-01-01 → 2026-09-07**, ~87 weekly rebalances on disk, never touched by any signal
computation before this run. Artifacts: `data/perps/backtests/20260909T215759Z-reveal/` (the reveal reason is inside `metrics.json`).

| sealed window (20 months) | net/yr | bootstrap 95% |
|---|---|---|
| XS-CARRY (registered) | **+9.58%** | **[−44.91%, +63.25%]** |
| reversed (high-funding long) | −15.29% | — |
| scrambled median (20 seeds) | **+9.84%** | — |
| stress (10 bps) | +6.72% | — |

**Sealed verdict: FAIL (1/4 gates).** The one passing gate is G3-reversed. G1 fails — the interval contains zero by a mile. G3-scrambled
fails in the most damning way possible: **random tercile books earned +9.84%/yr, more than the candidate's +9.58%** — the ranking carried no
information in 2025-2026; the +9.58% is what *any* tercile book collected from that regime's dispersion. G4 fails at stress. And the ride
got worse, not better: maximum drawdown −41.0%, against −33.5% and −12.6% in the seen windows.

This is the shrinkage the charter's honest prior promised, measured: the seen windows said +31.69% and +41.36%; the window the hypothesis
never influenced said +9.58% with an interval you could drive a truck through, indistinguishable from random. Per charter §11, the sealed
FAIL ends BA-007. The program closes:

- **XS-MOM**: FAIL on seen windows (2/6). Sealed window unopened, permanently — a failed signal earns no reveal.
- **XS-CARRY**: PASS on seen windows (6/6, after a dated engine-direction correction), **FAIL on the sealed reveal (1/4)**. The
  seen-windows pass was the entry ticket, not the prize; the seal was the prize, and it went to the scrambles.

What the repo keeps: a survivorship-free 1,018-symbol perp panel with resumable fetching; a cross-sectional engine whose every mechanism is
pinned by fixtures including signal direction; the forward-only grading protocol BA-008's withdrawal transferred into the record; and now a
complete worked example of the full lifecycle — hypothesis, pre-registration, seen-window pass, sealed test, shrinkage, death — executed in
one day, at a cost of zero dollars, which was the only honest price this hypothesis was ever worth.

*The next hypothesis, if one is ever registered, starts here: gates locked before the data exists, tested on data that cannot flatter it.*
