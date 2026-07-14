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


def test_examples_parse_back(spec):
    for example in spec.examples:
        assert spec.text_to_number(example["text"]) == example["number"]


@pytest.mark.parametrize("n", range(0, 101))
def test_round_trip_number_text_number(spec, n):
    # number -> text -> number must return the original value.
    assert spec.text_to_number(spec.number_to_text(n)) == n


@pytest.mark.parametrize("n", range(0, 101))
def test_round_trip_text_number_text(spec, n):
    # text -> number -> text must be stable for canonical text.
    text = spec.number_to_text(n)
    assert spec.number_to_text(spec.text_to_number(text)) == text


def test_connector_word_is_ignored(spec):
    # "leh" is a connector (parse.connectors in mizo.yaml) and must not
    # affect parsing even though number_to_text() never produces it.
    assert spec.text_to_number("sawm hnih leh pahnih") == 22
    assert spec.text_to_number("sawm leh pahnih") == spec.text_to_number("sawm pahnih")


def test_text_to_number_is_case_insensitive(spec):
    assert spec.text_to_number("SAWM HNIH") == 20


def test_unparseable_text_raises(spec):
    with pytest.raises(ValueError):
        spec.text_to_number("not mizo words")


@pytest.mark.parametrize("n", range(0, 10))
def test_freestanding_digit_accepts_bound_form(spec, n):
    # A lone digit may be spoken in bound form too, e.g. "khat" as well as
    # the canonical standalone "pakhat" for 1 -- parse.accepted_forms in
    # mizo.yaml declares both acceptable, but only for a freestanding digit;
    # multi-word rules must keep matching their named field exactly (see
    # test_bound_form_is_not_accepted_mid_phrase).
    bound_word = spec.lexicon["units"][n]["bound"]
    assert spec.text_to_number(bound_word) == n


def test_bound_form_is_not_accepted_mid_phrase(spec):
    # "sawm hnih" must mean 20 (exact_tens' canonical bound tens-digit slot),
    # not also match teens' ones-digit slot via bound-form leniency -- that
    # would make 12 and 20 ambiguous for the same input.
    assert spec.text_to_number("sawm hnih") == 20
