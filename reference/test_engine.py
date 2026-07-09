"""Tests for the reference engine (engine.py), run against
languages/mizo.yaml's own `examples:` block -- see docs/architecture.md's
"conformance vectors" idea. These examples are still UNVERIFIED Mizo
(see the TODO(verify) tags in mizo.yaml itself); these tests check that the
engine correctly implements the grammar as written, not that the grammar is
linguistically correct.
"""

from pathlib import Path

import pytest

from engine import load

MIZO_SPEC_PATH = Path(__file__).resolve().parent.parent / "languages" / "mizo.yaml"


@pytest.fixture(scope="module")
def spec():
    return load(MIZO_SPEC_PATH)


def test_examples_match(spec):
    for example in spec.examples:
        n = example["number"]
        expected = example["text"]
        assert spec.number_to_text(n) == expected, f"n={n}"


@pytest.mark.parametrize("n", range(0, 101))
def test_every_number_in_range_has_a_matching_rule(spec, n):
    # Every number in the supported range must match some grammar rule --
    # this catches gaps/overlaps in rule ranges even for numbers we don't
    # have a hand-written example for.
    spec.number_to_text(n)


def test_out_of_range_raises(spec):
    with pytest.raises(ValueError):
        spec.number_to_text(101)
    with pytest.raises(ValueError):
        spec.number_to_text(-1)
