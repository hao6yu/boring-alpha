# After-tax evaluation and a target-exposure benchmark — design

Date: 2026-09-04
Status: **revision 3, approved for planning.** Revised twice after external
review; §14 records what changed and why. Spec 1 of 2 for the BA-002 programme.
Spec 2 (the BA-002 charter and signal) follows once this is implemented.
Depends on: BA-001 development and validation reviews under `docs/reviews/`.

## 1. Why this exists

BA-001 classified Inconclusive: drawdown reduction replicated in both periods,
risk-adjusted return did not. The decision taken from that record is to reframe
the research question for the successor:

> Does a timing rule earn its turnover and tax cost against a static allocation
> at a lower target exposure with the same drawdown budget, on the same eight
> sleeves, measured after tax?

BA-001 could not answer this because the laboratory cannot yet (a) compare
against a benchmark whose target exposure and rebalancing schedule are fixed in
advance, (b) measure after-tax return, or (c) evaluate criteria other than
BA-001's. This spec adds those three things. It changes no trading behaviour of
any existing strategy and no existing run's meaning.

Decisions already taken with the account holder, recorded so the spec does not
reopen them:

- Objective: drawdown first, return secondary. Drawdown budget about 20%.
- Gating benchmark: static equal-weight at a 60% target exposure, remainder in
  cash, rebalanced annually (§5). This is informed by having seen static lose
  35% in 2008; the BA-002 charter will say so.
- Tax: lot-level, stylized federal-only rates declared in the charter; the
  holder's real rates live in an untracked local config and never enter the
  record.
- Universe: BA-001's eight sleeves, unchanged.
- Any after-tax conclusion must hold under every scenario in a preregistered
  grid (§4.11) covering the tax inputs that are declared rather than known: lot
  selection method, DBC's tax character, and the qualified fraction of equity
  distributions.

## 2. Scope

In scope:

1. Snapshot methodology v2: archive distributions alongside prices.
2. A tax-lot overlay: a pure function over a run's fills, prices,
   distributions and a tax policy, producing after-tax figures under a
   scenario grid.
3. A target-exposure static benchmark with a declared rebalancing schedule,
   selectable from configuration. This needs one small engine addition: a
   signal may say "hold" (§5.2).
4. A per-strategy criteria registry, with BA-001's behaviour pinned.
5. Sweep wiring: `tax.json`, an after-tax block in `summary.md`, artifact
   schema 6 with schema 5 still classifiable, and a CLI command that applies
   the overlay to existing sweeps.
6. A post-hoc after-tax note on BA-001's two sweeps, labelled as such.

Out of scope, deliberately, each either bounded or stated in the outputs:

- State tax, the 3.8% net investment income tax, historical rate changes, and
  the ordinary-income capital-loss offset. Rates are a fixed federal-only
  scenario.
- GLD's flow-through gains from gold sold to pay expenses (§4.6 gives the
  bound).
- Foreign tax credits on EFA and EEM distributions.
- Pay-date versus ex-date timing (ex-date is used throughout).
- The mechanics of raising cash to pay tax (§4.8 states the convention and
  what it ignores).
- BA-002's rule, grid, criteria and charter (spec 2).

## 3. Data: distributions in the snapshot

### 3.1 Methodology identifier

`yahoo-adjusted-v2+dgs3mo-v1`. The price and cash files, their columns and
their derivations are unchanged from v1, so a v2 snapshot's price fingerprint
equals a v1 snapshot's whenever Yahoo has not revised history. The identifier
changes because the archive contains more, and it enters `strategy_spec_sha256`
exactly as v1 does.

### 3.2 New file

`distributions_daily.csv`, columns exactly `date, symbol, close, dividend`.

- One row per (session, symbol) present in `market_daily.csv`, same ordering.
- `close` is the unadjusted close from the chart payload.
- `dividend` is the cash amount per share on its ex-date, `0.0` otherwise.
- Both come from the payload the fetcher already requests with
  `events=div,split`; today it discards the events.

### 3.3 Splits: recorded, and the units they imply

Checked against the endpoint on 2026-09-04: IWM split 2:1 and EFA 3:1 on
2005-06-09; EEM 3:1 on 2005-06-09 and again on 2008-07-24, inside the
development period. SPY, IEF, TLT, GLD and DBC report none.

The same check showed that the endpoint's `close` does not jump across EEM's
2008 split (43.92 to 42.30 on consecutive sessions) and that its June 2008
dividend, 0.517333, equals the issuer's split-restated figure to the cent. So
`close` and `dividend` are both already in split-adjusted units, consistent
with each other and with the adjusted close. Lot accounting is therefore done
in split-adjusted shares. A split is not a taxable event: a lot's total basis and
its holding period are unchanged, and its per-share basis divides by the split
ratio, which is exactly what keeping the account in split-adjusted units does.
No adjustment is needed in the overlay.

The fetcher records every split event per symbol in the snapshot manifest under
`splits`, so a future split is visible. The distributions reader requires the
split records, either from a snapshot manifest or from the block a sweep embeds
in its own manifest (§7).

### 3.4 What does not change

`load_csv_market_data`, `MarketData`, its fingerprint, the quality checks and
the engine never see distributions. The overlay reads them through its own
reader, which enforces the column set, one row per session-symbol pair matching
the price file, finite non-negative dividends, and positive closes. The overlay
records the SHA-256 of the distributions file it used.

### 3.5 Verification before trust

Before the overlay's numbers are cited anywhere, two hand checks are done and
written into a decision record for the first v2 snapshot:

1. **EEM 2008**, which has a split in the middle of the year: the archived
   ex-dates and amounts against the issuer's published distribution history.
   Pre-split amounts should equal the issuer's split-restated figures, and a
   contemporaneous pre-split figure, if one can be sourced, should be about
   three times the archived amount; post-split amounts should equal published
   amounts directly. This is the check that proves the unit convention.
2. **SPY 2019**, a no-split control: archived amounts equal published amounts.

Tax character (§4.5) is not validated by these checks; its inputs are declared
policy, not data, which is why §4.11 gates across them.

## 4. The tax-lot overlay

Module: `boring_alpha/tax/` with `policy.py` (configuration and the scenario
grid), `lots.py` (lot matching and wash sales), `overlay.py` (the yearly
computation and outputs). Pure functions; no I/O except the distributions
reader in `boring_alpha/data/distributions.py`.

### 4.1 Inputs

- A `BacktestResult`: fills (date, symbol, side, quantity, price, notional,
  cost) and the equity curve with per-session cash.
- The `MarketData` the run used: adjusted opens and closes, cash factors.
- The distributions table: unadjusted close and dividend per session-symbol.
- A `TaxPolicy` (§4.9) and one `Scenario` from the grid (§4.11).

### 4.2 Lots in real shares

The engine's quantities are in adjusted units: a position of `q` units is worth
`q · A_t` at adjusted close `A_t`. A real account holding the same value at
unadjusted close `P_t` holds `q · A_t / P_t` shares. Because adjusted closes
sit below unadjusted closes in the past, a lot bought when `A/P` was 0.5 holds
half the engine quantity in real shares. The overlay converts every fill to
real shares at the fill's own date and keeps lots in real shares with
unadjusted-price basis:

- BUY fill on date `f`: opens a lot of `q · A_f / P_f` shares; basis is the
  fill notional plus its trading cost; open date `f`.
- SELL fill on date `f`: closes `q · A_f / P_f` shares; proceeds are the fill
  notional minus its trading cost.

Identity, tested every session: the sum of real shares across a symbol's open
lots times `P_t` equals the engine's position value `q_total · A_t` to 1e-9.

Sells close lots by the scenario's method:

- `hifo`: highest basis per share first. Specific identification, which every
  major broker supports; what a tax-aware investor does.
- `fifo`: earliest open date first. The broker default and the conservative
  bound.

Partial closes split the lot. A sell exceeding open quantity is an error: the
engine cannot produce it, so it signals corrupted inputs.

### 4.3 Distributions create their own lots

On an ex-date `u` for a symbol, for every open lot of that symbol held through
the prior session:

- Cash = the lot's real shares × `D_u`.
- Reinvestment growth implied by the data is
  `g_u = (A_u / P_u) / (A_{u-1} / P_{u-1})`. This is what the adjusted series
  actually assumes, so using it (rather than a formula for the reinvestment
  price) keeps the identity in §4.2 exact.
- A child lot opens with real shares = the lot's shares × `(g_u − 1)`, basis =
  the cash, open date `u`. It is a purchase in its own right, with its own
  basis and holding period, as the tax code treats reinvested distributions.
- What happens to the parent depends on the distribution's character (§4.5):
  an **income** distribution leaves the parent's basis alone and the cash is
  taxed; a **return-of-capital** distribution reduces the parent's basis by
  the cash and nothing is taxed. Total basis rises by a taxed distribution and
  is unchanged by an untaxed one, which is the rule the code applies to both.

The identity extends: total income plus total capital gain over a lot's life
equals its adjusted profit and loss.

### 4.4 Cash interest

The engine's cash earns the session factor. That interest is ordinary income in
a taxable account. Interest per session is `cash_{t-1} · (factor_t − 1)` from
the equity curve's cash column, summed by calendar year.

### 4.5 Character of income and gains

**Distributions of `standard` and `collectibles` symbols are income.** Each
such symbol carries a `qualified_fraction` in `[0, 1]`; the scenario (§4.11)
selects the base set or the low set. A lot's distribution is qualified in that
fraction only if the lot passes the holding-period test: held more than 60 days
within the 121-day window beginning 60 days before the ex-date. The test uses
the complete fill history, since the window can cross a year end; a lot still
open at the period end is tested against the liquidation date. Qualified income
is taxed at the long-term rate; the remainder, and all income of lots failing
the test, at the ordinary rate. A monthly rule that holds a sleeve for one or
two months will often fail this test; a buy-and-hold benchmark never does.

Fund-year qualified fractions exist in issuer tax summaries but would need
archiving from PDFs. The policy declares one base fraction per symbol and one
low fraction applied to every equity sleeve, and §4.11 requires conclusions to
hold under both.

**Capital gains** by `gains_class`:

- `standard`: short-term if `(sale_date − open_date).days ≤ 365`, else
  long-term. The statute says "more than one year" and starts the clock the day
  after acquisition; the day-count is a stated approximation.
- `collectibles`: as standard, but long-term gains are taxed at the
  collectibles rate. GLD is a grantor trust holding gold; its long-term gains
  are collectibles gains.
- `commodity_pool`: DBC. It is taxed as a partnership: holders receive a
  yearly K-1 allocating the pool's income and its futures gains marked to
  market under Section 1256, and its cash distributions are adjustments to
  outside basis rather than income. What that allocation equals is not
  derivable from prices, so the class has two treatments and the scenario grid
  runs both:
  - `deferral`: capital gains as `standard`; distributions are return of
    capital (§4.3). The lower bound on tax: it credits DBC with deferral it does
    not have.
  - `mtm_60_40`: at each year end every open lot's change in adjusted value
    over the year is treated as realized, 60% long-term and 40% short-term,
    and the lot's basis is stepped to market; a later sale realizes only the
    change since the last mark. Distributions are return of capital. A
    stress treatment: the true allocation also contains ordinary interest
    income on the pool's collateral, which this does not separate.

  Neither is claimed to reproduce a K-1. The conclusion must hold under both.

Rates for the collectibles class: the statutory rule is ordinary rate capped at
28%, so `collectibles_rate` must satisfy `collectibles_rate ≤ min(ordinary_rate,
0.28)`; the configuration default is that minimum.

### 4.6 Wash sales

Monthly signals exit and re-enter sleeves about thirty days apart, and monthly
rebalancing buys back what it sold a month earlier, so wash sales are common in
both strategy and benchmark. They are adjusted, not counted:

- A SELL that realizes a loss is a wash sale to the extent the same symbol was
  bought within 30 calendar days before or after, counting child lots from
  reinvested distributions as purchases. Replacement shares are matched once.
- The disallowed loss (proportional to matched shares) is added to the
  replacement lot's basis, and the sold lot's holding period is added to the
  replacement lot's.
- Reported: `wash_sale_count` and `wash_sale_disallowed_total`.

**GLD expense sales.** The trust sells gold to pay its expense ratio, and
holders recognize their share of the resulting gain or loss with a basis
adjustment. Bound: about 0.4% of assets a year is sold, only the appreciated
fraction of it is gain, taxed at the collectibles rate, on a sleeve of 12.5%.
Even with gold at twice its basis that is on the order of one hundredth of one
percent of portfolio return a year. Not modelled; stated in the outputs as a
known omission with this bound.

### 4.7 Year end

At the last session of each calendar year, and at the period's final session:

1. Commodity-pool marks under `mtm_60_40` (§4.5) are computed and added to the
   year's short-term and long-term amounts.
2. Net short-term gains and losses; net long-term gains and losses; the
   collectibles long-term bucket separately.
3. Carried-forward losses are applied **retaining character**: the short-term
   carryover against net short-term, the long-term carryover against net
   long-term (collectibles bucket first, then the rest). If one character nets
   negative and the other positive, offset. Remaining net losses carry forward
   in their own pools without limit.
4. Tax = positive net short-term × ordinary rate + positive net long-term
   (standard) × long-term rate + positive net collectibles × collectibles rate
   + qualified income × long-term rate + ordinary income × ordinary rate + cash
   interest × ordinary rate.

### 4.8 The after-tax NAV convention

Every rule in this engine is homogeneous in account size: target weights are
proportions, costs are proportional to notional, and cash accrues by a factor.
A run started with twice the cash produces exactly twice the equity curve (a
test pins this). The overlay uses that to define after-tax wealth as the
pre-tax path **rescaled at each year end by the tax paid**, computed from the
pre-tax artifacts without re-running:

- Let `c` be the cumulative scale, starting at 1. For year `y`, all raw
  amounts (gains, income, interest, marks) computed from the unscaled lots are
  multiplied by `c_y`; carryovers are already in scaled dollars.
- `tax_y` is computed from those scaled amounts. After-tax equity at year end
  is `c_y · W_y − tax_y`, and `c_{y+1} = c_y − tax_y / W_y`.
- Pre-liquidation after-tax terminal wealth is `c · W_T` after the final year's
  tax.
- Liquidation: the final year is computed twice, without and with every open
  lot treated as sold at the last session (gains by holding period, wash-sale
  and mark rules applied). `tax_liquidation` is the difference. Post-liquidation
  wealth is the pre-liquidation figure minus it. Nothing is subtracted twice.

This is an accounting convention, not a transaction: no brokerage lets you
shrink every position and lot proportionally without selling. What it ignores,
each second order here because both accounts average 35 to 40% cash and would
pay tax from it: the trading cost of raising cash when cash is short; the gain
realized by doing so; and the drift in exposure between the payment and the
next scheduled rebalance. The first two, when they occur, fall more heavily on
the strategy paying more tax, so the convention is mildly favourable to it. The
convention is stated in the outputs by name.

Revision 1 charged taxes paid outside the account the cash rate. That
understated the cost for the strategy paying more tax whenever the portfolio
beat cash, and is withdrawn.

Post-liquidation wealth is the gating figure in spec 2, because it is the only
apples-to-apples comparison between a strategy that realizes gains and a
benchmark that defers them. Both figures are reported.

### 4.9 Policy

Configured in a new optional `[tax]` table. All keys required when present.

```toml
[tax]
distributions_path = "../data/current/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28          # must be <= min(ordinary_rate, 0.28)
qualified_fraction_low = 0.50     # applied to every income-paying equity
                                  # sleeve in the low scenario
# Federal-only stylized scenario. State tax, the 3.8% net investment income
# tax and historical rate changes are ignored by construction.

[tax.qualified_fraction]          # base scenario: share of distributions
SPY = 0.95                        # eligible for the long-term rate when the
IWM = 0.71                        # holding-period test passes
EFA = 0.95
EEM = 0.61
IEF = 0.0
TLT = 0.0
GLD = 0.0                         # no distributions
DBC = 0.0                         # not used: commodity_pool distributions are
                                  # return of capital

[tax.gains_class]                 # standard | collectibles | commodity_pool
SPY = "standard"
IWM = "standard"
EFA = "standard"
EEM = "standard"
IEF = "standard"
TLT = "standard"
GLD = "collectibles"
DBC = "commodity_pool"
```

Every symbol in `strategy.symbols` must appear in both tables; unknown symbols,
classes or fractions outside `[0, 1]` are errors. Rates must be finite and in
`[0, 1)`. The policy's canonical JSON is hashed to `tax_policy_sha256`.

The base fractions for IWM, EFA and EEM are the issuer's reported 2019 figures
as cited in the external review of revision 2 (71.18%, 95.35%, 60.55%); I have
not opened the issuer document myself, and the SPY figure is my expectation
rather than a reported number. They are declared inputs for the record, and the
account holder confirms them against the issuer summaries before spec 2 fixes
them in a charter. Whatever they are, §4.11 requires the conclusion to survive
the low set too.

### 4.10 Outputs

`TaxResult`, serialized as JSON, once per scenario (§4.11):

- `scenario`: lot method, commodity-pool treatment, qualified set.
- `policy`: the policy as applied, `tax_policy_sha256`,
  `distributions_sha256`, `overlay_version` (`tax-overlay-v1`), and the
  `code_sha256` of the code that computed it.
- `by_year`: qualified and ordinary income, cash interest, short-term and
  long-term gains and losses, collectibles gains, commodity-pool marks,
  return-of-capital basis reductions, wash-sale disallowed losses, carryovers
  used and remaining by character, scale factor, tax paid.
- `totals`: taxes paid, `tax_liquidation`, `wash_sale_count`,
  `wash_sale_disallowed_total`, unrealized gain at period end, open lot count,
  the GLD expense-sale omission stated with its bound, and the name of the NAV
  convention.
- `wealth`: `pre_tax_terminal`, `after_tax_pre_liquidation`,
  `after_tax_post_liquidation`.
- `metrics`: `after_tax_cagr` (post-liquidation, from initial cash over the
  period), `tax_drag_bps` (pre-tax CAGR minus after-tax CAGR, ×10⁴),
  `effective_tax_rate` (total tax / pre-tax profit, when profit is positive).
- `identity_checks`: the §4.2 share identity and the §4.3 income-plus-gain
  identity, each with its maximum absolute deviation.

Drawdown is not recomputed. It remains the pre-tax figure from the equity
curve: tax is owed on realized gains and does not change the path you live
through.

### 4.11 The scenario grid

Three tax inputs are declared rather than known: how lots are selected, what
DBC's K-1 allocates, and what fraction of equity distributions is qualified.
Rather than defend point estimates, the overlay runs every combination and any
criterion that uses after-tax figures must hold under all of them:

| Axis | Values |
|---|---|
| Lot method | `hifo`, `fifo` |
| Commodity-pool treatment | `deferral`, `mtm_60_40` |
| Qualified fractions | `base`, `low` |

Eight scenarios per run. The cost is trivial. The rule is one sentence: an
after-tax conclusion that depends on an assumption we cannot verify is not a
conclusion. `summary.md` reports the full grid, and the spec 2 criterion is
evaluated against the worst scenario for the strategy and the best for the
benchmark, which is what "holds under all" means when strategy and benchmark
are compared.

The grid is fixed in code, not configuration, so it cannot be narrowed after a
result is seen. Adding an axis is a code change with a new `overlay_version`.

## 5. Target-exposure benchmark

### 5.1 Configuration

```toml
[benchmark]
exposure = 0.60
rebalance = "annual"     # annual | monthly
```

When present, the gating benchmark for the strategy's profile (§6) is static
equal-weight scaled to a target exposure of `exposure` with the remainder in
cash, named `Target-Exposure Benchmark (60%, annual)`. Realized exposure
drifts between rebalances, which is why it is a target and not a fixed figure.
Both keys enter `strategy_spec_sha256` — only when the table is present, so
every existing BA-001 spec hash is unchanged. `exposure` must be finite and in
`(0, 1]`.

Rebalancing schedule is part of the benchmark's definition because it drives
its turnover and therefore its tax cost. BA-001's chartered benchmark
rebalances monthly, and that does not change. For a taxable investor holding a
fixed allocation the realistic practice is yearly rebalancing, which is why it
is the recommended value for BA-002. `annual` means: establish the allocation
at the first session of the run, then rebalance to target on the first session
of each calendar year (the December month-end signal); every other month-end
signal is a hold.

### 5.2 The one engine addition: hold

`SignalSnapshot` gains a field `hold: bool = False`, meaning "keep the current
allocation". The engine executes a pending hold snapshot as follows: if the
portfolio has never held a position, it rebalances to the snapshot's target
weights exactly as for a normal snapshot, because there is no allocation to
keep; otherwise it records the decision and places no orders. A run that starts
in July therefore enters on its first session under an annual policy, then
rebalances the following January. Nothing else in the engine changes.

Serialization: the decisions writer omits `hold` when it is false, so every
existing decisions file is reproduced byte for byte. The precise preservation
claim, pinned by a test on the checked-in synthetic run: equity, trades and
decisions files are byte-identical to today's; `manifest.json` differs only in
`artifact_schema` and `code_sha256`, as any code change makes it.

`ScaledAllocation` takes a `rebalance` argument and returns hold snapshots on
non-rebalance month-ends. Its trades CSV therefore shows an entry and then one
rebalance per January, which a test checks.

### 5.3 Reporting

Whenever a target-exposure benchmark gates, the full static allocation, the
ex-post exposure-matched allocation and cash remain as secondary rows, so a
reader can see all comparisons.

## 6. Per-strategy criteria registry

`criteria.py` currently hard-codes BA-001's variant names, C1–C5 and the
verdict rule, and `sweep.py` hard-codes its grid. Both move behind a profile:

```python
class StrategyProfile(Protocol):
    strategy_id: str
    def grid(self, config: AppConfig) -> dict[str, VariantSpec]: ...
    def evaluate_period(self, variants, extras) -> PeriodOutcome: ...
    def classify(self, development, validation) -> Verdict: ...
```

- `VariantSpec` carries a description, a strategy policy factory and a
  benchmark policy factory, so a profile decides both what runs and what it is
  compared against.
- `extras` carries what criteria may need beyond variant metrics: the tax
  results for every scenario and the secondary benchmarks' metrics.
- `PROFILES = {"BA-001": BA001Profile()}`; spec 2 adds `"BA-002"`. A config
  whose `strategy.id` has no profile is an error.

BA-001's profile must be behaviour-identical. The two existing sweeps'
`criteria.json` files are copied into `tests/fixtures/` and a test replays
their `variants` through `BA001Profile.evaluate_period`, asserting identical
criterion names, pass flags and detail strings, and that `classify` on the pair
returns `inconclusive`.

### 6.1 Classification checks

`run_classify` keeps its existing agreement checks and adds:

- `tax_policy_sha256` must be present in both sweeps and identical whenever
  either sweep has one. Development and validation must be scored under one
  policy.
- Schema compatibility replaces the exact-schema check: `READABLE_SCHEMAS =
  (5, 6)`. Both sweeps must still share a schema. A schema-5 pair (BA-001's)
  classifies exactly as today, and the golden test proves it against the real
  fixtures. Schema 6 adds fields; it removes none.

## 7. Sweep wiring, artifacts, CLI

- When `[tax]` is present, `run_sweep` applies the overlay under every scenario
  to the base strategy, the gating benchmark, the full static benchmark, the
  exposure-matched benchmark and cash, and to every variant's strategy,
  because a stability check on after-tax return will need them in spec 2.
- The sweep archives `input_distributions.csv.gz` beside the existing price
  and cash inputs, truncated at the period end like everything else, and
  embeds the distributions snapshot's `methodology`, `created_at`, `splits`
  and file SHA-256 in `manifest.json` under `distributions_manifest`. The
  reader accepts that block in place of a snapshot manifest, so a sweep
  directory is self-contained for re-scoring.
- `write_sweep_report` writes `tax.json` (write-once) and adds an "After tax"
  block to `summary.md`: for the strategy and each benchmark, pre-tax CAGR and
  after-tax CAGR post-liquidation under every scenario, the worst-case scenario
  for each, tax drag, taxes paid, liquidation tax and wash-sale disallowed
  totals, then one line naming the rates, the NAV convention and the ignored
  items.
- `manifest.json` and `criteria.json` gain `tax_policy_sha256` and
  `distributions_sha256` when tax is configured; `artifact_schema` becomes 6.
- New CLI command:

  ```bash
  boring-alpha aftertax experiments/BA-001/sweeps/<id> --policy configs/tax_policy.toml \
      --distributions data/current/distributions_daily.csv
  ```

  It reconstructs each variant's `BacktestResult` from the archived trades and
  equity CSVs, the archived price and cash inputs, and the initial cash in the
  manifest's embedded configuration; reads split records from the
  distributions snapshot's manifest; truncates the distributions at the
  sweep's `data_end`; applies the overlay under every scenario; and writes
  `tax-<policy-hash-12>-<distributions-hash-12>-<code-hash-12>.json` into the
  sweep directory. The name is derived from every input including the overlay
  implementation, so a corrected overlay produces a separately identified
  result rather than colliding with an old one, and re-running with identical
  inputs is idempotent.

## 8. BA-001 post-hoc note

Once the overlay is trusted (§3.5, §9), run `aftertax` on sweeps
`4b9d1479f811d108` and `f0a36ea722ebefd4` with the stylized policy, and write
`docs/notes/2026-MM-DD-BA-001-after-tax.md`: after-tax CAGR and tax drag for
the strategy, full static and exposure-matched in both periods, across the
scenario grid, with wash-sale totals. It is a diagnostic computed after the
results were known, and the note says so in its first line. It is not a review
and does not change BA-001's classification. Its purpose is to calibrate
expectations for BA-002 and to exercise the machinery on real trades before
anything depends on it.

## 9. Testing plan

Tests are written before the code they exercise, in the project's existing
style (unittest, `tests/test_*.py`, fixtures under `tests/fixtures/`).

Engine (`test_backtest.py`):
- Homogeneity: a synthetic run at 2× initial cash produces an equity curve
  equal to 2× the original at every session, to 1e-6 relative.
- A hold snapshot on an empty portfolio rebalances to its targets; a hold
  snapshot on a held portfolio records a decision and places no orders.
- A policy that never holds produces byte-identical equity, trades and
  decisions files to today's on the checked-in synthetic configuration; the
  decisions writer omits a false `hold`.

Fetcher (`test_fetcher.py`):
- `rows_from_chart` also returns unadjusted close and dividend per session
  from a fixture payload with dividend and split events; zero on non-ex-dates;
  the incomplete-session rule still applies; splits land in the manifest.

Distributions reader (`test_distributions.py`):
- Exact column set; a missing session-symbol pair relative to the price file is
  an error; negative or non-finite dividend is an error; split records are
  accepted from a snapshot manifest or an embedded block, and their absence is
  refused.

Lots (`test_tax_lots.py`):
- Real-share conversion: a lot bought when `A/P` is 0.5 holds half the engine
  quantity in real shares, and the §4.2 identity holds every session on a
  fixture with several ex-dates.
- HIFO and FIFO on hand-computed buys, child lots and partial sells; closed
  quantities, basis and proceeds (including costs) match by hand.
- Child lots: cash and share growth reproduce the adjusted series; the
  income-plus-gain identity holds to 1e-9.
- Return of capital reduces the parent's basis by the cash and the child opens
  with that basis, so total basis is unchanged; an income distribution leaves
  the parent alone.
- Wash sales: a loss sale with a repurchase 30 days later is disallowed and
  the basis and holding period transfer; 31 days later is not; a reinvested
  child lot counts as a purchase; replacement shares match once.

Overlay (`test_tax_overlay.py`):
- Holding period: 365 days short-term, 366 long-term.
- Qualified test: a lot held 61 days across the ex-date qualifies; 60 does not;
  a December ex-date whose window closes in February is decided correctly;
  the fraction applies only to qualifying lots; the low scenario replaces every
  equity fraction.
- Carryovers retain character across a loss year and a gain year.
- Collectibles class routes long-term gains to the collectibles rate; a policy
  with `collectibles_rate` above the cap is rejected.
- Commodity pool: under `mtm_60_40` a lot held across a year end is marked
  60/40 and its later sale realizes only the change since the mark; under
  `deferral` the same lot realizes everything at sale; both treat the
  distribution as return of capital.
- Cash interest is taxed yearly and equals the sum of session interest.
- Rescaling: after-tax terminal wealth equals the terminal wealth of a run
  whose equity was reduced by each year's tax at year end (constructed
  fixture), to 1e-9.
- Liquidation equals selling every open lot on the last session; nothing is
  subtracted twice.
- The grid produces exactly eight scenarios, fixed in code, each with its
  scenario stamp.
- Determinism: identical inputs produce identical JSON and hashes.

Benchmark (`test_config.py`, `test_signals.py`):
- `[benchmark]` produces weights summing to the exposure; out-of-range or
  non-finite rejected; the spec hash changes with either key and is unchanged
  when the table is absent.
- `annual` trades on the first session and each January only, including a run
  that starts mid-year.

Registry and CLI (`test_criteria.py`, `test_classify.py`, `test_cli.py`):
- Golden replay of BA-001's two `criteria.json` fixtures, and that they
  classify under the schema-compatibility path.
- Mismatched or missing `tax_policy_sha256` refused; unknown strategy id
  refused.
- `aftertax` output names include the code fingerprint; the same inputs under a
  different fingerprint produce a second file rather than a refusal.

Sweep (`test_sweep.py`):
- With `[tax]`, a synthetic sweep writes `tax.json`, archives the
  distributions input, embeds the distributions manifest block and adds the
  after-tax block; without it, equity, trades and decisions files are
  byte-identical to today's.
- `aftertax` on a synthetic sweep directory reconstructs the runs and writes an
  input-hashed file; running it twice does not rewrite; the in-sweep
  `tax.json` and the reconstructed result agree to 1e-9.

## 10. Financial judgment calls, and why

The account holder asked for best-practice guidance rather than neutral
options. These are the calls in this spec, the alternative, and when the
alternative would be right.

- **Gate across a scenario grid rather than on point estimates.** Lot
  selection, DBC's K-1 and qualified fractions are things we declare, not
  things we know. Requiring the conclusion to hold under every combination
  costs nothing to compute and removes the temptation to pick the assumption
  that flatters a result. Gating on a single "best estimate" would be right
  only with archived fund-year tax data and a K-1 history, which we do not
  have.
- **Gate on post-liquidation wealth, report pre-liquidation.** This is how
  fund after-tax returns are conventionally presented, because deferral is a
  real benefit that must be priced when buy-and-hold is compared with trading.
  Pre-liquidation is the right figure only for an investor who will never sell,
  which is a personal fact, not a strategy property.
- **An after-tax NAV convention, named as such.** Rescaling is exact under the
  engine's homogeneity and needs no opportunity-cost assumption; what it skips
  is second order for accounts that hold this much cash, and it is stated.
  Modelling withdrawal mechanics would be right only if either account were
  routinely fully invested.
- **Tax cash interest.** A cash-heavy rule that ignores tax on interest
  understates its own cost. Treasury bill interest is federally taxable.
- **Annual rebalancing for the target-exposure benchmark.** The benchmark is
  supposed to be what you would actually hold without a strategy, and a
  taxable investor holding a fixed allocation does not rebalance it monthly.
  Monthly would be right only if the comparison were meant to isolate signal
  from schedule, which is what BA-001's benchmark did and will keep doing.
- **Model wash sales rather than count them.** Monthly exit and re-entry makes
  them frequent for exactly the strategies being tested; counting them would
  leave the gating figure knowingly wrong.
- **Keep DBC and bracket its tax character.** Dropping it changes the universe
  you decided to keep; picking one treatment asserts a K-1 we have not seen.
  Two treatments and a rule that both must pass is the honest middle.
- **State GLD's expense-sale omission with a bound rather than model it.** The
  bound is small enough that modelling would add complexity without changing a
  decision.
- **Stylized federal-only rates in the record, real rates locally.** A charter
  must be reproducible by someone who is not you. Your bracket, state and
  filing status are inputs to your decision, not to the strategy's. The
  collectibles rate is the lower of your ordinary rate and 28%, not 28%
  automatically.
- **Drawdown stays pre-tax.** Realized-loss harvesting during drawdowns is a
  genuine offset, but modelling it rewards the strategy for losing money
  cleverly. Left out on purpose.
- **What I am not certain of.** GLD's collectibles treatment, the day-count
  approximation of "more than one year", and both DBC treatments are my
  understanding of the rules, consistent with the IRS and issuer materials the
  external reviews cited, and not verified tax advice. The base qualified
  fractions are numbers I have taken from a review rather than read myself.
  Each is a declared policy input or a grid axis, so correcting one is a policy
  change, not a code change, and the grid is what keeps a wrong one from
  deciding anything.

## 11. Open items before implementation is complete

1. Fetch a v2 snapshot and perform the §3.5 hand checks (EEM 2008, SPY 2019).
2. Account holder confirms or amends the stylized rates, the base qualified
   fractions (including SPY's), and the gains classes in §4.9, against the
   issuer summaries and tax documents.
3. Decide the location of the post-hoc note (`docs/notes/` proposed).

## 12. Implementation order

1. Engine homogeneity test, the `hold` snapshot with its empty-portfolio rule,
   and the compatible decisions serializer, with tests.
2. Fetcher v2 and the distributions reader (both manifest sources), with
   tests. Fetch a snapshot and do the hand checks.
3. `boring_alpha/tax/`: policy and scenario grid, lots (child lots, return of
   capital, wash sales), overlay (character, marks, year end, rescaling,
   liquidation), with tests.
4. `[benchmark]` configuration and the annual-rebalance policy, with tests.
5. Criteria registry refactor, schema compatibility and the tax-policy check,
   with the BA-001 golden tests.
6. Sweep wiring, `tax.json`, distributions archive and embedded manifest,
   summary block, schema 6, `aftertax` CLI.
7. BA-001 post-hoc note.

Each step leaves the test suite green and the existing behaviour intact. The
implementation plan will break these into tasks.

## 13. Not decided here

- BA-002's rule, grid, and the exact after-tax criteria and thresholds: spec 2.
- Whether the target-exposure benchmark should use tolerance bands instead of a
  calendar: a reasonable alternative, deferred so that the benchmark stays
  simple enough to be obviously what a passive holder would do.

## 14. Revision log

- **Revision 1 (2026-09-04).** Initial design.
- **Revision 2 (2026-09-04).** After an external review. Adopted: real-share
  lot accounting replacing an incorrect adjusted-unit conversion that doubled
  income for old lots; reinvested distributions as separately dated lots;
  trading costs in basis and proceeds; splits recorded rather than halted,
  after verifying the endpoint's units against EEM's 2008 split; Section 1256
  stylization for DBC replacing standard treatment; per-symbol qualified
  fractions with the 61-day holding-period test replacing a flat qualified
  flag; character-retaining loss carryovers; an unambiguous liquidation
  definition; taxes paid from inside the account by exact rescaling replacing
  cash-rate compounding; wash-sale adjustment replacing a count; identical tax
  policy required at classification; distributions archived in sweeps; overlay
  code fingerprint on post-hoc outputs; schema-5 artifacts kept classifiable
  with a test; the benchmark's rebalancing schedule named, configured and
  hashed, with annual as the recommended value; both lot methods gate. Pushed
  back on one item: GLD's expense-sale gains are stated with a bound rather
  than modelled, because the bound is immaterial.
- **Revision 3 (2026-09-04).** After a second external review. Corrected an
  inverted real-share test in §9. Renamed the rescaling an after-tax NAV
  convention and stated the three effects it ignores, since it is not a
  brokerage transaction. Return-of-capital distributions now reduce the parent
  lot's basis, which the generic child-lot rule had failed to do. DBC's
  treatment is no longer asserted: a `commodity_pool` class runs two
  treatments, deferral and full-return 60/40 mark, and both must pass.
  Qualified fractions are no longer called conservative; a base set and a low
  set both gate, with the base set taken from the review's cited 2019 figures
  pending confirmation. These three uncertainties form a fixed eight-scenario
  grid (§4.11). The post-hoc filename includes the overlay code fingerprint.
  Sweeps embed the distributions manifest so they are self-contained. Hold has
  a defined meaning on an empty portfolio, and the decisions serializer omits a
  false hold so existing files stay byte-identical, with the preservation
  claim restated precisely. Splits described correctly (total basis and
  holding period preserved, per-share basis divided). The qualification window
  is evaluated over the complete fill history. The benchmark is named a
  target-exposure benchmark because realized exposure drifts.
- **Revision 3.1 (2026-09-04).** After implementation of plan 1. §3.3 and
  §3.5's one-third relationship for EEM's June 2008 dividend was replaced,
  because the hand check could not source a contemporaneous pre-split figure
  and instead closed the unit question by inference: the archived amount
  equals the issuer's currently published, split-restated figure to the
  cent, which is what it would equal if it were already in split-adjusted
  units, and roughly three times what it would equal otherwise (see
  `docs/decisions/2026-09-04-distributions-v2.md`). §5.2's `ScaledAllocation`
  was not given a `rebalance` argument; instead a new subclass,
  `TargetExposureAllocation`, carries the rebalancing schedule, so the
  exposure-matched diagnostic keeps its monthly behaviour and its archived
  name.
