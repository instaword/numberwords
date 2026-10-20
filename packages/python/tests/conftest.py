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

# Two places the vectors files can be, and both are normal.
#
# In the repository they sit at the root, two levels up. In an unpacked sdist
# there is no repository -- pyproject force-includes them at the distribution
# root instead, which is PACKAGE_ROOT there. Checking for the file rather than
# guessing from the layout keeps `pytest` working in both, which is what lets a
# downstream packager verify the release the same way CI does.
_VECTORS_DIRS = (
    PACKAGE_ROOT.parent.parent / "vectors",
    PACKAGE_ROOT / "vectors",
)

sys.path.insert(0, str(PACKAGE_ROOT / "src"))


def _load_vectors_file(name):
    candidates = [directory / name for directory in _VECTORS_DIRS]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    # Never skip. A conformance suite that quietly runs zero tests when it
    # cannot find its table is worse than one that fails.
    raise AssertionError(
        f"{name} not found; looked in " + ", ".join(str(p) for p in candidates)
    )


@pytest.fixture(scope="session")
def vectors():
    return _load_vectors_file("mizo.json")


@pytest.fixture(scope="session")
def phrases():
    return _load_vectors_file("mizo.phrases.json")
