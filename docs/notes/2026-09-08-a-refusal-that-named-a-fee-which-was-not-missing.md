# A refusal that named a fee which was not missing, and the published law it was protecting

Round 102. Changed: [`correction_table.py`](../../tools/correction_table.py) (the gate asks the fee table),
[`sleeve_table.py`](../../tools/sleeve_table.py) (sweep 5→8, `UNPOSTED` → `REFUSED` with reasons, the closing prose derived, the
zero-tie verdict), [`test_sleeve_table.py`](../../tests/test_sleeve_table.py) 15→18, [`withdrawal_capacity.py`](../../tools/withdrawal_capacity.py)
and [`the-premium-belongs-to-the-window.md`](2026-09-07-the-premium-belongs-to-the-window.md) (dangling pointers, one amendment).

## The lie was in a message, not a number

`sleeve_table.py` printed this, every time it ran, since before round 94:

```
  not measured: IWM, EFA, EEM — the file carries no posted expense ratio for them, and a fee invented here would be round 69's
  error repeated.
```

Round 94 sourced all twelve ratios. The sentence stayed. Underneath it, `correction_table.measure` enforced the same thing as code —
`if sleeve not in wc.EXPENSE`, borrowed from `withdrawal_capacity`'s deliberately short *publication* list — and raised
`KeyError: IWM carries no posted expense ratio in the archive`. Two files, one message, one round out of date, and the message was the
kind that stops an investigation: it names a missing input, so the next reader goes looking for a fee table and finds the fee. That is
why r92's rule is written the way it is — a refusal must name the thing actually missing, or it is not a refusal but a misdirection.

The gate now asks `fund_fees` what `fund_fees` knows, and refuses only what is genuinely unpriced:

```
XLU has no ratio in `fund_fees.py`; measure it at a labelled flat fee or not at all
```

## The expansion was not free, and it bought the round's finding

`sleeve_table` had refused those three legs for four rounds with a reason that had evaporated, so they were swept. 24 real rows instead
of 15, runtime 8 s → 13 s. Round 67's insurance law — *a hedge is worth what the thing it hedges costs when it fails*, promoted in round
73 "from a sentence in a note to a column in a table", and pinned by a test asserting the equivalence on every row — **is false**:

```
  It breaks on 4 row(s), and not by rounding:
    IWM    panel  fund failed  8.7% of windows  delta   -300.47  out of equities 30.6% of days
    IWM      own  fund failed  7.1% of windows  delta   -266.00  out of equities 30.6% of days
    EFA   recent  fund failed 58.7% of windows  delta   -236.77  out of equities 27.8% of days
    EEM      own  fund failed 74.3% of windows  delta    -10.71  out of equities 32.3% of days
  (and 2 row(s) where neither arm could fund a dollar at all — a tie at zero is not a premium)
```

A fund can fail 8.7% of its windows and still be worth more uninsured. A fund can fail 74.3% of them and be worth insuring for $10.71 a
month, which is under the decision bar and so is not a counterexample to the *decision* — the tie-at-zero rows are now counted separately
and labelled `neither arm could fund a dollar`, because a 0.00-vs-0.00 row previously reported as "loses to the fund itself" was a verdict
on nothing. What does sort the rows, on the eleven whose record really contains the failure decade **and** whose fund really did fail: the
**duty** column, cleanly — every shelter that paid was out of equities at most 28.2% of days, every one that lost at least 30.6%, 2.4
points of separation. A shelter that whipsaws pays for its insurance twice. The small-cap sleeve is the warning: IWM's fund failed the
windows *and* the hedge cost $300 a month.

The report derives all of that from the rows each time it prints, including the separation claim, and prints the honest alternative when
the separation fails (it did, first time, until the comparison was narrowed to the law's own domain — QQQ's fund never failed and its
hedge lost, which is the law *working*, not breaking). The old paragraph's typed counts ("all five funds", "none of the four US equity
sleeves ever failed a window, so all four lose") are gone: they were round 100's disease in a tool's own prose.

## Tests, and what was refused rather than expanded

Round 94's decision to keep `withdrawal_capacity`'s five-fund withdrawal table stands — expanding it re-publishes every row of a
different study, and that is a scope choice with its own findings, not a fee lookup; its comment now says so and points at
`sleeve_table.REFUSED` instead of a constant that has been deleted. The equivalence test was narrowed to the five sleeves the law was
fitted from — **it may not be quietly rewritten backwards either** — and three tests were added: the material counterexample set pinned
by name and size, the sheet required to print its own refutation (`"is not an equivalence"`) rather than crash on it, and a repository-wide
scan that fails if any tool announces a priced leg as unpriced (it scans ±400 characters around the phrase, so the true refusal about XLU
still passes). The refusal dictionary is checked for *auditable silence*: every one of the twelve priced legs is either swept or refused
with a printed reason over twenty characters long, because a table that silently omits a fund is a table whose omissions are opinions.

## Checks

**2312 passed, 239 subtests** (18 tests in `test_sleeve_table.py`, up from 15, none lost — counted before and after, per r94). Neighbour
suites re-run green: `test_correction_table`, `test_withdrawal_capacity`, `test_fund_fees`, `test_runbook` (76 tests). Live state
unchanged: five books, one anchor each, all chains verify, sealed fees $0.00, first seal 2026-09-30.

*Round 102. 102 standing rules. Two files had been telling the operator a fee was missing when the fee had been on the table for eight
rounds; fixing the sentence cost a published law, and the law deserved to lose.*
