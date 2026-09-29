"""Behaviour the vectors cannot reach, and the constraints on what ships.

Everything here is either an invariant the current data cannot exercise, or
a promise about the distribution itself. The conformance suite is the main
event; these are the gaps it structurally cannot cover.
"""

import copy
import re
from pathlib import Path

import numberwords
import pytest
from numberwords import _render

PACKAGE_SOURCE = Path(_render.__file__).resolve().parent


def test_every_literal_in_a_template_is_a_separator_or_a_connector():
    # The parser skips literals and matches only placeholders, so a literal
    # must be something _tokenize also removes -- otherwise it would be
    # emitted on one side and matched on neither. Exactly two things
    # qualify: word separators, which the split consumes, and connector
    # words, which _tokenize drops by design (#10).
    #
    # Since #65 Mizo's "leh" is written by grammar.connector rather than by
    # a literal in ten templates, so today every literal is a separator
    # again. A literal that is a connector stays legal; one that is neither,
    # such as a suffix or a particle, still fails here, which is the case
    # this test exists for. Segments are walked too: a literal inside [...]
    # is emitted whenever the remainder is.
    def literals(items):
        for item in items:
            if isinstance(item, str):
                yield item
            elif item[0] == "optional":
                yield from literals(item[1])

    for rule in _render.RULES:
        for item in literals(rule["output"]):
            words = [
                _render._normalize_word(w)
                for w in _render._SEPARATOR_RE.split(item)
                if w
            ]
            # A pure separator splits to nothing, which passes vacuously.
            assert all(w in _render._CONNECTORS for w in words), (rule["name"], item)


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, "units"), (9, "units"),
        (10, "ten"), (19, "ten"),
        (20, "tens"), (99, "tens"),
        (100, "hundred"), (199, "hundred"),
        (200, "hundreds"), (999, "hundreds"),
        (1000, "thousands"), (9_999, "thousands"),
        (10_000, "ten_thousands"), (99_999, "ten_thousands"),
        (100_000, "hundred_thousands"), (999_999, "hundred_thousands"),
        (1_000_000, "millions"), (9_999_999, "millions"),
        (10_000_000, "ten_millions"), (99_999_999, "ten_millions"),
        (100_000_000, "hundred_millions"), (999_999_999, "hundred_millions"),
        (1_000_000_000, "billions"), (9_999_999_999, "billions"),
    ],
)
def test_rule_selection_follows_the_scale(n, expected):
    # The largest emitting scale not above n, then the first rule at that
    # scale whose fixed multiplier and condition hold -- 0 falling to the
    # smallest scale, since none is below it. Every boundary is pinned on
    # both sides, because an off-by-one in scale selection (`<` for `<=`)
    # moves exactly one number: 10 would render through the units rule and
    # hit a lexicon key that does not exist, and the vectors would say so
    # only as a KeyError. This states the definition directly. It is the
    # successor to the test that pinned ones_digit and tens_digit before
    # #65 removed them.
    assert _render._find_rule(n)["name"] == expected


def test_the_field_a_template_names_is_accepted_even_if_the_list_omits_it():
    # The renderer trap (#31). mizo.yaml declares `units: [bound]`, listing
    # only the extra form, so a version of _acceptable_fields that read the
    # list alone would stop accepting "pakhat". The vectors catch that too
    # -- deliberately, since that is why `standalone` was removed from the
    # list -- but state it directly rather than relying on a side effect.
    assert _render._acceptable_fields("units", "standalone", lenient=True) == [
        "standalone",
        "bound",
    ]
    assert numberwords.text_to_number("pakhat") == 1
    assert numberwords.text_to_number("khat") == 1


def test_a_table_the_spec_does_not_name_gets_exact_matching():
    assert _render._acceptable_fields("scales", "standalone", lenient=True) == [
        "standalone"
    ]


def test_leniency_does_not_apply_inside_a_multi_word_phrase():
    # "sawm hnih" is 20 via `tens`. If leniency applied to every slot it
    # would also read as sâwm + 2 through `ten`'s remainder, and the two
    # readings would collide.
    assert numberwords.text_to_number("sawm hnih") == 20
    strict = _render._acceptable_fields("units", "bound", lenient=False)
    assert strict == ["bound"]


def test_leniency_does_not_leak_into_a_remainder():
    # #65. A remainder is rendered by the units rule, a single placeholder,
    # which is exactly what leniency used to be keyed on. Keyed on the whole
    # input being one word instead, so "sawm khat" and "zâ khat" stay what
    # they were before recursion: not Mizo. The vectors cannot say so --
    # they list only what must be accepted.
    assert numberwords.text_to_number("khat") == 1
    for text in ("sawm khat", "zâ khat"):
        with pytest.raises(numberwords.NumberWordsError):
            numberwords.text_to_number(text)


def test_the_shorthand_is_only_ever_a_whole_phrase():
    # `scope: whole` (#65). Without it the shorthand could stand in as a
    # remainder and "za hnih khat" would read as 121. Found by the 3-token
    # sweep while prototyping the format, and invisible to the vectors for
    # the same reason as the test above.
    assert numberwords.text_to_number("hnih khat") == 21
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number("za hnih khat")


def test_the_unemitted_shorthand_is_accepted():
    # tens_shorthand is `emit: never`: "hnih hnih" for 22 drops the scale
    # word. Never produced by number_to_text(), always accepted.
    assert numberwords.text_to_number("hnih hnih") == 22
    assert numberwords.number_to_text(22) == "sawm hnih pahnih"


def test_spelling_aliases_resolve_to_the_canonical_word(monkeypatch):
    # parse.aliases (spec-wide spelling variants), not an `emit: never`
    # rule (an alternate template) tested above -- until #65 the second was
    # called parse_aliases, which is why these two tests used to need this
    # note more than they do now. mizo.yaml declares `aliases: {}` (#15), so no
    # vector reaches this path and the suite passes with the lookup deleted
    # from _tokenize. #27 populates it later; the code ships before that.
    #
    # The alias is a placeholder, not Mizo, and the circumflex sits on the
    # invented part so nothing here reads as a claim about spelling.
    # Patching the built dict skips the build-time normalisation of the
    # table itself; the engine's test covers that side.
    monkeypatch.setattr(_render, "_ALIASES", {"alt_spelling": "pakhat"})

    assert numberwords.text_to_number("alt_spelling") == 1
    assert numberwords.text_to_number("pakhat") == 1
    # Normalised before the lookup, not after -- otherwise an alias would
    # only work when typed one exact way.
    assert numberwords.text_to_number("ÂLT_SPELLING") == 1


@pytest.mark.parametrize(
    "text",
    [
        " sawm nga pariat",       # leading
        "sawm nga pariat ",       # trailing
        "sawm  nga pariat",       # repeated
        " sawm  nga   pariat ",   # all three at once
        "sawm-nga pariat",        # a mix of the two separators
        "sawm--nga-pariat",       # repeated, on the other separator
    ],
)
def test_stray_and_repeated_separators_are_ignored(text):
    # #40. Splitting on the effective separators leaves an empty string
    # wherever two separators meet or one sits at either end, and _tokenize
    # drops those.
    # The vectors cannot reach it -- every accepted_input is built by
    # joining words, so all of them are well-formed -- and the engine has
    # the same behaviour and the same gap.
    assert numberwords.text_to_number(text) == 58


@pytest.mark.parametrize("text", [" ", "   ", "-", " - "])
def test_text_that_is_only_separators_raises(text):
    # Same code path, opposite outcome: no tokens survive, so nothing
    # matches. "" is covered in test_api.py with the other bad input; these
    # are the cases that only exist because the filter runs.
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number(text)


def test_ambiguity_raises_instead_of_returning_the_first_match(monkeypatch):
    # parse_text collects every derivation's number and only then decides.
    # The tempting version returns on the first hit, which is indistinguishable
    # on the real spec -- nothing there is ambiguous -- and hides a genuine
    # spec fault behind a plausible answer. Force an ambiguity to prove the
    # collect-all behaviour is really there.
    lexicon = copy.deepcopy(_render.LEXICON)
    lexicon["units"][2]["standalone"] = lexicon["units"][1]["standalone"]
    monkeypatch.setattr(_render, "LEXICON", lexicon)

    with pytest.raises(numberwords.NumberWordsError, match=r"ambiguous"):
        numberwords.text_to_number("pakhat")


def test_a_bound_form_is_rejected_as_the_final_addend():
    # Q-E on #27: an addend takes the standalone form, so "zâ leh khat" is
    # not a rival reading of 101 -- it is not Mizo. The vectors structurally
    # cannot state this: they list what must be *accepted*, never what must
    # be rejected, so a target that accepted it would pass conformance.
    #
    # 1 is the only digit that keeps this assertion true as the range grows;
    # see the engine's copy of this test for why. Keep the two in step.
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number("zâ leh khat")


def test_stacked_scales_are_not_accepted_below_ten_to_the_fifth():
    # Q-K on #27, as revised: scale words multiply each other from 10^5 up
    # only, so "za sawm hnih" is 120 and not also 10^2 x 20 = 2,000.
    #
    # Unlike the test above, this one cannot currently fail for the reason it
    # describes: the compiled spec has no stacking rule yet, and 2,000 is
    # outside SUPPORTS besides. It pins the narrower fact that no other number
    # in range accepts the string, plus 120's canonical form.
    # Labelled rather than deleted (#36): it goes live when stacking lands
    # with the ladder, where `za` still sits below the 10^5 head-scale floor.
    assert numberwords.text_to_number("za sawm hnih") == 120
    assert numberwords.number_to_text(120) == "zâ leh sawm hnih"


def test_the_shipped_package_imports_nothing_it_promised_not_to():
    # Settled for #20: no PyYAML at runtime, no reading the spec file, and
    # no import from reference/. The package interprets the compiled
    # artifact and nothing else, so it can be installed on its own.
    banned = re.compile(
        r"^\s*(?:import|from)\s+(yaml|ast|reference)\b", re.MULTILINE
    )
    modules = sorted(PACKAGE_SOURCE.glob("*.py"))
    assert len(modules) == 3, [m.name for m in modules]
    for module in modules:
        source = module.read_text(encoding="utf-8")
        assert not banned.search(source), module.name


# --- #46: whitespace, and the characters that are only nearly whitespace ----
#
# Mirrored from reference/test_engine.py rather than shared, because the two
# implementations are meant to be independent -- and because conformance
# cannot join them here: every accepted_input in vectors/mizo.json is built by
# joining words with a separator the generator chose, so no vector contains an
# exotic space. Both sides pin themselves to the specification, not to each
# other, which is what "a target implements a specification" means in #46.


def test_the_whitespace_set_is_unicode_white_space():
    # Same guard as the engine's, stated independently. str.isspace() is wrong
    # by exactly four characters and never by fewer, and re's \s is the same
    # set again, so subtracting those four is the entire correction a Python
    # target needs. A Unicode update that moved the property would fail here.
    over_matched = {"\x1c", "\x1d", "\x1e", "\x1f"}
    derived = {chr(c) for c in range(0x110000) if chr(c).isspace()}
    assert set(_render._WHITESPACE) == derived - over_matched
    assert len(_render._WHITESPACE) == len(set(_render._WHITESPACE)) == 25


def test_the_renderer_does_not_trust_the_compiled_separator_tuple():
    # The mistake #46 sets up and this test closes. After the spec dropped
    # " ", PARSE["word_separators"] is ("-",) -- a renderer that builds its
    # split from that alone stops splitting on spaces while every other test
    # here still passes on single-word input. Stated as a property of the
    # compiled artifact so it fails if a future spec edit re-adds " " and
    # hides the dependency again.
    assert " " not in _render.PARSE["word_separators"]
    assert numberwords.text_to_number("sawm nga pariat") == 58


@pytest.mark.parametrize(
    "gap",
    [
        "\t", "\n", "\v", "\f", "\r",   # U+0009-U+000D
        "\x85",                         # NEXT LINE
        "\xa0",                         # NO-BREAK SPACE
        "\u1680",                       # OGHAM SPACE MARK
        "\u2003",                       # EM SPACE
        "\u2028",                       # LINE SEPARATOR
        "\u2029",                       # PARAGRAPH SEPARATOR
        "\u202f",                       # NARROW NO-BREAK SPACE
        "\u205f",                       # MEDIUM MATHEMATICAL SPACE
        "\u3000",                       # IDEOGRAPHIC SPACE
        "  ",                           # repeated
        " \t ",                         # mixed
    ],
)
def test_any_unicode_whitespace_separates_words(gap):
    assert numberwords.text_to_number("sawm" + gap + "nga pariat") == 58


@pytest.mark.parametrize("char", ["\x1c", "\x1d", "\x1e", "\x1f"])
def test_a_c0_separator_that_is_not_white_space_is_rejected(char):
    # The case that fails closed. A target built on str.isspace() parses this
    # and diverges from the oracle while passing every vector, so this test is
    # the only thing standing there on this side too.
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number("sawm" + char + "nga pariat")


# Enumerated by position rather than by example. The first version of this
# list covered position 0, the end of the string, beside a word and inside a
# word -- every position except standing alone between two separators, which
# was the one the implementation got wrong (#56). The examples and the code
# had come out of the same mental model, so the gap was invisible from both
# sides. Where a check has a positional dimension, enumerate the positions.
#
# Mirrored from reference/test_engine.py, not shared: the two
# implementations are independent and no vector can join them here.
IGNORABLE_POSITIONS = {
    "start of the string": "\ufeffsawm nga pariat",
    "end of the string": "sawm nga pariat\ufeff",
    "start of an inner word": "sawm \ufeffnga pariat",
    "end of an inner word": "sawm\u2060 nga pariat",
    "inside a word": "sa\xadwm nga pariat",
    "standing alone between separators": "sawm \u200b nga pariat",
    "standing alone, two of them": "sawm \u200b\ufeff nga pariat",
    "standing alone at the end": "sawm nga pariat \u00ad",
}


@pytest.mark.parametrize("position", sorted(IGNORABLE_POSITIONS))
def test_ignorable_characters_are_stripped(position):
    assert numberwords.text_to_number(IGNORABLE_POSITIONS[position]) == 58


def test_a_zero_width_character_is_not_a_separator():
    # Stripped, not treated as a separator (#46), so this reads as one
    # run-together word and matches nothing. The intended answer, not a gap.
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number("sawm\u200bnga pariat")


def test_the_declared_separator_still_works_beside_whitespace():
    assert numberwords.text_to_number("sawm-nga pariat") == 58
    assert numberwords.text_to_number("sawm\t-\xa0nga pariat") == 58
