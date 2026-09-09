import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from us_funding_history import read_history


def fixture(path, hours, skip=()):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    path.write_text("Date,Funding Rate (%),Annualized Rate (%)\n" + "".join(
        f"{(start + timedelta(hours=h)).isoformat()},0.001,8.76\n"
        for h in range(hours) if h not in skip))
    return path


def test_percent_conversion_and_complete_window(tmp_path):
    out = read_history(fixture(tmp_path / "history.csv", 720))
    assert out["mean_hourly_rate"] == pytest.approx(0.00001)
    assert out["mean_simple_annual_rate_on_constant_notional"] == pytest.approx(0.0876)
    assert out["rolling"]["30"]["complete_overlapping_windows"] == 1
    assert out["rolling"]["30"]["median_rate_sum"] == pytest.approx(0.0072)


def test_gap_is_reported_and_never_zero_filled(tmp_path):
    out = read_history(fixture(tmp_path / "history.csv", 721, skip=(360,)))
    assert out["missing_hours"] == 1
    assert out["rolling"]["30"]["complete_overlapping_windows"] == 0


def test_duplicate_observation_rejected(tmp_path):
    path = fixture(tmp_path / "history.csv", 2)
    path.write_text(path.read_text() + path.read_text().splitlines()[-1] + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_history(path)


def test_unit_mismatch_rejected(tmp_path):
    path = fixture(tmp_path / "history.csv", 2)
    path.write_text(path.read_text().replace("0.001,8.76", "0.1,8.76"))
    with pytest.raises(ValueError, match="unit"):
        read_history(path)
