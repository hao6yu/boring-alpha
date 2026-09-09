# The forward book was watching the losing candidate. It now watches the one that measures positive

Built 2026-09-06, round 32. New: [`constleverage.py`](../../src/boring_alpha/signals/constleverage.py), a
[`constant` model in paper.py](../../tools/paper.py), tests in
[`test_constleverage.py`](../../tests/test_constleverage.py) (8) and
[`test_paper_constant.py`](../../tests/test_paper_constant.py) (6).

## The asymmetry this closes

Since entry zero the book has tracked one model. Rounds 25 and 26 then measured that model, under costs an
account actually pays, at **−0.25%/yr against the comparator** with the cap on and **−1.27%/yr** forbidden to
borrow. Round 29 measured the only plan in the repository that still beats the comparator — a constant-leverage
book at **+1.63%/yr** — and round 30 stress-tested its loan against a floating rate. So for five rounds the project
has been accumulating forward evidence about a candidate its own accounting calls negative, while the only
candidate that measures positive has gone unobserved. That is not conservatism; it is measuring your own
pessimism and calling it a trial.

This is not a replacement, which matters because the existing chain is append-only and pre-registered: the
vol-target book continues untouched, still the only thing its chain is allowed to say anything about. `constant`
is a third model the same `--model` flag selects, so a second chain can be opened deliberately at the next
re-init rather than having its history rewritten now.

## What the policy is, and the one bug the interface caught

A constant weight, no lookback, no gate, no band, no review cadence — the plan contains no forecast, so the
forward record can only be about the market and the financing. `ConstantLeveragePolicy` is deliberately not a
signal, and it refuses to be one: it raises on `weight < 1.0`, because a 0.80× book is round 24's cash decision
wearing a leverage label, and on `weight > 2.0`, because round 30 measured that boundary and 2.00× is as far as
anything in this project has ever been priced.

Writing it against the real interface caught a bug worth stating, because it is the reason to write the interface
test at all. My first version returned `[(weight, 0.0), ...]`. `VolTargetPolicy` charges the **first** session's
funding as turnover — buying the book from cash *is* a trade — so a constant reporting zero entry cost would have
shown this plan's entire position acquired for free, flattering it against the comparator on day one and making
the two forward chains permanently incomparable. The policy now emits the weight as day-one turnover and zero
after, and the total is asserted: lifetime turnover must equal the entry and nothing else.

## The finding that reframes the whole comparison

I wrote this note expecting to say the constant book is simply *more exposure* than the signal — 1.25× against a
rule whose archive mean weight is **1.023×**, verified against `unlevered_timing.run` before this line was
written, and 0.843× once borrowing is forbidden. On the last sealed session that is backwards:

```
constant : constant 1.25x SPY (a loan, not a signal)              -> {'SPY': 1.25}
voltarget: vol-target 18%/30d, 200d gate, ... 30%-1.30x, ... -> 128% SPY  -> {'SPY': 1.28}
same asof: True    | exposure the constant adds: -0.03
```

The live signal currently wants **128%**, slightly *more* than the loan does, because the gate is off and realised
vol is low. So today the two books differ almost not at all in exposure — thirty thousandths of the account — and
that is the most useful thing this round produced. It means the forward record is not comparing a levered book to
an unlevered one, which is the framing every round since 25 has assumed. It is comparing **a book that holds 1.25
because nothing decides, against one that holds 1.28 today and will cut toward its 0.3 floor when vol spikes.**
The entire difference is behaviour under stress, which is exactly the thing the archive cannot settle and round 23
proved unmeasurable in the mean at $20,000. Two chains, one market, one behaviour: that is the cheapest design
that can answer it.

The test that pins this is written to fail honestly later. It asserts the signal's weight today is at least
`CONSTANT_WEIGHT − 0.05`; when the gate bites and the signal drops to 30% while the loan sits at 125%, that test
goes red for a *reason*, and the reason is the result.

## The stale number I did not quietly fix

`paper.py` finances a negative cash line at curve **+150bp**. Round 30 measured what a desk actually charges over
the same archive curve at **+202bp** — the book under-prices its own borrowings by 52bp on every day since entry
zero. I left it. The spread is pre-registered, both chains have been priced by it since the anchor entry, and
changing it would trade comparability against the archive for accuracy against the market, where the value the book
exists to provide is the former. The comment now says so at the constant, and any re-init should pin `0.0202` and
record the change — which is the same conclusion round 30 reached about the ledger's fixed-rate row: **the honest
number and the comparable number are not always the same number, and you have to say which one you are printing.**

## Checks

14 tests, 4.3 s, offline: the weight is constant and never `None`; `0.80` and `2.01` and `5.0` raise while `2.00`
is allowed; day-one turnover equals the weight, later turnover is zero, and the lifetime total equals the entry;
both models emit the same number of sessions and the same `asof`; the constant's mean weight over the archive is
strictly above the signal's, which is the assertion that stops the project confusing leverage with timing; the
label contains "loan" and does not contain "target"; and `BORROW_SPREAD` is still exactly `0.015`, which is a
change detector on a pre-registered input rather than a claim about the world.

Full suite: **1485 passed, 233 subtests**. `journalctl verify`: chain intact (1 entry), comparator
`100% SPY, fee 0.000945`, $0.00 paid in.
