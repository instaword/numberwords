"""Random round-trips across the whole supported range (#84).

The conformance vectors cover every number below 1000 and one of each
shape above that. A uniform draw over 10^13 almost never hits a power of
ten or a zero digit, so the strategy mixes those in. The bounds come from
the spec, so a later ceiling moves these tests without an edit here.
"""

from pathlib import Path

from hypothesis import assume, example, given, settings, strategies as st

from engine import load

_SPEC = load(Path(__file__).resolve().parent.parent / "languages" / "mizo.yaml")
LOW = _SPEC.supports["min"]
HIGH = _SPEC.supports["max"]

# 100 examples per test is the budget in #84: seconds, not minutes.
# database=None keeps a run from writing .hypothesis/ into the tree.
_RUN = settings(max_examples=100, database=None)


def edge_numbers(low, high):
    """Powers of ten inside the range, the number below each, and both bounds."""
    found = {low, high}
    for k in range(len(str(high))):
        power = 10 ** k
        if low <= power <= high:
            found.add(power)
        below = power - 1
        if low <= below <= high:
            found.add(below)
    return sorted(found)


def largest_power(high):
    return 10 ** (len(str(high)) - 1)


TOP_POWER = largest_power(HIGH)


@st.composite
def zero_in_the_middle(draw, low, high):
    """A number with a 0 that is neither its first nor its last digit.

    Built from a number already inside the range, with one interior digit
    set to 0. That cannot pass the ceiling. Building the digits first and
    then rejecting anything above the ceiling fails the run for filtering
    once the ceiling is not a string of nines, which is the day this test
    is supposed to follow the spec without an edit.
    """
    number = draw(st.integers(min_value=max(low, 100), max_value=high))
    digits = list(str(number))
    zero_at = draw(st.integers(min_value=1, max_value=len(digits) - 2))
    digits[zero_at] = "0"
    result = int("".join(digits))
    # Zeroing a digit can step below min when min is above 0. It does not
    # today. This discards that draw; it does not catch a failed conversion.
    assume(result >= low)
    return result


def numbers(low, high):
    return st.one_of(
        st.sampled_from(edge_numbers(low, high)),
        st.integers(min_value=low, max_value=high),
        zero_in_the_middle(low, high),
    )


NUMBERS = numbers(LOW, HIGH)


@example(TOP_POWER)
@example(HIGH)
@_RUN
@given(n=NUMBERS)
def test_formatting_then_parsing_returns_the_number(n):
    assert _SPEC.text_to_number(_SPEC.number_to_text(n)) == n


@example(TOP_POWER)
@example(HIGH)
@_RUN
@given(n=NUMBERS)
def test_parsing_then_formatting_returns_the_canonical_spelling(n):
    text = _SPEC.number_to_text(n)
    assert _SPEC.number_to_text(_SPEC.text_to_number(text)) == text
