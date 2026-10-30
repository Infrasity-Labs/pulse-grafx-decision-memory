"""Shared fixtures. Tests read recorded outputs in demo-state/ and need no Pulse install.

Missing evidence is never a quiet pass. With REQUIRE_EVIDENCE=1 (CI sets it) a recorded output that is missing fails the test.
Without it, a missing output skips the test, which is the right thing in a fork that has not run every step yet.
"""
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "demo-state"
REQUIRE_EVIDENCE = os.environ.get("REQUIRE_EVIDENCE") == "1"


def missing(what: str) -> None:
    """A recorded output or an installed package that a test needs is not there: fail under REQUIRE_EVIDENCE=1, skip otherwise."""
    if REQUIRE_EVIDENCE:
        pytest.fail(f"REQUIRE_EVIDENCE=1 and {what}", pytrace=False)
    pytest.skip(what)


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def state() -> Path:
    return STATE


def load(rel: str):
    p = STATE / rel
    if not p.exists():
        missing(f"{rel} not recorded yet")
    return json.loads(p.read_text())


@pytest.fixture(scope="session")
def loadj():
    return load
