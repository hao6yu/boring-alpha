# The forward book can actually run — and it was lying about its costs

Date: 2026-09-06 · Round 5 of the trading-model goal · tools: `tools/paper.py`, `tools/journalctl.py`
Status: **integrity fixes plus the first genuinely unseen session.** No performance claim.

## What round 5 set out to do

Round 4's closing commitment was to re-point the paper bot at the sized configuration and
start the forward record, because every table in this repository is a claim about the past.
Getting there meant proving the book could run. It could not, and then it could, and then
it turned out to have been flattering the strategy while it looked like it was running.

Four defects were found. All four pointed the same way — **toward the strategy looking
better** — which is the diagnostic that matters. A bug that hurts you gets found; a bug
that helps you gets published.

## Finding 1 — the fetcher works, so the forward record is real

`tools/fetch_market_data.py` (Yahoo chart + FRED DGS3MO, no API key, no money) ran
successfully. New immutable snapshot installed at `data/snapshots/20260906T195947Z`,
`data/current` repointed, the previous archive left untouched. 50,037 bars, one session
nobody had previously seen:

```
SPY 1993-01-29 .. 2026-09-04   8458 rows
SPY close 2026-09-03 = 773.17  ->  2026-09-04 = 770.19   (-0.385%)
```

Before adopting a re-download, the history was diffed rather than trusted:

| check | result |
|---|---|
| rows revised | 34,089 of 50,029 |
| worst relative revision, whole history | 2.03e-06 (**0.020 bps**) |
| worst revision, last 12 months | 3.47e-07 |
| largest change to any single-day SPY return | 0.020 bps |

Revisions are float noise from re-adjustment, not a restatement — the kind of thing the
content-addressed archive is for: a revised download changes the run id instead of silently
altering an existing result. One session is thin, but it is *new*, and it is the first
evidence in this repository that no backtest can contaminate.

**Plumbing rule established:** forward tools follow `data/current`; research tools stay
pinned to the archive they measured. A backtest that follows the data is not a backtest,
and a journal that cannot accept tomorrow's print is not a journal. Every sealed entry now
records which immutable snapshot it was computed from — resolved through the symlink,
because an entry saying it used "current" says nothing, `current` being the one thing here
guaranteed to change.

## Finding 2 — the book borrowed money and charged itself nothing

The pre-registered candidate asks for **128% of equity**, i.e. a 28% loan. The ledger
charged a 3 bps spread on turnover and a 9.45 bps expense ratio across all five of its
entries and **never once charged interest**. It was simulating a margin account no broker
operates.

This was not a rounding omission. Round 4 priced the same exposure honestly and found the
financing leg worth more than half the trade's entire benefit — $120,350 of interest
against $1,222,135 of gain at 1.5×. A forward book that omits it is not a conservative
version of the truth, it is a different and flattering truth.

The rate is read from the same FRED series the comparator accrues against, not hard-coded,
so the forward book and the funded simulator pay the same rate and remain comparable:

```
cash 3.82% + 150 bp spread = 5.32% borrow
entry note: "borrow 5.97 at 5.32% on 1,347 avg borrowed"
```

## Finding 3 — expense was levied on the wrong base

The expense ratio was charged against **net equity**. Funds bill against **market value**.
Those differ by exactly the leverage, and the error always favours the strategy, because a
levered book's expense is larger than its equity. At 128% the fund bills 128% of the
account's value; charging against 100% of equity understated the fee by the borrowed fifth.

Together with Finding 2 the effect compounds in one direction. Reported cost went from
**5.0 bps/yr to 17.5 bps/yr** on the same book — a 3.5× change in the cost the book
believed it was paying, from arithmetic, before any strategy changed.

## Finding 4 — a daily driver would fund five months in January

`command_step` credited `$500` on every invocation. Correct only if nobody runs it twice
in a month — a property nobody remembers in six weeks. Deposits are now gated on the
calendar month changing, so a bot driven daily funds once monthly, and a money-weighted
return stops being computed on money that was never committed.

## Finding 5 — `verify` checked the lock, not the door

The most serious one, because it corrupted the *evidence about the evidence*.

`journalctl.py verify` advertises "who edited this?" and recomputes the ledger hash chain.
It never re-checked the pinned comparator spec. I edited `comparator.json` from 9.45 bps to
1.0 bps — softening the benchmark the entire protocol exists to fix in place — and it
reported:

```
chain intact (1 entries)     [exit 0]
```

The chain was genuinely intact. That is precisely what makes it dangerous: the check was
passing honestly about the artefact nobody would bother to edit. Protection existed inside
`load_comparator()` and was reachable only from `report`, so a tampered benchmark passed
the tool whose job was to catch tampering.

Fixed: `verify` now checks both and exits non-zero on a spec edit.

```
ledger: chain intact (1 entries)
comparator: pinned spec intact (100% SPY, fee 0.000945)        exit 0

ledger: chain intact (1 entries)
comparator: comparator spec has been edited after pinning …    exit 2
```

Pinned by `tests/test_journalctl_verify.py`, including the inverse case that proves the
pin covers the canonical body rather than file formatting.

**Lesson, generalised from three rounds now:** a check must test the thing that would be
abused, not the thing that is convenient to test. Monotonicity in accuracy (round 3), a
control row that must equal the comparator exactly (round 4), and now a verify that must
check the benchmark rather than the ledger. In each case the check passed honestly and
about the wrong object.

## Ledger re-anchored, not quietly patched

Entries 1 and 2 were sealed under different rules: entry 1 with no borrow charge, entry 2
with one. That is not a forward record, it is a discontinuity with a hash chain attached.
The old ledger was archived rather than rewritten —
`data/paper/superseded/ledger-2026-09-06-pre-borrow-charges.jsonl` — and the book re-anchored
clean at 2026-09-04 against snapshot `20260906T195947Z`. Three entries carried no evidential
weight anyway (`underpowered`, 24 required), and a journal whose first entries are priced
inconsistent with its later ones forfeits the only property it has.

## Verification

Every new test was checked against the reintroduced defect, because a test that passes on
broken code is decoration:

| defect reintroduced | caught by |
|---|---|
| interest forced to zero | `test_a_levered_book_pays_interest_and_an_unlevered_one_does_not` |
| expense back on net equity | `test_expense_is_charged_against_holdings_not_equity` |
| deposit back to every step | `test_two_steps_in_one_month_take_one_deposit` |
| comparator fee softened | `test_editing_the_benchmark_fee_is_caught` (exit 2) |

Three tests, three targeted failures, no collateral. Suite: **1,158 passed, 233 subtests**
(12 new).

## What this changes about the goal

Nothing about whether the strategy works. It changes what the next answer will be worth.

Rounds 1–4 were backtests, and backtests in this repo are now demonstrably sensitive to
cost assumptions of the same size as the effects being measured — one missing interest leg
moved the book's believed cost by 3.5×. A forward record is worth exactly as much as its
accounting is honest, and until today the accounting was not.

The bot now runs the vol-target candidate at 128%, which round 4's sizing permits under the
1.5× cap, and it pays 5.32% for the privilege on the ledger it seals. The next fetch
adds a session; the next month adds a deposit; 24 entries from now there is either a skill
claim or a null result nobody can argue about. That is the only path from this repository
to the objective as stated, and it is now the first round where the path is unobstructed.

## Reproduce

```
.venv/bin/python tools/fetch_market_data.py --out /tmp/refresh   # dry run, scratch dir
.venv/bin/python tools/paper.py report
.venv/bin/python tools/journalctl.py verify ; echo "exit $?"     # 0 clean, 2 tampered
.venv/bin/python -m pytest tests/test_paper.py tests/test_journalctl_verify.py -q
```

## Next

Round 6: re-fetch to pick up the next sessions, seal the entry, and add the missing
comparator leg to the forward record — the book tracks its own value and the comparator is
computed from its quotes, but nothing yet seals the *doing-nothing* account as a parallel
ledger, so the dominance test is currently derived rather than witnessed.
