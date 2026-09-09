"""Rehearse the forward books against a month-end that has not happened yet.

Run: .venv/bin/python tools/rehearse_forward.py [--scenario all] [--capital 5000] [--deposit 500]

Five books are anchored, all of them holding one entry, and the first real seal is 2026-09-30. That means the code path that
actually decides whether this program works — seal an interval, accrue deposits, read the band, pay the spread, bill the
witness, append to both chains — has never once been exercised, and cannot be until the calendar moves. Everything in
`tests/test_paper*.py` exercises the engine on history, where a month-end is already in the file; the seal path itself was
last run in anger in round 24 against a toy archive, and round 84 changed two of its conventions (`_deposits_due` accrues a
transfer per calendar month, `days_to_invest` records the wait) under the cover of unit tests that could only call the
helper, never the command.

So the month-end is manufactured instead of waited for. This tool copies the sealed archive into a scratch directory, appends
synthetic month-end bars for dates after the seal, and drives the real CLI — `init`, `step`, `report`, `compare`, `verify` —
against the copy. Nothing here writes to `data/`: the append-only ledgers the repository trusts are not touched by a
rehearsal, and the synthetic rows never enter the corpus that scores claims. Prices are synthetic and the point is not a
return estimate; the point is that a seal is a *procedure*, and a procedure rehearsed against fabricated input is a procedure
known to run.

Four scenarios, each sealing as many month-ends as it needs:

  flat      three months, every price unchanged. The check is the absence of a sell: deposits arriving cannot be allowed to
            read as drift (round 84's defect), and a banded book that never sees movement must never issue a sell order.
  divergent SPY +12% and QQQ -12% in the second month, against the live 5-point band. A breach must produce a sell of the
            runner, and the entry must still verify.
  skipped   seal October, skip November, seal December. Two transfers must arrive on the December entry and the older one must
            be recorded as thirty days late, because a missed seal that forgives the deposit would raise the measured return
            by shrinking the denominator.
  crash     everything -25% in month one, then flat. Nobody is rebalanced into a hole, the book must not borrow, and the
            report must still print a witness gap rather than crash on a negative premium.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import re
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import labdata                                                  # noqa: E402  one resolver, one spelling of the override
import paper                                                   # noqa: E402

REAL_MARKET = ROOT / "data" / "current" / "market_daily.csv"
REAL_CASH = ROOT / "data" / "current" / "cash_daily.csv"

# The published-loop scenario copies the *live* state, not a fabricated book, so it names the real roots it copies and re-hashes.
DATA_ROOT = ROOT / "data"
PAPER_ROOT = DATA_ROOT / "paper"
JOURNAL_ROOT = DATA_ROOT / "journal"

MONTH_ENDS = (dt.date(2026, 9, 30), dt.date(2026, 10, 30), dt.date(2026, 11, 30), dt.date(2026, 12, 31))

SCENARIOS = {
    "flat": [{}, {}, {}, {}],
    "divergent": [{}, {"SPY": 1.12, "QQQ": 0.88}, {}, {}],
    "skipped": [{}, None, {}, {}],
    "crash": [{"*": 0.75}, {}, {}, {}],
}
SEALS = {"flat": (0, 1, 2), "divergent": (0, 1, 2), "skipped": (0, 2, 3), "crash": (0, 1)}


class Scratch:
    """A throwaway copy of the corpus and a throwaway book, repathed so the real paths are never in play."""

    def __init__(self, capital: float, deposit: float):
        # Round 87's own accident, in one comment. This class once set `self.cash = paper.CASH_FILE` a few lines before
        # repathing that global, so it appended a synthetic row to the real bill curve and discovered the mistake only because
        # `MarketData` then refused to load a price date with no cash factor. The real file was restored byte-exact against a
        # snapshot copy — the recovery worked because the archive is snapshotted, which the engine file rebuilt in round 84
        # was not. Two rules come out of it: bind the paths you will write to in the same statement that repaths the module,
        # and refuse to write to anything you cannot prove is scratch.
        self.dir = Path(tempfile.mkdtemp(prefix="ba-rehearsal-"))
        (self.dir / "data" / "current").mkdir(parents=True)
        shutil.copy(REAL_MARKET, self.dir / "data" / "current" / "market_daily.csv")
        shutil.copy(REAL_CASH, self.dir / "data" / "current" / "cash_daily.csv")
        (self.dir / "data" / "paper").mkdir()
        self.market = self.dir / "data" / "current" / "market_daily.csv"
        self.cash = self.dir / "data" / "current" / "cash_daily.csv"
        self._saved = (paper.DATA, paper.SNAPSHOT, paper.CASH_FILE, paper.PAPER_DIR, paper.OPENING, paper.MONTHLY)
        paper.DATA = self.dir / "data"
        paper.SNAPSHOT = self.market
        paper.CASH_FILE = self.dir / "data" / "current" / "cash_daily.csv"
        paper.PAPER_DIR = self.dir / "data" / "paper"
        paper.OPENING, paper.MONTHLY = capital, deposit

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        (paper.DATA, paper.SNAPSHOT, paper.CASH_FILE, paper.PAPER_DIR, paper.OPENING, paper.MONTHLY) = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)
        return False

    def append_month(self, asof: dt.date, factors: dict):
        """Append one synthetic month-end bar, and the cash row that has to travel with it.

        `MarketData` raises on a price date with no bill-curve factor, which the rehearsal discovered on its first run: the
        engine cannot seal a date the cash series does not cover. That is not a defect — `fetch_market_data.py` writes prices
        and cash in one atomic rename precisely so a run can never pair new prices with old cash — but it means a rehearsal
        that appends only prices is testing a corpus the fetcher could never produce. The factor is held flat at the last
        sealed value, which is an assumption, and a harmless one: the rehearsal scores a procedure, not a return.
        """

        for target in (self.market, self.cash):
            if self.dir not in target.parents:
                raise SystemExit(f"refusing to append synthetic rows to {target}: it is not inside the scratch directory")
        with self.market.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        last = [r for r in rows if r["date"] == rows[-1]["date"]]
        with self.cash.open(newline="", encoding="utf-8") as handle:
            flat = list(csv.DictReader(handle))[-1]["cash_factor"]
        with self.cash.open("a", newline="", encoding="utf-8") as handle:
            handle.write(f"{asof.isoformat()},{flat}\n")
        with self.market.open("a", newline="", encoding="utf-8") as handle:
            for row in last:
                factor = factors.get(row["symbol"], factors.get("*", 1.0))
                close = float(row["tr_close"]) * factor
                handle.write(f"{asof.isoformat()},{row['symbol']},{close:.10f},{close:.10f}\n")

    def call(self, func, **kwargs) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            func(SimpleNamespace(**{"book": "rehearsal", **kwargs}))
        return out.getvalue()

    def rows(self, ledger: str = "ledger") -> list:
        path = paper.PAPER_DIR / "books" / "rehearsal" / f"{ledger}.jsonl"
        return paper.read(path) if path.exists() else []


class SimpleNamespace:
    """The CLI's parsed arguments, without making the rehearsal depend on argparse's defaults."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _prices(entry) -> dict:
    """The sealed quotes, as the only place a price may be read from."""

    return {q.symbol: q.close for q in entry.quotes}


def _drift_points(entry, weights: dict) -> float:
    """How far the invested book sits from target, in weight points, computed the way round 84 insisted: across what is
    invested, never across a balance that includes the transfer that arrived this month."""

    prices = _prices(entry)
    invested = sum(h.units * prices[h.symbol] for h in entry.holdings)
    if invested <= 0.0:
        return 0.0
    return max(abs(h.units * prices[h.symbol] / invested * 100.0 - weights.get(h.symbol, 0.0) * 100.0)
               for h in entry.holdings)


def run(scenario: str, capital: float, deposit: float) -> list:
    """Drive one scenario end to end and return every check as (name, passed, detail)."""

    checks: list = []
    plan = SCENARIOS[scenario]
    model = "tilt_band"
    weights = paper.tilt_weights()
    with Scratch(capital, deposit) as scratch:
        scratch.call(paper.command_init, model=model, asof=None, comparator=None, tilt=None, band=None)
        chain = scratch.rows()
        checks.append((f"{scenario}: anchored and verified", paper.verify(paper.PAPER_DIR / "books" / "rehearsal" /
                                                                         "ledger.jsonl") and len(chain) == 1,
                       f"{len(chain)} entries, head {chain[-1].asof}"))
        prior_hold = {}
        for month in SEALS[scenario]:
            scratch.append_month(MONTH_ENDS[month], plan[month])
            out = scratch.call(paper.command_step)
            if "Traceback" in out:
                checks.append((f"{scenario}: seal {MONTH_ENDS[month].isoformat()}", False, out.strip().splitlines()[-1]))
                break
            chain = scratch.rows()
            head, previous = chain[-1], chain[-2]
            gap = (head.asof.year - previous.asof.year) * 12 + head.asof.month - previous.asof.month
            expected_cash = deposit * gap
            checks.append((f"{scenario}: {head.asof} sealed", head.asof == MONTH_ENDS[month] and len(chain) >= 2,
                            f"entry {head.index}, closing ${head.closing_value:,.2f}"))
            checks.append((f"{scenario}: {head.asof} accrued {gap} month(s) of transfers",
                           abs(head.cash_arrived - expected_cash) < 0.01,
                           f"sealed ${head.cash_arrived:,.2f}, expected ${expected_cash:,.2f}"))
            checks.append((f"{scenario}: {head.asof} reports the wait honestly",
                           head.days_to_invest == 30 * max(gap - 1, 0),
                           f"days_to_invest {head.days_to_invest}, expected {30 * max(gap - 1, 0)}"))
            prices = _prices(head)
            positions = sum(h.units * prices[h.symbol] for h in head.holdings)
            recovered = paper.recover_cash(head, prices, 0.0, {h.symbol: h.units for h in head.holdings})
            checks.append((f"{scenario}: {head.asof} closes on its own quotes and recovers its cash line",
                           abs(head.closing_value - positions - recovered) < 0.005 and head.closing_value > 0.0,
                           f"closing ${head.closing_value:,.2f} = positions ${positions:,.2f} + cash "
                           f"${recovered:,.2f} recovered at the sealed prices"))
            # A plan that says it never borrows may not end an interval owing money, and may not record that it borrowed a
            # cent in the note it sealed. Round 87 found the engine doing exactly that: a band-triggered rebalance sized a buy
            # one cent past the cash that existed, and the ledger's answer was to book a loan and charge 0.0049 of interest
            # on it, silently contradicting the `plan` string in the same entry.
            cent_loan = re.search(r"on (0\.0[1-9]) borrowed", head.note)
            checks.append((f"{scenario}: {head.asof} took no loan on a plan that forbids it",
                           recovered >= -0.005 and cent_loan is None,
                           f"recovered cash {recovered:+.4f}" + (f", note records {cent_loan.group(1)} borrowed"
                                                                  if cent_loan else ", no borrowing in the note")))
            sold = ([h.symbol for h in head.holdings if prior_hold.get(h.symbol, h.units) > h.units + 1e-9]
                    if prior_hold else [])

            checks.append((f"{scenario}: {head.asof} sold {len(sold)} sleeve(s), drift "
                           f"{_drift_points(head, weights):.1f} points",
                           (bool(sold) if scenario == "divergent" and month == 1 else not sold) if month else True,
                           f"sold {sold or 'nothing'}; band {paper.TILT_BAND_POINTS:g} points"))
            prior_hold = {h.symbol: h.units for h in head.holdings}
            checks.append((f"{scenario}: {head.asof} both chains verify",
                           bool(paper.verify(paper.PAPER_DIR / "books" / "rehearsal" / "ledger.jsonl"))
                           and bool(paper.verify(paper.PAPER_DIR / "books" / "rehearsal" / "shadow.jsonl")),
                           f"shadow entries {len(scratch.rows('shadow'))}, ledger entries {len(chain)}"))
        # The round-92 audit, run against the entries this scenario actually sealed: the only place in the repository where the
        # audit sees multi-entry chains with real trades, a real band breach, a skipped month and a crash in them. A check that
        # only ever runs on a fabricated fixture is a check that has never met the engine's own output.
        import audit_entries
        model_path = paper.PAPER_DIR / "books" / "rehearsal" / "model.json"
        model = json.loads(model_path.read_text()) if model_path.exists() else {}
        findings = audit_entries.audit(scratch.rows(), model)
        checks.append((f"{scenario}: no sealed entry contradicts itself", not findings,
                       "; ".join(f"{f['kind']} @ entry {f['index']}: {f['detail']}" for f in findings)
                       or f"{len(chain)} entries account for themselves"))
        report = scratch.call(paper.command_report)
        checks.append((f"{scenario}: the report prints and names its witness",
                       "VOO" in report and ("underpowered" in report.lower() or "dominance" in report.lower()),
                       report.strip().splitlines()[-1] if report.strip() else "printed nothing"))
    return checks


PUBLISHED = "published"
FETCH = "fetch"
STAMP_RE = re.compile(r"\d{8}T\d{6}Z")        # only a fetch names a directory like this; a rehearsal's does not
#: The one command the published scenario cannot run inside itself, because the whole point of the scenario is that it cannot write a real
#: snapshot. It is not unexercised: `--scenario fetch` below runs the fetch into a copy through the fetcher's own `--out`, and
#: `corpus_diff.py` follows `BORINGALPHA_DATA`, so it is no longer a reason to skip the diff — round 8 of this goal removed that excuse.
SKIP = {"fetch_market_data.py": "a rehearsal must not be able to write a real snapshot; run it for real with --scenario fetch"}


def next_seal_date(after: dt.date) -> dt.date:
    """The last weekday of `after`'s month, or of the next month if the corpus has already traded past it."""

    year, month = after.year, after.month
    end = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    if end <= after:
        month += 1
        if month == 13:
            month, year = 1, year + 1
        end = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    while end.weekday() >= 5:
        end -= dt.timedelta(days=1)
    return end


def weekdays_between(start: dt.date, end: dt.date) -> list[dt.date]:
    out, day = [], start + dt.timedelta(days=1)
    while day <= end:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def corpus_last() -> dt.date:
    with REAL_MARKET.open(newline="") as handle:
        return max(dt.date.fromisoformat(row["date"]) for row in csv.DictReader(handle))


def tree_manifest(root: Path) -> dict[str, tuple[int, str]]:
    """(size, sha256) of every file under `root`. The published-loop check compares the real tree against this, file by file."""

    return {str(path.relative_to(root)): (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(path for path in root.rglob("*") if path.is_file())}


def is_step(command: list[str]) -> bool:
    return len(command) > 2 and command[1].endswith("paper.py") and command[2] == "step"


def published_plan(copy_paper: Path) -> list[list[str]]:
    """The published block, minus the two commands a rehearsal must not run, with the step lines expanded to one per book on the copy.

    The expansion mirrors `monthly.py`: the runbook names the root and one book and says "and each other book", which a script can only
    learn by looking at a shelf — except that this looks at the *copy's* shelf, because that is the shelf the loop will seal.
    """

    import monthly                                                       # noqa: PLC0415  the runbook stays the authority

    published = monthly.published_commands()
    root_step = next((c for c in published if is_step(c) and "--book" not in c), ["python", "tools/paper.py", "step"])
    shelf = copy_paper / "books"
    books = sorted(d.name for d in shelf.iterdir() if (d / "ledger.jsonl").exists()) if shelf.is_dir() else []

    commands: list[list[str]] = []
    expanded = False
    for command in published:
        script = Path(command[1]).name if len(command) > 1 else ""
        if script in SKIP:
            continue
        if is_step(command):
            if not expanded:
                commands.append(root_step)
                commands.extend([*root_step, "--book", book] for book in books)
                expanded = True
            continue
        commands.append(command)
    return commands


def build_published_copy(dir_: Path, target: dt.date) -> Path:
    """A copy of the real books and journal, and a corpus carried forward flat to `target`. Returns the synthetic snapshot directory.

    The prices invented here are the last real close repeated, and the snapshot directory says so in its own name: a ledger entry sealed
    against a `REHEARSAL-*` snapshot can never be mistaken for one sealed against a fetched corpus.
    """

    data = dir_ / "data"
    data.mkdir(parents=True)
    shutil.copytree(PAPER_ROOT, data / "paper")
    shutil.copytree(JOURNAL_ROOT, data / "journal")
    snapshot = data / "snapshots" / f"REHEARSAL-{target.isoformat()}T000000Z"
    snapshot.mkdir(parents=True)
    shutil.copy(REAL_MARKET.parent / "distributions_daily.csv", snapshot)

    last = corpus_last()
    with REAL_MARKET.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or ["date", "symbol", "tr_open", "tr_close"]
        carried = {row["symbol"]: dict(row) for row in reader}
    with (snapshot / "market_daily.csv").open("w", newline="") as out_handle, REAL_MARKET.open(newline="") as source:
        writer = csv.DictWriter(out_handle, fieldnames=fields)
        writer.writeheader()
        for row in csv.DictReader(source):
            writer.writerow(row)
        for day in weekdays_between(last, target):
            for symbol, row in carried.items():
                writer.writerow({"date": day.isoformat(), "symbol": symbol,
                                 "tr_open": row["tr_close"], "tr_close": row["tr_close"]})
    with REAL_CASH.open(newline="") as handle:
        cash_rows = list(csv.DictReader(handle))
    with (snapshot / "cash_daily.csv").open("w", newline="") as out_handle:
        out_handle.write(REAL_CASH.read_text())
        for day in weekdays_between(last, target):
            out_handle.write(f"{day.isoformat()},{cash_rows[-1].get('cash_factor', '1.0')}\n")
    (snapshot / "REHEARSAL.json").write_text(json.dumps({
        "synthetic": True,
        "real_corpus_last_session": last.isoformat(),
        "rehearsal_asof": target.isoformat(),
        "sessions_invented": len(weekdays_between(last, target)),
        "symbols_carried": len(carried),
        "rule": "every invented session carries the last real close flat; the cash factor is held at its last value",
        "not_evidence": "no number derived from these rows measures a strategy; they exist to execute the plumbing",
    }, indent=2) + "\n")
    (data / "current").symlink_to(Path("snapshots") / snapshot.name)
    return snapshot


def run_published(target: dt.date | None = None) -> list:
    """Drive the published monthly block itself — every command an operator would run, as its own process — against a copy.

    The four engine scenarios above drive `paper.py` in-process on one scratch book. That is the right rehearsal for the engine and the
    wrong one for the month: a month is `forward_p0`, five seals, `journalctl`, the audit, the cost sheet, a report and a compare, each a
    separate process reading the state root at its own import. This scenario is the only place that chain, and the redirection that makes
    it point somewhere disposable, are exercised together.
    """

    checks: list = []
    target = target or next_seal_date(corpus_last())
    before = tree_manifest(DATA_ROOT)
    dir_ = Path(tempfile.mkdtemp(prefix="ba-published-rehearsal-"))
    saved_env = os.environ.get("BORINGALPHA_DATA")
    os.environ["BORINGALPHA_DATA"] = str(dir_ / "data")
    try:
        snapshot = build_published_copy(dir_, target)
        copy_root = dir_ / "data" / "paper" / "ledger.jsonl"
        anchor = dt.date.fromisoformat(json.loads(copy_root.read_text().splitlines()[-1])["asof"])
        commands = published_plan(dir_ / "data" / "paper")
        failures = []
        for command in commands:
            proc = subprocess.run(command, cwd=ROOT, env=dict(os.environ), capture_output=True, text=True)
            last_line = ((proc.stdout.strip().splitlines() or [""])[-1] if proc.stdout else "").strip()[:70]
            detail = last_line if proc.returncode == 0 else ((proc.stderr.strip().splitlines()
                                                               or [proc.stdout.strip()])[-1])[:70]
            checks.append((f"{PUBLISHED}: `{' '.join(command[1:])}` exits 0", proc.returncode == 0, detail))
            if proc.returncode != 0:
                failures.append((" ".join(command), proc.returncode, (proc.stderr or proc.stdout).strip()))
                break
        ledgers = {}
        for ledger in sorted((dir_ / "data" / "paper").rglob("ledger.jsonl")):
            rel = str(ledger.relative_to(dir_ / "data" / "paper"))
            if not rel.startswith("superseded"):
                ledgers[rel] = sum(1 for line in ledger.read_text().splitlines() if line.strip())
        sealed = [k for k, v in ledgers.items() if v >= 2]
        checks.append((f"{PUBLISHED}: every live book sealed exactly one new entry on {target.isoformat()}",
                       len(sealed) == len(ledgers) == len([c for c in commands if is_step(c)]),
                       f"{len(sealed)} of {len(ledgers)} ledgers gained an entry: " + ", ".join(f"{k} {v}" for k, v in sorted(ledgers.items()))))

        import paper                                                     # noqa: PLC0415  the module under rehearsal

        root_step = next(c for c in commands if is_step(c) and "--book" not in c)
        twice = subprocess.run(root_step, cwd=ROOT, env=dict(os.environ), capture_output=True, text=True)
        refused = twice.returncode != 0 and "already closed" in (twice.stdout + twice.stderr)
        checks.append((f"{PUBLISHED}: running the month twice is refused, not double-sealed", refused,
                       ((twice.stdout + twice.stderr).strip().splitlines() or [""])[-1][:90]))

        # The deposit clock, checked against calendar arithmetic written here rather than against the engine's own helper: the objective
        # names 2026-10-30 as the first deposit, and the only way to know the loop agrees with that date is to compute it independently.
        months = (target.year - anchor.year) * 12 + (target.month - anchor.month)
        expected = paper.MONTHLY * max(months, 0)
        head = json.loads(copy_root.read_text().splitlines()[-1])
        checks.append((f"{PUBLISHED}: the transfers the calendar owes at {target.isoformat()} are the ones that arrived",
                       abs(head["cash_arrived"] - expected) < 0.01 and head["days_to_invest"] == 30 * max(months - 1, 0),
                       f"cash_arrived ${head['cash_arrived']:,.2f} over {months} calendar month(s) from the {anchor.isoformat()} anchor, "
                       f"expected ${expected:,.2f}, days_to_invest {head['days_to_invest']}"))
        quotes = dict(head.get("quotes") or [])          # the ledger's own serialization: a list of ["SYMBOL", close] pairs
        checks.append((f"{PUBLISHED}: the seal priced itself off quotes it sealed, not off a pointer it read later",
                       bool(quotes) and all(v > 0 for v in quotes.values()),
                       f"{len(quotes)} sealed quotes, e.g. " + ", ".join(f"{s} {quotes[s]:.2f}" for s in list(quotes)[:3])))
        # What the entry does *not* carry is recorded rather than glossed: a sealed entry stores its quotes and its date, not the id of the
        # corpus directory it was read from, so distinguishability here lives in the directory name and in the copy being disposable.
        checks.append((f"{PUBLISHED}: the synthetic corpus is identifiable by name (entries seal quotes, not a snapshot id)",
                       snapshot.name.startswith("REHEARSAL-"),
                       f"synthetic snapshot {snapshot.name}; sidecar says what was invented"))
        after = tree_manifest(DATA_ROOT)
        touched = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]
        checks.append((f"{PUBLISHED}: no file under the real data/ tree changed", not touched,
                       f"{len(touched)} files changed" + (f": {touched[:3]}" if touched else "")))
        if failures:
            checks.append((f"{PUBLISHED}: the loop stopped at `{' '.join(failures[0][0])}` with exit {failures[0][1]}",
                           False, failures[0][2].splitlines()[-1][:90] if failures[0][2] else ""))
    finally:
        if saved_env is None:
            os.environ.pop("BORINGALPHA_DATA", None)
        else:
            os.environ["BORINGALPHA_DATA"] = saved_env
        shutil.rmtree(dir_, ignore_errors=True)
    return checks


def run_fetch(target: dt.date | None = None, fetch_command: list[str] | None = None) -> list[tuple[str, bool, str]]:
    """Rehearse the fetch — the first command of the monthly block, and the one the published scenario cannot run.

    The published scenario drops `fetch_market_data.py` because a rehearsal must not be able to write a real snapshot. The fetcher already
    takes `--out`, so pointing it at a copy is the whole trick, and this scenario spends it: fetch into the copy, let `corpus_diff.py` read the
    copy, then ask the loop whether a seal is due against the fetched corpus. What a real fetch costs in seconds and rows is measured, not
    assumed, and the copy's pointer ends up naming a fetch stamp — which is the only way to know on 30 September that the ritual will find a
    corpus it is allowed to seal.

    `fetch_command` exists so the suite can rehearse the wiring offline; run without it and this really fetches.
    """

    checks: list[tuple[str, bool, str]] = []
    target = target or next_seal_date(corpus_last())
    stamp_before = corpus_last()
    before = tree_manifest(DATA_ROOT)
    with tempfile.TemporaryDirectory(prefix="ba-fetch-rehearsal-") as raw:
        dir_ = Path(raw)
        snapshot = build_published_copy(dir_, target)
        copy_data = dir_ / "data"
        saved_env = os.environ.get(labdata.ENV_VAR)
        os.environ[labdata.ENV_VAR] = str(copy_data)
        template = fetch_command or [sys.executable, str(ROOT / "tools" / "fetch_market_data.py"), "--out", "{out}"]
        command = [part.replace("{out}", str(copy_data)) for part in template]
        started = dt.datetime.now(dt.timezone.utc)
        try:
            run = subprocess.run(command, cwd=ROOT, env=dict(os.environ), capture_output=True, text=True)
        except OSError as exc:                                                # noqa: PERF203
            checks.append((f"{FETCH}: the fetch command ran", False, f"{type(exc).__name__}: {exc}"))
            return checks
        took = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
        wrote = next((l for l in run.stdout.splitlines() if "wrote" in l), "")
        checks.append((f"{FETCH}: the fetch command exits 0", run.returncode == 0,
                       (wrote or ((run.stdout + run.stderr).strip().splitlines() or ["no output"])[-1])[:88]))

        pointer = copy_data / "current"
        pointed = Path(os.readlink(pointer)) if pointer.is_symlink() else Path("")
        fetched = copy_data / "snapshots" / pointed.name
        manifest = fetched / "manifest.json"
        checks.append((f"{FETCH}: the copy gained a snapshot named by a fetch stamp, not by this rehearsal",
                       STAMP_RE.fullmatch(pointed.name) is not None, f"`current` -> {pointed.name}"))
        checks.append((f"{FETCH}: the manifest landed last, so the snapshot is a completed download",
                       manifest.exists(), f"{manifest.name} present: {manifest.exists()}"))
        rows = sum(1 for _ in (fetched / "market_daily.csv").open()) - 1 if (fetched / "market_daily.csv").exists() else 0
        checks.append((f"{FETCH}: the copy's corpus is a full panel, not a stub",
                       rows > 1000, f"{rows:,} price rows in the fetched snapshot"))

        diff = subprocess.run([sys.executable, str(ROOT / "tools" / "corpus_diff.py")], cwd=ROOT,
                              env=dict(os.environ), capture_output=True, text=True)
        # The proof is not that the diff succeeded — it would succeed against the real archive too — it is that it named the directory it
        # read, which is this run's scratch tree and nowhere else. A check that cannot tell a rehearsal from a real run is not a check.
        saw_copy = diff.returncode == 0 and dir_.name in (diff.stdout + diff.stderr)
        checks.append((f"{FETCH}: corpus_diff read the copy, and says which directory it opened", saw_copy,
                       ((diff.stdout + diff.stderr).strip().splitlines() or ["no output"])[-1][:88]))

        seal = subprocess.run([sys.executable, str(ROOT / "tools" / "paper.py"), "step"], cwd=ROOT,
                              env=dict(os.environ), capture_output=True, text=True)
        said = ((seal.stdout + seal.stderr).strip().splitlines() or ["no output"])[-1][:88]
        # Today is mid-month, so the honest answer to a fresh fetch is "nothing new to seal" — a refusal is a pass here, and the check says
        # which branch it took. What would fail the check is a crash, or a seal against a corpus the month has not shut.
        answered = seal.returncode == 0 or "not due" in said or "already closed" in said
        checks.append((f"{FETCH}: the loop answers the fetched corpus instead of crashing on it", answered,
                       ("sealed" if seal.returncode == 0 else "refused, correctly: ") + said))
        changed = sorted(k for k, v in tree_manifest(DATA_ROOT).items() if before.get(k) != v)
        checks.append((f"{FETCH}: no file under the real data/ tree changed", not changed,
                       f"{len(changed)} files changed" if changed
                       else f"fetched in {took:.0f}s; the real corpus still ends {corpus_last()} (was {stamp_before})"))
        if saved_env is None:
            os.environ.pop(labdata.ENV_VAR, None)
        else:
            os.environ[labdata.ENV_VAR] = saved_env
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", default="all", choices=("all", PUBLISHED, FETCH, *SCENARIOS))
    ap.add_argument("--asof", help="for --scenario published: the seal date to rehearse (default: the next month-end)")
    ap.add_argument("--capital", type=float, default=5_000.0)
    ap.add_argument("--deposit", type=float, default=500.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (REAL_MARKET, REAL_CASH)}
    with REAL_MARKET.open("rb") as handle:                     # the real tail, read as bytes so the check cannot be the
        handle.seek(-60, io.SEEK_END)                          # reason the check is slow
        tail = handle.read().decode("utf-8").strip().splitlines()[-1].split(",")[0]
    results, all_checks = [], []
    if args.scenario in ("all", PUBLISHED):
        # The published block is the slower half of the rehearsal — eleven processes, five seals — so `all` runs it and `--scenario
        # published` alone exists for the night before a seal date, when the engine scenarios are not the thing being doubted.
        checks = run_published(dt.date.fromisoformat(args.asof) if args.asof else None)
        all_checks += checks
        results.append({"scenario": PUBLISHED, "checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks]})
    if args.scenario == FETCH:
        # Deliberately not part of `all`: this is the only scenario that touches the network, and the suite and the nightly `all` run both
        # have to work offline. It exists to be run on purpose, before a seal date, once.
        checks = run_fetch(dt.date.fromisoformat(args.asof) if args.asof else None)
        all_checks += checks
        results.append({"scenario": FETCH, "checks": [{"name": n, "passed": p_, "detail": d} for n, p_, d in checks]})
    for scenario in (SCENARIOS if args.scenario == "all"
                     else ([args.scenario] if args.scenario not in (PUBLISHED, FETCH) else [])):
        checks = run(scenario, args.capital, args.deposit)
        all_checks += checks
        results.append({"scenario": scenario, "checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks]})

    failed = [c for c in all_checks if not c[1]]
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (REAL_MARKET, REAL_CASH)}
    untouched = after == before
    if args.json:
        print(json.dumps({"results": results, "failed": len(failed), "corpus_untouched": untouched}, indent=2))
    else:
        print(f"  FORWARD REHEARSAL · synthetic month-ends on a scratch copy · the sealed corpus is untouched "
              f"({len(all_checks)} checks)")
        for scenario in (({PUBLISHED, FETCH, *SCENARIOS} if args.scenario == "all" else {args.scenario})):
            for check, passed, detail in [c for c in all_checks if c[0].startswith(scenario)]:
                label = check.split(": ", 1)[1] if ": " in check else check
                print(f"     {'ok  ' if passed else 'FAIL'}  {label:<60} {detail}")
        print(f"     {'all checks passed' if not failed else f'{len(failed)} CHECKS FAILED'}"
              f" · the real archive still ends {tail}")
        print(f"     the real corpus is byte-identical to what it was before the rehearsal: "
              f"{'yes' if untouched else 'NO'}")
    return 1 if (failed or not untouched) else 0


if __name__ == "__main__":
    raise SystemExit(main())
