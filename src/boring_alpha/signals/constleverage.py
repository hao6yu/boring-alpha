"""A constant-leverage policy: the one plan in this repository that still beats the index under honest
accounting, implemented as something the forward book can actually run.

Round 29 priced a **constant** 1.25× book at +1.63%/yr over the pinned comparator under a real brokerage sweep
and a posted desk rate, and round 30 stress-tested that loan against a floating rate. It is the only positive
row in `tools/action_ledger.py` that is not a rate the broker is simply not paying — and, unlike the vol-target
signal the forward book has been tracking since day one, it contains no forecast whatsoever. The forward book is
therefore currently observing a policy that every measurement in this project says is *negative* under
account-faithful costs, while the only policy that measures *positive* runs unobserved.

That asymmetry is the reason this module exists. It is deliberately not a signal:

  * The weight is a constant. There is no lookback, no gate, no band, no review cadence — the policy emits the
    same number on every session, so the trade it forces is the *rebalance back to target*, which is the only
    cost this plan pays by choice.
  * Because the weight never changes, anything the forward book records about it is attributable to the market
    and the financing, not to a model decision. That is the point: the plan's whole claim is `leverage ×
    (equity return − borrow rate)`, and a forward record of a constant weight measures that expression without
    any signal behaviour muddying the arithmetic.
  * It is a **loan**. The policy has no opinion about drawdown, and it will be exactly 1.25× through the month
    that produces a −60% drawdown, which round 30 measured as the binding risk. Anyone reading the forward
    record must read the financing line beside the return line, because the return line alone cannot tell this
    plan from simply holding more of the index.

Sizing is a parameter, not a hard-coded belief: `weight` is set at init and pinned into the book's config, so a
forward test of 1.25× and one of 1.10× are two separate pre-registrations rather than one number quietly
re-tuned. The default 1.25 is round 11's and round 29's figure, chosen before this module was written.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConstantLeveragePolicy:
    """Hold `weight` of one sleeve, financed at whatever the account is charged for the rest."""

    weight: float = 1.25
    sleeve: str = "SPY"
    name: str = "constant-leverage"
    tolerance: float = 1e-12

    def __post_init__(self) -> None:
        if self.weight < 1.0:
            raise ValueError(
                f"a constant book under 1.00x is not this policy: it holds cash, which is round 24's decision, "
                f"not a leverage decision. Use {self.weight:.2f}x only via the cash switch."
            )
        if self.weight > 2.0:
            raise ValueError(
                f"{self.weight:.2f}x is outside anything measured here: round 30's stress put a 2.00x book's "
                f"binding-window drawdown past −70%, and Reg T maintenance binds long before that."
            )

    def weights(self, closes=None, returns=None):
        """`weight` every session, charged exactly as any other policy charges its trades.

        Matching `VolTargetPolicy.weights` is the whole job here, including the parts that look incidental: the
        first session reports turnover equal to the weight, because funding a book from cash *is* a trade and
        must be charged as one — a constant-weight policy that reported zero turnover would show this plan's
        entry for free and would make its forward return incomparable to the vol-target book's. After day one the
        weight never moves, so turnover is zero, and the `rebalance_band` field exists only to record that a
        constant needs no band: it can never breach one.
        """

        sessions = len(closes) if closes is not None else 1
        out: list[tuple[float | None, float]] = []
        for position in range(sessions):
            out.append((self.weight, self.weight if position == 0 else 0.0))
        return out

    def target_weight(self, closes=None, returns=None, asof=None) -> float:
        return self.weight

    def describe(self) -> dict:
        """What gets pinned into the book's config, so the forward record says what it promised."""

        return {"model_key": "constant_leverage", "weight": self.weight, "sleeve": self.sleeve,
                "financing": "posted desk rate, floating at the desk's spread over the bill curve",
                "contains_no_forecast": True,
                "measured_excess": "+1.63%/yr full record, -1.49%/yr in 2007-09, max drawdown -59.7% (rounds 29-30)"}
