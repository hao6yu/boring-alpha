# BA-001 global-equity diagnostic: recorded as unavailable

Date: 2026-09-04
Resolves: the charter checklist item "Global-equity diagnostic sourced, or
recorded as unavailable."
Status: **unavailable.** Non-gating, so this does not block evaluation.

## What the charter requires

Charter revision 4 preregisters benchmark 4 as **MSCI ACWI Net Total Return
USD**, close-to-close, reported as a non-gating global-equity diagnostic, and
instructs:

> If a legally usable and reproducible daily series cannot be archived, report
> the benchmark as unavailable rather than substitute an ETF or synthetic proxy.

That clause exists because the substitution is tempting and would be wrong. No
global-equity fund spans the development period — VT lists June 2008, ACWI
March 2008 — while the index itself carries a December 2000 base date. Swapping
in a fund would shorten the comparison; blending one would be a proxy chosen
after seeing which proxies were available.

## What I found

MSCI's own historical index data requires a subscription; the public factsheets
give periodic levels, not an archivable daily series. Third-party aggregators do
carry the daily net-return series, but redistributing MSCI index values is
generally licensed, and I could not establish that any freely accessible copy is
legally usable for archiving inside this repository.

**I am not able to resolve the licensing question, and I have not tried to.**
That is a determination for the account holder, not for me to infer from a
vendor's public pages.

## Decision

Report the global-equity diagnostic as **unavailable** for now. Every sweep and
review through the development and validation periods should say so explicitly
rather than omit the row, so a later reader knows the benchmark was preregistered
and deliberately not substituted.

## How to resolve it later

Sourcing the series does not require a charter change; it is the same benchmark,
now obtainable. It would need:

1. A licensed daily series of MSCI ACWI Net Total Return USD covering at least
   2006-01 onward, so it spans the development warm-up.
2. Archiving under the same snapshot discipline as prices and cash: a dated
   directory whose `manifest.json` is written last, with a methodology
   identifier that enters `strategy_spec_sha256`.
3. A benchmark policy in the harness that consumes it, reported alongside cash,
   static, and exposure-matched.

Likely sources worth checking, in rough order of practicality: a brokerage or
data subscription the account already holds; a licensed vendor such as
Bloomberg, Refinitiv, or FactSet; or MSCI directly.

## Why not just use a fund anyway

Because the difference is not cosmetic. A fund's returns include its expense
ratio, tracking error, and the currency and tax treatment of its own domicile,
and the two candidates miss the first eighteen months of the development period
entirely. Reporting one under the name "global equity buy-and-hold" would state
something the data does not support, which is the failure mode this laboratory
is built to prevent.
