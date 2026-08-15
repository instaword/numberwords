"""Shared fixtures for the package's own tests.

These tests import numberwords from src/ rather than from an installed
copy, the same way the reference suite imports engine.py by running from
inside reference/. That keeps `pytest` working with no install step.

What that deliberately does *not* prove is that the built distribution
contains everything -- a src/ layout can pass every test here and still
ship a wheel missing _mizo.py. The wheel smoke test in CI is what covers
that, and it is the only thing that does.
"""

import json
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
VECTORS_PATH = REPO_ROOT / "vectors" / "mizo.json"

sys.path.insert(0, str(PACKAGE_ROOT / "src"))


@pytest.fixture(scope="session")
def vectors():
    with open(VECTORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
