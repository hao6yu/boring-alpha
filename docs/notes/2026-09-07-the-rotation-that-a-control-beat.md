# The rotation that a control beat

Measured 2026-09-07, round 75. New tool: [`rotation_search.py`](../../tools/rotation_search.py). Engine: `multi_asset_path`
in [`shelter_long_record.py`](../../tools/shelter_long_record.py). Tests: 19 in
[`test_rotation_search.py`](../../tests/test_rotation_search.py).

Round 74 said the recent window cannot be beaten by a shelter, because on that window the fund never failed and every dollar
of withdrawal capacity has to come from return. So this round changed the constraint instead of the average length: stay in
risk the whole time and move it between equity regimes. Seven pre-registered rows on one shared calendar — the intersection
of every symbol's prices, starting 2005-09-06 after a shared 200-day warmup — every rule and both comparators scored over
identical dates, and three of the seven rows are controls.

| rule | Δ vs plain SPY, long | Δ vs plain SPY, recent | Δ vs plain QQQ, long | Δ vs plain QQQ, recent | recent, month-end | switches |
|---|---:|---:|---:|---:|---:|---:|
| spy_only (control) | +0.00 | −0.00 | −281.39 | −350.12 | −0.00 | 0 |
| **qqq_only** (control) | **+281.39** | **+350.12** | 0.00 | 0.00 | +350.12 | 0 |
| **blend_sq** (control, 50/50, never touched) | **+154.18** | **+182.64** | −127.21 | −167.47 | +182.64 | 0 |
| dm12_sq (best of SPY/QQQ, 12m; IEF if both down) | **+406.28** | **+88.29** | +124.89 | −261.83 | +187.21 | 30 |
| dm6_sq | +31.88 | −59.05 | −249.51 | −409.17 | −128.46 | 44 |
| dm12_wide (SPY/QQQ/EFA/GLD) | +245.96 | +82.97 | −35.43 | −267.14 | **−243.91** | 47 |
| dm12_ief (ETVM, Treasuries scored) | −46.65 | −241.84 | −328.04 | −591.95 | −507.56 | 51 |

## The first pass in this repository's history, and what it is worth

`dm12_sq` clears round 60's $25 bar against plain SPY on **both** windows (+$406.28 long, +$88.29 recent) and stays positive
at month-end on both. No rule in rounds 61, 73 or 74 did that. It is also beaten, on the window that matters, by a row that
involves **no decision at all**: the static half-SPY-half-QQQ blend earns $94.35/mo more there, and plain QQQ earns $261.83
more. So the honest sentence is not "a rotation beats the index" — it is **"a growth tilt beats the S&P fund on withdrawal
capacity on both windows, and a trend overlay on top of the tilt costs you most of the tilt in the recent decade while
still buying you the crash protection on the long one."** On the long record that protection is worth $252/mo over the blend
(+406.28 vs +154.18) and $125/mo over plain QQQ: the rule earns its keep where there are crashes and pays for it where there
are none, which is the same sentence round 73 wrote about the shelter, arriving from the other side.

The pass rule as pre-registered did **not** require beating a control — it only required beating plain SPY — and the first
row through the door exposed that gap. The verdict column now carries the control comparison, and the docstring says out
right that this clause was added after the grid ran rather than pretending it was there from the start. The pre-registered
outcome is still printed beside it: `CLEARS the bar vs plain SPY, but the static 50/50 control beats it on the recent window
by $94.35/mo: the tilt does the work, not the rule`. A pass rule that cannot be embarrassed by a control is not one.

Widening the universe made things worse, and not because of the fees. EFA and GLD carry no posted expense ratio in the
archive and are charged the forward book's flat 35 bps, which *flatters* both (`dm12_wide` would be worse at their real
~29 and ~40 bps), and it still loses $267/mo against plain QQQ on the recent window. Scoring Treasuries as a competitor
(`dm12_ief`, the textbook ETVM) is the worst row on the page: −$241.84 recent, −$46.65 long, 51 switches. More choices,
more switches, less money.

One row should stop anyone quoting this table selectively: **`dm12_wide` is +$82.97 on the recent window at month-start
readings and −$243.91 at month-end**, a $327 swing from a choice of calendar day, and it is the only row whose sign flips.
The controls are identical in both columns, as any holding must be — a test asserts exactly that, because a control that
moves with the reading day means the pricing is broken.

## The bug the tests found, which is the reason to write tests after a result too

`weights_for` — the function turning monthly marks into daily weights — read **the current month's** mark as soon as the
month's second session arrived. For month-start readings that is harmless (the reading is that month's first day, so it was
knowable); for month-end readings it meant trading on a decision taken at the previous close, two days earlier — lookahead,
in the one column the pass rule checks. It is `sl.carry`'s job to expand a monthly mark into a daily series by holding the
*previous* month's decision, and the first draft had hand-rolled a second copy of the most dangerous line in the repository
beside the original. It now delegates, so the divergence cannot come back.

The numbers moved when it was fixed, and moved the wrong way for the story: `dm12_sq`'s recent premium fell from +$134.52 to
+$88.29, and `dm12_wide`'s from −$386.60 to +$82.97 (with its month-end twin collapsing to −$243.91). Had the bug made the
result *better* and gone unnoticed, this note would be recommending a strategy that cannot be traded.

## The engine change, and how it was held to account

Rotations need more than two legs, so `multi_asset_path` is now the general case of `two_asset_path`. Turnover is charged as
**the sum of positive weight changes** — one charge per purchase, which is what the original's single `abs(Δw)` already is,
since the sell half of a switch only raises the cash that pays for the buy. That convention, not a new one: rounds 61 to 74
are written in the original's numbers, and a generalisation that quietly re-based the cost model would invalidate all of them
while still looking self-contained.

The differential test runs the published MA200/IEF record through both engines: they agree to 1e-15 over 5,000 sessions and
dozens of switches. The one place they *can* differ is documented and constructed rather than waited for — a record that
opens sheltered is exactly one switch charge apart, because the original never charges for buying the shelter; on this
archive the record opens fully invested, so the difference never fires.

## What the objective has now, and has not

**Has:** a construction that beats plain DCA on the recent window on the repository's own measure, net of costs, at both
readings — `blend_sq`, two funds and no rule, at +$182.64/mo per $100k against plain SPY. It does not beat plain QQQ, which
is the price of not putting everything on one style; whether that price is worth paying is a question about a person's
tolerance, not about this archive.
**Has not:** any evidence that a *decision* adds anything over that. The rule that earns the most across both windows is the
one with the fewest decisions, and the row that finally cleared the pre-registered bar is beaten by a control. The next
hypothesis has to be stated against the control, not against the index: **a growth-tilted blend with a trend brake** — hold
50/50, shelter when both are under their averages — priced as an attempt to keep the blend's +$182.64 and lose less of it in
2008 and 2020 than plain blending does. If that cannot be said in advance to beat the control, the search has its answer and
the forward book should simply hold the tilt.
