"""Calibrate the instrument, then pin the calibration.

`journal.verdict` grants a skill claim the moment 24 entries exist and the gap is positive by any amount. That is a protocol,
not a statistical test, and a protocol that cannot be moved after the anchor must at least be *measured* — which is what
`tools/skill_null.py` does, by running the real `verdict()` over fabricated entries on paths where no skill is available
anywhere. This file holds that measurement to its properties, so the tool cannot rot into a number that flatters the book it
sits beside, and it holds the runbook's quoted figures to the tool's own output.

`--paths` is modest here and generous in the tool's defaults: a rate estimated from a few hundred paths carries sampling error,
and every assertion below is a property that error cannot flip.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import power_horizon as ph                                   # noqa: E402
import skill_null as sn                                      # noqa: E402
from boring_alpha import journal                             # noqa: E402

PATHS = 400
RUNBOOK = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")


def table(paths: int = PATHS, horizons=(24, 36, 60), seed: int = sn.DEFAULT_SEED, commission: float = 0.0,
          band: float | None = None) -> dict:
    argv = ["skill_null.py", "--paths", str(paths), "--seed", str(seed), "--commission", str(commission),
            "--horizons", ",".join(str(h) for h in horizons), "--json"]
    if band is not None:
        argv += ["--band", str(band)]
    saved, sys.argv = sys.argv, argv
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = sn.main()
    finally:
        sys.argv = saved
    assert code == 0
    return json.loads(out.getvalue())


def cell(rows: list, mode: str, horizon: int) -> dict:
    return next(r for r in rows if r["mode"] == mode and r["horizon"] == horizon)


class WhatTheInstrumentCannotSay(unittest.TestCase):
    def test_below_the_pinned_floor_it_prints_nothing_rather_than_zero(self):
        rows = table(horizons=(12,))["rows"]
        for r in rows:
            self.assertIsNone(r["beat"], f"{r['mode']} claimed a rate below the protocol's floor")
            self.assertIn(str(journal.MIN_ENTRIES_FOR_SKILL_VERDICT), r["withheld"])

    def test_the_floor_it_defers_to_is_the_one_the_pinned_module_declares(self):
        rows = table(horizons=(journal.MIN_ENTRIES_FOR_SKILL_VERDICT,))["rows"]
        for r in rows:
            self.assertIsNotNone(r["beat"], "the instrument went silent at exactly its own floor")


class WhatTheInstrumentCanSay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = table()
        cls.rows = cls.data["rows"]

    def test_a_beat_on_a_path_with_no_skill_is_common_at_the_floor_and_rare_at_60_months(self):
        for mode in ("hurdle-fee-matched", "hurdle-as-pinned"):
            rates = [cell(self.rows, mode, h)["beat"] for h in (24, 36, 60)]
            self.assertGreater(rates[0], 0.05, f"{mode}: the null is being reported as impossibly strict")
            self.assertLess(rates[0], 0.45, f"{mode}: a 45%+ false-positive rate would mean the study is measuring nothing")
            self.assertGreater(rates[0], rates[1], f"{mode}: the floor should get stricter with length, not looser")
            self.assertGreater(rates[1], rates[2], f"{mode}: the ordering of 36 and 60 months inverted")

    def test_the_median_gap_is_negative_because_the_book_pays_to_enter_and_the_comparator_does_not(self):
        """The protocol is generous to the bar by construction, so a no-skill book sits behind it. If this ever reads positive,
        the study has stopped being a null and someone has quietly given the book an advantage inside `run_once`."""

        for mode in ("hurdle-fee-matched", "hurdle-as-pinned"):
            for horizon in (24, 36, 60):
                self.assertLess(cell(self.rows, mode, horizon)["median_bps"], 0.0, f"{mode} at {horizon} months")

    def test_the_margin_that_holds_the_false_positive_rate_to_five_percent_shrinks_with_length(self):
        margins = [cell(self.rows, "hurdle-as-pinned", h)["margin_bps_p95"] for h in (24, 36, 60)]
        self.assertGreater(margins[0], 0.0)
        self.assertGreater(margins[0], margins[1], margins)
        self.assertGreaterEqual(margins[1], margins[2], margins)

    def test_the_archive_its_own_drift_is_the_difference_between_the_null_rows_and_the_replay_rows(self):
        for horizon in (24, 36, 60):
            self.assertGreater(cell(self.rows, "replay", horizon)["beat"], cell(self.rows, "hurdle-as-pinned", horizon)["beat"],
                               f"at {horizon} months the replay should carry the archive's drift and the null should not")

    def test_a_per_ticket_broker_lowers_the_books_odds_under_the_null(self):
        """A cost the book pays and the comparator never pays can only push the gap down. This is the same asymmetry that makes
        round 86's dominance table flip at small size, seen from the other end."""

        free = cell(table(horizons=(24,))["rows"], "hurdle-as-pinned", 24)["beat"]
        priced = cell(table(horizons=(24,), commission=9.95)["rows"], "hurdle-as-pinned", 24)["beat"]
        self.assertLess(priced, free, f"a 9.95 ticket moved the null from {free:.1%} to {priced:.1%}")


class TheStudyIsReproducible(unittest.TestCase):
    def test_the_material_is_the_archives_own_months_and_the_seed_is_all_the_rest(self):
        self.assertEqual(table()["archive_months"], len(ph.month_closes(None)) - 1,
                         "a bootstrap that is not the archive minus its first link is a different study")
        first, again = table(paths=120), table(paths=120)
        self.assertEqual(first["rows"], again["rows"], "the same seed produced a different table")
        self.assertNotEqual(first["rows"], table(paths=120, seed=sn.DEFAULT_SEED + 7)["rows"])

    def test_a_null_of_one_index_cannot_breach_a_band_because_nothing_ever_drifts(self):
        """A property of the construction rather than of the market: on a single index the two sleeves move by the same factor,
        the weights stay where they were put, and `--band` therefore changes nothing. If this ever fails, `same_index` has
        stopped meaning what it says and the null rows have been quietly measuring rebalancing instead of nothing."""

        wide = cell(table(horizons=(24,), band=5.0)["rows"], "hurdle-as-pinned", 24)["beat"]
        monthly = cell(table(horizons=(24,), band=0.0)["rows"], "hurdle-as-pinned", 24)["beat"]
        self.assertEqual(wide, monthly)

    def test_the_band_does_bite_when_the_sleeves_are_allowed_to_move_apart(self):
        """The counterpart, in the `replay` rows, where the archive's own two-fund dispersion is present."""

        wide = cell(table(horizons=(24,), band=5.0)["rows"], "replay", 24)["beat"]
        monthly = cell(table(horizons=(24,), band=0.0)["rows"], "replay", 24)["beat"]
        self.assertNotAlmostEqual(wide, monthly, delta=1e-9,
                                  msg="the band flag is ignored everywhere, so the table's header is a lie")


class TheRunbookStillMatchesTheTool(unittest.TestCase):
    """The runbook quotes two figures from this study. Quotation without checking is how documentation rots."""

    def test_the_quoted_false_positive_rate_and_margin_are_what_the_pinned_seed_still_produces(self):
        rate = float(re.search(r"prints `beat` \*\*(\d+\.\d)%\*\*", RUNBOOK).group(1)) / 100.0
        margin = float(re.search(r"clearing \*\*\+(\d+) bps\*\*", RUNBOOK).group(1))
        row = cell(table(paths=600, horizons=(24,))["rows"], "hurdle-as-pinned", 24)  # the published run's size
        self.assertAlmostEqual(rate, row["beat"], delta=0.005)
        self.assertAlmostEqual(margin, round(row["margin_bps_p95"]), delta=2)

    def test_the_runbook_points_at_the_tool_rather_than_at_itself(self):
        self.assertIn("skill_null.py", RUNBOOK)


if __name__ == "__main__":
    unittest.main()
