#!/usr/bin/env python3
"""Independent offline audit of the frozen 100-slot earnings data pilot.

Reads public local SEC documents and collector manifests only. No network,
credentials, model fitting, return calculation, or collector-file mutation.
Unproven fiscal comparability and earliest-event selection never become passes.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, timezone, timedelta
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POLICY_SHA = "f6178cb98b4716a8744b79a3bae2b0709f6c4ee056f3a66be0789fc38cb2e188"
CALENDAR = ROOT / "data/calendars/nyse-2006-2026-v1.json"
EASTERN = ZoneInfo("America/New_York")
EARLIER_REJECTION_REVIEWS = {
    "0001104659-22-104870": ("preliminary q3 results", "APRN offering materials incorporate preliminary Q3 results."),
    "0001493152-22-028213": ("updated financial guidance", "SDPI updates expectations/guidance."),
    "0001493152-23-005370": ("preliminary financial results", "SDPI reports preliminary results before the actual earnings release."),
    "0000827187-23-000005": ("preliminary results", "SNBR estimates results and announces the later earnings call."),
    "0001564590-23-005223": ("preliminary metrics", "UMBF discloses selected preliminary metrics; full results are scheduled for April25."),
    "0001650372-22-000071": ("international financial reporting standards", "TEAM accounting-transition presentation; not a new quarterly earnings release."),
    "0001169561-23-000005": ("preliminary", "CVLT preliminary earnings disclosure precedes the actual release."),
}
PRELIMINARY_EVENT_AMBIGUITIES = {
    "0001104659-22-104870": "APRN preliminary ended-quarter revenue range disclosed in the incorporated prospectus.",
    "0001493152-23-005370": "SDPI explicitly disclosed preliminary Q4/FY2022 revenue before the full release.",
    "0000827187-23-000005": "SNBR explicitly disclosed estimated preliminary full-year sales and EPS.",
    "0001169561-23-000005": "CVLT explicitly disclosed preliminary quarterly GAAP and non-GAAP results.",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    if path is None:
        raise ValueError("archived JSON source is missing")
    return json.loads(path.read_text())


def normalized_text(text):
    text = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", text))).strip()


def evidence_text(text):
    """Ignore only HTML/table separators and punctuation-adjacent whitespace."""
    text = normalized_text(text.replace("|", " "))
    return re.sub(r"\s+([,.;:])", r"\1", text).strip()


def evidence_in_source(excerpt, text):
    return bool(excerpt) and evidence_text(excerpt) in evidence_text(text)


def period_scope(kind):
    kind = (kind or "").lower()
    if "quarter" in kind or kind in ("three months", "3 months"):
        return "quarter"
    if "year" in kind or kind in ("twelve months", "12 months"):
        return "year"
    return kind


def local_file(value):
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    candidates = [path] if path.is_absolute() else [ROOT / path, HERE / path, ROOT / "data/snapshots/equity-event-pilot-2026-09-10/sec" / path]
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink() and candidate.resolve().is_relative_to(ROOT):
            return candidate.resolve()
    return None


def source_rows(report):
    if isinstance(report, list):
        return report
    for key in ("sources", "requests", "responses", "records"):
        if isinstance(report.get(key), list):
            return report[key]
        if isinstance(report.get(key), dict):
            return list(report[key].values())
    return []


def master_ranking(raw, seed):
    ciks = set()
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) == 5 and parts[0].strip().isdigit() and parts[2].strip() == "8-K":
            cik = parts[0].strip().zfill(10)
            if not "2023-07-01" <= parts[3].strip() <= "2023-09-30":
                raise ValueError("seed index contains an out-of-quarter original 8-K")
            ciks.add(cik)
    if not ciks:
        raise ValueError("no original 8-K CIKs in archived seed index")
    return sorted(ciks, key=lambda cik: hashlib.sha256((seed + "|" + cik).encode()).hexdigest())


def date_evidence(text, value):
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    patterns = [rf"\b{day.strftime('%B')}\s+0?{day.day}\s*,?\s*{day.year}\b",
                rf"\b{day.strftime('%b')}\.?\s+0?{day.day}\s*,?\s*{day.year}\b",
                rf"\b0?{day.day}\s+{day.strftime('%B')}\s*,?\s*{day.year}\b",
                re.escape(value)]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return text[max(0, match.start() - 100):match.end() + 100]
    return None


def period_labels(text):
    """Candidate period identities from headline/preamble; never date proximity."""
    prefix = text[:2400].lower()
    labels = set()
    names = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4", "1st": "Q1", "2nd": "Q2", "3rd": "Q3", "4th": "Q4"}
    for name, label in names.items():
        if re.search(rf"\b{name}\s+(?:fiscal\s+)?quarter\b", prefix):
            labels.add(label)
    labels.update("Q" + match for match in re.findall(r"\bq([1-4])\b", prefix))
    if re.search(r"\b(?:full[ -]year|year[ -]end|annual (?:financial )?results)\b", prefix):
        labels.add("FY")
    return labels


def iso_time(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("naive acceptance timestamp")
    return stamp


def audit():
    checks, provenance = [], []
    def check(code, ok, details=None, *, missing=False, slot=None):
        checks.append({"check": code, "status": "PASS" if ok else "PENDING" if missing else "FAIL",
                       **({"slot_id": slot} if slot is not None else {}), **({"details": details} if details is not None else {})})
        return bool(ok)
    def load(name):
        path = HERE / name
        if not path.exists():
            check("artifact_available", False, name, missing=True)
            return None
        value = read_json(path)
        provenance.append({"path": str(path.relative_to(ROOT)), "sha256": digest(path)})
        return value
    policy_path = HERE / "policy.json"
    if not check("frozen_policy_sha256", digest(policy_path) == POLICY_SHA):
        return {"status": "FROZEN_POLICY_FAILURE", "checks": checks}
    policy = load("policy.json")
    check("policy_sidecar", (HERE / "policy.json.sha256").read_text().split()[0] == POLICY_SHA)
    check("fixed_policy_denominator", policy["issuer_count"] == 25 and policy["denominator"] == 100 and len(policy["event_windows"]) == 4)
    calendar_raw = read_json(CALENDAR)
    sessions = calendar_raw["sessions"]
    check("calendar_order", sessions == sorted(set(sessions)))
    provenance.append({"path": str(CALENDAR.relative_to(ROOT)), "sha256": digest(CALENDAR)})
    selection, events, sources = load("sec-selection.json"), load("sec-events.json"), load("sec-sources.json")
    joins = load("price-joins.json")
    if not all(x is not None for x in (selection, sources)):
        return finish(checks, provenance)
    for label, artifact in (("selection", selection), ("events", events or sources), ("sources", sources)):
        check("artifact_policy_binding", artifact.get("policy_sha256") == POLICY_SHA, label)
    if joins is not None:
        check("price_join_policy_binding", joins.get("policy_sha256") == POLICY_SHA)
        check("price_join_calendar_binding", joins.get("calendar_sha256") == digest(CALENDAR))
        price_manifest = load("price-manifest.json")
        if price_manifest is not None:
            check("price_join_manifest_binding", joins.get("manifest_sha256") == digest(HERE / "price-manifest.json"))
        if events is not None:
            check("price_join_uses_current_events", joins.get("events_sha256") == digest(HERE / "sec-events.json"),
                  "A stale join cannot certify the latest corrected event cohort.")
    rows = source_rows(sources)
    verified_sources, seed_path, by_url, text_cache = {}, None, {}, {}
    for row in rows:
        path = local_file(row.get("path") or row.get("file"))
        if path is None:
            check("successful_raw_source_available", row.get("status") != 200, row.get("url"))
            continue  # Failed requests need not have bodies.
        declared = row.get("sha256") or row.get("response_sha256") or row.get("raw_sha256")
        actual = digest(path)
        if check("raw_source_hash", declared == actual, str(path.relative_to(ROOT))):
            verified_sources[path] = actual
            by_url[row.get("url")] = path
        if row.get("url") == policy["seed_index_url"]:
            seed_path = path
    check("source_manifest_has_records", bool(rows))

    def source_text(value):
        path = local_file(value)
        if path not in verified_sources:
            return ""
        if path not in text_cache:
            text_cache[path] = normalized_text(path.read_text(errors="replace"))
        return text_cache[path]

    def metadata_frame(cik, start, end):
        """Rebuild original filing candidates from archived provider metadata."""
        url = "https://data.sec.gov/submissions/CIK" + cik + ".json"
        path = by_url.get(url)
        if path is None:
            return [], [url]
        base = read_json(path)
        recent = base["filings"]["recent"]
        tables, missing = [recent], []
        if not recent.get("filingDate") or min(recent["filingDate"]) > start:
            for old in base["filings"].get("files", []):
                if old["filingFrom"] <= end and old["filingTo"] >= start:
                    old_url = "https://data.sec.gov/submissions/" + old["name"]
                    old_path = by_url.get(old_url)
                    if old_path is None:
                        missing.append(old_url)
                    else:
                        tables.append(read_json(old_path))
        output = {}
        for table in tables:
            days = table.get("filingDate", [])
            for i, day in enumerate(days):
                if start <= day <= end:
                    row = {k: v[i] for k, v in table.items() if isinstance(v, list) and len(v) == len(days)}
                    output[row["accessionNumber"]] = row
        return sorted(output.values(), key=lambda r: (r["filingDate"], r.get("acceptanceDateTime", ""), r["accessionNumber"])), missing

    ranked_source = load("sec-ranked-seed.json")
    if check("historical_seed_index_available", seed_path in verified_sources, missing=seed_path is None):
        ranked = master_ranking(seed_path.read_text(errors="replace"), policy["seed"])
        positions = {cik: index + 1 for index, cik in enumerate(ranked)}
        if ranked_source is not None:
            check("entire_historical_rank_reconstructed", [r["cik"] for r in ranked_source["rows"]] == ranked)
            check("rank_file_bound_to_selection", digest(HERE / "sec-ranked-seed.json") == selection.get("ranked_seed_sha256"))
    else:
        positions = {}
    issuers = selection.get("issuers", [])
    ciks = [str(row["cik"]).zfill(10) for row in issuers]
    check("exact_25_unique_issuers", len(ciks) == len(set(ciks)) == 25, {"observed": len(ciks)}, missing=selection.get("selection_status") == "IN_PROGRESS")
    ranks = []
    screened_by_cik = {r["cik"]: r for r in selection.get("screened", [])}
    for issuer, cik in zip(issuers, ciks):
        expected = positions.get(cik)
        check("issuer_seed_rank", expected == issuer.get("seed_rank") and expected is not None, {"cik": cik, "expected": expected, "observed": issuer.get("seed_rank")})
        if expected is not None:
            ranks.append(expected)
        check("seed_filing_in_Q3", "2023-07-01" <= issuer.get("seed_filing_date", "") <= "2023-09-30", cik)
        check("contemporaneous_common_stock_evidence_recorded", bool(issuer.get("common_stock_evidence")), cik)
        screen = screened_by_cik.get(cik, {})
        selected = next((r for r in screen.get("candidates", []) if r.get("accession") == issuer.get("seed_accession")), {})
        primary = source_text(selected.get("primary_file"))
        check("common_stock_evidence_in_archived_cover", bool(primary) and all(evidence_in_source(r.get("row_excerpt"), primary) for r in issuer.get("common_stock_evidence", [])), cik)
        check("selected_seed_original_earnings", selected.get("form") == "8-K" and selected.get("classification") == "EARNINGS_RELEASE"
              and bool(re.search(r"Item\s*2\.02\b", primary, re.I)), cik)
    check("issuer_order_is_rank_order", ranks == sorted(ranks) and len(ranks) == len(ciks))
    correction_path = HERE / "sec-selection-correction.json"
    if correction_path.exists():
        correction = load(correction_path.name)
        old_path = local_file(correction.get("initial_selection_file"))
        okay = check("initial_published_selection_preserved", old_path is not None and digest(old_path) == correction.get("initial_selection_sha256"))
        if okay:
            old = read_json(old_path)
            old_ciks = {r["cik"] for r in old["issuers"]}
            added, removed = set(ciks) - old_ciks, old_ciks - set(ciks)
            check("selection_repair_matches_source_finding", added == {"0001787414"} and removed == {"0001582982"},
                  {"added": sorted(added), "removed": sorted(removed)}, missing=not added and not removed)
    excluded = selection.get("screened_exclusions", [])
    excluded_ciks = [str(row.get("cik", "")).zfill(10) for row in excluded]
    check("no_selected_issuer_excluded", not set(ciks) & set(excluded_ciks))
    check("exclusion_records_unique", len(excluded_ciks) == len(set(excluded_ciks)))
    if ranks:
        required = {cik for cik, rank in positions.items() if rank <= max(ranks)}
        observed = set(ciks) | set(excluded_ciks)
        check("no_silent_rank_skips_or_replacements", required == observed,
              {"unexplained_ciks": sorted(required - observed), "extra_ciks": sorted(observed - required)})
        check("seed_inspection_limit", max(ranks) <= policy["max_seed_issuers_inspected"])
    for row in excluded:
        check("exclusion_reason_recorded", bool(row.get("reason") or row.get("unresolved_reasons")), row.get("cik"))
        cik = str(row.get("cik", "")).zfill(10)
        frame, missing = metadata_frame(cik, "2023-07-01", "2023-09-30")
        expected = {r["accessionNumber"] for r in frame if r.get("form") == "8-K" and "2.02" in r.get("items", "")}
        got = {r.get("accession") for r in row.get("candidates", [])}
        master_row = next((r for r in (ranked_source or {}).get("rows", []) if r["cik"] == cik), {})
        master_accessions = {Path(r["path"]).stem for r in master_row.get("seed_index_filings", [])}
        metadata_accessions = {r["accessionNumber"] for r in frame if r.get("form") == "8-K"}
        check("excluded_seed_original_filings_match_master", bool(master_accessions) and master_accessions == metadata_accessions,
              {"cik": cik, "missing_master_accessions": sorted(master_accessions - metadata_accessions)})
        check("excluded_seed_metadata_coverage", not missing, {"cik": cik, "missing_sources": missing}, missing=bool(missing))
        check("excluded_seed_all_item202_candidates_reviewed", expected == got, {"cik": cik, "unreviewed": sorted(expected - got)})
        check("exclusion_is_resolved", row.get("decision") == "EXCLUDED", {"cik": cik, "decision": row.get("decision")})
    if events is None:
        return finish(checks, provenance)
    slots = events.get("slots", [])
    expected_keys = {(cik, start, end) for cik in ciks for start, end in policy["event_windows"]}
    observed_keys = [(str(row.get("cik", "")).zfill(10), row.get("window_start"), row.get("window_end")) for row in slots]
    check("exact_100_fixed_slots", len(slots) == len(set(observed_keys)) == 100 and set(observed_keys) == expected_keys,
          {"observed": len(slots), "missing_keys": sorted(expected_keys - set(observed_keys))}, missing=events.get("status") == "IN_PROGRESS")
    check("slot_ids_unique", len({row.get("slot_id") for row in slots}) == len(slots))
    join_rows = joins.get("slots", []) if isinstance(joins, dict) else []
    joins_by_slot = {row["slot_id"]: row for row in join_rows}
    selected_accessions, periods, audited_slots = set(), set(), []
    for slot in slots:
        sid = slot.get("slot_id")
        current, prior = slot.get("current"), slot.get("prior")
        report = {"slot_id": sid, "current_present": bool(current), "prior_present": bool(prior)}
        audited_slots.append(report)
        if not current:
            check("current_document_available", False, slot.get("unresolved_reasons"), missing=True, slot=sid)
            check("missing_slot_retains_reason", bool(slot.get("unresolved_reasons")), slot=sid)
            continue
        check("prior_document_available", bool(prior), slot.get("unresolved_reasons") if not prior else None, missing=not prior, slot=sid)
        accession = current.get("accession")
        check("manually_rejected_guidance_not_selected", accession != "0001493152-22-028213",
              "Independent raw-source review: October 12, 2022 SDPI updates expectations/guidance, not actual earnings.", slot=sid)
        check("current_accession_used_once", accession not in selected_accessions and isinstance(accession, str), slot=sid)
        selected_accessions.add(accession)
        check("event_in_fixed_release_window", slot["window_start"] <= (current.get("release_date") or "") <= slot["window_end"], slot=sid)
        text_by_role = {}
        for role, event in (("current", current), ("prior", prior)):
            if not event:
                continue
            for field in ("exhibit_file", "primary_file", "index_file", "metadata_file"):
                path = local_file(event.get(field))
                okay = check("event_source_verified", path in verified_sources, {"role": role, "field": field}, missing=path is None, slot=sid)
                if okay and field == "exhibit_file":
                    text_by_role[role] = normalized_text(path.read_text(errors="replace"))
            evidence = event.get("classification_evidence")
            check("classification_evidence_recorded", bool(evidence), {"role": role}, slot=sid)
            primary = source_text(event.get("primary_file"))
            if role == "current":
                check("original_item202_source_support", event.get("form") == "8-K" and bool(re.search(r"Item\s*2\.02\b", primary, re.I)), {"role": role}, slot=sid)
            else:
                # The frozen prior-document rule does not require Item2.02 or 8-K.
                check("prior_original_filing_source_support", bool(primary) and isinstance(event.get("form"), str)
                      and "/A" not in event["form"] and event.get("classification") == "EARNINGS_RELEASE", slot=sid)
            if role == "current":
                security = event.get("security") or {}
                cover_evidence = security.get("common_stock_evidence") or []
                check("event_historical_symbol_from_cover", security.get("status") == "VERIFIED_SINGLE_COMMON_CLASS"
                      and slot.get("historical_symbol") == security.get("historical_symbol") and bool(cover_evidence)
                      and all(evidence_in_source(r.get("row_excerpt"), primary) for r in cover_evidence),
                      {"historical_symbol": slot.get("historical_symbol"), "cover_symbol": security.get("historical_symbol")}, slot=sid)
            text = text_by_role.get(role, "")
            release_excerpt = date_evidence(text, event.get("release_date")) or date_evidence(primary, event.get("release_date"))
            check("release_date_present_in_source", bool(release_excerpt), {"role": role, "release_date": event.get("release_date"), "excerpt": release_excerpt}, slot=sid)
            excerpt = date_evidence(text, event.get("period_end")) or date_evidence(primary, event.get("period_end"))
            check("claimed_period_date_in_source", bool(excerpt), {"role": role, "period_end": event.get("period_end"), "excerpt": excerpt}, slot=sid)
            pe = event.get("period_evidence") or {}
            check("explicit_period_excerpt_in_source", evidence_in_source(pe.get("excerpt"), text) or evidence_in_source(pe.get("excerpt"), primary),
                  {"role": role, "period_evidence": pe}, slot=sid)
        period_key = (slot.get("cik"), current.get("period_end"))
        check("distinct_current_fiscal_period", period_key not in periods and period_key[1] is not None, slot=sid)
        periods.add(period_key)
        try:
            index = source_text(current.get("index_file"))
            match = re.search(r"Accepted\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})", index)
            if match is None:
                raise ValueError("missing raw index acceptance")
            eastern = datetime.fromisoformat(" ".join(match.groups())).replace(tzinfo=EASTERN)
            check("acceptance_eastern_matches_raw_index", iso_time(current["acceptance_eastern"]) == eastern, slot=sid)
            metadata = read_json(local_file(current["metadata_file"]))
            table = metadata.get("filings", {}).get("recent", metadata)
            mi = table["accessionNumber"].index(accession)
            api = table.get("acceptanceDateTime", [None] * len(table["accessionNumber"]))[mi]
            check("filing_date_matches_raw_metadata", current["filing_date"] == table["filingDate"][mi], slot=sid)
            check("acceptance_utc_matches_raw_metadata", current.get("acceptance_utc") == api, slot=sid)
            utc = iso_time(api) if api else None
            exact = eastern == utc if utc else None
            # Exact timestamp failures remain visible, independent of the daily proxy.
            report["timestamp_reconciliation"] = {"index_eastern": eastern.isoformat(), "api_timestamp": api,
                                                   "exact_status": "PASS" if exact else "FAIL" if utc else "UNAVAILABLE"}
            cutoff = max(current["filing_date"], eastern.astimezone(EASTERN).date().isoformat())
            entry_index = bisect_right(sessions, cutoff)
            expected_entry = sessions[entry_index]
            report["expected_entry_session"] = expected_entry
            api_entry = sessions[bisect_right(sessions, max(current["filing_date"], utc.astimezone(EASTERN).date().isoformat()))] if utc else None
            report["timestamp_reconciliation"].update(index_based_entry=expected_entry, api_as_utc_based_entry=api_entry,
                daily_proxy_invariant=api_entry == expected_entry if utc else None)
            check("daily_timing_proxy_resolved", utc is None or api_entry == expected_entry,
                  report["timestamp_reconciliation"], slot=sid)
            joined = joins_by_slot.get(sid)
            if check("price_join_available", joined is not None, missing=joined is None, slot=sid):
                check("following_session_entry", joined.get("entry_session") == expected_entry, slot=sid)
                expected = sessions[entry_index - 60:entry_index + 21]
                check("price_window_boundaries", len(expected) == 81 and joined.get("price_window_start") == expected[0]
                      and joined.get("price_window_end") == expected[-1] and joined.get("expected_sessions") == 81, slot=sid)
        except (KeyError, TypeError, ValueError, IndexError):
            check("valid_acceptance_and_entry_inputs", False, slot=sid)
        candidates = slot.get("candidate_events", slot.get("candidates"))
        if candidates is None:
            check("earliest_qualifying_event_proven", False, "Candidate/rejection history absent; selected event alone cannot prove earliestness.", missing=True, slot=sid)
        else:
            extended_end = (date.fromisoformat(slot["window_end"]) + timedelta(days=10)).isoformat()
            frame, missing = metadata_frame(str(slot["cik"]).zfill(10), slot["window_start"], extended_end)
            expected_candidates = {r["accessionNumber"] for r in frame if r.get("form") == "8-K" and "2.02" in r.get("items", "")}
            reviewed = {r.get("accession") for r in candidates}
            check("event_candidate_metadata_coverage", not missing, {"missing_sources": missing}, missing=bool(missing), slot=sid)
            check("event_candidate_set_matches_raw_metadata", expected_candidates == reviewed,
                  {"missing_candidates": sorted(expected_candidates - reviewed), "extra_candidates": sorted(reviewed - expected_candidates)}, slot=sid)
            eligible = [item for item in candidates if item.get("classification") == "EARNINGS_RELEASE"
                        and slot["window_start"] <= (item.get("release_date") or "") <= slot["window_end"]]
            eligible.sort(key=lambda item: (item["release_date"], item.get("acceptance_eastern") or "", item.get("accession", "")))
            unresolved = [item.get("accession") for item in candidates if item.get("error") or (item.get("classification") == "EARNINGS_RELEASE" and not item.get("release_date"))]
            earlier_nonqualifying = [item for item in candidates if item.get("classification") != "EARNINGS_RELEASE"
                                     and item.get("filing_date", "9999") <= current["filing_date"]]
            rejection_reviews = []
            for item in earlier_nonqualifying:
                known = EARLIER_REJECTION_REVIEWS.get(item.get("accession"))
                text = source_text(item.get("primary_file")) + " " + " ".join(source_text(e.get("file")) for e in item.get("exhibit_candidates", []))
                verified = known is not None and known[0] in text.lower()
                rejection_reviews.append({"accession": item.get("accession"), "source_supported": verified,
                                          "finding": known[1] if known else "Unreviewed earlier rejection; classifier label alone is insufficient."})
            check("earlier_rejections_independently_source_reviewed", all(r["source_supported"] for r in rejection_reviews), rejection_reviews, slot=sid)
            report["earlier_rejection_reviews"] = rejection_reviews
            ambiguity = [{"accession": item["accession"], "reason": PRELIMINARY_EVENT_AMBIGUITIES[item["accession"]]}
                         for item in earlier_nonqualifying if item.get("accession") in PRELIMINARY_EVENT_AMBIGUITIES]
            report["event_definition_status"] = "UNRESOLVED_EVENT_DEFINITION" if ambiguity else "NO_KNOWN_PRELIMINARY_RESULT_AMBIGUITY"
            report["preliminary_event_ambiguities"] = ambiguity
            check("event_definition_resolved", not ambiguity, {"reason": "UNRESOLVED_EVENT_DEFINITION", "predecessors": ambiguity,
                  "policy_issue": "Frozen policy does not explicitly exclude preliminary earnings; the collector selects the first full release. No retrospective event substitution is made."} if ambiguity else None, slot=sid)
            report["first_public_earnings_information_verified"] = False
            check("earliest_under_collector_full_release_convention", not missing and not unresolved and expected_candidates == reviewed
                  and bool(eligible) and eligible[0].get("accession") == accession,
                  {"unresolved_candidates": unresolved, "qualifying_in_order": [r["accession"] for r in eligible]}, slot=sid)
        if prior:
            def url_cik(event):
                match = re.search(r"/edgar/data/(\d+)/", event.get("primary_url", ""))
                return match[1].zfill(10) if match else None
            check("current_prior_same_registrant_source_paths", url_cik(current) == url_cik(prior) == str(slot["cik"]).zfill(10), slot=sid)
            continuity = slot.get("corporate_continuity")
            if continuity:
                transition_text = source_text(continuity.get("transition_primary_file"))
                check("corporate_continuity_source_evidence", evidence_in_source(continuity.get("transition_excerpt"), transition_text), slot=sid)
                report["accounting_basis_change"] = continuity.get("accounting_basis_change")
            try:
                before, after = date.fromisoformat(prior["period_end"]), date.fromisoformat(current["period_end"])
                # A fiscal Q4 can end Jan1 and the next Dec31 in the same calendar year.
                # The separate comparison below requires matching source period scope.
                check("prior_fiscal_year_relationship", 350 <= (after - before).days <= 378, slot=sid)
                prior_index = source_text(prior.get("index_file"))
                pm = re.search(r"Accepted\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})", prior_index)
                if pm is None:
                    raise ValueError("prior raw acceptance absent")
                prior_eastern = datetime.fromisoformat(" ".join(pm.groups())).replace(tzinfo=EASTERN)
                prior_metadata = read_json(local_file(prior["metadata_file"]))
                pt = prior_metadata.get("filings", {}).get("recent", prior_metadata)
                pi = pt["accessionNumber"].index(prior["accession"])
                check("prior_timing_fields_match_raw_sources", prior["filing_date"] == pt["filingDate"][pi]
                      and iso_time(prior["acceptance_eastern"]) == prior_eastern
                      and prior.get("acceptance_utc") == pt.get("acceptanceDateTime", [None] * len(pt["accessionNumber"]))[pi], slot=sid)
                check("prior_original_form_matches_raw_metadata", prior["form"] == pt["form"][pi] and "/A" not in pt["form"][pi], slot=sid)
                check("prior_document_precedes_current", prior["accession"] != accession and prior["filing_date"] < current["filing_date"]
                      and prior_eastern < iso_time(current["acceptance_eastern"]), slot=sid)
            except (KeyError, TypeError, ValueError):
                check("prior_period_or_timestamp_valid", False, slot=sid)
            left, right = period_labels(text_by_role.get("current", "")), period_labels(text_by_role.get("prior", ""))
            pc, pp = current.get("period_evidence") or {}, prior.get("period_evidence") or {}
            def verified_scopes(role, event):
                output = set()
                primary = source_text(event.get("primary_file"))
                for pe in [event.get("period_evidence") or {}] + event.get("period_candidates", []):
                    if pe.get("period_end") != event.get("period_end"):
                        continue
                    excerpt = pe.get("excerpt", "")
                    if not (evidence_in_source(excerpt, primary) or evidence_in_source(excerpt, text_by_role.get(role, ""))):
                        continue
                    scope = period_scope(pe.get("kind"))
                    if scope in {"quarter", "year"}:
                        output.add(scope)
                    if re.search(r"quarter\s+and\s+(?:(?:full|fiscal)\s+)?year\s+ended|year\s+and\s+quarter\s+ended", excerpt, re.I):
                        output.update(("quarter", "year"))
                return output
            cs, ps = verified_scopes("current", current), verified_scopes("prior", prior)
            common = cs & ps
            sc = sp = "quarter" if "quarter" in common else "year" if "year" in common else None
            check("same_explicit_period_scope", bool(common), {"current_source_scopes": sorted(cs), "prior_source_scopes": sorted(ps), "matched_scope": sc}, slot=sid)
            report["matched_period_scope"] = sc
            try:
                cd, pd = date.fromisoformat(current["period_end"]), date.fromisoformat(prior["period_end"])
                exact_year = cd.year == pd.year + 1 and (cd.month, cd.day) == (pd.month, pd.day)
                def ordinal_support(role, pe):
                    names = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4"}
                    for name, label in names.items():
                        if name + " quarter" in pe.get("kind", ""):
                            return {label}
                    return period_labels(text_by_role.get(role, "")[:1000]) - {"FY"}
                cq, pq = ordinal_support("current", pc), ordinal_support("prior", pp)
                weekly_year = 357 <= (cd - pd).days <= 372 and (sc == sp == "year" or (len(cq) == 1 and cq == pq))
                check("prior_comparable_period_not_date_proximity_only", sc == sp and sc in ("quarter", "year") and (exact_year or weekly_year),
                      {"exact_prior_year_end_date": exact_year, "current_quarter_source_labels": sorted(cq), "prior_quarter_source_labels": sorted(pq), "days_apart": (cd - pd).days}, slot=sid)
            except (KeyError, TypeError, ValueError):
                check("prior_comparable_period_not_date_proximity_only", False, slot=sid)
            report["headline_period_labels"] = {"current": sorted(left), "prior": sorted(right)}
            # Source-backed scopes/dates are not an independent accounting-measure audit.
            report["accounting_measure_definitions_audited"] = False
            report["accounting_review_limitation"] = "Source-backed fiscal period matching does not establish unchanged GAAP/non-GAAP definitions, restatements, or economic comparability."
    result = finish(checks, provenance)
    result["slot_audit"] = audited_slots
    result["fixed_denominator"] = 100
    result["observed_slots"] = len(slots)
    result["observed_current_documents"] = sum(bool(slot.get("current")) for slot in slots)
    result["observed_prior_documents"] = sum(bool(slot.get("prior")) for slot in slots)
    by_slot = {}
    for row in checks:
        if row.get("slot_id") is not None:
            by_slot.setdefault(row["slot_id"], []).append(row)
    required_prior_checks = {"prior_document_available", "current_prior_same_registrant_source_paths", "prior_fiscal_year_relationship", "prior_document_precedes_current", "prior_timing_fields_match_raw_sources", "prior_original_filing_source_support", "prior_original_form_matches_raw_metadata", "same_explicit_period_scope", "prior_comparable_period_not_date_proximity_only"}
    for row in audited_slots:
        own = by_slot.get(row["slot_id"], [])
        row["blocking_failures"] = [{"check": c["check"], "status": c["status"], **({"details": c["details"]} if "details" in c else {})}
                                    for c in own if c["status"] != "PASS"]
        row["daily_proxy_success"] = any(c["check"] == "daily_timing_proxy_resolved" and c["status"] == "PASS" for c in own) and not any(
            c["check"] in {"acceptance_eastern_matches_raw_index", "filing_date_matches_raw_metadata", "acceptance_utc_matches_raw_metadata", "valid_acceptance_and_entry_inputs"}
            and c["status"] != "PASS" for c in own)
        exact = row.get("timestamp_reconciliation", {}).get("exact_status")
        row["exact_timestamp_match"] = True if exact == "PASS" else False if exact == "FAIL" else None
        row["prior_pair_source_support"] = row["prior_present"] and required_prior_checks <= {c["check"] for c in own if c["status"] == "PASS"}
        row["prior_pair_source_support"] = row["prior_pair_source_support"] and not any(c["check"] in {
            "event_source_verified", "claimed_period_date_in_source", "explicit_period_excerpt_in_source", "original_item202_source_support"}
            and c["status"] != "PASS" for c in own)
    result["global_validation_failures"] = [row for row in checks if row.get("slot_id") is None and row["status"] == "FAIL"]
    result["global_pending_inputs"] = [row for row in checks if row.get("slot_id") is None and row["status"] == "PENDING"]
    result["timestamp_counts"] = dict(Counter(r.get("timestamp_reconciliation", {}).get("exact_status", "UNRESOLVED") for r in audited_slots if r["current_present"]))
    result["daily_proxy_invariant_count"] = sum(r.get("timestamp_reconciliation", {}).get("daily_proxy_invariant") is True for r in audited_slots)
    result["corporate_action_review"] = "Price structure/adjustment consistency is not source verification of every actual split/dividend; the separate final join must retain this distinction."
    result["independent_manual_findings"] = [
        {"accession": "0001193125-23-197167", "finding": "BSBK false exclusion: the explicit three-and-six-month net-income release qualifies under the frozen policy.",
         "source": "data/snapshots/equity-event-pilot-2026-09-10/sec/8b3941261de0c53ebb87daf9479c6007a4b5642b47253c7f9af11bb5ca91adb1.htm"},
        {"accession": "0001493152-22-028213", "finding": "SDPI false current-event selection: updated third-quarter expectations/full-year guidance is not actual earnings.",
         "source": "data/snapshots/equity-event-pilot-2026-09-10/sec/f7fce7c3132cf754d822c70ccbb63543d731eacf4d60396f85f8ab4f8e041446.htm"}]
    result["limitations"] = ["Source-text period labels are evidence candidates, not proof of accounting comparability.",
        "Earliest-event evidence requires complete candidate coverage and source-supported rejection decisions.",
        "The first-full-release convention was not explicit about preliminary earnings in the frozen policy; affected slots are blocked for formal admission.",
        "Historical Q3 issuer selection is a data-availability sample and cannot be a performance universe.",
        "This audit computes no investment returns and makes no profitability or native-execution claim."]
    return result


def finish(checks, provenance):
    counts = Counter(row["status"] for row in checks)
    return {"schema": "equity-event-independent-sample-audit-v1", "created_at": datetime.now(timezone.utc).isoformat(),
            "policy_sha256": POLICY_SHA, "audit_script_sha256": digest(Path(__file__)), "status": "AUDIT_ISSUES" if counts["FAIL"] else "WAITING_FOR_INPUTS" if counts["PENDING"] else "AUTOMATED_CHECKS_PASS_MANUAL_REVIEW_REQUIRED",
            "check_counts": dict(counts), "checks": checks, "inputs": provenance,
            "network_requests": 0, "strategy_returns_calculated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "sample-audit.json")
    args = parser.parse_args()
    result = audit()
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"status": result["status"], "check_counts": result.get("check_counts", {}), "output": str(args.output)}))


if __name__ == "__main__":
    main()
