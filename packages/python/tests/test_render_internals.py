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
    # _rule_matches ignores literals and compares only placeholders, so a
    # literal must be something _tokenize also removes -- otherwise it would
    # be emitted on one side and matched on neither. Exactly two things
    # qualify: word separators, which the split consumes, and connector
    # words, which _tokenize drops by design (#10).
    #
    # Before #19 every literal was a separator and this asserted just that.
    # The hundreds rules put "leh" in the template (Q-M on #27) -- the first
    # literal that is a word rather than punctuation. A literal that is
    # neither, such as a suffix or a particle, still fails here, which is
    # the case this test exists for.
    for rule in _render.RULES:
        for template in (rule["output"],) + tuple(rule["parse_aliases"]):
            for item in template:
                if isinstance(item, tuple):
                    continue
                words = [
                    _render._normalize_word(w)
                    for w in _render._SEPARATOR_RE.split(item)
                    if w
                ]
                # A pure separator splits to nothing, which passes vacuously
                # -- that is the pre-#19 case, unchanged.
                assert all(w in _render._CONNECTORS for w in words), (rule["name"], item)


@pytest.mark.parametrize(
    "n, expected",
    [(0, (0, 0)), (7, (7, 0)), (58, (8, 5)), (100, (0, 0)), (118, (8, 1)), (199, (9, 9))],
)
def test_positional_variables_match_the_engines_definition(n, expected):
    # ones_digit is n % 10 and tens_digit is (n // 10) % 10 -- the compiler
    # emits conditions written against exactly those, so a target that
    # computed them differently would evaluate the conditions differently.
    #
    # This was added when 100 was the only case no vector reached: dropping
    # the modulo from tens_digit changed nothing in 0-100, and it was the
    # one mutation the suite did not catch. #19 is the range extension that
    # comment predicted -- at 118 the modulo is load-bearing ((118 // 10)
    # is 11, which is not a units key at all), so the vectors now catch it
    # too. Kept as the direct statement of the definition, and 118 and 199
    # are pinned here so it stays that way.
    variables = _render._positional_variables(n)
    assert (variables["ones_digit"], variables["tens_digit"]) == expected


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
    # "sawm hnih" is 20 via exact_tens. If leniency applied to every slot
    # it would also match teens' ones-digit slot for 12, and the two
    # readings would collide.
    assert numberwords.text_to_number("sawm hnih") == 20
    strict = _render._acceptable_fields("units", "bound", lenient=False)
    assert strict == ["bound"]


def test_parse_aliases_are_accepted():
    # compound_tens declares a shorthand that drops the scale word: "hnih
    # hnih" for 22. Never produced by number_to_text(), always accepted.
    assert numberwords.text_to_number("hnih hnih") == 22
    assert numberwords.number_to_text(22) == "sawm hnih pahnih"


def test_spelling_aliases_resolve_to_the_canonical_word(monkeypatch):
    # parse.aliases (spec-wide spelling variants), not a rule's
    # parse_aliases (alternate templates) tested above -- the names are
    # unhelpfully close. mizo.yaml declares `aliases: {}` (#15), so no
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
    # #40. Splitting on word_separators leaves an empty string wherever two
    # separators meet or one sits at either end, and _tokenize drops those.
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
    # parse_text collects every matching number and only then decides. The
    # tempting version returns on the first hit, which is indistinguishable
    # on the real spec -- nothing there is ambiguous -- and hides a genuine
    # spec fault behind a plausible answer. Force an ambiguity to prove the
    # collect-all behaviour is really there.
    lexicon = copy.deepcopy(_render.LEXICON)
    lexicon["units"][2]["standalone"] = lexicon["units"][1]["standalone"]
    monkeypatch.setattr(_render, "LEXICON", lexicon)

    with pytest.raises(numberwords.NumberWordsError, match=r"ambiguous"):
        numberwords.text_to_number("pakhat")


def test_a_bound_form_is_rejected_as_the_final_addend():
    # Q-E on #27: an addend takes the standalone form, so "zâ leh riat" is
    # not a rival reading of 108 -- it is not Mizo. The vectors structurally
    # cannot state this: they list what must be *accepted*, never what must
    # be rejected, so a target that accepted it would pass conformance.
    with pytest.raises(numberwords.NumberWordsError):
        numberwords.text_to_number("zâ leh riat")


def test_stacked_scales_are_not_accepted_below_ten_to_the_fifth():
    # Q-K on #27, as revised: scale words multiply each other from 10^5 up
    # only. Under the withdrawn "every scale" reading "za sawm hnih" would
    # have been 120 and 10^2 x 20 = 2,000 at once. Same reason as above --
    # only a rejection test can pin the boundary.
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
