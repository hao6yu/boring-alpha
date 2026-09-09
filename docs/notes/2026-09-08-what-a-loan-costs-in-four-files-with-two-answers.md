# What a loan costs, in four files, with two answers — and the audit that now re-prices the prices

Round 104. Added [`cost_conventions.py`](../../tools/cost_conventions.py) and
[`test_cost_conventions.py`](../../tests/test_cost_conventions.py) (13 tests); patched
[`withdrawal_capacity.py`](../../tools/withdrawal_capacity.py), [`run_voltarget_scan.py`](../../tools/run_voltarget_scan.py),
[`leverage_sizing.py`](../../tools/leverage_sizing.py), [`funded_policy.py`](../../tools/funded_policy.py),
[`rebalance_cost.py`](../../tools/rebalance_cost.py), [`fund_fees.py`](../../tools/fund_fees.py),
[`sleeve_table.py`](../../tools/sleeve_table.py); widened the fee-copy scan in
[`test_fund_fees.py`](../../tests/test_fund_fees.py) 19→20; corrected [round 103's note](2026-09-08-the-fifth-file-that-guessed-and-the-footer-that-said-it-had-not.md).

## The fact round 30 fixed and two research files never learned

`paper.py` carries the loan price for the forward engine, with provenance:

> *Round 30 measured a real all-in desk spread near this; the first version of this constant was 150 bps and it was raised, at a
> re-init, to what the posted desk quotes.* — `paper.BORROW_SPREAD = 0.0202`

`withdrawal_capacity.BORROW_SPREAD` was **0.015**. `run_voltarget_scan.BORROW_SPREAD` was **0.015**. The research family that decides
whether leverage pays had been pricing loans at the value the chain rejected twenty-four rounds ago — **52 bps of flattery on every
levered study in the repository**, in the direction that makes borrowing look cheap. That is round 103's finding one layer down: round 94
sourced the *expense ratios*, and nobody re-looked at the *carry*.

Both constants now read `paper.BORROW_SPREAD`. Measured effect, at the desk quote instead of the stale one:

```
ITOT   candidate      1.06      11    $671 → $668/mo safe   11/11 starts pay more, worst start +56   verdict unchanged
```

Three dollars a month on the withdrawal capacity, no verdict moved — and the correction still had to happen, because the number that
decides "should this book carry 1.06×" was set by an assumption nobody was allowed to change mid-chain, and the studies were not in the
chain. The same fingerprint showed up on QQQ's guarantee frontier in `income_accounting`, where the pin had to move with it:

```
lever          1.00      1.25      1.50      1.75      2.00
was          171.09    113.75     69.00     40.00     20.00
now          171.09    112.50     67.50     38.75     20.00
```

Nothing moves at 1.0×, every borrowed rung moves down by about a percent, and the top of the grid is unchanged to the cent — the
signature of a loan price rather than a market revision. The test that pinned 113.75 now pins 112.50, with the old figure left in the
line as the price it was measured at (r96: a published figure is a claim until a command can reprint it, including in a test).

## The tool, and what else it turned up

`cost_conventions.py` prints the inventory (every trading-cost constant in `tools/`, at file:line, normalised to bps per side or dollars
per ticket), the duplication, the *prose* figures, and then re-runs the rule-ranking battery at every one-way cost the tools quote:

* **Ticket costs in two names:** `power_horizon.COMMISSIONS = (0.0, 4.95, 9.95)` and `rebalance_cost.COMMISSIONS = (0.0, 4.95, 9.95)` —
  agreeing copies — plus `rebalance_cost.TICKET = 9.95`, the last element of the tuple above it spelled out a second time.
* **`EXPENSE = 0.000945`** in `run_voltarget_scan.py`: SPY's posted ratio under a name round 94's `_ER` scan could never see. Now
  `fund_fees.fee_for("SPY")`, and the copy scan matches any fee-named constant holding a bare ratio (allow-list in the test, so a legitimate
  assumption has to declare itself to survive: one entry, the leveraged-fund ratio).
* **The same leveraged-fund assumption typed twice:** `leverage_sizing.ETF_EXPENSE` and `withdrawal_capacity.WRAPPER_EXPENSE`. One literal
  now, in the file that stated it first.
* **31 cost figures typed into prose.** The stale ones were fixed rather than catalogued: two prints of *"cash + 150 bps"* (the rejected
  quote, still in the labels readers see), `funded_policy`'s *"2.0 bps per unit turnover"* (now `wc.TURNOVER_COST`), `rebalance_cost`'s
  *"monthly, 3 bps"* regime label (now `f"monthly, {SPREAD:.0f} bps"`), `fund_fees`'s *"DBC alone is 49 bps"* and `sleeve_table`'s
  *"SPY's path at 3 bps"*, both interpolated now.
* **A runner that had been dead for rounds.** Plain `run_voltarget_scan.py` printed a DO NOTHING line, then died on `NameError: rows` —
  the `rows = []` and its policy grid had been removed at some point while `rows.sort()` stayed, and the wide-scan code sat unreachable
  under a `continue`. Its `--candidate` path is intact and exits 0; the dead path now refuses with the true reason instead of half-running,
  and the test pins both.

## The fork that remains, measured instead of noted

Two one-way costs coexist by design: 2 bps (`withdrawal_capacity.TURNOVER_COST`, plain sleeves in the withdrawal family) and 3 bps
(`paper.SPREAD_BPS`, the forward engine and everything priced through it). The runbook prints numbers from both families on one page, so
the question is not which is right but whether anything crosses the fork. Re-run at 0, 2, 3 and 25 bps a side:

```
    at  0.0 bps a side  2 rules pass (blend_sq, qqq_only)  control gap: dm12_sq $89.72
    at  2.0 bps a side  2 rules pass (blend_sq, qqq_only)  control gap: dm12_sq $92.94
    at  3.0 bps a side  2 rules pass (blend_sq, qqq_only)  control gap: dm12_sq $94.55
    at 25.0 bps a side  2 rules pass (blend_sq, qqq_only)  control gap: dm12_sq $130.05
```

Between the two conventions the archive actually uses, the figure moves **$1.61 a month**; across the whole ladder, **$40.33**. No verdict
moves at any rung, and that is the measurement that lets a rotation row sit beside a tilt row. The tool exits 1 if a same-named cost ever
has two answers again, or if a verdict does start depending on the convention — and its first draft printed *"widest move $0.00"* under
exactly that sentence, because it computed the spread inside each run instead of across them. A check that measures the wrong thing agrees
with everything, which is r92 wearing a formula.

## The other correction, against this round's own predecessor

Round 103's note claimed the control gap was unchanged by its fee fix. It had moved by **$1.41**: the before/after diff was capped at six
entries per rule, numbers filled the cap, and the verdict strings carrying the gap never printed. The amended note says so. Restated:
verdicts and pass sets unchanged, every dollar figure on that page moved by up to $3.17, the gap by $1.41 — and a truncated diff is not an
all-clear outside the truncation.

## Checks

**2330 passed, 239 subtests** (2316 + 1 widened fee-copy scan + 13 new; collected count printed before the run). Neighbours green:
`test_leverage_sizing`, `test_fund_fees`, `test_cost_conventions`. Live state unchanged: five books, one anchor entry each, sealed fees
$0.00, first seal 2026-09-30.

*Round 104. 104 standing rules. The reader of a table cannot see the constants underneath it, so the constants now have to print
themselves — with the price of a loan wrong in two files, the wide-scan runner long dead, and the fork between two honest conventions worth
$1.61 a month of measured peace.*
