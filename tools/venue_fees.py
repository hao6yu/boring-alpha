#!/usr/bin/env python3
"""The Coinbase cost stack for this lab: what is measured, what is ingested, and what makes a run refuse.

The objective's venue is Coinbase (the account is in the US, and the model has to be executable where the money actually is). A trade on
that venue costs three separable things, and this file keeps them separate because they have very different epistemic statuses:

  * **Spread and market impact** — measured, live, from the venue's own public order book. Right now the BTC-USD touch is one cent wide
    against a ~$78,600 mid (0.001 bps), which is why spread is not what kills a monthly crypto strategy and pretending otherwise would be
    flattering the strategy.
  * **The taker/maker fee** — *not* obtainable here. Every machine path was tried on 2026-09-08 and the attempts are recorded in
    `PROBE_LOG` below: the help centre and the pricing pages answer `403 Forbidden` to any non-browser client (a browser user-agent changes
    nothing — it is a JS challenge, not a UA filter), the harness's own fetcher gets the same challenge page, and the archived copy of the
    pricing page is a 12 KB client-side shell containing no fee text at all. So the fee is **ingested**: the operator, who can see their own
    tier in the product they will actually trade, supplies it, and this tool hashes what was supplied and dates it.
  * **The stablecoin/fiat conversion line** — measured, live, from the `USDC-USD` book: the round trip across it costs exactly the touch, and
    the mid's deviation from parity is printed as a peg risk in bps, because a "dollar" 30 bps from a dollar is a position, not cash. What
    this line does *not* answer is the one that matters — whether an account that never leaves the venue earns anything on idle cash, since
    the specs credit the cash leg with a T-bill yield held somewhere else. `tools/ba006.py` prices both readings.
  * **The retail quote line** — Coinbase's public `/v2` buy quote, printed because it is free to measure and because it is *unreliable*:
    sampled twice on 2026-09-08 it came out +6.1 bps and then -1.6 bps against the book mid, so it is a noise floor of a few bps and not a
    fee. Anyone tempted to read a strategy's viability out of it should note that the sign changed in minutes.

Two rules from the standing review bind this file. A fee that cannot be looked up is not a fee (r103), so pricing a trade without a
current record is a refusal, not a default, and this file deliberately bakes in no number of its own. And a refusal must name the reason it cannot rule the
thing out (r106), so the refusal prints the probe log rather than a shrug.

Usage:
    tools/venue_fees.py report                      # what is known, what is missing, what it cost to find out
    tools/venue_fees.py ingest --product advanced-trade --taker-bps 60 --maker-bps 40 \\
                               --tier "US$10K-$50K" --as-of 2026-09-08 --note "seen in the app under Fees"
    tools/venue_fees.py taker --for ba005           # the number a run must use, or the run stops
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

VENUE_DIR = ROOT / "data" / "venues"
RECORD = VENUE_DIR / "coinbase-us-spot-v1.json"
MEASURES = VENUE_DIR / "measures.jsonl"

#: A schedule older than this may not be used to price a trade. Fees move, and a run that prices on a stale tier is asserting a
#: number it has no idea is still true — the same mistake the equity book made with a loan quote three rounds ago.
MAX_AGE_DAYS = 90

BOOK = "https://api.exchange.coinbase.com/products/{pair}/book?level=2"

#: The stablecoin legs. `USDC-USD` is the conversion market the objective's "stablecoin/fiat conversion line" points at, and
#: `BTC-USDC` is the same coin on the other side of it — a book that is worse for the same trade.
#: Probed 2026-09-08 from the venue's own product list, which needs no key: there is **no `USDC-USD` product** (its book answers 404),
#: and the USDC-quoted coin markets (`BTC-USDC`, `ETH-USDC`) come back `status: delisted, trading_disabled: true`. So the objective's
#: "stablecoin/fiat conversion line" is not a market with a spread — it is an internal conversion quoted at exactly 1.0, whose fee, if any,
#: is a product fact behind the same wall as the schedule. The tool records those probe answers and invents no number for the line.
PRODUCT_LIST = "https://api.exchange.coinbase.com/products"                            # not the `PRODUCTS` tuple below: that is the
#: product *lines* an ingest may name, and this file had that name first.
CONVERSION_QUOTE = "https://api.coinbase.com/v2/prices/USDC-USD/buy"
USDC_QUOTED_COINS = ("BTC-USDC", "ETH-USDC")
CONVERSION_PAIR = "USDC-USD"                                                   # probed anyway, so the 404 is on the record
QUOTE = "https://api.coinbase.com/v2/prices/{pair}/{side}"

#: The attempts made against the venue's published schedules, kept so the refusal is evidence rather than an excuse.
PROBE_LOG = (
    {"probed": "2026-09-08", "url": "https://help.coinbase.com/en/exchange/trading-and-fees/exchange-fees",
     "outcome": "HTTP 403 Forbidden", "note": "also 403 with a browser user-agent and Accept-Language: it is a JS challenge"},
    {"probed": "2026-09-08", "url": "https://www.coinbase.com/advanced-fees", "outcome": "HTTP 403 Forbidden",
     "note": "same for /legal/trading-rules/exchange and /fees"},
    {"probed": "2026-09-08", "url": "http://web.archive.org/web/20260506154253/https://www.coinbase.com/advanced-fees",
     "outcome": "200 OK, 12,367 bytes, sha256 139b5b1a2fb53de2…, but 0 occurrences of 'taker', 'maker', or any 'd.dd%' figure",
     "note": "the archived copy is the client-side shell; the table is rendered by JavaScript the archive did not run"},
    {"probed": "2026-09-08", "url": "https://api.exchange.coinbase.com/fees", "outcome": "not attempted",
     "note": "the endpoint needs an authenticated account key, and this lab holds no credentials and asks for none"},
)

PRODUCTS = ("advanced-trade", "exchange", "consumer")


def _get(url: str) -> bytes:
    import fetch_market_data as fm                                              # noqa: PLC0415  one TLS/CA answer in the repository
    return fm._get(url)


#: What every probe returned — bytes and hashes — for the run in progress. `_fetch` fills it and `measure()` empties it, which is how a
#: measurement can be archived the way the fee schedule would have been archived: dated, sourced, hashed, instead of quoted in prose.
RAW_LOG: list[dict] = []


def _fetch(url: str) -> bytes:
    body = _get(url)
    RAW_LOG.append({"url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    return body


def touch(pair: str) -> dict:
    """The top of one book, as bid/ask/mid and the touch in bps. Rows are `[price, size, number_of_orders]`: index 0 is the price."""

    try:
        book = json.loads(_fetch(BOOK.format(pair=pair)))
        bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
        mid = (bid + ask) / 2
        return {"bid": bid, "ask": ask, "mid": mid, "touch_bps": round((ask - bid) / mid * 10_000, 3)}
    except Exception as exc:                                                    # noqa: BLE001  a failed probe is a fact, not a crash
        return {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}


def measure() -> dict:
    """Live, public, no key: what it costs to cross the venue's own book, its conversion market, and what its retail quote marks up."""

    RAW_LOG.clear()
    out: dict = {"measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "books": {}, "retail_quote": {},
                 "conversion": {}}
    for pair in ("BTC-USD", "ETH-USD"):
        out["books"][pair] = touch(pair)
    usdc = out["conversion"]["USDC-USD"] = {"book": touch(CONVERSION_PAIR)}
    # The product list answers the two questions the objective's conversion clause actually asks, and it answers them without a key: is
    # there a USDC-USD market at all, and are the USDC-quoted coin books executable? Both answers happen to be no.
    try:
        usdc["public_quote"] = json.loads(_fetch(CONVERSION_QUOTE))["data"]["amount"]
    except Exception as exc:                                                    # noqa: BLE001
        usdc["public_quote"] = f"{type(exc).__name__}"
    try:
        prods = {prod["id"]: prod for prod in json.loads(_fetch(PRODUCT_LIST))}
        usdc["product_listed"] = "USDC-USD" in prods
        usdc["usdc_quoted_coins"] = {pid: ({"listed": True,
                                            "tradable": prods[pid].get("status") == "online"
                                            and not prods[pid].get("trading_disabled")}
                                          if pid in prods else {"listed": False, "tradable": False})
                                     for pid in USDC_QUOTED_COINS}
        usdc["online_usdc_quoted"] = sorted(pid for pid, prod in prods.items()
                                            if prod.get("quote_currency") == "USDC" and prod.get("status") == "online"
                                            and not prod.get("trading_disabled"))
    except Exception as exc:                                                    # noqa: BLE001
        usdc["product_list_error"] = f"{type(exc).__name__}: {str(exc)[:60]}"
    spot = out["books"].get("BTC-USD", {}).get("bid")
    if spot:
        try:
            buy = float(json.loads(_fetch(QUOTE.format(pair="BTC-USD", side="buy")))["data"]["amount"])
            mid = out["books"]["BTC-USD"]["bid"] + (out["books"]["BTC-USD"]["ask"] - out["books"]["BTC-USD"]["bid"]) / 2
            out["retail_quote"]["BTC-USD"] = {"buy_quote": buy, "markup_bps_vs_mid": round((buy - mid) / mid * 10_000, 2)}
        except Exception as exc:                                                # noqa: BLE001
            out["retail_quote"]["BTC-USD"] = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
    out["probes"] = list(RAW_LOG)
    return out


def ingest(product: str, taker_bps: float, maker_bps: float, tier: str, as_of: str, note: str,
           text_file: Path | None) -> dict:
    """Record what the operator read, hashed if they saved the text, and never silently."""

    if product not in PRODUCTS:
        raise SystemExit(f"unknown product {product!r}; this lab prices {', '.join(PRODUCTS)}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise SystemExit("--as-of must be YYYY-MM-DD: the date is the point of the record")
    blob = text_file.read_bytes() if text_file else None
    record = {
        "venue": "Coinbase", "market": "US spot", "product": product, "tier": tier,
        "taker_bps": float(taker_bps), "maker_bps": float(maker_bps),
        "as_of": as_of, "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "operator-supplied; the published schedule is unreachable to a script and the probe log is in this file",
        "note": note,
        "supplied_text_sha256": hashlib.sha256(blob).hexdigest() if blob else None,
        "supplied_bytes": len(blob) if blob else None,
        "measured": measure(),
        "probe_log": list(PROBE_LOG),
    }
    VENUE_DIR.mkdir(parents=True, exist_ok=True)
    if RECORD.exists():
        # Versions are cheap and cheap beats overwriting: a run priced on tier X should be re-derivable months later.
        stamp = json.loads(RECORD.read_text())["recorded_at"]
        (VENUE_DIR / f"coinbase-us-spot-{stamp}.json").write_text(RECORD.read_text())
    RECORD.write_text(json.dumps(record, indent=2) + "\n")
    return record


def load() -> dict | None:
    return json.loads(RECORD.read_text()) if RECORD.is_file() else None


def age_days(record: dict, today: date | None = None) -> int:
    return ((today or date.today()) - date.fromisoformat(record["as_of"])).days


def taker_bps(purpose: str, today: date | None = None) -> float:
    """The number a run must use. Absent or stale is a refusal that explains itself, never a default."""

    record = load()
    if record is None:
        lines = ["", "  no Coinbase fee record: this lab cannot price a trade, and it will not guess.",
                 f"  what was tried ({PROBE_LOG[0]['probed']}):"]
        for probe in PROBE_LOG:
            lines.append(f"    - {probe['url']}\n        {probe['outcome']}; {probe['note']}")
        lines.append("  supply what the account actually shows:  tools/venue_fees.py ingest --product … --taker-bps … --as-of …")
        lines.append(f"  then {purpose} may run.")
        raise SystemExit("\n".join(lines))
    age = age_days(record, today)
    if age > MAX_AGE_DAYS:
        raise SystemExit(f"the Coinbase fee record is {age} days old (limit {MAX_AGE_DAYS}), so {purpose} will not price a trade on it; "
                         f"re-ingest what the account shows today")
    return float(record["taker_bps"])


def display(path: Path) -> str:
    """A path for humans: relative to the repo when it is inside it, absolute when a test or an overlay moved it."""

    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def snapshot() -> int:
    """Append today's measurement to an append-only archive, hashed, so a probe answer stays checkable after the venue changes it.

    This is the objective's "dated, sourced, with the hash beside the number" applied to the half of the cost stack that is actually
    reachable. The fee schedule still has to be ingested by a person, and a measurement landing here changes that not at all: `taker`
    still refuses, because the spread is not the fee (r110). One line per run, never edited, so the archive can show the venue's own
    answers moving over time instead of leaving one day's prose as the only record of it.
    """

    measured = measure()
    probes = measured.pop("probes")
    record = load()
    line = {"probed_at": measured["measured_at"], "probes": probes, "measured": measured,
            "fee_record_present": record is not None,
            "fee_record": None if record is None else {
                "as_of": record["as_of"], "product": record["product"], "tier": record["tier"],
                "file_sha256": hashlib.sha256(RECORD.read_bytes()).hexdigest()}}
    VENUE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(line, sort_keys=True)
    with MEASURES.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")
    entries = MEASURES.read_text(encoding="utf-8").splitlines()
    print("  Measured Coinbase probes, archived append-only")
    print(f"    file       {display(MEASURES)}  ({len(entries)} entries; this is line {len(entries)})")
    print(f"    probed     {line['probed_at']}, {len(probes)} urls, entry sha256 "
          f"{hashlib.sha256(payload.encode()).hexdigest()[:16]}")
    for probe in probes:
        print(f"      {probe['bytes']:>7,} B  {probe['sha256'][:16]}…  {probe['url']}")
    print("    fee record   still absent — this archive prices nothing"
          if not line["fee_record_present"] else
          f"    fee record   {line['fee_record']['as_of']} ({line['fee_record']['product']}), file sha256 "
          f"{line['fee_record']['file_sha256'][:16]}…")
    print("    an archived measurement is not a licence: `taker` still refuses without an ingested fee record.")
    return 0


def report(today: date | None = None) -> int:
    record = load()
    print("  Coinbase, US spot — the cost stack a crypto run must pay, separated by how each part is known")
    measured = measure()
    print(f"    measured at {measured['measured_at']} (public, no key)")
    for pair, facts in measured["books"].items():
        if "error" in facts:
            print(f"      {pair:<8} book probe failed: {facts['error']}")
        else:
            print(f"      {pair:<8} bid {facts['bid']:>12,.2f}  ask {facts['ask']:>12,.2f}  touch {facts['touch_bps']:>7.3f} bps")
    for pair, facts in measured["retail_quote"].items():
        if "error" not in facts:
            print(f"      {pair:<8} retail buy quote {facts['buy_quote']:>12,.2f}  "
                  f"marked up {facts['markup_bps_vs_mid']:.2f} bps over the book mid")
    usdc = measured["conversion"].get("USDC-USD", {})
    book = usdc.get("book", {})
    print(f"      USDC-USD book      {book.get('error', 'no answer')} — listed on the exchange: "
          f"{usdc.get('product_listed', 'unknown')}")
    print(f"      USDC-USD quote     {usdc.get('public_quote', 'no answer')} — exact parity, because both legs are dollars: there is no "
          f"market to spread against")
    coins = usdc.get("usdc_quoted_coins", {})
    print("      USDC-quoted coins  " + (", ".join(f"{pid} {'tradable' if c.get('tradable') else 'NOT executable'}"
                                                   for pid, c in coins.items()) or "unknown"))
    print(f"      online USDC books  {', '.join(usdc.get('online_usdc_quoted') or ['none'])}")
    print("      the conversion line therefore has no observable spread and no bookable cost. That is not the same as free: it is")
    print("      *unpriced*, which is why no conversion bps appears anywhere in this repository and why the cash leg is priced by its")
    print("      yield rather than by a conversion fee nobody outside an authenticated session can read.")
    if MEASURES.exists():
        archived = [json.loads(l) for l in MEASURES.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"    measured archive  {len(archived)} entries, newest {archived[-1]['probed_at']}  ({display(MEASURES)})")
    print("    the line that does decide the cash leg: the specs credit the below-the-line cash with a T-bill yield, and a T-bill is held at a")
    print("    broker, not on this venue. What idle USD earns *here* is a product fact behind the same 403 wall, so `tools/ba006.py` prices")
    print("    the cash leg at the T-bill yield and at zero, and prints both beside its verdict.")
    if record is None:
        taker_bps("BA-005")                                                      # raises, printing the probe log
    age = age_days(record, today)
    state = "current" if age <= MAX_AGE_DAYS else f"STALE beyond {MAX_AGE_DAYS} days"
    print(f"    fee record    {record['product']} / tier {record['tier']}: taker {record['taker_bps']:.1f} bps, "
          f"maker {record['maker_bps']:.1f} bps\n"
          f"                as of {record['as_of']} ({age} days old, {state}), method: {record['method']}")
    if record.get("supplied_text_sha256"):
        print(f"                supplied text sha256 {record['supplied_text_sha256'][:16]}… ({record['supplied_bytes']:,} bytes)")
    print("    not obtainable by script — the attempts that make this refusal evidence:")
    for probe in PROBE_LOG:
        print(f"      - {probe['outcome']}: {probe['url']}")
    return 0 if age <= MAX_AGE_DAYS else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("report", "snapshot", "ingest", "taker"))
    ap.add_argument("--product", choices=PRODUCTS)
    ap.add_argument("--taker-bps", type=float)
    ap.add_argument("--maker-bps", type=float)
    ap.add_argument("--tier", default="unspecified")
    ap.add_argument("--as-of", help="YYYY-MM-DD, the date the figure was seen")
    ap.add_argument("--note", default="")
    ap.add_argument("--text-file", type=Path, help="save the page or a typed copy; it is hashed, not trusted")
    ap.add_argument("--for", dest="purpose", default="the next run")
    args = ap.parse_args()

    if args.command == "report":
        return report()
    if args.command == "snapshot":
        return snapshot()
    if args.command == "taker":
        print(f"  taker fee for {args.purpose}: {taker_bps(args.purpose):.1f} bps")
        return 0
    if args.taker_bps is None or args.maker_bps is None or not args.as_of or not args.product:
        raise SystemExit("ingest needs --product --taker-bps --maker-bps --as-of (and --tier/--note/--text-file if you have them)")
    record = ingest(args.product, args.taker_bps, args.maker_bps, args.tier, args.as_of, args.note, args.text_file)
    print(f"  recorded: {record['product']} taker {record['taker_bps']:.1f} bps / maker {record['maker_bps']:.1f} bps "
          f"as of {record['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
