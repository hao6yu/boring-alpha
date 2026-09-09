# The stopping rule that was checked by nobody — and the cent that proved it

Round 93. Changed: [`audit_entries.py`](../../tools/audit_entries.py) (new), [`test_audit_entries.py`](../../tests/test_audit_entries.py)
(19 tests), [`rehearse_forward.py`](../../tools/rehearse_forward.py) (the audit runs as one of its own checks),
[`forward_p0.py`](../../tools/forward_p0.py) (the status screen now carries it), [`RUNBOOK.md`](../RUNBOOK.md) rule 4.

## The rule had no one watching it

Stopping rule 4 has been in the runbook since round 89 and reads, in part, *any sealed entry whose plan line contradicts its own
numbers*. Rounds 91 and 92 gave rules 1 and 2 commands. Rule 4's first half — hashes — had `journalctl.py verify` all along, and
its second half had nothing. That is the half that actually broke: round 87's rehearsal sealed an interval where a buy rounded a
fraction of a cent past the cash that existed, so the engine booked a loan, charged interest on it, wrote `borrow 0.00 … on 0.01
borrowed` into the note, and left `violations` empty. The chain verified. Every hash matched. The entry contradicted itself and
nothing was watching.

The engine was fixed that round. The *check* was never written, which meant the same class of error — one field disagreeing with
another — would have arrived silently again, and a rule nobody can execute is a decoration (r91).

## What the audit looks for

Nine checks, each derivable from the sealed record alone — no corpus, no fetch, no model consulted about meaning, only about what
it sums to: `sequence`, `anchor`, `priced`, `undeclared-loan`, `leverage`, `free-trade`, `cadence`, `idle`, `violation`. Two of
them deserve the reason they exist rather than a description.

**`undeclared-loan`** computes implied cash as `closing − holdings at the sealed quotes`, by calling `paper.recover_cash` rather
than a second implementation of that rule. Round 82's lesson was that a subtle rule written twice arrives twice, and this rule is
subtle: the previous balance is the sum of cash and holdings priced *then*, so subtracting today's marks would move
mark-to-market into the cash line, which would make the witness a straight line that every strategy beats in a rising market and
loses to in a falling one. Negative by more than a cent with no borrow clause in the note is the round-87 defect, exactly.

**`cadence`** compares the transfer that arrived against `paper._deposits_due` for the gap since the last seal, using the model's
own monthly figure. Round 84's defect class, and it matters for a reason that is easy to miss: paid-in is the denominator of every
return this repository reports, so a seal that forgives a missed month or funds the anchor month twice does not merely misreport a
transfer, it quietly changes the divisor of every percentage next to it.

`leverage` deliberately does **not** flag the shelter ladder or the constant-over-100 book for borrowing; those models borrow by
design, and flagging that is a misunderstanding rather than an audit. It flags a loan on a model whose plan says it never borrows.
There is a negative test for exactly this distinction, because a check that fires on the wrong model will be turned off within a
month.

## Two things the audit learned about itself, from its own fixtures

**A fixture that prices what the test means to leave unpriced** is a test that passes on nothing. My entry builder added a quote
for every symbol it was given holdings for — so the test for `priced` was auditing a holding that *was* priced, and asserting a
finding the code correctly did not make. It failed the first time it ran, and the fix was in the fixture, not the tool.

**The audit crashed on the defect it was meant to report.** `paper.recover_cash` deliberately raises `KeyError` on a symbol it has
no price for, rather than inventing one — so an entry with an unpriced held symbol blew a hole straight through the audit instead
of producing a line about it. A tool that crashes has reported less than a tool that names the missing price, so the audit now
reports `priced` and skips the cash check for that entry: you cannot audit the cash behind a number nobody computed. That is a
behaviour change in an audit, which is the most dangerous kind, so it is pinned by its own test.

The `lookahead` check I meant to write turned out to be redundant: `journal.Entry` already refuses to construct an entry whose plan
was posted after its own interval closed. Rather than keep a check that can never fire, the audit converts the construction failure
into a finding — `unreadable` — because a ledger line the protocol refuses to read is what rule 4 exists for, not a traceback on a
Tuesday.

## Where it runs, and why that matters more than the checks

Only running an audit on hand-made fixtures is how the r87 defect stayed invisible for a round: my fixtures were built from what I
expected the engine to write, and the bug was in what it *did* write. So the audit is now one of the rehearsal's own checks —
`no sealed entry contradicts itself` — which means four scenarios over a manufactured corpus (a flat month, a divergent month that
forces a real band breach and a sell, a skipped month, a 25% crash) must pass it, with real trades, real fees, a real skipped
deposit and a real mark-down in the chain. All four pass, and the real archive is byte-identical afterwards:

```
ok    no sealed entry contradicts itself    3 entries account for themselves
```

The live books audit clean: five records, one anchor entry each, sealed fees to date $0.00. The screen that carried four answers now
carries the fifth half-line — `all chains verify, and every entry accounts for itself` — which is the honest wording for a
three-week-old record with nothing in it yet.

**2229 passed, 239 subtests** (`/tmp/suite_r93.txt`). 93 standing rules.

*Round 93. All four stopping conditions now have a command, and the one that this project has actually been caught by is the one
that finally stopped being checked by nobody.*
