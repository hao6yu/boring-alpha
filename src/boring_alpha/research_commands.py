"""Prepare/show/confirm a local freeze. None of these commands runs a strategy."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tomllib

from boring_alpha.config import load_config
from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.profiles import profile_for
from boring_alpha.report import json_text, write_once
from boring_alpha.research_access import capture_inputs, synthetic_input_sha256
from boring_alpha.research_contract import build_contract, canonical_sha256
from boring_alpha.research_freeze import build_freeze, confirm_freeze, freeze_sha256, load_freeze
from boring_alpha.tax.policy import policy_record, policy_sha256


def _periods(config):
    if config.strategy.strategy_id == 'BA-001':
        return {config.evaluation.period: {
            'start': config.backtest.start.isoformat(), 'end': config.backtest.end.isoformat(),
            'status': 'unopened' if config.evaluation.period == 'sealed' else 'seen',
        }}
    raw = tomllib.loads(config.raw_bytes.decode())
    selected = Path(raw['evaluation'].get('periods_path', 'evaluation_periods.toml'))
    path = selected if selected.is_absolute() else config.path.parent / selected
    registry = tomllib.loads(path.read_text(encoding='utf-8'))[config.strategy.strategy_id]
    periods = {}
    for name, bounds in registry.items():
        if name not in ('development', 'validation', 'sealed'):
            raise ValueError('BA-002 registry has an unexpected period')
        start, end = str(bounds['start']), str(bounds['end'])
        if end == 'dataset':
            raise ValueError('research preparation requires a fixed reviewed end date; replace the dataset-ended registry bound before preparing a freeze')
        date.fromisoformat(start), date.fromisoformat(end)
        periods[name] = {'start': start, 'end': end, 'status': 'unopened' if name == 'sealed' else 'seen'}
    return periods


def show_research_freeze(path: Path) -> int:
    record = load_freeze(path)
    identity = record['identity']
    print(f"Research freeze: {path}\nStatus: {record['status']}\nFull identity: {freeze_sha256(record)}")
    print('SYNTHETIC ONLY' if identity['contract']['synthetic'] else 'Historical research proposal; confirmation alone does not reveal data.')
    print(json_text(identity))
    return 0


def _draft_for(config, charter_text):
    profile = profile_for(config.strategy.strategy_id)
    if config.research is None:
        raise ValueError('configure research.calendar_path and freeze_path first')
    if hasattr(profile, 'validate_config'):
        profile.validate_config(config)
    calendar = SessionCalendar.load(config.research.calendar_path)
    synthetic = config.data.source == 'synthetic'
    if calendar.synthetic is not synthetic:
        raise ValueError('calendar and configured data disagree on synthetic provenance')
    if not synthetic:
        from boring_alpha.research_family import canonical_journal_path
        canonical_journal_path(config.strategy.strategy_id)  # Locate only; never initialize during preparation.
    periods = _periods(config)
    if config.strategy.strategy_id == 'BA-002':
        contract = build_contract(
            synthetic=synthetic, periods=periods,
            data_methodology='synthetic-v1' if synthetic else config.data.methodology,
            tax_policy_sha256=policy_sha256(config.tax), tax_policy=policy_record(config.tax),
            calendar_sha256=calendar.sha256, calendar_authority_sha256=calendar.authority_sha256,
        )
        for bounds in periods.values():
            calendar.requirements(date.fromisoformat(bounds['start']), date.fromisoformat(bounds['end']), (9, 12, 15))
    else:
        contract = {
            'strategy_id': config.strategy.strategy_id, 'family_id': 'BA-TREND',
            'strategy_spec_sha256': config.strategy_spec_sha256,
            'synthetic': synthetic, 'periods': periods,
            'tax_policy_sha256': policy_sha256(config.tax) if config.tax else canonical_sha256({'tax_policy': None}),
            'calendar_sha256': calendar.sha256,
            'calendar_authority_sha256': calendar.authority_sha256,
        }
    # Raw-byte provenance only: no numerical market observations are parsed.
    input_digest = synthetic_input_sha256(config) if synthetic else capture_inputs(config).sha256
    return build_freeze(config, contract, input_manifest_sha256=input_digest,
                        charter_text=charter_text)


def prepare_research_freeze(config_path: Path, charter_path: Path) -> int:
    config = load_config(config_path)
    draft = _draft_for(config, charter_path.read_text(encoding='utf-8'))
    path = config.research.freeze_path
    if path.exists():
        existing = load_freeze(path)
        if existing['status'] != 'draft' or freeze_sha256(existing) != freeze_sha256(draft):
            raise ValueError('freeze path already contains a different or confirmed review; choose a new research.freeze_path for the new draft')
    path.parent.mkdir(parents=True, exist_ok=True)
    write_once(path, json_text(draft))
    print('Draft prepared; no execution, confirmation or journal initialization occurred.')
    return show_research_freeze(path)


def confirm_research_freeze(config_path: Path, identity_hash: str, reason: str) -> int:
    config = load_config(config_path)
    if config.research is None:
        raise ValueError('research paths are required')
    draft = load_freeze(config.research.freeze_path)
    if draft['identity']['strategy_spec_sha256'] != config.strategy_spec_sha256:
        raise ValueError('configured behavior differs from the draft; prepare a new draft')
    current = _draft_for(config, draft['identity']['charter_text'])
    if freeze_sha256(current) != freeze_sha256(draft):
        raise ValueError('configured policy, calendar, windows, code or inputs differ from the draft; prepare a new draft')
    confirm_freeze(config.research.freeze_path, expected_sha256=identity_hash, reason=reason)
    if not draft['identity']['contract']['synthetic']:
        from boring_alpha.research_family import canonical_journal_path
        print(f"Research journal: {canonical_journal_path(config.strategy.strategy_id)}")
    print('Freeze confirmed. No strategy was run and no holdout was revealed.')
    return show_research_freeze(config.research.freeze_path)
