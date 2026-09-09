# The benchmark is now witnessed, not inferred — and it is already losing

Date: 2026-09-06 · Round 6 of the trading-model goal · tool: `tools/paper.py`
Status: **structural, plus the first measurement of the candidate against a witnessed
benchmark.** No skill claim; the book has one interval of history.

## Why this round, given round 5's plan

Round 5 committed to two things: seal the next entry, and make the dominance test
witnessed rather than derived. The first is blocked by the calendar — the archive ends
2026-09-04, a Friday, and today is Sunday, so there is no new session to seal and
pretending otherwise would be the same sin as back-filling. The second was the real gap,
and it turned out to be the more important one.

## The gap: the graded party was computing its own benchmark

`comparator_return` recomputes doing-nothing from the strategy's own quotes. That number
is reproducible, so it is not *weak* — but it is produced by the code under evaluation,
from that code's own data, and the P0 dominance rule is the single claim in this repository
that must not rest on the graded party's arithmetic.

So the comparator now has **its own append-only hash-chained ledger**
(`data/paper/shadow.jsonl`), sealed in the same breath as the strategy entry, priced from
identical quotes and identical deposits, and carrying the strategy entry's hash in its own
sealed note. Two accounts, two chains, one price source. Dominance is now something the
journal witnessed.

That back-reference is not decoration. Without it the two chains could be rewritten
independently and re-paired at report time — a benchmark swapped after the fact while every
individual hash stays valid.

## Costs must be symmetric, and the first version was not

Two bugs in the shadow account, found because the test suite was written to be falsifiable
rather than to pass:

**1. The expense ratio was charged to a cash line already at zero.** An always-fully-invested
account has no cash to take a fee from, so the debit produced a small negative balance on an
account that has never borrowed anything — and a `max(0.0, cash)` then hid it. That clamp
does not just conceal, it *forgives*: the fee is computed, reported in the note, and removed
from the closing value. The benchmark gets cheaper and every strategy in front of it gains.

Fixed by paying the fee in units, which is how a fund actually bills it — expense is eroded
out of NAV.

The test for this cannot look at a single run, because the clamp makes the closing value
clean. It runs the identical book twice, once with the fund's real expense ratio and once
with zero, and asserts the fee-paying book ends lower:

```
test_the_expense_ratio_actually_bites_the_benchmark
  → reintroducing the clamp+debit: FAILED (with_fee == without_fee)
```

**2. The benchmark's fee was a literal at a call site**, which means someone could make the
benchmark cheaper without touching the pinned comparator spec — a rig whose direction
advances strategies that should not be advanced. Now the comparator is built from the pinned
config, and `test_the_benchmark_pays_the_same_expense_ratio_as_the_strategy` recomputes the
implied ratio from the sealed note and asserts it equals the strategy's.

## The vacuous-test catch, recorded because it is the second time

The first draft of these twelve tests **passed against both defects deliberately
reintroduced**. Not one of them noticed a fee being computed, reported, and then forgiven,
and not one noticed the benchmark being priced ten times cheaper than the strategy it judges
— because a `less(strategy, benchmark)` assertion still holds when the benchmark gets
friendlier, and because `max(0.0, cash)` makes every closing-value check clean.

Twelve green tests were telling me nothing. This is round 3's lesson in a new costume: a
check that passes about the wrong object is worse than no check, because it manufactures
evidence of scrutiny that never happened. Every test in this file was then re-run against
the reintroduced defect, and each defect now fails exactly the test written for it:

| defect reintroduced | caught by |
|---|---|
| expense → cash + `max(0.0, …)` clamp | `test_the_expense_ratio_actually_bites_the_benchmark` |
| benchmark fee divided by 10 | `test_the_benchmark_pays_the_same_expense_ratio_as_the_strategy` |

Suite: **1,170 passed, 233 subtests**, up from 1,158.

## What the witness says so far

The candidate is run over five sealed intervals (anchor 2024-01-31 through 2024-05-31)
against its own benchmark, same deposits, same quotes, both chains hashed
(`.venv/bin/python` scratch harness, `PAPER_DIR` redirected to a temp directory):

| | strategy | doing-nothing |
|---|---|---|
| ending value | $6,973.53 | $6,996.02 |
| fees paid | $26.47 | $3.98 |

```
sealed entry 1  2024-02-29  $5,494.31   witness $5,497.92  gap    -3.61
sealed entry 2  2024-03-28  $5,987.75   witness $5,997.35  gap    -9.60
sealed entry 3  2024-04-30  $6,481.85   witness $6,496.62  gap   -14.77
sealed entry 4  2024-05-31  $6,973.53   witness $6,996.02  gap   -22.49
```

**Behind by $22.49 on $7,000 paid in, paying 6.7× the benchmark's fees, and the gap
widens every single month** (−3.61, −9.60, −14.77, −22.49) because it is fee-driven, not
market-driven.

The sealed notes say where the money went. Over the four intervals the book paid
**$21.68 in interest, $2.41 in spread, $2.36 in expense ratio** — 82% of its cost is the
loan, at 6.89–6.99% (archive cash index plus the 150 bps spread, read from the data, not
assumed), on $554–$1,305 average borrowed. The benchmark's split, from its own sealed
notes: $2.02 of spread, $1.65 of it the one-time cost of putting the $5,000 opening cash to
work, plus $1.97 of expense ratio running $0.43–$0.55 a month, against the book's
$5.69–$8.32. It pays no interest because it owns no loan.

The tool's own convention puts the book at 45.7 bps/yr on a $5,790 average balance, roughly
10 for the benchmark. That ratio is *flattered by the small size* — it includes the anchor
month, when the book was still ramping. At the 1.28× the candidate actually asks for, the
interest term alone is 0.28 × 6.9% ≈ 190 bps of equity per year, and unlike spread and
expense it is proportional to equity rather than to turnover, so it does not amortise as the
account grows. The benchmark's cost stays where it is.

That is a simulation over four intervals on a book that has not yet run, and it is not a
verdict — the gate is 24 entries and $10,000 paid in. But it is the same conclusion the
backtests reached from the opposite direction, now arriving through a path that cannot be
argued with: **the levered, trading book's costs are its whole story at this size.** Round 4
measured the same thing at scale and found the honest answer was that leverage — not a
signal — is what beats DCA, and that financing cost is worth more than half the trade.

## Harness discipline worth keeping

The older `test_paper.py` suite broke loudly when the shadow path appeared: its scratch
harness redirected three paths and not the fourth, so `init` found the repo's real shadow
ledger and refused. That is the good failure mode. A harness that silently *shared*
production state would have passed against it, which is how a test suite becomes theatre.
All four paths are now redirected, with a comment saying why.

## Also this round

- `command_init` refuses unless **both** chains are absent: they advance together, so
  neither may be removed alone.
- A tie is no longer labelled `DOMINATED`. The anchor printed "BEHIND … [DOMINATED]" at
  $0.00 gap, which put a verdict on the ledger before any interval had elapsed — the exact
  habit this journal exists to break. Now: `LEVEL … level at the anchor, nothing measured yet`.
- The shadow's fee breakdown moved to `key=value` form. Prose that a test has to split on
  the word "expense" will eventually be parsed wrong and the wrong number will look
  plausible; the anchor-entry parse failure caught this the same afternoon.
- Real book re-anchored with both chains starting together; the pre-shadow ledger archived
  at `data/paper/superseded/ledger-2026-09-06-pre-shadow.jsonl` and excluded from any
  Layer 2 claim, per the protocol's §7 rule about mixing accountings.

## Reproduce

The real book, and the tests written against the two defects:

```
.venv/bin/python tools/paper.py report           # witnessed dominance block
.venv/bin/python -m pytest tests/test_paper_shadow.py tests/test_paper.py -q
```

The five-interval demonstration above runs the same code against a temp book, never the
repo's (its `PAPER_DIR` is the only mutable state, so one assignment isolates it). It
truncates the archive at each month-end — the same `end=` argument `init` uses, so no
interval can see a later close — and calls the ordinary `command_init`/`command_step`:

```python
tmp = pathlib.Path(tempfile.mkdtemp())
paper.PAPER_DIR, paper.LEDGER, paper.SHADOW, paper.CONFIG = (
    tmp, tmp/"ledger.jsonl", tmp/"shadow.jsonl", tmp/"model.json")
real, state = paper.load_data, {"cut": None}
paper.load_data = lambda asof=None: real(state["cut"])
for cut in [date(2024,1,31), date(2024,2,29), date(2024,3,29),
            date(2024,4,30), date(2024,5,31)]:
    state["cut"] = cut
    paper.command_step(None) if state["cut"] != date(2024,1,31) else (
        paper.command_init(argparse.Namespace(model="voltarget", asof=cut)))
paper.command_report(None)
```

## Next

Round 7: Monday's session lets a real entry seal against a witnessed benchmark for the first
time. The structural work is done — after that the journal's value is a function of how many
months it is left alone for, and the honest forecast in §5 of the protocol (P1–P4) is what
gets tested, not a new backtest. The one remaining structural weakness worth naming: the
shadow chain reproduces the *buy-on-arrival* convention by hand rather than sharing the
funded simulator's code path, so the two implementations could drift. Either unify them or
add a cross-implementation agreement check.

What this round does **not** change: nothing here makes the candidate earn money. It makes
the question answerable without taking anyone's word for it, and the first answer it gives
is that a 1.28× book financed at cash + 150 bps starts roughly two percentage points a year
behind a person who does nothing at all, and has to out-earn that every month to be worth
having.

Two named next actions, both cheap and neither a new backtest:

1. **The benchmark the goal actually names has never been in the archive.** The objective is
   stated as beating VOO and QQQ; the archive carries neither, so every sentence in this
   repository about beating QQQ has been a sentence about SPY wearing a borrowed name. VOO
   is SPY under a different ticker and the substitution is honest. QQQ is not a proxy for
   anything here — it is a different risk, a different financing cost at any leverage, and
   the sleeve most likely to make the levered case. `tools/fetch_market_data.py` line 93 is
   the whole change, and it costs no money.
2. **Nobody has tested whether the plan pays a withdrawal.** Round 4's "+$346 a month" is an
   accrual on a paper equity line that spends 71% of its height underwater, not cash someone
   could take out. The goal is a monthly amount, so the next simulation worth writing is one
   that draws a fixed sum every month and reports whether the book survives to month 60. If
   it does not, the leverage number is wrong regardless of what it accrues.
