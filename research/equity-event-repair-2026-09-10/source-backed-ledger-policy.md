# Inactive-security ledger policy, repair v2

The controls **pass for the declared data/ledger policy below**. ATVI becomes a merger receivable locked against reinvestment. SIVB remains an unpriced holding during the halt; after the documented OTC transition, its available daily closes may serve as explicitly labeled valuation proxies. This does not certify actual liquidation, a complete daily NAV history, or strategy profitability.

This is a rule and evidence repair under policy SHA256 `023eacfa0bf521fe3b1382950371f547ea18f888c5472e997b6650aceaebba05`, before model returns. Detailed facts, source limitations, original-input hashes, and decisions are in [inactive-repair.json](inactive-repair.json). No additional prices, SEC endpoint requests, account access, paid data, or changes to the original inactive audit were made.

| Control | Defensible now | Still unresolved |
|---|---|---|
| ATVI | Exchange cutoff; eligible-share $95 receivable carried separately and locked against spending | Observed broker cash-credit time |
| SIVB/SIVBQ | Halt guard; retained unpriced shares; identity transition; declared post-transition OTC valuation proxy | Current halt-period valuation; liquidation and execution policy |

## ATVI: cancel the shares into a claim, not a simulated trade

Nasdaq identifies October 12, 2023 as the last trading date, with a halt after the 20:00 Eastern after-hours close. The merger closed before the October 13 open; trading remained halted that day, with suspension effective October 16. Consequently, the provider's October 13 daily row is ineligible as a regular Nasdaq execution price regardless of its reported volume. [Nasdaq corporate-action alert](https://nasdaqtrader.com/TraderNews.aspx?id=ECA2023-588).

For eligible ordinary shares, the completed merger cancelled the equity into a right to receive $95 per share without interest. Ownership and the filing's excluded-share categories still matter; unmatched unsettled transactions cannot silently receive an entitlement. [Issuer-hosted completion filing](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b).

The proposed ledger treatment is:

1. On confirmed completion, move the eligible share lot into a merger-claim lot. Preserve units, original basis, and source provenance. Record contractual face amount `95 × entitled units` separately. Do not create a sale fill or use `divCash` as the merger payment.
2. Keep `cash_credit_date = null`; increase spendable cash by zero. The claim earns no cash interest and cannot fund purchases. Leave it locked through the study endpoint if receipt remains unverified.
3. Carry the completed receivable at its contractual face amount as an explicit accounting convention. This is not an observed trade price or customer cash balance. Report settled cash and locked claims separately, and exclude the claim from spending capacity.
4. Transfer the claim to cash only upon separately evidenced receipt and availability; reconcile documented withholding or charges. Reduce the claim as cash is credited to prevent double counting.

This **passes the conservative receivable treatment** without inventing a credit date. The actual customer's cash timing stays unknown, but it is unnecessary for a policy that leaves the proceeds locked. DTCC distinguishes anticipated payment from actual allocation after receipt and verification of funds. IBKR reports distinguish received settlement cash, including corporate-action receipts; neither generic guide supplies ATVI's historical customer credit. [DTCC allocation guidance](https://dtcclearning.com/helpfiles/data/ca_web_ts/Content/Topics/ca_web/coveo_exclude/factor_rate/alloc_status.htm), [IBKR cash-report guide](https://www.ibkrguides.com/reportingreference/reportguide/cash-and-collateral-report.htm).

Do not infer ordinary-share credit from OCC option-exercise settlement or employee stock-award deadlines. The current broker guide's illustrative stock-settlement interval was also not used.

## SIVB: retain the unresolved position through the halt

Nasdaq halted SIVB at 08:35:18 Eastern on March 10, 2023. The existing archive has 12 flat daily rows during March 10–27, four with positive volume. All are excluded as regular Nasdaq execution and mark evidence. Preserve their raw provenance; this classification does not establish that the provider fabricated them. [Nasdaq halt notice](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-halts-svb-financial-group).

An unfilled planned entry is cancelled without a transaction. A position already held retains its quantity and basis; the last supported quote is a separately labeled stale reference. Set its qualified current mark to unavailable during the halt. Do not generate observed zero returns, delete the holding, or credit cash.

On March 28, map SIVB to SIVBQ common shares using CUSIP 78486Q101 and record the OTC venue transition. This changes the identifier, not the economic position. An option-adjustment memo supports the identity link but does not demonstrate a stock fill or the user's broker permissions. [OCC memo 52179](https://infomemo.theocc.com/infomemos?number=52179).

Keep Nasdaq suspension separate from formal delisting: Nasdaq subsequently confirmed March 28 suspension and announced legal removal subject to its Form 25 process. This review does not assert an exact formal delisting date. The earlier halt already rules out a Nasdaq fill. [Nasdaq delisting announcement](https://ir.nasdaq.com/news-releases/news-release-details/delisting-securities-pingtan-marine-enterprise-ltd-srax-inc-svb).

The existing post-transition archive contains 45 structurally valid, positive-volume daily bars through May 31. Its provider metadata identifies SVB Financial Group; the historical common-share identity and transition date come from OCC. Under this declared convention, use an available post-March 28 raw OTC close to value the retained shares. Label it **vendor OTC close valuation proxy**, not a trade fill or guaranteed liquidation value. The original audit's hashes and aggregate checks support this data convention; current PINK metadata is not applied backward.

The proposed listed-stock universe makes no new OTC entry. Marking an existing holding does not sell it or release cash. A fixed horizon ending on a qualified OTC observation may report a marked holding under the proxy, separately from cash. A horizon ending during the halt or after available coverage retains an unpriced holding and an unresolved requested outcome. No eventual bankruptcy payment or cancellation is needed merely to report a marked holding within this window.

These controls **pass for this explicit marked-or-unpriced ledger policy**. Future modeling must still distinguish three requested outputs:

- A marked-holding endpoint after OTC trading resumes can use the stated close proxy, without claiming a sale.
- Complete daily NAV and drawdown through the halt remain unavailable unless a separately declared stale-mark or other valuation convention is explicitly labeled. Unpriced days cannot be silently removed.
- A 20-session liquidation rule needs a frozen delayed-exit, OTC eligibility, and execution/cost policy before returns are calculated. It need not guarantee every historical customer fill, but valuation bars cannot silently become executed orders.

A separately labeled zero-available-value stress case may accompany those outputs; it is not observed recovery. The treatment pass is narrower than the combined source/price gate and does not assert that a trading model cannot be tested. No further daily-price queries or ultimate-bankruptcy research are needed for this bounded control policy.
