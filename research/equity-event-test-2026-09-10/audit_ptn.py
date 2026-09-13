"""Offline PTN sample audit; no network, prices outside three dates, or returns.

Canonical auction replacement is deliberately separate from correction replay.
An ambiguous or deleted auction is unresolved, never silently imputed.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATES = ("2022-08-30", "2022-08-31", "2023-06-16")
NY = ZoneInfo("America/New_York")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def event_key(row):
    hd = row["hd"]
    return (int(hd["publisher_id"]), int(hd["instrument_id"]), int(hd["ts_event"]))


def ns(day, clock):
    return int(dt.datetime.fromisoformat(day + "T" + clock).replace(tzinfo=NY).timestamp()) * 10**9


def canonical_day(trades, statistics, day, close="16:00:00"):
    """Return sample proxy and evidence; refuses ambiguous auction revisions.

    Callers must apply their own frozen as-of cutoff before invoking this helper.
    This sample audit consumes the archived UTC day and makes no timing claim.
    """
    start, end = ns(day, "09:30:00"), ns(day, close)
    relevant = [s for s in statistics if int(s["stat_type"]) in (1, 11, 16)]
    assert all(int(s["update_action"]) == 1 for s in relevant), "auction delete/update requires explicit resolution"
    assert len({(event_key(s), int(s["stat_type"])) for s in relevant}) == len(relevant), "ambiguous auction revisions"
    opening = [s for s in relevant if int(s["stat_type"]) == 1]
    closing = [s for s in relevant if int(s["stat_type"]) == 11]
    assert len(opening) == len(closing) == 1, "missing/conflicting opening or closing auction"
    selected = [s for s in relevant if int(s["stat_type"]) in (1, 11) or start <= event_key(s)[2] < end]
    groups, replacements = [], []
    for stat in selected:
        key = event_key(stat)
        same = [t for t in trades if event_key(t) == key]
        assert all(int(t["price"]) == int(stat["price"]) for t in same), "same-event different-price collision"
        bulk = [t for t in same if int(t["sequence"]) == int(stat["sequence"]) and int(t["size"]) == int(stat["quantity"])]
        assert len(bulk) == 1, "official auction lacks unique corresponding normalized bulk trade"
        assert int(stat["price"]) > 0 and int(stat["quantity"]) > 0
        groups.append({"stat_type": int(stat["stat_type"]), "event_ns": key[2], "sequence": int(stat["sequence"]),
                       "price": int(stat["price"]) / 1e9, "canonical_shares": int(stat["quantity"]),
                       "same_event_trade_rows": len(same), "same_event_reported_shares": sum(int(t["size"]) for t in same),
                       "additional_fill_shares_removed": sum(int(t["size"]) for t in same) - int(stat["quantity"]),
                       "close_publication_offset_seconds": (key[2] - end) / 1e9 if int(stat["stat_type"]) == 11 else None})
        replacements.append({"key": key, "price": int(stat["price"]), "size": int(stat["quantity"])})
    removed = {r["key"] for r in replacements}
    points = [{"key": event_key(t), "price": int(t["price"]), "size": int(t["size"])} for t in trades
              if start <= event_key(t)[2] < end and event_key(t) not in removed] + replacements
    assert points
    return {"date": day, "source_trade_rows": len(trades), "auction_groups": groups,
            "proxy": {"open": int(opening[0]["price"]) / 1e9, "high": max(r["price"] for r in points) / 1e9,
                      "low": min(r["price"] for r in points) / 1e9, "close": int(closing[0]["price"]) / 1e9,
                      "volume": sum(r["size"] for r in points)},
            "exact_duplicate_records": len(trades) - len({json.dumps(t, sort_keys=True) for t in trades}),
            "source_stat_rows": len(statistics)}


def main():
    manifest_path = HERE / "ptn-download-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    groups, files = {}, []
    for entry in manifest["downloads"]:
        params = entry["params"]
        day = params["start"]
        if day not in DATES or params["end"] != (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat():
            continue
        assert params["dataset"] == "XASE.PILLAR" and params["symbols"] == "PTN"
        content = (ROOT / entry["path"]).read_bytes()
        assert sha(content) == entry["sha256"] and len(content) == entry["bytes"]
        rows = [json.loads(line) for line in content.splitlines() if line]
        assert len(rows) == entry["rows"]
        assert params["schema"] not in groups.setdefault(day, {}), "duplicate sample query"
        groups[day][params["schema"]] = rows
        files.append({k: entry[k] for k in ("path", "sha256", "bytes", "rows")})
    assert len(files) == 9
    days, identities = [], []
    for day in DATES:
        group = groups[day]
        assert set(group) == {"definition", "statistics", "trades"}
        assert len(group["definition"]) == 1
        definition = group["definition"][0]
        assert definition["raw_symbol"] == "PTN" and definition["exchange"] == "XASE"
        ident = {k: definition[k] for k in ("raw_symbol", "exchange", "instrument_class", "security_type")}
        ident.update(date=day, instrument_id=int(definition["hd"]["instrument_id"]), publisher_id=int(definition["hd"]["publisher_id"]))
        identities.append(ident)
        for kind in ("trades", "statistics"):
            for row in group[kind]:
                assert int(row["hd"]["instrument_id"]) == ident["instrument_id"]
                assert int(row["hd"]["publisher_id"]) == ident["publisher_id"]
                assert int(row["price"]) > 0 and int(row["price"]) < 2**63-1
                if kind == "trades":
                    assert row["action"] == "T" and 0 < int(row["size"]) < 2**32
        result = canonical_day(group["trades"], group["statistics"], day)
        assert result["exact_duplicate_records"] == 0
        days.append(result)
    assert days[2]["proxy"]["close"] == 2.19
    assert days[0]["proxy"]["close"] < 1 < days[1]["proxy"]["open"]
    output = {"status": "SAMPLE_PASSES_DECLARED_PRIMARY_VENUE_PROXY_CHECKS", "full_download_recommended": True,
              "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "manifest_path": str(manifest_path.relative_to(ROOT)),
              "manifest_sha256": sha(manifest_bytes), "script_sha256": sha(Path(__file__).read_bytes()), "files": files,
              "identities": identities, "days": days,
              "anchor": {"date": "2023-06-16", "issuer_reference_close": 2.19, "sample_close": days[2]["proxy"]["close"],
                         "source": "research/equity-event-repair-2026-09-10/ptn-evidence.json"},
              "split_check": "Unadjusted sub-dollar pre-split close and post-1:25 split dollar prices are consistent with issuer Aug31 adjusted-trading date; no exact overnight ratio is required or inferred.",
              "aggregation": "Replace all matching publisher/instrument/event-timestamp auction trades with one official statistics price/quantity. Core ordinary prints use09:30<=ts_event<scheduled close; official closing auction is separately included even when publication is later. Sample days are full sessions. No entire16:00minute inclusion.",
              "limitations": ["NYSE American primary-venue proxy, not consolidated volume/extrema or actual execution prices.",
                              "Native non-printable individual auction fills coexist with bulk trades; the sample-specific duplication is removed. Future same-timestamp price conflicts must remain unresolved.",
                              "Vendor handling of later trade cancellations remains a disclosed aggregation limitation, not a new audit gate; the sample contains no statistics deletes or revisions.",
                              "No inference about absence of dividends or complete336-session/four-window coverage. Full history and in-window actions still need checks.",
                              "This is a whole-archived-day sample audit, not a causal strategy ledger; eventual revision cutoff is separately frozen before returns."],
              "no_network_by_auditor": True, "no_strategy_returns": True}
    path = HERE / "ptn-sample-audit.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes()), "full_download_recommended": True,
                      "days": [{"date": d["date"], "proxy": d["proxy"]} for d in days]}))


if __name__ == "__main__":
    main()
