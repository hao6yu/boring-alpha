# A headline with no command under it, and a stopping rule that called a loss "ahead"

Round 96. Changed: [`forward_p0.py`](../../tools/forward_p0.py) (`--witness`, verdict wording, one refusal),
[`power_horizon.py`](../../tools/power_horizon.py) (`secondary_bars`, printed every run),
[`test_forward_p0.py`](../../tests/test_forward_p0.py) (25 → 34), [`test_power_horizon.py`](../../tests/test_power_horizon.py)
(18 → 21), [`RUNBOOK.md`](../RUNBOOK.md), and round 82's
[note](2026-09-07-a-benchmark-that-could-not-compound.md) amended with its own re-run.

## The objective asks about two indexes. The command could only price one.

`--witness` now exists, and `--witness VOO,QQQ` prints a block for each. It changed which bar is *standing*: it did not. P0 stays
100% VOO — priced before the evidence existed, which is the only reason a bar means anything — and every non-VOO verdict line carries
`(a secondary bar cannot redefine P0)` appended to whatever the verdict was, including the two wordings written before the flag
existed. The index side is charged that fund's own posted ratio out of `fund_fees.py` (r94's table), and it still pays one buy per
deposit month however plain the fund is: a change of witness must not be able to change the cost sheet, and a test asserts the ticket
count is identical for both.

Two things fall out of pointing the tool at QQQ that VOO never asked. QQQ costs six times what VOO costs, so the free version of the
same bet is simultaneously **easier to beat on fees and harder to beat on returns**. And because QQQ is one of the book's own sleeves,
that comparison measures the *weighting*, not the instrument choice — the tool prints that caveat itself rather than leaving it to the
reader, since a number that flatters and a number that misleads are often the same number.

## The most consequential figure in the repository had no command under it

Round 82's replay: paid in $2,020,000, tilt closed at **$9,841,466**, plain QQQ at **$12,316,793**. For an objective phrased "beat VOO,
QQQ, or whatever", that row *is* the answer, and it existed only as a table inside a note — nine rounds of "venue dominates signal",
two of them about pre-registration, and nobody had ever made the number re-runnable. So `power_horizon.py` now prints all four bars on
every run, at the same $100,000 opening, one tenth a month, no commission, 3 bps of spread, on the same simulator the fee tables came
from:

```
  the bars, since the witness existed (193 month-ends, $100,000 opening, a tenth a month, no commission):
    plain VOO, the standing bar                paid in $   2,020,000   closed at $     7,853,675   +$    5,833,675
    plain QQQ, the free version of the same bet paid in $   2,020,000   closed at $    12,216,556   +$   10,196,556
    plain SPY, the free market                 paid in $   2,020,000   closed at $     7,760,092   +$    5,740,092
    the tilt, 50/50 rebalanced monthly         paid in $   2,020,000   closed at $     9,778,202   +$    7,758,202
    the best bar is `plain QQQ, the free version of the same bet`, ahead of the tilt by $2,438,354
```

Every row came back **0.4–0.8% below the published figures**, all four in the same direction, with paid-in and the month count
identical — which is what revised closes after a re-pull look like, and not what a changed fee looks like (a fee change would move VOO
and QQQ by different amounts, since their ratios differ 6×). The note now carries both readings with the drift explained, and the test
tolerance is 1.5% with a message telling whoever trips it to amend the note rather than the assertion. The finding survived the
re-run: QQQ ahead of the rebalanced tilt by $2.44M against $2.48M. Rebalancing a divergent pair to a fixed weight sells the winner
every month, and the free version of the bet never sells it.

## The bug the new fixture caught, in a stopping rule

To test verdict wording at all the fixture had to cross the protocol's 24-entry floor, and on the first decidable chain the printed
verdict read: **`ahead, but inside the no-skill margin (…, not evidence either way)`** — for a book *behind by $10,255*. Round 91's
margin gate tested the shortfall against the false-positive threshold before anything had looked at the sign, so a losing book was
handed the word "ahead". The margin is a *false-positive* threshold from r90's null: it is there to stop a small positive gap being
believed, not to talk a negative one into a tie. The gate now fails a non-positive gap first:

```
  FAILS P0 — behind by $10,290.82 net of tickets, and a no-skill margin cannot rescue a negative gap
```

Nothing in nine years of fixtures could reach that branch, because every fixture was three entries long. A test suite whose worst-case
fixture is unrealistically small cannot exercise the code that decides whether the programme continues; that is the same fault as a
stopping rule with no command behind it, wearing a different hat.

## Also, and briefly

- An unpriceable witness is now a named refusal — `IWM cannot be the bar for this chain: it has no sealed quote for it` — instead of a
  `ValueError` traceback out of `journal.comparator_path` (r93: a crash reports less than a sentence that names the missing input). The
  live books quote all twelve posted funds every seal, so this only bites on partial fixtures and on a book sealed before a fund joined
  the table; both are worth a sentence rather than a stack trace.
- `--json` changed shape: `{"primary": …, "secondary": […]}`. The old key set still lives under `primary`; one test was updated rather
  than the format kept, because the format was the thing that had become wrong.
- The monthly screen still prints exactly four conditions and the word QQQ does not appear in it, pinned by a test. The place to widen
  a standing rule is a note, not a default.

## Checks

**2268 passed, 239 subtests** — nine new tests in `test_forward_p0.py` (fee-matched bars, ticket invariance, wording on a decidable
fixture, sleeve disclosure, two refusals, the untouched status screen, the JSON shape, the runbook's standing-bar sentence) and three
in `test_power_horizon.py` (reprint within 1.5% of the published table, equal paid-in across bars, QQQ best by over a million). Live
state unchanged: five books, one anchor each, `all chains verify, and every entry accounts for itself`, sealed fees to date $0.00,
first seal 2026-09-30.

*Round 96. 96 standing rules. The archive's answer to the objective is now printed by a command rather than remembered in a note, and
the answer is: the free version of the bet is the bar to beat.*
