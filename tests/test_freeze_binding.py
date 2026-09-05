"""Legacy freeze bindings use only temporary fictional records and CSV bytes."""

from dataclasses import replace
from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from boring_alpha.config import _strategy_spec_hash, load_config
from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_access import (
    RunContext, capture_inputs, legacy_research_context, prepare_run,
)
from boring_alpha.research_freeze import build_freeze, confirm_freeze, freeze_sha256
from boring_alpha.tax.policy import policy_sha256

BASELINE = ("a" * 64, "b" * 64)


@pytest.fixture
def frozen_legacy(tmp_path):
    base = load_config(prepare_ba002_demo(tmp_path)["development"])
    calendar = SessionCalendar(
        source="FICTIONAL binding fixture, not an exchange authority", version="1",
        coverage_start=date(2025, 1, 1), coverage_end=date(2025, 1, 31),
        sessions=(date(2025, 1, 2), date(2025, 1, 3)), synthetic=False,
    )
    base.research.calendar_path.write_bytes(calendar.canonical_bytes())
    prices, cash = tmp_path / "prices.csv", tmp_path / "cash.csv"
    prices.write_text("date,symbol,tr_open,tr_close\n2025-01-02,SPY,100,100\n")
    cash.write_text("date,cash_factor\n2025-01-02,1\n")
    # Capture never parses these values. Tax input remains generated demo data,
    # marked explicitly as a temporary fixture, not an actual source snapshot.
    (base.tax.distributions_path.parent / "manifest.json").write_text(json.dumps({
        "methodology": "fictional-binding-v1", "synthetic": False,
    }))
    config = replace(base, strategy=replace(base.strategy, strategy_id="BA-001"),
        data=replace(base.data, source="csv", methodology="fictional-binding-v1", prices_path=prices, cash_path=cash),
        backtest=replace(base.backtest, start=date(2025, 1, 1), end=date(2025, 1, 31)),
        evaluation=replace(base.evaluation, period="sealed", start=date(2025, 1, 1), end=date(2025, 1, 31)))
    config = replace(config, strategy_spec_sha256=_strategy_spec_hash(
        config.strategy, config.portfolio, config.execution, config.data, config.benchmark))
    for stage in ("development", "validation"):
        (config.evaluation.review_dir / f"BA-001-{stage}-fictional.md").write_text("Fictional binding test only.\n")
    contract = {
        "strategy_id": "BA-001", "family_id": "BA-TREND", "synthetic": False,
        "strategy_spec_sha256": config.strategy_spec_sha256,
        "tax_policy_sha256": policy_sha256(config.tax),
        "calendar_sha256": calendar.sha256, "calendar_authority_sha256": calendar.authority_sha256,
        "periods": {"sealed": {"start": "2025-01-01", "end": "2025-01-31", "status": "unopened"}},
    }
    record = build_freeze(config, contract, input_manifest_sha256=capture_inputs(config).sha256,
                          charter_text="Temporary fictional legacy-binding test only",
                          code_sha256=BASELINE[0], evaluator_sha256=BASELINE[0])
    config.research.freeze_path.write_text(json.dumps(record))
    confirmed = confirm_freeze(config.research.freeze_path, expected_sha256=freeze_sha256(record),
                               reason="Fictional binding test only", journal_path=config.research.journal_path)
    return config, confirmed


def test_legacy_accepts_exact_policy_calendar_and_authority_bindings(frozen_legacy):
    config, freeze = frozen_legacy
    with patch("boring_alpha.research_access.capture_inputs", side_effect=AssertionError("context parsed inputs")):
        selected = legacy_research_context(config)
    assert selected.contract == freeze["identity"]["contract"]
    assert selected.approved_contract == selected.contract


@pytest.mark.parametrize("field", ["tax_policy_sha256", "calendar_sha256", "calendar_authority_sha256"])
def test_legacy_checks_each_frozen_binding_independently(frozen_legacy, field):
    config, freeze = frozen_legacy
    # A single changed field isolates each comparison. In particular, changing
    # authority identity must fail even while the complete calendar hash agrees.
    freeze["identity"]["contract"][field] = "f" * 64
    config.research.freeze_path.write_text(json.dumps(freeze))
    with pytest.raises(ValueError, match="calendar or tax policy differs"):
        legacy_research_context(config)


def test_legacy_rejects_a_tax_policy_change_with_unchanged_strategy_spec(frozen_legacy):
    config, _ = frozen_legacy
    changed = replace(config, tax=replace(config.tax, ordinary_rate=0.37))
    assert changed.strategy_spec_sha256 == config.strategy_spec_sha256
    with pytest.raises(ValueError, match="tax policy differs"):
        legacy_research_context(changed)


@pytest.mark.parametrize("change", ["sessions", "authority"])
def test_legacy_rejects_calendar_file_changes_after_confirmation(frozen_legacy, change):
    config, _ = frozen_legacy
    calendar = json.loads(config.research.calendar_path.read_text())
    if change == "sessions":
        calendar["sessions"].pop()
    else:
        calendar["version"] = "new-authority-revision"
    config.research.calendar_path.write_text(json.dumps(calendar))
    with pytest.raises(ValueError, match="calendar or tax policy differs"):
        legacy_research_context(config)


def test_legacy_unseal_reason_also_serves_as_the_first_reveal_reason(frozen_legacy):
    config, _ = frozen_legacy
    reason = "Explicit first reveal of temporary fictional fixture only"
    with patch("boring_alpha.research_access.capture_execution_identity", return_value=BASELINE):
        context = prepare_run(config, unseal_reason=reason)  # No second --reveal.
        try:
            context.attempt.start_access()
            events = json.loads(config.research.journal_path.read_text())["events"]
            assert [event["event"] for event in events] == ["attempted", "access_started"]
            assert events[0]["reveal_reason"] == reason
            assert events[1]["rerun"] is False
        finally:
            context.finish(error="fictional fixture finished without market parsing")


@pytest.mark.parametrize("diagnostic,repair_of", [(True, None), (False, None), (False, "not-derived-from-this")])
def test_run_context_delegates_diagnostic_status_to_attempt(diagnostic, repair_of):
    attempt = SimpleNamespace(revealed_diagnostic=diagnostic, repair_of=repair_of)
    assert RunContext(None, BASELINE, attempt=attempt).revealed_diagnostic is diagnostic
    assert RunContext(None, BASELINE).revealed_diagnostic is False
