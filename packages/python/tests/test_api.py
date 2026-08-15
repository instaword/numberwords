"""The public surface: two functions and one exception, nothing else.

A published package's API is the part that cannot be changed quietly, so
what is *absent* is asserted as deliberately as what is present.
"""

import numberwords
import pytest


def test_public_names_are_exactly_the_three_agreed():
    assert sorted(numberwords.__all__) == [
        "NumberWordsError",
        "number_to_text",
        "text_to_number",
    ]


def test_nothing_else_leaks_into_the_package_namespace():
    # Everything public must be in __all__. Helpers keep their leading
    # underscore, and imported submodules (_render, _mizo) are private by
    # the same rule. This is what stops an implementation detail becoming
    # something a caller can depend on by accident.
    public = {name for name in vars(numberwords) if not name.startswith("_")}
    assert public == set(numberwords.__all__)


def test_version_is_declared():
    assert numberwords.__version__ == "0.1.0"


def test_it_converts_both_ways():
    assert numberwords.number_to_text(58) == "sawm nga pariat"
    assert numberwords.text_to_number("sawm nga pariat") == 58


@pytest.mark.parametrize("n", [-1, 101, 1000])
def test_out_of_range_raises(n):
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.number_to_text(n)


@pytest.mark.parametrize("text", ["not mizo words", "", "pakhat pakhat"])
def test_unparseable_text_raises(text):
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number(text)


@pytest.mark.parametrize("n", ["58", 5.0, 5.5, None, True, [5]])
def test_number_to_text_rejects_anything_that_is_not_an_int(n):
    # Without the guard these leak the internals: 5.5 raises KeyError from
    # a lexicon lookup, "58" raises TypeError from the range comparison,
    # and True quietly answers "pakhat" because bool subclasses int. One
    # documented failure mode is worth more than faithfulness to the
    # engine here -- the engine is never handed a caller's arguments.
    with pytest.raises(numberwords.NumberWordsError, match=r"expected an int"):
        numberwords.number_to_text(n)


@pytest.mark.parametrize("text", [58, None, ["pakhat"], b"pakhat"])
def test_text_to_number_rejects_anything_that_is_not_a_str(text):
    with pytest.raises(numberwords.NumberWordsError, match=r"expected a str"):
        numberwords.text_to_number(text)


def test_the_error_reports_the_public_module_in_a_traceback():
    # The class is defined in _render.py, so an uncorrected __module__ makes
    # every traceback name a private module. Part of the public shape rather
    # than cosmetics: it is what a user pastes into a bug report or searches
    # for. Catching is unaffected either way, which is why nothing else here
    # would notice the name being wrong.
    assert numberwords.NumberWordsError.__module__ == "numberwords"
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.number_to_text(101)


def test_the_error_is_a_valueerror():
    # Callers who already catch ValueError keep working; this is why the
    # exception subclasses it rather than Exception.
    assert issubclass(numberwords.NumberWordsError, ValueError)
    with pytest.raises(ValueError):
        numberwords.number_to_text(101)


def test_the_error_message_names_the_supported_range():
    # A bare "invalid value" tells a caller nothing about what to do next.
    with pytest.raises(numberwords.NumberWordsError, match=r"\[0, 100\]"):
        numberwords.number_to_text(101)
