"""Shared fixtures. Tests read recorded outputs in demo-state/ and need no Pulse install."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "demo-state"


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def state() -> Path:
    return STATE


def load(rel: str):
    p = STATE / rel
    if not p.exists():
        pytest.skip(f"{rel} not recorded yet")
    return json.loads(p.read_text())


@pytest.fixture(scope="session")
def loadj():
    return load
