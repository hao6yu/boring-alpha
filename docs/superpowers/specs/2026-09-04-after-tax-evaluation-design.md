# After-tax evaluation and a fixed-exposure benchmark — design

Date: 2026-09-04
Status: **draft for review.** Spec 1 of 2 for the BA-002 programme. Spec 2 (the
BA-002 charter and signal) follows once this is implemented.
Depends on: BA-001 development and validation reviews under `docs/reviews/`.

## 1. Why this exists

BA-001 classified Inconclusive: drawdown reduction replicated in both periods,
risk-adjusted return did not. The decision taken from that record is to reframe
the research question for the successor:

> Does a timing rule earn its turnover and tax cost against a fixed
> lower-exposure static allocation with the same drawdown budget, on the same
> eight sleeves, measured after tax?

BA-001 could not answer this because the laboratory cannot yet (a) compare
against a benchmark whose exposure is fixed in advance rather than matched after
the fact, (b) measure after-tax return, or (c) evaluate criteria other than
BA-001's. This spec adds those three things and nothing else. It changes no
trading behaviour and no existing run's meaning.

Decisions already taken with the account holder, recorded here so the spec does
not reopen them:

- Objective: drawdown first, return secondary. Drawdown budget about 20%.
- Gating benchmark: static equal-weight scaled to 60% exposure, remainder in
  cash, fixed a priori. This is informed by having seen static lose 35% in 2008;
  the BA-002 charter will say so.
- Tax: lot-level, stylized rates declared in the charter; the holder's real
  rates live in an untracked local config and never enter the record.
- Universe: BA-001's eight sleeves, unchanged.

## 2. Scope

In scope:

1. Snapshot methodology v2: archive distributions alongside prices.
2. A tax-lot overlay: a pure function over a run's fills, prices,
   distributions and a tax policy, producing after-tax figures.
3. A fixed-exposure static benchmark selectable from configuration.
4. A per-strategy criteria registry, with BA-001's behaviour pinned.
5. Sweep wiring: `tax.json`, an after-tax block in `summary.md`, artifact
   schema 6, and a CLI command that applies the overlay to existing sweeps.
6. A post-hoc after-tax note on BA-001's two sweeps, labelled as such.

Out of scope, deliberately:

- Any change to the engine, signal, portfolio, execution, loader, or gates.
- BA-002's rule, grid, criteria and charter (spec 2).
- Wash-sale adjustment, state tax, the ordinary-income loss offset, Section
  1256 mark-to-market for commodity pools, foreign tax credits, and pay-date
  versus ex-date timing. Each is either counted or stated, not modelled.
- Taxes paid from inside the account (which would change position sizing).
  See §4.6 for why the outside-the-account treatment is acceptable here.

## 3. Data: distributions in the snapshot

### 3.1 Methodology identifier

`yahoo-adjusted-v2+dgs3mo-v1`. The price and cash files, their columns, and
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

### 3.3 Splits halt the fetch

The lot accounting assumes share counts change only by trading. The fetcher
records every split event per symbol in the manifest under `splits` and, if any
symbol has one, prints them and exits non-zero without writing a snapshot. I
believe none of the eight ETFs has split, and this is how the belief is checked
rather than assumed. If a split ever appears, the overlay needs a share-factor
adjustment (a small extension), and the halt is what forces that work to happen
before a wrong number is produced.

### 3.4 What does not change

`load_csv_market_data`, `MarketData`, its fingerprint, the quality checks and
the engine never see distributions. The overlay reads them through its own
reader, which enforces the column set, one row per session-symbol pair matching
the price file, finite non-negative dividends, and positive closes. The overlay
records the SHA-256 of the distributions file it used.

### 3.5 Verification before trust

Before the overlay's numbers are cited anywhere, one symbol-year is checked by
hand: the archived ex-dates and amounts for SPY in 2019 against the issuer's
published distribution history. The result is written into the manifest note
of the first v2 snapshot's decision record. I have not verified that the chart
endpoint's dividend amounts are actual cash per share rather than adjusted
amounts; this check is what settles it.

## 4. The tax-lot overlay

Module: `boring_alpha/tax/` with `policy.py` (configuration), `lots.py` (lot
matching), `overlay.py` (the yearly computation and outputs). Pure functions;
no I/O except the distributions reader in `boring_alpha/data/distributions.py`.

### 4.1 Inputs

- A `BacktestResult` (fills with date, symbol, side, quantity, price; the
  equity curve with per-session cash).
- The `MarketData` the run used (adjusted opens and closes, cash factors).
- The distributions table (unadjusted close and dividend per session-symbol).
- A `TaxPolicy` (§4.7).

### 4.2 Lots

Every BUY fill opens a lot: symbol, open date, quantity in the engine's units,
adjusted cost per unit (the fill price), and a running `reinvested` amount
starting at zero. Every SELL fill closes quantity from open lots of that symbol
by the policy's method:

- `hifo` (default): highest adjusted cost per unit first. This is what specific
  identification permits a taxable investor to do, and it is the realistic
  choice for anyone who is paying attention.
- `fifo`: earliest open date first. The broker default and the conservative
  bound. Always computed alongside as a diagnostic; never the criterion.

Partial closes split the lot; the closed portion carries its share of
`reinvested`.

### 4.3 Distributions on adjusted prices

The engine's prices are dividend-adjusted, so a lot's adjusted growth already
contains reinvested distributions. Taxing income yearly *and* taxing the full
adjusted gain at sale would tax distributions twice. The overlay separates the
two components exactly:

- Let `A` be the adjusted close and `P` the unadjusted close. The ratio `A/P`
  is the cumulative reinvestment factor (up to a constant), because the only
  adjustments are dividends (§3.3 guarantees no splits).
- A lot of `q` units opened on date `b` holds, in real shares on session `t`,
  `q · (A_t / P_t) / (A_b / P_b)`.
- On an ex-date `t` with dividend `D_t`, income for the lot is
  `real_shares_{t-1} · D_t`, where `t-1` is the prior session. It is taxed as
  income in the calendar year of `t` at the symbol's distribution class rate,
  and added to the lot's `reinvested` basis.
- At sale, the lot's capital gain is
  `q_sold · (fill_price − adjusted_cost) − reinvested_sold`.

Identity: income + capital gain = adjusted P&L, so nothing is taxed twice or
missed. Simplification, stated: reinvested amounts inherit the parent lot's
open date for the holding-period test, which slightly favours long-term
treatment. Its size is bounded by dividend yield times the short-term/long-term
rate gap and is reported (§4.8, `reinvested_income_total`).

### 4.4 Cash interest

The engine's cash earns the session factor. That interest is ordinary income
in a taxable account (Treasury bill interest is federally taxable), and a rule
that holds 35–40% cash must bear it. Interest per session is
`cash_{t-1} · (factor_t − 1)`, read from the equity curve's cash column; summed
by calendar year and taxed at the ordinary rate.

### 4.5 Year end

At the last session of each calendar year, and at the period's final session:

1. Net short-term gains and losses; net long-term gains and losses; separately.
2. If one net is negative and the other positive, offset.
3. Apply carried-forward loss (a single pool, applied to short-term first, then
   long-term). Any remaining net loss carries forward without limit.
4. Tax = positive net short-term × ordinary rate + positive net long-term ×
   long-term rate + positive net collectibles long-term × collectibles rate
   + income × class rates + cash interest × ordinary rate. Collectibles
   long-term gains are their own bucket; net losses offset it last. The
   statute's ordering rules for the 28% group are more involved; this is a
   stated simplification.

Holding period: long-term if `(sale_date − open_date).days > 365`. The statute
says "more than one year" and starts the clock the day after acquisition; the
day-count is a stated approximation.

Wash sales are not adjusted. The overlay counts `wash_sale_candidates`: SELL
fills that realize a loss where the same symbol has a BUY fill within 30
calendar days before or after. A monthly rule re-entering a sleeve one month
after exiting it will sometimes trip this. The count says how much the omission
could matter.

### 4.6 Paying the tax

Taxes are paid from outside the account at each year end and charged the cash
return they could have earned: after-tax terminal wealth is

```
W_after = W_T − Σ_y tax_y · (cash_index_T / cash_index_{y_end}) − tax_liquidation
```

Paying from outside avoids changing position sizes, so pre-tax artifacts stay
exactly what the engine produced and the overlay remains a pure function over
them. The bias is that the money paid in tax would in reality have been invested
rather than earning cash; charging cash rather than the portfolio's return is
the conservative side of that error for the strategy paying more tax.

Terminal liquidation: every open lot is treated as sold at the last session's
adjusted close, its gain classified and taxed in the final year's netting.
Reported both ways (§4.8). Gating (in spec 2) uses the post-liquidation figure,
because it is the only apples-to-apples comparison between a strategy that
realizes gains and a benchmark that defers them.

### 4.7 Policy

Configured in a new optional `[tax]` table. All keys required when present.

```toml
[tax]
distributions_path = "../data/current/distributions_daily.csv"
lot_method = "hifo"            # hifo | fifo (fifo is always also reported)
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28

[tax.distribution_class]       # qualified (long_term_rate) | ordinary
SPY = "qualified"
IWM = "qualified"
EFA = "qualified"
EEM = "qualified"
IEF = "ordinary"
TLT = "ordinary"
GLD = "ordinary"
DBC = "ordinary"

[tax.gains_class]              # standard | collectibles (long-term at collectibles_rate)
SPY = "standard"
IWM = "standard"
EFA = "standard"
EEM = "standard"
IEF = "standard"
TLT = "standard"
GLD = "collectibles"
DBC = "standard"
```

Every symbol in `strategy.symbols` must appear in both class tables; unknown
symbols and unknown class names are errors. Rates must be finite and in
`[0, 1)`. The policy's canonical JSON is hashed to `tax_policy_sha256`.

The proposed defaults above are stylized: ordinary near a high federal bracket,
long-term near the 20% bracket, collectibles at the statutory 28% cap. They are
declared assumptions for the record, not advice. GLD is a grantor trust whose
long-term gains are taxed as collectibles; DBC is a commodity pool whose
Section 1256 treatment (60/40, marked to market yearly) is not modelled and is
treated as standard — this overstates DBC's deferral benefit slightly, and DBC
is one sleeve of eight. Foreign-equity distributions (EFA, EEM) are treated as
fully qualified, which is generous. The account holder verifies all of this
before spec 2 fixes it in a charter.

### 4.8 Outputs

`TaxResult`, serialized as JSON:

- `policy`: the policy as applied, plus `tax_policy_sha256`,
  `distributions_sha256`, `lot_method`.
- `by_year`: for each calendar year, income by class, cash interest, realized
  short-term and long-term gains (gross gains and losses), carried loss used
  and remaining, tax paid.
- `totals`: taxes paid, liquidation tax, `reinvested_income_total`,
  `wash_sale_candidates`, unrealized gain at period end, open lot count.
- `wealth`: `pre_tax_terminal`, `after_tax_pre_liquidation`,
  `after_tax_post_liquidation`.
- `metrics`: `after_tax_cagr` (post-liquidation, from initial cash over the
  period), `tax_drag_bps` (pre-tax CAGR minus after-tax CAGR, ×10⁴),
  `effective_tax_rate` (total tax / pre-tax profit, when profit is positive).
- `fifo`: the same `wealth` and `metrics` under first-in-first-out, for
  comparison.

Drawdown is not recomputed. It remains the pre-tax figure from the equity
curve: tax is owed on realized gains and does not change the path you live
through.

## 5. Fixed-exposure benchmark

A new optional `[benchmark]` table with one key:

```toml
[benchmark]
exposure = 0.60
```

When present, the gating benchmark for the strategy's profile (§6) is
`ScaledAllocation(symbols, lookback, sleeve_weight, exposure)` — the class that
already produces the exposure-matched diagnostic — named
`Fixed-Exposure Benchmark (60%)`. The number is fixed in the charter and the
config; nothing about the strategy's realized exposure feeds it. `exposure`
must be finite and in `(0, 1]`, and it enters `strategy_spec_sha256` — but only
when the table is present, so every existing BA-001 spec hash is unchanged.

Without the table, behaviour is exactly today's: full static equal-weight is
the benchmark. BA-001's configs therefore still describe BA-001.

In reporting, the full static allocation, the ex-post exposure-matched
allocation and cash remain as secondary rows whenever a fixed-exposure
benchmark gates, so a reader can see all three comparisons.

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
  compared against. The sweep's `_pair` becomes "run one variant spec".
- `extras` carries what criteria may need beyond the variant metrics: the tax
  results (§4) and the fixed-exposure benchmark's metrics.
- `PROFILES = {"BA-001": BA001Profile()}`; spec 2 adds `"BA-002"`. Loading a
  config whose `strategy.id` has no profile is an error.
- `classify` in the CLI looks up the profile from the sweeps' `strategy_id`
  and keeps its existing checks that the two sweeps share a spec hash and code
  revision.

BA-001's profile must be behaviour-identical. The two existing sweeps'
`criteria.json` files are copied into `tests/fixtures/` and a test replays
their `variants` through `BA001Profile.evaluate_period`, asserting identical
criterion names, pass flags and detail strings, and that `classify` on the pair
returns `inconclusive`.

## 7. Sweep wiring, artifacts, CLI

- When `[tax]` is present, `run_sweep` applies the overlay to the base
  strategy, the gating benchmark, the full static benchmark, the
  exposure-matched benchmark and cash, and stores the results. Every variant's
  strategy also gets an overlay, because a stability check on after-tax return
  will need them in spec 2.
- `write_sweep_report` writes `tax.json` (write-once, like everything else) and
  adds an "After tax" block to `summary.md`: a table of pre-tax CAGR, after-tax
  CAGR post-liquidation, tax drag, taxes paid, liquidation tax and wash-sale
  candidates for the strategy and each benchmark, followed by a one-line
  statement of the lot method and rates used.
- `manifest.json` gains `tax_policy_sha256` and `distributions_sha256` when tax
  is configured; `artifact_schema` becomes 6. Schema 5 artifacts remain
  readable by `classify`.
- New CLI command:

  ```bash
  boring-alpha aftertax experiments/BA-001/sweeps/<id> --policy configs/tax_policy.toml \
      --distributions data/current/distributions_daily.csv
  ```

  It reconstructs each variant's `BacktestResult` from the archived trades and
  equity CSVs and the archived `input_prices.csv.gz` / `input_cash.csv.gz`,
  applies the overlay, and writes `tax-<policy-hash-12>.json` into the sweep
  directory. The name is derived from the policy and distributions hashes, so
  re-running is idempotent and nothing existing is touched. This is the path
  for the BA-001 note (§8) and for re-scoring any past sweep under a new policy
  without re-running it.

- The trades CSV already carries everything a lot needs (date, symbol, side,
  quantity, price). The equity CSV carries cash per session. Initial cash is
  read from the configuration text embedded in the sweep manifest. The
  distributions file is truncated at the sweep's `data_end` before use. No
  artifact format changes are needed for reconstruction.

## 8. BA-001 post-hoc note

Once the overlay is trusted (§3.5, §9), run `aftertax` on sweeps
`4b9d1479f811d108` and `f0a36ea722ebefd4` with the stylized policy, and write
`docs/notes/2026-MM-DD-BA-001-after-tax.md`: after-tax CAGR and tax drag for
the strategy, full static and exposure-matched in both periods, under both lot
methods. It is a diagnostic computed after the results were known, and the
note says so in its first line. It is not a review and does not change BA-001's
classification. Its purpose is to calibrate expectations for BA-002 and to
exercise the machinery on real trades before anything depends on it.

## 9. Testing plan

Tests are written before the code they exercise, in the project's existing
style (unittest, `tests/test_*.py`, fixtures under `tests/fixtures/`).

Fetcher (`test_fetcher.py`):
- `rows_from_chart` variant that also returns unadjusted close and dividend
  per session from a fixture payload containing dividend events; zero on
  non-ex-dates; incomplete-session rule still applies.
- A payload with a split event causes the fetch to refuse to write.

Distributions reader (`test_distributions.py`):
- Exact column set enforced; a missing session-symbol pair relative to the
  price file is an error; negative or non-finite dividend is an error.

Lots (`test_tax_lots.py`):
- HIFO and FIFO on a hand-computed sequence of buys and partial sells; the
  closed quantities, gains and `reinvested` splits match by hand.
- A sell exceeding open quantity is an error (the engine cannot produce it, so
  it is a corruption signal).

Overlay (`test_tax_overlay.py`):
- Double-taxation guard: one lot bought and held across two ex-dates, then
  sold. Total tax equals income tax on the two distributions plus gains tax on
  the price-only gain; income + gain equals adjusted P&L to 1e-9.
- Holding period: 365 days is short-term, 366 is long-term.
- Netting and carryforward: a loss year followed by a gain year pays tax only
  on the excess.
- Collectibles class routes long-term gains to the collectibles rate.
- Cash interest is taxed yearly and equals the sum of session interest.
- Taxes compound at cash to the period end (a tax paid earlier costs more).
- Liquidation: an open lot at period end produces the same tax as selling it
  on the last session.
- Wash-sale candidates counted on both sides of the 30-day window and not
  counted for gains.
- Determinism: identical inputs produce identical JSON and hashes.

Benchmark (`test_config.py`, `test_signals.py`):
- `[benchmark] exposure = 0.60` produces target weights summing to 0.60; out
  of range or non-finite rejected; the spec hash changes with the value.

Registry (`test_criteria.py`, `test_classify.py`):
- Golden replay of BA-001's two `criteria.json` fixtures (§6).
- Unknown strategy id rejected.

Sweep and CLI (`test_sweep.py`, `test_cli.py`):
- With `[tax]`, a synthetic sweep writes `tax.json` and an after-tax block;
  without it, artifacts are byte-identical to today's apart from
  `artifact_schema`.
- `aftertax` on a synthetic sweep directory reconstructs the runs and writes a
  policy-hashed file; running it twice does not rewrite; the in-sweep
  `tax.json` and the reconstructed result agree to 1e-9.

## 10. Financial judgment calls, and why

The account holder asked for best-practice guidance rather than neutral
options. These are the calls in this spec, what the alternative is, and when
the alternative would be right.

- **Gate on highest-cost-first lots, report first-in-first-out.** Specific
  identification is legal and every major broker supports it; a tax-aware
  investor uses it. FIFO is the right *conservative* bound, and it is the right
  criterion only if the account would in practice be run on broker defaults.
- **Gate on post-liquidation wealth, report pre-liquidation.** This is the
  standard way fund after-tax returns are presented, precisely because
  deferral is a real benefit that must be priced when a buy-and-hold benchmark
  is compared with a trading strategy. Pre-liquidation is the right figure only
  for an investor who will never sell — for instance if the estate would
  receive a stepped-up basis — and that is a personal fact, not a strategy
  property.
- **Tax cash interest.** A cash-heavy rule that ignores tax on interest
  understates its own cost. Treasury bill interest is federally taxable.
- **Charge taxes the cash rate.** Paying tax from outside the account is a
  modelling convenience; charging cash rather than the portfolio return is the
  smaller and conservative error for the strategy that pays more tax.
- **Stylized rates in the record, real rates locally.** A charter must be
  reproducible by someone who is not you. Your actual bracket, state and
  filing status are inputs to your decision, not to the strategy's.
- **Drawdown stays pre-tax.** Realized-loss harvesting during drawdowns is a
  genuine offset, but modelling it rewards the strategy for losing money
  cleverly. Left out on purpose.
- **What I am not certain of.** GLD's collectibles treatment and DBC's Section
  1256 treatment are my understanding of the rules, not verified advice; the
  qualified fraction of EFA/EEM distributions is well below 100% in practice;
  and the chart endpoint's dividend convention is unverified until §3.5 is
  done. Each is a declared assumption to be checked, and the spec is written so
  that changing any of them is a policy change, not a code change.

## 11. Open items before implementation is complete

1. Fetch a v2 snapshot and perform the §3.5 hand check on SPY 2019.
2. Confirm the eight symbols report no splits.
3. Account holder confirms or amends the stylized rates and classes in §4.7.
4. Decide the location of the post-hoc note (`docs/notes/` proposed).

## 12. Implementation order

1. Fetcher v2 and the distributions reader, with tests. Fetch a snapshot.
2. `boring_alpha/tax/`: policy, lots, overlay, with tests.
3. `[benchmark]` configuration and the fixed-exposure policy, with tests.
4. Criteria registry refactor with the BA-001 golden test.
5. Sweep wiring, `tax.json`, summary block, schema 6, `aftertax` CLI.
6. BA-001 post-hoc note.

Each step leaves the test suite green and the existing behaviour intact. The
implementation plan will break these into tasks.
