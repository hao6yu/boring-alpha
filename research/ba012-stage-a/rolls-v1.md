# BA-012 roll map, version 1

Generated independently of acquired prices on September 10, 2026 by
`tools/build_ba012_rolls.py`. The generator reads only the pinned calendar and
checks the frozen protocol checksum. `rolls-v1.json` and
`rolls-calendar-evidence-v1.json` each have a SHA-256 sidecar.

The map covers 2,007 joint reference dates, January 11, 2016 through
December 29, 2023. It contains 32 rolls each for NES, MTN and M6E, 48 for
1OZ, and 40 for MZC. Q1 2024 maturity dates are calendar metadata only, needed
for the contracts selected at the end of 2023. No 2024 price data was read.

## Holiday interpretation resolved for the parent diagnostic

The prior note's gold ambiguity is resolved by direct observations of the
[official gold Calendar](https://www.cmegroup.com/markets/metals/precious/1-ounce-gold.calendar.html):
1OZM27 last trades May 26, 2027, excluding Memorial Day May 31; 1OZZ26 last
trades November 25, 2026, excluding Thanksgiving November 26. These examples
also confirm the prior-month termination and same-date settlement convention
on the actual calendar. The conflicting floating-price paragraph remains
outside this early-exit study.

The [MTN Calendar](https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-10-year-us-treasury-note.calendar.html)
lists November 27, 2026 and February 25, 2027 for December/March last trades.
Those dates match first-position dates on the
[underlying TN Calendar](https://www.cmegroup.com/markets/interest-rates/us-treasury/ultra-10-year-us-treasury-note.calendar.html).
TN June 2027 has first-position May 27, first-notice May 28 and first-delivery
June 1, skipping Memorial Day May 31. Together with Rule 54's two-business-day
formula, these provide a documented basis for applying the normal Treasury
holiday convention to hypothetical MTN deadlines. This interpretation is not
an assertion that prelaunch MTN contracts or their calendars existed.

The generator therefore excludes the reviewed exchange settlement holidays
for month-end expiry counts. The separate 2018 mourning closure is applied to
the backward count of joint observation sessions, rather than treated as a
universal commodity holiday. It is outside the relevant prior-month expiry
calculations. M6E's June 2023 LTD is June 16 under its explicit banking exception.

## Reference interface

Each `rows` element supplies `date_chicago`, `previous_joint_date_chicago` and
an ordered `markets` list: NES, MTN, M6E, 1OZ, MZC.

- `active_parent_raw_symbol`: selected contract after this reference, including
  the new contract on a roll date.
- `interval_parent_raw_symbol`: the preceding date's active contract; use
  this same symbol at both endpoints for the day's difference and return.
- `required_parent_raw_symbols`: both old and new on a roll reference; one
  symbol otherwise. The first date has no preceding interval.

The earliest permitted exit is the fifth joint session strictly before the
exchange deadline. On the exit date, finish the old contract's interval and
seed the new contract's reference. Do not subtract prices across maturities.
Execution timing and positions are not modeled by this manifest.

Symbols are expected CME outright raw symbols, with an explicit full maturity
year/month alongside the single-digit year suffix. The downstream free
symbology check must confirm dated symbol-to-ID mappings. Never accept a
spread merely because it was included in the `.FUT` parent acquisition.

## Scope of the remaining broker limitation

This is an **exchange-deadline parent-exposure diagnostic**. IBKR's public EUR
currency delivery exception does not establish that every M6E account has an
earlier closeout; its Cash/IRA footnote can impose one. Current account/M6E
applicability is unverified, and no earlier date is fabricated. The output
allows a parent integer-risk diagnostic but explicitly disallows treating it
as validated account-specific execution or funded feasibility. Any applicable
earlier known deadline requires a documented map revision before a final
account-specific conclusion.

Missing required price windows must be DATA_INCOMPLETE. Neither an absent bar
nor an unresolved broker condition establishes capital infeasibility.
