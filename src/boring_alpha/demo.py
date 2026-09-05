"""Create a self-contained fictional BA-002 laboratory, never market evidence.

Run ``python -m boring_alpha.demo DIRECTORY`` and use the printed commands.
No network, exchange data, approval records or research-state ledger is used.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from boring_alpha.config import load_config
from boring_alpha.data.synthetic import generate_synthetic_market_data
from boring_alpha.report import json_text, write_once
from boring_alpha.tax.policy import policy_record, policy_sha256

SYMBOLS = ('SPY', 'IWM', 'EFA', 'EEM', 'IEF', 'TLT', 'GLD', 'DBC')
START, END = date(2016, 9, 1), date(2019, 12, 31)


def prepare_ba002_demo(root: Path) -> dict[str, Path]:
    """Write deterministic, write-once fixture inputs under an explicit root."""
    from boring_alpha.data.calendar import SessionCalendar
    from boring_alpha.research_contract import build_contract
    from boring_alpha.research_freeze import build_freeze
    from boring_alpha.research_access import synthetic_input_sha256
    from boring_alpha.research_contract import canonical_sha256

    root = root.resolve()
    for name in ('configs', 'data', 'research', 'reviews'):
        (root / name).mkdir(parents=True, exist_ok=True)
    # This deliberately fictional calendar is defined independently of prices.
    # It includes every weekday, even real-world holidays. It is NOT an exchange
    # calendar and cannot authorize a historical market-data run.
    sessions = []
    day = START
    while day <= END:
        if day.weekday() < 5:
            sessions.append(day.isoformat())
        day += timedelta(days=1)
    calendar_record = {
        'schema_version': 1, 'source': 'fictional weekday-only demo, NOT an exchange',
        'version': '1', 'coverage_start': START.isoformat(),
        'coverage_end': END.isoformat(), 'sessions': sessions, 'synthetic': True,
    }
    calendar = SessionCalendar.from_dict(calendar_record)
    write_once(root / 'research/calendar.json', json_text(calendar_record))
    periods = {
        'development': {'start': '2018-01-01', 'end': '2018-12-31', 'status': 'seen'},
        'validation': {'start': '2019-01-01', 'end': '2019-12-31', 'status': 'seen'},
    }
    write_once(root / 'configs/evaluation_periods.toml', '\n'.join(
        f'[BA-002.{key}]\nstart = {value["start"]}\nend = {value["end"]}\n'
        for key, value in periods.items()
    ))
    write_once(root / 'reviews/BA-002-development-synthetic.md',
               '# Synthetic fixture only\nNo historical development review or run approval.\n')
    policy_text = '''[tax]
distributions_path = "../data/distributions_daily.csv"
ordinary_rate = 0.35
long_term_rate = 0.20
collectibles_rate = 0.28
qualified_fraction_low = 0.50
[tax.qualified_fraction]
SPY = 0.95
IWM = 0.71
EFA = 0.95
EEM = 0.61
IEF = 0.0
TLT = 0.0
GLD = 0.0
DBC = 0.0
[tax.gains_class]
SPY = "standard"
IWM = "standard"
EFA = "standard"
EEM = "standard"
IEF = "standard"
TLT = "standard"
GLD = "collectibles"
DBC = "commodity_pool"
'''
    paths = {'policy': root / 'configs/tax_policy.toml'}
    write_once(paths['policy'], policy_text)
    for period, bounds in periods.items():
        text = f'''[strategy]
id = "BA-002"
name = "BA-002 Multi-Horizon Trend (SYNTHETIC)"
symbols = ["SPY", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC"]
lookback_months = 15
horizons = [9, 12, 15]
warmup_months = 15
sleeve_weight = 0.125
[portfolio]
initial_cash = 100000
[execution]
cost_bps = 10
[data]
source = "synthetic"
start = "{START}"
end = "{END}"
seed = 21
annual_cash_rate = 0.02
[backtest]
start = "{bounds['start']}"
end = "{bounds['end']}"
[evaluation]
period = "{period}"
review_dir = "../reviews"
[benchmark]
exposure = 0.60
rebalance = "annual"
[report]
output_dir = "../experiments"
[research]
calendar_path = "../research/calendar.json"
freeze_path = "../research/freeze.json"
''' + policy_text
        paths[period] = root / f'configs/{period}.toml'
        write_once(paths[period], text)
    config = load_config(paths['development'])
    contract = build_contract(
        synthetic=True, periods=periods, data_methodology='synthetic-v1',
        tax_policy_sha256=policy_sha256(config.tax), tax_policy=policy_record(config.tax),
        calendar_sha256=calendar.sha256, calendar_authority_sha256=calendar.authority_sha256,
    )
    freeze = build_freeze(config, contract,
        input_manifest_sha256=synthetic_input_sha256(config),
        charter_text='SYNTHETIC BA-002 demonstration only. Not a historical charter freeze.')
    write_once(root / 'research/freeze.json', json_text(freeze))
    data = generate_synthetic_market_data(SYMBOLS, START, END, seed=21, annual_cash_rate=0.02)
    # Zero distributions are deliberate: the adjusted and cash-price units are
    # identical in this generated dataset. Tax mechanics have separate fixtures.
    rows = ['date,symbol,close,dividend']
    for day in data.dates:
        for symbol in sorted(SYMBOLS):
            rows.append(f'{day},{symbol},{data.bar(day, symbol).close!r},0.0')
    write_once(root / 'data/distributions_daily.csv', '\n'.join(rows) + '\n')
    write_once(root / 'data/manifest.json', json_text({
        'methodology': 'synthetic-ba002-demo-v1', 'splits': {symbol: [] for symbol in SYMBOLS},
        'synthetic': True,
    }))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    paths = prepare_ba002_demo(parser.parse_args().directory)
    print('SYNTHETIC ONLY — no economic meaning, no historical authorization.')
    for period in ('development', 'validation'):
        print(f'boring-alpha sweep "{paths[period]}"')
    print('Use the exact sweep paths printed by those commands with boring-alpha classify.')


if __name__ == '__main__':
    main()
