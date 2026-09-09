# The sheet that can say no

Measured 2026-09-07, round 79. New tool: [`decision_sheet.py`](../../tools/decision_sheet.py). Tests: 16 in
[`test_decision_sheet.py`](../../tests/test_decision_sheet.py).

Seventy-eight rounds have produced four grids that disagree in informative ways — [`rotation_search.py`](../../tools/rotation_search.py),
[`tilt_brake.py`](../../tools/tilt_brake.py), [`binding_payout.py`](../../tools/binding_payout.py),
[`mix_sweep.py`](../../tools/mix_sweep.py) — and no page that says what to do about it. Notes drift, and a note that quotes a
figure outlives the archive that produced it. Round 71's rule for the shelter ticket applies to this whole body of work: an
instruction sheet is regenerated from the tools that measured the claim, prints nothing it did not read from one of them, and
**must be able to refuse**. So the sheet exists, and there is not one dollar amount written in its source.

```
  scale $100,000 · position income · horizon recent · archive through 2026-09-04

  1. THE TWO POSITIONS, PRICED SIDE BY SIDE  [mix_sweep.py]
     record A: 2011-06-24 on (the last fifteen years)      record B: 1999-12-22 on (the earliest this family can be scored)
     mix_00      0% QQQ             A funds    $919.02  B funds      none   worst drawdown A 33.7% B 55.2%
     mix_50     50% QQQ             A funds  $1,101.66  B funds      none   worst drawdown A 30.9% B 69.0%
     mix_100   100% QQQ             A funds  $1,269.14  B funds      none   worst drawdown A 35.2% B 83.0%
     brake_75   75% QQQ +cash brake A funds  $1,020.00  B funds    $466.68  worst drawdown A 29.4% B 30.8%

  4. THE ASK, PRICED
     asked $900.00/mo = 0.82x the static blend's recent-window capacity
     the mix_100 book funds $1,269.14/mo on the recent record at a 5% failure budget
     measured failure probability at exactly that withdrawal: 0.0% of 63 ten-year windows
```

Four positions from two records, side by side rather than averaged into a recommendation nobody can act on: plain fund, the
blend, the tilt, and the braked tilt. A withdrawal can then be asked — the sheet's fourth block prices it at **exactly that
dollar figure**, not at the nearest grid point, and refuses if the book cannot fund it:

```
  REFUSED · $900.00/mo exceeds what the brake_75 book can fund on the deep record ($466.68/mo at this size)
  what would change it: reduce the withdrawal, add capital, or accept a failure budget you have named instead of 5%
```

And refusals are the point, not an error path. The objective as literally stated — a short-horizon bot reading global news —
is answered by the sheet directly:

```
  REFUSED · cannot price attention-corpus veto (round 72): the corpus peaks with rallies, and every priced veto cell was negative
  what would change it: acquire the data first; no amount of modelling substitutes for it

  REFUSED · cannot price intraday or multi-day trading: the archive holds daily closes, no intraday print and no quoted spread
  REFUSED · cannot price options or any derivative: no options data exists in the archive
  REFUSED · cannot price single-name selection: the archive holds index ETFs and nothing else
```

Those four refusals are the same four refusals the archive imposes, and exit code 3 tells a caller so. A sheet that printed a
number for a five-day strategy from daily closes would be the most expensive document in this repository, and it would be
wrong in a direction nobody could audit.

## What the tests hold down

The sheet's whole claim is traceability, so the tests attack that claim rather than the layout:

- **no dollar literal in the source.** A regex over the module fails the build if anyone types a figure into the sheet. This
  is the discipline that round 73's `sleeve_table` used for prose and it generalises: a hand-typed number is a number that
  will be quoted after the tool that measured it has moved.
- **every figure on the rendered page appears in the data the renderer was handed** (to the cent, both signs, with a guard that
  the page printed enough figures for the check to mean anything).
- **each section names its source tool**, and the refusal block is asserted to be present.
- **everything scales linearly** — a $250,000 scale is 2.5× a $100,000 one for every book and window, which is the difference
  between a parametric sheet and advice about somebody's account.
- the withdrawal asked is priced by a **fresh path at that exact payout**, twice called with the same answer, and monotone
  between two asks.
- the four numbers in block 2 are **differential-tested against `rotation_search.grid`**, and the header's date is differential-tested
  against the archive itself: a sheet that cannot say when it last looked at the data will be read as current a year from now.
- every refusal path is exercised, including nonsense parameters refusing *before* anything is priced, and `main` exiting 3
  with the reason on stderr where it cannot be mistaken for the sheet.

## What the sheet inherits, and therefore what it is worth

It inherits every assumption underneath it, and says so by naming its sources: flat 35 bps for the three sleeves with no
posted expense ratio, month-start readings except where a tool prints both, ten-year windows, a 5% failure budget, 2 bps of
turnover and no market impact, no taxes, and a withdrawal model with no path dependency beyond the sequence it simulates. The
sheet is not more honest than the grids under it — it is only more legible, and legibility is what was missing.

## Where that leaves the objective

The objective has an answer now, and it is parametric, priced, and re-runnable in one command:

- **Beating plain VOO/SPY monthly on withdrawal capacity is available for free** (hold the growth tilt: +$182.64 to +$350.12
  /mo per $100k over plain SPY on the last fifteen years) and **no decision in the archive beats the static tilt that does
  it** — rounds 61, 72, 74, 75, 76, 78, each with its own family and its own control.
- **A 5% failure budget over the whole scoreable record cannot be met by any static book**; only a brake meets it, at
  $458–$467/mo per $100k, about 0.42x of the income answer. The two positions differ by **2.40x** in capacity at matched
  weights ($1,101.66 against $458.06) and **2.72x** between the two books the sheet actually offers ($1,269.14 against
  $466.68), and that gap is the price of the budget.
- **The bot the objective describes cannot be priced here at all**, and the sheet refuses it by name rather than quietly
  substituting a monthly moving average. If the short-horizon, news-informed shape is the one worth pursuing, the next
  artefact is a data feed and its ingestion contract, not another tool reading daily closes.

That is as close to "a way to achieve it" as this archive can honestly produce: two priced positions, a refusal with a
reason, and one command that regenerates the whole thing from the measurements.

## Checks

16 tests, 13 s, offline. Suite: **2021 passed** (collected first: 2005 + 16); ledger chain intact. Exit codes: 0 for a sheet,
3 for a refusal.
