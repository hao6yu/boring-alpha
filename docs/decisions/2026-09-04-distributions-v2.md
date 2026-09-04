# Distributions snapshot v2: hand checks

Date: 2026-09-04
Snapshot: `data/snapshots/20260904T192633Z`, methodology `yahoo-adjusted-v2+dgs3mo-v1`
Resolves: spec §3.5 of `docs/superpowers/specs/2026-09-04-after-tax-evaluation-design.md`
Status: **open**

## What was checked

The chart endpoint's dividend amounts are in the same split-adjusted units
as its `close`. The tax overlay depends on that. Two symbol-years were
compared by hand against the issuer's published distribution schedule.

### EEM 2008 (3:1 split on 2008-07-24)

| Ex-date (archived) | Archived amount | Issuer amount per share | Issuer source | Relationship |
|---|---:|---:|---|---|
| 2008-06-25 | 0.517333 | 0.517255 | iShares MSCI Emerging Markets ETF (EEM) fund-data download, "Distributions" sheet, fetched 2026-09-04 from `https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=239637&component=fundDownload&userType=individual` (the download link on `https://www.ishares.com/us/products/239637/ishares-msci-emerging-markets-etf`) | equal — not the hypothesized one third; see note below |
| 2008-12-23 | 0.340000 | 0.340423 | Same document as above | equal, post-split |

**Note on the June 2008 row.** The archived amount is equal to the issuer's
currently published figure to the cent, not a third of it, so the "one
third, pre-split" relationship anticipated in the task brief does not hold
against this source. Before accepting "equal" as confirmation, I checked
whether iShares' own currently published historical series for EEM has
itself been retroactively restated to today's (post-2008-split) share
count, which would make this comparison uninformative for the specific
pre-split arithmetic being tested. It has: the same document's "Historical"
sheet shows NAV of 43.75 on 2008-07-23 and 42.91 on 2008-07-24 (the split's
effective date) — a smooth series with no threefold discontinuity — and
shares outstanding of 507,600,000 on 2008-07-23 versus 510,750,000 on
2008-07-24, not a roughly threefold jump. A real, un-adjusted 3:1 split
would show both. So iShares' own currently published distribution and NAV
history for EEM is presented in current-share terms throughout 2008,
including before the split, and cannot supply "the issuer's pre-split
per-share figure" the brief asked for.

I looked for a contemporaneous (2008–2009), non-restated source for the
original June 2008 per-share amount and could not obtain one:

- The Wayback Machine holds a snapshot of iShares' 2008-era distribution
  history page for EEM from 2009-01-07
  (`https://web.archive.org/web/20090107181725/http://www.ishares.com/product_info/fund/distributions/EEM.htm`),
  but its distribution table was rendered as a Flash/SWF object; the
  archived HTML carries no extractable numeric table (the Wayback replay
  needs a Flash emulator, which does not run in this environment), so I did
  not obtain a figure from it and did not cite it as a data source.
- SEC EDGAR: I checked both registrants that file iShares' shareholder
  reports — iShares Trust (CIK 0001100663) and iShares, Inc. (CIK
  0000930667) — for every N-CSR/N-CSRS they filed with a period in 2008.
  None of iShares, Inc.'s 2008 filings (periods 2008-02-29 and 2008-08-31)
  contain EEM's own financial statements; EEM is only cross-referenced
  there in a fee-schedule clause for a different fund. None of iShares
  Trust's 2008 filings cover the "MSCI Emerging Markets" fund group either
  (they cover FTSE/Xinhua, ACWI, EAFE, Kokusai, bond, sector, and European
  MSCI country funds instead). I was not able to identify which filing, if
  any, carries EEM's own fiscal-2008 financial highlights within the time
  available.

I did not estimate a figure and did not infer one from the archived data
itself. This cell is reported as **not sourced** for the purpose of testing
the one-third relationship; the 0.517255 figure above is real and cited,
but — for the reason just given — does not settle whether the
split-adjustment is applied correctly to the pre-split period.

### SPY 2019 (no splits)

| Ex-date (archived) | Archived amount | Issuer amount per share | Issuer source | Relationship |
|---|---:|---:|---|---|
| 2019-03-15 | 1.233000 | 1.233119 | State Street SPDR historical distributions file, fetched 2026-09-04 from `https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx` (linked from `https://www.ssga.com/us/en/individual/resources/documents/etf-dividend-distributions`) | equal |
| 2019-06-21 | 1.432000 | 1.431640 | Same document as above | equal |
| 2019-09-20 | 1.384000 | 1.383619 | Same document as above | equal |
| 2019-12-20 | 1.570000 | 1.569992 | Same document as above | equal |

## Conclusion

The December 2008 EEM row (post-split) and all four SPY 2019 rows match the
issuer's published amounts to the cent, which is consistent with the
split-adjusted-units assumption for those dates. The June 2008 EEM row
(pre-split) does not confirm the anticipated one-third relationship: the
only issuer figure I could obtain for it comes from iShares' currently
published data, which I found — by checking that same data's own NAV and
shares-outstanding history around 2008-07-24 — to already be restated to
today's post-split share count, so it cannot test whether the archived
value is correctly a third of what was actually paid per pre-split share in
June 2008. I was unable to find a contemporaneous, non-restated source for
that figure within the sourcing rules (a Wayback Machine capture of the
period's distribution page is Flash-rendered and not extractable; the
relevant SEC N-CSR/N-CSRS filings for both iShares registrants in 2008 do
not appear to carry EEM's own fund-specific financial statements).

This leaves the pre-split half of the split-adjusted-units assumption open.
The overlay's outputs may not be cited until this is closed — either by
locating a genuine pre-split per-share figure for EEM's June 2008
distribution, or by an equivalent hand check on a different pre-split
symbol-date where such a figure can be sourced.

## Consequences for existing configurations

BA-001's configurations declare `yahoo-adjusted-v1+dgs3mo-v1`. The loader
checks a run's declared methodology against the snapshot at `data/current`,
so they now refuse to run against it. That is by design: BA-001's runs are
archived under their own identity, and a rerun against a v2 snapshot would
be a different run. The v1 snapshot directory is kept.
