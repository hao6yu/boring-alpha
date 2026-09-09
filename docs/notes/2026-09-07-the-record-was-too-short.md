# The record was too short, and the published number was the friendliest of four readings

Measured 2026-09-07, round 66. Tool: [`shelter_long_record.py`](../../tools/shelter_long_record.py) (new). Tests: 20 in
[`test_shelter_long_record.py`](../../tests/test_shelter_long_record.py).

Round 64 priced the shelters on 2006-onward because that is where `rotation_edge.panel` is forced to begin — DBC's
listing date, the shortest of ten sleeves. **That is a constraint of a neighbouring tool, not of the question.** A
two-asset shelter plan needs SPY, the shelter and the bill curve, and IEF and TLT have been quoted since 2002-07-30. So
this round builds its own engine and asks the same question on a record that begins in 2002, includes 2008, and offers
**169** ten-year windows where round 64 had 127.

The engine is a third independent path to the flagship number: handed round 58's own weights over round 58's own window,
it returns **$593.13** — that round's published figure, to the cent.

## Then the number moved, and it was not the arithmetic

`--pin` reads the same rule on the same window four ways:

| how "monthly MA200" is read | safe $/mo |
|---|---:|
| **as published (round 58)** — `frequency_cost`'s month-end signal days, first allowed at index 200, so in cash until 2007-02-28 | **593.13** |
| this file's month-end marks, forced to cash for the panel's first 200 days | 527.08 |
| this file's month-end marks, average warmed from 1993 | 527.08 |
| this file's month-start marks, average warmed from 1993 | 489.62 |
| this file's month-start marks, forced to cash for the first 200 days | 467.07 |

The first row is not the second one with a hole punched in it, and the difference between them is the finding. Round 58's
series sits in cash from the panel's first day until **2007-02-28** — thirteen months, because `WARMUP` gates every
frequency and `signal_days` takes the first month-end at or after index 200 — whereas the forced-cells above are in cash
for two hundred days and then follow a warmed signal. Same engine, same window, same costs, same rule: a **$60.01/mo
span, 13% of the lowest**, and the cell that has been quoted since round 58 is the **highest** of them. The driver is the
warm-up hole, which is not a market judgement at all but a side-effect of where the panel starts: under the published
reading **the rule sits in cash by fiat for thirteen months** and then enters. A rule handed an entry point rather than
earning one is being given money, and the amount is bigger than any shelter gain this repository has measured ($50 to
$224 in rounds 64-65). Reading the trend from the first day it can on a panel that starts in 2006 supports $489.62 to
$527.08.

## The shelters, re-measured on the longer record, under both readings of monthly

| shelter | record | windows | month-start safe | vs cash | month-end safe | vs cash | held CAGR (start / end) | held maxDD | capacity (start / end) |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| cash (bills) | 2002-08-01 | 169 | 494.11 | — | 530.91 | — | — | 0.0% | $700 / $750 |
| **IEF** | 2002-08-01 | 169 | **567.22** | **+$73.12** | **581.64** | **+$50.73** | 2.89% / 7.05% | 15.4% / 13.5% | $775 / $850 |
| TLT | 2002-08-01 | 169 | 503.24 | **+$9.13** | 609.42 | +$78.52 | **−0.58%** / 8.55% | **41.4%** / 29.0% | $700 / $900 |
| GLD | 2004-11-18 | 142 | 640.07 | +$145.97 | 714.53 | +$183.62 | 6.42% / 10.84% | 29.4% | $825 / $800 |

**TLT's promotion is withdrawn.** Round 64 paid it +$90.20 a month; on the longer record and the conservative reading of
"monthly" it earns **+$9.13**, below round 60's $25 materiality bar, while losing 0.58% a year *while the rule holds it*
and drawing down 41.4%. Its case survives only under one convention, which is not a case. The reason is visible in the
held column: the long bond's whole panel-era reputation rests on 2008-and-later rallies measured through a signal that
was in the market for a smaller share of the good episodes once 2003's bond selloff and 2013's taper are included.

**IEF survives everything**: positive under both conventions (+$73.12, +$50.73), on both records (+$64.03 on the panel,
+$73.12 on the long record), at every fee in the grid, with the smallest held drawdown in the table and a capacity that
rises under both readings. It is the only shelter whose gain does not depend on a choice of reading. GLD remains the
biggest number and the same second bet, now measured on 142 windows rather than 127.

The duty cycle is **19.6%** of days out of equities on this record (20.4% under month-end), where round 64 quoted 25%
from the panel. Both are true of their own samples, which is why the number now travels with the sample name.

## Checks

20 tests, 6.4 s, offline. The engine reproduces round 58's $593.13 to the cent when handed its weights, and the four-way
reading is pinned from the other direction — including the two structural facts the finding rests on, that forcing the
warm-up hole in *lowers* the month-start cell and that it changes nothing under month-end. The synthetic engine tests
check full-equity against the index (bar the cost of entering it), the bill curve against itself, one switch against one
charge of 2 bps, and that an equity fee never lands on a bond day. `month_signal` is pinned to read the trend on a
month's **last** trading day by crashing a synthetic series only on that day and watching the mark follow. The
`month_marks` trap — handing it the sliced date list shifts every month-end back a trading day — is pinned as a
behaviour so nobody walks into it a fourth time. The sample boundary is asserted (2002-08-01, 288 months, 169 windows)
as is the finding itself: IEF above the bar under both conventions, TLT below it under one. Full suite **1831 passed**
(collected first: 1811 + 20). `journalctl verify`: chain intact, comparator `100% SPY, fee 0.000945`, $0.00 paid in.
