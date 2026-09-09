"""A runbook that nobody checks becomes a rumour, so this file checks it on every test run.

`docs/RUNBOOK.md` is the last mile of this repository: the archive cannot grade the growth tilt — only time can — but it can
hand the operator an exact monthly procedure, and rounds 87 and 88 proved that every step of it runs. What those rounds could
not guarantee is that the *document* stays true as the tools move under it. A runbook whose commands have rotted is worse than
no runbook, because it teaches the wrong procedure with the authority of documentation, and a runbook whose numbers were typed
rather than read is the same failure the sheet's discipline rule refuses to tolerate in a report.

So every load-bearing claim in it is re-derived here from the tools it cites: the commands must exist with the flags given, the
friction table must recompute from `paper`'s constants, the first-seal rule must come from `_deposits_due` itself, and the
status strings it quotes must be strings the tools actually print.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import paper                                                       # noqa: E402
from boring_alpha import journal                                       # noqa: E402
import power_horizon as ph                                         # noqa: E402
import rebalance_cost as rc                                        # noqa: E402

RUNBOOK = ROOT / "docs" / "RUNBOOK.md"
TICKET = rc.COMMISSIONS[-1]              # the per-order ticket the runbook prices the book against
TWO_YEARS = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 2)))


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _commands() -> list[str]:
    block = re.search(r"```sh\n(.*?)\n```", _text(), re.DOTALL)
    assert block, "the runbook's monthly procedure is not in a fenced sh block"
    return [line.split("#")[0].strip() for line in block.group(1).splitlines() if line.strip()]


class TheProseReprintsItsOwnFigures(unittest.TestCase):
    """The runbook is the document an operator obeys, so every percentage in it is a claim with a command underneath it.

    Round 100 found one that did not: the friction paragraph had said $175,786 was 0.87% of paid in for three rounds when the
    division is 8.70% — a mental-arithmetic slip against a paid-in figure ten times its size, in the direction that makes
    rebalancing look harmless. Nothing in the suite could notice, because no test read the prose. This one does, and it reads it
    by recomputing rather than by grepping a second copy of the number.
    """

    @classmethod
    def setUpClass(cls):
        record = ph.month_closes(None)
        cls.rows = rc.grid(record, "the record", len(record))
        five = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 5)))
        cls.rows += rc.grid(five, "five years", len(five))
        cls.paid = cls.rows[0]["paid_in"]

    def figures(self) -> dict:
        bill = 100.0 * rc.idealisation_tax(self.rows, "the record", "50% QQQ")["spread_cost_pct_paid_in"]
        recent = 100.0 * rc.idealisation_tax(self.rows, "five years", "50% QQQ")["spread_cost_pct_paid_in"]
        plain = rc.by(self.rows, window="the record", construction="50% QQQ", regime=rc.PLAIN)[0]["value"]
        band = rc.by(self.rows, window="the record", construction="50% QQQ", regime="band 5 pts")[0]["value"]
        drift = 100.0 * (plain - band) / self.paid
        return {"bill": bill, "recent": recent, "drift": drift, "ratio": drift / bill}

    def test_every_friction_percentage_in_the_prose_is_the_tools_own(self):
        text = RUNBOOK.read_text()
        f = self.figures()
        quoted = {f"{f['bill']:.3f}%": f["bill"], f"{f['recent']:.3f}%": f["recent"],
                  f"{f['drift']:.2f}%": f["drift"], f"{f['ratio']:.0f} times": f["ratio"]}
        for published, computed in quoted.items():
            self.assertIn(published, text,
                          f"the runbook no longer prints {published}, which rebalance_cost recomputes as {computed:.4f}")

    def test_the_corrected_slip_stays_corrected(self):
        self.assertNotIn("0.87% of paid in", RUNBOOK.read_text(),
                         "the round-100 correction regressed: a tenth of the policy cost, quoted as the policy cost")

    def test_the_typed_figure_would_have_been_caught(self):
        """r93, on the check itself: put the slip back the way the paragraph used to phrase it, and the scan must reject it.

        The document *does* still contain the string `0.87%`, inside the sentence that records the correction, so the scan is on
        the phrase as written — a share of paid in — rather than on bare digits.
        """

        f, text = self.figures(), RUNBOOK.read_text()
        self.assertNotIn(f"{f['drift'] / 10.0:.2f}% of paid in", text,
                         "the scan accepted the old slip, so it is not scanning for the figure")
        self.assertIn(f"{f['drift']:.2f}% of paid in", text, "and it does not find the true one either")


class TheDecisionFiguresAreReprinted(unittest.TestCase):
    """The two paragraphs an operator acts on — what to beat, and how big a win counts — with a command under every digit.

    Round 100 found one wrong share sitting in prose with no test able to see it. This extends the same discipline to the rest of
    the runbook's headline figures. The dollar figures are pinned to the dollar on purpose: the corpus gets re-pulled, and when a
    re-pull moves a replay then the runbook's sentence really is stale, so failing here and forcing the figure to be re-printed is
    the mechanism working. `corpus_diff.py` decides whether a revision matters; this class refuses to quote a moved figure as though
    it had not moved.
    """

    @classmethod
    def setUpClass(cls):
        cls.bars = ph.secondary_bars(None, "the record")["rows"]
        five = ph.month_closes(ph.last_date() - dt.timedelta(days=int(365.25 * 5)))
        cls.recent = ph.secondary_bars(five[0][0], "five years")["rows"]
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "skill_null.py"), "--paths", "600", "--json"],
                             capture_output=True, text=True, check=True)
        cls.null = json.loads(out.stdout)["rows"]

    @staticmethod
    def row(rows, prefix):
        return next(r for r in rows if r["bar"].startswith(prefix))

    def test_the_bar_paragraph_prints_what_the_command_prints(self):
        text = RUNBOOK.read_text()
        b = {p: self.row(self.bars, p) for p in ("plain VOO", "plain QQQ", "the tilt, rebalanced",
                                                 "the tilt, only past", "the tilt, never", "T-bills")}
        five_voo = self.row(self.recent, "plain VOO")
        bills = b["T-bills"]
        want = [f"${bills['paid_in']:,.0f} paid in", f"into ${bills['closed_at']:,.0f}",
                f"({100 * (bills['closed_at'] - bills['paid_in']) / bills['paid_in']:+.1f}% of paid in)",
                f"bar's ${b['plain VOO']['closed_at']:,.0f}",
                f"{b['the tilt, rebalanced']['closed_at']:,.0f} monthly, ${b['the tilt, only past']['closed_at']:,.0f} banded",
                f"${b['the tilt, never']['closed_at']:,.0f} never touched",
                f"${b['plain QQQ']['closed_at'] - b['the tilt, only past']['closed_at']:,.0f} behind plain QQQ",
                f"{100 * self.row(self.recent, 'T-bills')['closed_at'] / five_voo['closed_at']:.0f}% of the standing",
                f"{five_voo['worst_drawdown']:.1%}"]
        for published in want:
            self.assertIn(published, text, f"the runbook no longer prints {published!r}, which power_horizon prints today")

    def test_the_calibration_sentence_is_the_current_calibration(self):
        text = RUNBOOK.read_text()
        pinned = {r["horizon"]: r for r in self.null if r["mode"] == "hurdle-as-pinned" and r["paths"]}
        self.assertIn(f"**{100 * pinned[24]['beat']:.1f}%**", text, "the false-`beat` rate at the floor has moved")
        self.assertIn(f"**+{pinned[24]['margin_bps_p95']:.0f} bps**", text, "the p95 margin at 24 has moved")
        self.assertIn(f"~{pinned[36]['margin_bps_p95']:.0f} at 36", text, "the margin required at 36 has moved")
        self.assertIn(f"{abs(pinned[60]['median_bps']):.0f} bps", text, "the no-skill median at 60 has moved")

    def test_the_runbook_still_asks_for_no_margin_at_sixty_years(self):
        """`by anything at all at 60` is a claim about the p95, not a style choice: it has to stay non-positive to be true."""

        sixty = next(r for r in self.null if r["mode"] == "hurdle-as-pinned" and r["horizon"] == 60)
        self.assertLessEqual(sixty["margin_bps_p95"], 0.0,
                             f"the luckiest 5% of no-skill paths now clears {sixty['margin_bps_p95']:+.0f} bps at 60")

    def test_the_footer_names_the_classes_that_do_the_recomputing(self):
        """The sentence claiming the figures are checked is itself a claim, so it names the classes and this test reads them back."""

        text, here = RUNBOOK.read_text(), Path(__file__).read_text()
        for cls in ("TheFrictionTableIsComputed", "TheProseReprintsItsOwnFigures",
                    "TheDecisionFiguresAreReprinted"):
            self.assertIn(cls, text, f"the footer no longer names {cls}")
            self.assertIn(f"class {cls}(", here, f"{cls} is named and no longer exists")

    def test_the_runbook_does_not_copy_a_figure_it_cannot_reprint(self):
        """Round 82's tilt-versus-QQQ dollars appeared here and in the bar table, and only one of the two could be reprinted."""

        text = RUNBOOK.read_text()
        self.assertNotIn("12,316,793", text, "round 82's replay dollars are quoted here and nowhere reprinted")
        self.assertIn("the command's own line is the figure", text, "the sentence that dropped them should still say why")


class TheCommandsExist(unittest.TestCase):
    def test_every_command_in_the_procedure_names_a_tool_that_exists(self):
        for line in _commands():
            parts = line.split()
            self.assertEqual(parts[0], ".venv/bin/python", f"`{line}` is not written the way the repository is run")
            self.assertTrue((ROOT / parts[1]).exists(), f"{parts[1]} does not exist")

    def test_the_cost_audit_runs_after_the_seals_and_immediately_before_the_report(self):
        """Where a check sits in the month is part of what it checks.

        Sealing is calendar-bound and must not be blocked by a pricing disagreement; the report is where figures get republished,
        so an audit that runs after it would be decoration. This pins the seat, not the outcome: the audit is the last command to
        run before anything is printed, and everything after it only prints.
        """

        cmds = _commands()
        at = [i for i, c in enumerate(cmds) if "cost_conventions" in c]
        self.assertEqual(len(at), 1, "the audit must appear exactly once in the month")
        i = at[0]
        seals = [j for j, c in enumerate(cmds) if " step" in c or " step --book" in c]
        self.assertTrue(seals, "the block lost its seals")
        self.assertGreater(i, max(seals), "the audit runs before the seals, so a cost disagreement would block a seal")
        rest = cmds[i + 1:]
        self.assertTrue(rest, "the audit is last, so nothing consumes what it protects")
        for c in rest:
            self.assertTrue(" report" in c or " compare" in c, f"{c} runs after the audit but is not a print-only command")

    def test_the_audit_is_the_only_monthly_command_whose_failure_is_about_the_page_not_the_book(self):
        """`audit_entries.py` checks the ledger against itself; this one checks the money facts the *prose* rests on.

        Pinned because the two are easy to conflate, and they protect different things: a book that will not verify is a book that
        never happened, and a cost constant that has two answers leaves the book intact and the recommendation wrong.
        """

        cmds = _commands()
        ledger = [c for c in cmds if "audit_entries" in c]
        costs = [c for c in cmds if "cost_conventions" in c]
        self.assertEqual(len(ledger), 1)
        self.assertEqual(len(costs), 1)
        self.assertLess(cmds.index(ledger[0]), cmds.index(costs[0]),
                        "the ledger is audited after the costs, so a cost failure hides a ledger failure")

    def test_every_subcommand_and_flag_is_one_the_tool_actually_accepts(self):
        """Checked against the tool's own help rather than against this test's memory of it. A runbook that says
        `step --force` after the flag was removed would otherwise keep its authority for years."""

        for line in _commands():
            argv = line.split()[2:]
            tool = line.split()[1]
            # A tool with no subcommands takes its flags straight off the top-level help; one with them has to be asked about
            # the subcommand named, because `paper.py --help` never mentions `--book`.
            probe = argv[:1] if argv and not argv[0].startswith("--") else []
            help_text = subprocess.run([sys.executable, str(ROOT / tool)] + probe + ["--help"],
                                       capture_output=True, text=True, check=True).stdout
            if probe:
                self.assertIn(probe[0], help_text, f"`{line}`: {tool} has no subcommand {probe[0]}")
            for token in argv[len(probe):]:
                if token.startswith("--"):
                    self.assertIn(token, help_text, f"`{line}`: {tool} {probe} does not accept {token}")


class TheFrictionTableIsComputed(unittest.TestCase):
    """The table's expense and spread columns, re-derived from the same constants the engine charges itself with."""

    @classmethod
    def setUpClass(cls):
        cls.weights = paper.tilt_weights()
        cls.weighted = sum(cls.weights[s] * paper.fee_for(s) for s in cls.weights)

    def row(self, capital: float) -> tuple:
        for line in _text().splitlines():
            if line.startswith(f"| ${capital:,.0f} |"):
                cells = [c.strip().replace("**", "") for c in line.strip("|").split("|")][1:]
                return tuple(float(c.replace("$", "").replace(",", "").split()[0]) for c in cells[:4])
        raise AssertionError(f"the runbook has no friction row for ${capital:,.0f}")

    def test_the_weighted_expense_ratio_in_the_prose_is_the_one_the_engine_charges(self):
        self.assertIn(f"{self.weighted:.5%}", _text(),
                      "the runbook quotes an expense ratio that the posted fees do not add up to")

    def test_every_row_of_the_table_recomputes_to_the_cent(self):
        for capital in (5_000.0, 20_000.0, 100_000.0, 250_000.0):
            expense = capital * self.weighted / 12.0
            spread = capital * 0.10 * paper.SPREAD_BPS / 10_000.0
            expense_shown, spread_shown, total_shown, _tickets = self.row(capital)
            self.assertAlmostEqual(expense_shown, expense, delta=0.005, msg=f"at {capital:,.0f}")
            self.assertAlmostEqual(spread_shown, spread, delta=0.005, msg=f"at {capital:,.0f}")
            self.assertAlmostEqual(total_shown, expense + spread, delta=0.01, msg=f"at {capital:,.0f}")

    def test_the_ticket_column_is_two_tickets_because_the_book_has_two_sleeves(self):
        for capital in (5_000.0, 20_000.0, 100_000.0, 250_000.0):
            self.assertAlmostEqual(self.row(capital)[3], 2 * TICKET, delta=0.005, msg=f"at {capital:,.0f}")
        ratio = 2 * TICKET / self.row(5_000.0)[2]   # against the *total*, which is expense plus spread, not their sum
        self.assertGreater(ratio, 20.0, "the runbook's '26×' line has to stay embarrassing or it has been quietly softened")
        self.assertIn("26×", _text())

    def test_the_first_interval_cost_quoted_is_spread_on_the_opening_plus_one_month_of_expense(self):
        first = paper.OPENING * paper.SPREAD_BPS / 10_000.0 + paper.OPENING * self.weighted / 12.0
        self.assertIn(f"${first:,.2f}", _text(), f"the runbook's floor figure is ${first:,.2f} by the engine's own arithmetic")


class TheClaimsAboutTheFirstSealAreTheRulesThemselves(unittest.TestCase):
    def head(self, asof):
        return journal.Entry(index=0, asof=asof, prior_hash="0" * 64, plan="p", plan_posted_on=asof,
                            opening_value=paper.OPENING, cash_arrived=0.0, invested=0.0, days_to_invest=0,
                            fee_paid=0.0, closing_value=paper.OPENING,
                            quotes=(journal.Quote("SPY", 100.0),), holdings=(), violations=(), note="")

    def test_no_deposit_on_the_first_seal_and_one_on_the_second(self):
        self.assertEqual(paper._deposits_due(self.head(dt.date(2026, 9, 4)), dt.date(2026, 9, 30), paper.MONTHLY), 0.0)
        self.assertEqual(paper._deposits_due(self.head(dt.date(2026, 9, 30)), dt.date(2026, 10, 30), paper.MONTHLY),
                         paper.MONTHLY)
        text = _text()
        self.assertIn("no deposit", text)
        self.assertIn("2026-10-30", text)

    def test_the_crossover_is_described_as_a_bracket_because_that_is_what_the_scan_produces(self):
        failing = [c for c in (rc.dominance(TWO_YEARS, cap, 9.95) for cap in rc.CAPITAL_LADDER) if not c["dominates"]]
        winning = [c for c in (rc.dominance(TWO_YEARS, cap, 9.95) for cap in rc.CAPITAL_LADDER) if c["dominates"]]
        self.assertTrue(failing and winning, "the scan no longer turns over, and the runbook needs rewriting, not re-phrasing")
        low, high = max(c["capital"] for c in failing), min(c["capital"] for c in winning)
        self.assertIn(f"between ${low:,.0f} and ${high:,.0f}", _text(),
                      "the runbook must name the bracket the scan produced, not a threshold someone preferred")

    def test_the_status_strings_it_quotes_are_strings_the_tools_print(self):
        sources = {p: (ROOT / "tools" / p).read_text() for p in ("paper.py", "journalctl.py")}
        for status in ("chain intact", "underpowered", "DOMINATED", "intact"):
            self.assertTrue(any(status in text for text in sources.values()), f"nothing prints `{status}`")
            self.assertIn(f"`{status}", _text())

    def test_the_stopping_rule_names_fields_the_ledger_actually_seals(self):
        fields = {f.name for f in dataclasses.fields(journal.Entry)}
        for quoted in re.findall(r"`([a-z_]+)`", _text()):
            if quoted in {"fee_paid", "cash_arrived", "days_to_invest"}:
                self.assertIn(quoted, fields, f"{quoted} is not a sealed field any more")


class TheDocumentStaysItself(unittest.TestCase):
    def test_it_takes_no_position_on_anything_personal(self):
        """The objective is scale-parametric on purpose: the archive prices a procedure, not a person's circumstances, and a
        runbook that started naming wrappers and tax treatments would be making claims nothing in this repository measured."""

        text = _text().lower()
        for forbidden in ("401k", "ira", "roth", "taxable account", "rollover", "withhold", "your broker is", "transfer your"):
            self.assertNotIn(forbidden, text, f"the runbook has started talking about {forbidden}")

    def test_it_names_both_records_and_both_exist(self):
        self.assertTrue((ROOT / "data" / "journal" / "ledger.jsonl").exists())
        books = sorted(p.parent.name for p in (ROOT / "data" / "paper" / "books").glob("*/ledger.jsonl"))
        self.assertGreaterEqual(len(books), 4, books)
        text = _text()
        for book in ("tilt_band", "journalctl.py"):
            self.assertIn(book, text)

    def test_it_forbids_the_one_thing_that_would_make_the_record_worthless(self):
        text = _text().lower()
        for promise in ("append-only", "never rewritten", "ever edited"):
            self.assertIn(promise, text)


if __name__ == "__main__":
    unittest.main()
