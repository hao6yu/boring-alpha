# RUNBOOK — the monthly procedure, and the conditions under which it stops

This file exists because the archive cannot grade the growth tilt and never will: the tilt's claim is about the *future*, and
every figure in this repository is a measurement of the past. What the archive can do is record the forward test honestly, and
that recording is a procedure. Rounds 87 and 88 rehearsed both ends of it against manufactured month-ends
([the seal](2026-09-07-the-month-end-that-has-not-happened-yet.md), [the fetch and the whole loop](
2026-09-07-the-monthly-loop-run-twice-before-it-ran-once.md)), so the commands below are not hopeful prose: each one was run
against a scratch corpus whose month-end bar had not happened yet, and the tests in
[`test_runbook.py`](../tests/test_runbook.py) fail if this file quotes a number its own tools do not produce.

Nothing here is advice about anybody's personal finances, and nothing here needs to know any. Every figure is scale-parametric
— the friction table is in *fractions*, and the dollar columns are what those fractions cost at the named capital.

## Every month, in this order

Order matters, and the reason is a refusal, not a preference: the engine will not seal an interval for a date the corpus does
not contain, and the corpus will not contain a session the exchange has not finished trading. Fetch, then seal.

```sh
.venv/bin/python tools/forward_p0.py --status --commission 0   # all four stopping conditions on one screen
.venv/bin/python tools/fetch_market_data.py            # writes a new snapshot, repoints data/current
.venv/bin/python tools/corpus_diff.py                 # what the fetch actually moved (rule 4, corpus half)
.venv/bin/python tools/paper.py step                   # the root book
.venv/bin/python tools/paper.py step --book tilt_band  # and each other book, one command each
.venv/bin/python tools/journalctl.py verify            # recompute every hash, re-check the pinned comparator
.venv/bin/python tools/audit_entries.py               # every sealed entry against its own numbers (rule 4)
.venv/bin/python tools/cost_conventions.py            # what every cost on this page actually is, and whether the fork moves a verdict
.venv/bin/python tools/paper.py report --book tilt_band
.venv/bin/python tools/paper.py compare
```

Before a seal date, `rehearse_forward.py` walks the month on a scratch copy of the corpus and reports whether the real files were left
byte-identical. It has two halves, and they doubt different things:

* `--scenario flat|divergent|skipped|crash` drives the **engine** in-process on one scratch book — deposits arriving as drift, a band breach
  that must sell, a skipped month that must accrue two transfers, a crash nobody is rebalanced into. It has had a class under it since
  round 107 (`tests/test_rehearse_forward.py`), including the case where the audit inside it is made to lie and the rehearsal has to fail.
* `--scenario published` (added round 116, for the first real seal) drives the **block above** exactly as an operator runs it — every
  command its own process, the five live books, the audit, the pinned-comparator check — against a copy of `data/` reached through
  `BORINGALPHA_DATA` (`tools/labdata.py`), on a corpus carried forward flat to the seal date. It checks three things the engine scenarios
  cannot reach: that the block's order survives with the fetch replaced by a carried-forward corpus, that running the month **twice** is
  refused rather than double-sealed, and that every file under the real `data/` tree is byte-identical afterwards. The synthetic corpus is
  named `REHEARSAL-<date>T000000Z` and carries a sidecar saying what is invented, so an entry sealed in a rehearsal can never be mistaken
  for one sealed against a fetched corpus. One command of thirteen is skipped, and one only: the fetch, because a rehearsal must not be able
  to write a real snapshot. `corpus_diff.py` runs — it follows `BORINGALPHA_DATA` too, so it reports on the copy it was handed. Run it with `--asof 2026-10-30` to rehearse the first
  deposit month: the scenario computes independently of the engine how many transfers that date owes the books ($0 at 2026-09-30, one $500
  transfer at 2026-10-30) and fails if the sealed entry does not carry exactly that.

* `--scenario fetch` is the third half, and the only one that touches the network, so it is not part of `all`: run it by hand once before a
  seal date. It runs the real `fetch_market_data.py` against a copy through the fetcher's own `--out`, then `corpus_diff.py` against that copy,
  then asks the loop whether a seal is due — and refuses the run unless `corpus_diff` says out loud which directory it opened. Measured cost of
  the real fetch on 2026-09-08: **8 seconds, 73,009 rows**, and the loop's answer to a mid-month fetch was the correct refusal.

`tools/monthly.py` runs that block, in that order, plus one seal per book found on disk, and stops at the first command that fails.
It is the shape a bot takes in a project that has decided not to make decisions: the mechanical half of the month is one command, so
it can be done on the first of the month and never half-done. It reads its orders from the block above rather than carrying a copy
(`tests/test_monthly_runner.py` fails if the two disagree), it re-reads the stopping-condition screen *after* the seals so what is
printed is the state the seals left, and it skips a seal the calendar has not asked for — saying why, in the same words the engine
would have used. It has no `--force`, no `--yes`, no `--tilt`, no `--band`, because a runner that could overrule a refusal is a hole
in every refusal the tools have been built to make. `--dry-run` prints the plan and runs nothing, which is the way to see what a
given Tuesday would do.

`forward_p0.py --witness` can price the book against an index other than VOO (`--witness VOO,QQQ` prints one block each), because the
objective names more than one index and a tool that could only ask one question was answering the wrong one. It does not change which
bar is standing. **P0 is 100% VOO, priced before the evidence existed, and a bar moved after the results arrive is not a bar.** Every
other witness is a *secondary bar*, its verdict line says `a secondary bar cannot redefine P0`, and it gets the same refusal a caller
gets for an unsourced ticker: the index side is charged that fund's own posted expense ratio from `fund_fees.py`, and it still pays one
buy per deposit month however plain it is. Two things to read off a secondary bar: QQQ's fee is six times VOO's, so the free version of
the same bet is cheaper to beat and harder to beat at once; and if the witness is one of the book's own sleeves the answer is about
weighting, not instrument choice — the tool prints that caveat itself. On the sealed archive the tilt loses to plain QQQ, by the gap
`power_horizon.py` prints in its bar table below — round 82 first measured that gap, and the archive has been re-pulled since,
so the command's own line is the figure and this sentence deliberately does not copy it. The question is therefore not a formality: it is the
question the objective actually asks, and the honest answer so far is that nothing in this archive beats the free version of the bet.

The exchange calendar in `data/calendars/` is an input as well, and inputs age: the checked artifact publishes coverage only through the
end of a past month, so a fetch that adds no sessions can land in a gap the artifact cannot read. `corpus_diff.py` prints the coverage end
it is refusing against, and when the gap falls inside the interval the closure rules were reviewed for it answers from those rules and
says that is what it is doing — the licence for that is round 108's independent re-derivation of the rules in
`tests/test_nyse_rules_independently.py`, which reproduces all 5,197 sessions and 194 closures the artifact vouches for. On the live
corpus the answer is that the archive is current and not stalled: the weekday between the last session and the fetch was a closure.
`tools/build_nyse_calendar.py` is still the command that extends the artifact itself, and `tests/test_corpus_diff.py` pins both halves of
the sentence — the admission and the answer — so an answer can never arrive without its provenance.

`corpus_diff.py` runs immediately after the fetch, because a fetch is a re-pull and a re-pull is a revision: it compares the two newest
snapshots session by session and prints what moved — sessions added or removed, symbols added or lost, the worst single revised close
per fund, the count of restated dividends, and the cash factor. A revision inside **1.5%** (`corpus_diff.TOLERANCE`, the same constant
the replay pins in `tests/test_power_horizon.py` import rather than copy) is a vendor tidying its decimals and the month continues;
outside it the command exits non-zero and the month stops, because a number that has moved by more than the tolerance is a number whose
notes have to be re-read before they are quoted. Round 95 found this out by being surprised: a fetch, a pointer move two days earlier,
and a bit-level assertion failing with the finding entirely intact.

**The corpus is not byte-reproducible, and the published figures are.** The same window fetched twice on the same day disagreed on **72.6% of
price rows** — median relative move 1.8e-07, largest 2.31e-06, worst row 2003-08-25 TLT — because a vendor's adjusted series is a derived
quantity and every later dividend or split is folded back into it. `tools/corpus_drift.py data/current <the new snapshot>` measures the drift and
then recomputes the four figures this project publishes from both corpora, through the same functions the specs quote them from: P0's bill
$830.79/mo against $830.79/mo, its median multiple 1.24x, the 20% sleeve's bill $1,044.73, its drawdown 24.76%. Every one moved below half of its
printed unit, so the command exits 0 and says the quiet part: **the snapshot, not the vendor, is the authority**. It exits 1 the day a figure
moves further than it is printed, and the tolerance it used travels in the message.

**A fetch that exits non-zero means the corpus did not move, and a seal must not be attempted.** `main()` fetches everything
before writing anything, so a failure leaves the previous snapshot in place; the atomic rename means there is no half-written
corpus to clean up. If the seal then says `book is already closed at …`, that is the truth and not a bug: the pointer still
names the old corpus, which is exactly the failure round 88's rehearsal was written to catch.

`journalctl.py` is the older record — one journal, comparator pinned to 100% SPY, one entry deep, and left alone. `paper.py`
is the five forward books. Both verify, neither is ever edited.

## What the outputs mean, in the words they actually use

| output | meaning |
|---|---|
| `chain intact (N entries)` | every hash recomputed, the pinned comparator spec unchanged since the anchor |
| `underpowered — N more monthly entries … required` | the skill test cannot yet distinguish the book from its witness. This is expected and is not a failure |
| `DOMINATED — the fee line is $X` | on the intervals sealed so far, the book is behind the witness and this is what its own costs were. Over one or two months this says nothing about the strategy; it says a great deal about costs |
| `intact` in `compare` | that book's chain verifies; the gap column is against its *own* sealed witness on the same sealed quotes |
| `sold 0 sleeve(s), drift 0.0 points` | a banded book that had nothing to do, which is the correct behaviour when prices did not move |

## The first seal, and what it cannot show

The five books are anchored at 2026-09-04 with an opening balance and a monthly transfer. **The seal on 2026-09-30 will carry
no deposit**, because the anchor already funded September's money — this is `paper._deposits_due`'s rule, it is pinned by four
tests, and round 87 confirmed it through the command rather than the helper. The first transfer lands on 2026-10-30. If a
month-end is ever skipped, the next seal arrives with *every* transfer it skipped and `days_to_invest` recording how long the
oldest one waited, because forgiving a missed transfer would shrink paid-in, and paid-in is the denominator of every return
this journal reports.

The expected cost of the first interval, at flat prices, is the fee line the rehearsal printed: **$2.11 on a $5,000 opening**,
which is $1.50 of spread on buying the opening and $0.61 of fund expense. Nothing about the market. It is the floor.

## Friction, by size, with the number that actually matters

The tilt's weighted expense ratio is 0.14725% a year, and the archive charges each sleeve its own posted ratio rather than the
book's average — SPY at 0.0945%, QQQ at 0.20%, VOO at 0.03% where it is the witness. On every buy, a 3 bps spread. On every
deposit, that spread applies to the deposit alone:

| capital | expense, monthly | spread on the month's transfer | total, steady state | a $9.95 ticket, two sleeves, monthly |
|---|---|---|---|---|
| $5,000 | $0.61 | $0.15 | $0.76 | **$19.90 — 26× everything else** |
| $20,000 | $2.45 | $0.60 | $3.05 | $19.90 — 6.5× |
| $100,000 | $12.27 | $3.00 | $15.27 | $19.90 — 1.3× |
| $250,000 | $30.68 | $7.50 | $38.18 | $19.90 — 0.5× |

Read the last column as the only column. A flat ticket is the one cost in this account that does not scale, and round 86 priced
what that means: **commission-free, the tilt's advantage over plain VOO is identical at every size from $1,000 to $1,000,000;
at a $9.95 ticket it is not** — at $2,500 of capital over a two-year horizon the two-sleeve book ends *behind* plain VOO, and
the crossover sits between $2,500 and $5,000 on that horizon. There is no threshold to memorise, because it moves with the
tape; the rule that follows is stable — at a small account and a short horizon, hold one fund or use a broker that charges
nothing per ticket, and do not expect a rebalancing policy to help, because the ticket count is set by the number of sleeves,
not by how often the band fires.

`power_horizon.py` prints seven bars on every run: the three plain funds, the same 50/50 pair rebalanced monthly, past five points
of drift, and never, and T-bills at the archive's own curve charged SGOV's ratio. The last row is the one a reader actually holds while
deciding, and it is not close: over the record it turns $2,020,000 paid in into $2,447,542 (+21.2% of paid in) against the standing
bar's $7,853,675, and over the last five years it keeps 71% of the standing bar's terminal with a hole of 0.0% instead of -4.1%. Its
accrual is the product of the *daily* factors between month keys — exact on a stub month, which is what round 47's defect demanded —
and a test requires it to agree with `cash_yield_gap.bill()["last10y"]` on the last 120 months: both readings come out at
**2.4523% a year**, because two engines that own the same curve should not disagree. Over the record the ordering is monotone in how *little* the book trades — $9,778,202 monthly, $9,812,539 banded,
$9,988,324 never touched — and the banded construction the forward ledger actually runs sits $2,404,018 behind plain QQQ. That does not
contradict the 0.054% bill above: the bill counted transactions, and the $175,786 between the band and the drift control —
**8.70% of paid in**, 161 times the bill — contains no transaction at all. It is the price of holding a fixed weight on a pair that trends apart, and
no transaction ledger in any broker's statement will ever show it to you. Round 100 corrected that percentage: the paragraph had said 0.87%
for three rounds, which was arithmetic done in the head against a paid-in figure ten times too large, and it erred in the direction that
makes activity look harmless. `decision_sheet.py` now recomputes both figures from `rebalance_cost.py` every time it prints, and
`tests/test_runbook.py` reprints the two quoted here.

`cost_conventions.py` reprints the other half of the friction: every trading-cost constant in `tools/` with the file and line it
lives on, every fact written down more than once, every bps figure typed into prose instead of interpolated — and then it re-runs the rule
battery at each one-way cost the tools disagree about, because the honest question about two conventions is not which is right but
whether anything on the wrong side of the fork changes verdict. Round 104 wrote it after finding the price of a loan carried at two values
in three files, one of them corrected in round 30. Round 103's rule applies to it: the numbers it prints come from the modules, and
`tests/test_cost_conventions.py` includes the case where the audit has to fail.

`decision_sheet.py --capital <size> --commission <ticket>` prints this verdict for the size named, and refuses the two-sleeve
form where the archive says it loses. It is the command to re-run when the account changes size, not when the market moves.

## When this stops

The programme has falsification conditions written *before* the evidence arrives, which is the only kind of stopping rule worth
having, and one command prints the current answer to each of them — `forward_p0.py --status`. It is the first line of the monthly
block, and three of its four lines read `not decidable` today because the record is three weeks long. A screen that pretended
otherwise would be the most expensive line in this repository.

1. **P0, the standing rule, and the command that decides it.** The tilt must beat plain index dollar-cost-averaging — VOO on the
   same transfers, charged its own expense ratio and its own tickets — net of every fee and every cost the book actually paid,
   over a horizon long enough to be evidence. That comparison is `tools/forward_p0.py --book <name> --commission <ticket>`: it
   reads the sealed chain, rebuilds the index side from the same sealed quotes, and counts the book's orders off the sealed
   holdings instead of assuming them, so a banded book is charged for the trades it actually made. Until 24 entries exist it
   prints a cost sheet and says `not decidable`, and it refuses outright to score a chain that does not verify. If after 24
   entries it reads `FAILS P0`, the answer is VOO and the tilt is retired. The books exist to be able to say this.
2. **The band, against its own twin, and the command that decides it.** `tilt_band` differs from `tilt` in exactly one declared
   field. The comparison is `tools/forward_p0.py --book tilt_band --against tilt --commission <ticket>`, which nets each book's
   sealed value by the orders *it actually made* — counted off sealed holdings, not assumed from the model's description of
   itself — and refuses to compare books that have not sealed the same intervals. The allowed shortfall is the measured
   rebalancing bill as a share of paid in: **0.054% of paid in over the 16-year record ($1,091 on the 50/50 book),
   against 0.003% ($18) over the last five years**, both from `rebalance_cost.py`. Past that cap the verdict reads `BAND FAILS its own twin`; inside it,
   `no verdict either way`, which is the honest reading and not a pass.
3. **No claim while `report` says `underpowered` — and once it stops saying that, the sign is not the test, the size is.** The
   floor is 24 entries and enough paid in; past it, `journal.verdict` prints `beat` if the gap is positive *by any amount*. That
   instrument has since been calibrated: `tools/skill_null.py` runs it on 600 paths on which no skill is available anywhere —
   every fund earning the same index, the comparator charged the book's own expense ratio — and at the floor of 24 entries it
   prints `beat` **18.8%** of the time on luck alone, the luckiest 5% of those paths clearing **+152 bps**. So require a margin,
   not a sign: ahead by more than ~150 bps annualised at 24 entries, ~50 at 36, and by anything at all at 60 — at 60 the no-skill
   distribution sits 58 bps *behind*, because the book paid 3 bps to enter every month for five years while the comparator, being
   a construction, paid nothing. The pinned floor grows conservative with length rather than merely sharper, which is why a
   `beat` at 60 entries is close to proof and one at 24 is a one-in-five fluke. Re-run `skill_null.py --paths 600` after any
   change to the fee table or the deposit schedule, and trust its printed column over this sentence.
4. **Integrity, immediately, and there is a command for each of its three halves.** Hashes are one half: `journalctl.py verify` and
   `paper.py compare` must report `intact`. Self-consistency is the second, and it is the half this project has actually been
   caught by — round 87 sealed an interval whose note admitted a cent borrowed, whose `plan` field promised the book never
   borrows, and whose `violations` tuple was empty. `tools/audit_entries.py` reads every sealed entry and asks it to account for
   itself: sequence, anchor, an unpriced holding, an undeclared loan (implied cash is computed by `paper.recover_cash`, not by a
   second copy of that rule), declared leverage on a model that says it never borrows, a trade that paid nothing, a transfer that
   disagrees with the cadence rule, an unreported idle month, a ledger line the protocol itself refuses to construct, and any
   confessed violation. It exits non-zero on any of them, and prints `clean` rather than nothing when there are none — because
   `not tested` and `nothing found` have to look different on screen. The third half is the input itself: `corpus_diff.py` reports what the last fetch moved, and a
   close or a dividend revised outside its tolerance stops the month for the same reason a bad entry does. The programme stops until a
   finding is understood. This is
   not a risk-management formality: the ledger's value is that it cannot be quietly wrong, and "quietly wrong" is exactly what a
   hash protects least well.

## Things that never happen here

Ledger files are append-only: no editing, no reordering, no deleting, and no `init` on a book that already exists. A book's
config is written once at the anchor and is never rewritten — a book anchored without a band cannot acquire one later, and this
is enforced by a test that reads the raw bytes. The corpus is not hand-edited; it is fetched, and the fetch either completes
into a named snapshot or fails. `--tilt` and `--band` are refused on the command line because a rebalancing band is a measured
property of a model, not a caller's preference. And `decision_sheet.py` refuses a news veto, an intraday claim, options, and
single stocks, because the archive cannot price them and a sheet that invented a figure for them would be the most expensive
document in this repository.

*Every dollar figure above was read from `paper.py`'s constants, `power_horizon.secondary_bars`, and `rebalance_cost` on the sealed
archive. `tests/test_runbook.py` recomputes them on every run: `TheFrictionTableIsComputed` the friction table and the first interval's fee line,
`TheProseReprintsItsOwnFigures` the two shares of paid in, and `TheDecisionFiguresAreReprinted` the bar table and the
`skill_null.py` calibration. A figure in this file with no class under it is a figure that has not been looked at since it was written.*
