# BA-012 settlement data amendment v2

Registered before settlement prices are read. Frozen v1 remains unchanged. This final feasibility attempt ends at **2026-09-10 16:42:18 UTC**. The JSON and SHA-256 sidecar are the controlling amendment.

The only changes are the reference source and gold maturity schedule. Use CME-published settlement statistics, and map each October GC maturity to December of the same full year. Recompute roll continuity and gold deadline metadata after that mapping; publish its hash before reading prices. The calendar, five markets, 252 scheduled intervals, 72 monthly decisions, covariance, 8% risk target, costs, margins, stress limits, integer objective and partial-fill rules remain unchanged. This is sizing participation research only.

Attribute a settlement to the literal UTC date in `ts_ref`, without converting that date to Chicago. Its information cutoff is that date at **16:30 America/Chicago**. Eligible records are settlement `stat_type=3`, `rtype=24`, ADD `update_action=1`, actual (`stat_flags & 2`) and nonintraday (`stat_flags & 8 == 0`). Final bit 1 is recorded, not required. Choose the latest eligible message available by the cutoff; never insert a later final revision retrospectively. Genuine event and receipt timestamps must pass the cutoff. Before May 21, 2017, use the explicitly labelled event-time proxy because genuine capture timestamps do not exist.

The JSON fixes tie handling. Any pre-cutoff settlement DELETE conservatively invalidates the instrument/session; unsupported actions, ambiguous timestamps, conflicting ties, invalid prices and missing old/new roll endpoints remain `DATA_INCOMPLETE`. This avoids inventing undocumented deletion matching. Significant unresolved implementation complexity is a stop reason.

Different products settle at different times. These references are neither simultaneous marks nor executable fills. The study has seen v1 coverage, so this amendment is not an untouched holdout. Missing data cannot establish capital infeasibility. No strategy P&L, funding decision, account-specific execution claim or automatic further variant is authorized by this record.

Sources and exact policies are in the controlling JSON.
