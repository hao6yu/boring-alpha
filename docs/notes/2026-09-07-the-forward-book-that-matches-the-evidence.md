# The forward book that matches the evidence

Measured 2026-09-07, round 81. Changed: [`paper.py`](../../tools/paper.py) (new `tilt` model, `posted_fee`,
`comparator_spec`, `--comparator`). New live books: `tilt`, `tilt_qqq`. Tests: 14 in
[`test_paper_tilt.py`](../../tests/test_paper_tilt.py).

Eighty rounds measured the past. The journal is the only artefact in this repository that faces forward — and it was running
the row that every recent table ranks worst for income. The root book is the `shelter` model (MA200-gated SPY, IEF below),
which rounds 78 and 80 identify as the **insurance** position: the only thing that meets a 5% failure budget over the whole
scoreable record, at roughly 0.42x the capacity. There was no book for the **income** position at all, and no book anywhere
whose witness was the fund the objective actually names: the pinned comparator is `100% SPY` at 9.45 bps, while the question
asked is "did this beat plain **VOO** or **QQQ**?"

## What is running now

| book | model | construction | witness | fee charged to the witness |
|---|---|---|---|---|
| `(root)` | `shelter` | MA200 → SPY, else IEF | 100% SPY | 0.0945% |
| `constant` | `constant` | 1.25× SPY, financed | 100% SPY | 0.0945% |
| **`tilt`** | **`tilt`** | **static 50% SPY / 50% QQQ** | **100% VOO** | **0.0300%** |
| **`tilt_qqq`** | `tilt` | static 50% SPY / 50% QQQ | **100% QQQ** | 0.2000% |

All four anchored **2026-09-04** with the same $5,000 opening and $500/mo contribution at a 3 bps spread, so they stay
comparable as accounts rather than as parameter choices (round 70's rule), and each book's benchmark comes from its own anchor
config, never from a report-time flag. Nothing was superseded: the shelter book is not wrong, it is the other position, and
round 78 said so in dollars.

The income book makes **no decision**. That is not a shrug, it is the finding: rules (r74), rotations (r75), brakes (r76),
payout levels (r77), mixes (r78) and schedules (r80) — six families, each against its own control, costs charged — none beat a
static growth tilt net of costs, so the book the evidence supports is the one that stops deciding.

## The three inconsistencies the work turned up

1. **A witness charged a fee nobody posted.** `fee_for` fills unposted sleeves with a 35 bps guess — right for a holding,
   wrong for a benchmark, because the comparator is the number the objective is scored against (round 73's rule, applied to a
   live artefact for the first time). New `posted_fee` refuses: `IEF`, `EFA`, `GLD`, `DBC` can be held and charged the
   conservative guess, and cannot witness. `--comparator IEF` exits with that reason.
2. **The config described its witness twice, in two amounts.** A top-level `expense_ratio` of 9.45 bps sat beside a
   comparator that could be any posted fund — a 6.45 bps disagreement baked into the file the journal trusts. Both fields now
   come from `comparator_spec`, and a test asserts they agree.
3. **The disclosure paired weights with the wrong fees.** `50% SPY / 50% QQQ` was printed against `0.200% / 0.095%`, charging
   the cheap fund with the expensive fee — the wrong number in the one place a reader is told what the sleeves cost. One
   ordering now drives both strings, and a test rebuilds the expected pairing from the fee table.

## What the caller may not do

`--tilt 0.70` is refused outright: *the tilt weight is not a caller's choice*. The whole reason the book exists is that 0.50
was measured rather than picked, so a command line may not pick it. `paper.TILT_WEIGHT` is duplicated by value — the file's
stated convention for live parameters, deliberately not importing a research tool into the journal — and pinned by test to
`mix_sweep.MIXES`'s control row, so moving one without the other fails a test rather than passing a review (round 73's
discipline, applied to the live artefact rather than to a report).

And the book still refuses to be impatient, which is the point of it: `step` says *"book is already closed at 2026-09-04;
nothing new to seal"*, and `report` prints

```
skill: underpowered — 23 more monthly entries, $5,000 more paid in required before a skill claim
LEVEL with doing-nothing by $0.00   [level at the anchor, nothing measured yet]
```

That line is the answer to the question behind the objective — *how long until we know?* Roughly **two more years of monthly
seals**, on a $5,000 book with $500 arriving each month, before this journal is entitled to claim skill against VOO. Not my
estimate: the tool's own power arithmetic, printed rather than paraphrased. A tie at the anchor is rendered as level, not as
a win and not as a loss, because a verdict before an interval has elapsed is a verdict about nothing.

## What this book cannot do for the objective

It cannot detect a regime the tools did not measure; it holds one balance and its forward record can only **falsify** a
backtest, never rescue one. It answers questions about a $5,000 account, and every capacity figure elsewhere in this repository
is per $100,000 — the shapes carry, the dollars do not. And it does not make the refused asks purchasable: intraday, spread
awareness and a news veto are still refused by [`decision_sheet.py`](../../decision_sheet.py) with the missing data named, and
a paper book is not that data.

What it does do is put the objective's own question — the model versus plain VOO, versus plain QQQ, same deposits, same dates,
fees each fund actually pays — inside an append-only chain that will answer it whether or not anyone is watching.

## Checks

14 new tests, 0.2 s, and all 55 pre-existing paper tests unchanged: the tilt weight asserted against `mix_sweep`'s control row
(with an assertion that the control has no brake, so the live book cannot quietly grow one); weights sum to 1.0 with no
borrowing in the tilt; `--tilt` refused before any book is touched; the name's fee pairing rebuilt from the fee table;
`posted_fee` refusing all four unposted candidates while `FEES` still carries their guess; every posted fund able to witness at
its own fee; the two config fields describing a witness agreeing; both income books sharing fees, sleeves, opening, monthly and
spread while differing only in witness; every book on disk anchored the same day with its witness starting at the same cash;
and no book allowed to render a verdict at one entry. Suite: **2051 passed** (collected first: 2037 + 14); ledger chain intact.
