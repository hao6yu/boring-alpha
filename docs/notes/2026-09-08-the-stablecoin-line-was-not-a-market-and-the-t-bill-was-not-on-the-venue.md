# The stablecoin line was not a market, and the T-bill was not on the venue

Goal round 5 (of 96), `goal-91eb485f…`. Step 1 has one clause I had not yet discharged — "the stablecoin/fiat conversion line" — and the fee
record it also demands is still sitting with the operator. So this round went after the clause that *is* answerable from here. It turned out to
be answerable in the negative, which is a result, and the negative then knocked over an assumption the two specs were leaning on.

## What the venue actually answers, keyless, on 2026-09-08

| probe | answer |
| --- | --- |
| `/products/USDC-USD/book?level=2` | `404 Not Found` |
| `/products` (837 listings) | `USDC-USD` **not listed**; `BTC-USDC`, `ETH-USDC` listed but `status: delisted, trading_disabled: true`; online USDC-quoted books: `AUDD-USDC, EURC-USDC, TGBP-USDC, USDT-USDC, XSGD-USDC` |
| `/v2/prices/USDC-USD/buy` | `{"data":{"amount":"1"}}` — exact parity, because both legs are dollars |

So there is no conversion *spread* to measure and archive: the conversion is not a market, it is an internal move between two representations
of the same currency, and the one place it is quoted says 1.0. `tools/venue_fees.py` prints that as **unpriced**, never as free — "free" would
be a claim about a fee that may be charged inside the app, behind the same wall that hides the schedule — and a test asserts no conversion,
peg, or USDC constant exists in the source, because a line with no market is precisely where a plausible number would sneak in.

Two things fall out that matter more than the parity itself:

- **The stablecoin route to the trade is not executable.** `BTC-USDC` is delisted, so on this venue the coin is held as `BTC-USD` and the cash
  leg of any plan is USD. Any later design that parks the cash in a stablecoin and crosses a USDC book would be writing an order the venue
  rejects.
- **The question that decides the cash leg is a yield, not a fee.** Both specs credit the below-the-line months with a T-bill return, and a
  T-bill lives at a broker, not on Coinbase. What idle USD earns *there* is a product fact I cannot fetch — so instead of assuming it either
  way, `tools/ba006.py` now prices the cash leg both ways and prints the answer next to the verdict:

| weight | bill, T-bill cash | bill, zero-yield cash | the yield was worth |
| --- | --- | --- | --- |
| 5% | $919/mo | $915/mo | $4/mo |
| 10% | $980/mo | $971/mo | $8/mo |
| 20% | $1,045/mo | $1,028/mo | $16/mo |

**The unsourced assumption is not load-bearing.** At most 2.0% of P0's affordable bill turns on which cash the account holds, and the 20% row
still clears with a cash leg earning nothing. That does not rescue the result — the start-date ladder did that work, and the sleeve still beats
the seatbelt by only +$17/mo — but it closes the objection that a Coinbase-only account cannot hold the bills the backtest pays itself. Say it
plainly, since it is the round's actual finding: *the executability gap is real, and it is worth $16 a month, against a result that only exists
from one start date.*

## Two ways this round went wrong, both now pinned

- **A shadowed constant.** My first cut named the product-list URL `PRODUCTS` — a name this file already used for the tuple of product *lines*
  an ingest may name. The symptom was `ValueError: unknown url type: "('advanced-trade', 'exchange', 'consumer'…`, which is what shadowing
  looks like from outside. Fixed by renaming to `PRODUCT_LIST` with a comment saying the file had that name first.
- **A stale binding.** The cash-leg block reused the variable `costed`, which the fee grid just above it rebinds on every rung, so its
  "T-bill" column printed the **240 bps** bills — 894/935/963, entirely plausible-looking, and wrong. It was caught only because I wrote a
  test that compares the two places which must agree
  (`test_the_cash_column_in_the_variants_block_is_the_same_number_as_the_main_table`). A shared name across sections of a report is not a
  shared value; the grid rebinds it, so the block now names its own.

## Where the objective stands after five rounds

Step 1 is as complete as it can be without a human: prices archived and hashed, spread measured, the conversion line answered as unpriced, and
one input outstanding — the fee tier, which only the account holder can read. Steps 2 and 3 are done and published: BA-005 fails, on
fee-independent grounds. Step 4 is done: the failure is archived, the venue bar is written, and BA-006 — the one form that bar permits — clears
at 20% at a fee of zero, on one start date, with a signal that does not beat simply holding the same slice. Step 5 verified read-only this
round: 13-command plan, every book correctly `not due`, ledger chains intact, three of four stopping conditions still `not decidable`.

Nothing is complete while the evidence is historical, and it is still only historical: first real seal 2026-09-30, 23 entries to a skill claim.

## Checks

**2428 passed, 239 subtests** (2420 + 8 new; collected count printed before the run). Rules: **115**. Files: `tools/venue_fees.py` (probes
the product list and the parity quote, prints the line as unpriced), `tools/ba006.py` (both cash legs priced, one `gates()` everywhere),
`tests/test_venue_fees.py` (11→14), `tests/test_ba006.py` (20→25), `docs/data/coinbase-spot.md` (the probe answers and the cash table).

*Goal round 5. The conversion line the objective asked for turned out not to exist as a market; the assumption it exposed turned out to be worth
$16 a month; and the Coinbase answer keeps converging on the sentence the equity archive already wrote.*
