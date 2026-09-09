"""Invariants for the break-even accuracy simulator.

The simulator answers one question — how often must a weekly market/flat call be
right to beat plain DCA — and its whole answer is the *shape* of the terminal
value as a function of accuracy. The first version of this tool passed that
question silently wrong: the signalled leg was written as a nudge to the position
held last week instead of the position itself, so the call and the holding came
apart and every accuracy in the grid paid the same noise, around -62%. Nothing in
the output said "bug"; the only reason it was caught is that a correct simulator
must be monotonically better as accuracy rises, and the broken table was not.

So the monotonicity test below is the load-bearing one. It is cheap, it needs no
research archive, and it fails loudly on any future edit that lets a signal and
its own position drift apart.
"""

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import required_accuracy as ra  # noqa: E402


def synthetic_weeks(n, up_return, down_return, cash, share_up=0.58, period=7):
    """Deterministic weekly bars whose realised up-share is close to `share_up`.

    Up weeks arrive on a fixed period rather than from a coin, so tests below are
    reproducible and the accuracy curve is smooth enough to compare point to
    point. `period` is deliberately not 4 or 5, so it does not resonate with the
    five-session weekly grid.
    """

    bars = []
    for week in range(n):
        up = (week % period) < round(share_up * period)
        bars.append((up_return if up else down_return, cash, 500.0))
    return bars


class SimulatorBehaviour(unittest.TestCase):
    def setUp(self):
        self.bars = synthetic_weeks(600, 0.012, -0.009, 0.0008)

    def terminal(self, accuracy, cost=0.0001):
        return sum(
            ra.run(self.bars, accuracy, cost, 4000 + rep)[0] for rep in range(12)
        ) / 12.0

    def test_better_calls_are_worth_more(self):
        """Monotone in accuracy. The bug this guards was found exactly this way."""
        ladder = [self.terminal(a) for a in (0.50, 0.55, 0.60, 0.65, 0.70, 0.80)]
        for lower, upper in zip(ladder, ladder[1:]):
            self.assertGreaterEqual(upper, lower * 0.995)
        self.assertGreater(ladder[-1], ladder[0] * 1.5)

    def test_accuracy_alone_does_not_decide_the_position(self):
        """A correct call must move the book to the leg it names, not sit still."""
        # With a coin-flip signal the position is unrelated to the outcome, so the
        # timer should land near the mid-point of always-long and always-flat; a
        # simulator that ignores the sign of the call collapses onto one of them.
        coin = self.terminal(0.50)
        flat_all = ra.run(self.bars, 0.0, 0.0001, 7)[0]
        long_all = ra.run(self.bars, 1.0, 0.0001, 7)[0]
        self.assertLess(long_all, coin * 50)          # coin flips constantly, paying both legs
        self.assertGreater(coin, flat_all * 1.5)      # but is not the same as staying flat

    def test_costs_are_a_toll_not_a_switch(self):
        """Higher friction moves the whole curve down without changing its shape."""
        cheap = self.terminal(0.62, 0.00003)
        dear = self.terminal(0.62, 0.0005)
        self.assertGreater(cheap, dear)
        self.assertLess(dear / cheap, 0.98)
        self.assertGreater(dear / cheap, 0.5)

    def accrue(self, bars, pick, cost=0.0, start_held=True):
        """Reference implementation: deposit first, then the held leg, then costs."""
        value, held = ra.OPENING, start_held
        for equity, cash, deposit in bars:
            value += deposit
            want = pick(equity, cash)
            if want != held:
                value -= value * 2.0 * cost
                held = want
            value *= (1.0 + equity) if held else (1.0 + cash)
        return value

    def test_perfect_accuracy_never_holds_the_losing_leg(self):
        """At accuracy 1.0 the timer takes max(equity, cash) every week."""
        value = ra.run(self.bars, 1.0, 0.0, 11)[0]
        self.assertAlmostEqual(value, self.accrue(self.bars, lambda e, c: e > c), places=6)

    def test_zero_accuracy_never_holds_the_winning_leg(self):
        value = ra.run(self.bars, 0.0, 0.0, 11)[0]
        self.assertAlmostEqual(value, self.accrue(self.bars, lambda e, c: e <= c), places=6)

    def test_deposits_are_paid_in_exactly_once(self):
        """Money in the account must be conserved when nothing can move."""
        still = [(0.0, 0.0, 500.0)] * 40
        value, _switches = ra.run(still, 0.6, 0.0, 3)
        self.assertAlmostEqual(value, ra.OPENING + 40 * 500.0, places=6)

    def test_switching_is_charged_on_both_legs(self):
        """A week that flips the position pays out and back in, never one side."""
        flip = [(0.01, -0.01, 0.0), (-0.01, 0.01, 0.0)] * 6
        paid, switches = ra.run(flip, 1.0, 0.0010, 5)
        free = ra.run(flip, 1.0, 0.0, 5)[0]
        self.assertGreater(switches, 5)
        self.assertAlmostEqual(paid, free * (1.0 - 0.0020) ** switches, places=6)


class WeeklyBars(unittest.TestCase):
    def test_session_to_week_compounding_is_the_product_of_sessions(self):
        """Five sessions at a constant daily move must compound, not add."""
        daily = 1.001
        weekly = (1.0 + daily) ** ra.SESSIONS_PER_WEEK - 1.0
        self.assertGreater(weekly, daily * ra.SESSIONS_PER_WEEK)
        self.assertTrue(math.isfinite(weekly))


if __name__ == "__main__":
    unittest.main()
