# The attention feed: a point-in-time non-price input, captured properly and priced to nothing

Measured 2026-09-06. Tools: [`attention_feed.py`](../../tools/attention_feed.py) (capture) and
[`attention_bar.py`](../../tools/attention_bar.py) (price), tests
[`test_attention_bar.py`](../../tests/test_attention_bar.py). Reproduce with
`.venv/bin/python tools/attention_feed.py fetch && … panel && … verify`, then
`.venv/bin/python tools/attention_bar.py [--cost-bps 2]`. Sealed data: `data/attention/`, 84 response blobs,
8.7 MB, re-hash verified.

## Why this round went to a feed instead of another window

Fifteen rounds priced every price-only mechanism this repo could build against plain DCA and found them
redundant; the one survivor (constant leverage) contains no forecast. The goal as written asks for something
that reads trend and news. That input is not in `data/current`, and no further window on twelve ETFs can
supply it. So the question became whether a non-price series could be obtained in a form this repository is
willing to believe, and what it is worth — not whether a fourth framing of momentum might do better.

Two properties decide whether a news proxy is evidence or hindsight: the value for a day must have been
knowable **on** that day, and the series must never be revised. Wikipedia page views have both — which is why
they are the feed, and they are the same series the academic literature uses for financial anxiety
nowcasting. Reader attention, not news content: the cheapest honest approximation to the goal's input that a
retail account can obtain point-in-time, for free, on the day.

## The trap, and the guard for it

`2020_stock_market_crash` begins on 2020-03-09 in this capture because the article was *created* that day. An
event-named article exists only after the event, so its view series carries a rise nobody on the ground could
have seen, and a backtest on it grades the historian. The guard is mechanical and runs at capture, not at
analysis: a board article must return data for the first month of the sample and every month after it
(`completeness()` → `require_full_sample`), and anything that appears mid-sample is rejected by name. Two more
guards were earned on the way in: the API counts a redirect as its own article with a stub's view count (so
titles are resolved through the MediaWiki API first), and attention to *any* topic grows with Wikipedia's own
traffic (so the board carries a control basket of evergreen non-financial articles).

Sample: **2015-07-01 to 2026-09-04**, 4,084 days, the endpoint's own depth limit — which is why this feed does
not contain 2008 and never will. 14 of 14 articles accepted, each with 4,084 days, every blob content-addressed
with SHA-256 and re-hashed by `verify`. Nothing scored until that was sealed.

## The result, at the bar every round since 15 has used

$5,000 opened, $500 a month, SPY's real expense ratio, 2 bps a leg, against DCA into SPY and into VOO, four
windows, three thresholds, both directions, both baskets, 24 cells and none dropped.

| cell | $/mo vs DCA | vs VOO | exposure | turnover | verdict |
|---|---|---|---|---|---|
| financial z≥0.5 panic buys | −$455 | −$464 | 19% | 2.13× | refuted by its control |
| financial z≥0.5 panic exits | −$138 | −$147 | 76% | 2.04× | refuted by its control |
| financial z≥1.0 panic buys | −$379 | −$388 | 10% | 1.78× | refuted |
| financial z≥1.0 panic exits | −$250 | −$260 | 85% | 1.87× | refuted |
| financial z≥1.5 panic buys | −$479 | −$488 | 1% | 0.18× | refuted |
| financial z≥1.5 panic exits | −$87 | −$96 | 93% | 0.27× | refuted |

**No cell clears the pre-registered rule, and all six directions are refuted by the control basket** at the
same threshold on the same windows — the control's largest lead $129/mo, its best cell +$51/mo against the
financial basket's best of +$28/mo, and every one of those six shared-window cells negative, from −$87 to
−$479. The financial z has lag-1 autocorrelation **+0.62**, so 128 scored months
carry about **30** independent bets; the control's is +0.44 (50 bets).

What the feed carries is real but not usable: attention *rises when the market falls*, so "panic exits" is a
noisy restatement of "the market is falling", and everything it earns by sitting out a crash it also pays in
the whipsaw months, at 2× the turnover. Both directions lose, and the most positive sub-window cell in the
whole 24-cell grid (+$28/mo) sits below the noise floor with a worse mirror image. Six articles about the
Moon, photosynthesis,
volcanoes, Everest, humans and water reproduce the same shape — better. That is the finding, and the control
clause is the only reason it is a finding rather than a headline about a news signal that works.

## The bug in this round's own first pass, and why the file now refuses to price it

The first version of the grid showed `panic exits` earning **+$507 a month**. It was true of a different
book: the schedule assigned `1.0` to *every* sleeve, so an "on" month held SPY **and** VOO at full weight —
**2× exposure, priced and labelled as unlevered**. The exposure column read 76% because 2.0 is also greater
than 0.5. Corrected, that cell is −$138/mo and the grid's whole positive side vanishes. Three consequences are
now structural rather than remembered:

- a schedule whose rows sum above 1.0 **raises** instead of being priced (`price()` refuses leverage in a tool
  that has said "unlevered" in its own docstring);
- a held month holds one sleeve, asserted row by row, with the benchmark leg pinned at zero — the comparator
  is never a holding;
- a sit-out is an explicit `{SPY: 0.0, VOO: 0.0}`. It is *not* an empty row, which `run_book` reads as "hold
  what you held" and which would have turned this whole test into buy-and-hold while printing a convincing
  number.

The bug was caught by a test written to check something else — that a sit-out row is a zero and not an
omission. That is the argument for writing the boring test.

## What this does to the goal

Sixteen rounds, and the count of independent non-price inputs that beat DCA net of costs in this repository is
still zero: cross-sectional rotation (full and partial), mean reversion, overnight split, weekly and daily
timing, sector overlays, leveraged timing — and now attention, captured point-in-time, immutable, verified,
and worth −$87 to −$479 a month on the shared window.

The feed is not discarded, because it is the first non-price asset here and the only one with a sealed
provenance: `data/attention/` can be re-fetched and diffed, and `verify` proves the blobs behind any future
claim are the blobs pulled today. What the round actually establishes is a **pipeline** — capture sealed →
rule frozen → grid complete → control basket that can refute the signal — and the pipeline says the news idea
is worth −$138/mo at the shape tested, on the only sample the feed permits.

Two honest doors remain, and both are now describable precisely rather than hopefully: either the input has to
be something other than *aggregate* attention (headline-level text, which no free point-in-time source here
provides), or the trading decision has to stop being a forecast — which is where the levered-index ticket of
round 17 sits, at +$23/mo on a $20,000 account, refusing every desk whose posted rate exceeds 8.72%.

## Checks

`tests/test_attention_bar.py`, 23 tests, 1.7 s, all offline: truncating the history cannot rewrite a past
z-score (tested at three cuts, which is the point-in-time property rather than an assertion of it); no z
exists before its own window does; a month's weights cannot move when a *later* month's signal moves; a
never-trading book pays no fees and finishes below the book that holds the index; a schedule asking for more
than 1.0× is refused with the word "leverage" in the error; a held row sums to exactly 1.0 and holds no VOO;
a mid-sample article is rejected and a full-sample one accepted; the sample start is the endpoint's own limit;
a tampered blob makes the panel refuse to build (tested on copies in a temp dir, never on the sealed record);
the grader can pass, can refuse, runs its control clause first, and cannot let the control basket pass by
construction; and the sealed result is pinned — no cell clears, all six directions refuted, every shared-window cell below
the noise floor. Full suite: **1372 passed, 233 subtests**. `journalctl verify`: chain intact (1 entry),
comparator spec `100% SPY, fee 0.000945` unchanged — the sealed ledger is untouched at one entry and $0.00
paid in.
