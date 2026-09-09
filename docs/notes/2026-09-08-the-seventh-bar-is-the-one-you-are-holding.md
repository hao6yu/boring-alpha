# The seventh bar is the one the reader is already holding, and the fee table had been lying about it

Round 99. Changed: [`fund_fees.py`](../../tools/fund_fees.py) (two cash legs, `priced()` separated from `RATIOS`),
[`paper.py`](../../tools/paper.py) (`posted_fee` distinguishes priced from traded), [`cash_yield_gap.py`](../../tools/cash_yield_gap.py)
(imports its two ratios instead of restating them), [`power_horizon.py`](../../tools/power_horizon.py) (`cash_bar`, a seventh row),
tests: [`test_power_horizon.py`](../../tests/test_power_horizon.py) 25→28, [`test_fund_fees.py`](../../tests/test_fund_fees.py) 11→17,
[`test_forward_p0.py`](../../tests/test_forward_p0.py) 34→35.

## A table of bets with no do-nothing option in it is an argument

Rounds 96 and 97 put the objective's own comparison behind a command, and the table was still missing the alternative every reader is
literally holding while they decide: cash. So the printed block gained a seventh row — T-bills at the archive's own curve, charged
SGOV's ratio pro rata on sessions and the journal's 3 bps spread on every transfer in, on the funds' calendar to the day:

```
    plain VOO, the standing bar          closed at $    7,853,675   worst hole -22.0%
    plain QQQ, the free version of the same bet closed at $   12,216,556   worst hole -31.3%
    the tilt, never rebalanced           closed at $    9,988,324   worst hole -27.6%
    T-bills, charged SGOV's ratio        closed at $    2,447,542   worst hole 0.0%   its own ratio 0.09%
```

$2,020,000 paid in became $2,447,542, which is **+21.2% of paid in over sixteen years** — the honest number for the safest thing the
archive can price. Over the last five years bills kept **71%** of the standing bar's terminal ($795,912 against $1,118,151) with a hole
of 0.0% instead of -4.1%: the 2022 drawdown was not deep enough, or the cash rate not low enough, for the risk-free bar to win. The row
prints its own ratio so nobody reads it as a free option; what a bank sweep actually pays (0.02%) is a different question owned by
`cash_yield_gap.py`, and the printed line says so rather than importing that fight.

The accrual is the product of the **daily** factors between two consecutive month keys, not a monthly rate. That is round 47's defect
named and obeyed: the archive's last month is a four-session stub, and annualising it reported the curve 93 bps low. Interval compounding
is exact on a stub and on a full month, and it means the bill row shares the other six rows' deposit schedule, so the paid-in column stays
identical and the comparison stays a comparison.

## Two engines, one curve, zero basis points apart

The row is a new construction, so it was checked against the file that already owns the curve. `cash_yield_gap.bill()["last10y"]`
annualises the mean of the last 120 complete monthly factors; the new bar accrues the same sessions a different way. Over months
-121…-2 the two readings are **2.4523% and 2.4523%** — 0.0 bps apart (the test allows 30). Two constructions of one curve agreeing to a
basis point is the shape of evidence this repository trusts: not a fixture that asserts what its author expected, and not a self-report,
but a second engine meeting the first (r93).

## And the fee table had been lying about the bill fund by 26 bps

`fee_for("SGOV")` used to return the 0.35% `GUESS` for a fund that charges 0.09%. That is the exact fault round 94 catalogued, still
live in the one instrument a cautious reader would buy: the table's own guardrail — *the guess is used only where a symbol is genuinely
absent* — was true of the symbol and false of the symbol's nature, because a cash fund had never been in any table at all. The two bill
legs are now sourced rows in their own table (`CASH_FUNDS`, ratios already written — and wrongly duplicated — in
`cash_yield_gap.py` for four rounds), and `cash_yield_gap.py` imports them.

**Priced is not tradeable, and conflating them was a crash.** `paper.posted_fee` refused a benchmark by testing `fee_for(symbol) ==
GUESS`; add SGOV to the table and that test passes, after which the function indexed `FEES["SGOV"]` and raised `KeyError`. Round 96's
`--witness` flag makes that reachable from a command line. The gate now distinguishes the two refusals:

```
SGOV has a sourced ratio but is not a traded leg of this archive: the corpus quotes no price for it,
so it can be neither held nor made a witness
```

The scan that catches hand-copied fees was widened to match how this copy actually hid: a dict-literal scan let `SGOV_ER, BIL_ER =
0.0009, 0.0014` through for four rounds, so the new scan keys on an uppercase `*_ER` constant holding a ratio-shaped number, with its
own negative test written from the line that actually fooled the old one — a check nobody has seen fire is a decoration (r91, r93).

## Checks

**2299 passed, 239 subtests** — ten new tests: the bill row's ratio is the table's and not the guess; the bill bar meets
`cash_yield_gap.bill()` within 30 bps over 120 months; the bar refuses a calendar it cannot accrue on; the only row allowed a zero hole is
the bill row, named as such; a bill fund is priced and refuses to be a sleeve, while `XLU` still gets the old refusal; the sweep ratios
are imported; the widened scan finds nothing and *does* fire on the fabricated copy; and `--witness SGOV` is a sentence rather than a
traceback. Live state unchanged: five books, one anchor each, all chains verify, sealed fees $0.00, first seal 2026-09-30.

*Round 99. 99 standing rules. The safest thing this archive can price returns 21% of paid in over sixteen years and never once went
backwards, and every construction that beat it did so by standing in the -31% hole.*
