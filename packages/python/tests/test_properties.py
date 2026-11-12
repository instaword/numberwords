"""The package's half of the random round-trips (#84).

Same two properties and the same draw as reference/test_properties.py.
Copied, not imported: this suite does not import the reference tests or
the engine. The range is SUPPORTS in _mizo.py, which the compiler copies
from meta.supports. The provenance test and the artifact diff already
fail if those two disagree, so a ceiling change moves these tests when
the artifact is regenerated. The spec file is not in the sdist, and this
suite is what a packager runs from there.
"""

from hypothesis import assume, example, given, settings, strategies as st

import numberwords
from numberwords._mizo import SUPPORTS

LOW, HIGH = SUPPORTS

# 100 examples per test is the budget in #84: seconds, not minutes.
# database=None keeps a run from writing .hypothesis/ into the tree.
_RUN = settings(max_examples=100, database=None)


def _edge_numbers(low, high):
    found = {low, high}
    for k in range(len(str(high))):
        power = 10 ** k
        if low <= power <= high:
            found.add(power)
        below = power - 1
        if low <= below <= high:
            found.add(below)
    return sorted(found)


def _largest_power(high):
    return 10 ** (len(str(high)) - 1)


@st.composite
def _zero_in_the_middle(draw, low, high):
    """A number with a 0 that is neither its first nor its last digit.

    See zero_in_the_middle in reference/test_properties.py. Kept in step
    with that function.
    """
    number = draw(st.integers(min_value=max(low, 100), max_value=high))
    digits = list(str(number))
    zero_at = draw(st.integers(min_value=1, max_value=len(digits) - 2))
    digits[zero_at] = "0"
    result = int("".join(digits))
    assume(result >= low)
    return result


def _numbers(low, high):
    return st.one_of(
        st.sampled_from(_edge_numbers(low, high)),
        st.integers(min_value=low, max_value=high),
        _zero_in_the_middle(low, high),
    )


_TOP_POWER = _largest_power(HIGH)
_NUMBERS = _numbers(LOW, HIGH)


@example(_TOP_POWER)
@example(HIGH)
@_RUN
@given(n=_NUMBERS)
def test_formatting_then_parsing_returns_the_number(n):
    assert numberwords.text_to_number(numberwords.number_to_text(n)) == n


@example(_TOP_POWER)
@example(HIGH)
@_RUN
@given(n=_NUMBERS)
def test_parsing_then_formatting_returns_the_canonical_spelling(n):
    text = numberwords.number_to_text(n)
    assert numberwords.number_to_text(numberwords.text_to_number(text)) == text
