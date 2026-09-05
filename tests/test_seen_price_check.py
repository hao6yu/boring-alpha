"""Fictional, offline checks for the bounded conditional source diagnostic."""

from datetime import date
import hashlib
import io
import zipfile

import pytest

from tools import check_ba002_seen_prices as diagnostic


def test_local_numeric_fields_outside_both_bounds_are_excluded():
    raw = (
        b"date,symbol,tr_open,tr_close\n"
        b"2006-02-27,SPY,INVALID_PRIOR_OPEN,INVALID_PRIOR_CLOSE\n"
        b"2006-02-28,SPY,1,2\n"
        b"2021-12-31,SPY,3,4\n"
        b"2022-01-03,SPY,INVALID_FUTURE_OPEN,INVALID_FUTURE_CLOSE\n"
    )
    assert diagnostic.bounded_local_bytes(
        raw, ["date", "symbol", "tr_open", "tr_close"]
    ) == (
        b"date,symbol,tr_open,tr_close\n"
        b"2006-02-28,SPY,1,2\n"
        b"2021-12-31,SPY,3,4\n"
    )


def test_invalid_date_cannot_be_assumed_outside_the_boundary():
    with pytest.raises(ValueError, match="invalid date"):
        diagnostic.bounded_local_bytes(
            b"date,cash_factor\nUNKNOWN_DATE,INVALID_NUMBER\n",
            ["date", "cash_factor"],
        )


def fictional_zip(symbol):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            f"{symbol.lower()}.csv",
            "19980106 00:00,INVALID_PRIOR_FIELDS\n"
            "20080723 00:00,1200000,1260000,1170000,1230000,1\n"
            "20080724 00:00,400000,420000,390000,410000,1\n"
            "20220103 00:00,INVALID_FUTURE_FIELDS\n",
        )
    return output.getvalue()


@pytest.mark.parametrize("symbol", ["SPY", "IWM", "EEM"])
def test_qc_date_first_scaling_and_only_eem_pre_split_adjustment(monkeypatch, symbol):
    raw = fictional_zip(symbol)
    expected_hash = hashlib.sha256(raw).hexdigest()
    monkeypatch.setitem(diagnostic.EXPECTED_ZIP_SHA256, symbol, expected_hash)
    monkeypatch.setattr(diagnostic, "tls_context", lambda: object())

    def fetch(request, *, timeout, context):
        assert request.full_url == (
            f"https://raw.githubusercontent.com/QuantConnect/Lean/{diagnostic.COMMIT}"
            f"/Data/equity/usa/daily/{symbol.lower()}.zip"
        )
        assert timeout == 45
        return io.BytesIO(raw)

    monkeypatch.setattr(diagnostic, "urlopen", fetch)
    rows, source = diagnostic.fetch_qc(symbol)
    assert set(rows) == {date(2008, 7, 23), date(2008, 7, 24)}
    assert rows[date(2008, 7, 23)] == (
        {"open": 40.0, "close": 41.0} if symbol == "EEM"
        else {"open": 120.0, "close": 123.0}
    )
    assert rows[date(2008, 7, 24)] == {"open": 40.0, "close": 41.0}
    assert source["zip_sha256"] == expected_hash
    assert source["interpreted_rows"] == 2


def test_qc_pinned_hash_mismatch_refuses_before_archive_interpretation(monkeypatch):
    monkeypatch.setattr(diagnostic, "tls_context", lambda: object())
    monkeypatch.setattr(
        diagnostic, "urlopen", lambda *args, **kwargs: io.BytesIO(fictional_zip("SPY"))
    )
    monkeypatch.setitem(diagnostic.EXPECTED_ZIP_SHA256, "SPY", "0" * 64)
    with pytest.raises(ValueError, match="pinned ZIP hash mismatch"):
        diagnostic.fetch_qc("SPY")


@pytest.mark.parametrize("qc,yahoo,exceeds", [
    (10.0, 10.02, False),
    (10.0, 9.98, False),
    (10.0, 10.0201, True),
    (10.0, 9.9799, True),
    (100.0, 100.05, False),
    (100.0, 99.95, False),
    (100.0, 100.0501, True),
    (100.0, 99.9499, True),
])
def test_fixed_tolerance_boundary(qc, yahoo, exceeds):
    result = diagnostic.compare(date(2010, 1, 4), "SPY", "close", qc, yahoo)
    assert result["allowed_difference_dollars"] == max(0.02, qc * 0.0005)
    assert result["exceeds_tolerance"] is exceeds
