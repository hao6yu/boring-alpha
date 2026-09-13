"""Two fixed inactive-security windows; aggregate availability only, never returns.

Default is offline. --fetch permits at most the two absent fixed windows, subject
to the shared audit's five-attempt ceiling and policy deadline. No automatic retry.
--fetch-extension permits the separately approved July 25 ATVI boundary check.
Licensed rows remain under git-ignored data/snapshots. Errors never expose bodies.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from tools.tiingo_seen_reference import NoRedirect, read_key
from tools.check_ba002_seen_prices import tls_context

RAW = ROOT / "data/snapshots/equity-event-pilot-2026-09-10"
META = ROOT / "data/snapshots/equity-event-metadata-2026-09-10"
MANIFEST = HERE / "inactive-manifest.json"
WINDOWS = {"ATVI": ("2023-08-01", "2023-11-15"),
           "SIVBQ": ("2023-02-01", "2023-05-31")}
ATVI_EXTENSION = ("2023-07-25", "2023-11-15")
FIELDS = ("open", "high", "low", "close", "volume", "adjOpen", "adjHigh",
          "adjLow", "adjClose", "adjVolume", "divCash", "splitFactor")
SOURCES = [
    {"url": "https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b",
     "fact": "Issuer-hosted October 13, 2023 8-K: completed acquisition, ordinary shares converted to a $95 cash entitlement subject to stated exclusions; pre-open trading halt requested. This establishes entitlement, not brokerage cash-availability date."},
    {"url": "https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-halts-svb-financial-group",
     "fact": "Nasdaq halted SIVB and SIVBP on March 10, 2023 at 08:35:18 Eastern; halt continued pending requested information."},
    {"url": "https://infomemo.theocc.com/infomemos?number=52179",
     "fact": "OCC memo 52179: underlying SIVB becomes SIVBQ March 28, 2023 on OTC market; common-share CUSIP 78486Q101. Memo does not establish fills or ultimate recovery."},
    {"url": "https://www.tiingo.com/documentation/end-of-day",
     "fact": "Tiingo documents raw and adjusted prices, with CRSP-methodology split and dividend adjustments; divCash dates represent ex-dates. Numeric schema validity alone does not verify these adjustments."},
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("w") as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def audit(symbol, raw, window=None):
    # Interpret dates before any price field. No out-of-scope numeric inspection.
    values = json.loads(raw, parse_float=str, parse_int=str)
    if not isinstance(values, list):
        raise ValueError("unexpected response shape; body suppressed")
    start, end = WINDOWS[symbol] if window is None else window
    if (start, end) != WINDOWS[symbol] and not (symbol == "ATVI" and (start, end) == ATVI_EXTENSION):
        raise ValueError("unapproved window")
    rows = {}
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str):
            raise ValueError("invalid date schema")
        day = date.fromisoformat(item["date"][:10]).isoformat()
        if not start <= day <= end:
            raise ValueError("out-of-window response refused before numeric inspection")
        if day in rows:
            raise ValueError("duplicate date")
        row = {field: Decimal(str(item[field])) for field in FIELDS}
        if not all(v.is_finite() for v in row.values()):
            raise ValueError("nonfinite numeric field")
        for keys in [("open", "high", "low", "close"),
                     ("adjOpen", "adjHigh", "adjLow", "adjClose")]:
            opening, high, low, close = (row[k] for k in keys)
            if not 0 < low <= min(opening, close) <= max(opening, close) <= high:
                raise ValueError("invalid OHLC")
        if any(row[x] < 0 for x in ("volume", "adjVolume", "divCash")) or row["splitFactor"] <= 0:
            raise ValueError("invalid volume or action")
        rows[day] = row
    if list(rows) != sorted(rows):
        raise ValueError("unordered dates")
    segments = (("before_acquisition", start, "2023-10-12"),
                ("acquisition_date", "2023-10-13", "2023-10-13"),
                ("after_acquisition", "2023-10-14", end)) if symbol == "ATVI" else (
                ("before_halt", start, "2023-03-09"),
                ("halt_before_otc", "2023-03-10", "2023-03-27"),
                ("otc_period", "2023-03-28", end))
    summary = []
    for label, a, b in segments:
        selected = {d: r for d, r in rows.items() if a <= d <= b}
        summary.append({"segment": label, "start": a, "end": b, "rows": len(selected),
                        "first_date": min(selected, default=None), "last_date": max(selected, default=None),
                        "zero_volume_rows": sum(r["volume"] == 0 for r in selected.values()),
                        "positive_volume_rows": sum(r["volume"] > 0 for r in selected.values()),
                        "nonzero_divCash_rows": sum(r["divCash"] != 0 for r in selected.values()),
                        "nonunit_splitFactor_rows": sum(r["splitFactor"] != 1 for r in selected.values())})
    terminal = rows.get("2023-10-13") if symbol == "ATVI" else None
    observed = {"symbol": symbol, "requested_start": start, "requested_end": end,
                "rows": len(rows), "first_date": min(rows, default=None), "last_date": max(rows, default=None),
                "field_validation": "PASS" if rows else "EMPTY", "segments": summary,
                "raw_adjusted_OHLC_differ_rows": sum(any(r[a] != r[b] for a,b in
                    zip(("open","high","low","close"),("adjOpen","adjHigh","adjLow","adjClose"))) for r in rows.values()),
                "investment_returns_calculated": False, "terminal_return_imputed": False}
    if symbol == "ATVI":
        dividend_checks = []
        ordered_days = list(rows)
        for index, day in enumerate(ordered_days):
            current = rows[day]
            if current["divCash"] <= 0:
                continue
            prior_day = ordered_days[index - 1] if index else None
            prior = rows[prior_day] if prior_day else None
            before = None if prior is None else prior["adjClose"] / prior["close"]
            after = current["adjClose"] / current["close"]
            dividend_checks.append({"declared_dividend_exdate": day, "preceding_available_date": prior_day,
                "pre_adjustment_factor": None if before is None else str(before), "post_adjustment_factor": str(after),
                "factor_changed": None if before is None else before != after,
                "concurrent_split_declared": current["splitFactor"] != 1})
        observed["declared_dividend_adjustment_checks"] = dividend_checks
        unexplained = sum(x["factor_changed"] is False and not x["concurrent_split_declared"] for x in dividend_checks)
        observed["declared_dividends_without_adjustment_factor_change"] = unexplained
        observed["declared_dividends_without_pre_action_row"] = sum(x["preceding_available_date"] is None for x in dividend_checks)
        observed["corporate_action_gate"] = "NOT_PASSED_DECLARED_DIVIDEND_ADJUSTMENT_UNEXPLAINED" if unexplained else "NOT_FULLY_VALIDATED"
        observed["acquisition_row_present"] = terminal is not None
        observed["acquisition_row_close_equals_public_cash_entitlement"] = None if terminal is None else terminal["close"] == 95
        observed["terminal_cash_dividend_field_equals_public_cash_entitlement"] = None if terminal is None else terminal["divCash"] == 95
        observed["acquisition_row_repeats_prior_OHLC"] = None if terminal is None or "2023-10-12" not in rows else all(
            terminal[f] == rows["2023-10-12"][f] for f in ("open", "high", "low", "close"))
        observed["control_verdict"] = "UNRESOLVED_TERMINAL_CASH_AVAILABILITY_AND_EXECUTION_STATUS"
        observed["defensible_treatment"] = [
            "The issuer-hosted completion filing supports the ordinary-share $95 cash entitlement and acquisition date, subject to its exclusions.",
            "Do not treat the acquisition-date daily OHLC or positive volume as proof of an executable regular Nasdaq session; administrative, off-exchange or other provenance is not resolved here.",
            "The terminal OHLC and divCash fields do not encode the verified merger cash entitlement. No terminal return is inferred from their labels or filled by assumption.",
            "A future ledger needs a separately documented cash-entitlement event and a defensible cash-credit availability date or explicit unresolved credit delay; neither automatic same-day cash nor reinvestment is justified by these rows.",
            "Check the before/after adjustment factors at each declared dividend. A boundary action lacking a preceding row cannot establish either correct adjustment or a missing adjustment. Identical raw and adjusted prices after the last action can be normal. The field-validation PASS only checks numeric shape; it does not pass the corporate-action gate.",
        ]
        observed["cash_entitlement_supported_by_official_source"] = True
        observed["cash_credit_date_resolved"] = False
    else:
        halted = [r for d,r in rows.items() if "2023-03-10" <= d <= "2023-03-27"]
        observed["halt_rows_with_flat_OHLC"] = sum(len({r[f] for f in ("open", "high", "low", "close")}) == 1 for r in halted)
        observed["control_verdict"] = "UNRESOLVED_HALT_VALUATION_AND_EXECUTABILITY"
        observed["defensible_treatment"] = [
            "OCC memo 52179 supports the historical SIVB to SIVBQ common-security ticker link and March 28 OTC transition; current PINK metadata is not a historical exchange classification.",
            "Rows during Nasdaq's halt are not evidence of regular Nasdaq execution. Positive volume could reflect other venue, administrative or reporting provenance; this audit does not establish that the provider is wrong.",
            "Apply the official halt state before price-window completeness: no assumed fill during the halt, no gap compression and no zero-return substitution. A retained holding's executable exit and valuation remain unresolved without an explicit supported treatment.",
            "This bounded window covers the halt and OTC transition only; it does not establish ultimate liquidation recovery or a terminal cash payment.",
        ]
    metadata_path = META / (symbol + ".json")
    metadata = json.loads(metadata_path.read_text())
    observed["existing_metadata"] = {k: metadata.get(k) for k in ("ticker", "exchangeCode", "startDate", "endDate")}
    observed["metadata_sha256"] = sha(metadata_path)
    return observed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--fetch-extension", action="store_true")
    args = parser.parse_args()
    policy = json.loads((HERE / "policy.json").read_text())
    policy_hash = sha(HERE / "policy.json")
    ledger = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {
        "schema": "inactive-price-request-audit-v1", "policy_sha256": policy_hash,
        "requests": [], "paid_data_usd": 0, "max_attempts": 5}
    if ledger["policy_sha256"] != policy_hash or len(ledger["requests"]) > 5:
        raise ValueError("ledger does not match current policy or limit")
    key = None
    results = []
    extensions = []
    queries = [(symbol, *window, False) for symbol, window in WINDOWS.items()]
    if args.fetch_extension or (RAW / "ATVI.inactive-extension-prices.json").exists():
        queries.append(("ATVI", *ATVI_EXTENSION, True))
    for symbol, start, end, is_extension in queries:
        path = RAW / (symbol + (".inactive-extension-prices.json" if is_extension else ".inactive-prices.json"))
        output_results = extensions if is_extension else results
        url = f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?startDate={start}&endDate={end}&resampleFreq=daily&format=json"
        ignored = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT).returncode == 0
        if not ignored:
            raise ValueError("raw destination is not git-ignored")
        previous = [r for r in ledger["requests"] if r["symbol"] == symbol and r["status"] == "COMPLETE" and r["url"] == url]
        if path.exists():
            if len(previous) != 1 or sha(path) != previous[0]["sha256"]:
                raise ValueError("raw file lacks a matching completed hash")
        elif (args.fetch and not is_extension) or (args.fetch_extension and is_extension):
            if any(r.get("http_status") == 429 for r in ledger["requests"]):
                output_results.append({"symbol": symbol, "status": "QUOTA_STOP_429"})
                continue
            deadline = datetime.fromisoformat(policy["deadline_utc"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= deadline or len(ledger["requests"]) >= 5:
                output_results.append({"symbol": symbol, "status": "DEADLINE_OR_REQUEST_LIMIT"})
                continue
            if key is None:
                key = read_key(ROOT / ".env")
            attempt = {"symbol": symbol, "url": url, "started_at": datetime.now(timezone.utc).isoformat(), "status": "ATTEMPTING"}
            if is_extension:
                attempt["scope"] = "Explicitly approved third request: extend ATVI to July 25 solely to check adjustment across first-row August 1 dividend; original packet retained."
            ledger["requests"].append(attempt)
            save(MANIFEST, ledger)
            try:
                opener = build_opener(HTTPSHandler(context=tls_context()), NoRedirect())
                request = Request(url, headers={"Authorization": f"Token {key}", "Accept": "application/json", "User-Agent": "BoringAlpha bounded inactive-security audit"})
                with opener.open(request, timeout=min(20, policy["request_timeout_seconds"])) as response:
                    attempt["http_status"] = response.status
                    if response.status != 200 or response.geturl() != url:
                        raise ValueError("unexpected response")
                    raw = response.read(5_000_001)
                if len(raw) > 5_000_000 or key.encode() in raw:
                    raise ValueError("oversize or reflection refused")
                audit(symbol, raw, (start, end))
                RAW.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    output.write(raw)
                    output.flush()
                    os.fsync(output.fileno())
                attempt.update(status="COMPLETE", sha256=sha(path), bytes=len(raw), file=str(path.relative_to(ROOT)))
            except HTTPError as error:
                attempt.update(status="HTTP_ERROR", http_status=error.code)
                # Deliberately do not read, serialize or print the response body.
            except Exception:
                attempt.update(status="FAILED", error="request or validation failed; details suppressed")
            attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
            save(MANIFEST, ledger)
        if path.exists():
            output_results.append(audit(symbol, path.read_bytes(), (start, end)))
        else:
            output_results.append({"symbol": symbol, "status": "DATA_NOT_ACQUIRED"})
    report = {"schema": "inactive-price-availability-audit-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "policy_sha256": policy_hash, "script_sha256": sha(Path(__file__)), "manifest_sha256": sha(MANIFEST) if MANIFEST.exists() else None,
              "request_attempts": len(ledger["requests"]), "paid_data_usd": 0, "results": results,
              "bounded_extensions": extensions,
              "inactive_controls_gate": "UNRESOLVED_NOT_PASSED",
              "primary_sources": SOURCES, "raw_rows_published": False, "investment_returns_calculated": False,
              "limitations": ["Price-row existence does not prove executable trading during a halt.",
                              "Adjusted daily OHLC and divCash do not alone establish delisting consideration or cash-availability timing.",
                              "An OTC ticker-history series must be joined by historical security identity; current PINK metadata cannot label every historical date.",
                              "No missing price, halt fill or terminal return is imputed; this is availability analysis only."]}
    save(HERE / "inactive-results.json", report)
    print(json.dumps({"request_attempts": report["request_attempts"], "results": results, "bounded_extensions": extensions}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Inactive audit stopped; exception details suppressed.", file=sys.stderr)
        raise SystemExit(1) from None
