"""Past-only classifications and observable-time accounting for the proxy screen."""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import us_spread_conditional as conditional


def policy():
    p = json.loads(conditional.POLICY_FILE.read_text())
    p.update(lookback_hours=8, minimum_past_paired_bars=4, holding_hours=2, nonoverlap_spacing_hours=3)
    return p


def rows(gaps, prices=None):
    prices = prices or [100] * len(gaps)
    return [{"start": i * 3600, "bucket_end": (i + 1) * 3600,
             "perp_close": prices[i], "dated_close": prices[i] + gap,
             "gap_usd_per_underlying": gap, "gap_bps_of_perp": 10000 * gap / prices[i],
             "both_have_reported_volume": True} for i, gap in enumerate(gaps)]


def test_current_outlier_does_not_change_its_own_threshold():
    data = rows([1, 1, 1, 1, 10, 1, 1, 1])
    signal = conditional.classify(data, policy())[0]
    assert signal["signal_start"] == 4 * 3600
    assert signal["past_p90_bps"] == 100
    assert signal["group"] == "high"


def test_appending_future_prices_cannot_change_prior_classifications_or_slots():
    data = rows([1, 1, 1, 1, 2, 3, 1, 4, 2, 1, 2, 4])
    original = conditional.classify(data[:8], policy())
    changed = deepcopy(data)
    for r in changed[8:]:
        r["gap_bps_of_perp"] = 100000
    assert conditional.classify(changed, policy())[:len(original)] == original


def test_dollar_gap_unchanged_is_zero_pnl_despite_different_price_ratio():
    # Signal at4, entry at5, exit7. Both dollar gaps are10, despite perp100->200.
    data = rows([10] * 9, [100] * 7 + [200, 200])
    p = policy()
    out = conditional.attach_outcomes(conditional.classify(data, p), data, 9 * 3600, p)
    assert out[0]["delayed_narrowing_bps"] == 0
    assert data[5]["gap_bps_of_perp"] - data[7]["gap_bps_of_perp"] == 500


def test_snapback_before_delayed_entry_is_not_tradable_response():
    data = rows([1, 1, 1, 1, 3, 1, 1, 1, 1])
    p = policy()
    r = conditional.attach_outcomes(conditional.classify(data, p), data, 9 * 3600, p)[0]
    assert r["signal_available_at"] == 5 * 3600
    assert r["entry_start"] + 3600 == 6 * 3600
    assert r["signal_to_entry_narrowing_bps"] == 200
    assert r["delayed_narrowing_bps"] == 0


def test_missing_future_entry_and_exit_preserve_signal_and_selection():
    data = rows([1, 1, 1, 1, 3, 1, 1, 1, 1])
    p = policy()
    signals = conditional.classify(data, p)
    out = conditional.attach_outcomes(signals, [r for r in data if r["start"] not in (5 * 3600, 7 * 3600)], 9 * 3600, p)
    assert out[0]["group"] == signals[0]["group"] == "high"
    assert out[0]["nonoverlap_slot"] == signals[0]["nonoverlap_slot"]
    assert out[0]["outcome_state"] == "MISSING_ENDPOINT"
    assert out[0]["missing_entry"] and out[0]["missing_exit"]
    assert len(out) == len(signals)


def test_missing_interior_does_not_erase_endpoint_or_imply_complete_path():
    data = rows([1, 1, 1, 1, 3, 2, 2, 1, 1])
    p = policy()
    signal = conditional.classify(data, p)[0]
    out = conditional.attach_outcomes([signal], [r for r in data if r["start"] != 6 * 3600], 9 * 3600, p)[0]
    assert out["outcome_state"] == "OBSERVED_ENDPOINTS"
    assert out["missing_path_bars"] == 1
    assert out["delayed_narrowing_bps"] == 100


def test_preentry_snapback_does_not_depend_on_later_exit_availability():
    data = rows([1, 1, 1, 1, 3, 1, 1])
    p = policy()
    out = conditional.attach_outcomes(conditional.classify(data, p), data, 7 * 3600, p)
    assert out[0]["outcome_state"] == "RIGHT_CENSORED"
    assert out[0]["signal_to_entry_narrowing_bps"] == 200
    summary = conditional.describe(out[:1])
    assert summary["signal_to_entry_narrowing_bps"]["count"] == 1
    assert summary["delayed_narrowing_bps"] is None


def test_nonoverlap_slots_are_chosen_across_groups_before_outcomes():
    p = policy()
    data = rows([1, 1, 1, 1, 2, 3, 1, 4, 2, 1, 2, 4])
    signals = conditional.classify(data, p)
    assert [s["signal_start"] // 3600 for s in signals if s["nonoverlap_slot"]] == [4, 7, 10]
    out = conditional.attach_outcomes(signals, data, 12 * 3600, p)
    assert out[-1]["right_censored"]


def test_zero_volume_and_stale_past_cannot_satisfy_history_floor():
    data = rows([1] * 8)
    for r in data[:4]:
        r["both_have_reported_volume"] = False
    assert conditional.classify(data, policy()) == []
    data = rows([1] * 8)
    for r in data[4:]:
        r["start"] += 100 * 3600
    assert conditional.classify(data, policy()) == []


def test_reference_cost_is_labeled_and_uses_cash_on_full_account():
    p = policy()
    p["holding_hours"] = 24
    quote = {"fills": {leg: {"asks": 100, "bids": 100} for leg in ("perp", "dated")}}
    quote_policy = {"fee_cases": [{"name": "base_assumed", "perp_bps": 5, "dated_bps": 5,
                                  "perp_min_usd": 0, "dated_min_usd": 0}]}
    r = {"entry_perp_close": 100, "entry_dated_close": 100, "delayed_narrowing_bps": 30}
    c = conditional.cost_reference(r, quote, quote_policy, 1, p)[0]
    # 20 bps fees + 10%/365 funding + (5000/2500)*4%/365 cash, in bps.
    assert c["reference_hurdle_bps"] == pytest.approx(20 + 1000 / 365 + 800 / 365)
    assert c["price_change_exceeds_reference_hurdle"] is True


def test_nearest_rank_and_duplicate_times():
    assert conditional.percentile(list(range(1, 11)), 0.9) == 9
    data = rows([1] * 8)
    with pytest.raises(ValueError, match="duplicate"):
        conditional.classify(data + [data[-1]], policy())
