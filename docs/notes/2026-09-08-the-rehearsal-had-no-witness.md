# The rehearsal had no witness

Round 107. Added [`test_rehearse_forward.py`](../../tests/test_rehearse_forward.py) (12 tests) around the existing
[`rehearse_forward.py`](../../tools/rehearse_forward.py); no tool changed.

## The proof, and the hole under it

`rehearse_forward.py` manufactures a month-end the corpus does not contain and walks four scenarios through the real engine: a flat
month, a divergent one that breaches the band, a month with no session, and a 25% crash. Run today, 22 days before the first real seal, it
says:

```
     ok    2026-09-30 sealed                          entry 1, closing $4,997.89
     ok    2026-10-30 accrued 1 month(s) of transfers sealed $500.00, expected $500.00
     ok    2026-10-30 both chains verify              shadow entries 3, ledger entries 3
     ok    no sealed entry contradicts itself         3 entries account for themselves
     ok    the report prints and names its witness    BEHIND doing-nothing by $1.02   [DOMINATED — the fee line is $2.93]
     all checks passed · the real archive still ends 2026-09-04
     the real corpus is byte-identical to what it was before the rehearsal: yes
```

That is the first seal rehearsed green, second month included, fee accrual included, with the crash and the skipped month survivable. And
the suite had never once run it: no `test_rehearse_forward.py` existed. Every other claim in this repository has a class under it (r100) —
the one artifact whose entire job is to prove the forward path can seal was asserting itself, in a terminal, on whoever remembered.

## What the tests hold

- **All four scenarios, every check green, and at least 10 checks each** — an empty check list is the vacuous pass this repository has
  learned to distrust.
- **The two dates the objective needs appear in the labels**: `2026-09-30 sealed` and `2026-10-30 sealed`. A rehearsal that silently
  stopped reaching September would otherwise still print `all checks passed`.
- **The first deposit as a measured detail**, `$500.00` in the accrued line — the anchor-plus-one-month shape of the books is exercised,
  not assumed.
- **A skipped month is skipped, a crash seals only its survivors**, both derived from the tool's own `SEALS` table rather than restated.
- **The negative case** (r93): `audit_entries.audit` is patched to report one fake finding, and the rehearsal must turn it into exactly one
  failed check whose detail contains the injected word, print `FAIL`, print `CHECKS FAILED`, and exit 1. The audit inside the rehearsal is
  the check most likely to become decorative, so it is the one broken on purpose.
- **Nothing real is touched**: 16 files watched by sha256 — the corpus, the root chain, and all four book chains ×3 — compared before and
  after every test.

## Two things that went wrong on the way, because they are the useful part

The digest guard was **vacuous for a minute**: `BOOKS = ROOT / "data" / "books"` was a guess, and `real_state()` came back with two files
— the corpus — while the five real chains sat under `data/paper/books/`, exactly where `paper.PAPER_DIR` says. The guard passed
magnificently over nothing. The fix was to print the guard's own coverage (16 files) before trusting it, which is the same rule r92 states
for a refusal: show what you actually looked at.

Second: the injected-failure test needs the scratch state left *as a passing run would leave it*, so its cleanup is another rehearsal
rather than a bare `addCleanup(setattr, …)` — otherwise the next test in the class inherits the sabotage and fails for a reason that is not
in its own text.

## Checks

**2350 passed, 239 subtests** (2338 + 12 new; collected count printed before the run). Rehearsal green, five books sealed once at the
anchor, sealed fees $0.00, first real seal 2026-09-30, `23 more monthly entries … before a skill claim`.

*Round 107. 107 standing rules. The seal is rehearsed and witnessed now; the news signal is still dead; the bar is still the Nasdaq-100
fund doing nothing — and nothing in the objective can be claimed until the calendar moves.*
