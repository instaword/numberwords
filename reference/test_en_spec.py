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

Scope is 0-999. The hundreds rule writes "and" before the remainder
("three hundred and five"). That is the canonical form; "three hundred
five" is accepted, because "and" is dropped before matching (#82). Below
100 the same word is still ignorable filler.
"""

import copy
from pathlib import Path

import pytest

import generate_vectors
from engine import Spec, load

EN_SPEC_PATH = Path(__file__).resolve().parent.parent / "languages" / "en.yaml"


@pytest.fixture(scope="module")
def en():
    return load(EN_SPEC_PATH)


def test_spec_loads_in_the_engine(en):
    # Before #29 this raised KeyError: 'output' -- en.yaml was written in a
    # format the engine never implemented.
    assert en.supports == {"min": 0, "max": 999}


def test_examples_match(en):
    # Hand-written in the spec, independent of the engine: catches a rule
    # change that silently alters output. Same role as mizo.yaml's examples.
    for example in en.examples:
        assert en.number_to_text(example["number"]) == example["text"]


@pytest.mark.parametrize("n", range(0, 1000))
def test_round_trip_number_text_number(en, n):
    assert en.text_to_number(en.number_to_text(n)) == n


@pytest.mark.parametrize("n", range(0, 1000))
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
        (100, "one hundred"),
        (101, "one hundred and one"),
        (110, "one hundred and ten"),
        (115, "one hundred and fifteen"),
        (120, "one hundred and twenty"),
        (121, "one hundred and twenty-one"),
        (305, "three hundred and five"),
        (999, "nine hundred and ninety-nine"),
    ],
)
def test_number_to_text(en, n, expected):
    assert en.number_to_text(n) == expected


def test_teens_are_keyed_by_the_remainder_not_by_value(en):
    # en.yaml keys its teens table 0-9 rather than 10-19, because the format's
    # lookup keys are multiplier, remainder or a literal integer -- there is
    # no whole-number key. `teens` is a scale-10 rule with multiplier 1, so
    # its remainder is the ones digit. This asserts the modelling actually
    # holds rather than happening to work for the values in examples:.
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
        ("twenty and one", 21),  # "and" is filler here: nothing writes it
        ("one hundred and", 100),  # a dangling "and" with no remainder
        ("and three hundred and five", 305),  # leading filler
        ("three hundred and and five", 305),  # a doubled "and" is still one
        ("THREE HUNDRED AND FIVE", 305),
        ("three hundred five", 305),  # American form, "and" dropped (#82)
        ("one hundred one", 101),
        ("nine hundred ninety-nine", 999),
    ],
)
def test_accepted_input_forms(en, text, expected):
    assert en.text_to_number(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "twenty-ten",    # well-formed words, not a well-formed number
        "banana",        # not a numeral at all
        "",              # empty
    ],
)
def test_unparseable_text_raises(en, text):
    with pytest.raises(ValueError):
        en.text_to_number(text)


@pytest.mark.parametrize(
    "text",
    [
        "zero hundred",
        "zero hundred five",
        "zero hundred and five",
    ],
)
def test_a_zero_hundreds_multiplier_is_rejected(en, text):
    # Output never writes "zero hundred": number_to_text only reaches this
    # rule with a multiplier of at least 1. Dropping `multiplier > 0` changes
    # no rendering, so the round-trip tests still pass. The condition is what
    # refuses these (#98), for the same reason
    # test_no_scale_word_is_multiplied_by_zero exists for Mizo.
    with pytest.raises(ValueError):
        en.text_to_number(text)


@pytest.mark.parametrize("n", [-1, 1000])
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


def test_generator_keeps_the_canonical_output_verbatim(en):
    # Regression guard for the same hyphen, one layer up. generate_vectors
    # used to build its "canonical" variant by splitting the rendered string
    # into words and re-joining them with word_separators[0] -- which assumes
    # the literal text between placeholders is always the first separator.
    # That is true of Mizo and false here: it produced "forty two", and the
    # real canonical survived only as the alternate-separator variant,
    # because "-" happened to be second in the list below.
    #
    # Reordering removes the coincidence, so this fails if the assumption
    # comes back. It matters because vectors/mizo.json asserts that `text`
    # appears in `accepted_inputs`, and that invariant should hold by
    # construction rather than by luck -- for the second vectors file as much
    # as the first.
    assert generate_vectors.accepted_inputs(en, 42).count("forty-two") == 1

    shuffled = copy.deepcopy(en._data)
    # Whitespace is implicit since #46, so only the non-whitespace
    # separators are declared; the effective list the generator sees is
    # still (space, "/", "-"), which keeps "-" out of first place.
    shuffled["parse"]["word_separators"] = ["/", "-"]
    reordered = Spec(shuffled)
    assert reordered.number_to_text(42) == "forty-two"
    assert "forty-two" in generate_vectors.accepted_inputs(reordered, 42)


def test_single_digits_parse_without_mizo_form_names(en):
    # #31: English lexicon entries have one field, `word`, and en.yaml
    # declares no accepted_forms at all. Single digits still parse, because
    # the field a template names always matches and leniency only widens
    # from there.
    #
    # This used to pass for the opposite reason: the engine looked for
    # Mizo's `standalone`/`bound` on every one-placeholder template, and
    # en.yaml had to switch them off by name to get exact matching back.
    # The assertion is unchanged; what it proves is not.
    assert "accepted_forms" not in en.parse_config
    for n in range(0, 10):
        assert en.text_to_number(en.number_to_text(n)) == n


def test_no_connector_position_is_certified(en):
    # en.yaml declares no grammar.connector, and the generator certifies
    # connector positions only for a language that does (#65). "forty and
    # two" is tolerated by the engine and blessed by nothing. The "and" the
    # hundreds rule writes is different: it is in the canonical spelling, and
    # leaving it out is certified too, because that is the accepted American
    # form (#82).
    assert en.connector is None
    assert en.text_to_number("forty and two") == 42
    assert not any(
        "and" in candidate
        for candidate in generate_vectors.accepted_inputs(en, 42)
    )
    accepted = generate_vectors.accepted_inputs(en, 305)
    assert "three hundred and five" in accepted
    assert "three hundred five" in accepted
