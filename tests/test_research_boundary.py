"""Historical evidence labels bind to the family boundary, not chosen prose."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from boring_alpha.config import load_config
from boring_alpha.demo import prepare_ba002_demo
from boring_alpha.research_commands import prepare_research_freeze
from boring_alpha.research_contract import load_contract, validate_contract
from boring_alpha.period_evidence import build_period_evidence
from test_criteria_ba002 import evidence_inputs
from test_research_contract import historical_contract


@pytest.mark.parametrize('period', ['development', 'validation'])
@pytest.mark.parametrize('end', ['2022-01-01', '2022-12-31'])
def test_historical_seen_period_cannot_reach_protected_dates(period, end):
    contract = historical_contract()
    contract['periods'][period]['end'] = end
    with pytest.raises(ValueError, match='cannot label protected dates'):
        validate_contract(contract)


@pytest.mark.parametrize('start', ['2021-12-31', '2022-01-02', '2023-01-01'])
def test_historical_holdout_must_start_at_the_family_boundary(start):
    contract = historical_contract()
    contract['periods']['sealed']['start'] = start
    with pytest.raises(ValueError, match='family protected boundary'):
        validate_contract(contract)


def test_exact_boundary_accepted_and_fictional_dates_remain_unrestricted():
    contract = historical_contract()
    contract['periods']['validation']['end'] = '2021-12-31'
    assert validate_contract(contract)['periods']['sealed']['start'] == '2022-01-01'
    fictional = deepcopy(contract)
    fictional['synthetic'] = True
    fictional['periods']['validation']['end'] = '2023-12-31'
    fictional['periods']['sealed'] = {'start': '2024-01-01', 'end': '2026-08-31', 'status': 'unopened'}
    assert validate_contract(fictional)['synthetic']


def test_prepare_refuses_mislabeled_historical_contract_before_input_capture(tmp_path):
    from dataclasses import replace
    paths = prepare_ba002_demo(tmp_path)
    config = load_config(paths['development'])
    # Only metadata is fictionalized as historical. No real data or journal
    # exists, and numeric parsing/capture is explicitly forbidden.
    historical = replace(config, data=replace(config.data, source='csv', methodology='yahoo-adjusted-v2+dgs3mo-v1'))
    calendar_path = config.research.calendar_path
    import json
    calendar = json.loads(calendar_path.read_text())
    calendar['synthetic'] = False
    calendar_path.write_text(json.dumps(calendar))
    registry = paths['development'].parent / 'evaluation_periods.toml'
    registry.write_text('''[BA-002.development]
start = 2018-01-01
end = 2018-12-31
[BA-002.validation]
start = 2019-01-01
end = 2022-12-31
[BA-002.sealed]
start = 2023-01-01
end = 2026-08-31
''')
    charter = tmp_path / 'fictional-charter.md'
    charter.write_text('Fictional test only')
    with patch('boring_alpha.research_commands.load_config', return_value=historical), patch(
        'boring_alpha.research_commands.capture_inputs', side_effect=AssertionError('captured market inputs')):
        with pytest.raises(ValueError, match='cannot label protected dates'):
            prepare_research_freeze(paths['development'], charter)


def test_archive_contract_reader_enforces_the_same_boundary(tmp_path):
    import json
    contract = historical_contract()
    contract['periods']['validation']['end'] = '2022-01-01'
    path = tmp_path / 'contract.json'
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match='cannot label protected dates'):
        load_contract(path)


def test_loss_deduction_diagnostic_cannot_be_used_as_a_gating_account():
    raw = evidence_inputs()
    for record in raw['tax']['runs']['strategy'].values():
        record['loss_sensitivity'] = {'annual_capacity': 3000}
    with pytest.raises(ValueError, match='diagnostic only'):
        build_period_evidence(**raw)
