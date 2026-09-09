# Forward journal protocol — what "worked" means, fixed before it runs

Date pinned: 2026-09-06. Status: **written before the first fill.** No entry in
the ledger contains money.

Module `src/boring_alpha/journal.py`. CLI `tools/journalctl.py`. Tests
`tests/test_journal.py` (27). Ledger `data/journal/ledger.jsonl`, append-only,
hash-chained. Comparator spec `data/journal/comparator.json`.

**Comparator protocol hash:**

```
3eb35b246b402361103f01fa5931b5cc085581b376667841e6460117abc2f394
```

which decodes to `100% SPY, expense ratio 0.0945%`, anchored at 2026-09-03 off
snapshot `20260904T192633Z`.

---

## 1. Why this exists and not another strategy

Four evaluations of the trend family, and a fifth idea killed on a diagnostic,
all against prices that have been public for decades. The archive runs to
2026-09-03, and a BA-001 sweep already ran an equity path to 2025-12-31, so
2022-onward is **not** a clean holdout. There is no clean history left to spend.

A ledger is the only instrument that produces dates nobody has looked at. It
cannot be accelerated, which is the problem with it, and it is the only thing
here that can eventually answer "did you beat the index" with evidence rather
than a simulation of the index.

It also exists because of a specific defect found in BA-004. That charter scored
a no-signal vehicle against the fund it holds, so it could not fail — and it did
not fail, while losing **$5,700 to doing nothing** on the same schedule. The
benchmark was chosen to be the thing being tested. This journal inverts that:
the benchmark is computed from the journal's own recorded prices, and the
benchmark is pinned in this document before the first entry containing money.

## 2. The comparator, and why it is one number

`100% SPY, 0.0945%, zero commission`, one line, no menu. Same cash, same dates,
same prices, no decisions. Zero commission is generous to it by construction, so
losing to it can never be blamed on a modelled cost.

It is a single pinned thing on purpose. A comparator *set* is a winner-selection
machine: on the same schedule in the same archive, the eight funds available run
from **$49,857** to **$140,155** on $68,000 paid in. Given that spread, anyone
offered five comparators will find one they beat, and that number means nothing.

**Re-pin rule.** The archived series is SPY. If the real holding turns out to be
a cheaper vehicle — VTI or ITOT at 3 bps — that makes the bar *easier* by 6.45
bps of the 9.45, and the comparator must be re-pinned in writing, dated, **before
the first fill**, with the reason recorded here. Changing it after a result is
seen is the failure this document exists to prevent, and `journalctl.py report`
will refuse on a hash mismatch rather than trust an edited file.

## 3. Two verdicts, and only one of them needs the future

**Layer 1 — measured, decisive from entry one.** Fees charged, dollar-days of
uninvested cash, declared violations, days from deposit to invest. These are not
estimates and no confidence interval attaches to them. A $10 monthly fee on a
$5,000 account is roughly 2.4%/yr, which is 80× the 30 bps gate BA-004 argued
over; that conclusion is available in month one and does not care what markets did.

**Layer 2 — inferred, gated.** Money-weighted return of the real account against
the comparator, same flows. `verdict()` refuses to compute it before **24
entries** and **$10,000 paid in**, and prints what is missing rather than a
number. A shortfall in basis points from six months of a small account is
rounding wearing a costume, and the code is written so it cannot be coerced into
producing one early.

Both thresholds are in the module as named constants, overridable — the override
exists for testing, and using it to obtain a real verdict early would be visible
in the invocation and is a violation to be declared, not a shortcut.

## 4. What "worked" means

**Worked** = Layer 2 renders, and the account's money-weighted return exceeds the
comparator's by more than **+30 bps/yr**, with **zero declared violations** across
the whole period. Not "outperformed in some months". Not "lower drawdown". Not
"tracked well". The violation condition is not decoration: a strategy that beats
its benchmark because the holder broke the rules has produced a measurement of
the holder's reflexes, not of the plan, and BA-004 already established that a
violation voids a period as evidence.

**Did not work** = the shortfall is zero or negative at 24 entries, on any
instrument, at any scale. In which case the correct response is to keep the
comparator and delete the strategy, which is exactly what was done to BA-004 and
what was not done to BA-001, BA-002 and BA-003.

**Underpowered** = 24 entries not reached. This is not a failure and not a
success; it is the honest state of the evidence, and it is the state this journal
starts in.

## 5. Ex-ante predictions, so this document can be wrong

Recorded before any entry carries money. Being wrong here is the point.

- **P1.** Layer 1 will report at least one finding in the first three entries,
  almost certainly fees or delay rather than violations. If three clean entries
  come out clean, suspect the recording, not the discipline.
- **P2.** Over the first twelve entries the account will **lose** to the
  comparator. Prior: the deposit-to-invest delay alone was measured at 8–45 bps
  for a ten-day lag, and there is no mechanism in a hold-forever plan that adds
  return. A win in year one would be luck or a bookkeeping error, in that order.
- **P3.** At 24 entries the account will most likely still be classified **did
  not work**, and the reason will be a fixed-dollar fee or carried cash, not
  instrument choice.
- **P4.** At least one violation will be declared — a skipped month, a plan
  written after the fact, or an unplanned sell. The journal's value is
  proportional to how often it catches this, not to how good the numbers look.

## 6. What this cannot do

It cannot manufacture a large sample quickly; 24 entries is two years and that is
the floor, not the target. It cannot say anything about *why* a shortfall
happened — Layer 1 names costs, Layer 2 gives one signed number, and the space
between them is where honest ambiguity lives. It cannot be run retrospectively:
back-filling entries from statements is a backtest with extra steps, and if
back-filled it must be labelled as such and excluded from any Layer 2 claim.

It also cannot rescue the arithmetic of the account size. A +30 bps claim on
$12,000 is about $36 a year. That is the price of admission for the experiment,
not a plan for earning. If the pile grows, the claim gets more meaningful at the
same effort, which is the real reason it is worth starting now rather than later.

## 7. Amendment, 2026-09-06 — financing, cadence, and what `verify` checks

Recorded here rather than in a commit message, because this document is the thing
the journal's credibility rests on. Three rules bind the book from this date, all
introduced after the comparator hash above was pinned. **The hash itself is
unchanged** (`3eb35b24…`, still verified by `journalctl.py verify`): what changed
is what the book charges itself, not what it is measured against.

1. **A negative cash line pays interest.** The pinned candidate targets 128% of
   equity, so the book carries a loan; until this date it carried that loan at
   zero. The rate is the archive's own cash index plus 150 bps, read from the data
   and recorded in every entry's sealed note, currently 5.32%. The comparator is
   unlevered and pays none, so the levered book is charged for being levered.
2. **Expense is charged on fund market value, not net equity.** They differ by the
   leverage, and the difference always favours a levered strategy.
3. **The monthly deposit is gated on the calendar month.** A daily driver must not
   fund five months in January.

`verify` additionally re-checks the pinned comparator spec and exits non-zero if it
has been edited. Until this date it checked only the ledger chain, so a softened
benchmark passed the tool whose stated job was to catch that edit. The pin was
never broken; the check did not cover it.

Bookkeeping: the ledger sealed before this amendment is archived under
`data/paper/superseded/` and excluded from any Layer 2 claim — entries 1–2 were
priced without financing, so including them would average two different accountings
into one number. The book re-anchored at 2026-09-04 against snapshot
`20260906T195947Z`, which every subsequent entry names in its own hash.
