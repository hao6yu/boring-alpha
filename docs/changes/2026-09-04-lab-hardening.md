# Lab hardening — the ideas behind the changes

Date: 2026-09-04
Range: `2abda20..896b13e` (21 commits; 247 declared test methods, 269 executions)
Status: **revised twice after review.** No run on historical market data has
happened.

Draft 2: a review found five mechanisms weaker than draft 1 claimed, plus four
factual errors in the document. Draft 3: a second review found six of those
closures incomplete, and preregistered the global-equity benchmark. Sections 14
and 15 record both rounds. Every finding in both was confirmed before anything
was changed, and each fix carries a test that fails when the fix is reverted.

This document explains *why* each change was made, not what the diff says. It is
organised by idea, not by commit, because the commits interleave. Where I made a
judgment call on your behalf it is marked **Decision**, and there is a
consolidated list of those at the end.

---

## 1. The problem this work was solving

The lab you had was already unusually honest for a first cut: signals were
observed at the month-end close and filled at the next open, cash was a real
series rather than zero, artifacts were content-addressed, and the charter was
written before the code. I could not make the engine leak future information.

What it lacked was *mechanism*. The charter promised things the code could not
do and could not check:

- "Advance only if results are economically coherent, broadly stable, not
  dominated by one sleeve" — a judgment you would make after seeing results.
- "The tooling refuses data beyond that period's end date" — nothing did.
- "An unavailable sleeve remains cash" — the engine raised instead.
- Stability checks at 9 and 15 months, at 2× costs, with a sleeve removed —
  no way to run them.

Discipline that lives only in a document is discipline you have to remember
under pressure, at exactly the moment a result is interesting. The through-line
of this work is moving each promise from prose into code that enforces it.

---

## 2. Governance: the charter moved twice, both before any data

Your registry policy says a charter change after results exist requires a new
identifier. That rule exists to stop post-hoc edits. But no historical data had
been run, so amending in place was still genuine pre-registration.

**Decision.** I added a clause making that explicit: before a strategy's first
historical run, its charter may be amended in place with a dated change-log
entry; from that run onward, the existing rule applies. Without this the
policy would have forced a new strategy ID for corrections made before any
evidence existed, which is ceremony without protection.

### Revision 2 — your four decisions

You chose these; I implemented them.

1. **Anchor convention.** The 12-month lookback now runs month-end to
   month-end, rather than to the same calendar date a year earlier. The old
   convention landed one or two sessions short in about a quarter of months.
   On synthetic data the anchor session moved in 28 of 96 months and changed
   the target weights in 3. The new convention is what nearly every published
   implementation uses, so cross-checks will now agree.

2. **Ragged start.** Sleeves may begin on different dates. The portfolio starts
   at the first month-end where all eight have a full lookback. After that
   common start, a missing bar is a data error that halts the run — never a
   silent move to cash. For this universe DBC binds; its first bar in the data
   I fetched is 2006-02-06.

3. **Numeric advancement criteria.** C1 to C5 with explicit thresholds,
   replacing the qualitative language. The important property is that they were
   written before any result existed.

4. **Taxable account.** Recorded as a friction, with backtests staying pre-tax
   and a lot-level after-tax check added to the pre-paper checklist.

### Revision 3 — one decision I made

**Decision.** A sealed-test run now requires *both* a development review and a
validation review on disk, not merely a stated reason. Revision 2 required a
written review before validation but only a reason before the sealed test. That
asymmetry looked backwards: the sealed test is the one run that cannot be
repeated, so it should carry the strictest precondition, not the loosest. A
reviewer raised it and I agreed.

---

## 3. Making the discipline mechanical

### Period sealing by truncation

Every run now declares which period it targets — `development`, `validation`,
`sealed`, or `exploratory`. The boundaries live in a checked-in registry
(`configs/evaluation_periods.toml`) rather than in the run config, so a config
cannot quietly widen its own window, and a change to a boundary shows up in a
diff.

The mechanism is **truncation, not refusal**. When a period is named, the
dataset is cut at that period's end before the engine sees it. The alternative
— rejecting an over-long file — would force you to maintain trimmed copies of
every CSV, and copies drift.

Truncation buys a property that turned out to matter more than I expected: a
development run keeps its identity when you later append more data. The data
hash covers only what was loaded. `tests/test_seal_identity.py` pins this by
appending three years of data and asserting the run is byte-identical; I
verified it fails when truncation is removed.

`exploratory` is unbounded, always permitted, and stamps every artifact and
console line with a warning that the run is not evidence. The demo config uses
it.

### Gates

A validation run requires a written development review under `docs/reviews/`.
A sealed run requires both reviews plus `--unseal "<reason>"`, and the CLI asks
you to log it in the charter.

None of this is cryptographic. You can create the file the gate looks for. The
point is to make looking at data you promised not to look at yet a deliberate,
reviewable act rather than something that happens because you typed a date
wrong.

### A mechanical verdict

`criteria.py` evaluates C1 to C5 from run metrics and applies the
advance/reject/inconclusive rule. Every criterion carries the arithmetic that
decided it, because a verdict you cannot check is not evidence. `classify`
computes the outcome; it is never typed in.

---

## 4. The artifact-identity bug, and why it mattered most

This is the change I would most want you to scrutinise, because I introduced
the bug and then had to fix it.

Sealing added `git_commit`, `git_dirty`, and `python_version` to the run
manifest — sensible provenance. But the run identifier is a hash of config,
data, and code, and *none of those three fields are inputs to it*. So the same
run id could produce two different manifests, and the write-once check would
refuse with "refusing to overwrite changed experiment artifact".

The workflows that trigger it are ordinary. Commit a docs change — the code
hash is unchanged, `git_commit` is not — and re-running an experiment to verify
it now fails with what reads as a data-integrity alarm.

Why this is worse than a normal bug: the write-once check is the lab's alarm
for nondeterminism, and principle 6 says existing results are never silently
replaced. Making that alarm fire on environmental noise trains you to ignore it
or delete the directory. It destroys the mechanism the artifact system rests on.

**The fix separates identity from environment.** `manifest.json` is now a pure
function of configuration, data, code, and the resolved evaluation period, and
stays write-once. Each invocation appends a line to `provenance.jsonl`
recording timestamp, commit, dirty flag, Python version, and any unseal reason.
That is strictly more informative than the original design: you learn every
environment a run was ever reproduced in.

The same fix folded in the resolved period bounds as an identity input, which
closes an honest gap — a run now states which boundaries it obeyed, so the same
config under a different registry is a different run.

---

## 5. Being honest about data

### Plausibility checks

`data/quality.py` inspects a loaded dataset and splits findings into those that
stop a run and those recorded against it.

Errors: a one-session move beyond ±40%; an open gapping beyond ±25% from the
prior close; a cash factor implying an annual rate outside −10% to +30%, which
is what a rate entered where a one-session growth factor belongs looks like.

Warnings: shared-calendar gaps over five business days; ten or more identical
consecutive closes.

Each message names the symbol, the date, and the likely cause. The thresholds
are deliberately loose enough that real crises pass — verified against the
fetched data, where the worst days are all genuine 2008 sessions and nothing
trips an error.

Inspection runs *after* the seal truncates, so findings describe the data the
run actually used.

### A negative control

Synthetic data now takes a regime. The default `trending` builds slow cycles
that any trend rule trades well — useful for exercising machinery, and
flattering by construction. `random_walk` is driftless and memoryless: the
series on which a trend rule should earn nothing and still pay costs.

The tests assert the *generator's* property — no detectable drift pooled over
20 seeds and roughly 100,000 sessions — rather than asserting the strategy
fails on noise. A single-seed "strategy loses on noise" claim would be flaky.
Whether BA-001 earns anything on the control belongs in the harness as a
reported diagnostic.

---

## 6. The evaluation harness

`boring-alpha sweep` runs the charter's pre-registered grid in one command: the
12-month rule, the same rule at 2× cost, the 9- and 15-month neighbours, and
the rule with its largest-contributing sleeve held permanently in cash.

Running them together is the point. Run separately, the stability checks become
a menu you pick from after seeing outcomes — exactly what the charter forbids.
`summary.md` leads with the pre-registered result and labels everything after
it as a check.

New reported diagnostics: exposure-matched benchmark (so a half-invested
strategy is not judged only against a fully invested one), one-way turnover,
cost drag, worst month, time in market, per-sleeve and per-cluster attribution,
and a stationary block bootstrap interval on the Sharpe difference.

**On the bootstrap.** On roughly a decade of monthly decisions the interval
will often contain zero. That is the honest answer, not a defect, and the
summary says so in plain words when it happens. It also cautions in the other
direction: an interval that excludes zero should still be read with the
charter's prior-evidence discount, since this rule was published before your
test.

**A correction worth flagging.** I first ranked sleeves by raw currency profit.
The charter defines contribution as a sleeve's share of excess return *over
cash*. Those disagree whenever holding periods differ — a sleeve deployed all
period at roughly the cash rate scores high on raw profit and near zero on
excess — and with cash at 4–5% that is ordinary, not exotic. Since C5 removes
"the largest-contributing sleeve" and C5 gates advancement, the harness could
have removed the wrong sleeve and returned a confident verdict. The engine now
charges each sleeve the cash its capital forwent, and C5 ranks on that. Raw
profit is still shown beside it, because the disagreement is informative.

---

## 7. The portfolio / execution split

Your principles document requires four separable layers and says backtest,
paper, and live modes must share the first three. The last two were fused:
`Portfolio.rebalance` valued the book, decided the trades, and filled them with
costs in one method.

Nothing in the system emitted an order. So a paper fill had nothing to be
compared against, and the milestone this lab exists for — comparing paper
results against historical simulation — was unreachable without either this
split or a second implementation of the sizing rule that would drift from the
first.

One rebalance is now three named steps:

```
decision → plan_rebalance → Order intents
         → execute        → Fill records   (the only place a cost model lives)
         → apply          → cash and positions
```

`execute` takes a plain price mapping rather than a market dataset, so paper
mode can feed it broker quotes unchanged.

**Records are flat and matched by `(date, symbol, side)`.** I initially designed
`Fill` to hold a reference to its `Order`. On reflection that models a link the
live system will not have: a broker returns fills that know nothing about our
objects, and reconciliation matches them by instrument, side, and date. Flat
records also serialise directly.

*Correction.* An earlier draft of this section said an order that fills for
nothing is visible by the absence of a fill. That is not what the code does: a
buy scaled to zero still emits a zero-notional fill, deliberately, because the
old fused path appended a zero-quantity trade and the ledger is written in list
order — dropping the row would have broken behaviour-neutrality.
`tests/test_execution.py` pins it.

**Sizing deliberately did not change.** Orders are still sized from equity at
the execution open, not at the decision close. The decision-close version is
arguably more faithful to an order you actually place after a month-end, but it
changes results, and bundling a behaviour change into a refactor makes neither
reviewable. Recording `reference_price` makes that comparison available later as
a declared variant.

**The refactor is behaviour-neutral, and this was verified, not asserted.** I
captured the demo backtest and sweep artifacts before starting and diffed after:
equity curves, metrics, decisions, criteria, and summary all byte-identical. A
reviewer went further, reconstructing the pre-refactor code and running both
paths — 4,764 fills and 2,088 equity points at a maximum difference of exactly
zero — and a 200,000-case fuzz found the new planner *strictly better*: above
roughly $540,000 of position value the old code emitted rounding-residual dust
trades that the new code cannot. Relevant only if you fund the real run well
above the demo's $100,000, but now a known property rather than a surprise.

**The ledger gained two columns**, `intended_notional` and `reference_price`
(`artifact_schema` 5). Slippage is now visible: in the fetched data DBC was
decided at 142.879 on the month-end close and filled at 142.743 the next open.

---

## 8. Real data

`tools/fetch_market_data.py` builds both CSVs from public sources, with its
methodology in the docstring because those choices are what the charter's "data
provenance and adjustment methodology reviewed" item is about.

Prices come from Yahoo's chart endpoint; the cash leg from FRED `DTB3`.

Two things you should carry forward:

- **The source is not research-grade.** Yahoo's endpoint is free, unofficial,
  has no SLA, and its back-adjusted history is revised. This is tolerable only
  because a revised download changes the data hash and so produces a new run
  id rather than altering a result in place. A strategy heading toward real
  money needs a proper vendor.
- **`tr_open` is derived, not sourced.** The endpoint adjusts only the close, so
  the open is put on the same basis with the close's own factor. This is the
  usual convention and it is an assumption — the single most likely place for an
  error to enter. I verified on 2008-10-13 that the adjustment factor is
  constant across a non-ex-dividend window and that raw and adjusted returns
  agree to six decimals.

Ingestion for the development period loads clean with **zero quality warnings**.
I audited rather than trusting that: every sleeve's worst day is a genuine
crisis date, the implied cash rate spans −0.02% to 6.24%, and the largest
shared-calendar gap is two business days (Hurricane Sandy, October 2012).

**No backtest was run.** The amendment window is still open.

---

## 9. On the tests

The suite went from 8 declared test methods to 247. Three things about it are
worth more than the count.

**The count is executions, not distinct coverage.** 247 test methods are
declared; subclassed fixtures re-run 22 of them, giving 269
executions. Read the declared number.

**A permanent lookahead test.** Halving every price after a cutoff must leave
all earlier decisions, trades, and equity points identical. This is the property
the whole lab depends on, and it is now pinned rather than inspected.

**Three tests were found that could not fail.** Reviewers proved it by breaking
the implementation deliberately and watching the suite stay green — the engine's
reference-price wiring, the residual-cash clamp, and a partial-fill assertion.
All three came from test code I wrote into the plan verbatim. Every replacement
now carries its own mutation proof.

The final review found two more of the same kind: the no-trade threshold could
be inflated from `1e-10` to `1e2` — changing the demo from 423 fills to 367 and
moving final equity by $12.40 — with every test still passing, and the
cost-to-attribution charge could be zeroed out with no test failing, which feeds
C5's sleeve selection. Both are now pinned.

This is the pattern I would most want you to be sceptical about in my work: I
write tests that describe what the code does rather than tests that would catch
it being wrong.

---

## 10. Decisions I made on your behalf

Each with what it costs if I got it wrong.

1. **Pre-data amendment clause** added to the registry policy. *Cost: a charter
   could be edited before its first run without a new ID — which is the intent,
   but it is a loosening you should agree with.*

2. **Sealed runs require both reviews** (charter revision 3). *Cost: more
   ceremony before the sealed test; trivially reversible.*

3. **`criteria.json` allowed to differ** in `code_sha256` and `sweep_id` during
   behaviour-neutrality verification, because both derive from the code hash by
   design. *Cost: none — I checked every other field matched rather than taking
   a report's word.*

4. **Accepted 202 tests where my plan predicted 201.** The plan's arithmetic was
   stale. *Cost: a miscount could mask a deleted test; I confirmed against the
   suite's own output.*

5. **Ruled against my own plan on three tests** that a reviewer mutation-proved
   could not fail. *Cost: rework in test files only.*

6. **Bundled one minor fix into a running fix round** rather than deferring it.
   *Cost: negligible; the field was inert.*

7. **Ticked the charter's "Implementation matches revision 3" checkbox** and
   corrected the change-log sentence saying the implementation was behind, after
   a reviewer verified all four named items are implemented. *Cost: a charter
   that overstates readiness — which is why the edit names the four implementing
   functions so you can check it. This is the one edit to a locked document.*

---

## 11. What I deliberately did not do

- **No real-data run.** The first is yours to time.
- **No change to BA-001's signal, universe, weights, costs, or execution
  timing.** Nothing in this work alters what the strategy does.
- **Taxes are not modelled.** Recorded as a friction and a pre-paper checklist
  item.
- **No broker connectivity, order types beyond market-on-open, whole-share
  rounding, or partial-fill modelling** beyond the existing cash constraint.
- **The global-equity benchmark is preregistered but not yet sourced.** Charter
  revision 4 names it: MSCI ACWI Net Total Return USD, close-to-close, as a
  non-gating diagnostic, with an explicit instruction to report it *unavailable*
  rather than substitute an ETF or synthetic proxy if a legally usable and
  reproducible daily series cannot be archived. An index rather than a fund
  because none spans the development period — VT lists June 2008, ACWI March
  2008 — while the index carries a December 2000 base date. Naming a fund would
  have shortened the comparison or quietly changed what is compared.
- **The charter's reserved research questions stay reserved** — calendar luck,
  lookback ensembles, tolerance bands, tranching, execution-timing sensitivity.
  Each would be a new identifier under your registry policy.

---

## 12. Open risks I would want you to weigh

1. **The data source.** Free and revisable. The artifact system contains the
   damage but does not eliminate it.
2. **`tr_open` derivation.** Documented and spot-checked, not independently
   verified against a second vendor.
3. **Statistical power.** Roughly 180 monthly decisions across three regimes,
   with the sealed period essentially one regime. The bootstrap will probably
   say so.
4. **Prior evidence.** A 12-month trend rule on this universe is published work.
   The development window is out-of-sample for this implementation only. The
   charter now says this; it is worth re-reading before you interpret a result.
5. **"The sealed test cannot be repeated" is loose wording.** What cannot be
   repeated is the *reveal*: once you have seen sealed results you cannot unsee
   them. Re-running the identical sweep is not only allowed but is what the
   artifact system is built for, and it will reproduce the same run id. The
   charter's precondition guards the first look, not reproducibility.
6. **Deferred minor findings** carried rather than fixed: a bare `KeyError` when
   a reference price is missing; `execute` and `apply` disagreeing about how to
   treat an unrecognised order side (now guarded, but the asymmetry was real);
   local variable names still saying `trade` where they hold `Fill`s. The final
   reviewer judged each acceptable to carry.

---

## 14. Findings from the review of this document's first draft

Five mechanisms were weaker than draft 1 claimed. I confirmed each before
changing anything, and each is now closed with a test that fails when the fix
is reverted.

1. **Evaluation periods could be cherry-picked.** The window check accepted any
   *subset* of a registered period, so a 2017-only run was accepted as
   "development" — confirmed by loading exactly that config. An evidence run now
   has to match its registered start, and its end unless the period ends at the
   dataset. This is the most consequential of the five: it was a hole in the
   protection the evaluation protocol exists to provide.

2. **`classify` could combine incompatible strategies.** It compared four fields
   and *skipped any that were absent*, so a missing field silently passed.
   Universe, sleeve weight and initial capital were never compared at all. Runs
   now carry `strategy_spec_sha256`, a fingerprint of what the strategy is with
   the window deliberately excluded, and absence is refused rather than skipped.

3. **The fetcher was unsafe in three ways.** It used DTB3 — a bank-discount
   quote computed against par on a 360-day year — as though it were a return on
   money invested. It is not, and the error understates cash, which flatters a
   rule whose entire signal is "does this beat cash". Now DGS3MO, on an
   investment basis; the two differ by about 0.14 points at current levels. It
   also included the still-trading current session, and wrote prices before
   fetching cash so a FRED failure could pair new prices with stale cash. Both
   fixed, and the fetcher now has twelve tests where it had none.

4. **Sweep artifacts preserved too little.** Only aggregates were written, which
   does not meet principle 6's list of decisions, trades and equity curves. Each
   variant now keeps its own, and — more importantly — the dataset the sweep saw
   is stored beside the results. A data hash proves the inputs changed; it does
   not let you rebuild the old run, and Yahoo's history gets revised.

5. **The C5 correction was weakly tested.** The fixture ranked the same sleeve
   first under both definitions, so reverting to the original raw-profit bug
   kept the suite green — I verified that it did. A new fixture makes the two
   disagree by a wide margin, and the revert now fails.

Plus one the review raised in passing: **NaN passed every guard**, because it
fails all ordered comparisons, so `<= 0` never caught it. Prices, cash factors
and configured numbers are now checked for finiteness.

This is the second time in this work that my tests described what the code did
rather than catching it being wrong, and the second time an outside reading
found it. Treat that as the standing risk in what I produce here.

## 15. Findings from the review of draft 2

Six of the closures above were incomplete. All six confirmed, all six fixed.

1. **A dataset-ended sealed run could still stop early.** The registry fixes
   only such a period's start, and the engine honoured whatever end the config
   named — so a run could report 2022 to 2023 as "the sealed test" while data
   existed through 2026. Finding 1 of the previous round closed the *start* of
   the cherry-picking hole and left the end open. An evidence run against a
   dataset-ended period must now extend through the latest complete shared
   session.

2. **The fetch was not atomic as a pair.** Two separate renames leave a window
   in which a crash pairs new prices with old cash. A run now writes into a
   timestamped snapshot directory with `manifest.json` written *last*, so a
   directory lacking a manifest is visibly incomplete, and `data/current` is
   repointed only after the manifest lands.

3. **`strategy_spec_sha256` recorded only `data_source="csv"`.** That cannot
   tell one adjustment or cash methodology from another, and the fetcher sits
   outside `code_fingerprint()` — so changing how the data is built was
   invisible to a run's identity. CSV configs must now declare
   `data.methodology`; it enters the spec hash, and the fetcher stamps the same
   identifier into every snapshot manifest.

4. **A NaN quality threshold disabled its own check.** Verified: two findings
   became zero. The previous round's claim that "configured numbers are finite"
   did not cover the override table. Overrides are now checked for finiteness,
   and magnitude thresholds for positivity.

5. **A test proved nothing.** The one asserting the spec hash ignores the
   evaluation window replaced the start date *with itself*. It now compares a
   development config against a sealed one.

6. **The document's own arithmetic was wrong**, in the section complaining about
   arithmetic. Corrected above — and then got it wrong a second time on first
   commit, because I quoted a count measured before adding more tests. The
   figures are now 247 declared, 22 inherited re-runs, 269
   executions, measured against the committed tree.

Item 5 is the third time an outside reading has caught a test of mine that
cannot fail, and item 6 is the second time it has caught an inaccuracy in my
account of the work. Neither the code nor the note should be read as
self-verified.

## 16. If you want to proceed

The next step is a development sweep, which is BA-001's first real-data run and
closes the amendment window:

```bash
cp configs/ba_001_real_csv.example.toml configs/ba_001_development.toml
boring-alpha sweep configs/ba_001_development.toml
```

That writes `summary.md` and `criteria.json`. Then a written review under
`docs/reviews/BA-001-development.md`, which the tooling requires before it will
let you run validation.

If anything in this document should change in the charter, now is the last cheap
moment.
