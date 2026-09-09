# The venue that will not look up its own fee

Round 110, and the first round under the new goal (`goal-91eb485f…`): a Coinbase-executable model, because that is where the account is. Step 1
of that goal is "make the cost stack a dated, sourced input", and the round turned into finding out whether that is even possible from inside
this environment. It is not — completely — and the honest artefact is the refusal.

## What was tried, in this order, on 2026-09-08

| path | result |
| --- | --- |
| `help.coinbase.com/…/exchange-fees` via urllib | `403 Forbidden` |
| same, with a Chrome user-agent and `Accept-Language` | `403 Forbidden` — it is a JS challenge, not a UA filter |
| same URL through the harness's own fetcher | `403`, body reads `Just a moment…` |
| `coinbase.com/advanced-fees`, `/fees`, `/legal/trading-rules/exchange` | `403 Forbidden` |
| Wayback copy of `/advanced-fees` (snapshot `20260506154253`) | 200 OK, 12,367 bytes, **0** occurrences of `taker`, `maker`, or any `d.dd%` — it archived the client-side shell, not the rendered table |
| `api.exchange.coinbase.com/fees` | not attempted: needs an account key, and this lab holds no credentials and asks for none |

What *is* machine-readable at Coinbase, with no key: the **order book** and the **retail quote line**. So the cost stack got split by how each
part is known, which is what `tools/venue_fees.py` prints:

```
    measured at 2026-09-08T15:42:38Z (public, no key)
      BTC-USD  bid    78,665.17  ask    78,665.91  touch   0.094 bps
      ETH-USD  bid     2,494.91  ask     2,494.92  touch   0.040 bps
      BTC-USD  retail buy quote    78,653.10  marked up -1.58 bps over the book mid

  no Coinbase fee record: this lab cannot price a trade, and it will not guess.
```

Two useful things fall out of the measured part. Spread is **not** the obstacle: the BTC-USD touch is a fraction of a basis point, so a
monthly crypto strategy is killed by the fee or nothing, and anyone quoting "crypto spreads" as the reason a backtest failed is quoting the
wrong line. And the retail quote line is **noise, not a fee**: sampled twice within minutes it read +6.1 bps and then −1.6 bps over the book
mid, sign and all, so it is printed as a noise floor with that caveat in the docstring rather than being used as a cost.

## The refusal is the artefact

`venue_fees.py` holds **no fee number of its own** — no constant, no fallback, nothing to degrade to. The fee arrives by
`ingest --product … --taker-bps … --as-of …`, is hashed if a text copy is supplied, and is refused after 90 days: a run priced on a tier
nobody looked at for a quarter is asserting a number it cannot see, which is precisely the loan-quote mistake the equity book made three
rounds ago. `tests/test_venue_fees.py` (11 tests) pins both sides of the 90-day line, that the refusal names all four blocked URLs and the
ingest command, that a superseded record survives as a file, and that no fee-named constant exists in the source. Two of those tests caught
the tool's own sloppiness: the docstring forbade a `GUESS` constant by naming it, which failed the very rule-style test defending the rule —
a prohibition should not require the forbidden token in the file.

And one test exists purely to remember a bug: the first order-book read came back as a **18,879 bps** spread, because Coinbase's book rows
are `[price, size, number_of_orders]` and I read index 1 as the price. It looked like a finding. It was caught only because a book one cent
wide on a $78,600 asset cannot cost 100 bps — so the test asserts the arithmetic against the obvious, not just against the endpoint.

## What this blocks, and what unblocks it

BA-005 cannot run until there is a fee record, and it will say so rather than price on a hunch. The unblock is one thing only the account
holder can do, and it is better data than a web page would have been — the product's own fee screen, which shows the tier that will actually
be charged:

```
Coinbase app → Advanced Trade → (profile) Fees & tokens, or the fee schedule shown when placing an order
  tools/venue_fees.py ingest --product advanced-trade --taker-bps <what you see> --maker-bps <what you see> \
      --tier "<your volume tier>" --as-of 2026-09-08 --note "seen under Fees in the app"
```

Then `tools/ba005.py` gets built and allowed to answer the pre-registered question. The fee matters here far more than it does in the equity
book, and the arithmetic is simple enough to state before the run: one inversion of the position is a full sell and a full buy, so it costs
**2 × the taker fee of the sleeve** — 1.2 points at 60 bps, 2.4 points at 120 bps. The number of inversions a monthly 200-day rule actually
makes on BTC is unknown until BA-005 runs, and if it is anywhere near the six or so a year that rule makes on equities, the fee alone is
between 7 and 14 points of the sleeve a year, against an index that charges nothing to hold. The equity book pays about 3 bps a side for the
same decision. That is why this round spent itself on the cost input rather than on a backtest that would have had to be thrown away.

## Checks

**2382 passed, 239 subtests** (2371 + 11 new; collected count printed before the run). Rules: **110**. Goal
`goal-91eb485f-350c-41ec-984d-2f9590cb1449` active, step 1 delivered as a refusal plus an ingest path; steps 2-5 gated on the fee record.
Forward loop untouched: first real seal 2026-09-30, 23 entries to a skill claim.

*Round 110. The venue is chosen, its spread is measured, its fee is the one input this repository cannot fetch — and the model now refuses to
pretend otherwise.*
