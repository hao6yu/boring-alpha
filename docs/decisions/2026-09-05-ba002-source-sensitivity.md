# BA-002 seen-history source sensitivity

Authorized by the holder's September 5 "go" after the Tiingo preflight and
issuer-confirmed missing TLT distribution. Written **before any performance
calculation for this experiment**. This fixes the comparison, not its outcome.

## Inputs and one explicit correction

Preserve original Yahoo snapshot `20260904T192633Z` and the Tiingo reference
`tiingo-seen-20260905-v1`. Build two new, local-only snapshots, each containing
only 2006-02-28–2021-12-31, including the common warmup. Do not change
`data/current`, the original configs, BA-001 artifacts or research freeze.

1. `yahoo-adjusted-v3-tlt-20121101+dgs3mo-v1`: insert the issuer-confirmed TLT
   cash dividend on 2012-11-01. Multiply both existing adjusted open and close
   strictly **before** that date by `1 - dividend / previous_session_raw_close`.
   Leave raw prices, ex-date/later adjusted prices, other symbols and cash
   unchanged. Verify the event and its adjustment step are both absent first.
   This is [Yahoo's documented convention](https://help.yahoo.com/kb/SLN28256.html),
   not literal reinvestment at the ex-date close. Evidence is linked in the
   [preflight](../reviews/BA-002-preflight.md).
2. `tiingo-adjusted-v1-seen-splits+dgs3mo-v1`: use Tiingo's own adjusted OHLC;
   restate raw closes and cash dividends by the product of subsequent observed
   split factors through 2021-12-31. Ex-date quotes exclude their own split
   from that product. Preserve reported split precision and record it. The
   EEM 2008 issuer comparison established the dividend-unit convention.

Both feeds use the exact same bounded DGS3MO cash bytes. This does not verify
cash against another source. Archive input hashes, correction evidence and
conversion code. Do not choose a source according to its strategy returns.

The generated snapshot manifests, checked before performance execution, are:

- `data/snapshots/ba002-yahoo-corrected-seen-20260905-v1/manifest.json`:
  `b60a6fc57858620443ae94603775c85a9407c1b81ddde21d48714f2b50f45c8b`.
- `data/snapshots/ba002-tiingo-seen-20260905-v1/manifest.json`:
  `0db57f4b1fbd5d31239e72ea98116c9e34b8fff1c69e64a4efc9f9654f321d2a`.

Independent row comparison confirms exactly 1,682 pre-ex-date TLT adjusted-price
rows and one distribution row changed in the bounded Yahoo copy. All other
retained row fields are identical. Both copies have identical cash bytes,
3,990 sessions per ETF, and complete calendar coverage in each research window.

## Fixed computation

- Seen A: 2007-06-01–2017-12-31. Seen B: 2018-01-01–2021-12-31.
- Existing BA-002 grid: 9/12/15 base, double cost, and each of the three
  leave-one-horizon-out rows, all with 15-month warmup.
- Existing eight ETFs, 12.5% sleeve limit, $100,000 account, monthly targets,
  next-session execution, 10 bps per side; double-cost row is 20 bps for both
  strategy and benchmark.
- Existing annual 60%-invested benchmark and full eight-scenario tax policy.
  Capital-loss deduction sensitivity stays off. No signal, cost, rate, timing,
  horizon, threshold or window changes between cases.
- Exactly two feeds × two windows × five rows × two paired accounts:
  **40 account backtests and 320 tax-overlay evaluations**.

Require exact independent-calendar coverage, existing quality checks,
account replay reconciliation, eight-scenario completeness and valid tax
identity flags. Preserve every account's decisions/orders, fills and equity,
all tax records, the truncated inputs, and executable-source hashes/bytes.
Publish completion manifests last. A failed check is an incomplete diagnostic,
not permission to relax tolerance or silently repair another vendor price.

## Interpretation and boundaries

This is an explicitly **non-gating source-sensitivity experiment**. Formal
BA-002 contracts only admit the original v2 methodology. Therefore do not
fabricate a run context, relabel a source as v2/synthetic, weaken the contract,
or write formal schema-7 sweep evidence. Reuse the existing profile's grid,
backtester, tax engine and serializers in a distinct diagnostic artifact kind.
The preflight's proposed new freeze is deferred until a formal methodology
choice; this authorized diagnostic does not confirm the old freeze.

Report after-tax post-liquidation CAGR for every scenario, the worst-strategy
minus best-benchmark envelope, and paired cost-net pre-tax drawdowns. Compare
those numbers descriptively with the **unchanged** base 50 bps/year hurdle,
positive stress margins, and 20%/no-worse-than-benchmark drawdown limits.
Those comparisons do not confer formal eligibility or holdout permission.

Show both sources and both periods. Agreement does not establish that either
feed is ground truth. A source-dependent conclusion is unresolved, not a reason
to select the flattering feed. If neither source clears the existing economic
requirements, say so and do not tune another variant within this experiment.

No observations on or after 2022-01-01 are numerically loaded. No historical
market API calls, live trading, purchase, new reveal, formal classification,
commit or push is authorized by this experiment. Raw licensed source extracts
and reconstructable row-level outputs remain Git-ignored and local.
