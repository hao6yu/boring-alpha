"""Schema-7 BA-002 publication and independently checked archive consumption."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile

from boring_alpha.archived_config import validate_archived_config
from boring_alpha.data.calendar import SessionCalendar
from boring_alpha.data.distributions import FINGERPRINT_VERSION, load_distributions
from boring_alpha.metrics import calculate_metrics
from boring_alpha.period_evidence import IDENTITY_FIELDS, build_period_evidence
from boring_alpha.report import (
    append_provenance, decisions_json, equity_csv,
    json_text, trades_csv, write_once, write_once_bytes,
)
from boring_alpha.research_contract import contract_sha256, load_contract
from boring_alpha.tax.reconcile import validate_replay
from boring_alpha.tax.reconstruct import (
    gunzip_to, initial_cash_from, market_data_from_archive, read_manifest,
    reconstruct_result, require_run_window, run_files, schema7_run_map,
    symbols_from, verify_archive_artifacts,
)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'cannot read evidence artifact {path}: {exc}') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{path} must contain an object')
    return value


def write_ba002_sweep(config, data, sweep, unseal_reason=None):
    from boring_alpha.research_freeze import archival_freeze, freeze_sha256
    from boring_alpha.sweep import _cash_rows, _gzip_bytes, _gzip_csv, _price_rows, _summary, benchmark_description

    identity = sweep.evidence.identity
    execution_code, execution_evaluator = sweep.run_context.verify()
    if identity['code_sha256'] != execution_code or identity['evaluator_sha256'] != execution_evaluator:
        raise ValueError('implementation changed during the sweep; refusing mixed-code evidence')
    freeze = sweep.run_context.research.freeze
    freeze_digest = freeze_sha256(freeze)
    run_identity = {
        **identity, 'config_sha256': hashlib.sha256(config.raw_bytes).hexdigest(),
        'freeze_sha256': freeze_digest,
        'period': config.evaluation.period,
        'start': config.backtest.start.isoformat(), 'end': config.backtest.end.isoformat(),
    }
    sweep_id = hashlib.sha256(json_text(run_identity).encode()).hexdigest()[:16]
    shared = {
        'artifact_schema': 7, 'sweep_id': sweep_id, 'strategy_id': 'BA-002',
        **identity,
        'evaluation_period': config.evaluation.period,
        'backtest_start': config.backtest.start.isoformat(),
        'backtest_end': config.backtest.end.isoformat(),
        'evidence_status': sweep.evidence.evidence_status,
        'account_map': sweep.account_map, 'row_definitions': sweep.row_definitions,
        'freeze_sha256': freeze_digest,
        'repair_of': sweep.run_context.attempt.repair_of if sweep.run_context.attempt else None,
        'revealed_diagnostic': sweep.run_context.revealed_diagnostic,
    }
    criteria = {
        **shared, 'variants': sweep.variants, 'verification': sweep.verification,
        'passed': sweep.outcome.passed,
        'criteria': [asdict(criterion) for criterion in sweep.outcome.criteria],
        'reference_12': sweep.reference_12,
    }
    tax = {**shared, **sweep.tax}
    payloads = {
        'input_prices.csv.gz': _gzip_csv(_price_rows(data)),
        'input_cash.csv.gz': _gzip_csv(_cash_rows(data)),
        'input_distributions.csv.gz': _gzip_bytes(sweep.distributions.canonical_csv()),
        'research_contract.json': json_text(sweep.research_contract).encode(),
        'freeze.json': json_text(archival_freeze(freeze)).encode(),
        'calendar.json': json_text(sweep.calendar_record).encode(),
        'account_map.json': json_text(sweep.account_map).encode(),
        'criteria.json': json_text(criteria).encode(),
        'tax.json': json_text(tax).encode(),
        'summary.md': _summary(config, sweep).encode(),
    }
    for variant, pair in sweep.runs.items():
        for role, result in zip(('strategy', 'benchmark'), pair):
            prefix = f'variants/{variant}/{role}'
            payloads[f'{prefix}_equity.csv'] = equity_csv(result).encode()
            payloads[f'{prefix}_trades.csv'] = trades_csv(result).encode()
            payloads[f'{prefix}_decisions.json'] = decisions_json(result).encode()
    manifest = {
        **shared, 'complete': True,
        'evaluation_start': config.evaluation.start, 'evaluation_end': config.evaluation.end,
        'config_toml': config.raw_bytes.decode(), 'grid': sweep.grid,
        'benchmark': benchmark_description(config), 'data_source': data.source,
        'data_start': data.dates[0], 'data_end': data.dates[-1],
        'distributions_manifest': sweep.tax['distributions_manifest'],
        'run_map': schema7_run_map(), 'warnings': list(data.warnings) + list(sweep.warnings),
        'artifacts_sha256': {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()},
    }
    root = config.report.output_dir / 'BA-002' / 'sweeps' / sweep_id
    root.parent.mkdir(parents=True, exist_ok=True)
    # Serialize publication across processes and publish manifest last. An
    # interrupted writer leaves no completed manifest and cannot classify.
    import fcntl
    with (root.parent / f'.{sweep_id}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        root.mkdir(exist_ok=True)
        for name, content in payloads.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            write_once_bytes(target, content)
        write_once(root / 'manifest.json', json_text(manifest))
        verify_archive_artifacts(root, manifest)
        append_provenance(root, unseal_reason, research_freeze=freeze)
        if sweep.distributions_provenance is not None:
            with (root / 'distributions_provenance.jsonl').open('a') as handle:
                handle.write(json.dumps(sweep.distributions_provenance, sort_keys=True) + '\n')
    return sweep_id, root


def load_ba002_evidence(root: Path, freeze_path: Path | None = None):
    """Reconcile archived accounts and recompute inputs; ignore saved verdicts."""
    manifest = read_manifest(root)
    from boring_alpha.research_freeze import load_freeze, freeze_sha256
    if manifest['strategy_id'] != 'BA-002' or manifest['artifact_schema'] != 7:
        raise ValueError('complete BA-002 schema-7 evidence is required')
    verify_archive_artifacts(root, manifest)
    criteria, tax = _read_json(root / 'criteria.json'), _read_json(root / 'tax.json')
    for payload in (criteria, tax):
        for key in (*IDENTITY_FIELDS, 'artifact_schema', 'sweep_id', 'strategy_id',
                    'evaluation_period', 'backtest_start', 'backtest_end', 'evidence_status',
                    'account_map', 'row_definitions', 'freeze_sha256', 'repair_of', 'revealed_diagnostic'):
            if key not in manifest or payload.get(key) != manifest[key]:
                raise ValueError(f'archived evidence {key} differs from its manifest')
    contract = load_contract(root / 'research_contract.json')
    if contract_sha256(contract) != manifest['contract_sha256']:
        raise ValueError('archived contract identity differs from its manifest')
    validate_archived_config(manifest, contract)
    if tax.get('distributions_manifest') != manifest.get('distributions_manifest'):
        raise ValueError('tax distributions metadata differs from its manifest')
    if not isinstance(tax.get('runs'), dict) or set(tax['runs']) != set(manifest['run_map']):
        raise ValueError('tax evidence does not cover the complete archived account map')
    approved = None
    archived_freeze = load_freeze(root / 'freeze.json')
    frozen = archived_freeze['identity']
    if freeze_sha256(archived_freeze) != manifest.get('freeze_sha256') or frozen['contract'] != contract:
        raise ValueError('archived freeze differs from manifest or contract')
    for key in ('code_sha256', 'evaluator_sha256', 'strategy_spec_sha256'):
        if frozen[key] != manifest[key]:
            raise ValueError(f'archived freeze {key} differs from execution identity')
    if not contract['synthetic']:
        if freeze_path is None:
            raise ValueError('historical BA-002 classification requires --freeze for the independently confirmed record')
        external = load_freeze(freeze_path, require_confirmed=True)
        if freeze_sha256(external) != freeze_sha256(archived_freeze):
            raise ValueError('archived freeze differs from the selected confirmed record')
        approved = external['identity']['contract']
    if manifest.get('revealed_diagnostic') is not False or manifest.get('repair_of') is not None:
        raise ValueError('a repaired revealed run is diagnostic, not new seen-history eligibility evidence')
    calendar = SessionCalendar.load(root / 'calendar.json')
    if calendar.sha256 != manifest['calendar_sha256'] or calendar.authority_sha256 != manifest['calendar_authority_sha256']:
        raise ValueError('archived calendar identity differs from its manifest')
    if calendar.synthetic != contract['synthetic']:
        raise ValueError('calendar and contract disagree on synthetic provenance')
    if _read_json(root / 'account_map.json') != manifest['account_map']:
        raise ValueError('archived account map differs from manifest')
    data = market_data_from_archive(root, manifest)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'distributions.csv'
        gunzip_to(root / 'input_distributions.csv.gz', path)
        table = load_distributions(path, manifest_block=manifest['distributions_manifest'])
    block = manifest['distributions_manifest']
    if (block.get('fingerprint_version') != FINGERPRINT_VERSION
        or table.sha256 != manifest['distributions_sha256']
        or table.sha256 != block.get('sha256') or table.csv_sha256 != block.get('csv_sha256')):
        raise ValueError('archived distributions differ from their canonical identity')
    symbols, cash = symbols_from(manifest), initial_cash_from(manifest)
    start, end = date.fromisoformat(manifest['backtest_start']), date.fromisoformat(manifest['backtest_end'])
    calendar.validate_inputs(data, table, symbols, start, end, horizons=(9, 12, 15), warmup_months=15)
    variants = {row: {} for row in manifest['account_map']}
    reconciled = {}
    for account, equity_path, trades_path in run_files(root, manifest):
        result = reconstruct_result(account, equity_path, trades_path, cash)
        require_run_window(result, data, manifest)
        validate_replay(result, data, cash)
        calendar.validate_output_sessions(tuple(point.date for point in result.equity_curve), start, end)
        reconciled[account] = True
        for row, roles in manifest['account_map'].items():
            for role, account_id in roles.items():
                if account == account_id:
                    # Calculate the gate's drawdown from verified curves, not
                    # a saved pre-tax score. Other metrics remain diagnostics.
                    metrics = calculate_metrics(result, data)
                    variants[row]['strategy' if role == 'strategy' else 'static'] = metrics
    return build_period_evidence(
        variants=variants, tax=tax, account_map=manifest['account_map'],
        row_definitions=manifest['row_definitions'],
        verification={'calendar_complete': True, 'account_reconciliation': reconciled},
        identities={key: manifest[key] for key in IDENTITY_FIELDS},
        contract=contract, approved_contract=approved,
        period=manifest['evaluation_period'], start=start, end=end,
        evidence_status=manifest['evidence_status'], artifact_schema=7,
    )


def write_ba002_backtest(config, data, strategy, benchmark, cash,
                        strategy_metrics, benchmark_metrics, cash_metrics,
                        unseal_reason=None, run_context=None):
    """A primary-rule diagnostic, explicitly not a five-row eligibility sweep."""
    from boring_alpha.research_access import validate_ba002_inputs
    from boring_alpha.research_freeze import archival_freeze, freeze_sha256
    from boring_alpha.sweep import _cash_rows, _distributions_for, _gzip_bytes, _gzip_csv, _price_rows

    if run_context is None:
        raise ValueError('BA-002 publication requires an explicit RunContext')
    table, block, _ = _distributions_for(config, data, run_context)
    context = validate_ba002_inputs(config, data, table, run_context)
    for result in (strategy, benchmark, cash):
        validate_replay(result, data, config.portfolio.initial_cash)
        context.calendar.validate_output_sessions(tuple(p.date for p in result.equity_curve),
                                                 config.backtest.start, config.backtest.end)
    execution_code, execution_evaluator = run_context.verify()
    identity = {
        'config_sha256': hashlib.sha256(config.raw_bytes).hexdigest(),
        'data_sha256': data.fingerprint(), 'code_sha256': execution_code,
        'evaluator_sha256': execution_evaluator,
        'freeze_sha256': freeze_sha256(context.freeze),
        'contract_sha256': contract_sha256(context.contract),
        'calendar_sha256': context.calendar.sha256, 'distributions_sha256': table.sha256,
    }
    run_id = hashlib.sha256(json_text(identity).encode()).hexdigest()[:16]
    payloads = {
        'decisions.json': decisions_json(strategy).encode(),
        'metrics.json': json_text({'strategy': strategy_metrics, 'static_benchmark': benchmark_metrics,
                                  'cash_benchmark': cash_metrics}).encode(),
        'research_contract.json': json_text(context.contract).encode(),
        'freeze.json': json_text(archival_freeze(context.freeze)).encode(),
        'calendar.json': context.calendar.canonical_bytes(),
        'input_prices.csv.gz': _gzip_csv(_price_rows(data)),
        'input_cash.csv.gz': _gzip_csv(_cash_rows(data)),
        'input_distributions.csv.gz': _gzip_bytes(table.canonical_csv()),
    }
    for name, result in (('strategy', strategy), ('benchmark', benchmark), ('cash', cash)):
        payloads[f'{name}_equity.csv'] = equity_csv(result).encode()
        payloads[f'{name}_trades.csv'] = trades_csv(result).encode()
    root = config.report.output_dir / 'BA-002' / run_id
    root.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        write_once_bytes(root / name, content)
    write_once(root / 'manifest.json', json_text({
        'artifact_schema': 7, 'kind': 'single-backtest-diagnostic', 'complete': True,
        'run_id': run_id, 'strategy_id': 'BA-002', **identity,
        'config_toml': config.raw_bytes.decode(), 'distributions_manifest': block,
        'evaluation_period': config.evaluation.period,
        'backtest_start': config.backtest.start, 'backtest_end': config.backtest.end,
        'evidence_status': 'synthetic' if context.contract['synthetic'] else 'diagnostic-only',
        'repair_of': run_context.attempt.repair_of if run_context.attempt else None,
        'revealed_diagnostic': run_context.revealed_diagnostic,
        'warning': 'Pre-tax single-rule diagnostic; use the complete sweep for after-tax eligibility.',
        'artifacts_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()},
    }))
    append_provenance(root, unseal_reason, research_freeze=context.freeze)
    return run_id, root
