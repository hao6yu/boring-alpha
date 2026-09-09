# Pre-flight: the mirror-image hypothesis, killed before it was written

Date: 2026-09-05. Status: **negative, no charter drafted.**

## Why this was worth ten minutes

BA-001, BA-002 and BA-003 are the same family pointed the same way: buy what has
gone up, sell what has gone down. All three failed. `src/boring_alpha/signals/`
contains one module, `trend.py`, and the string "mean revert" does not appear
anywhere in the repository. Three evaluations of one family, and the inverse
hypothesis — which has a different mechanism, different failure modes and a real
literature behind it — had never been looked at.

It also looked *promising* for a reason specific to this repo. BA-001's own
validation review describes the rule exiting IWM and EFA at the February 2020
month-end, eight days into the collapse, and exiting SPY at the March month-end,
after the trough. A rule that sells into the decline and re-enters after it is a
rule paying the whipsaw cost that a reversal rule collects. That is a plausible
story about why trend underperformed here and why the other side might not.

The cheap test was to check the raw moments before writing a charter, a protocol,
or a single line of engine code.

## Test

Monthly close-to-close, snapshot `20260904T192633Z`, eight sleeves. For every
month, sort by the prior month's sign and take the mean of the *following* month.
A positive spread (down-months outperform) is what a reversal strategy needs.
Three eras, run separately, so a single flattering decade could not carry it.

| sleeve | 1993-02..2007-05 | seen A+B 2007-06..2021-12 | 2022-01..2026-09 |
|---|---:|---:|---:|
| SPY | −0.02 pp | +0.05 | +0.26 |
| IWM | −1.28 | −0.50 | +0.26 |
| EFA | −1.77 | −0.60 | −0.17 |
| EEM | +1.87 | −0.45 | −0.29 |
| IEF | −0.25 | −0.11 | −0.01 |
| TLT | +0.10 | −0.15 | −0.13 |
| GLD | −0.50 | −0.14 | −0.55 |
| DBC | −0.95 | −0.79 | −1.20 |
| **mean of sleeves** | **−0.35** | **−0.34** | **−0.23** |

Down-month counts: 190, 808 and 1003.

## Result

The sign is wrong, and it is wrong in all three eras. After a down month these
assets go on doing worse, by roughly a third of a percentage point per month on
average, versus the following up month. That is continuation, not reversion. The
one sleeve with a positive reading in the early era is EEM in a single emerging
market stretch, and it reads negative in both later eras.

So a reversal strategy in this universe would have been paying the whipsaw in the
other direction, and the BA-001 observation about February 2020 was the symptom
of something more general than trend's bad luck: this sleeve set trends in the
short run.

No charter. No protocol. Nothing was pinned, no holdout was consumed by a scored
run, and this note is the whole cost of the idea.

## The part that matters more than the kill

The direction is not BA-001's problem. BA-001's reported failure was cost drag
(15.7 bps/yr against the benchmark's 5.7) and a Sharpe 0.30 short of static, not
a signal pointing the wrong way — and this diagnostic says its direction was
actually supported by the data. That relocates the constraint: the binding
problem in this repository is **how often it trades and what that costs**, not
which family of signal it uses. Any next attempt that intends to beat plain
index ownership in *dollars* has to start from a turnover budget and work
backwards into the signal, which is the opposite of how all three so far were
built.

This is an in-sample diagnostic and it is labelled as one. It looked at conditional
moments, not at a strategy's equity path, and it scored nothing; but it did
consume a look, and it should be counted against the family's remaining
credibility rather than treated as free.
