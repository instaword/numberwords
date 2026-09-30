"""The package against vectors/mizo.json.

This is the contract. The reference engine generates the vectors; this
package is checked against them; neither imports the other. That is the
whole point of the conformance table -- a target is correct when it agrees
with the checked-in file, not when it agrees with a copy of the oracle
sitting next to it.

Both directions are checked, and the parse direction iterates
`accepted_inputs` rather than just `text`. A test that only round-trips
`text` re-creates the exact gap #12 was filed to close: every alternate
spelling the engine tolerates would go unchecked in the target.
"""

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
EXPECTED_ACCEPTED_INPUTS = 7387


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
