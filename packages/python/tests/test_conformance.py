"""The package against vectors/mizo.json and vectors/mizo.phrases.json.

This is the contract. The reference engine generates the vectors; this
package is checked against them; neither imports the other. That is the
whole point of the conformance table -- a target is correct when it agrees
with the checked-in file, not when it agrees with a copy of the oracle
sitting next to it.

Both directions are checked, and the parse direction iterates
`accepted_inputs` rather than just `text`. A test that only round-trips
`text` re-creates the exact gap #12 was filed to close: every alternate
spelling the engine tolerates would go unchecked in the target.

The vectors only say what must be accepted, so a parser that accepts too
much passes all of them. The phrase file covers the other half (#75): every
phrase of up to three words its vocabulary can spell, each either listed
with the number it names or, by being left out, rejected.
"""

import itertools

import pytest

import numberwords

# The generated table for Mizo 0-9,999,999,999: all of 0-999, and above
# it one number of each shape plus #27's structural cases (#12, #65).
# Asserted rather than assumed: an empty or truncated vectors file would
# otherwise make every parametrised test below pass by having nothing to run.
#
# Both move with supports.max, and both are range knobs a range PR has to
# bump by hand -- that is the point of stating them rather than deriving
# them from the file being checked.
EXPECTED_VECTORS = 1234
EXPECTED_ACCEPTED_INPUTS = 7644

# The phrase file's size, asserted for the same reason. These move with the
# vocabulary rather than the range: a new scale word or alias grows all
# three, and a range PR that adds one has to bump them by hand too.
EXPECTED_PHRASE_VOCABULARY = 31
EXPECTED_PHRASES = 30783
EXPECTED_ACCEPTED_PHRASES = 2245


def test_the_vector_table_is_the_size_it_should_be(vectors):
    assert len(vectors) == EXPECTED_VECTORS
    total = sum(len(v["accepted_inputs"]) for v in vectors)
    assert total == EXPECTED_ACCEPTED_INPUTS


def test_every_vector_has_the_fields_this_suite_reads(vectors):
    for vector in vectors:
        # `number` is a *string* in the file (JSON object keys and this
        # field are both stringified on purpose). Reading it as an int
        # without converting silently compares int to str and passes
        # nothing.
        assert isinstance(vector["number"], str)
        assert isinstance(vector["text"], str)
        assert vector["accepted_inputs"], vector["number"]
        # The canonical spelling must itself be an accepted input --
        # otherwise the parse direction below could pass while the output
        # of number_to_text() did not parse back.
        assert vector["text"] in vector["accepted_inputs"]


def test_number_to_text_matches_every_vector(vectors):
    for vector in vectors:
        n = int(vector["number"])
        assert numberwords.number_to_text(n) == vector["text"], n


def test_text_to_number_accepts_every_accepted_input(vectors):
    checked = 0
    for vector in vectors:
        n = int(vector["number"])
        for text in vector["accepted_inputs"]:
            assert numberwords.text_to_number(text) == n, text
            checked += 1
    # Guards the loop itself: an empty accepted_inputs list anywhere would
    # otherwise reduce this test to a no-op without failing.
    assert checked == EXPECTED_ACCEPTED_INPUTS


def test_round_trip_number_text_number(vectors):
    # Every number in the table, which is every number the package is
    # certified for. This used to walk range(0, 101) and was never widened
    # when the range reached 199 and then 999; reading the table is what
    # keeps it from going stale again.
    for vector in vectors:
        n = int(vector["number"])
        assert numberwords.text_to_number(numberwords.number_to_text(n)) == n, n


def test_round_trip_text_number_text(vectors):
    # The other direction: re-emitting a parsed input gives the canonical
    # spelling back, not merely something that parses.
    for vector in vectors:
        for text in vector["accepted_inputs"]:
            n = numberwords.text_to_number(text)
            assert numberwords.number_to_text(n) == vector["text"], text


def _every_phrase(phrases):
    """Every phrase the phrase file covers: 1 to max_words words from its
    vocabulary, joined by one space -- the same phrases the generator
    parsed, built here rather than imported, since the package never
    imports the oracle."""
    for length in range(1, phrases["max_words"] + 1):
        for words in itertools.product(phrases["vocabulary"], repeat=length):
            yield " ".join(words)


def test_the_phrase_file_is_the_size_it_should_be(phrases):
    assert len(phrases["vocabulary"]) == EXPECTED_PHRASE_VOCABULARY
    assert sum(1 for _ in _every_phrase(phrases)) == EXPECTED_PHRASES
    assert len(phrases["accepted"]) == EXPECTED_ACCEPTED_PHRASES


# One row per kind of word the vocabulary is built from
# (generate_vectors.phrase_vocabulary), so a generator that stopped adding
# one kind fails a row named after it.
@pytest.mark.parametrize(
    "kind, word",
    [
        ("a unit's standalone form", "pakhat"),
        ("a unit's bound form", "khat"),
        ("a scale word", "za"),
        ("a connector", "leh"),
        ("an alias spelling", "nuaih"),
    ],
)
def test_the_phrase_vocabulary_has_every_kind_of_word(phrases, kind, word):
    assert word in phrases["vocabulary"], kind


def test_text_to_number_agrees_with_the_phrase_file(phrases):
    # Closed-world, both halves at once: a listed phrase must give its
    # number, and every phrase that is not listed must be rejected. The
    # second half is what the vectors cannot state.
    accepted = phrases["accepted"]
    built = set()
    wrong = []
    for text in _every_phrase(phrases):
        built.add(text)
        try:
            got = numberwords.text_to_number(text)
        except numberwords.NumberWordsError:
            got = None
        expected = int(accepted[text]) if text in accepted else None
        if got != expected:
            wrong.append((text, expected, got))
    assert not wrong, wrong[:10]
    # A listed phrase the loop never builds would never be checked.
    assert set(accepted) <= built, sorted(set(accepted) - built)[:10]
