"""Offline paths and immutable registration for the authorized diagnostic."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = ROOT / 'data/snapshots' / HERE.name
SOURCE_HERE = HERE.with_name('insider-purchase-test-2026-09-13')
SOURCE_RAW = RAW.with_name(SOURCE_HERE.name)
POLICY_SHA = '16c563cda8d5b98367f5fd9165e066227d4f58f63bc400d6cb3a7eddc4133e0b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(b)
    tmp.replace(path)
    return hashlib.sha256(b).hexdigest()


def policy():
    p = HERE / 'experiment-policy.json'
    assert digest(p) == POLICY_SHA
    return json.loads(p.read_text())


def check_budget():
    assert datetime.now(timezone.utc) < datetime.fromisoformat(policy()['deadline_utc'])
