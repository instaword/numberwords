"""Tests for languages/en.yaml — the worked reference example.

These exist to check something `test_engine.py` structurally cannot: that the
rule-spec format is **language-agnostic**, which is the central claim in
docs/architecture.md. With Mizo as the only working spec, nothing could tell
the difference between "the engine interprets specs" and "the engine
implements Mizo". English is the control.

English is a good control precisely because it is unlike Mizo where it
matters: irregular teens that can't be composed, a hyphen inside the
canonical form ("forty-two") that is also a word separator when parsing, and
lexicon entries with one form each rather than two.

Scope is 0-99. English above 99 needs recursion the format doesn't have yet
(#27); a valid 0-99 spec proves more than an invalid 0-999 one.
"""

from pathlib import Path

import pytest

from engine import load

EN_SPEC_PATH = Path(__file__).resolve().parent.parent / "languages" / "en.yaml"


@pytest.fixture(scope="module")
def en():
    return load(EN_SPEC_PATH)


def test_spec_loads_in_the_engine(en):
    # Before #29 this raised KeyError: 'output' -- en.yaml was written in a
    # format the engine never implemented.
    assert en.supports == {"min": 0, "max": 99}


def test_examples_match(en):
    # Hand-written in the spec, independent of the engine: catches a rule
    # change that silently alters output. Same role as mizo.yaml's examples.
    for example in en.examples:
        assert en.number_to_text(example["number"]) == example["text"]


@pytest.mark.parametrize("n", range(0, 100))
def test_round_trip_number_text_number(en, n):
    assert en.text_to_number(en.number_to_text(n)) == n


@pytest.mark.parametrize("n", range(0, 100))
def test_round_trip_text_number_text(en, n):
    text = en.number_to_text(n)
    assert en.number_to_text(en.text_to_number(text)) == text


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, "zero"),
        (9, "nine"),
        (10, "ten"),
        (13, "thirteen"),
        (19, "nineteen"),
        (20, "twenty"),
        (21, "twenty-one"),
        (42, "forty-two"),
        (70, "seventy"),
        (99, "ninety-nine"),
    ],
)
def test_number_to_text(en, n, expected):
    assert en.number_to_text(n) == expected


def test_teens_are_keyed_by_ones_digit_not_by_value(en):
    # en.yaml keys its teens table 0-9 rather than 10-19, because the format's
    # lookup keys are positional variables or literal integers -- there is no
    # whole-number key. This asserts the modelling actually holds rather than
    # happening to work for the values in examples:.
    for ones, word in enumerate(
        ["ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    ):
        assert en.number_to_text(10 + ones) == word


@pytest.mark.parametrize(
    "text, expected",
    [
        ("forty-two", 42),      # canonical form
        ("forty two", 42),      # space instead of the canonical hyphen
        ("FORTY-TWO", 42),      # case_insensitive
        ("Ninety-Nine", 99),    # mixed case
        ("twenty and one", 21),  # "and" is a connector, dropped when parsing
    ],
)
def test_accepted_input_forms(en, text, expected):
    assert en.text_to_number(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "one hundred",   # above supports.max -- no rule generates it
        "twenty-ten",    # well-formed words, not a well-formed number
        "banana",        # not a numeral at all
        "",              # empty
    ],
)
def test_unparseable_text_raises(en, text):
    with pytest.raises(ValueError):
        en.text_to_number(text)


@pytest.mark.parametrize("n", [-1, 100, 1000])
def test_out_of_range_raises(en, n):
    with pytest.raises(ValueError):
        en.number_to_text(n)


def test_hyphen_is_both_canonical_output_and_a_separator(en):
    # Worth pinning down because it is the one place English stresses the
    # format differently from Mizo: "-" appears inside number_to_text's
    # canonical output AND in parse.word_separators. Rendering must keep it
    # while parsing must split on it.
    assert en.number_to_text(42) == "forty-two"
    assert en.text_to_number("forty-two") == 42
    assert en.text_to_number("forty two") == 42


def test_single_digits_parse_without_mizo_form_names(en):
    # Regression guard for #31. English lexicon entries have one field,
    # `word`; the engine's leniency path is hardcoded to Mizo's `standalone`
    # and `bound`. en.yaml disables that path via accepted_forms. If the
    # workaround is removed before #31 is fixed, every single digit stops
    # parsing -- this catches it as 10 clear failures rather than a puzzling
    # round-trip break.
    for n in range(0, 10):
        assert en.text_to_number(en.number_to_text(n)) == n
