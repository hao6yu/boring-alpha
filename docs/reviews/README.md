# Evaluation reviews

BA-001 reviews precede the next evaluation period. Its validation command
requires a file named `<STRATEGY_ID>-development*.md` here. BA-002 instead uses
its fixed seen-history contract and confirmed freeze; calling its second seen
window `validation` does not create an independent validation period.

Current BA-002 status: [two-feed source sensitivity complete — practical
no-go](BA-002-source-sensitivity.md). Both feeds fail the existing economic
requirements; this is a non-gating diagnostic, not a formal classification.
The [earlier preflight](BA-002-preflight.md) records the data issues that led to
the comparison. No holdout evaluation occurred.

A review records what was run, what the artifacts show against the charter's
advancement criteria, what surprised the author, and what was decided. It cites
run identifiers rather than repeating numbers, and it is written before the next
period's results are known. Reviews are not deleted when they turn out to be
wrong; a later review supersedes an earlier one and says so.

## Standing instruments

[Forward journal protocol](FORWARD-JOURNAL-protocol.md) is not a review of a
strategy. It pins a comparator, and a definition of "worked", against a ledger
that does not yet contain money — the only apparatus here capable of generating
evidence nobody has previously looked at, since every archived window has now
been examined. The rules below follow from it and bind everything else here:

- **A benchmark may not be the thing being tested.** BA-004 scored a no-signal
  vehicle against the fund it holds, passed its own gate, and lost $5,700 to
  doing nothing on the same schedule. The protocol for it is
  [here](BA-004-test-protocol.md) and the superseded verdict is
  [here](../notes/2026-09-05-BA-004-retention-audit.md).
- **A skill claim needs a gate.** Cost findings are decisive from the first
  entry. Return claims need 24 entries, $10,000 paid in, and zero violations.
- **A timing signal must state its required accuracy before its mechanism.**
  The bar is measured in [required accuracy](../notes/2026-09-06-required-accuracy.md):
  ~56–58% of weeks correct, every week, with 38% of the fund's growth sitting in
  17 of them. Four rules that exist here fall short in fifteen of sixteen
  windows. Propose a signal only with an accuracy estimate and this table
  beside it, or propose a sizing rule instead.
- **A leverage proposal must state its cap, its wrapper, and its margin-call
  count.** [Leverage sizing](../notes/2026-09-06-leverage-sizing.md) prices the
  dial: best marginal value at 1.5–1.75×, marginal dollars negative past 2.5×,
  margin calls appearing at 3× and every row above it disqualified. It also
  finds a crossover near 1.7× where an ETF wrapper becomes cheaper than retail
  margin and cannot be force-sold at all — a bigger dollar finding than any
  signal searched for, from a choice requiring no forecast. Scope it honestly:
  every one of those numbers is an *accumulation* number, and
  [withdrawal capacity](../notes/2026-09-06-withdrawal-capacity.md) shows the
  same dial reducing the monthly amount a plan can be relied on to pay, at
  every leverage, with financing free, and worse again inside a wrapper.
- **An income claim must be quoted as a withdrawal, at its worst start date,
  with its smallest cheque.** "Beats DCA by $346 a month" is an accrual on a
  balance that spends decades underwater. What the goal asks is answered by
  [withdrawal capacity](../notes/2026-09-06-withdrawal-capacity.md): bisect the
  largest monthly withdrawal every start month in the record survives, print
  which start sets the floor, and print the least ever actually paid. Averaged
  over starts the sequence-risk figure is meaningless, and a headline quoting
  the first cheque lets a policy that halves spending in a bear market be
  compared against a fixed one as though it were the same promise.
- **A check must test the object that would be abused.** Three rounds produced a
  check that passed honestly about the wrong thing: a timing table that was not
  monotone in accuracy ([required accuracy](../notes/2026-09-06-required-accuracy.md)),
  a leverage sweep whose control row had to equal the comparator exactly
  ([leverage sizing](../notes/2026-09-06-leverage-sizing.md)), and a `verify` that
  recomputed the ledger chain while ignoring the pinned benchmark it exists to
  protect ([forward book](../notes/2026-09-06-forward-book-integrity.md)). When
  adding a gate, name the edit it would catch; if you cannot, it is decoration.
- **The benchmark needs its own sealed ledger.** The dominance rule is the one
  claim here that must not rest on the graded party's arithmetic, so doing-nothing
  now runs as a parallel chain, `data/paper/shadow.jsonl`: advanced in the same
  breath as each strategy entry, priced from the same quotes and the same
  deposits, and carrying that entry's hash inside its own sealed note so the two
  cannot be rewritten independently and re-paired at report time. Costs are
  symmetric by construction, and the first draft of that symmetry was wrong in
  the flattering direction
  ([witnessed benchmark](../notes/2026-09-06-witnessed-benchmark.md)). A benchmark
  priced cheaper than the thing it judges is a rig, and so is one priced dearer.
- **Score a timing claim against its own weights read backwards.** Same numbers,
  same mean, same time spent at each weight, order reversed — so anything the
  reversal matches was never timing.
  [Policy withdrawal](../notes/2026-09-06-policy-withdrawal.md) runs that row next
  to the flat-at-the-policy's-own-average control, and it is the row that decides
  whether a raised floor is a trading rule or a discount: SPY's candidate pays
  $518 against $343 reversed, and ITOT's pays $669 against $720, which is why one
  of those two gets a claim made about it and the other does not. Showing the win
  at every sleeve is not the same as showing it is real — the reversed row loses on
  two of four sleeves and the write-up says so.
- **Check the encoding before the result.** Three faithful-looking call sites of one engine
  priced the same policy at $1.80m, $2.05m and $2.07m on the same archive, same costs, same
  window. The rule was never the variable; the call was. Weight *wanted* and weight *held* are
  different objects — one is `raw_weights` with the gate disengaged until the trend window
  fills, the other is what survives the review cadence and the no-trade band — and a band
  switched off at read time turns a couple of hundred fills into 8,428. [Funded
  policy](../notes/2026-09-06-funded-policy.md) therefore pins the encoding as a row of its
  own table and buys the right number by reproducing the pre-registered scan to the trade and
  the cent, on the archive that scan was sealed against. A simulator is not a measure of a
  rule; it is a measure of the call that passed it in.
- **Test that a guard can refuse.** The funded simulator takes an `allow` set, documented as
  restricting trading to the sessions the policy decided to trade, and every caller that passed
  one believed it. It could refuse exactly one trade — the opening one — because the test ORs
  the argument with a flag that is sticky from the first fill onward. [The cadence
  gate](../notes/2026-09-06-cadence-gate.md) gave it teeth and re-measured the pre-registered
  candidate in place: 241 fills became 222 and the full-window beat over plain DCA fell from
  $156,921 to $113,439, while the classification — two of four windows, short of the four the
  bar demands — did not move. Give a guard the smallest input that should make it say no, and
  check that it says no. If it cannot, then every number it appears to have enforced was an
  accident with a citation attached, and the honest response is to re-run the numbers and leave
  the old ones standing in the note that printed them.
- **Charge the borrowed money at what money actually costs.** Ten rounds left one mechanism
  standing — more index than you have money for — and the rate it depends on was the only
  load-bearing input in the repo that was typed in rather than fetched. [The financing
  break-even](../notes/2026-09-06-financing-break-even.md) priced it against the April 2026
  posted menu: the same 45 cells earn a median $206 a month at the cheapest desk and lose a median
  $12 at the most expensive, because retail base-tier margin spans 4.90% to 12.00% on identical
  collateral, which is 710 bps of certainty against a timing edge worth $32 a month. Three of the
  tool's own lies were caught on the way — a solver priced at a different band from the row it
  described (40-65 bps too generous), a `at_rate` that double-charged the cash rate, and a
  discontinuity that leaps over its own zero. Print the outside answer next to yours, and print
  the decision the difference leaves.
- **Test the rule at the leverage it would actually run at, and compare it to the exposure it took.**
  A timing rule that only works at 1.0x is advice about where to sit, not a way to make money, so
  round 12 multiplied the candidate's weight path by a leverage factor — floor and cap scaled with it,
  which is the only reading of "the same rule, run bigger" that leaves the rule intact.
  [The levered gate](../notes/2026-09-06-levered-gate.md) found an operating point and a hard
  boundary: at 1.25x it beats plain DCA on *both* axes — more money and a shallower worst month — in
  12 of 15 cells with no margin call anywhere, and at 1.5x in 10 of 15; at a custodian's 10.575% the
  same book is worth −$65 to −$87 a month, and at matched drawdown the median is +$95 cheap against
  −$65 dear. The dollars are still the borrowing: the rule loses to a constant book at its own
  realized exposure in two thirds of cells. Three of its own lies were caught on the way — a benchmark
  quietly handed the policy's no-trade band (−$607 and 4.5 points of under-investment on one window),
  a control whose churn was set by a band rather than by the rule's calendar, and a bisection whose
  bracket was moved the wrong way, which claimed a crossing in 12 of 15 cells while missing by up to
  29 points and would have published a median three times too large. Its check read the lever rather
  than the drawdown, and printed its own note only on the rows that refused to answer.
- **Price a signal's bar on the trades it actually makes, and take its accuracy from what its money
  implies rather than from what its decisions count.** Nine rounds rested on round 3's "56–58% needed,
  every rule a point or two short", and that bar came from a shadow timer that redraws its state every
  week — a coin's turnover, 844 switches, charged to a rule that makes 107. [The accuracy
  bar](../notes/2026-09-06-accuracy-bar.md) re-ran the claim on each rule's own calendar and inverted it
  instead of counting it: the toll is 1.5 points of the headline, the misplaced expense ratio 0.15, and
  the redraw **12.8 points** on the one rule the goal would use; the trend filter's real bar is 71.0%
  against a skill of 59.5%, and nothing clears its own bar in 96 rule-windows. The count was the deeper
  error — one calendar scores +30 points of wedge run forward and −35 run reversed, with both rows
  losing money — so a percentage of right decisions cannot rank two books that the money ranks.
  Four of its own lies were caught on the way: a run list priced five bars left of where it lives, silent
  and $1,626 away on a twelve-run row; a coin control that read 41.7% on one seed against a true 52.0,
  which is why that row is now twenty-five books; a bar solver whose tolerance was tight enough to call
  the comparator unreachable; and a test of the expense fix that compared two books built from bars the
  fix had already touched, so it could not have failed. Its own candidate's row is the one to remember:
  bar 100.0%, gap zero, +$0 a month in every cell — a gate floored at 30% never leaves the fund, and a
  two-state frame has no symbol for that, which is how it got scored as doing nothing and reported as a
  decision.
- **Price the door you say is open, in the same units, the same round — an unpriced hope is how a search
  stalls.** The accuracy bar's closing argument was that the bar *falls* as a rule makes more, smaller
  bets, which was the one finding arguing for the goal's own instinct, short-term trading. It was tested
  rather than admired: [`--cadence 1`](../notes/2026-09-06-cadence-bar.md) moves the review frequency and
  nothing else, every lookback staying in sessions. The prediction held — every bar fell, 0.2 to 3.7
  points, the coin's by exactly the amount the run-count arithmetic said — and it bought nothing: 22 of 33
  comparable rows lost *more* money on a daily clock, 0 of 42 daily rows made any, the median change was
  −$23 a month, and the best row anywhere was −$58. The toll cannot be blamed, because cutting it fifteen
  fold recovers a fifth of the damage; a faster clock adds events, not information, and grades the same
  opinion on a shorter span. One rule's hit rate moved nine points in the wrong direction while its money
  moved 4%, which is the previous bullet's lesson arriving from the other side: the count is a statistic
  of the calendar, not of the book. Pinned in `TheCadenceIsAFreedomNotAnEdge`, including the two invariants
  that make the grid trustworthy — 5.0× the bars, identical deposits, and the same signal answering the
  same question on the same Tuesday.
- **Count the bets, not the names, and charge the universe before you credit the signal — an edge worth
  less than the cost of the shelf it sits on is not a missing finding, it is an affordable one.** Rounds
  13 and 14 both ended by blaming one autocorrelated series for the missing independent calls, so the
  premise was tested where the archive can actually test it: [`cross_section.py`](../notes/2026-09-06-cross-section.md)
  ranks nine sleeves on a monthly calendar against *two* comparators — equal-weight of everything it is
  allowed to name, and plain DCA into the index fund. The ranking passed the test round 13 designed for
  it: forward beat reversed by $413 a month, and the reversal never once out-earned the rule. It still
  lost the only contest that decides anything, because holding nine sleeves instead of one cost $520 a
  month and 235 decisions across those nine sleeves implied **2.5** independent bets at +0.32 average
  pairwise correlation. Two more traps surfaced on the way: the average pairwise correlation rose to 2.0
  effective sleeves in the one window where the rotation cleared, and the choice between two funds on the
  same index at a 6.45 bps fee gap moved the headline by $24 a month — the same size as the only positive
  result in the file. Pinned in `TheResultIsPinned`, which pins the loss, the win over equal weight, the
  forward-minus-reversed spread, and the fact that the sign *inverts* at a three-month lookback.
- **Charge a deviation only for the trades it caused itself, and discount its months by their own
  persistence — a tilt inherits its signal's sign, its universe's cost, and its own variance.** Round 15 left
  a working ranking priced out of its own universe and an obvious retreat: hold the index fund, point a
  fraction of it at the ranking. [`partial_tilt.py`](../notes/2026-09-06-partial-tilt.md) swept 5 to 50% of
  the account, printed all 40 forward cells, and refused every one: the recent window pays +$5 to +$45 a
  month and the other three lose at every size, while the forward tilt beats the reversed one five-fold — the
  ranking works and the default sleeve simply was the best thing on the shelf. Two arithmetic traps surfaced.
  Charging a tilted book its *own* turnover instead of the *increment* over the comparator's bills it for the
  benchmark's own fund splice: one month in 235 came out 11.8× instead of 10×, and only the proportionality
  test caught it. And the terminal gap grows 11.3× when the tilt grows 10×, so halving a tilt does not halve
  its damage. Pinned in `TheTiltIsAWeightNotAnAlchemy` — including `test_the_pass_rule_can_pass`, because a
  verdict that can only print "NO" is decoration, and `verdict` now raises if a cell is missing from the grid
  instead of grading the survivors.
- **Give a protective number an error direction, not just a value, and state the result at the size that has
  to live with it.** [`monthly_ticket.py`](../notes/2026-09-06-monthly-ticket.md) turned the one surviving
  mechanism into an order sheet with a refusal path, and the delever trigger it prints taught two things. The
  first draft's closed form, `1 - L m`, was conservative below 1/(1-m) and *dangerous* above it — a
  protective figure whose error changes sign at a leverage nobody was looking at, which no amount of
  eyeballing the 1.25x default would have revealed; the exact form is now asserted against the maintenance
  ratio itself, and the crossover is pinned. The second is that the same policy quoted two different ways
  tells two different stories: +$142/month on the archive's compounding schedule, +$23/month on a $20,000
  account, and the second is the one that answers the goal. A number that scales linearly in NAV is a
  multiplier on a balance sheet, and the honest unit is the small one. Pinned in
  `TheProtectivePriceIsThePriceTheEngineActsOn` and `TheDollarFigureBelongsToTheAccountNotTheArchive`.
- **Build the control that can refute the signal before you build the signal, and make the price refuse the
  shape it cannot price.** The one input the goal kept asking for was non-price, so round 18 went and got it
  properly — [`attention_feed.py`](../notes/2026-09-06-attention-feed.md) seals Wikipedia page views (knowable
  on the day, never revised) into content-addressed blobs behind a guard that rejects any article created
  after the sample began, because an event-named article postdates the event it would forecast.
  [`attention_bar.py`](../notes/2026-09-06-attention-feed.md) then priced it at the usual bar: six
  shared-window cells, −$87 to −$479 a month, all six refuted by the six-article non-financial control basket
  at the same thresholds and windows. Two failures of process, both now structural. The pass rule's control
  clause had been a footnote rather than a clause, so the first pass printed PASS beside a control making more
  money; and the schedule assigned a full weight to *every* sleeve, so an invested month was 2x and an
  "unlevered timing" grid reported +$507/mo that was really −$138. A schedule summing above 1.0 is now
  refused rather than priced, a held row is asserted to hold one sleeve, a sit-out is an explicit zero and
  not the empty row `run_book` reads as "keep holding" — and the bug was caught by a test written to check
  something else, which is the standing argument for writing the boring test.
- **Price the decision the user actually controls before pricing another forecast, and let the benchmark be
  the thing that cannot be scored rather than the thing that lost.** Round 19 stopped looking for a signal and
  priced the withdrawal rule — [`income_frontier.py`](../notes/2026-09-06-income-frontier.md) scales each of
  four spending rules until they deliver the *same* guaranteed floor across every start date, then compares
  what they pay. The guardrail is worth 32% more income on T-bills and 59% more on SPY than a fixed cheque at
  an identical guarantee; the entire spread between plans at the same floor is smaller than that, and the
  loan that survived the accumulation tests is Redundant here and disqualified outright at 20 years. Two
  defects the round found in its own machinery are the ones worth remembering. `withdrawal_capacity.run` had
  been scoring a cash account as ruined in its first month (`value <= 0 or position <= 0` — right for an
  all-equity book, wrong for a plan that never held a sleeve), so the benchmark this repo has been quoting
  against since round 7 was not computable; and the new frontier was accumulating margin calls and discarding
  them, which is how a plan that only works because the lender never had to sell gets to count as reliable.
  The 36 pre-existing withdrawal tests, unchanged, are what make the first fix safe. Say "not measured" when a
  record is too short — VOO has no 20-year history and writing "cannot promise" there would have been the most
  consequential wrong sentence in the table.
- **A control that copies its subject is worse than no control, and a conclusion written before the last plan
  was priced is a guess.** Round 20 re-opened round 8's candidate in round 19's equal-floor frame
  ([`2026-09-06-candidate-frontier.md`](../notes/2026-09-06-candidate-frontier.md)) after noticing that
  round 19's "no trading mechanism raises a monthly income" had been written while pricing only constant
  leverage. The candidate — an 18% vol target behind a 200-day trend gate, charged its own monthly turnover at
  a zero band and borrowing at the posted tier on average — clears the bar: +$123/mo over the same sleeve
  flat, +$127 over its own mean weight, +$320 over the mirror image of its own path (which dies outright),
  +$98 over itself with the gate removed, and it ends the worst 20-year start with 66% of the lump where the
  index left 12%. Two near-misses are the transferable part. The `avg` control shared one variable with the
  policy selector, so it silently *was* the candidate and matched it to the dollar — the reading would have
  been "the policy is worth nothing over its own average", the exact inverse of the truth. And the borrow was
  priced against this year's cash yield, which made a 20-year backtest borrow a point under the posted rate in
  the years that matter. Both now fail loudly. Keep asking which plan has not been priced yet, and give every
  control a test that fails when it stops being a control.
- **Check whether a row is capable of ranking anything before ranking with it, and check whether a control can
  fail before trusting its silence.** Round 21 priced round 20's candidate on every sleeve in the archive
  ([`2026-09-06-sleeve-league.md`](../notes/2026-09-06-sleeve-league.md)) because the goal names VOO and QQQ
  and the proof had been written on SPY. The rule is worth +$123/mo on a record holding two crises and **$3/mo
  on VOO's fifteen benign years** — and the reason the VOO row looked like a result at all is that a guardrail's
  median is capped at twice its floor, so on any record mild enough to cut nobody, every plan reports 1.98x to
  2.00x and the column is printing the number 2.00. The tool now flags those rows `NOT DISCRIMINATING` rather
  than letting a gap through. The reversal control, which decided round 20 by dying, is silent on ITOT for a
  structural reason: one crisis, mid-record, so the mirror image de-risks through it too (0.90 against the
  candidate's 0.53, versus 1.02 against 0.53 on SPY). A control's power is a property of the record, so the
  honest sentence there is "this control cannot decide this sleeve", and the test pins the gap as *inside the
  noise band* instead of pinning a win.
- **Price the protection before recommending it, and check what the machinery already does before declaring a
  blocker.** Twenty-one notes quoted the payout of the de-risking rule; round 22 priced its premium
  ([`2026-09-06-de-risk-premium.md`](../notes/2026-09-06-de-risk-premium.md)) as the distribution of ending
  capital, on disjoint windows rather than the 143-start grid that re-counts 2008 forty-five times. The shape
  is the finding: the rule costs the most for whoever invests **at the bottom** (the six most expensive
  ten-year SPY starts are 2008-12 to 2011-10) and the most where it pays (1994-95, 2001-02), and at $20k it
  is $21/mo on the median decade against a $25/mo noise floor — so it is a 20-year product, not a 10-year
  one. The methodological part is the same mistake this file keeps making in new clothes: the note's first
  draft asserted the rule could not enter the forward book because the comparator was wrong for it. One
  `cat` showed `model.json` already pinned to `voltarget` against plain SPY, running since that afternoon,
  asking for 128% of the account. **An assumed limitation is a bug report waiting on one command.**
- **Measure the instrument before believing its silence, and check whether a stated minimum is being read as a
  plan.** Twenty notes said the forward book would settle whether the rule earns anything. Round 23 measured
  what the book can resolve ([`2026-09-06-book-power.py.md`](../notes/2026-09-06-book-power.md): power 6%
  against the edge the archive predicts, flat from month 6 to month 240, and — the part that generalises —
  **identical detectable rates across a 50× range of account size**, because a proportional edge and its noise
  both scale with capital and only the ratio makes a test. The report line was not lying: it says *23 more
  entries required*, a minimum, and this file series read it as a promise. Two smaller lessons in the same
  round: the tool shipped with `edge × capital × 12` printed under a `/mo` label, which inflated the edge
  twelvefold and made the book look three times more capable — now pinned by a calibration test that injects a
  known noisy edge and demands it back; and a test called `list()` on an infinite generator, hanging the suite
  for ten minutes while looking exactly like a slow bootstrap.
- **When measurement is impossible at the size that exists, price the things that have no variance — and audit
  what your own simulations pay for free.** Round 23 proved the forward book cannot resolve a 0.34%/yr edge at
  any deposit size; round 24 went looking for improvements that need no statistical power at all
  ([`2026-09-06-cash-yield-gap.md`](../notes/2026-09-06-cash-yield-gap.md)) and found one worth **$46/mo on
  $20,000 of idle cash**, eight times the trading rule's whole expected edge, with a break-even sweep rate
  (2.79%) the owner can check on a statement in ten seconds. The same arithmetic then turned around: the rule
  sat idle 15.7% of the record and every simulation credited that slice with the archive's bill curve —
  **0.45%/yr of unearned credit against a 0.34%/yr measured edge**, i.e. the assumption is larger than the
  result resting on it. Two standing habits in one round: an external source that conflicts with the sealed
  archive (52bp) gets disclosed and the *lower* number used, and a headline is only as trustworthy as the
  weakest leg it is built from.
- **A levered strategy is a loan application: price the funding, not just the return — and remember which of
  your conclusions a shared mispricing could have moved.** Round 25 re-ran everything under an account's actual
  funding ([`2026-09-06-sweep-repricing.md`](../notes/2026-09-06-sweep-repricing.md)): the rule's excess over its
  own fund is **+0.40%/yr on the book's own accounting and −0.00%/yr once the borrow is charged at the posted
  desk rate** instead of the bill rate plus a 3bp execution spread. Six rounds of *comparative* conclusions
  survived, because every plan borrowed on the same terms; the one *absolute* claim the project existed to
  support did not. Two durable habits from the same round: the first version of the switch used an annual posted
  rate per month and printed −10.07%/yr, which looked like a finding until a first-order estimate (mean leverage
  × the rate gap ≈ 0.7%/yr) said it was impossible — bound the answer before trusting a tool you just wrote; and
  taking the unearned cash credit away **unpinned the guardrail from its own 2× ceiling** (1.97× → 1.77×), so
  the assumption that flattered the strategy was also the reason the benchmark could not rank it.
- **Build the control whose correct answer is zero, and compare a timing rule against the same average exposure
  rather than against full investment.** Round 26 forbade the rule to borrow and split its P&L by month type
  ([`2026-09-06-unlevered-timing.md`](../notes/2026-09-06-unlevered-timing.md)): the signal is worth **+0.51%/yr**
  against a static control at its own average weight (0.843), it halves the worst drawdown (−25.9% against
  −50.8%), and it loses 1.27%/yr to the index because 61 rally months cost more than 37 crash months returned.
  The static-100% control row then exposed a two-round-old bug — the benchmark leg was not charged the fund's
  expense ratio that the strategy leg paid, so every excess in rounds 23 and 25 was biased against the rule by
  0.0945%/yr; the four-row table in the round-25 note is corrected in place, its conclusion unchanged, because
  a constant error cannot move a comparison *between* rows. Ordering claims survive constant mis-specification;
  level claims do not, which is now the third time this file series has had to learn it the hard way.
- **A rate spread is only worth money on a balance that exists — so check what the spread is applied *to*
  before getting excited about how wide it is.** Round 27 opened the last unread file in the snapshot
  (73,009 distribution rows) to test whether the total-return assumption in every backtest here was hiding a
  cost now that idle cash pays nothing ([`2026-09-06-distribution-float.md`](../notes/2026-09-06-distribution-float.md)).
  It hides about nothing: a month's delayed reinvestment costs 0.00000004 of the account, because the float is
  one quarterly cheque (0.27% of a SPY account) rather than the account itself. The same 2.86% spread that was
  worth $46/mo applied to the balance in round 24 is worth under a cent applied to a dividend. That is the
  second time this series has had to price a *balance* rather than a *rate* (round 23: capital buys no power
  because signal and noise scale together), and it is the discipline to apply before any future "there's a
  spread here!" finding. Two free facts came out of the read, though: TLT/IEF pay **monthly** while every equity
  sleeve pays quarterly, and GLD pays nothing — which is cash-flow shape, and matters to a monthly-income goal
  in a way the return series cannot show.
- **Sort the findings by whether they can be observed, not by how large they are.** Round 28 measured nothing and
  added [`action_ledger.py`](../notes/2026-09-06-action-ledger.md), which puts all twenty-seven rounds' priced
  actions in one table with a variance column, because the aggregate had never been read: every note was honest
  and almost none disagreed, so nobody had asked what they summed to. The answer is that the only two actions
  with no variance in them — the idle-cash switch and the cheap share class — are the only two whose outcome the
  owner can verify inside a month, and everything the project would call a *trading bot* is on the losing side
  or unmeasurable at this size. Stated plainly, the goal as written ("beat VOO and QQQ with a trading model") is
  not what the evidence supports; what it supports is a housekeeping bot worth ~$46/mo on $20,000 before any
  market view. Writing that sentence down is more useful than a twenty-ninth audit, and a summary table needs a
  `--verify` flag because a table outlives the analysis that justified it: this one's first run caught the
  divide-by-twelve-twice in its own verification line, which is the argument for putting the re-derivation next
  to the row rather than in the prose.
- **Check that two artifacts in this repository are scoring the same portfolio before you say they disagree.**
  Round 29 found that `monthly_ticket.py` was printing +136 bps for a leveraged plan while `action_ledger.py`
  (round 28) implied the leveraged row was negative, and the obvious write-up was "the ticket overstates by the
  cash-leg subsidy." It did not. The ticket prices a **constant 1.25× book** — mean weight 1.250, no idle cash
  ever — while the ledger row was the **vol-target rule**, mean weight 1.023, holding cash about a quarter of the
  record. Under account-faithful financing the ticket's own policy measures **+1.63%/yr, +$27.24/mo on $20,000**,
  and the cash leg is worth *nothing* to it (+1.63% under both cash assumptions, to the cent) because a book that
  is always over 100% has no cash leg to under-credit ([`ticket-repricing`](../notes/2026-09-06-ticket-repricing.md)).
  Two things came out of nearly publishing a false correction. The ledger was missing a row and is wrong less
  often now: a constant-leverage book is the only plan in this repository that survives sweep cash and a posted
  desk rate, and it survives *because it is a loan*, not because it is clever — which is r25 stated as a result
  rather than a warning. And the first version of the caveat I printed into the ticket carried the wrong number,
  which is the argument for re-deriving a caveat from the tool that owns the figure before it goes into a tool
  whose entire purpose is to be obeyed.
- **A rate you assumed constant is a risk you did not price, and the average over a rate cycle is not the
  underwriting.** Round 30 re-priced round 29's surviving plan — the constant 1.25× book — against a *floating*
  desk rate, because margin is billed as a spread over an index and this archive contains that index
  ([`2026-09-06-floating-loan.md`](../notes/2026-09-06-floating-loan.md)). Calibrated so both models agree today
  (4.90% − 2.88% = 202bp), the floating model looks *better* on the full record (+2.32% against +1.63%/yr) and that
  improvement is entirely a regime gift: the sample contains a cheap-money decade and one rate shock, and at a
  spread 300bp wider the floating number falls **below** the fixed one. The decisive row is the binding window, not
  the average — 2007-09 is −1.49%/yr into a **−59.7% drawdown**, the largest number in this project and larger than
  the unlevered index's own worst fall. So the conservative fixed-rate figure stays the one to sign against, and
  the loan's apparent advantage over it is a property of the last twenty years' rates rather than of the plan. The
  control that made the whole comparison trustworthy is the same one as round 26: an unlevered book must earn
  **exactly zero** excess under *both* financing models, or the financing model is touching something other than
  financing.
- **Price a rate-dependent action against the whole rate history, not the rate today — and say which percentile
  the quote came from.** Round 31 turned round 30's discipline on this project's own first-ranked recommendation,
  the no-variance idle-cash switch ([`2026-09-06-cash-option.md`](../notes/2026-09-06-cash-option.md)). Priced in
  all 404 months of the sealed record it is worth +$46.12/mo on $20,000 today at the **55th percentile**, +$33.72
  at the record's median, **+$1.05 at its lower quartile**, and nothing or slightly negative in **19.1% of months**
  — the zero-rate decade. Six rounds had quoted the spot and never the distribution. The decision does not change
  (the worst month in 33 years costs $1.65 on $20,000, so the action is still free), but the *form* does: a
  twelve-rung ladder is the high-rate form of this recommendation and friction at the lower quartile, so the
  default should be a T-bill ETF. It also says the cash switch and round 30's loan are one exposure in two
  costumes — long the bill curve, short the desk — so neither should be described as regime-proof. The test that
  keeps this honest asserts the median month is worth **strictly less** than today's quote; a headline that drifts
  above the median has become a best-case number, and that is the same error as quoting a window.
- **If the thing you are measuring forward is the thing your own accounting calls negative, you are measuring your
  pessimism.** Round 32 closed an asymmetry six rounds in the making: the forward book had tracked only the
  vol-target rule since entry zero, which rounds 25-26 price at **−0.25%/yr** under account-faithful costs, while
  the only plan measuring positive — a constant-leverage book, **+1.63%/yr**, and −1.49%/yr into a −59.7% drawdown
  in its binding window — had never been observed at all ([`2026-09-06-second-book.md`](../notes/2026-09-06-second-book.md)).
  `constant` is now a third `--model` the same flag selects, so a second chain opens at the next re-init and the
  existing append-only chain is untouched. Writing the policy against the real interface caught a real bug: my
  first version reported zero entry turnover, while `VolTargetPolicy` charges first-session funding as a trade —
  the new plan would have acquired its position for free and been permanently incomparable to the old one. The
  round's actual finding came from running both models on the last sealed session: the signal wants **128%** today
  against the loan's **125%**, so the two books are *not* "more exposure versus less" as every round since 25
  assumed — they are one behaviour versus none, and the difference only exists under stress. Also left alone
  deliberately: the book's 150bp borrow spread against round 30's measured 202bp, because the pre-registered
  number and the accurate number are different things and the comment now says which one it is printing.
- **Price the alternative before you accept a conclusion, even one you derived yourself.** Rounds 29-30 concluded
  the only surviving plan is a margin loan, and every note since repeated the phrase without asking whether the
  loan is the cheap way to buy the exposure — a fund's own leverage delivers the same thing with no margin
  agreement, which at $20,000 or in an account where margin is unavailable is the only route available. It is not
  cheaper at the leverage this project actually recommends: at 1.25× the loan costs **0.98%/yr of exposure against
  the fund's 1.63%**, and with a dealer paid for the fund's swap the crossover solves to a **negative rate — the
  fund never wins at any interest rate** ([`2026-09-06-leverage-routes.md`](../notes/2026-09-06-leverage-routes.md)).
  The reason is a denominator: a borrower pays interest on `L − 1` and nothing on the rest, while a fund pays its
  fee on the whole position *and* pays for the same funding — so the crossover **rises** with leverage (fund wins
  below 0.15% at 1.25×, below 2.98% at 3×), meaning the fund is a better-value unit of leverage the more of it you
  buy, which is arithmetic and not advice. And the fund wins on cost precisely when the bill curve is near zero,
  the calm years, while its daily reset pays a path cost of `−(L−1)·L/2·σ²` that no expense ratio shows. Two
  sub-lessons: my first crossover formula was wrong and a printed number contradicted a measured one, which is the
  standing argument for printing both; and a conclusion restated across five rounds stops being a claim and becomes
  scenery, so re-price the load-bearing ones on a schedule.
- **If an archive holds the data to compute a number exactly, do not publish an approximation of it — and when you
  already have, go back.** Round 33's note printed the textbook path-cost term `−(L−1)·L/2·σ²` as "−0.40%/yr at
  1.25×" and moved on. Round 34 found the snapshot carries **8,458 daily SPY sessions**, so the quantity is
  computable rather than estimable, and computed it was not the same number
  ([`daily_reset.py`](../../tools/daily_reset.py), [`2026-09-06-leverage-routes.md`](../notes/2026-09-06-leverage-routes.md)
  corrected in place): the formula was within 0.5pp across 33 years and off by **18 points in 2022 and 14 points in
  2017**, and in 2017 the realised path cost was **positive +12.77%/yr** — a 3× fund returned +78.2% against the
  index's +21.8%. A quantity that changes sign with the regime cannot be quoted as a cost or bounded
  conservatively in either direction. The corollary that matters for the goal: the same 3× exposure held on a
  **monthly** rebalance earned more over the record than daily reset, because fixed notional between rebalances
  lets realised leverage fall into a fall rather than buying more of it — so route choice is worth more per year
  than the fee comparison in round 33 that prompted this file. (The **+3.54%/yr** and **+6.40%/yr** originally
  printed here were single start-day draws; phase-averaged they are **+0.91%/yr** and **−17.96%**. See r37.) Two
  of the new tests
  failed first because I encoded the formula's sign rather than the measurement's; the fix was to assert magnitude
  and let the regime decide.
- **A comparison is unfinished until the thing you recommend has been billed for what it costs you to do it.**
  Round 34 concluded monthly rebalancing beat daily by +3.54%/yr and printed it, having priced nothing on the
  rebalancing side — the exact shape of error r27 warns about, caught the same round by its own rule when a scratch
  estimate produced a `0.0x` turnover. Measured off the same 8,458 sessions
  ([`daily_reset.py`](../../tools/daily_reset.py) `turnover_per_year`), the bill is **0.12%/yr for daily against
  0.03%/yr for monthly at 3×**, so the route choice is dominated by path behaviour and not by cost, and the
  recommendation survives being billed. Two findings the unfinished version hid. An **unlevered** book is not
  turnover-free: holding 1.0 means trading the drift back twelve times a year, **0.41×/yr on this archive** — a
  real cost every index fund in the project pays and none has ever billed. And a flat market at 2× still turns
  over 0.50×/yr, because funding the book to target is a trade that recurs once per simulated block: cold-start
  entry cost and steady-state drift are different things and a control that conflates them fails twice before you
  name which is which.
- **When a thing has failed the same test for thirty rounds, check whether it was ever the kind of thing that
  takes that test.** Round 36 re-scored the vol-target rule as the contract it demonstrably is rather than the
  return strategy it has been graded as, and the decomposition round 26 built for an entirely different purpose
  turned out to be premium and claim in accounting form ([`2026-09-06-insurance-pricing.md`](../notes/2026-09-06-insurance-pricing.md)).
  The claim returns **91.9 cents per premium dollar** — an ~8% loading, the profile of a functioning insurance
  product — paying +2.81%/yr in 37 crash months against −3.05% in premium, netting −0.25%/yr (**$49/yr on
  $20,000**) to cut peak-to-trough from −51.8% to −29.4%. The question was never "why doesn't this make money" but
  "is 8% loading fair for 22 points of drawdown," which is a question about the account and finally has a number
  attached to it. Two things made the number trustworthy rather than convenient: re-bucketing at 3/4/5/6/8% moves
  the claim count 61→14 months and leaves the net cost at −0.25%/yr to two decimals, so the verdict is not my
  definition's artefact; and the broker's bill is only **1.1% of the gross premium** (13% of the net), so the drain is structural —
  being under-invested into recoveries — and cannot be fixed by cheaper execution, which closes that line of hope
  permanently. A first version of the drawdown test had the two numbers reversed and asserted nothing but my own
  sign error.
- **A backtest whose answer moves when you change a cosmetic input must report the distribution over that input,
  not one value from it.** Round 37 audited round 34's headline — monthly beats daily by +3.54%/yr — and found it
  was **one** start day out of 21, chosen by where a loop incrementing by 21 happens to begin
  ([`2026-09-06-cadence-luck.md`](../notes/2026-09-06-cadence-luck.md)). Phase-averaged, the edge at 3× is
  **+0.91%/yr**, and the worst of the 21 starts is **15.43%, below daily rebalancing**; the published figure was the
  near-best draw. Determinism is not precision — it only means an input was fixed without being declared. The
  direction survived the correction (less-frequent cadence wins the mean and the bill at 1.25× and 2×) and so did
  the recommendation, which is exactly why the size had to be reported honestly: at the **1.25× this account can
  actually survive, the entire cadence question is worth 0.24% of luck and +0.16%/yr of mean**, so rounds 33–36 were
  arguing over a lever worth fifteen basis points. What does not survive is the *idea* of infrequent rebalancing as
  a free improvement — dispersion scales with leverage (0.24% spread at 1.25×, 11.15% at 3× monthly, 83.72%
  quarterly with a worst start of −56.19%), so **cadence is a leverage decision, not a schedule**. Phase-averaging
  cost three lines; the prose it invalidated cost a note.
- **Compose before summing, and never let a row's value come from a different quantity than the row claims to
  measure.** Round 38 composed the ledger's positive rows into one account on one path ([`combined_account.py`](../../tools/combined_account.py)),
  and found the sum had never been valid. The two headline positive rows are **opposite stances on the same
  dollars** — the cash switch needs 100% of the account idle, the loan needs 125% in equity — and the engine proves
  it mechanically, pricing both in one term `(1 - w) * cash`: at w=1.0 the switch is worth *exactly* zero, and at
  1.25 it is also zero, the cash rate appearing twice and cancelling under a posted all-in desk rate. **Every stance
  holding cash loses to plain VOO, monotonically** (10% cash −1.19%/yr, all cash −11.89%/yr, −$198/mo). What
  survives composing is one thing: borrow 25% and own the index, **+2.48%/yr, $41.40/mo** — and measured on SPY
  rather than VOO the same stance gives +1.63% — and round 39 found that gap was **the window, not the fund**:
  the series cover different decades, so on a shared 192 months the two funds agree to **0.024%/yr, inside their own
  fee gap**, while the *same* fund over its own 404 months against those 192 moves **0.83%/yr**. Half the edge is the
  calendar. See r39. Then the row itself: `action_ledger.py` carried
  **$25.00/mo** for nine rounds across three notes, and that figure was round 18's *noise floor* — how badly the
  comparator can be measured — transcribed as the value of the action, **23× too big** against a true 6.45bp =
  **$1.07/mo**. A floor and a prize are different kinds of quantity. Ledger totals moved to $47.20 certain /
  $27.24 stochastic, the row is now derived from `wc.EXPENSE` at import, and `--verify` covers it: the unverified
  6 of 8 rows were exactly the ones that rotted.
- **Before comparing two series, compare their windows — in this archive a cross-symbol comparison is a cross-era
  comparison unless you stop it being one.** Round 38 closed by attributing 0.85%/yr of the loan's edge to "which
  near-identical fund the tool named" and pinned it with a test. Round 39 checked the precondition and found the two
  runs had never covered the same months: SPY has **404** (from 1993-01-29, carrying dot-com and 2008) and VOO
  **192** (from 2010-09-09, inside the archive's strongest sustained bull). Re-run on the **common** window the two
  funds differ by **0.024%/yr — tighter than the 0.065% fee gap between them**, which is the behaviour two funds on
  one index are *required* to show, and the false claim it replaced had been passing a test written to confirm it.
  What actually moves the number is the sample: the *same fund and same policy* is worth **+1.63%/yr** over its own
  404 months and **+2.46%/yr** over 192, so **the era is worth 0.83%/yr — half the edge** ([`combined_account.py`](../../tools/combined_account.py)
  `common_months`). Two things follow for the goal. Every excess figure in this project is a statement about a window
  as much as a policy, and the windows differ by series by design, so a plan's edge should be quoted per-window or
  not at all. And the correction is cheap to miss because unequal windows produce *plausible* numbers — nothing threw,
  no assertion fired, and the fund explanation sounded right for a round until someone counted the rows.
- **When the claim contains a time unit, price the shape and not only the mean — the mean is the one statistic a
  plan can satisfy while paying nothing for a decade.** The goal says *earn extra each month*; in 40 rounds every
  figure produced for the only plan that beats the index was an annualised mean (+1.63%/yr, $27.24/mo). Priced as a
  **series** ([`combined_account.py`](../../tools/combined_account.py) `monthly_edge`, `rolling_edge`, `streaks`), that
  plan is negative in **39.1%** of months, its worst single month costs **2.6× a full year** of its own advertised pay,
  its rolling-one-year hit rate is **76.3%** with a worst window of **−14.52%/yr**, and its excess-over-holding went
  underwater in **2000-04 and did not surface until 2009-02 — nine years, −22.2%** deep. Hit rate is *lowest at five
  years* (71.0%), below both one and ten: five-year windows straddle the crises without being long enough to recover,
  so "time repairs it" is only true in decades and the question was about months. This is also the round the goal's
  own contradiction becomes visible rather than inferred: the action with the good shape (idle-cash switch, positive
  **80.9%** of months, worst month **−$1.65**, no drawdown — bounded because its variance comes from a fee schedule,
  not an index) is the one that **loses to the index by 11.89%/yr**, and the action that beats the index behaves like
  the index. **No stance in the archive is both positive in level and well-behaved in shape**, and r38's algebra
  (no middle stance exists) plus this round's distribution explains why none could.
- **When the claim is about a monthly amount, name which order statistic it is — a mean and a guarantee are
  different numbers, and the same stance can raise one while cutting the other.** This repository answered the goal's
  monthly sentence twice, in two files, with opposite signs: `leverage_sizing.py` (round 3) reports 1.25× at
  **+$143/mo**, which is `per_month_equivalent` of a **terminal** gap — an annuity that was never withdrawn — while
  `withdrawal_capacity.py` (round 4) reports the largest withdrawal surviving **every** start falling from **$379/mo
  at 1.0× to $335/mo at 1.25×** — figures r42 re-measured on the dense grid as **$364 → $318**, the coarse grid having
  stepped over the April 2000 start that ends the promise. Priced side by side at one capital ([`income_accounting.py`](../../tools/income_accounting.py)),
  the mean is maximised at **2.0×** and the guarantee at **1.0×**, and every step up the grid moves money out of the
  guarantee into the mean (+$136 for −$47 at 1.25× on the dense grid; +$545 for −$151 at 2.0×). QQQ's guarantee falls from $171.25 to
  $20.00 across the grid (round 41 read its printed **$0.00** as a cliff; r43 found a probe-resolution artefact — see
  the next rule) while its mean column reads +$165 to +$661/mo. Every binding start is **2000-04/2000-05/
  2001-07** — the dot-com window r39 found in the era effect and r30 found in the drawdown, reached now by a
  decumulation engine sharing no code with either. One exception survived scrutiny and is reported as such: ITOT at
  1.25× guarantees $9.38 *more*, on **11 start dates**, with binding start `none` already by 1.5×. This is the
  goal's answer in its own unit and the sign is reversed rather than merely small: **no leverage level both beats the
  index and increases what the account can promise every month.** A mean that cannot be spent is not a paycheck, and
  any figure quoted without saying which statistic it is cannot be compared to one that does.
- **A statistic whose value depends on an input nobody was asked to choose must be reported with that dependence
  attached, and a minimum is the worst case of this rule because it is monotone in the sampling, not in the
  data.** Round 42 tried to confirm round 41's guarantee and found it was sampled on `withdrawal_capacity.py`'s
  default stride of 3 — while `income_frontier.py` already carries a test whose whole docstring says the coarse grid
  lets the levered promise through. Re-measured on every grid from 1 to 12, the SPY guarantee at 1.0× runs **$364.45
  (165 starts) → $378.52 (55) → $390.23 (14)**: **$25.78/mo of level from a cosmetic input**, and biased in the
  direction that flatters the loan, because the start date that ends the promise is **April 2000** and every third
  month from January lands on May. The corrected headline is **−$46.88 at 1.25×**, and it is worse than the number
  this rule replaced. What survived is the part that mattered: the delta is negative at **every** grid, in a band of
  −$41 to −$47, and the guarantee is maximised at 1.0× on all of them — so the finding is grid-robust and the
  *level* was never grid-robust, which is exactly why r37's rule ("report the distribution over the input, not one
  value from it") is not only about calendar phases. Two tests now pin the direction of the bias rather than its size,
  and the cross-artifact pin was deliberately moved onto the other file's grid so that changing this file's default
  cannot quietly break it.
- **A zero produced by a bounded search is a statement about the search, and so is a maximum: refine both ends of a
  bisection before either becomes a finding.** Round 41 reported QQQ's guaranteed cheque as "**exactly** $0.00 at
  every leverage above 1.0×", phrased deliberately to be checkable, and it was wrong. `withdrawal_capacity.capacity`
  probes 40 points to a 6%/yr ceiling, so its smallest rung is **$150/mo** on a $100k lump, and its
  `if not passing: return 0.0, 0, "none"` reports every frontier below that first rung as zero — QQQ's real figure at
  1.25× is **$113.75**, and at 2.0× **$20.00**. The `binding start` of `none` that seemed to corroborate the cliff
  means only "the grid found no failure", because it never probed that low; at a $5/mo rung the binding start is
  **2000-04**, same as every other row. The correction moves the finding *against* the loan (−$57.34 rather than
  −$43.36) and leaves its sign untouched, while the graded 171 → 114 → 69 → 40 → 20 is both weaker theatre and better
  economics than the cliff. The same function's ceiling has the twin failure in the other direction, which SPY
  demonstrates live: probed to a 0.2%/yr ceiling it returns **$200.00 with binding `none` at every leverage including
  1.0×** — that is the ceiling, not a frontier. So `income_accounting.py` re-probes any zero at a finer ceiling,
  flags any frontier resting on the ceiling as truncated, and prints the refinement inside the row. Two tests pin it:
  one asserts the refined figures, one asserts that the **unrefined engine still returns exactly 0.00**, so the
  artefact is recorded rather than quietly trusted again.
- **Condition an income on the account's own state before calling it income — a bounded, positive, verified series
  can still be pro-cyclical in exactly the wrong direction.** After 43 rounds two actions stand: borrow 25% (raises
  the mean, *lowers* the guaranteed monthly amount, r41/r43), and move idle cash into a bill ladder — the only one
  needing no borrowing, quoted for 13 rounds off an unconditional mean of $39.85/mo. Conditioned
  ([`cash_yield_gap.py`](../../tools/cash_yield_gap.py) `contingency`), it pays **+$5.77/mo through the GFC and
  +$5.46 through March 2020 — 14% of its own average — and went negative (−$1.32) inside the crisis**, and
  **+$6.66/mo across 2010-2021, which is 144 of the 404 months in the record**. Worst decile of market months
  +$33.39 against +$42.64 in the best. The mechanism was knowable in advance and is the rule: a bill ladder earns
  the policy rate, and cutting the policy rate is the response to the account being hurt, so this income is a claim
  on the central bank's normal and crises are its suspension. Note *how* the claim had to be tested — the monthly
  correlation with SPY is **+0.037**, i.e. uninformative, and an uncorrelated series can still pay in crises; it is
  the conditional **level** that indicts it, so the test pins the correlation as small rather than negative. The
  honest headline is now a vector, not a number: **$6.66 in a 2010-2021 rate regime, $5.77 in a 2008 crisis, $32.24
  in a rate-raising year, $46.12 today, $39.85 if the next 404 months look like the last 404** — and 1998 is printed
  as the counterexample rather than dropped, because its worst month paid $80.41 when the crisis was a term-premium
  problem rather than a policy cut.
- **Enumerate episodes from the data rather than dating them by hand, and state the unit of observation — a
  per-month and a per-episode average of the same events are different numbers, and hiding which one you used is
  hiding a choice.** Round 44's finding (the deposit switch pays $5.77/mo in the GFC against a $39.85 mean) was
  built on six windows whose dates I typed in — the same species of cosmetic input that moved r34's cadence figure
  11 points, r38's guarantee $26/mo and r41's QQQ cell $94/mo. Re-run with a bear month defined mechanically (SPY
  more than D% below its own trailing peak, D = 10/20/30%, episodes = maximal runs, nothing tuned
  ([`bear_sweep`](../../tools/cash_yield_gap.py))), the conclusion **strengthened**: pay falls monotonically with
  depth — **+$27.19 / +$15.68 / +$12.87** against calm months' +$45.07 / +$44.48 / +$41.86 — while calm pay barely
  moves, so the deepening threshold is not merely redefining the complement. What the hand-drawn table could not
  show is the second half: **month-weighted a crisis pays $27.19, episode-weighted the same nine episodes average
  $32.54**, because a 2-month episode at $95.71 and a 32-month one at $3.95 each count as one crisis. "What a crisis
  pays" has no fact of the matter behind it. Both are printed, and a test fails if they converge. The 2022-04…2023-05
  episode — index down 14 months, switch paying **$54.51**, above its own record mean, bill rate raised 0.71%→5.41%
  — is pinned as a test so the mechanism cannot decay into "crises pay badly": the switch earns the policy rate, and
  easing into drawdowns is a strong tendency, not a law.
- **Price the input you were handed before praising the output: a leveraged recommendation is a financing position
  first, so publish the break-even rate rather than only the edge measured at one assumed rate.** Fourteen rounds
  priced the loan at bill+150bp or at `MENU_PUBLIC` = 4.90% all-in — the April 2026 posted flat tier of the
  *cheapest* US desk. Posted base tiers elsewhere: Schwab 10.00%, E\*TRADE 10.45%, Fidelity 10.575%, Merrill
  ~11.13%, Firstrade ~12.00%, and sub-$100k accounts pay the base tier because the discounts start above their
  balance. `financing_desk.py` now solves the rate at which a constant-leverage book stops beating the same money
  unlevered: **SPY full history 9.21% at 1.25×, and the tolerable rate FALLS with leverage (8.25% at 2.0×; QQQ
  full history 6.60%, and 4.10% at 2.0×)** because variance drag scales with exposure squared while financing
  scales with (w−1) — leaning harder makes the recommendation *less* robust to your quote. Every large-custodian
  tier exceeds the full-history break-even, so the tilt survives at those desks only on the post-2010 window
  (SPY 13.15%), where it keeps 13% of its edge. The decisive arithmetic: the rate-card gap at 1.25× costs
  **1.77pp/yr against a measured edge of +2.18pp — 81% of it, and 163% of the full-archive edge.** No signal this
  project measured ever exceeded ~2.5pp/yr net, so the priority order is **desk → leverage → fund → model**, and
  the model is where the fun is rather than the money. Two identities keep it honest: excess must be **exactly**
  zero at w=1.00 for every rate (nothing is borrowed), and `compounded` must return `None` rather than a complex
  number for a destroyed account — the first draft divided two monthly *returns* and reported SPY's benchmark as
  −2.84%/yr.
- **A sealed archive's last month is a stub, so any window statistic that annualises the tail is pricing days that
  were never traded — and a spot rate is the one number that must never be transcribed.** `bill()` annualised the
  last three monthly cash buckets by compounding their mean twelve times. At the 2026-09-04 seal, September held
  four trading days (0.73% annualised, against July's 3.98%), so the spot bill read **2.88% where the curve's own
  last complete month said 3.81% — 103bp of calendar artefact**, and `worth_spot` read **$46.12/mo against a true
  $63.34**, with the percentile reporting 55th ("*below* the median of the record", the file's way of saying this
  is not a good time) when the answer is **65th, above the median** ([note](../notes/2026-09-06-the-seal-is-not-a-month.md)).
  Distribution figures moved by pennies; only the spot and its comparison were wrong. Note the direction: the defect
  **understated** the top-ranked action by 37%, which is why thirteen rounds of reading it produced no alarm —
  a number that flatters the thesis gets challenged, a number that hurts it gets believed. Fixed structurally
  (`cash_months()` drops a trailing bucket whose month has not finished, judged from the calendar, and every
  consumer reads it), and the ledger's first row — which carried `46.12` and "55th percentile" as **source
  literals**, r38's failure mode in the file r38 exists to prevent — is now derived by `rows(data)` on every print,
  re-derived under `--verify`, and pinned by a test asserting the placeholder is still a placeholder. The same
  round re-priced the switch against the sweep it *replaces*: at a desk paying 3.13% by default it is **−$11.91/mo
  over the record** and pays in only 42% of months, with a break-even sweep of **3.82% today, 2.04% in the median
  month** — so the value is in the 2bp, the action is leaving the desk, and the ladder is for someone who won't.
- **After fixing a defect, measure where it was allowed to matter rather than assuming the fix covers the family:
  the statistic class decides, not the size of the bug.** Round 47's partial-month stub lives in
  `withdrawal_capacity.monthly`, called by eight tools; fixing only the site where it was noticed left the other
  seven reading four trading days of September as a month. Diffing every headline with and without it
  ([`monthly_complete`](../../tools/withdrawal_capacity.py),
  [note](../notes/2026-09-06-blast-radius.md)): the guaranteed cheque moves **exactly $0.00** (it is bound by an
  April-2000 window ending 2020 — six years before the stub exists), full-history excess moves **0.003pp** of its
  1.12pp (1 part in 370), the negative-month share moves on the denominator only, the switch's *median* month moves
  under a cent — while the **spot** moved 103bp and the spot-derived action 37%. The rule: a window minimum cannot
  see the tail, full-history compounding dilutes one bucket to nothing, and **anything anchored at the spot is the
  casualty, because a spot is the shortest window you can build and the shortest window runs off the end of the
  data.** One category is genuinely its own: the 16-year excess moved **0.153pp**, fifty times the full-history
  movement, because dropping the stub slides the whole 192-month window a month — r39's era effect entering
  sideways through a calendar artefact, and the reason the leverage recommendation is stated as a range. The rule
  now lives in one module all eight consumers import, and a test asserts it *keeps* the last bucket at a month-end
  seal — a fix that always drops is wrong in the opposite direction. Two tests compare **formula to formula**,
  because after the fix there is no longer a call site that can be patched to reproduce the defect.
- **When two rounds produce the largest actions in the repo, add them to the ledger that claims completeness — and
  re-audit every variance class the new numbers contradict.** `action_ledger.py` says "every action this repository
  has priced"; four rounds after r46 found **710bp** of posted margin spread and r47 found the sweep that eats most
  of the cash switch, neither was a row. Worse, the top row was classified **`none`** for variance while its own
  evidence said **3 cents/mo in 2021, −$1.65 worst month** — the r41 error (a mean dressed as a guarantee) surviving
  in the file that exists to prevent it. Adding the financing row at **$29.58/mo** (0.0710 × 0.25 × $20,000 ÷ 12,
  derived from the rate card, [note](../notes/2026-09-06-ledger-desk-rows.md)) and demoting the cash row leaves
  **3 variance-free actions worth $30.66/mo** — the certain group no longer tops its own table — and the ordering
  argument in the ledger's own units: **deciding *where* to borrow beats deciding *to* borrow**, $29.58 vs the whole
  1.25× tilt's $27.24, needing no simulation, just two rate cards and a multiplication. The distinction that keeps
  the new row `none` while the cash row cannot be: a posted base tier is contractual and banked at any bill yield,
  its condition ("zero if you don't borrow") is under your control; the cash row's condition is the rate cycle, which
  is not. Four tests needed restating and one is the tell — a pre-existing `max(sure) > 30` floor was calibrated to
  the row that moved, so it became an assertion about **which** row tops the group, not how big it is. r29's
  comparison list went empty by construction and is now asserted empty rather than guarded.
- **Print the count next to every minimum, and never take a slope across minima computed on different samples.**
  The guaranteed withdrawal rose from **$333.98 at 25 years to $577.73 at 30** — impossible, since a longer plan must
  survive one more year of the same path. A longer plan can only start *earlier*, so its grid shrinks: 45 starts at
  30y, all 1993–Sep 1996, against 165 at 20y including the 2000s. **The minimum was measuring which decade was
  sampled, not patience.** On one shared 44-start grid it falls monotonically at every step (1,269 → 853 → 690 → 618
  → 581), the only shape the arithmetic allows; the control moves short horizons 2.1× and the 30-year row 0.6%, a
  near-no-op exactly where the grids already coincide, which proves the columns differ by sample and not method
  ([`guarantee(..., until=)`](../../tools/income_accounting.py),
  [note](../notes/2026-09-06-income-ladder.md)). The artefact flattered the *longest, most prudent* plan — the
  direction nobody questions — so the raw non-monotone step is itself pinned by a test, keeping the control from
  being "simplified" away. Same round, same care applied to the objective's own units: inverting every engine for a
  monthly target gives **$137,192** in the index with a sale rule for $500/mo (4.373%/yr, worst of 165 starts,
  linearity verified at $40k/$250k) against **$157,046** for a T-bill ladder at today's 65th-percentile bill and
  **$293,657** at the record median, with **never** in 2021 (−0.00% net of SGOV's 9bp) — so the ladder loses P0 to
  just holding the index *and* carries all the regime risk: **cash income is a decision not to hold equities, priced
  at half the cheque.**
- **A benchmark's sample size is a risk factor, not a footnote — and a required return is a mean, so it cannot price
  a horizon.** The objective names VOO as its bar; VOO's own record has 72 ten-year windows, a median +13.36%/yr and
  a **worst of +11.08%**, because VOO's entire history is 2010 onward — this archive holds no lost decade for that
  ticker, while SPY's 284 windows median +8.79% and reach −3.45% ([`required_edge.py`](../../tools/required_edge.py),
  [note](../notes/2026-09-06-required-edge.md)). The same plan — $50k, $500/mo, principal intact, needing exactly
  12.00%/yr — would have failed in **6 of 72 VOO windows (8%) and 197 of 284 SPY windows (69%)**: an 8%-or-69% risk
  statement decided purely by which ticker's autobiography gets read, so "beats VOO" must be followed by "on a
  record that starts in 2010" or it is not a risk statement at all. Second half: with no contributions and a
  principal floor the recurrence has an exact fixed point, so the required return is **exactly 12×target/capital at
  every horizon from 5 to 30 years** (bisection verified to 1e-6 against the algebra) — length costs a *mean* nothing,
  while r50's *path minimum* falls from $592.97 to $364.45 per $100k over the same stretch. Capitalising VOO's median
  buys $500/mo for **$44,910**; surviving the worst start needs **$137,215** — **3.05× apart, same archive**, and that
  gap *is* sequence risk. Practical consequence measured: at $20k the goal needs +16.64pp over VOO's median (best
  ever measured here: +1.63pp, ten times short); at $50k it needs +12.00%, **less than the index's own median**, so
  no model is required; and $500/mo of contributions makes the required return **exactly zero at any capital**.
- **A withdrawal plan's failure probability must be simulated on paths, never inferred from window returns — and
  check *where* a shortcut's error lands, not just its size.** Round 51 counted windows whose CAGR fell below the
  required return; that proxy is wrong the moment money leaves on a schedule (+30%/−50% vs −50%/+30% share a CAGR and
  end $1,600 apart on the same plan). Simulated monthly with expenses
  ([`plan_survival.py`](../../tools/plan_survival.py), [note](../notes/2026-09-06-simulated-not-averaged.md)):
  **VOO 8% → 36% (understated 4.33×), SPY 69% → 71% (1.02×)**. The error is concentrated on the *friendly* sample —
  because a steadily-rising sample fails not when the average misses the target but when withdrawals land inside a
  drawdown and sell at the bottom, and those windows are exactly the ones a CAGR test marks as passing. An
  approximation whose error is worst where the news is best is the dangerous kind. Same round, three prices for one
  promise, and the third is **not for sale**: on SPY at 10 years, certainty costs **no amount of money** — in the
  worst window the index itself finished below its start, so a level-withdrawal plan cannot either at $5bn; money buys
  a buffer, only a different asset buys a floor. The premium on "always" is itself sample-set: 1.02× (VOO) to 1.57×
  (QQQ) to unreachable. Cross-check: this engine's zero-failure $188,429 vs the guarantee's $137,195 = **1.37×**, and
  the gap is exactly the stricter demand (*finish whole*, not merely *never liquidated*) — pinned as a test, so drift
  in either engine fails loudly. Untested ≠ failed: VOO has no 20-year window, so `p_fail` is `None`, never `inf`.
- **When a remedy's mechanism is orthogonal to the failure mode, its own statistic can move enormously while the
  outcome gets worse — so measure the mechanism, not just the endpoint, and check that a knob can move before
  reporting its effect.** The cash bucket was priced on the archive ([`bucket_plan.py`](../../tools/bucket_plan.py),
  [note](../notes/2026-09-07-the-bucket-priced.md)): forced selling — the month the plan must sell equities because
  cash ran out, the *only* thing a bucket touches — collapsed **237.3 → 0.1 months per window**, and failure rose
  **28% → 32%** at 12mo and **62%** at 60mo; across 36 capital/target/horizon/buffer cells, **no cell reduced
  failure**. Mechanism: the bucket moves *when* you sell, while the failure mode here is cumulative returns facing
  cumulative withdrawals — so the buffer is a permanent short position in the return and hastens the shortfall it
  claims to defer. At $250k the unbuffered plan already never fails (P=0, consistent with r52's $188,429 threshold),
  so the bucket had nothing to protect and only cost to bring. Second lesson, from the policy axis: refill-only and
  two-way **agree to the dollar** at every band because the sweep-back leg *cannot fire* — cash exceeds its target
  only if you are not spending it. An axis with no spread is not a finding about its settings, it is a dead branch.
  Flat-market identity now pinned: the leak is exactly the wrapper's expense, `0.0009 × buffer × years`.
- **When two implementations of one statistic disagree, diff the *conventions* before the code — and never quote a
  withdrawal guarantee without naming which promise it is.** This file's first run missed the capacity engine's
  guarantee by **18.3%**, and neither implementation was wrong: `wc.capacity` has always withdrawn an *inflated*
  cheque (`inflate=0.025`, a default present since the file was written and named in none of the headline numbers),
  and [`allocation_floor.py`](../../tools/allocation_floor.py) withdrew a level one. Match the convention and two
  engines sharing no code agree to **1.2%** ([note](../notes/2026-09-07-the-floor-priced.md)). The convention itself
  is worth **21%** of the headline ($447.73 level vs $368.83 indexed on the same $100k/20y) — more than every
  allocation finding around it. Second finding: the floor *is* bought with bills, and with *some* bills. P(liquidation)
  on $500/mo falls monotonically 10%→0% to 65% bills, guaranteed income peaks **at an interior maximum of +$34.35/mo
  (+9.3%)**, and then the corner turns over — **100% bills guarantees *less* than 0% bills** ($366.06 vs $368.83),
  because SPY's 20-year windows straddle ZIRP (bill factor as low as 0.00001, 1.86%/yr average). Third: the
  cheque and the estate sit at opposite ends of that curve — the income-maximising weight has **P(erasure) = 100%**
  and a 0.40× median ending against 2.10× all-equity. A survival figure that reports only the cashflow is describing
  the consumption of the account.
- **A control that never touches a corrupted leg cannot detect its corruption, and a whole-sample average can be a
  sign flip in disguise.** The short-horizon hypothesis was finally scored ([`trend_cost_test.py`](../../tools/trend_cost_test.py),
  [note](../notes/2026-09-07-the-hypothesis-tested.md)) and the tool was wrong twice before it was right: MA200 at
  **+2036%/yr** (the off-risk leg read `cash_factors`'s daily *factor* as a monthly rate and paid ~190%/yr in bills)
  then **+20.33%** (one day of lookahead: the signal earned the return of the day that produced it), then **8.86%**
  — a **230×** swing, while the buy-and-hold benchmark moved 0.02pp and looked healthy the whole time, because it
  never holds cash. *Validate a new leg against an independent aggregate (`cash_factors` compounded = `wc.monthly`,
  1e-12) before reading any treated arm.* Result at last: six pre-declared rules, 8,457 days, no lookahead, posted
  costs — **all five timing rules lose to plain hold**, and against the fair comparator (the rule's own average
  exposure, held passively with the rest in bills — de-levering is free) four land within ±0.4pp: **no timing value
  anywhere**. But by era the sign flips: +4.47pp/+3.78pp of genuine timing in 1993-2009, then **−3.1pp and −3.3pp in
  2010-2019** — the only span where VOO exists — and −2.6/−3.8pp since 2020. Averaging those is cancellation, not
  summary, and the era the user trades in is the negative one.
- **An overlay that never fires is not evidence of safety, and a control with no information is the only thing that
  makes a risk-reduction claim honest.** Cross-sectional rotation ([`rotation_edge.py`](../../tools/rotation_edge.py),
  [note](../notes/2026-09-07-the-switch-was-disconnected.md)): 10 sleeves, common window 2006-02→2026-09 (5,177 days,
  set by the thinnest sleeve), month-end signals, four pre-declared rules. **First version ranked by growth *factor*
  and compared it to a net *return*** — monotone, so every CAGR and drawdown stayed correct, but the absolute-momentum
  overlay asked "is 0.64 > 0.014?" and so **never fired in 235 signals across a window containing 2008**, showing
  IWM at "+66.5%" in December 2008 on the way out. Fixed, it halves the drawdown, so the bug had disabled the one
  component producing the entire benefit. Results: `rs_top1` 10.72% / DD **61.7%** / −0.43pp vs SPY hold (11.15%, DD
  55.2%) — **more risk, less return, 90bp/yr of costs buy-and-hold does not pay**; `dual_top1` 10.19% / DD **29.3%**,
  the only real result, bought with −0.96pp — and **`static_60_40`, which computes nothing and trades once a month,
  reproduces DD 30.1% at 0.0010%/yr**: the news-and-trend machine's whole risk benefit is available from an
  allocation chosen asleep, at an eighth of the cost. Expense assumption is not load-bearing (doubling unposted ERs
  moves each rule 0.12–0.14pp, ordering identical, all still lose). By era the r55 pattern repeats exactly: every
  rule beats SPY in 2006-2009 (dual +7.47pp) and loses in 2010-2019 (dual **−4.94pp**) — crisis-exit devices billed
  as alpha, and the whole-window average is their sum, not a description of either.
- **The frequency axis belongs to the engine, not to each caller that remembers it, and a negative slice start is a
  silent redefinition of a signal.** [`frequency_cost.py`](../../tools/frequency_cost.py) swept the one thing the
  objective actually specifies — how often the model acts — across six frequencies with the information held fixed
  ([note](../notes/2026-09-07-the-frequency-axis.md)). **Both families peak at monthly.** MA200's GROSS spans
  **1.15pp across the whole axis with no trend** (annual 9.01% vs daily 8.86%): a 200-day average is the same number
  however often you look, so everything that moves with frequency is the invoice (cost/yr ×16) and the drawdown, which
  *improves* 38.9%→19.7% — the sensation of short-term trading working comes from the smoothness column while the
  payment lands in the return column. Momentum is worse: gross falls 10.29%→7.53% (monthly→daily), so **2.76pp of the
  loss is the information degrading, not the bill growing**; net 6.86%, **4.88% at 4× slippage against 11.15% for
  doing nothing**, and the drawdown worsens (29.3%→40.1%). The test suite caught a real defect the review missed:
  `signal_days("daily")` skipped the warm-up gate, so `rets[i-251:i+1]` on a young list **clamped to zero** and the
  first daily signals were one-to-a-handful-day rankings sold as 12-month evidence; after the fix the row moved
  0.02pp — *a defect that changes nothing you are looking at is exactly the kind that survives review.*
- **Two rows that agree to the cent are a bug report, and `.get(key, default)` on keys built somewhere else is a
  silent failure mode.** The objective's two halves finally shared a table ([`monthly_income_race.py`](../../tools/monthly_income_race.py),
  [note](../notes/2026-09-07-two-halves-one-table.md)): $100k, 10y, 5% failure budget, four legs at monthly, four bill
  weights, one sample for all of them. **MA200 pays $593.13/mo against the index's $435.47 (+36%) and ends at 1.35x
  against 2.32x — the two halves are both true of the same account** — but a static 60/40 pays **$569.45**, so of the
  trend rule's +$157.66, **$133.98 (85%) is the bond leg and $23.68/mo is the model**; the rotation leg is $44/mo
  *worse* than the asleep control. Bills raise income only when the equity leg is a trend rule (for the index:
  435→378→297→235, failing 17/24/67% at the index's own payout), inverting r54 because that cheque was *indexed* over
  20y and this plan is *nominal* over 10y in the flattest rate era on record. Long record, two promises: plain equity
  prices at **$0.00 under "ends whole"** — SPY breaks that promise in 8% of 10y windows with nothing withdrawn — vs
  $763.82 under "never zero", and MA200 at $557.91/$1,098.43. Bugs: a `(year,month)`-keyed dict read with `date` keys,
  every miss defaulted to "hold cash", so the long-history trend row printed **$31.04 — the same figure as the row
  below it, which is the only reason it was caught**; and a month-end mark map written `i+1` then `-1`, putting all 246
  marks one trading day late, caught by the compounding identity, not by anyone reading the table.
- **A stuck switch and a working one look identical in a headline number, so report the duty cycle; and an era split
  on the *income* metric is the one a plan actually needs.** The objective's "global news" premise was tested with the
  only macro series the archive holds — the DGS3MO bill yield itself, 0.011%–6.89% annualised, now 3.87%
  ([`rates_gate.py`](../../tools/rates_gate.py), [note](../notes/2026-09-07-the-only-macro-series.md)). Four
  pre-declared gates, 403 months, scored at round 58's fixed $435.47/mo: **`yield_gate` fails 49% against the index's
  20%** and gives up 3.3pp of CAGR for under 2pp of drawdown; `tightening_exit` fires off only 10% of months and so has
  a max DD *identical* to the index's (50.8%) — a rule that rarely trades cannot claim credit for calm markets.
  **Combining the macro gate with MA200 subtracts**: $332.75/mo vs $557.91 alone, 18% failure vs 0% — while buying the
  repository's lowest drawdown (16.2%), the fifth straight round where a signal's risk benefit is available cheaper by
  allocating. The era split is the round's point: MA200 beats the index by 36pp and 24pp in windows started
  1993-2004 and 2005-2015 and **loses by 17pp in 2016-onward (17% vs 0%, n=69)** — so round 58's "+36% income" is a
  property of the decades it includes, now measured on the metric the plan lives on. Convention priced rather than
  disclaimed: monthly vs daily expense = **0.027pp of CAGR and $6.38/mo (1.5%)** on the same sleeve and months.
- **A plan's verdict depends on which end of the account you measure it from, so name the cash-flow direction before
  quoting a number.** Rounds 52/54/58 priced withdrawals from a lump sum; this objective is a monthly contribution
  into a still-growing account, which is a different question and gets the opposite answer
  ([`contribution_race.py`](../../tools/contribution_race.py), [note](../notes/2026-09-07-money-going-in.md)).
  $20k start + $1,000/mo for 10y on the same panel and legs where round 58 found +36% income: **MA200 ends $502.43/mo
  *smaller* than the index** ($242,302 vs $302,594 median, 1.731× vs 2.161× of contributions), and all three
  alternatives lose. The rule converts growth into sequence protection, and a contributor does not want sequence
  protection — a crash is a purchase — so they pay the 1.73pp and use none of the benefit. The advantage is **exactly
  linear in capital** (tested: ratio 2.000 at 200k/100k, 5.000 at 250k/50k), so "a bot that earns me extra monthly" has
  no answer without a capital figure: the 15-cell grid runs −$159 to −$2,485/mo and **no capital tested up to $250k
  clears even $25/mo**. The one thing the model wins in this frame is the tail: on the long record **4.2% of 10-year
  windows left a plain-equity contributor with less than they deposited, and the trend rule has no such window** — and
  it costs $58.66/mo on the median to buy that, an order of magnitude less than the panel implies, because on 2006+ no
  contributor ever lost and the risk lives in the decades the panel cannot see.
- **Calibrate a screening tool on a planted edge before believing its "no", and score *excess* return against a null,
  never raw.** 28 configurations were evaluated in rounds 55-60 and each round named a winner; none checked whether
  the winner was the luckiest of 28 ([`deflated_edge.py`](../../tools/deflated_edge.py),
  [note](../notes/2026-09-07-nothing-to-select.md)). Block-bootstrap Reality Check, 2000 circular 12-month draws over
  the 246 common months, **calibrated first**: 26 columns of pure noise give p = 0.64, the same field with one column
  planted at +1.2%/mo gives p = 0.000 and names the right column. On the archive the **raw**-return test comes back
  p = 0.000 with best Sharpe 0.95 / DSR 0.916 — and it is worth nothing, because every column is long equity all 246
  months, so it measured the equity premium the benchmark also earns (0.78) and can be bought for 0.03%/yr. Against the
  benchmark (**the objective's actual question**): 26 columns, best information ratio **−0.01** (`rs_top1`), its DSR
  0.002, Reality-Check **p = 0.981**, and **0 of 26 configurations above zero** — so there is no selection luck to
  correct, because there is nothing to select; the six rounds of negatives are consistent with an empty null, not a
  broken search. The mean-excess test cannot see r58's income advantage or r60's 4.2%-vs-0% tail, which are shape
  claims and stand. Caught by the calibration: the observed statistic had been computed on **centred** series, making
  every p-value exactly 1.000 while the output looked like a normal negative; and one merged month-map would have made
  all 28 columns identical, caught by a new guard that then correctly fired on a real tie (`dual_top1` and
  `mom_top1@monthly` realise one path) and had to be re-expressed as multiplicity — threshold set by **27 distinct
  paths**, not 28 labels.
- **Score a risk claim as a 2x2 against the thing it is supposed to protect, and then look up how many episodes
  produced the cell.** An average over 283 windows is the wrong statistic for someone who lives one entry, so every
  entry month was scored separately ([`entry_state.py`](../../tools/entry_state.py),
  [note](../notes/2026-09-07-the-two-by-two.md)). $435.47/mo from $100k over 10y, 283 starts: the index plan fails in
  **56 (19.8%)**; MA200 monthly has **insurance 56, redundant 0, cost 0**, P(fail) 0.0% — it saved every entry the
  index broke and failed in none the index survived — while **static 60/40 has 0 insurance, shares all 56, and adds 65
  failures of its own (42.8%)**, and `ma200_and_gate` converts 11 saves into redundancies plus 34 fresh failures. In
  the contribution frame the rule saves all 12 index failures, the 60/40 only 3 (concordance 75%). The neatness was
  doubted before publishing: the payout ladder moves the zero immediately (0 at $435.47, **33 at $600**, 134 at $800,
  262 at $1,100), direct counts match the cells, and round 60's 4.2% reappears from a second implementation. The
  caveat that decides how much to read into it: **all 56 failing entries run 1998-02 to 2007-07 and 96% of them began
  in 1998-2002.** One episode, one protection — and since 2007 the index plan at this payout has never broken, which is
  the same fact round 59 saw as the rule losing the 2016-onward era.
- **A difference between two legs is a point on a curve, not a fact — say which intercept you read, and price
  insurance as a capacity.** Rounds 58 (+36% income), 60 (−17% wealth) and 62 (free and perfect at $435) were one
  curve sampled at three points, so the payout was swept over every window ([`insurance_breakeven.py`](../../tools/
  insurance_breakeven.py), [note](../notes/2026-09-07-the-capacity-of-insurance.md)). Median difference vs the index,
  $/mo per $100k: whole record **+$234.67 at zero withdrawal**, +$163.33 at $435.47, +$52.83 at $1,000; since 2006
  **−$687.29 / −$551.57 / −$365.98**; 1993-2005 +$587 / +$540 / +$435. **The sign is set by which crashed decade is in
  the sample, not by how much is withdrawn** — there is no payout that makes the rule a winner since 2006 and none that
  makes it a loser over the full record. What *is* stable: the protection has a **capacity** — the rule is the safer leg
  to **$825/mo per $100k** ($2,063 on $250k, $4,125 on $500k, homogeneity verified) and the riskier leg above it (85.5%
  vs 69.3% failure at $1,000), because lower average growth means a large withdrawal outruns the shelter; the bond
  sleeve that round 56 recommended as the cheaper alternative holds a **third** of that capacity ($275-325) and is
  never ahead on the median at any payout. And the reporting trap this file exists to record: round 58's **+$157.66**
  was the *horizontal* intercept (each leg's own maximum withdrawal at one failure budget) and this round's **−$551.57**
  is the *vertical* gap at a payout the index funds — both true, opposite signs, same curve.
- **Measure a conditional holding period, not a whole history — and never score an unposted expense ratio as zero.**
  The trend rule parks 25% of days in bills, so the shelter was changed and nothing else ([`shelter_test.py`](../../tools/
  shelter_test.py), [note](../notes/2026-09-07-where-the-rule-parks.md)). Round 58's cash row had to reproduce **$593.13**
  before any delta meant anything; it did, to the cent. Shelters, at the pessimal fee: IEF **+$64.03/mo** of extra
  withdrawal capacity, IEF+TLT +$82.25, TLT **+$90.20**, GLD **+$223.50**, DBC **−$239.20 with P(fail) 22.8%** — all
  signs stable across 0.20/0.35/0.60% because `tc.daily_legs` returns `0.0` for anything unposted (r58's failure mode,
  live in the plumbing). The unconditional returns rank them **TLT 2.75% < IEF 3.21%** while the income ranks them the
  other way; what ranks every pair correctly is the return **while the signal holds it** (DBC −8.51% < IEF 7.40% < TLT
  8.23% < GLD 11.94%), and every shelter but commodities paid *more* while held than over its history with *less*
  drawdown — because a month-end MA200 exit is a stress detector and stress is when bonds and gold rally. So the
  shelter's quality is a property of the signal's timing, not of the asset class, and it cannot be carried into another
  strategy. GLD's win is a second bet (29.4% drawdown while held). The boundary that matters more than any fee: IEF/TLT
  start 2002-07 and GLD 2004-11, while round 62's plan-breaking entries are 1998-02 onward — the shelter is priced for
  the twenty years it has been quotable, not for the crash it was proposed for.
- **A capacity belongs to the whole construction, not to the signal — re-measure it after changing either end of the
  account, and let a scan report its own wobble.** Round 63's ceiling was quoted for the trend rule with a cash shelter
  and re-measured here under the round-64 shelter, same panel, same 127 windows ([`shelter_test.py`](../../tools/
  shelter_test.py), [note](../notes/2026-09-07-the-ceiling-belongs-to-the-construction.md)): bills **$725** → IEF
  **$775** (+2 rungs of $25, a 7% lift, on top of +$64/mo of income) → GLD **$925** (+24%, same second bet as always) →
  DBC **$225** (−20 rungs). Reconciled rather than papered over: round 63's $750 and this round's $725 for the *same*
  construction differ because one sample selects starts by year from the long record (129) and the other from the panel
  (127) — if they had agreed exactly, that would have been the bug. Two mechanisms the first draft got wrong: the scan
  **raised** when the ordering flipped back, but P(fail) over 127 windows is a step function in rungs of 1/127 and two
  steep curves can step over each other — TLT and IEF+TLT flip **3 times** each, now printed in the row rather than
  smoothed; and the sweep must stop once the benchmark fails everywhere, or it will report a ceiling where there is
  nothing left to be safer than. Also quoted honestly: at those rungs the plan already fails 25-35% of the time, so a
  capacity is where the argument turns, not a comfort zone.
- **A backtest's start date is a position, not a neutral boundary — and a record's length is chosen by whoever wrote the
  neighbouring tool, not by the question.** Round 64's shelter test ran from 2006 because `rotation_edge.panel` is
  shortened by DBC, though a two-asset plan needs only SPY, the shelter and the bill curve; [`shelter_long_record.py`](
  ../../tools/shelter_long_record.py) builds its own engine from 2002-08 and gets 169 ten-year windows instead of 127
  ([note](../notes/2026-09-07-the-record-was-too-short.md)). Its engine reproduces round 58's **$593.13** exactly when
  handed round 58's weights, which is what licensed what came next: read four ways on that same window, the same rule
  supports **467.07 / 489.62 / 527.08 / 593.13**, a $60/mo span (13%) whose highest cell is the one published since
  round 58 — because `signal_days(monthly)` cannot fire until index 200, so the rule sits in cash by fiat until
  **2007-02-28** and is handed an entry point worth more than any shelter gain found in rounds 64-65. On the longer
  record the shelter verdicts split: **IEF** +$73.12 (month-start) and +$50.73 (month-end), positive under both
  conventions, both records and every fee — the only shelter whose case does not depend on a reading; **TLT's promotion
  is withdrawn** (+$9.13 under the conservative reading, below round 60's bar, **−0.58% while held** and a 41.4% held
  drawdown, against the panel's +$90.20); GLD +$146 to +$184 on 142 windows, still a second bet. Duty cycle quoted with
  its sample: 19.6% on this record against round 64's 25%.
- **A hedge's insurance cell is bounded by how often the thing it hedges fails — so name the payout band it applies to,
  and check that the frame you scored it in has any failures at all.** Round 62's 56/0/0 was re-scored on round 66's
  2002-on record ([`shelter_long_record.py](../../tools/shelter_long_record.py) `--grid`,
  [note](../notes/2026-09-07-three-months-of-work.md)): in round 62's own contribution frame **nothing fails anywhere**
  (0 of 169), so the claim is untestable there — it needs the withdrawal frame. At the published $435.47 the claim holds
  exactly (7 insurance / 0 redundant / 0 cost, concordance 0%) and the entries covered are **2003-04-04 to 2003-04-23**:
  three adjacent months, not 56 spread across a decade, because the dot-com lost decade is outside this record. Raising
  the withdrawal to $700 gives the hedge 42 entries to cover and shows what the shelter buys in the *risk* frame
  (IEF: insurance 11→42, cost 23→12, own failure 49.7%→24.9%); at $900 the insurance cell is empty for every leg and the
  hedge is pure cost, which is rounds 63/65's capacity in round 62's table. Shape worth keeping: the insurance cell is a
  **hump in the withdrawal, not a slope** — `[7, 42, 0]` across those three payouts — and two of my own test drafts
  asserted a monotone narrowing before measuring. GLD is dropped from the grid rather than paired by row number against a
  longer record.
- **Name the axis "beat" is measured on, score each construction against the comparator over exactly its own dates, and
  never infer a static hedge's sign from a dynamic one's.** [`correction_table.py`](../../tools/correction_table.py)
  re-measured every published income claim after round 66's convention finding, on both records and both readings
  ([note](../notes/2026-09-07-the-axis-and-the-static-hedge.md)). The flagship premium over the index is **+$130.46 to
  +$144.88/mo per $100k** in the honest cell (MA200 + IEF, long record, either convention) — about a third of the
  $157.66 quoted since round 58, and $54-92 with a bill shelter on the panel. New and uncomfortable: **a static 60/40
  with the bond half in bills supports $83.53 LESS than plain VOO and fails in 30.2% of windows against the index's
  4.1%**, so the repository's standing "cautious alternative" has negative capacity — while the identical weights with
  the off-equity half in IEF reach +$62.21, 0.0% failure and $575 of capacity with no signal at all. The two P(fail)
  columns explain how a rule that loses on return (round 61, 0 of 26) wins here: it removes the order returns arrive in,
  failing in none of 169 windows where the index fails in seven. Self-check kept: the table's index row on the panel
  returns **$435.47**, which is round 58's payout, the same number by construction.
- **A path no live model exercises is an untested path, and a reimplementation of a measured rule needs a differential
  test against the original.** The forward book was running the candidate rounds 25-32 concluded loses while the
  construction rounds 55-68 settled on had no forward record, so it was brought to the belief ([note](
  ../notes/2026-09-07-the-book-that-could-not-sell.md)) and found unable to sell: `orders_for` issued signed quantities and
  the applier negated them again, so a SELL of a whole position **doubled** it — 65.72939881 units of IEF recorded as
  131.45879762. Latent for the book's whole life because every model in it had held one symbol and never wanted out.
  Three more went with it: one global expense ratio under-charged an unposted-fee shelter by ~4x (now per-symbol, with
  the labelled flat 35 bps and a refusal on unknown symbols), a closed sleeve re-sealed as a `0.00000000`-unit holding,
  and `BORROW_SPREAD` finally pinned at the 0.0202 paper.py had been demanding since round 30 — legal only at an anchor.
  And my own first draft read the trend on the prior month's *last* day, i.e. the friendlier of round 66's two readings:
  the day-by-day differential test against `shelter_long_record` failed on 2023-01-03 and caught it before it became a
  flattering forward record.
- **One construction per book, comparable only if everything except the model is shared, and a report's benchmark comes
  from the same anchor config the executor reads.** Round 69's supersession left the repository's only positively-measured
  plan — constant 1.25×, +1.63%/yr full record — with no forward chain, so `paper.py` gained `--book` and `compare`
  ([note](../notes/2026-09-07-two-books-one-quote.md)). The invariant that makes two books worth comparing is asserted, not
  assumed: identical deposits and quotes have to produce an **identical witness** (5,497.92 for both at the May 2025
  rehearsal), one book's step leaves the other's chain byte-identical, and a tampered anchor prints `BROKEN` rather than
  being skipped. Rehearsal worth remembering: the financed book paid 6.47 against the sheltered book's 3.26 in one month
  and finished −4.39 versus −1.18 against doing-nothing — rounds 29/30's financing finding in a single fee line. Two fixes
  came with it: `command_report` had been rebuilding its comparator from literals while `step` read it from config, and my
  own test assumed `invested` reveals leverage when it is capped at own cash on purpose — gross exposure and the sealed
  borrow line are what say whether a book is levered.
- **The artifact a person acts on must be regenerated from the measurement, not restated — and it must be able to refuse.**
  The repository's user-facing sheet still recommended the levered plan rounds 29-30 withdrew, fifty rounds of drift that
  nobody noticed because no one had to act on it. [`shelter_ticket.py`](../../tools/shelter_ticket.py) now prints the
  settled construction's decision and its numbers at any capital, importing `correction_table.measure` and
  `paper.shelter_weights` rather than restating them, and exits 3 when it refuses ([note](
  ../notes/2026-09-07-the-ticket-that-can-say-no.md)). Writing it found four bugs: a default payout in per-$100k units
  tested against a scaled ceiling (the sheet refused itself at half capital); measurement taken at the caller's capital and
  then scaled again (figures here are **not** linear in capital — the promise has an absolute floor, so scaling is a claim
  and belongs in one place); `paper.shelter_weights` defaulting a **missing reading to "shelter"**, i.e. round 45's
  artefact inside the live rule's failure mode, now a refusal; and a sheet printing "trend read 2026-09-04" when the reading
  was **2026-08-03** — a decision that can't name its own price can't be audited. At $250,000 the sheet says $1,418.06/mo
  against the index's $1,091.90 (+30% at every size, ceiling $1,937.50), and the shelter's worth over cash reproduces round
  66's $73.12 to a cent from a new path. The old ticket is kept, banner and all: the desk table is the only posted-rate
  evidence here, and deleting a wrong recommendation destroys the record of why it was wrong.
- **A conditional test is priced as a paired plan difference through the same cost engine, and the classifier reads `n`
  before it reads magnitude.** Round 18 refuted attention as a *signal*; the objective's other claim — that news tells you
  when the **rule** is about to be wrong — is a veto, and [`news_veto.py`](../../tools/news_veto.py) priced it over 128
  months, both readings, three thresholds, round 18's control basket at every cell
  ([note](../notes/2026-09-07-the-veto-the-news-would-have-paid-for.md)): **all six cells negative**, −$7 to −$498/mo per
  $100k, because the months an attention spike would have stepped aside from averaged **+2.35% to +12.69%** in equities —
  attention peaks with rallies, so the veto sells into strength. H3 died too: mean |z| at the rule's 19 turns was 0.70
  against 0.63 overall, so no switch-cost saving either. Three apparatus failures preceded the answer. A valuation
  *formula* credited the veto with the profit of the exposure it removed and ignored the shelter's fee — both plans now run
  through the engine and the answer is the mean paired difference, which also needs no windows. A one-month cell (θ=1.5,
  a single April, +12.69%) graded as **CANDIDATE worth $1,057/mo** because the control clause compares magnitudes and a
  one-month magnitude is enormous — `MIN_MONTHS = 12` now reads `n` first. And the corpus boundary was **verified, not
  remembered**: Wikimedia's Analytics API begins 2015-07-01, the legacy 2008-2016 endpoint counts differently, and splicing
  it would revise the series in place, breaking round 18's never-revised property — so the news half is permanently
  untestable at a ten-year horizon on lawful data, and the tool prints `UNRESOLVABLE` above its own plan-level figures.
- **A premium must be scored per fund against that fund's own posted fee and its own history, on a window every candidate
  shares — and its sign must be explained by the hedge's payout band, not by the ticker.** The objective named VOO and QQQ
  and the evidence was one fund; the sweep found `correction_table.measure` charging every row the **SPY** fee, so a QQQ or
  VOO row was misprised in the one cost both arms share. With `measure(..., sleeve=)` looking the fee up by symbol and
  refusing unposted ones, [`sleeve_table.py`](../../tools/sleeve_table.py) scored 18 rows
  ([note](../notes/2026-09-07-the-premium-belongs-to-the-window.md)): on the window all five funds share (2011-06-24, set by
  the youngest fund's own warmup) **every US sleeve loses to holding the fund** — −$155.72 to −$191.47, agreeing within
  $12.59 — while their own records pay +$130.46 to +$183.77, a spread of $53.31. Funds agree to tens of dollars, windows
  disagree by hundreds: round 66's warning about record length turned on this repository's own headline. One law covers all
  18 rows and is pinned as a test: **a row pays a premium exactly when the plain fund failed ≥1 window** (the one
  month-end exception, QQQ panel +$13.91, is under the $25 bar and is pinned by name and size). VOO's honest record *is*
  the common window — the fund started in 2010 — so the only defensible 2002-on VOO answer is a labelled proxy (SPY's path,
  VOO's fee: +$129.82, i.e. the whole fee gap is worth **$0.64/mo**). QQQ loses on every window at both conventions
  (−$25.47 to −$315.13). `carry` also opens a record **sheltered** when the fund's own average doesn't exist yet — round 45's
  artefact one level down, now guarded by `since >= that fund's 201st session`. The ticket must print all three windows and
  `--record recent` refuses: "loses to holding the fund itself by 159.06/mo". Binding constraint for the next rounds: the
  **recent** window, where the current construction is a ~$160/mo cost per $100k, not a premium.
- **A rule search must be pre-registered with a two-window pass rule, differentially tested for lookahead, and forced to
  print its own family spread — and "trades less" is not "costs less" until you name what the cost is.** Round 73's binding
  constraint was the recent window, so [`rule_search.py`](../../tools/rule_search.py) priced nine rules chosen to attack how
  the incumbent loses there, with the grid and the pass rule (bar on **long AND recent**, both readings) written before the
  first run ([note](../notes/2026-09-07-nine-rules-and-the-window-that-refuses-them.md)). **0 of 9 clear it** −$111.05 to
  −$457.82, spread $346.77. The reason is arithmetic, not mood: on that window the fund failed **0.0%** of windows, so no
  insurance pays and all capacity must come from return — while every one of these rules sits in near-zero-yield Treasuries
  through the index's best fifteen years. Together with round 61 (0 of 26 on return) that closes the design space from both
  sides: *single fund + shelter, monthly, unlevered, posted costs* cannot beat plain DCA recently. Secondary findings, each
  pinned: `ma200_slope` earns **+$331.23** on the long record against the incumbent's +$130.46 at half the duty and 10
  switches instead of 24 — so "the current rule" is no longer defensible as *the* trend rule, even though it fails the
  recent window; the ±2% hysteresis band cut switches 24→14 and made the recent window **worse** (−$159.06 → −$257.88),
  because the cost is months out of the market, not trades; vol targeting is the dearest way to hold less (−$435.76, 66
  switches). The tests pin the method, not the ranking: each month's decision recomputed from a record truncated at that
  month's reading day (9 rules × 7 months), a flat-price synthetic pinning a chatty plan to `(1−2 bps)^40`, a fully invested
  plan tied to its comparator to the cent, and per-rule warmups (21/50/100/200/231/252) so a fast rule is not accused and a
  slow one not forgiven.
- **A search's pass rule must be tested against a no-decision control, and a hand-rolled copy of a decision lag is a
  lookahead bug waiting for the convention that exposes it.** Round 74's conclusion (no shelter can beat the fund on the
  recent window, because nothing pays out there) meant the constraint had to change, so
  [`rotation_search.py`](../../tools/rotation_search.py) priced seven pre-registered rows on one shared calendar
  ([note](../notes/2026-09-07-the-rotation-that-a-control-beat.md)). **`dm12_sq` became the first row in this repository's
  history to clear the $25 bar against plain DCA on both windows (+$406.28 long, +$88.29 recent, both readings)** — and the
  static 50/50 control, which involves no decision, beats it by **$94.35** on the recent window, while plain QQQ beats it by
  $261.83 there and earns +$350.12 itself. So the finding is *a growth tilt, with the trend overlay paying for crashes it
  must not use in a bull decade*; the control clause was added **after** the run and says so in the docstring, with the
  pre-registered verdict still printed beside it. `dm12_wide` is +$82.97 at month-start and **−$243.91** at month-end on the
  same window — a $327 swing from a calendar day, and the only row whose sign flips; the controls are identical in both
  columns, asserted, because a control that moves with the reading means the pricing is broken. The bug: `weights_for` read
  the **current** month's mark from its second session, which is lookahead under end-of-month readings; it now delegates to
  `carry`, and the corrected lag cost the winner $46/mo of its recent premium — had the bug flattered the result instead, the
  note would be recommending an untradeable strategy. `multi_asset_path` generalises `two_asset_path` charging turnover as
  the **sum of positive weight changes** (one charge per purchase — the same convention, so rounds 61-74 stand): the
  differential test reproduces the published MA200/IEF record to 1e-15 over 5,000 sessions, and the one documented
  divergence (a record opening in the shelter, one switch charge) is constructed in its own test.
- **A declared hypothesis must be priced against the control it amends, not against the index, and an inert clause must be
  named as inert.** Round 75 wrote down its own successor — a growth tilt with a trend brake — and
  [`tilt_brake.py`](../../tools/tilt_brake.py) priced four pre-registered variants against the static 50/50 blend itself
  ([note](../notes/2026-09-07-the-amendment-that-cannot-pay-for-itself.md)). **0 of 4 pass: −$112.95 to −$223.08/mo per
  $100k on the recent window** against a row that asks nothing of anyone, worth +$8.08 to +$60.92 on the crash-containing
  one — insurance, again, priced three ways now (hedges r73-74, selection r75, a brake here, same sign every time, the loss
  tracking time out of equity). **The tail clause could not fire and that is the finding**: at the published payout every
  brake and the control have P(fail) = 0.0% over 132 and 63 windows, so the measure cannot see a brake's benefit while
  charging its cost; the clause's only work on the page is catching plain SPY at **+5.3%**, which says the improvement in the
  tail comes from *diversifying styles*, not from timing them. Pinned: the brake is fully sheltered in October 2008 and May
  2020 and **unsheltered in March 2020** — a monthly MA200 cannot see a one-month collapse, asserted rather than looked
  away from; the two tools cancel to the cent on the row they both price (−$154.18 here, +$154.18 in r75), because a shared
  helper drifting under one tool is the failure mode nobody sees; and Treasury-vs-cash braking **reverses** between windows,
  the shelter having lost money to rising rates over the last fifteen years.
- **An inert risk clause is not a verdict on the risk — re-ask the question at a payout that binds, publish raw window
  counts instead of intervals on overlapping samples, and never hand a scale to a function expecting dollars.** Round 76's
  tail clause read 0.0% for everything because at $435.47/mo nothing holding growth fails;
  [`binding_payout.py`](../../tools/binding_payout.py) repriced the same six books at 0.90x–2.00x of the **control's** capacity, with a
  pre-registered rule allowing a claim only at ≤1.25x ([note](../notes/2026-09-07-the-payout-level-that-makes-risk-cost-something.md)).
  The clause is now the most informative line on the page — `brake_either` fails 6 of 132 windows where the blend fails 22,
  `dm12_sq` and plain QQQ 0 — but the protection is worth nothing on the recent record, where the brakes fail on 77.8% and
  54.0% at the control's own capacity and their capacity is 0.798x/0.849x of it. `dm12_sq` **dominates** the control on the
  long record (1.428x capacity, 0 failures through 1.25x) and loses on the recent one (0.914x, 28.6%): the same code, the
  window deciding. Plain QQQ outranks the "diversified" blend on capacity *and* tail on both windows — with the caveat
  asserted in the test, that the shared calendar starts 2005-09-06 and never touches 2000-02, where that fund's tail lives.
  Plain SPY is the floor: the only row failing at 0.90x, the lowest capacity on the page, and the objective's own benchmark.
  Two methods notes: the first version of this tool passed the multiples themselves as payout dollars and printed a table of
  plausible 0.0% cells, so a test now requires a failure at 2.00x and monotonicity in the withdrawal; and no confidence
  interval is published on the counts, because 132 overlapping ten-year windows are not 132 trials.
- **Move the sample before you believe a ranking, and let the start date be the data's limit rather than an outcome.**
  Round 77's QQQ result rested on a calendar starting 2005-09-06, chosen by the youngest leg of a five-asset pool, so the
  growth index's own −82% collapse was in none of the windows measured; [`mix_sweep.py`](../../tools/mix_sweep.py) re-scored
  the same family from **1999-12-22** — QQQ's first day plus the engine's own 200-day warmup, the earliest this family can be
  scored, printed not chosen ([note](../notes/2026-09-07-the-budget-that-only-a-brake-can-meet.md)). **Zero of five static
  mixes meet a 5% failure budget at any payout**: pushed down to **$1/mo** they still fail on 5.5%–7.0% of ten-year windows,
  monotonically worse with more growth, worst drawdown −55.2% → −83.0%. Every comfortable 0.0% in rounds 75-77 was a property
  of a benign start date. The ranking inverts: **the only rows that fund the record at all are the two cash-braked ones**
  ($458.06 and $466.68/mo, drawdown −30.9%/−30.8%) — the first construction in this repository that the risk measure
  *requires* rather than permits, at 0.42x of the withdrawal the recent window supports and 86.6% failure at that withdrawal
  (at $1,101/mo everything fails; the brake just has less return to rescue it). The gap between the two positions — about
  2.4x in capacity — is the price of the budget, and is the round's real product. Discipline held: the brake parks in cash so
  no shelter's warmup truncates the tail under test (`dm12_sq` excluded from this grid for that reason, priced in r77), the
  recent window reproduces $919.02 / $1,101.66 / $1,269.14 by differential against `binding_payout.py` rather than by being
  typed in, and a test asserts the −82% episode is inside the window so a grid testing the wrong decade cannot pass.
- **A body of measured evidence needs a sheet that can refuse, and a sheet's honesty is testable: no typed figures, every
  printed number traceable, every refusal path exercised.** After 78 rounds the repository had four grids disagreeing
  informatively and no page stating what to do; [`decision_sheet.py`](../../tools/decision_sheet.py) applies round 71's rule
  to the whole body of work ([note](../notes/2026-09-07-the-sheet-that-can-say-no.md)) — two positions side by side (income:
  the growth tilt, $1,269.14/mo per $100k recent capacity; insurance: the braked tilt, the only book funding the deep record,
  $466.68/mo, **2.40x less at matched weights**), a withdrawal priced at *exactly* the dollar asked on a fresh path, and four
  refusals with reasons and exit code 3 (news veto, intraday, options, single names) — the same four the archive imposes.
  Discipline is now mechanical, not aspirational: a regex fails the build if a dollar literal is ever typed into the sheet;
  every figure on the rendered page must exist in the data the renderer was handed (both signs, with a minimum-figure guard so
  the check cannot pass vacuously); each section names its source tool; everything scales linearly in capital; the header's
  date is differential-tested against the archive; and block 2's four figures are differential-tested against
  `rotation_search.grid`. What the sheet inherits it names too — flat 35 bps on three sleeves, month-start readings, ten-year
  windows, a 5% budget, 2 bps turnover, no taxes, no impact — because a sheet is no more honest than the grids under it, only
  more legible, and legibility was what was missing.
- **Before crediting a schedule with a gain, measure it against the spread of the family it was chosen from and against the
  anchoring choice that defines it — on this archive cadence is noise, not edge.** The objective says *short term* and every
  rule so far read monthly, so [`cadence_sweep.py`](../../tools/cadence_sweep.py) removed the schedule constraint while
  holding signals, costs, windows and the lag fixed, via `sl.cadence_carry`, differentially tested against `sl.carry` to the
  last day ([note](../notes/2026-09-07-how-often-to-decide-and-what-it-costs.md)). Two findings and one bug class. **Faster is
  worse where the risk is:** on the record with the tail the brake funds $510.09 weekly, $638.09 every 21 days and $307.87
  quarterly; rot12 funds $432.76 weekly and $136.98 quarterly, and no schedule approaches the static books. **Five of ten
  schedules clear the $25.00/mo pre-registered bar; zero clear the family spread they were selected from** ($212.71 and
  $241.56/mo), so the gains — +$25.64 to +$107.03 — are 12%–50% of their own selection noise. And the killer: the *same*
  signal on the *same* 21-day rhythm funded $939.89 recent / $458.06 deep when anchored to the calendar month (r78) against
  $873.94 / $638.09 when anchored to every 21st day — **anchoring, a choice with no economic content, moves capacity 2–8x more
  than every schedule effect in the table.** The bug class closed on the way: a scheduled day that declines to answer (`None`,
  hold) is not a day that says sell everything (`{}`, flat) — conflating them lets a missing reading sell the portfolio, which
  is worse than round 75's lookahead because it looks conservative. The report prints its own refutation: the anchoring line,
  the family spread, and the scored claim as necessary-but-not-sufficient.
- **A live artefact's parameters must be pinned to the measurement that chose them, and a benchmark may never be charged a
  guessed fee.** Eighty rounds measured the past while the journal ran the row every recent table ranks worst for income
  (the `shelter` book is round 78's *insurance* position) and no book witnessed the fund the objective names. [`paper.py`](../../tools/paper.py)
  now carries a fifth model, `tilt` — static 50/50 SPY/QQQ, no decision in it, because six families (r74-r80) failed to beat
  one — and books `tilt`/`tilt_qqq` witness the objective's actual benchmarks, plain VOO at 3 bps and plain QQQ at 20 bps,
  same anchor, same $5,000, same $500/mo ([note](../notes/2026-09-07-the-forward-book-that-matches-the-evidence.md)). Three
  rules, each bought by a defect found in the wiring: **`fee_for`'s 35 bps guess is acceptable for a holding and fatal for a
  witness** (new `posted_fee` refuses an unposted comparator — a guessed fee on the benchmark is how a book beats an index it
  never paid for, round 73 applied to a live artefact); **two config fields described one witness and disagreed by 6.45 bps**
  (a literal SPY fee sat beside a comparator that could be anything posted); and **the disclosure paired weights with the
  wrong fees** (`50% SPY / 50% QQQ` against `0.200% / 0.095%`, charging the cheap fund the expensive fee — the wrong number in
  the one place a reader learns what the sleeves cost). Refusals are the design: `--tilt` is rejected outright because the
  weight was measured rather than chosen (pinned by test to `mix_sweep`'s control row, duplicated by value per this file's
  convention), a benchmark without a posted fee is refused, `step` refuses before a new month-end, and a one-entry book may
  not render a verdict. The tool also answers the question behind the objective with its own power arithmetic — **23 more
  monthly seals before a skill claim is supportable** — which is the honest answer to *how long until we know*, printed
  rather than estimated.
- **Recover a cash line at the prices the ledger sealed, and differential-test every copy of an accounting rule before
  trusting either.** A study set out to ask how many seals the live book needs and whether capital shortens the wait, so its
  benchmark had to be the journal's own; the test comparing the study's simulator against `paper.shadow_step` agreed to a
  quarter — because the copy faithfully reproduced a defect. Both chains recovered cash as *prior total minus holdings priced
  at today's prices*, which drops the month's mark-to-market into the cash line for the orders to sweep, so the interval
  closed worth its deposits whatever the market did: a fund up a third in three months left the witness at
  [$5,498.21 → $6,497.89](../notes/2026-09-07-a-benchmark-that-could-not-compound.md) — the deposit schedule, less fees. That
  is not cosmetic and not symmetric: a benchmark that cannot move hands every strategy a win in a rising market and a loss in
  a falling one, and it is the one number the P0 rule must not take from the graded party's arithmetic. Fix: one shared
  `recover_cash` reading `Entry.quotes`, used by `shadow_step` **and** `command_step`, so a subtle rule has one home; the
  study carries cash as a state variable for the same reason. Two corollaries, both from this round's wreckage. **A test that
  asserts a sign may be pinning a defect** — `…loses_to_one_that_does_not` held only because of the bug (its own docstring
  allowed the exception, and the book is now ahead by $24.92), so it asserts the half that cannot legitimately reverse and
  the direction moved to a property test: a rising market must lift the witness above its deposits, a falling market below,
  and its units must never fall into strength. **And invariance is a claim, not a feeling**: with proportional costs alone
  the wait is identical at $5,000 and $250,000 (224 seals; 595 on the last five years, to nine decimal places), so capital
  buys dollars and not knowledge — while a $9.95 ticket splits it to 1,451 against 603, i.e. the only scale-sensitivity in the
  account is the broker's flat charge, which is a broker fact and not a model fact.
- **Charge a trade where the trade happens, charge every line its own fee, and never report a cost and a policy effect inside
  the same number.** Round 82 left a question about the evidence: every capacity table since round 73 is built on a constant
  weight vector, which rebalances continuously and is charged nothing for it. [`rebalance_cost.py`](../../tools/rebalance_cost.py)
  billed it, with a claim written down first — *billing will reorder the mixes, shrink the tilt's edge, and a drift band will
  dominate*. The answer was two of three and the middle was missed: the mixes' ranking is identical under all three charged
  regimes in both windows, the tilt's lead over plain VOO moved by less than 0.2% ($1,924,527 stands), and **the idealisation
  cost 0.054% of everything paid in** — five hundredths of a percent, not a threat to the evidence. What cost money was the
  *policy*: rebalancing monthly rather than drifting ended **$210,122 behind, 10.4% of paid-in**, ~190× the spread bill — and
  on the last five years that sign **flips** (+$1,319), so a band is different exposure, not a better one, and the tool reports
  per window and refuses to average ([note](../notes/2026-09-07-what-a-rebalance-costs-and-what-it-does.md)). Hence the rule's
  three parts. **Count at the trade**: a sell tally reading `units` after the orders settle sees a book that sold in half its
  months never sell at all (it reported zero). **Charge each line its own fee**: burning a *summed* expense pro-rata eroded
  SPY at QQQ's 20 bps and vice versa — round 81's ordering bug wearing a different hat, value-preserving in total, and caught
  only because an oracle test computes the same account another way (a never-rebalanced 50/50 must equal two half-sized
  single-fund accounts). **And separate bill from outcome**: a spread has a sign, an end-value gap is that spread plus the
  tape, and adding them is the oldest trick on this list. Two corollaries worth carrying: a book whose deposit is large
  relative to its holdings *never sells* — rebalancing is a cost of mature accounts, so young accumulators pay for a service
  they are not using — and a band does not reduce the ticket count at all ($9.95 a ticket is 3.78% of every dollar deposited
  at $5,000 against 0.08% at $250,000, halved by holding one fund, unaffected by any band). Third round running that an
  independent recomputation — not a spot check — found an accounting error: make it the default way to believe a number.
- **Measure a policy on the state the policy acts on, and when a rule has been lost, pick the convention that cannot flatter
  the book.** Round 84 anchored the execution policy round 83 could not settle — a fifth book, `tilt_band`, identical to the
  live tilt book in weight, sleeves, fees, witness and anchor date, differing only in trading **past five points of drift**
  ([note](../notes/2026-09-07-the-band-that-was-measured-and-the-file-that-got-destroyed-writing-it.md)). The band's first
  draft measured drift over *equity including the deposit that had just arrived*, which finds every sleeve underweight by
  about the deposit share every month: at this book's 10% ratio that is five points of phantom drift, exactly the band, so a
  banded book would have breached on schedule, rebalanced monthly and reported itself patient. Drift is now the distance from
  target across the **invested** book — incoming money is not a misallocation, it is next month's rebalance, and it is spent in
  the buy-only branch — applied to both copies of the rule (`paper.py`, `power_horizon.py`) because two copies that disagree is
  round 82's lesson. The round also lost `tools/paper.py`: a scripted patch reused one variable for two files and wrote the
  second file's content to the first path. The file was untracked, so there was no blob, no snapshot, no editor history, and the
  `.pyc` was overwritten by importing the corpse; the engine is now rebuilt from the 96 paper tests and the sealed configs, and
  trusted because it reproduces round 83's figures to the dollar and round 74's witness line, not because it looks right. What
  survived was what the design protects: the append-only ledgers reported `chain intact` throughout. Hence the operational
  rules — a patch script writes **one** file and re-reads it to prove the write, and the tool tree gets committed, since the
  ledger is protected by design while the code that reads it was protected by nothing. And where recovery could not pin a
  convention, the self-punishing one was taken and written down: `_deposits_due` now pays a transfer per calendar *month*
  rather than per seal, because forgiving a missed month lowers paid-in, which is the denominator of every return this journal
  reports; `days_to_invest` records the wait, which finally makes the ledger's own idle-cash finding reachable.
- **A trigger must be measured on the quantity the policy is about, and a published table must be able to tell when the engine
  underneath it changed.** Round 84 changed how drift is measured after round 83's table had already been published, so round
  85 re-ran the study rather than trusting its own conclusion: the mix ranking is still identical under all three charged
  regimes in both windows, the bill the free-rebalancing idealisation omitted is still 0.003–0.054% of paid-in, the tilt is
  still $1,924,527 ahead of plain VOO on identical charges, and the end-value effect of rebalancing is still not one-signed
  (−$210,122 over the record, +$1,319 over five years) — but two published cells moved: the banded 25% book is worth $35,535
  more and the banded 75% book $7,398 more, because the old measure read the monthly deposit as drift. A rebalance trigger
  computed on a balance that includes uninvested cash **fires on the funding schedule instead of on the market**: at a 10%
  monthly deposit it manufactures five points of phantom drift a month, forever, which is larger than any sane band, so the
  book trades to a schedule it never chose and pays the spread to obey its own payroll ([correction
  appended to the round 83 note](../notes/2026-09-07-what-a-rebalance-costs-and-what-it-does.md); the same disease in a signal
  would be a rule that reacts to contributions, and any bot with a "deviation" trigger should assume it has this bug until
  shown otherwise). The correction is appended rather than written over, and the headline cells are now pinned to the cent by
  four tests, so the table refuses instead of quietly re-quoting itself: the cleanest evidence that the corrected numbers are
  the honest ones is that over five years the band never fires, and there the banded and never-rebalanced books are now the
  same account to the dollar.
- **A flat cost is a different physics from a proportional one, so a scale-free conclusion is only free of it at one end of the
  range.** Seventy rounds of this repository concluded the growth tilt beats plain VOO *at any size*, and every one of those
  conclusions was about proportions. A ticket is not a proportion: it is stamped per order whether the account is $1,000 or
  $1,000,000, and a two-sleeve book pays two a month where the witness pays one. Priced on the sealed month-ends, at
  $2,500 of capital on a $9.95 broker over **two years** the tilt ends **behind** plain VOO — 0.30% of everything paid in, the
  first P0 failure the tilt has ever produced, and at $1,000 it is −5.4%; over sixteen years the same broker costs 20 points of
  a 97-point edge and flips nothing, because the horizon changes the numerator while leaving the ticket count alone. Commission
  free, every cell in a row is identical to the cent, which is the invariance round 82 proved and the reason the flat charge is
  a second physics rather than a haircut ([note](../notes/2026-09-07-the-first-size-at-which-the-tilt-loses.md)). Two things
  follow for a small account earning monthly: the venue is currently worth more than any signal in the archive — the best rule
  here is worth $88 a month on a $100,000 book and the second sleeve costs a small account its entire two-year edge — and the
  fix is one fund or a free broker, never a rebalancing policy, because the ticket count is set by the fund count. Checking
  those figures turned a defect up in the sheet itself: its one line comparing the best rule against plain SPY was a per-hundred-
  thousand figure wearing a dollar sign, printing the same value for a $25,000 and a $400,000 account. It had survived because
  the comparison it reports is scale-free in **sign**; it misreported magnitude, never direction, which is how a sheet can be
  read correctly for thirty rounds and still be wrong — a report that is only ever checked for its conclusions is never checked
  for its arithmetic. Now scaled, with two tests demanding every monthly dollar figure be linear in the capital quoted.
- **A procedure that has never run against its real input is untested, and a ledger may not contradict its own sealed plan by a
  cent.** Five books are anchored and the first real seal is 2026-09-30, so the seal path — the procedure that decides whether
  this programme ever produces evidence — has never run against a date the archive does not already contain, and round 84's two
  convention changes could only be unit-tested on the helper. Round 87 manufactured the month-end instead: copy the corpus to
  scratch, append synthetic bars *and the cash row that must travel with them*, drive the real CLI, check 85 things
  ([note](../notes/2026-09-07-the-month-end-that-has-not-happened-yet.md)). It found the engine correctly refusing to seal a
  date the bill curve does not cover; it confirmed a September seal carries no deposit because the anchor already funded
  September; it proved a flat tape produces no sell in a banded book, which is round 84's phantom drift dead in integration.
  And it found a cent borrowed on a plan whose sealed `plan` field says *never borrow* — buy sized from target weight, cash
  debited gross of spread, rounding leaving a fraction of a cent short, the ledger inventing a loan and two tenths of a cent
  of interest rather than leaving the dust in cash. Now trimmed when the plan's own weights sum to at most one (a structural
  guard, so the shelter ladder's intended leverage survives and an unknown unlevered model inherits the protection), with a
  violation if cash still ends negative. Rehearsing also cost one synthetic row appended to the live bill curve by a harness
  that bound a path before repathing it: repaired byte-exact against a snapshot, and the pattern is now twice-proven —
  round 84's engine was unrecoverable for want of a copy, this file survived because the archive happens to be snapshotted, and
  the tool tree remains the one place with no copy at all.
- **Rehearse the whole path, and treat a loud refusal that has a test defending it as a decision rather than an oversight.**
  The fetcher had 26 tests on its pure functions and had never once run `main()`; the claim "fetch, then seal" — the two
  commands the operator will type every month — had never been executed end to end. Round 88 stubbed the one transport seam
  (`_get`, a single function, so the stub cannot drift), stood the clock forward where the exchange calendar demands it, and ran
  the loop twice offline: fetch, anchor, fetch, seal
  ([note](../notes/2026-09-07-the-monthly-loop-run-twice-before-it-ran-once.md)). Atomicity is now measured rather than read — a
  refused endpoint or an empty payload exits 2 and leaves the previous corpus byte-identical, and `current` is a byte copy of a
  named snapshot — and the tool confirms no fetch can produce a session the exchange has not finished trading, so the first seal
  cannot be pulled forward by fetching harder. Then the test caught my own patch: reading round 87's refusal, I made
  `write_snapshot` invent a `-2` suffix instead of colliding, which (a) broke an existing test defending `exist_ok=False` —
  a snapshot's name is its identity and its manifest is the completion marker — and (b) built the `current` symlink from the
  unsuffixed timestamp, silently pointing the pointer at the *previous* corpus. That failure has no traceback: the engine would
  report `book is already closed at 2026-09-30` forever and the operator would conclude a month had been sealed. Reverted; the
  comment now says why. A pointer that lies is worse than a tool that stops, a suite earns its keep by refusing its author, and
  end-to-end coverage is the only kind that catches a regression you introduced yourself this afternoon.
- **Publish the procedure and let tests re-derive every number in it, because a programme that lives in its author's head is
  not runnable and a document nobody checks becomes a rumour.** The tools were rehearsed end to end in rounds 87 and 88, but the
  monthly procedure existed only in CLI help and a dozen rounds of notes, so round 89 wrote [`RUNBOOK.md`](../RUNBOOK.md) and a
  guard file whose job is to refuse it ([note](../notes/2026-09-07-the-last-mile-is-a-document-so-it-got-tests.md)): each command
  is checked against that tool's own `--help` for the subcommand named, every dollar in the friction table is recomputed from
  `paper`'s constants, the first-seal claim calls `_deposits_due` instead of trusting the sentence, quoted statuses must be
  strings something in `tools/` prints, and the stopping rule may name only fields the ledger seals. One test insists the ugliest
  number stays ugly — the runbook's claim that tickets cost 26× the book's whole proportional cost at a $5,000 account must exceed
  20, because a document softens itself when its author stops looking. The number itself is the round's real product and it is not
  a signal: $19.90 a month to move two sleeves against $0.76 a month to own them. A venue is worth more than a tilt, which is
  round 86's crossover in operating language. The runbook also fixes four stopping conditions *before* the evidence — P0 against
  plain VOO at 24 entries, the band against its own twin capped by the measured bill ($1,091 / 0.054% over the record, $18 /
  0.003% over five years), no claim while `report` says `underpowered`, and an immediate halt on any integrity failure — and it
  discloses that today's posted ratios applied across a 16-year backtest flatter the years of funds that cut fees since issue.
- **Calibrate the instrument you are not allowed to change, and publish its false-positive rate beside its verdict.** The pinned
  protocol grants `skill: beat` past 24 entries if the gap is positive by any amount — a sign, not a test — and round 89's runbook
  leaned on it. The threshold cannot move (pre-registration is the point), so round 90 measured it instead: the real
  `journal.verdict` run over paths bootstrapped jointly month-by-month from the archive, chained from its last month, in three
  constructions that differ in what they hold equal ([note](../notes/2026-09-07-the-instrument-nobody-was-allowed-to-change-gets-calibrated.md)).
  At the floor it prints `beat` on ~19% of paths where no skill exists anywhere; the false-positive rate *falls* with length
  (18.8% → 12.3% → 4.8% at 24/36/60 months) not because the test sharpens but because the book pays 3 bps on every purchase while
  `comparator_path` pays nothing — a hurdle of roughly 100 bps a year at two years, decaying to ~60 at five. So the runbook's
  stopping rule now demands a margin, not a sign: >~150 bps at 24 entries, ~50 at 36, any positive gap at 60, where 60 is where the
  no-skill distribution sits 58 bps behind. The uncomfortable row is the replay: on the archive's own returns with the month order
  scrambled, the tilt beats plain VOO 62% of the time at 24 months — so a 24-month verdict can come out either way even if history
  repeats in distribution. Two lessons about the study itself: a mode named `null-symmetric` was not symmetric (expense ratios
  matched, spread not — relabelled as a hurdle rather than quietly kept), and a one-index null cannot exercise a rebalancing band at
  all, which is now asserted rather than assumed, because an impossibility is a property and it catches plumbing rot that a looser
  test sails past.
- **A stopping rule with no command behind it is a decoration, and the command that enforces it must read its inputs off the
  sealed record rather than assume them.** P0 has been this repository's first rule since it was written — beat plain index
  investing net of every fee and every ticket — and round 89 made it condition one of the runbook. Nothing computed it: `report`
  scores a book against its own zero-commission twin, and `journal.verdict`'s comparator is generous on purpose (zero commissions,
  and it is advanced by the book's *net* cash), which is right for a protocol afraid of false skill claims and wrong for the
  question "does this apparatus earn its keep" ([note](../notes/2026-09-07-the-stopping-rule-that-had-no-command-behind-it.md)).
  `tools/forward_p0.py` rebuilds the index side from the same sealed quotes, clears the fee line before charging the comparator its
  own expense ratio, and counts the book's orders out of changes in sealed holdings — so a banded book pays for the breaches it
  traded, not for a theory about bands. It prints `not decidable` below the protocol's floor, refuses a negative commission, and
  refuses to score a chain that does not verify, tested by copying a live ledger, moving one closing value a dollar, and demanding
  the refusal. Applying round 90's margin rather than the bare sign, it can also say *ahead but inside the no-skill margin*, which
  is the honest reading of a small positive gap. The measurement it enables is the project's sharpest practical line: 48 tickets in
  two years against the index's 24, which at $9.95 is 2.81% of paid in on a $5,000 account against a commission-free edge of 3.12% —
  the venue consumes roughly 90% of the tilt's advantage at that size, and at $25,000 it consumes 0.56% and the argument changes
  sides. Two cautions recorded in the round: hand-copied constants rot (the new test first compared a hand-written margin against
  the wrong row of `skill_null`'s JSON, a 17 bp error a re-derivation test now forbids), and an assertion that looks like a pass is
  not one — the first draft selected `rows[0]` rather than the construction it meant.
- **Every rule that can stop the programme needs a command behind it, and that command must be allowed to print "not yet".**
  Round 91 armed stopping rule 1; rule 2 (the band against its own unbanded twin) was still eyeballed through `compare`, which scores
  each book against its *zero-commission witness* — the wrong pair, because the twin that matters is the same model without the band.
  `forward_p0.py --against` compares net dollars at identical paid-in, each side net of the orders it actually made, refuses chains
  that did not seal the same intervals, and caps the allowed shortfall at the measured bill as a **share of paid in** (0.054%,
  `--bill-cap`) so it stays scale-parametric; inside the cap it prints `no verdict either way` rather than a pass, because a check that
  can only say pass or fail is eventually read as a pass
  ([note](../notes/2026-09-07-one-screen-for-four-ways-this-programme-can-be-wrong.md)). `--status` puts all four conditions on one
  screen with the command that owns each, three of them reading `not decidable` and the screen still exiting 0: nothing is wrong, the
  record is three weeks old, and a status tool that cried failure at honest ignorance would train the operator to ignore the one exit
  code that matters. Two fixtures failed their own premises and both are kept as lessons: two books with identical sealed closing
  values *tie* at zero commission, so a test asserting one was ahead was asserting nothing; and the bill cap belongs on paid in
  ($6,000 with two deposits in it), not on the opening balance — a denominator that quietly excludes money that arrived. A banded
  book is *claimed* to trade less than its twin; the comparison counts orders off sealed holdings precisely because a claim is not
  evidence, and the day the chain says otherwise is a finding rather than an embarrassment.
- **An audit has to meet the engine's own output, not only fixtures written from what you expected it to write.** Stopping rule 4 is
  the rule this project has actually been caught by (round 87: a note admitting `on 0.01 borrowed`, a `plan` field promising it never
  borrows, `violations` empty — every hash matching), and it was the last rule with no command. `tools/audit_entries.py` asks each sealed
  entry to account for itself — nine checks, all derivable from the record alone — with implied cash computed by `paper.recover_cash`
  rather than a second copy of that subtle rule, and the cadence check reading the model's own monthly figure because paid-in is the
  denominator of every percentage reported here. Then it runs *inside the rehearsal*, against a manufactured corpus with real trades, a
  real band breach, a skipped deposit and a crash in the chain, which is the difference between a passing test suite and a check that has
  ever met production output ([note](../notes/2026-09-07-the-stopping-rule-that-was-checked-by-nobody.md)). Three lessons from building
  it: the fixture that priced every symbol it was given holdings for made the unpriced-holding test assert a finding the code correctly
  declined to make (a test that passes on nothing looks exactly like a passing test); the audit **crashed** on `KeyError` from the very
  defect it existed to report, and now names the missing price instead — an audit that crashes has reported less than one that says what
  is missing; and a check needs its *negative* test, since flagging the shelter ladder for borrowing is a misunderstanding, and a check
  that fires on the wrong model gets switched off inside a month. A check that can never fire is deleted rather than kept for comfort:
  `journal.Entry` already refuses a plan posted after its own interval, so the audit converts that refusal into an `unreadable` finding
  instead of a traceback.
- **A fact that exists in four files exists four times, and the copies disagree in whichever direction nobody was watching.**
  Round 94 counted four statements of the same expense ratios in this repository and found the engine charging seven legs a flat 0.35%
  whose own comment claimed deliberate pessimism while three of the seven legs were *dearer* than the guess (DBC by 49 bps, EEM by 37),
  and the comparator battery — whose job is to price the bar — wrong on four of eight legs with a comment asserting that an error there
  only hurts if it is too low, in a table where two were. The TLT line was 33 bps/yr off against a whole-programme rebalancing bill of 54
  bps *over sixteen years* (r83). `tools/fund_fees.py` is now the only table, carrying issuer, URL pattern and retrieval date; the four
  consumers import it; `tests/test_fund_fees.py` fails any tool that maps a ticker to a number under 2% outside the table (numeric guard,
  because a weight map is not a cost and a scan that cries wolf gets ignored inside a week)
  ([note](../notes/2026-09-08-four-files-four-answers-one-fact-what-a-fund-charges.md)). Two consequences that are decisions and not
  cleanups: sealed books are **not** re-priced — a book whose cost assumption moves mid-chain stops being one chain, so the live shelter
  book keeps its harsher 0.35% on the bond legs and the bias is now published rather than latent; and the witness refusal survives with
  its teeth moved from four named funds to "anything without a source". When a pin's premise dies, the pin is rewritten to the new truth
  with the old number recorded (`three_times_what_the_old_global_fee_would_have_charged` → a derived 1.6×: the bug was real, the headline
  belonged to the guess), and a tool whose inputs just changed is re-run before it is quoted again. The round's own accident became the rule's second half:
a patch that rewrote one pin sliced to the next `class` and silently destroyed its neighbour — round 81's witness-fee guard — and
**nothing failed**: the suite only got *smaller*, 2240 expected against 2239 measured, which is how the loss was caught. A rewrite of
a test file is verified by the test count before and after, not by the rewrite succeeding.
- **Automation may take the mechanical half of a discipline and must leave the judgement half alone.** Round 95 built the bot the
  objective asks for and it is a runner: `tools/monthly.py` parses the runbook's own ```sh block (so the document is the authority and
  a divergence is a red suite), adds one seal per book found on disk, re-reads the stopping-condition screen *after* the seals, and stops
  at the first failure while printing no summary for a half-run month. Two distinctions carry the design. A seal the calendar has not
  asked for is **skipped with a reason** — computed from the same `max(data.dates)` versus head-`asof` comparison the engine uses, read
  through the engine rather than re-derived (r82) — while a failing command **stops everything**: the first is a fact about dates, the
  second a fact about the record, and a screen that conflated them would train the operator to distrust both. And it has no `--force`,
  no `--yes`, no `--asof`, no `--tilt`, no `--band`, with a test asserting the help text carries none of them, because the file that runs
  when nobody is reading is the last place a refusal should be negotiable
  ([note](../notes/2026-09-08-the-bot-shaped-artefact-is-a-runner.md)). What it deliberately does not automate is the finding of 94
  rounds: no news input, no signal ranking, no position sizing — `decision_sheet.py` already refuses to price a news veto, and r90
  measured a decision-maker that says `beat` 18.8% of the time on paths with no skill in them. Automating an ungraded decision is the
  fastest route this repository knows to losing money with confidence. The round's own follow-up is the durable half: the runner's
  first live fetch repointed the corpus — same sessions, same last date, one close revised by a hundredth of a basis point — and an
  `assertEqual` between two computed figures in `test_shelter_long_record.py` failed at 1.4e-11. The finding was untouched; the pin had
  been asserting a property of the downloaded bytes, i.e. a hidden lock forbidding the monthly procedure from running. **Immaterial is a
  claim about cents, not about bits:** a pin that compares computed floats must name a tolerance and a relative bound, and anything that
  re-fetches has to be run against the pins *before* it is run for real.
- **A published figure is a claim until a command can reprint it, and a fixture that never reaches the decision branch cannot
  test a decision.** Round 96 took the two most load-bearing sentences in this repository and put machinery under both. The first was
  round 82's replay — paid in $2,020,000, the tilt closed at $9,841,466, plain QQQ at $12,316,793 — the archive's actual answer to
  "beat VOO, QQQ, or whatever", existing only as a table in a note for fourteen rounds. `power_horizon.py` now prints all four bars on
  every run and a test pins each row to within 1.5% of the published number, with a message telling anyone who trips it to amend the
  note rather than the assertion; the reprint came back 0.4–0.8% low on all four rows with paid-in and the month count identical, which
  is revised closes rather than a changed fee, and the finding held (QQQ ahead by $2.44M where it was $2.48M). The second was a stopping
  rule's wording: crossing the protocol's 24-entry floor for the first time, a book **behind by $10,255** printed `ahead, but inside the
  no-skill margin` — round 91's margin gate compared the shortfall before anyone compared the sign, so a false-*positive* threshold was
  talking a loss into a tie. A no-skill margin may only ever raise the bar for a positive gap; a non-positive gap fails first
  ([note](../notes/2026-09-08-a-headline-with-no-command-under-it.md)). Same round, same direction: `--witness` lets the tool price the
  objective's second index while every non-VOO verdict is stamped `(a secondary bar cannot redefine P0)`, an unpriceable witness became
  a sentence naming the missing sealed quote instead of a traceback (r93), and the monthly screen is pinned to keep printing four
  conditions about VOO. Every nine years of fixtures here were three entries long, and the branch that decides whether the programme
  continues had never been stood on.
- **A ledger that itemises transactions prices the activity and not the policy.** Round 83's bill for this book's rebalancing is
  $1,091 over sixteen years, 0.054% of paid in, and it is still true; `power_horizon.py` now prints six bars — three plain funds, and
  the same 50/50 pair rebalanced monthly, past five points of drift, and never — and the ordering is monotone in how little the book
  trades: $9,778,202, $9,812,538, $9,988,324. The $175,786 — **8.70% of paid in**, round 100's correction, not the 0.87% this rule first
  printed, a slip against a paid-in figure ten times too large and in the flattering direction — between the band and the drift control contains no
  transaction at all: it is what a fixed weight on a trending pair costs in weight you were not permitted to keep, invisible to any
  invoice because nothing was sold. Stopping rule 2's cap stays at the pre-registered 0.054% — a cap is not renegotiated with the tape —
  but a `no verdict either way` inside it now means only "the band cost no tickets", which is a weaker sentence than "the band cost
  nothing" ([note](../notes/2026-09-08-a-cost-with-no-transaction-in-it.md)). Two corollaries carried by tests. Where the same word means
  two things, print the convention beside the number: the new column is drawdown of the *balance* with deposits still arriving (-22.0%
  VOO, -31.3% QQQ), while `mix_sweep.py` draws down the *index* and prints 33.7% and 35.2% — both honest, neither the other's check.
  And where a policy has not fired, say so and pin it: banded and never-rebalanced are identical to the cent over 61 months, so a test
  asserts that equality with a message saying a failure is news about the tape, not a flaky assertion. Third converging measurement of
  one shape — 82 (QQQ beats the tilt), 75 (the static control beats the best signal), 97 (the least active variant of the tilt wins) —
  and the archive's most reliable prediction about itself is that doing less has beaten doing more by more than the cost of doing.
- **The corpus is an input, and an input that is re-pulled is an input that is revised.** Rounds 95 and 97 were one accident seen
  twice: a fetch moved the pointer, and later a bit-level pin failed / a sixteen-year replay drifted 0.4–0.8% on all four rows with
  paid-in unchanged — discovered by surprise, not by looking, while the ledger was verified twice over and the data underneath it never
  once. `tools/corpus_diff.py` is rule 4's third half (hashes, self-consistency, and now the input): it compares the two newest
  snapshots and prints sessions added or removed, funds added or lost, the worst revised close per fund, restated dividend counts and
  the cash factor — the first run of it reporting **eleven of twelve funds with historical closes revised, worst cell 0.0002%**, in a
  fetch that added no sessions. It stops the month only on a revision outside tolerance, a removed session, a lost fund, or a dividend
  restated past half a cent, and it is line 3 of the runbook's block, so the runner picked it up without an edit (r95's design paying
  off) ([note](../notes/2026-09-08-rule-4-grew-a-third-half.md)). Two traps it was built against. Its first cash reader looked for a
  column that did not exist, found nothing, and printed `0 sessions differ` — an invented verdict of *unchanged* in numeric dress (r92),
  so both readers now refuse by naming the columns they did find. And the tolerance is one constant imported by the pin that uses it,
  with a test grepping the pin for the literal — the same fact written twice is the fact that will disagree (r94). The real snapshots
  are only ever asked to run and parse fully, never to be within tolerance: that number belongs to the vendor, and a suite that fails on
  it would be legislating round 95's accident into policy.
- **A comparison must contain the option the reader is already holding, and "priced" is not the same predicate as "tradeable".** Round
  99 added the seventh bar to `power_horizon.py`'s table — T-bills at the archive's own curve, charged SGOV's ratio pro rata on sessions
  plus the journal's spread on the way in — because a table of bets without the do-nothing option in it argues instead of comparing. It
  turns $2,020,000 paid in into $2,447,542 over the record (+21.2% of paid in) and keeps 71% of the standing bar's terminal over five
  years with a hole of 0.0% against -4.1%: even the 2022 drawdown did not make safety pay. Its accrual is the product of *daily* factors
  between month keys — exact on a four-session stub, which is round 47's defect obeyed — and it agrees with the file that already owns the
  curve (`cash_yield_gap.bill()["last10y"]`) to **0.0 bps** across 120 months, with 30 allowed
  ([note](../notes/2026-09-08-the-seventh-bar-is-the-one-you-are-holding.md)). Two faults surfaced on the way. `fee_for("SGOV")` had been
  returning the 0.35% guess for a 0.09% fund: round 94's own guardrail was true of the symbol and false of its nature, because a cash fund
  was in no table at all, so the two bill legs are now sourced in `CASH_FUNDS` and `cash_yield_gap.py` imports what it used to restate — and
  the dict-literal copy scan had let `SGOV_ER, BIL_ER = 0.0009, 0.0014` hide for four rounds, so the scan now keys on an uppercase `*_ER`
  constant, with a negative test built from the line that actually fooled it. And `paper.posted_fee` refused benchmarks by asking "is it
  priced?", which the new rows made true for a symbol with no price series: it would have died in a `KeyError` behind round 96's
  `--witness`. Gates must name the distinction they encode — priced, traded, scoreable are three questions — because the failure mode of a
  conflated gate is a traceback where a sentence belongs (r93).
- **A figure in prose is a figure no test runs, and the runbook is the document a person obeys.** Round 100 found its own headline from
  round 97 off by ten times: the runbook, a note, and rule r97 all printed the band-to-drift-control gap as "0.87% of paid in" where
  $175,786 / $2,020,000 is **8.70%** — dollars straight from the tool, share by mental arithmetic, and wrong in the flattering direction,
  in the very paragraph arguing that a policy costs more than its invoice. Corrected everywhere and disclosed in place, with the ratio the
  slip had hidden: **the policy cost 161 times the bill for it** (0.054% vs 8.70%, both from `rebalance_cost.py`; the sheet's older sentence
  had the relationship inverted too, as "the policy is worth 10.4% of it")
  ([note](../notes/2026-09-08-a-figure-wrong-by-ten-times-in-the-obeyed-document.md)). 2,299 tests could not see it, because every one of them
  checks a tool against data; the fix is to stop letting prose carry uncommanded figures. `decision_sheet.py` now derives both shares at print
  time, `TheProseReprintsItsOwnFigures` recomputes all four friction percentages and requires the runbook to print each at its own rounding
  (failing on a digit, not on a tolerance), and `test_decision_sheet.py` fails on any typed `% of paid in` in the renderer's source. The class
  ships with its own negative test, built from this round's actual slip — and that test first caught the correction sentence mentioning the old
  figure, which is why the scan is on the phrase `X% of paid in` rather than on bare digits: the accurate claim is also the one that survives
  recording its own history (r93's negative-test rule, applied to a documentation test).
- **A published figure needs a class under it, and a copied figure with provenance is still a copy.** Round 101 took round 100's rule to
  the rest of the runbook: recompute every load-bearing figure from the tool cited beside it, and require the prose to print it at its own
  rounding. Two stale figures and one removed copy: the banded book's gap to plain QQQ was written as **$2,404,018** where the command prints
  $2,404,017 (a hand-rounded difference of two numbers printed to the dollar, in a sentence quoting that command); and the tilt-versus-QQQ
  pair from round 82 (12,316,793 / 9,841,466) was attributed honestly to round 82 **and still wrong to print**, because the archive had been
  re-pulled since and round 96 had measured that revision at 0.4–0.8% — the sentence now carries no dollars and points at
  `power_horizon.py` instead ([note](../notes/2026-09-08-every-figure-in-the-obeyed-document-has-a-class-now.md)). The five `skill_null.py`
  calibration figures all reprinted (18.8%, +152 bps, ~50 at 36, 58 bps behind), and the qualitative claim *no margin at 60 entries* is now
  tested too, since it is only true while the p95 stays ≤ 0 (today: −0.18 bps). Dollar figures are pinned to the dollar **on purpose** and the
  docstring says so: a re-pull that moves a replay makes the runbook's sentence genuinely stale, and failing loudly is the mechanism —
  `corpus_diff.py` decides whether a move matters, this class refuses to quote a moved figure as if it had not moved. And the new footer test
  caught this round's own footer naming a class (`TheNumbers`) that never existed: the claim *"this is checked"* is itself a claim needing a
  check, which is the whole argument for the round in one line.
- **A refusal that names a missing thing which is present is worse than no refusal, and the fix may cost a published law.** Round 102
  found `sleeve_table.py` still printing that IWM/EFA/EEM were unmeasured because "the file carries no posted expense ratio for them" —
  false since round 94 sourced all twelve — with `correction_table.measure` enforcing the same lie as code by borrowing another file's
  *publication* list as a fee check (`KeyError: IWM carries no posted expense ratio`). A message like that does not just refuse, it sends
  the next reader to the wrong shelf, which is why r92 demands the actually-missing thing be named; the gate now asks `fund_fees` and
  refuses only XLU-shaped things ([note](../notes/2026-09-08-a-refusal-that-named-a-fee-which-was-not-missing.md)). Sweeping the three legs
  then broke round 67's insurance law — *a hedge is worth what its fund costs when it fails* — which had been pinned as a row-by-row
  equivalence: IWM's fund failed 8.7% of its windows and the shelter still cost **$300.47 a month**; EEM's failed 74.3% and was worth
  $10.71, under the decision bar, so it is an exception and not a material one. What does sort the rows on records that contain the failure
  decade is the **duty** column: shelters that paid were out of equities ≤ 28.2% of days, shelters that lost ≥ 30.6%, 2.4 points apart on 11
  rows. The report now derives every count it prints (the old prose had typed counts — round 100's disease inside a tool), prints its own
  refutation instead of crashing on it, labels a 0.00-vs-0.00 row `neither arm could fund a dollar` rather than "loses", refuses the
  remaining legs by asset class with a printed reason, and fails a test if any priced leg is announced unpriced anywhere in `tools/`.
  Round 94's five-fund withdrawal table stays five: publication scope is a decision, and its comment now says so and points at
  `sleeve_table.REFUSED` rather than at a constant that has been deleted.
- **A fee lookup gated by another file's scope list is a policy wearing a costume, and its default is the policy.** Round 103 found the
  fifth site of round 94's fact: `rotation_search.py` — the battery that ranks every candidate rule — priced legs with
  `wc.EXPENSE[sym] if sym in wc.EXPENSE else FLAT_FEE`, so a *publication* list (the five sleeves `withdrawal_capacity` chose to tabulate)
  silently decided that three of the battery's five legs had unknown fees and got the flat 0.35% guess: **IEF over-billed 20 bps** (the leg
  the shelter rules hide in), GLD under-billed 5, EFA over-billed 3. Direction matters more than magnitude here: a study grading shelters
  that over-charges the safe sleeve is biased against precisely the construction the objective would use. Measured both ways — the fix moved
  the largest cell on the page **+$3.17/mo**, changed no verdict, and left the pass count at 2 of 7; the sheet's headline moved by five cents
  ([note](../notes/2026-09-08-the-fifth-file-that-guessed-and-the-footer-that-said-it-had-not.md)). Publish the small number, don't skip the
  fix: the same footer had been telling the reader that GLD and EFA's "real expense ratios are not in the archive", the third instance in
  eight rounds of a refusal naming an input that is present (r92, r102). The rule as practice: a fallback value must be **unreachable for the
  universe the tool scores** — assert it in a test rather than believe it — and where it is reachable, the tool is pricing with the fallback.
  Remaining defaults are now asserted unreachable (`power_horizon`'s book is fully priced) or labelled and derived (`wc.TURNOVER_COST` for the
  2 bps switch cost, printed instead of typed).
- **Sourcing a fact is not sourcing the call graph, and an audit that cannot fail is a rumour with a table.** Round 104 wrote
  [`cost_conventions.py`](../../tools/cost_conventions.py) after finding the price of a loan carried at **two values in three files**:
  `paper.BORROW_SPREAD` was corrected from 150 to 202 bps back in round 30 (pre-registered to move only at an anchoring), while
  `withdrawal_capacity` and `run_voltarget_scan` still typed 0.015 — 52 bps of flattery on every levered study, in the direction that makes
  borrowing cheap ([note](../notes/2026-09-08-what-a-loan-costs-in-four-files-with-two-answers.md)). Round 94 had sourced the *expense
  ratios* and left the *carry*; the same round then found `EXPENSE = 0.000945` (SPY's ratio under a name the `_ER` scan couldn't see), the
  leveraged-fund assumption typed in two files, the commission tuple spelled out twice, and a runner that crashed mid-print because the
  `rows` list it sorted had been deleted under it rounds ago. Practice, now machine-checked: **a constant whose name claims to know what a
  fund charges holds the table's value or a declared assumption** (allow-list in the test, so an assumption must state itself to survive);
  **a bps figure in prose is a figure nobody re-prices** (the tool lists them; this round fixed the stale ones — two labels still saying
  "cash + 150 bps"); and **a disagreement between conventions is reported with its consequence measured**, by re-running the ranking at each
  rung: pass sets invariant from 0 to 25 bps, the figure compared across families moving $1.61 a month between the two conventions the
  archive uses. The audit exits 1 on two answers for one cost or on a verdict that moves — and its first draft measured the spread *within*
  each run, printing "$0.00" under a sentence about how far figures travel, which is the same failure as a check that can only print pass
  (r92) wearing a formula. Round 103's own note was corrected the same round for a claim built on a diff capped at six entries per row: the
  control gap had moved $1.41, and a truncated diff proves nothing outside its cap.
- **A verdict of "immaterial" is a claim about a tolerance, never a claim about the prose — and the document the operator obeys is the
  first thing a re-pull makes stale.** Round 105 ran the published procedure for real on a fresh fetch ([note](../notes/2026-09-08-the-dollar-that-a-re-pull-moved.md)).
  `corpus_diff.py` printed `revised closes: 11 of 12 symbols`, then two lines later printed *Nothing has to be re-read … old closes
  unmoved*, contradicting its own line above it. Nothing had to be re-read at the 1.5% tolerance the bar tests pin — and the fetch moved
  `$9,812,538 banded → $9,812,539` and `$2,404,017 behind QQQ → $2,404,018` in `docs/RUNBOOK.md`, where `TheDecisionFiguresAreReprinted`
  pins every digit to the dollar on purpose (r100: the obeyed document gets classes, r95: immaterial is about cents not bits, r98: a
  re-pull is a revision). Practice, three parts: **the tool may not call a revision nothing** — its within-tolerance verdict is now
  conditional on whether any old close moved, and when one did it names the cent-pinned document and says re-print with the command that
  printed it, never by hand; **re-run the cent-pinned classes after every fetch, before publishing anything**, which is what caught this
  (one dollar, caught, disclosed, not smoothed over); and **a check earns its seat in the month, not just its existence** — `cost_conventions.py`
  was added to the block between the seals and the report, because sealing is calendar-bound and must not be blocked by a pricing
  disagreement while figures must not be republished past a failed audit, and `test_runbook.py` now pins that seat (`… runs_after_the_seals_and_immediately_before_the_report`)
  along with the rule that everything after it only prints.
- **A fetch that adds nothing has to name the reason it cannot rule out, and an input with a coverage end is an input that ages.**
  Round 106 followed round 105's empty-looking fetch to its edge: the vendor's last session really was 2026-09-04 (checked against the raw
  payload, not inferred), and the missing weekday was 2026-09-07 — US Labor Day. Nothing was wrong, and the tool had still printed *"history
  added, old closes unmoved"* over a diff that added nothing and contradicted itself ([note](../notes/2026-09-08-a-calendar-is-an-input-and-it-ages.md)).
  `corpus_diff.py` now states which of four cases it is in — nothing to add, the gap was all closures, the source fell short (naming the
  open days it missed), or **the calendar cannot say** — and the live case is the fourth, because the shipped NYSE calendar publishes
  coverage only through 2026-08-31 while the archive already runs to 2026-09-04 and the forward test needs 2026-09-30. Practice: **silence
  in a report is a claim** — a calm line over an unexplained gap is r105's "nothing has to be re-read" in a different font; **a refusal has
  to carry its own lift** (the message names `tools/build_nyse_calendar.py`, the command that would end the refusal, per r92); and **the
  calendar is a dated input like the price file**, so the runbook now says plainly that from here to the first seal the month's dates cannot
  be checked against published closures, with `tests/test_corpus_diff.py` pinning the *admission* (it asserts the coverage-end figure
  appears in the tool's own line, so the honesty cannot rot into a guess when the dates shift).
- **The artifact that proves the production path is itself a claim, and it gets one class or it gets nothing.** Round 107 ran
  [`rehearse_forward.py`](../../tools/rehearse_forward.py) — the month-end that has not happened yet, four scenarios, the round-87 lesson
  machinery — and it passed: `2026-09-30 sealed`, `2026-10-30 … sealed $500.00`, both chains verify, `the real corpus is byte-identical`,
  exit 0, 22 days before the first real seal. It also passed **nothing**: the suite had never run it, so the proof would have survived a
  month of refactors and then quietly stopped being a proof ([note](../notes/2026-09-08-the-rehearsal-had-no-witness.md)).
  `tests/test_rehearse_forward.py` (12 tests) now runs all four scenarios, requires each to make ≥10 checks so an empty list cannot pass
  vacuously, requires the two dates the objective actually needs to appear in the labels, pins the first deposit's `$500.00` as a
  *detail* rather than an assumption, and — r93 — breaks the audit inside the rehearsal on purpose and requires the tool to print `FAIL`,
  count `CHECKS FAILED`, and exit 1. Two sub-lessons, both from writing the guard rather than reading it: the new "the rehearsal touched
  nothing real" digest watched **two files for a minute before it was caught watching nothing**, because `BOOKS` had been guessed at
  (`data/books/`) instead of read (`paper.PAPER_DIR / "books"`), and a guard's first test must print what it covers; and a scratch-state
  cleanup after an injected failure needs the *cleanup* to be a passing run, or the next test inherits the sabotage.
- **An independent check the repository cannot run is not an independent check — write the second implementation and let it disagree.**
  `docs/data/nyse-calendar.md` has always said the calendar artifact's rules were verified against `exchange_calendars==4.13` in a
  disposable environment; round 106 found that package is not in the lab venv and cannot be, so the artifact rested on a check nothing in
  the repository could re-run — and the artifact's coverage (through 2026-08-31) stops before the forward test's first seal, leaving
  September unanswerable ([note](../notes/2026-09-08-the-second-implementation-disagreed-with-itself-first.md)). Round 108 wrote the second
  implementation from first principles (computus, nth-weekday scans, per-holiday observance) as
  [`test_nyse_rules_independently.py`](../../tests/test_nyse_rules_independently.py) and it disagreed with the artifact **twice, and was
  wrong both times**: Thanksgiving is the fourth *Thursday* (my first pass closed the fourth Monday), and a Christmas on a Saturday closes
  the Friday before while a New Year on a Saturday closes nothing at all (2010-12-24 and 2021-12-24 are closures, and the archive has no SPY
  bar on either — the corpus is the referee). After fixing my rules, the two implementations agree on all 5,197 sessions and all 194
  closures. Practice: **when a check can't be run, re-implement the fact rather than inherit the claim**; **let the archive referee** —
  bar data is a witness to which days traded, and it costs nothing to ask; and **a source switch must be spoken, not performed**:
  `corpus_diff.py` now prints the artifact's coverage end it is refusing against and then answers from the rule set *naming that it did
  so*, with the refusal bounded to the reviewed window (`rule_closures(2031)` returns None rather than extrapolating), and
  `tests/test_corpus_diff.py` pins the admission and the answer in the same sentence — an answer without its provenance is the artifact
  claiming to cover dates it has never seen.
- **A date from a press release is not a date about the endpoint you will actually use — knock on the door you intend to knock on, and
  pre-register a new asset class before its first return.** Round 109 opened crypto ([note](../notes/2026-09-08-an-endpoint-dates-itself-by-what-it-serves.md)):
  the first version of `tools/fetch_crypto.py` carried `BTC-USD: 2011-08-17`, the date Coinbase the *company* began quoting bitcoin. The
  tool faithfully reported the difference as *1,433 missing sessions* — an honest report that was still wrong about its own meaning, because
  an endpoint that never served a day is not a hole in a record. The floor is now probed (lookback by doubling years, then bisection to the
  day) and the record's floor is taken from the **first candle served**, so a probe that lands a day early cannot manufacture a hole; the
  same fetch then found two genuine ETH holes (2016-05-21, 2016-05-22) and reported them instead of stitching. Practice:
  **a source's limits are facts about the source** — the 400 Bad Request on a page wider than ~300 daily candles is recorded in the fetcher's
  own docstring and pinned by `tests/test_fetch_crypto.py`, which asserts no probe window exceeds 30 days; **the probed floor may precede the
  data, never follow it** (pinned against the live artifact); and **a new class starts locked, not warm** — `docs/strategies/BA-005.md` fixes
  one instrument, one 200-day rule, one monthly frequency, one window (2016-05-18 to 2026-09-04), and a failure decided by the ruin promise
  rather than the terminal, before a single crypto return was computed, with the venue's 60 bps taker fee written down as an *assumption that
  must be re-sourced or the run refuses*. Depth claims in that spec (83.8%, 76.7%, 53.1%) are recomputed from the candles by a test, because
  rule 100 says a figure in prose is a figure nobody re-prices.
- **A blocked source is refused with its evidence, and a measurement has to know its own noise.** The Coinbase goal (round 110,
  [note](../notes/2026-09-08-the-venue-that-will-not-look-up-its-own-fee.md)) started by trying to source the venue's fee, which BA-005
  requires before it may price anything: the help centre and both pricing pages answer `403 Forbidden` to any non-browser client — a browser
  user-agent changes nothing — the harness fetcher gets the same JS challenge, the Wayback copy is a 12 KB client-side shell with zero
  occurrences of "taker"/"maker"/any percentage, and the authenticated fee endpoint needs credentials this lab neither holds nor asks for.
  So `tools/venue_fees.py` carries that attempt log and refuses *with* it (exit 1, four named URLs), takes the fee only from an operator
  `ingest` that is dated and hashed, and holds **no fee number of its own** — `tests/test_venue_fees.py` greps the file for fee-named module
  constants and fails if one appears, and tests both sides of the 90-day staleness line rather than one. Practice: **the refusal is the
  artefact** (r106 again: silence dressed as calm is worse than a named block, and an ingest path makes the block actionable rather than
  fatal); **a prohibition must not require the forbidden token in the file** — the first docstring said "no `GUESS` here" and failed the
  r103-style test it was defending; and **publish the noise with the number**: the retail quote line measured +6.1 bps over the book mid and
  then −1.6 bps minutes later, so it is printed as a noise floor and not as a cost, and the first read of the order book came back as a
  *18,879 bps* spread because Coinbase's rows are `[price, size, fills]` and I read index 1 as the price — an error shaped like a finding,
  caught only because a one-cent-wide book on a $78,600 asset cannot cost 100 bps, so `test_the_touch_is_read_from_the_price_not_the_size`
  exists now.
- **Refusing to grade is for when the missing input decides the grade; refusing when it cannot decide is hiding.** BA-005 was locked and run
  the same day ([note](../notes/2026-09-08-a-hundredfold-asset-and-a-brake-on-it.md)). The Coinbase fee record did not exist, so the runner
  could not price a trade — and it still printed **FAIL**, because the gate that failed (max drawdown 56.5% against 40.7% allowed) fails at a
  fee of zero and a fee only ever takes money out of a path. `tools/ba005.py` therefore computes `best_dd` as the minimum across the fee grid
  and reports the failure as *fee-independent* (exit 1), while holding `NO VERDICT` (exit 3) for the case where the fee is the thing in
  question. Practice: **separate the gates by what can move them** — the terminal needed the fee (break-even 1,333 bps per switch, so in
  practice it needed nothing), the drawdown gate needed only the archive; **print the break-even instead of a guess** — one number
  (`1 - (bar/gross)^(1/switches)`) replaces an invented fee and tells the operator exactly how far their tier can be from perfect; and
  **report the signal against just holding the thing** — timing the coin added **+2.9%** over a decade that multiplied it ~100×, so the
  honest headline is "an asset bet with a brake on it", not "a trading model that beat the index". `tests/test_ba005.py` pins the locked
  numbers are the parsed numbers, that one switch costs exactly one fee on the sleeve (`(1-f)**switches`, not `(1-2f)**switches`), that the
  break-even fee reproduces the bar when charged, that the fee grid is monotone, and that the hold comparison line exists — because the
  +2.9% is invisible without it. The failure stands: a locked failure condition that is convenient to forget was never a failure condition.
- **A failure rate over few windows is a coarse instrument, so grade the pair and print the resolution with the number.** BA-005's step 3
  (goal round 2, [note](../notes/2026-09-08-the-brake-cost-less-than-nothing-and-the-ruin-gate-was-the-real-one.md)) had to price a ruin
  promise on 123 months of crypto history. Four 10-year windows is not a distribution, so the horizon dropped to 5 years and the count to 64
  — at which one window is 1.6 points of failure rate, and BA-005's 6%-against-QQQ's-5% is literally one more failing plan. So
  `tools/ba005.py` prints `one window is 1.6 points, so a 1.6-point gap in P(fail) is one plan, not a trend` in the same block that prints
  the rates, and its gate fires only when the candidate fails more often **and** is more often halved: the P(erase) pair (16% against the
  index's 0%) is the evidence, the P(fail) pair is decoration. Practice: **when the record is short, shorten the horizon and say so** rather
  than keeping the headline horizon and reporting four observations as a distribution (round 47's lesson, same shape); **print the resolution
  inside the number's own block**, because a reader who cannot see that 6% and 5% are 4-and-3-of-64 will read a trend into it; **reuse the
  archive's own bill function** (`monthly_income_race.safe_amount`, which produced the $435/mo figure) so a crypto ruin test is comparable
  to the equity book instead of a new invention with a similar name — and let a test recompute it independently (`test_the_bill_charged_is_the
  _archive_sown_not_a_copy_of_it`) in rule 108's spirit. The verdict stands on the two strong legs: drawdown 56.5% against 40.7% allowed, and
  16% of windows halved against 0%, at the index's own $1,019/mo. BA-005 is archived as a failure, the objective's step-4 bar is written into
  the spec, and the generalisation is that a Coinbase candidate must be *risk-specified before it is return-specified* and graded against a
  blend, because a full-weight single volatile asset cannot clear the drawdown gate at any fee this venue charges.
- **A sized sleeve can beat the index's *bill* while the model behind it earns nothing, so grade the seatbelt and the overlap, and withhold
  the pass when the licence condition is unmet.** BA-006 (goal round 3, [note](../notes/2026-09-08-the-sleeve-did-it-the-signal-did-not.md))
  priced BA-005's signal at weights parsed from the spec — 5/10/20% — against the P0 blend, on the archive's own bill function, and the result
  inverts the archive's standing verdict on its own terms: at 20% the affordable monthly bill is **+25.8% over P0** with P(erase) 0% and 0.9
  points more drawdown, the first candidate here to beat the index on the *promise* rather than merely out-earning it and failing. And the
  condition that stops it from being a win is the one written to be awkward: the seatbelt test **fails at 5% and 10%** (the signal blend
  supports a *smaller* bill than buying and holding the same weight of coin) and passes at 20% by **$17/mo on an $831 base**. Practice: **put
  a "could you have got this by doing less" leg in the pass conditions** (condition 4), because without it a table like this licenses a model
  that contributed −$23, −$0, and +$17 a month; **state the overlap with the window count** — 63 rolling 5-year windows out of 122 months are
  2 non-overlapping looks at one decade, and the tool prints `read every rate below as a sample of 2, not of 63` above the table rather than
  letting 63 rows imply a sample size; **keep one gate constant across a line of specs** (BA-006 imports `ba005.DD_LIMIT` and the horizon
  rather than re-typing 1.25, and a test asserts it) because a second copy of a threshold is a second threshold; and **exit 3 is for the case
  where the missing input is the licence, not the answer** — the fee grid printed under the table shows the result survives 240 bps, so the
  fee cannot change the ranking and *still* the PASS is withheld, because a pass is a trade permission and this repository does not issue one
  against a cost it cannot see (r103). Where history cannot separate two designs (+$17/mo is not separation), the spec now says what the
  forward book must do before any such evidence exists: carry **both** legs — signal sleeve and plain-hold sleeve at the same weight — and let
  the seals choose, rather than picking the more complicated one on evidence that cannot tell them apart.
- **Print the start-date ladder with the verdict, because a single-window result on a record that begins where the data begins is priced from
  a date nobody can invest from.** BA-006's 20% sleeve cleared all four gates and raised the affordable bill 25.8% over P0 with P(erase) 0%
  — the first candidate here to beat the index on the *promise*. The disclosure this round added (goal round 4,
  [note](../notes/2026-09-08-one-start-date-was-the-whole-result.md)) re-ran the whole test from +2y and +4y and printed every rung at every
  weight: at 2018 the sleeve adds 6-7% and the largest weight is the worst, every weight there failing the seatbelt; at 2020 it adds
  nothing and at 20% it goes
  backwards. This is the archive's own oldest practice returned to in a new asset class — `withdrawal_capacity.py` has graded every
  start since round 4 precisely because a *guarantee* must survive the binding start, and the ladder's guarantee reading is therefore
  its worst rung (2020: +0%, +0%, −1%), not its first; a clearing weight appears at **2016-05-18 and nowhere else**. Practice: **the disclosure gets no flag** — `--sensitivity` was
  built, then removed, because a switch that hides the sentence undermining the headline is not a disclosure (a test now asserts
  `--sensitivity` is absent from the source); **one gate function, three callers** — the table, the ladder, and the summary line all call
  `gates()`, because the first version of the summary compared a raw bill margin instead of the gates and reported the 2018 roll as
  "surviving" when every weight there fails the seatbelt: a looser copy of a threshold is a different threshold, and it flattered the result
  in the one place written to be honest about it; **the verdict line must carry the conclusion of the disclosure, not just link to it**, so
  the tool prints `a clearing weight appears at 2016-05-18 and nowhere at 2018-05-18, 2020-05-18; a decision made today sits closer to the
  later starts`; and **a disclosure may not edit the locked conditions** — the gates, exit codes, and licence terms are untouched, and what
  changed instead is the *pre-registered expectation* written into the spec: the forward book, if a fee record ever licenses it, is expected
  to show no improvement, which turns a flat first seal from an excuse into the predicted outcome. The archive's standing conclusion now holds
  across three asset-class expressions: plain QQQ is the bar, the signal does not beat the asset, and the window that flatters a rule is the
  one that starts where the asset's story starts.
- **A line you cannot price gets recorded as unpriced, not assumed, and the assumption it displaces gets priced both ways.** The objective's
  step 1 asks for the stablecoin/fiat conversion line beside the fee. Probed 2026-09-08 with keyless endpoints (goal round 5,
  [note](../notes/2026-09-08-the-stablecoin-line-was-not-a-market-and-the-t-bill-was-not-on-the-venue.md)): `/products/USDC-USD/book` answers
  `404` because **no such product is listed**; `BTC-USDC` and `ETH-USDC` are listed but `status: delisted, trading_disabled: true`; the only
  online USDC-quoted books are other stablecoins; `/v2/prices/USDC-USD/buy` returns exactly `"1"`, which is parity rather than a price, since
  both legs are dollars. So `venue_fees.py` prints the line as **unpriced** — never free — and a test asserts no conversion/peg/USDC constant
  appears in the source. Practice: **"not a market" is a finding, and it is reportable in the same breath as the probes that found it**
  (the negative answers are printed as the venue's own words, not as a tool failure); **when a probe contradicts a clause of a spec, price
  the clause's consequence rather than arguing about it** — the specs credit the below-the-line cash with a T-bill the venue does not hold, so
  `tools/ba006.py` now prints the bill at the T-bill yield and at zero on every weight ($919/$915, $980/$971, $1,045/$1,028) and states
  whether the unsourced assumption is load-bearing (it is not: ≤2.0% of P0's bill, and the 20% row survives zero-yield cash); and **the same
  delisted fact removes a route** — the only executable way to hold the coin on this venue is `BTC-USD`, so any "hold the cash side in
  stablecoin and trade the USDC book" design is not executable here and should not be quietly assumed in a later spec. Two hazards this round
  produced are worth remembering: a **name collision** — a new `PRODUCTS` constant shadowed the existing tuple of product *lines*, and the
  failure surfaced as `ValueError: unknown url type: "('advanced-trade', 'exchange', 'consumer'…`, which is what a shadowed constant looks
  like from the outside — and a **stale binding**: the new cash-leg block reused `costed`, which the fee grid above it rebinds on every rung,
  so the block's "T-bill" column printed the 240 bps bills, plausible enough to survive reading and catchable only by a test that compares
  the two places that must agree.
- **Read the authority before adding a tool, and when the capability is genuinely new, fold it into the file that already owns the job.**
  Goal round 6 re-derived a rehearsal for the first real seal — copy the tree, fabricate the month-end, drive the CLI, check the real files
  byte-identical — wrote `tools/rehearse_month.py`, got it green, and only then found the paragraph 20 lines into the runbook it was built to
  protect: `rehearse_forward.py` had been doing this since rounds 87/88, with a class under it since 107, and its own docstring opens with the
  exact sentence this round believed it had discovered ("the code path that actually decides whether this program works … has never once been
  exercised"). The duplicate is deleted. Practice: **the additive part is the redirection, not the rehearsal** — `tools/labdata.py` now
  resolves the state root from one place (`BORINGALPHA_DATA`, refusing anything that names the real tree, including the repository root,
  because that typo reads like a rehearsal and writes into the append-only ledgers), and `journalctl.py` deliberately does *not* let it move
  the pinned comparator snapshot: an overridable anchor turns a verification tool into a way of passing; **the new capability is what made the
  runner, rather than the engine, rehearseable**, so it went in as `rehearse_forward.py --scenario published` — eleven processes over the five
  live books, 15 checks, fetch and corpus-diff dropped because a rehearsal must not be able to write a real snapshot; **a rehearsal must
  check the refusal, not only the run** — the scenario re-runs the same month and requires `already closed`, because the likeliest way a
  monthly book dies is someone running it twice, and `all checks passed` on the happy path alone would have missed that indefinitely; and
  **one rehearsal tool, two documented halves** (`--scenario` engine vs published), stated in the runbook, because two tools that each copy
  the tree and each fabricate a month-end drift apart exactly when it matters. The published block is verified: all five books seal
  2026-09-30, `journalctl verify` and `audit_entries` pass against the copy, and the real `data/` tree is re-hashed file by file and found
  unchanged.
- **A measurement that matters gets stored as an artifact with a date and a hash, and the check on it must be hermetic before it is trusted.**
  Step 1 asks for the Coinbase cost stack as a *dated, sourced* input. The schedule is unreachable to a script and stays ingested-only, but the
  reachable half (both coin books, the retail quote, the conversion quote, the product list) had been living as prose in a note since round 5.
  It is now `tools/venue_fees.py snapshot`, which appends one JSON line to `data/venues/measures.jsonl` per run — UTC time, and per URL the byte
  count and the sha256 of the payload as fetched — through a single `_fetch` choke point, so the hash is of the bytes and not of a re-serialised
  guess (rule r108: one place, not two). Practice, and the trap it came from: **the first version of the test class did not inherit the fixture
  that redirects `VENUE_DIR`/`RECORD`/`MEASURES` into a temp directory, so it appended six genuine probe lines to the real archive before
  failing** — an evidence file polluted by the machinery meant to prove it, caught because one test asserts the artifact under test is inside a
  temp dir (`test_the_fixture_moves_the_archive_off_the_real_tree`); the polluted file was deleted and the archive restarted at one honest entry
  rather than left as seven lines of mixed provenance. Two more properties are now pinned because they are the ones that would rot silently: a
  test that an archived measurement **still does not license a price** (`taker` must keep refusing — a fresh spread is not a fee, and one day
  somebody will read it that way), and that the file only ever grows (`after.startswith(first)`). The same round verified the loop's money clock
  at the runner level rather than assuming it: `rehearse_forward.py --scenario published` now recomputes the transfer arithmetic from the
  calendar independently of `paper._months_apart` and checks the sealed entry carries it — $0 due by the first seal on 2026-09-30, exactly one
  $500 transfer with `days_to_invest 0` at 2026-10-30 — which is the objective's "first deposit 2026-10-30" becoming a checked property instead
  of a sentence. Related finding, recorded rather than papered over: a sealed entry carries its quotes and its date but **not the id of the
  snapshot it was read from**, so the check that distinguishes a rehearsal entry is the corpus directory's name and the fact that the copy is
  disposable, and the check says so in its own text rather than claiming the entry names it.
- **A check has to be able to tell a rehearsal from a real run, and a skipped step needs a current excuse.** `corpus_diff.py` had been dropped
  from the published rehearsal since round 116 for a reason that was true of the tool's first draft and stopped being true the moment a resolver
  existed — it read `ROOT/data/snapshots` because that is where it had always looked. Redirecting it through `tools/labdata.py` (with the NYSE
  calendar deliberately left pinned: a corpus is state, a calendar is an authority, and an authority a rehearsal can move is not an authority)
  turned the skipped step into a run step and exposed that the rehearsal's own check was hollow: it asked only that the diff *succeed* and that a
  rehearsal name was absent from its output, so it would have passed had the tool read the real archive the whole time — which is exactly what it
  was doing. The check now requires the command to name the scratch directory it opened, which is the difference between observing a tool and
  observing its output. Practice for the archive, twice over: **write the check that would fail if the thing under test silently did the wrong
  thing, not the check that passes when the exit code agrees with you.** The same round measured rather than assumed the last unexercised command
  of the monthly block — `tools/fetch_market_data.py` already took `--out`, so a fetch could be rehearsed into a copy at all — and, on the way,
  learned that the corpus is not byte-reproducible: two fetches of the same window on the same day disagreed on 72.6% of price rows (median
  1.8e-07, max 2.31e-06 relative, worst 2003-08-25 TLT) because adjusted closes are re-derived from every later corporate action.
  `tools/corpus_drift.py` now measures that and then recomputes the four published figures from both corpora through the spec's own functions, and
  its first real run caught the author's own calibration mistake: a 1e-9 relative tolerance judged all four figures "moved" while every printed
  digit was identical, so the tolerance is now the precision each figure is published at, with one relative cap kept for the case printed
  tolerances cannot see — a monthly bill near zero, where half a cent is a doubling, and a test exists for exactly that.
